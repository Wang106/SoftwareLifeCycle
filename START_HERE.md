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
当前69页面：身份状态代理及原请求重试控制器已实现，页面发送/结果/内存恢复待接入；已有默认关闭的授权状态受控发送/原请求重试/页面内存恢复；又完成USER/SERVICE本地身份及GLOBAL/PROJECT/SOFTWARE授权新增准备、字段/角色校验、冻结确认复制。新增注册代理/原请求重试控制器及双语页面发送/回执/内存恢复已实现，默认关闭；未配置批准环境和身份，模拟回归不等于真实管理员验收。
API代码0.18.36/schema0020；身份私有目录/UUID详情/有界状态历史已增加，线上API版本未独立验证。36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0。增量0。
内网只有可用部署位置，尚未开始安装；离线安装包/无Docker启动脚本尚未实现和演练。系统与CPU信息可稍后提供，不阻塞服务器端代码与模拟测试。

## 下一包
PR#25完整CI37781503558三个任务成功（2071后端/721前端），代码main ff45bc52ec36e90793c700edadc7d44f2b76ad06 前端CI和Cloudflare成功；后端在交接记录时运行，文档后的最新main须核对。69页面/API代码0.18.36/schema0020；后台线上部署/版本未核验。
身份状态冻结准备/确认复制、独立默认关闭的代理/精确回执校验及PrincipalSubmission原请求重试控制器已实现。下一包接入双语发送按钮、精确结果组件、明确原请求重试及页面内存恢复，不重复开发代理、读取或冻结准备。页面能力使用principalSubmissionConfigured与当前/me只读投影；未配置批准应用/API及OIDC/会话时关闭。目标来自精确UUID；观察到管理员保护和详情/history不一致阻断准备；issuer匹配仅参考，后台独立检查保护/expected_status并实际撤销会话。
控制器保留原目标/key/body，unknown后拒绝或开关关闭也不能把此前可能提交的操作说成失败。回执应用状态与当前状态独立，撤销数为实际非负安全整数，启用为0。详情/history只能新标签独立观察，不能替代原请求回执；未知原请求只存内存，跨刷新/跨会话导入恢复未实现。未来UI保留未知原请求，不允许刷新数据或生成新操作静默覆盖；实际发送需批准环境/身份与人员。
旧失败邮件CI37760543828已修复并经后续多次完整CI验证，起点最新main37769795022也全部成功；不要重复修复PG夹具计数。初版PR#25 CI随head更新cancelled，不是新的失败故障。
契约见docs/principal-status-submission.md、docs/principal-status-preparation.md、docs/admin-principal-ui.md。公共样例只读/OIDC及所有提交默认关闭，不配置实际变量/秘密/身份/授权；Render工作区待明确选择，后台提供方部署仍未核验。内网尚未安装、SSO待定、人员用户后续自定、系统/架构/Windows或无Docker条件未确认，这不阻断模拟开发。
之后批准身份/内网真实验收、首批三类及全部14业务提交、更正撤销、跨会话恢复、无Docker离线安装/启动与内网运营；VIN最后。36/44=82%；模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，全部增量0。
