# Plus 登录的本地 Codex 开发

当前选择：用户启动本地 Codex CLI，使用 ChatGPT Plus 登录；GitHub Actions 只负责自动 CI。
不需要 OPENAI_API_KEY、CODEX_APP_PRIVATE_KEY 或专用 GitHub App。已经注册的 App 可保持未安装，
不生成密钥、不主动删除或撤销用户在别处设置的凭据。CODEX_APP_ID 本身不是秘密。
这次切换不代表用户电脑已经安装、登录或启动成功。

## 首次安装与登录

启动脚本支持 Linux、macOS、Windows 的 WSL；原生 Windows 终端不由本脚本支持。
开发机需要 Git、Python 3、Node.js 22（项目构建用），以及用于 PR/CI 操作的 GitHub CLI（gh）。
Codex 安装方式以官方页面为准：https://learn.chatgpt.com/docs/codex/cli 。
在 Linux/macOS/WSL 可使用官方安装命令：

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | sh
codex login
gh auth login
gh auth setup-git
git clone https://github.com/Wang106/SoftwareLifeCycle.git
cd SoftwareLifeCycle
python3 scripts/codex_plus.py
```

`codex login` 选择 **Sign in with ChatGPT**，使用有 Plus 的账号；不是 API key 登录。
GitHub 登录使用有 Wang106/SoftwareLifeCycle 写入权限的账号。若已有完整 checkout，进入它即可，
先保留已有本地改动，工作树干净时可 `git pull --ff-only`，不要覆盖已有改动或强行切主线。
首次工具安装、登录与系统/网络权限提示由用户在自己机器完成；不向聊天发送密码或登录缓存。
脚本本身不安装依赖、不改变登录状态、不修改 git 配置、不替用户提交未检查代码。

启动器传入 `forced_login_method="chatgpt"` 和 `model_provider="openai"`，
从子进程环境移除 OPENAI_API_KEY/CODEX_API_KEY/AZURE_OPENAI_API_KEY/OPENAI_BASE_URL。
API 登录不符合强制模式时 CLI 会退出，用户重新用 ChatGPT 登录；不静默改用 API 计费。
启动器保留 workspace-write 与 on-request，不绕过安全审批，不运行无人值守无限重试。
默认不选定付费模型或额外额度；使用当前登录计划提供的能力，额度用尽停止。
这些控制针对启动的 Codex 会话；并不限制用户自行在其他终端运行的 API 程序。

## 开发、测试与提交

内置任务指令读取仓库交接，再按启用队列的范围逐包开发：Acceptance 更正双语确认/原始结果，
然后手动导出/只读恢复导入。已完成任务由实际合并 PR/代码确认，不仅靠队列 enabled 标志。
后续宽泛任务没有明确范围时仍保持禁用。CLI 不读写 API 控制器的 codex-state CAS 运行所有权。
任务跨会话恢复使用代码分支、开放 PR、HANDOFF.md 和 DEVELOPMENT_STATUS.md。

每包在独立分支做针对性测试、更新交接、提交推送 PR。GitHub Actions 自动跑已有完整 CI：
Backend, PostgreSQL and migrations / Frontend tests and Cloudflare production build / CI acceptance。
已配置 main 必须 PR、strict 最新主线、这三项检查、管理员不得绕过，force/delete 禁止。
用户授权 CLI 在检查当前精确 head CI 后合并，但具体沙箱/网络安全审批仍由 CLI 提示；
gh/连接权限缺失时保存工作并报告，不复制 ChatGPT 登录缓存来获得仓库权限。
合并后核对 main CI；Cloudflare/Render 与 Actions deploy 证据分别报告。
done_code 或绿色 CI 不代替实际提供方/schema/浏览器/内网验收。

## 中断后恢复

同一台机器，在本仓库目录执行：

```bash
python3 scripts/codex_plus.py --resume
```

这会打开当前仓库的保存会话选择器，不盲目选择 --last，也不扫描所有仓库会话。
选中已有会话后输入“读取最新 main/PR/HANDOFF 后恢复当前任务”，再开始下一轮；
resume 的首个位置参数是 SESSION_ID，启动器不会误把整段任务指令当成会话 ID。
CLI 会话记录在本机，不承诺跨机器自动同步。
换机器或本机记录丢失时，获取最新仓库，执行不带 --resume 的启动命令；
Codex 从已推送任务分支/PR 和交接恢复。新会话不能恢复尚未推送的本地/内存改动。
启动器不会自动清理、stash、reset 或 force-push 工作区。
关闭前尽量提交并推送安全检查点；不要提交 .env、auth.json、私钥或真实身份/公司数据。

## GitHub Actions 的 API 模式已经停用

dispatcher 已移除 schedule；手动 dry_run 仍可运行不付费的 38 项标准库回归。
正常 dispatcher、worker、continuation 均需要 CODEX_DEVELOPMENT_MODE=api 才可能开发，
还要原启用开关、API/App 凭据与完整 main 保护。该模式变量当前未配置，启用开关 false。
因此已有未配置的 App ID、误点普通 Run workflow 或 CI 完成事件不会启动 API 开发。
不要为本 Plus 方式填写 API Secrets、设置 mode=api 或重新添加定时调度。
旧 API 文档仅保留作历史/可选方案，不是当前操作步骤。

## 使用边界与验证

机器/终端会话必须保持运行，用户负责启动/恢复；这不是 24 小时云端自动开发服务。
一次启动可指示会话内继续完成已授权队列，但不能保证 CLI 每轮永不暂停，
安全提示、额度、登录、网络、CI、冲突与任务边界都可能需要用户处理。
不新增 API 调用费用，不承诺无限 Plus 用量，也不自动购买任何额度。
公共样例只读、真实 OIDC/提交门控关闭、内网未部署，产品进度仍36/44=82%。
本地验证：38 调度/启动器回归、actionlint、进度 --check 和 prompt 预览；
实际用户 Plus 登录、CLI 会话/沙箱/gh 推送与跨会话运行尚需用户机器验收。

官方 OpenAI documentation：
- https://learn.chatgpt.com/docs/codex/cli
- https://learn.chatgpt.com/docs/auth （ChatGPT 登录与 forced_login_method）
- https://learn.chatgpt.com/docs/developer-commands?surface=cli （resume 与 CLI 参数）
