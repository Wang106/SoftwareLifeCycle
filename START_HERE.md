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


## PR#28 验收 — 2026-10-08（Codex）
PR https://github.com/Wang106/SoftwareLifeCycle/pull/28 已合并，代码main 759b94d190407b50c6b90f416ebfb953bf7f875f，最终feature fffe74f1a437d3fcb18a8d52e896be1a6559c33c；起点 5cf8798fdac12bd23f42b95e7d17b4cc0f5b23e9。
exact-head完整CI37802955859三个任务成功：2071后端、172 PostgreSQL-module cases（不是全部真实PG总数）、无skip；802前端（原777，新增20组件事件/双语结果回归、4页面能力门禁及1新结果组件本地化覆盖=25）。0020单迁移头、SQL、隔离PostgreSQL升降级往返、进度--check、类型检查、Next/Worker生产构建及中英文禁用认证SSR全部通过。后端113399660155、前端113399660461、acceptance113403554017成功。两条首批路由GET405/POST禁用503、private/no-store。Cloudflare feature Preview成功，build5b808204-972c-46f9-971c-a8f70447431d；无新增测试失败，首次feature完整通过后合并。
Snapshot/实际报告/Batch双语发送、原审计查询和明确原请求重试已接入 /commands；结果组件显示原子审计确认的原应用值及精确业务/审计链接。页面能力来自独立firstSubmissionConfigured和唯一当前USER会话，只读明确false才可发送；只读切换可查询自己的原记录。门禁默认关闭，没有实际环境配置。
本轮仅前端及文档变更，无后台/schema变更；69页面/API代码0.18.36/schema0020不变。双击、发送/查询互锁、过期确认/发送、复制锁、目标/查询/能力刷新、unknown后拒绝、只读恢复、原字节重试、精确三类回执/独立新标签链接均有模拟回归。没有自动重试或当前状态/replayed推断。仅confirmed或首次明确rejected可新请求；查询缺失仍unknown。去除query组件key以保留同页已尝试控制器，未发送预览随query变化失效。
恢复仅当前组件内存；卸载/刷新/跨会话仍会丢失，beforeunload对应用内其他路由不保证提醒，跨会话导入待实现。没有实际提供方/管理员/浏览器/API在线探针或内网安装；公共样例只读、OIDC及所有提交默认关闭，未配置真实变量/身份/授权/秘密，不重试被拒绝的浏览器访问。Render工作区未选择、后台部署/版本未核验；SSO/人员/Windows无Docker/系统架构保持待定。
代码main的自动CI与Cloudflare在本记录时尚未完成验收；此文档提交后的最新main精确head另核对，不将feature Preview当成main部署。Actions部署独立门控保持关闭；提供方自动构建不证明Actions门禁/凭据已通过。后续最新完整CI/提供方证据优先于历史pending记录。
执行器Mac部分快照，无完整Node依赖；本地新测试Node语法与进度--check通过，完整套件为Actions，无另启独立云端Codex任务。历史交接完整保留，原SoftwareLifeCycle_12全文未取得。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，增量全部0。首批真实身份提交/恢复/结果及真实双语端到端验收仍未完成，不用模拟回归提升里程碑。14业务、2自身会话、6管理员和离线操作分计。
下一包Approval Action/Release Decision固定提交通道与精确原审计恢复契约，然后双语发送/结果界面；继续其余11业务命令、批准身份/内网真实验收、跨会话导入恢复、追加更正撤销、无Docker离线安装与运营迁移，VIN最后。契约docs/first-command-submission.md。
