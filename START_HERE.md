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
当前69页面：已有默认关闭的授权状态受控发送/原请求重试/页面内存恢复；又完成USER/SERVICE本地身份及GLOBAL/PROJECT/SOFTWARE授权新增准备、字段/角色校验、冻结确认复制。新增注册代理/原请求重试控制器及双语页面发送/回执/内存恢复已实现，默认关闭；未配置批准环境和身份，模拟回归不等于真实管理员验收。
API代码0.18.36/schema0020；身份私有目录/UUID详情/有界状态历史已增加，线上API版本未独立验证。36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0。增量0。
内网只有可用部署位置，尚未开始安装；离线安装包/无Docker启动脚本尚未实现和演练。系统与CPU信息可稍后提供，不阻塞服务器端代码与模拟测试。

## 下一包
PR#23完整CI及代码main前端CI/Cloudflare部署成功，见最新交接；之后文档提交的最新main CI/部署须重新核对。69页面/API代码0.18.36/schema0020；身份目录、UUID详情/有界history和注册回执新标签链接已实现。后台线上部署/版本未核验。
下一包身份激活禁用冻结准备、确认复制与独立默认关闭的提交代理/受控发送/精确回执/原请求重试。目标来自精确UUID读取；详情与history不一致要求刷新，管理员保护/issuer匹配只作信息，后端独立检查保护与expected_status、原子撤销实际会话。新准备不代表有效身份或授权。注册/授权发送与身份读取已完成，不重复开发。
原请求和未知结果仍仅存页面内存；跨刷新/跨会话导入恢复未实现。真实发送需批准的独立环境、身份与人员；公共环境保持关闭。后续首批三类及全部14业务提交、更正撤销、无Docker离线安装/启动与内网运营；VIN最后。
用户失败邮件已核对解决：旧CI37760543828三个耗时8:35/1:46/0:03；修正后CI37761779402成功并合并PR#22，起点main完整CI37763156141成功，本包CI37765286022也完整成功。旧通知不会撤回；不要重新实现已修复的PG夹具计数问题。
契约见docs/admin-principal-ui.md及docs/admin-principal-reads.md。Render工作区仍需明确选择确认才能核验后端提供方部署，未自行代选；不要将一般“继续开发”推断为批准创建账号或开启写入。内网尚未安装；这不阻塞继续代码与模拟回归。
