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
按 docs/automation/tasks.json 中 enabled 的任务范围开发；已完成任务根据实际代码/合并 PR 跳过。
Acceptance 更正界面/恢复已由 PR47/48 合并；先核对实际代码，不重复开发。
启用任务完成时明确停止；不要自行开启 disabled 的 Impact 撤销/迁移等宽泛范围。
这些范围内正常开发、测试、提交和成功 CI 后合并已有用户授权，不需逐包询问是否继续。
每包在独立分支做针对性测试，更新 DEVELOPMENT_STATUS.md/HANDOFF.md，提交并推送 PR。
用已有用户 GitHub 登录及 gh/git；不可把 ChatGPT 登录缓存或凭据上传 GitHub。
合并前核对当前 PR head SHA 的三个必需 CI job，包含最新 main，遵守分支保护。
再核对合并后 main CI 和实际部署证据，不能将 skipped/unverified 说成成功。
在 HANDOFF 中记录精确分支/提交/PR、已做测试、待办、阻塞和下一包；GitHub 是跨机器恢复源。
如额度用尽、登录/权限缺失、出现冲突或队列启用任务完成，保存现有工作并停止，明确原因。
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
    args = parser.parse_args()
    if args.print_prompt:
        print(PROMPT)
        return 0
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
