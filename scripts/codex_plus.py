"""Start a user-controlled Codex session using ChatGPT authentication only."""
import argparse
import json
import os
from pathlib import Path
import shutil
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PROMPT = """继续开发 Wang106/SoftwareLifeCycle，使用当前 ChatGPT Plus 登录额度。
不要使用 API key、付费 API、购买额外额度或启用 GitHub Actions API 开发模式。
先读 AGENTS.md、START_HERE.md、REQUIREMENTS.md、DEVELOPMENT_STATUS.md、ROADMAP.md、
docs/development-plan-progress.json 和 HANDOFF.md 最新记录；核对最新 main、开放 PR 和精确 CI。
保留所有已有改动，已有未完成 PR 优先恢复，不重复实现，不 force-push。
按 docs/automation/plus-tasks.json 中 pending 的任务范围开发；completed 的证据先核对实际合并PR。
该清单仅用于当前Plus本地会话，不启用旧API队列；发现开放PR先恢复相关任务。
Acceptance 更正界面/恢复已由 PR47/48 合并；先核对实际代码，不重复开发。
下一项是Impact撤销模型/迁移方案审查，只允许该任务列出的文档路径，不实现代码或数据库迁移。
任务完成时明确停止；不要自行扩大到撤销实现、评审下游或离线运营范围。
这些范围内正常开发、测试、提交和成功 CI 后合并已有用户授权，不需逐包询问是否继续。
每包在独立分支做针对性测试，更新 DEVELOPMENT_STATUS.md/HANDOFF.md，提交并推送 PR。
用已有用户 GitHub 登录及 gh/git；不可把 ChatGPT 登录缓存或凭据上传 GitHub。
合并前核对当前 PR head SHA 的三个必需 CI job，包含最新 main，遵守分支保护。
再核对合并后 main CI 和实际部署证据，不能将 skipped/unverified 说成成功。
在 HANDOFF 中记录精确分支/提交/PR、已做测试、待办、阻塞和下一包；GitHub 是跨机器恢复源。
清单完成标记须核对真实合并证据，不能把待验收任务当完成；较新PR/HANDOFF证据覆盖旧pending记录。
如额度用尽、登录/权限缺失、出现冲突或pending任务完成，保存现有工作并停止，明确原因。
关闭会话之前尽量提交并推送安全检查点；未推送的本地改动不能保证跨机器恢复。
公共样例保持只读，真实身份/OIDC/提交门控关闭，内网未部署；不设置真实业务权限。
报告七模块和七计划百分比。CLI 的安全授权提示按实际需要由用户处理。
"""


def build_command(executable, resume=False):
    command = [executable]
    if resume:
        command.append("resume")  # Current-repository picker, never blindly --last.
    command += [
        "--sandbox", "workspace-write", "--ask-for-approval", "on-request",
        "-c", 'forced_login_method="chatgpt"',
        "-c", 'model_provider="openai"',
    ]
    # resume's first positional argument is SESSION_ID, not a prompt.
    return command if resume else command + [PROMPT]


def session_env(source):
    env = dict(source)
    for name in ("OPENAI_API_KEY", "CODEX_API_KEY", "AZURE_OPENAI_API_KEY", "OPENAI_BASE_URL"):
        env.pop(name, None)
    return env


class CheckFailed(Exception):
    pass


