"""Apply data-only model output on a fresh runner; never execute candidate code."""
import base64
import json
import os
import re
import subprocess
from pathlib import Path

from common import MAX_PATCH, sha, validate_candidate, validate_path, validate_tasks
from github_api import GitHub, StateStore
from orchestrator import ensure_pr, event, retry_or_block, validate_remote_diff

ROOT = Path(__file__).resolve().parents[2]


def git(work, *args, **kwargs):
    return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "core.fsmonitor=false",
                           "-C", str(work), *args], check=True, capture_output=True, **kwargs).stdout


def apply_and_read(work, patch, task, base, task_new_paths=()):
    if git(work, "rev-parse", "HEAD").decode().strip() != base:
        raise ValueError("Publisher checkout does not match reserved base")
    if git(work, "status", "--porcelain"):
        raise ValueError("Publisher checkout is not clean")
    # git apply itself rejects escaping paths; staged modes and scope are checked next.
    git(work, "apply", "--check", "--index", "-", input=patch)
    git(work, "apply", "--index", "-", input=patch)
    tokens = git(work, "diff", "--cached", "--name-status", "-z", "--no-renames").split(b"\0")
    entries = []
    for index in range(0, len(tokens) - 1, 2):
        status, raw_path = tokens[index:index + 2]
        if status not in (b"A", b"M"):
            raise ValueError("Deletion/rename requires manual review")
        path = raw_path.decode("utf-8")
        # Tests introduced by this task's partial checkpoint are still new to
        # main and may be completed on retry. Baseline main tests stay immutable.
        validate_path(path, task, added=status == b"A" or path in task_new_paths)
        line = git(work, "ls-files", "--stage", "--", path).decode().strip()
        mode = line.split()[0]
        if mode != "100644":
            raise ValueError("Executable/symlink/submodule candidate rejected")
        content = git(work, "show", ":" + path)
        if len(content) > 1048576:
            raise ValueError("Candidate file too large")
        if re.search(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----|\bsk-[A-Za-z0-9_-]{20,}", content):
            raise ValueError("Credential-like candidate content rejected")
        entries.append((path, content))
    if not entries or len(entries) > 50:
        raise ValueError("Empty or oversized candidate file set")
    final_patch = git(work, "diff", "--cached", "--binary")
    if len(final_patch) > MAX_PATCH:
        raise ValueError("Normalized patch too large")
    return entries


def publish(api, store, tasks, payload, tid, work_sha, run_id, work):
    state = store.load(api.ref("main"))
    task = next(task for task in tasks if task["id"] == tid)
    record = state["tasks"][tid]
    if (record["status"] != "developing" or record["run_id"] != str(run_id)
            or record["work_sha"] != work_sha):
        raise ValueError("Stale or unowned execution output")
    data, patch = validate_candidate(payload, tid, work_sha)
    if data["status"] == "blocked":
        record.update(status="blocked", reason="Codex requires review; inspect worker final result")
        event(state, tid, "Worker blocked without publishing code")
        store.save(state)
        return
    compare = api.get("compare/" + record["base_main_sha"] + "..." + work_sha)
    prior_files = compare.get("files", [])
    if len(prior_files) >= 300:
        raise ValueError("Truncated checkpoint comparison")
    task_new_paths = {item["filename"] for item in prior_files if item["status"] == "added"}
    entries = apply_and_read(work, patch, task, work_sha, task_new_paths)
    if api.ref(record["branch"]) != work_sha:
        raise ValueError("Task branch moved; refusing to overwrite")
    tree_entries = []
    for path, content in entries:
        blob = api.mutate("git/blobs", "POST", {"content": base64.b64encode(content).decode(), "encoding": "base64"})
        tree_entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    parent = api.get("git/commits/" + work_sha)
    tree = api.mutate("git/trees", "POST", {"base_tree": parent["tree"]["sha"], "tree": tree_entries})
    commit = api.mutate("git/commits", "POST", {
        "message": f"codex-auto {tid} run {run_id} {data['status']}\n\n" + task["title"],
        "tree": tree["sha"], "parents": [work_sha]})
    # A non-fast-forward update is rejected by GitHub if a writer races this call.
    api.mutate("git/refs/heads/" + record["branch"], "PATCH", {"sha": commit["sha"], "force": False})
    record["head_sha"] = sha(commit["sha"])
    validate_remote_diff(api, task, record["base_main_sha"], record["head_sha"])
    if data["status"] == "checkpoint":
        retry_or_block(record, "Partial checkpoint published; resume next bounded attempt")
    else:
        ensure_pr(api, task, record)
        record["status"] = "waiting_ci"
    event(state, tid, "Published bounded patch; completion requires independent exact-head CI")
    store.save(state)


def main():
    api = GitHub()
    tasks = validate_tasks(json.loads((ROOT / "docs/automation/tasks.json").read_text()))
    publish(api, StateStore(api), tasks, os.environ["CANDIDATE_JSON"], os.environ["TASK_ID"],
            sha(os.environ["WORK_SHA"]), os.environ["GITHUB_RUN_ID"], Path(os.environ["CANDIDATE_DIR"]))
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as report:
        report.write("Codex patch processed on clean runner; CI and deployment remain separate evidence.\n")


if __name__ == "__main__":
    main()
