"""Start a user-controlled Codex session using ChatGPT authentication only."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
PROMPT = """继续开发 Wang106/SoftwareLifeCycle，使用当前 ChatGPT Plus 登录额度。
不要使用 API key、付费 API、购买额外额度或启用 GitHub Actions API 开发模式。
先读 AGENTS.md、START_HERE.md、REQUIREMENTS.md、DEVELOPMENT_STATUS.md、ROADMAP.md、
docs/development-plan-progress.json 和 HANDOFF.md 最新记录；核对最新 main、开放 PR 和精确 CI。
保留所有已有改动，已有未完成 PR 优先恢复，不重复实现，不 force-push。
按 docs/automation/tasks.json 中 enabled 的任务范围开发；已完成任务根据实际代码/合并 PR 跳过。
先完成 Acceptance 更正双语确认和原始结果，再完成手动导出与只读恢复导入。
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true", help="Pick a saved session for this repository")
    parser.add_argument("--print-prompt", action="store_true", help="Print the task instructions without launching Codex")
    args = parser.parse_args()
    if args.print_prompt:
        print(PROMPT)
        return 0
    if os.name == "nt":
        print("Run this launcher inside Windows WSL, Linux or macOS. See docs/automation/plus-local.md.", file=sys.stderr)
        return 2
    executable = shutil.which("codex")
    if not executable:
        print("Install official Codex CLI, then run codex login and choose ChatGPT. See docs/automation/plus-local.md.", file=sys.stderr)
        return 2
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("This launcher requires your interactive terminal; it is not a CI service.", file=sys.stderr)
        return 2
    try:
        return subprocess.call(build_command(executable, args.resume), cwd=ROOT, env=session_env(os.environ))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