def load_plus_tasks():
    """Read only the local queue; no API-controller ownership or login data."""
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    data = json.loads((ROOT / "docs/automation/plus-tasks.json").read_text(), object_pairs_hook=unique_pairs)
    if (data.get("schema") != 1 or data.get("mode") != "chatgpt-local"
            or data.get("repository") != "Wang106/SoftwareLifeCycle"
            or not isinstance(data.get("tasks"), list) or not data["tasks"]):
        raise ValueError("invalid Plus queue")
    known = set()
    for task in data["tasks"]:
        tid = task.get("id")
        if (not isinstance(tid, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", tid)
                or tid in known or not isinstance(task.get("title"), str) or not task["title"]
                or task.get("status") not in ("pending", "completed", "blocked")
                or not isinstance(task.get("depends_on"), list)
                or not set(task["depends_on"]).issubset(known)):
            raise ValueError("invalid Plus task")
        if task["status"] == "completed":
            evidence = task.get("evidence", {})
            if (type(evidence.get("pr")) is not int or evidence["pr"] <= 0
                    or not re.fullmatch(r"[0-9a-f]{40}", str(evidence.get("merge_sha", "")))):
                raise ValueError("completion needs merged PR evidence")
        else:
            if not task.get("allowed_paths") or not task.get("acceptance"):
                raise ValueError("unfinished task needs scope and acceptance")
            # The currently authorized next package is documentation-only.
            for path in task["allowed_paths"]:
                if (not isinstance(path, str) or path.startswith("/") or ".." in path.split("/")
                        or not re.fullmatch(r"[A-Za-z0-9_./-]+", path)
                        or not (path.startswith("docs/") and path.endswith(".md")
                                or path in ("DEVELOPMENT_STATUS.md", "HANDOFF.md"))):
                    raise ValueError("Plus review task must stay in documentation")
        known.add(tid)
    return data["tasks"]


def task_summary(tasks):
    completed = {task["id"] for task in tasks if task["status"] == "completed"}
    ready = [task for task in tasks if task["status"] == "pending"
             and set(task["depends_on"]).issubset(completed)]
    lines = [f"{task['status']}: {task['id']} — {task['title']}" for task in tasks]
    lines.append("下一待核对任务：" + (ready[0]["id"] if ready else "无；停止并报告阻塞或队列完成。"))
    lines.append("本地清单不是远端验收；会话须核对最新main/开放PR/合并证据后执行。")
    return lines


def read_command(command, env):
    """Bounded read-only probe; never print credential-bearing subprocess output."""
    try:
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        raise CheckFailed("检查无法完成（工具、网络或超时）；未启动模型。") from None
    if result.returncode:
        raise CheckFailed("检查失败；请核对工具、GitHub 登录及仓库访问权限。未启动模型。")
    return result.stdout.strip()


def check_environment(env):
    """Inspect prerequisites without fetching, changing git, or invoking a model."""
    errors, notices = [], []
    try:
        notices.extend(task_summary(load_plus_tasks()))
    except (OSError, ValueError, TypeError, AttributeError):
        errors.append("Plus任务清单无法验证；先修复 docs/automation/plus-tasks.json，未启动模型。")
    if os.name == "nt":
        return ["请在 Windows WSL、Linux 或 macOS 中运行。"], []
    executables = {name: shutil.which(name) for name in ("codex", "git", "gh", "node")}
    for name, path in executables.items():
        if not path:
            errors.append(f"缺少 {name}；安装步骤见 docs/automation/plus-local.md。")
    if executables["node"]:
        try:
            version = read_command([executables["node"], "--version"], env)
            if not re.fullmatch(r"v22\.\d+\.\d+", version):
                errors.append("项目构建需要 Node.js 22，与 CI 保持一致。")
        except CheckFailed as exc:
            errors.append(str(exc))
    if executables["git"]:
        try:
            remote = read_command([executables["git"], "remote", "get-url", "origin"], env)
            if remote not in (
                "https://github.com/Wang106/SoftwareLifeCycle",
                "https://github.com/Wang106/SoftwareLifeCycle.git",
                "git@github.com:Wang106/SoftwareLifeCycle.git",
                "ssh://git@github.com/Wang106/SoftwareLifeCycle.git",
            ):
                errors.append("origin 不是目标仓库的标准 HTTPS/SSH 地址；请手动核对，不会自动改写。")
            changed = read_command([executables["git"], "status", "--porcelain"], env)
            if changed:
                notices.append("存在本地改动：会话须先检查并保留；未推送内容不能跨机器恢复。")
        except CheckFailed as exc:
            errors.append(str(exc))
    if executables["gh"]:
        try:
            repository = json.loads(read_command([
                executables["gh"], "repo", "view", "Wang106/SoftwareLifeCycle",
                "--json", "nameWithOwner,viewerPermission"], env))
            if (repository.get("nameWithOwner") != "Wang106/SoftwareLifeCycle"
                    or repository.get("viewerPermission") not in ("WRITE", "MAINTAIN", "ADMIN")):
                errors.append("当前 gh 登录没有目标仓库写入权限；请核对 gh auth login。")
            pulls = json.loads(read_command([
                executables["gh"], "pr", "list", "--repo", "Wang106/SoftwareLifeCycle",
                "--state", "open", "--limit", "100", "--json", "number"], env))
            if not isinstance(pulls, list) or any(type(p.get("number")) is not int for p in pulls):
                raise ValueError
            if pulls:
                notices.append("发现开放 PR（最多显示100个）：" + ", ".join(
                    f"#{p['number']}" for p in pulls) + "；启动后先核对并恢复相关任务。")
            else:
                notices.append("当前未发现开放 PR；开始前仍须核对远端最新 main 和交接。")
        except (CheckFailed, ValueError, TypeError, AttributeError) as exc:
            errors.append(str(exc) if isinstance(exc, CheckFailed) else "GitHub 检查响应无法验证；未启动模型。")
    notices.append("检查不验证 Plus 登录、剩余额度、git 推送或沙箱审批；这些由实际会话确认。")
    return errors, notices


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true", help="Pick a saved session for this repository")
    parser.add_argument("--print-prompt", action="store_true", help="Print the task instructions without launching Codex")
    parser.add_argument("--check", action="store_true", help="Read-only prerequisites and GitHub access check; no model call")
    parser.add_argument("--show-tasks", action="store_true", help="Show local task scope without tools, network or model calls")
    args = parser.parse_args()
    if args.print_prompt:
        print(PROMPT)
        return 0
    if args.show_tasks:
        try:
            print("\n".join(task_summary(load_plus_tasks())))
            return 0
        except (OSError, ValueError, TypeError, AttributeError):
            print("Plus任务清单无法验证；未启动模型。", file=sys.stderr)
            return 2
    env = session_env(os.environ)
    errors, notices = check_environment(env)
    for notice in notices:
        print(notice, flush=True)
    for error in errors:
        print(error, file=sys.stderr, flush=True)
    if errors:
        return 2
    if args.check:
        print("启动前检查通过（未启动 Codex 模型）。")
        return 0
    executable = shutil.which("codex")
    if not executable:
        print("Install official Codex CLI, then run codex login and choose ChatGPT. See docs/automation/plus-local.md.", file=sys.stderr)
        return 2
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("This launcher requires your interactive terminal; it is not a CI service.", file=sys.stderr)
        return 2
    try:
        return subprocess.call(build_command(executable, args.resume), cwd=ROOT, env=env)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
