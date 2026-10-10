"""One bounded scheduler tick. The caller holds the repository concurrency lock."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from common import sha, successful_ci, validate_path, validate_tasks
from github_api import APIError, GitHub, StateStore

ROOT = Path(__file__).resolve().parents[2]


def event(state, tid, message):
    state["events"].append({"at": datetime.now(timezone.utc).isoformat(), "task": tid, "message": message})


def latest_ci(api, head, branch):
    runs = api.get("actions/workflows/ci.yml/runs", head_sha=head, per_page=100)["workflow_runs"]
    runs = [run for run in runs if run["head_sha"] == head and run["head_branch"] == branch]
    if not runs:
        return None, []
    run = max(runs, key=lambda item: (item["id"], item.get("run_attempt", 1)))
    jobs = api.pages(f"actions/runs/{run['id']}/jobs", "jobs", filter="latest")
    return run, jobs


def validate_remote_diff(api, task, main_sha, head):
    compare = api.get("compare/" + main_sha + "..." + head)
    files = compare.get("files", [])
    if not files or len(files) >= 300:
        raise ValueError("Empty or truncated remote diff")
    total = 0
    for item in files:
        if item["status"] not in ("added", "modified"):
            raise ValueError("Deletion/rename requires manual review")
        validate_path(item["filename"], task, added=item["status"] == "added")
        total += item.get("additions", 0) + item.get("deletions", 0)
    if total > 2500:
        raise ValueError("Diff exceeds unattended scope")


def ensure_pr(api, task, record):
    prs = api.get("pulls", state="open", head="Wang106:" + record["branch"], base="main")
    if len(prs) > 1:
        raise ValueError("Multiple PRs for task")
    if prs:
        pr = prs[0]
    else:
        pr = api.mutate("pulls", "POST", {
            "title": "Codex: " + task["title"], "head": record["branch"], "base": "main",
            "body": "Automated Codex task `" + task["id"] + "`.\n\n"
                    "Independent CI must pass for the exact head before merge. "
                    "Public sample remains read-only; real identity and internal acceptance are pending.\n\n"
                    "Acceptance:\n" + "\n".join("- " + text for text in task["acceptance"]),
        })
    record["pr"] = pr["number"]
    return pr


def retry_or_block(record, reason):
    record["status"] = "ready" if record.get("attempts", 0) < 3 else "blocked"
    record["reason"] = reason


def reconcile(api, tasks, state, main_sha, require_deployment=False):
    """Reconstruct from remote evidence, including a crash between push and state save."""
    for task in tasks:
        record = state["tasks"].get(task["id"])
        if not record or record["status"] in ("done_code", "blocked", "ready"):
            continue
        status = record["status"]
        if status == "developing":
            origin = api.get(f"actions/runs/{record['run_id']}")
            # Never reclaim a live run solely because a wall-clock lease expired.
            if origin["status"] != "completed":
                continue
            head = api.ref(record["branch"])
            if head == record["work_sha"]:
                retry_or_block(record, "Execution ended without a durable patch; resume from previous commit")
                continue
            commit = api.get("git/commits/" + head)
            marker = f"codex-auto {task['id']} run {record['run_id']} "
            if not commit["message"].startswith(marker):
                record.update(status="blocked", reason="Unexpected branch update; manual reconciliation required")
                continue
            validate_remote_diff(api, task, record["base_main_sha"], head)
            record["head_sha"] = head
            if commit["message"].startswith(marker + "checkpoint"):
                retry_or_block(record, "Recovered interrupted checkpoint; resume same branch")
                continue
            ensure_pr(api, task, record)
            record["status"] = "waiting_ci"
            event(state, task["id"], "Recovered published commit after interrupted state update")
            status = "waiting_ci"
        if status == "waiting_ci":
            pr = api.get(f"pulls/{record['pr']}")
            if pr.get("merged"):
                record.update(status="merged_pending", merge_sha=sha(pr["merge_commit_sha"]))
                continue
            if (pr["state"] != "open" or pr["base"]["ref"] != "main" or pr["head"]["ref"] != record["branch"]
                    or pr["head"]["repo"]["full_name"] != api.repo):
                record.update(status="blocked", reason="PR closed or context changed")
                continue
            if pr["head"]["sha"] != record["head_sha"]:
                record.update(status="blocked", reason="PR head changed outside scheduler")
                continue
            # A main update must be incorporated and tested; no force-push/rebase.
            if main_sha != record["base_main_sha"]:
                try:
                    merged = api.mutate("merges", "POST", {"base": record["branch"], "head": main_sha,
                        "commit_message": "chore: sync verified main into Codex task"})
                except APIError as error:
                    if error.code != 409:
                        raise
                    record.update(status="blocked", reason="Main synchronization conflict")
                    continue
                record["base_main_sha"] = main_sha
                if merged:
                    record["head_sha"] = sha(merged["sha"])
                validate_remote_diff(api, task, main_sha, record["head_sha"])
                event(state, task["id"], "Main synchronized; fresh exact-head CI required")
                continue
            run, jobs = latest_ci(api, record["head_sha"], record["branch"])
            if not run or run["status"] != "completed":
                continue
            record["ci"] = {"run_id": run["id"], "sha": run["head_sha"], "conclusion": run["conclusion"]}
            if not successful_ci(run, jobs, record["head_sha"], record["branch"]):
                retry_or_block(record, "Exact-head CI failed or required jobs missing; inspect recorded run")
                continue
            validate_remote_diff(api, task, main_sha, record["head_sha"])
            if not task["auto_merge"]:
                record.update(status="blocked", reason="Task requires manual merge")
                continue
            # Branch protection is authoritative. No bypass token, no auto-dismissal.
            try:
                result = api.mutate(f"pulls/{record['pr']}/merge", "PUT", {
                    "sha": record["head_sha"], "merge_method": "merge",
                    "commit_title": "Codex: " + task["title"]})
            except APIError as error:
                if error.code not in (403, 405, 409):
                    raise
                record.update(status="blocked", reason=f"GitHub merge gate HTTP {error.code}; no bypass attempted")
                continue
            if not result.get("merged"):
                record.update(status="blocked", reason="GitHub refused merge under repository rules")
                continue
            record.update(status="merged_pending", merge_sha=sha(result["sha"]), deployment="unverified")
            event(state, task["id"], "Merged exact tested PR head; main CI and deployment separately pending")
        if record["status"] == "merged_pending":
            run, jobs = latest_ci(api, record["merge_sha"], "main")
            if not run or run["status"] != "completed":
                continue
            if not successful_ci(run, jobs, record["merge_sha"], "main"):
                record.update(status="blocked", reason="Merged main CI failed; stop queue and repair on separate branch")
                continue
            record["main_ci"] = {"run_id": run["id"], "sha": record["merge_sha"], "conclusion": "success"}
            # deploy.yml currently proves only a Render request, not live API/schema.
            # Do not reinterpret provider checks or a skipped workflow as live success.
            if require_deployment:
                record["reason"] = "Main CI passed; independent live deployment evidence is required"
                continue
            record.update(status="done_code", reason="Code verified; live deployment remains unverified")
            event(state, task["id"], "Code accepted by exact-main CI; no production-readiness claim")


def select(tasks, state, day, daily_max=6):
    if any(record["status"] in ("developing", "waiting_ci", "merged_pending", "blocked")
           for record in state["tasks"].values()):
        return None
    if state["daily"].get(day, 0) >= daily_max:
        return None
    for task in tasks:
        if not task["enabled"]:
            continue
        record = state["tasks"].get(task["id"], {})
        if record.get("status") == "done_code":
            continue
        if all(state["tasks"].get(dep, {}).get("status") == "done_code" for dep in task["depends_on"]):
            return task
    return None


def tick(api, state_store, tasks, control_sha, run_id, daily_max=6, require_deployment=False):
    main = sha(api.ref("main"))
    if main != control_sha:
        return {"execute": "false", "reason": "Dispatcher checkout superseded; next tick uses latest main"}
    state = state_store.load(main)
    reconcile(api, tasks, state, main, require_deployment)
    state_store.save(state)
    day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
    task = select(tasks, state, day, daily_max)
    if not task:
        return {"execute": "false", "reason": "No runnable task: completed, waiting, blocked or daily budget reached"}
    run, jobs = latest_ci(api, main, "main")
    if not successful_ci(run, jobs, main, "main"):
        return {"execute": "false", "reason": "Current main requires successful exact-head CI"}
    own_pr = state["tasks"].get(task["id"], {}).get("pr")
    if any(pr["number"] != own_pr for pr in api.pages("pulls", state="open")):
        return {"execute": "false", "reason": "Another open PR exists; avoid duplicate development"}
    record = state["tasks"].setdefault(task["id"], {"branch": "codex/auto/" + task["id"], "attempts": 0})
    if record["attempts"] >= 3:
        record.update(status="blocked", reason="Task attempt budget exhausted")
        state_store.save(state)
        return {"execute": "false", "reason": record["reason"]}
    if record["attempts"] == 0:
        try:
            api.ref(record["branch"])
        except APIError as error:
            if error.code != 404:
                raise
            api.mutate("git/refs", "POST", {"ref": "refs/heads/" + record["branch"], "sha": main})
        else:
            record.update(status="blocked", reason="Unowned task branch already exists")
            state_store.save(state)
            return {"execute": "false", "reason": record["reason"]}
        record["base_main_sha"] = main
    if record["base_main_sha"] != main:
        try:
            api.mutate("merges", "POST", {"base": record["branch"], "head": main,
                                         "commit_message": "chore: sync verified main before retry"})
        except APIError as error:
            if error.code != 409:
                raise
            record.update(status="blocked", reason="Main synchronization conflict before retry")
            state_store.save(state)
            return {"execute": "false", "reason": record["reason"]}
        record["base_main_sha"] = main
    work = sha(api.ref(record["branch"]))
    record.update(status="developing", work_sha=work, run_id=str(run_id), attempts=record["attempts"] + 1)
    state["daily"][day] = state["daily"].get(day, 0) + 1
    state["daily"] = dict(sorted(state["daily"].items())[-31:])
    event(state, task["id"], "Reserved attempt before model execution; interrupted runs still count")
    state_store.save(state)
    return {"execute": "true", "task_id": task["id"], "control_sha": control_sha,
            "work_sha": work, "branch": record["branch"]}


def main():
    tasks = validate_tasks(json.loads((ROOT / "docs/automation/tasks.json").read_text()))
    if os.environ.get("AUTODEV_ENABLED") != "true":
        result = {"execute": "false", "reason": "Autodevelopment disabled"}
    else:
        api = GitHub()
        limit = int(os.environ.get("DAILY_MAX") or "6")
        if not 1 <= limit <= 6:
            raise ValueError("Daily maximum must be 1..6")
        result = tick(api, StateStore(api), tasks, sha(os.environ["CONTROL_SHA"]),
                      os.environ["GITHUB_RUN_ID"], limit, os.environ.get("REQUIRE_DEPLOYMENT") == "true")
    with open(os.environ["GITHUB_OUTPUT"], "a") as output:
        for key, value in result.items():
            output.write(key + "=" + value + "\n")
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as report:
        report.write("Codex scheduler: " + result.get("reason", "reserved " + result.get("task_id", "")) + "\n")


if __name__ == "__main__":
    main()
