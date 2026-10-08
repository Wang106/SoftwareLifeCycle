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
当前69页面：身份状态代理、原请求重试控制器及双语页面发送/精确结果/内存恢复已接入，独立默认关闭；已有默认关闭的授权状态受控发送/原请求重试/页面内存恢复；又完成USER/SERVICE本地身份及GLOBAL/PROJECT/SOFTWARE授权新增准备、字段/角色校验、冻结确认复制。新增注册代理/原请求重试控制器及双语页面发送/回执/内存恢复已实现，默认关闭；未配置批准环境和身份，模拟回归不等于真实管理员验收。
API代码0.18.36/schema0020；身份私有目录/UUID详情/有界状态历史已增加，线上API版本未独立验证。36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0。增量0。
内网只有可用部署位置，尚未开始安装；离线安装包/无Docker启动脚本尚未实现和演练。系统与CPU信息可稍后提供，不阻塞服务器端代码与模拟测试。

## 下一包
下一包将Snapshot/实际报告/Batch的既有确认准备接入双语发送、明确原审计查询/原请求重试和精确结果链接，使用firstSubmissionConfigured及当前会话只读投影；默认关闭、未知原请求不被编辑/刷新/新操作覆盖。传输代理、共享解析/审计验证和FirstSubmission控制器已实现，不重复开发。之后批准身份/内网真实验收、全部14业务提交、跨会话恢复、追加更正撤销、无Docker离线安装及运营；VIN最后。
首批Snapshot/实际报告/Batch独立默认关闭的提交代理与原操作回执恢复代理、严格三字段/操作正文解析、actor/body绑定原子审计投影及FirstSubmission冻结原请求控制器已实现。recover后台只GET原审计，不能再次写入；只读切换仍可查询自己的已提交记录，缺失或不匹配保留unknown。提交须正确HTTP后精确审计确认，原应用结果与后来状态独立。页面仍准备/确认复制，发送/查询/结果按钮未接入。
起点最新main 2d8562eb0595400422d8f96f29296ca3748ea96c 的CI37788438285三个任务成功、Cloudflare成功，覆盖上一包记录时pending状态；Actions部署仍skipped。69页面/API代码0.18.36/schema0020；本包完整CI待核对。详情或当前状态不代替原审计回执，恢复只存内存，跨刷新/会话导入未实现。
公共样例只读/OIDC和所有提交默认关闭，不配置实际身份/授权/秘密。内网尚未安装、SSO待定、人员用户后续自定、Windows/无Docker条件未确认。真实浏览器/提供方/管理员、Render工作区、后台部署版本及运营验收未完成。契约docs/first-command-submission.md；新窗口核对最新GitHub head/CI/provider，不复用历史状态。
