# 新 Codex 窗口接手入口

新窗口可以从仓库继续开发，无需依赖旧聊天窗口。前提是新窗口有 Wang106/SoftwareLifeCycle 仓库读写权限，并能读取当前 main；打开一个空窗口不会自动加载仓库、旧聊天、登录状态或执行环境。

## 可直接复制的任务
> 继续开发 Wang106/SoftwareLifeCycle。以最新 main 为准，先读取 AGENTS.md、START_HERE.md、REQUIREMENTS.md、DEVELOPMENT_STATUS.md、ROADMAP.md、docs/development-plan-progress.json，以及 HANDOFF.md 的当前入口和最新记录。核对分支、未合并 PR、CI 和部署证据，按下一包继续实现。测试通过后提交、合并并核对部署；更新进度与交接，报告七个模块及七项计划的百分比和剩余工作。公共演示保持只读，OIDC 和授权状态提交默认关闭；内部服务器尚未部署，SSO 待定，不创建实际身份、授权或秘密。无需重复询问是否继续正常开发。

云端使用已授权的此 GitHub 仓库作为任务环境；本地打开该仓库的完整 checkout。当前旧桌面工作目录只是部分文件/临时材料，不能当成完整代码库。如 Git CLI 网络不可用，可以使用已授权 GitHub 连接服务；不能把连接服务操作声称为已经启动了云端 Codex 任务。

## 阅读和核对顺序
| 文件/证据 | 用途 |
| --- | --- |
| AGENTS.md | 新会话工作规则和运行边界 |
| REQUIREMENTS.md | 仓库可核对需求；原对话全文对账仍未完成 |
| DEVELOPMENT_STATUS.md | 最新摘要、完成度及限制；后面的验收记录覆盖前面的旧状态 |
| ROADMAP.md / docs/development-plan-progress.json | 两套验收口径和分母 |
| HANDOFF.md | 当前入口、最新验收及下一包；早期段落是历史 |
| docs/grant-status-submission.md / docs/grant-status-preparation.md | 本轮提交通道及页面准备边界 |
| docs/internal-browser-acceptance.md | 内网部署前准备和未来真实验收 |
| .github/workflows/ci.yml / frontend/package.json | 实际测试及构建命令 |
| 当前 GitHub PR/Actions/provider checks | 文档之后可能出现的新证据；核对 exact head，不复用旧成功标识 |

先检查 checkout 状态与 main 新提交，保护未提交改动；未完成 PR 不应被重复实现。每包结束后先更新摘要和追加交接，使下一窗口知道确切完成点。

## 当前接手快照
当前69页面：首批业务提交/原审计恢复基础、控制器及双语发送/查询/结果界面已接入；身份状态代理、原请求重试控制器及双语页面发送/精确结果/内存恢复已接入，独立默认关闭；已有默认关闭的授权状态受控发送/原请求重试/页面内存恢复；又完成USER/SERVICE本地身份及GLOBAL/PROJECT/SOFTWARE授权新增准备、字段/角色校验、冻结确认复制。新增注册代理/原请求重试控制器及双语页面发送/回执/内存恢复已实现，默认关闭；未配置批准环境和身份，模拟回归不等于真实管理员验收。
API代码0.18.36/schema0020；身份私有目录/UUID详情/有界状态历史已增加，线上API版本未独立验证。36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0。增量0。
内网只有可用部署位置，尚未开始安装；离线安装包/无Docker启动脚本尚未实现和演练。系统与CPU信息可稍后提供，不阻塞服务器端代码与模拟测试。

## 下一包
Approval Action/Release Decision的固定提交通道与精确原审计恢复契约，继承冻结请求、未知结果和原子审计边界，公开环境默认关闭；再接双语界面，逐步覆盖其余11业务命令。批准身份/内网真实验收、跨会话导入恢复、追加更正撤销、无Docker离线安装及运营迁移仍待完成，VIN最后。

Snapshot/实际报告/Batch双语发送、原审计查询和明确原请求重试已接入 /commands；结果组件显示原子审计确认的原应用值及精确业务/审计链接。页面能力来自独立firstSubmissionConfigured和唯一当前USER会话，只读明确false才可发送；只读切换可查询自己的原记录。门禁默认关闭，没有实际环境配置。
最新起点main5cf8798fdac12bd23f42b95e7d17b4cc0f5b23e9完整CI37797183654/Cloudflare成功，Actions skipped；本包提交后须核对精确head的新CI/provider。未知原请求仅组件内存，不跨卸载/刷新/会话。
