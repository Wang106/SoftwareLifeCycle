# 后续开发计划 — 2026-10-06

工作方式：Codex 云端继续开发；GitHub main 是唯一工程事实源。每个开发包须有
代码、回归证据、交接文档和部署核验。公共演示环境继续只读、只放样例数据，
界面默认中文并可切换英文。

## 当前完成度

| 模块 | 已完成 / 总项 | 完成度 | 剩余工作 |
| --- | ---: | ---: | --- |
| 领域基础 | 5/5 | 100% | 生产数据校验属于后续运营验收 |
| 发布治理 | 5/5 | 100% | 演示范围完成；正式身份和运营验收待后续 |
| 分发与生产追溯 | 5/5 | 100% | 演示范围完成；受控提交及更正待后续 |
| 证据、评审与审计 | 9/9 | 100% | 固定53项兼容读取范围完成 |
| 身份与授权 | 8/9 | 89% | 批准的 OIDC 配置及真实提供方验收 |
| 受控写入体验 | 3/5 | 60% | 登录、提交、结果恢复、完整更正/撤销 |
| 生产运营 | 1/6 | 17% | 恢复、监控、环境隔离、部署门禁及网络/数据审批 |
| **合计** | **36/44** | **82%** | 按 ROADMAP 已勾选项计算，不代表生产就绪 |

17/17 个已识别前端读取组完成迁移。API0.18.27 完成固定53项候选审查：
50项退役、3项保留且具备有界增长证据。Phase4 对应验收项完成，
CI 也完成后，当前总进度36/44（82%）。该结果不代表真实身份、受控提交或生产运营完成。

## 7 项开发计划进度（每轮必须报告）

计算规则：每组采用固定、等权的验收里程碑，完成度＝已通过数÷该组总数，
四舍五入至整数。计入已有且验证过的准备表单和后端安全基础；真实登录、
提交、恢复和公司环境验收仍未完成。百分比不是工时、上线就绪度，也不把
7 组的平均值替代 ROADMAP 的 36/44（82%）。

<!-- development-plan-progress:start -->
| 计划 | 已完成 / 验收里程碑 | 完成度 |
| --- | ---: | ---: |
| 1. 其余兼容读取治理 | 10/10 | **100%** |
| 2. 持续集成 | 4/4 | **100%** |
| 3. 身份、权限管理及会话 | 1/5 | **20%** |
| 4. 首批受控提交 | 2/6 | **33%** |
| 5. 覆盖全部 14 项命令 | 2/5 | **40%** |
| 6. 追加式更正和撤销 | 1/5 | **20%** |
| 7. 生产运营与公司迁移 | 0/6 | **0%** |
<!-- development-plan-progress:end -->

计算源：`docs/development-plan-progress.json`。运行
`python scripts/report_development_plan_progress.py` 获取每轮报告；`--check` 防止
文档表格漂移，`--update` 更新本表。每个已完成里程碑列出仓库证据。
后续每轮必须报告这 7 行、当轮增量及剩余内容；功能模块表也继续保留。
新增范围须注明分母变更及原因，不通过缩小分母提高进度。

计划 1 固定为 9 个兼容读取族（组织、工厂、生产、分发、SCR/Issue、发布/ASR、
Snapshot、DVP、治理/审计）及一次完整清单闭环验收，共 10 项。清单记录 53 个
待退役或复核边界的候选路径，包括已退役路径及仍在使用/可能已有限制的读取；
候选不等于全部 unbounded。已有限制的活跃路径可保留，完成时须在
该里程碑的 bounded_evidence 中逐路径记录边界/增长测试证据，不能强制退役。
API0.18.27 已完成全部9族和53项闭环；ROADMAP 对应项随证据完成。


计划 2 共 4 项：配置进 main、自动后端/PG、自动迁移/前端、失败阻断与主线验收。
计划 3 共 5 项：API 基础、提供方/环境、浏览器会话、授权管理、真实提供方验收。
计划 4 共 6 项：首批请求准备、后端安全、真实提交、恢复、结果追溯、端到端验收。
计划 5 共 5 项：14 表单、14 后端安全、14 真实提交、完整结果恢复、全量端到端验收。
计划 6 共 5 项：实际报告更正、判断关系替代、分发撤销、生产更正、全量一致性验收。
计划 7 共 6 项：环境、恢复、监控、部署回滚、网络、数据及上线接受。

## 开发顺序与验收

| 顺序 | 开发包 | 实施内容 | 验收条件 | 依赖 |
| --- | --- | --- | --- | --- |
| 1 | 其余兼容读取治理 | 逐路由核对 SCR/Issue、发布证据/策略/组件/护照/就绪度及治理/审计旧读取；退役无消费者接口，保留必要服务并明确分页 | 路由清单与调用证据对应；HTTP 合约、增长数据、真实 PG 回归通过；禁止静默截断完整证据 | 可立即开展仓库内审查；外部消费者如存在需核对迁移 |
| 2 | 持续集成 | 审查现有 CI PR #1 并补齐后端/PG、迁移单头及升级、前端生产构建 | 合并后的 main 自动执行；故意失败的校验阻止错误变更；不能把未合并 PR 算完成 | 仓库 Actions 权限与执行环境 |
| 3 | 身份、权限管理及会话 | 配置批准的 OIDC；浏览器登录/注销/会话过期；审计身份与授权管理 | 真实提供方正反例；错误项目/软件/角色及停用身份均拒绝；浏览器不泄露凭据 | 提供方、issuer/audience/JWKS、回调地址及独立受控环境须确定 |
| 4 | 首批受控提交 | 优先 Snapshot、实际软件报告、Batch；复用现有请求准备、确认、request ID/版本保护 | 重试不重复；并发冲突可解释；网络中断后能查询确定结果；结果链接到精确对象与审计 | 第 3 包及受控可写目标；公共演示仍只读 |
| 5 | 覆盖全部 14 项命令 | 扩展评审、决策、分发、授权、部署、更换、影响评估、DVP、资源及测试发布 | 所有表单验证、确认、权限拒绝、重试/不确定结果恢复及精确追溯通过中英文端到端验收 | 第 4 包的提交与恢复模式 |
| 6 | 追加式更正和撤销 | 定义历史替代/撤销规则、权限、原因和对下游的约束，扩展现有实际报告更正 | 不覆写旧判断/批次；保留前后记录和审计；幂等、并发及下游一致性测试通过 | 各业务状态与撤销政策须确定；不把撤销解释为实体刷写回滚 |
| 7 | 生产运营与公司迁移 | 环境隔离、非演示禁 seed、备份恢复演练、结构化日志、告警、回滚手册及批准网络 | 可重复部署/回滚和真实恢复演练；审批后才导入公司数据；权限与数据隔离通过验收 | 公司网络、数据隐私、安全、保留政策及负责人 |

兼容读取治理和 CI 已完成；下一步先推进可独立验证的授权管理，身份配置的外部依赖不阻止仓库内开发。
后续 VIN/车辆级追溯作为另行定义的数据与权限扩展，不提前混入本轮范围。

## 估算与完成规则

沿用目前的条件估算：到受控内部使用约 4–8 个聚焦开发包，到生产就绪评审
合计约 12–20 包。上表是工作组，一组可拆成多个可验收包；数字不是日期承诺，
不会因本轮小切片自动减一。兼容范围、SSO、受控环境与更正政策可能扩大工作量。
只有实现及验证进入 main，才更新对应 ROADMAP 项。

## 这 7 项完成后，开发是否完成？

**就当前已确定的版本范围而言，是：7 个工作组全部达到验收条件，且当前
ROADMAP 的 44 项都有实现和证据，可认定本版开发及生产准备范围完成。**
这不是“再执行 7 次继续”；一个工作组通常包含多个开发包。

| 完成层级 | 判断标准 | 当前状态 |
| --- | --- | --- |
| 演示可用 | 样例追溯、默认中文/可选英文及公开只读浏览通过验证 | 已具备 |
| 受控内部使用 | 批准的真实身份、独立受控环境、权限拒绝、提交/重试/结果恢复及审计通过验收 | 尚未完成 |
| 当前路线图完成 | 7 个工作组验收通过；44/44 项均有 main 中的实现及验证证据 | 当前 36/44 |
| 正式上线批准 | 在真实目标环境完成安全/权限、恢复演练、网络和数据治理的运营评审，由公司接受发布 | 尚未完成，不能用演示测试替代 |

第 7 组包含备份恢复、安全/数据与运行准备；实现文档不等于真实演练通过。
SSO、公司环境和审批是外部依赖，开发过程中会提前准备可审查的配置和测试，
但不会凭空选择提供方、录入公司数据或开启公开写入。验收不通过的缺陷继续
修复；验收通过后的维护与新增需求单独管理，不延长本版的既定完成范围。
VIN/车辆级追溯仍排最后，属于另行确定的数据与权限扩展。

## 本轮进展 — API 0.18.22

第二批再退役 11 个生产/分发旧 GET，累计 19 个：部署目录、富详情/来源历史、
批次目录、交付目录/最新富详情/指定版本富详情、分发目录/富详情、授权目录/
富详情。精确 Batch、分页目录、精确 profile/artifacts 及 14 个写入命令保持。
下一包继续治理剩余 SCR/Issue、发布证据/策略/组件/护照/就绪度及治理历史。
进度仍为 34/44，不能把 19 个接口退役换算成未知分母的整体完成率。

## 本轮进展 — API 0.18.23

再退役 8 个 SCR/Issue 旧读取，累计 27。计划 1 从 40% 到 50%；其他计划
百分比是已实现基础的首次固定里程碑记录，不表示本轮新增真实登录/提交。
计划表及 JSON 清单成为后续每轮的固定报告内容。接下来处理发布/ASR、
Snapshot、DVP、治理/审计旧读取，再完成完整清单闭环和 CI。

## 2026-10-05 — Release/ASR retirement and fixed-candidate closure, API0.18.27

The 19 release-family candidates are resolved: 16 legacy GETs now return HTTP410
without database access; three active scalar reads remain: exact ASR profile,
ASR downstream-summary and release coverage. Retained reads use full SQL counts,
no growing child arrays or child ORM graph, and preserve stored UUID/Snapshot scope.
SQLite growth checks compare fixed read-query count before/after120 records;
PostgreSQL verifies complete aggregates and no audit mutation. Existing downstream
summary tests cover the fixed seven count queries and exact recorded parent chain.

Retired paths are the combined/standard/application directories, rich exact SSR,
ASR decision/decisions/components/evidence/snapshot-policy/downstream/readiness,
and five version-only overview/verification/artifacts/readiness/decision reads.
Bounded summaries/catalogs/children remain. Version consumers first use exact
release-catalog/application/resolve and explicitly handle unique/ambiguous/missing;
no arbitrary release or UUID is inferred. SSR/components pages use the UUID path
and returned identity, not unsupported query pins. Evidence/frozen policy pages
pin selected Snapshot; passport children pin Snapshot/decision together. Current
readiness fails closed on stale selection. Working artifact/policy aggregates
and frozen Snapshot manifests/rules remain different scopes. Coverage preserves
any-PASS semantics; this slice does not infer latest-result semantics or approval.

Fixed53 candidates now equal50 retired +3 audited bounded, disjoint and exact.
All nine families and full closure pass: plan1 10/10=100% (80→100).
The corresponding ROADMAP endpoint acceptance item completes: Phase4 9/9=100%,
overall35/44=80%. Consumers remain17/17. Other plans remain0/20/33/40/20/0;
phase percentages100/100-demo/100-demo/100/89/60/0. This completes the fixed
compatibility scope, not authenticated submissions, CI or production readiness.

Validation:1191 backend tests pass with no skips, including129 real PostgreSQL
checks;465 frontend tests; Cloudflare/OpenNext build;18 production Next SSR
checks across nine views in Chinese/English; single migration head0018 and full
upgrade SQL. Existing warnings are deprecations/collection notices (9661).
No schema, provider, credentials or grant change; all14 POSTs and shared command
helpers remain. Public sample remains read-only. Cloud rollout still requires
independent feature-commit build and live API/page checks recorded below.

## 2026-10-05 — CI integrated and verified on main

Mode: Codex cloud. Started from a18cc71816b89472f02e2b6a61fec50f5faed9a1.
PR#1 was reconciled with current main without restoring old API0.18.13 documents
or undoing the fixed53 compatibility closure. Updated feature c156d1e01fa41ea8062f05c899bdeb47d95df5da
passed PR run37248117693. Merge 479e0a292e921b1f325985038903d71edafa7a8c passed main push run37248330054.
See https://github.com/Wang106/SoftwareLifeCycle/actions/runs/37248330054.

Python3.12/PostgreSQL16 backend1204 passed, no skips (1191 existing +13 CI gate/
target-guard tests);129 real PostgreSQL cases are retained, including ordinary
module database fixtures. The report gate's named _postgres count is a narrower
classification, not the total real-database count. Single0018 head, full upgrade
and head downgrade SQL, isolated upgrade/downgrade/re-upgrade, report gate and
artifact upload pass. Node22 frontend465 passed and OpenNext production build pass.
The stable CI acceptance job requires both validations to succeed. Local execution
of all16 success/failure/skipped/cancelled dependency combinations allows only
both-success; process regressions reject malformed/missing/empty/failed/error/
skipped/no-PostgreSQL reports and prevent remote/company database connection.

Actions run on main push, PR and manual dispatch, with SHA-pinned actions,
read-only repository token, no persisted checkout credentials and disposable
PostgreSQL data. No deployment/OIDC/company credentials or grants were introduced.
This does not install branch protection or make independent Render/Cloudflare
automatic deployment wait for CI. CI failures make the workflow/check red;
merge/deployment enforcement and recovery remain separate operations work.

CI plan2 now4/4=100% (0→100); plans100/100/20/33/40/20/0 retain fixed denominators.
The ROADMAP CI item completes:36/44=82%, phases100/100-demo/100-demo/100/89/60/17.
Plan7 still0/6 because its fixed environment/restore/monitor/release/network/data
milestones are broader than adding CI. Read consumers17/17 and53=50+3 remain.
API0.18.27/schema0018 and public sample read-only remain; deployment health and
Cloudflare build evidence are recorded separately below.

Next: approved OIDC provider/controlled target configuration, browser session and
audited grant administration, then first authenticated submissions/recovery/results;
all14 commands, broader append-only corrections and operational acceptance follow.
No approved provider or company target is inferred from CI success. Backup/restore,
monitoring, environment separation, gated deploy/rollback and company network/data
acceptance are still incomplete. This is not a production-ready certificate.

## 2026-10-06 — 默认关闭的 OIDC 浏览器认证实现

新增登录、回调、会话读取、本地退出和双语账户页；修正前端 HUMAN 与后端
USER 的身份类型不一致。签名模拟提供方请求往返及实际 Next 关闭态路由/SSR
检查通过，CI 增加该路由检查。真实提供方、浏览器及服务器撤销验收尚未完成，
因此 identity-session 保留未完成状态，记录部分实现证据而不增加百分比。
详见 [浏览器认证契约与验收边界](oidc-browser-auth.md)。

## 2026-10-06 — 服务端会话撤销实现及部署

PR#6 已合并；服务端会话登记、Token 摘要绑定、到期检查、16 个活动会话限制、
事务审计及撤销已实现。前端 v2 Cookie 在退出成功后重放失败；撤销故障保留
Cookie 并提示重试。远端后端1285、前端541、迁移往返及 Preview/main 发布通过。
真实提供方及实际浏览器凭据/恢复验收仍缺失，identity-session 保持未完成；
七项计划100/100/20/33/40/20/0，本次增量0。细节见 oidc-browser-auth.md。

## 当前后续顺序 — 2026-10-06

前两工作组已完成，不再重复开发。API0.18.30 本轮实现项目/软件已有角色
暂停与恢复；这不是整个授权管理里程碑完成。公共站保持样例只读。

| 顺序 | 开发步骤 | 完成条件／依赖 |
| --- | --- | --- |
| 1 | 完成审计身份与授权管理：先有界目录/精确详情，再身份登记/停用、角色新增、全局管理员及恢复规则，最后中英文管理界面 | 精确范围权限、旧请求重试、并发、审计回滚和管理员防锁死通过；首个管理员及恢复方式需确定 |
| 2 | 准备独立受控环境，配置批准的OIDC；建立测试用户及精确项目/软件角色 | 提供方、issuer/audience/JWKS、回调域名、秘密及可写目标确定；与公共演示隔离、禁seed |
| 3 | 真实浏览器登录/注销/过期/撤销验收 | 中英文、错误角色/项目/软件、停用身份、提供方不可用及凭据恢复正反例通过 |
| 4 | 首批Snapshot、实际软件报告、Batch真实提交 | 确认前提/请求ID；成功、冲突、中断及未知结果恢复；精确对象和审计追溯 |
| 5 | 按首批模式扩展剩余11项命令 | 全14项受控提交/恢复；权限拒绝、中英文真实提供方端到端通过 |
| 6 | 追加式更正与撤销：判断/DVP关系、发布/分发/授权、部署/更换/批次 | 前后历史、原因、权限、幂等/并发和下游一致性；不能覆写或伪造实体刷写回滚 |
| 7 | 生产运营：备份恢复、保留策略、监控告警、可重复部署和回滚 | 实际恢复/回滚演练、事件处置和环境隔离有证据 |
| 8 | 公司服务器与数据迁移及上线接受 | 批准网络/数据范围、权限和隐私检查，非演示禁seed，完成公司发布验收 |
| 9 | VIN/车辆级追溯（另定范围、最后处理） | 确定必要数据、权限与保留规则，不提前扩大当前44项分母 |

步骤1可继续独立开发，步骤2的配置准备可同时推进；真实提供方验收是步骤3–5
的依赖。运营工具可提前实现，真实演练须在批准目标执行。每个步骤可能分成
多轮开发，不能把8个步骤解释为再发8次“继续”即可上线；暂不承诺固定完成日期。
各轮自动提交/部署，按精确提交核验CI与运行状态，仅在里程碑完整验收后更新百分比。

## 管理读取切片 — API0.18.31 / 2026-10-06

已有角色暂停/恢复后，本包完成管理员GLOBAL/PROJECT/SOFTWARE有界目录、
精确详情及项目/软件状态历史分页。目录支持精确UUID/角色/状态筛选，完整
SQL计数；排除秘密字段和原始审计JSON。真实提供方/管理界面验收仍待完成。
下一步身份登记/停用、角色新增、全局管理员保护与恢复，然后中英文管理
界面；身份配置、真实提交、恢复、更正及运营的顺序保持。里程碑仍36/44，
七计划100/100/20/33/40/20/0，不将仅完成读取换算成整个授权管理完成。

## 本地主体管理切片 — API0.18.32 / 2026-10-06

实现本地主体默认停用登记、启用/停用及停用时同步撤销注册会话；精确预期状态、
原因、原管理员/原请求重试、审计插入后回滚与 PostgreSQL 并发验证纳入CI。
平台管理员主体暂禁止状态变更，等待全局管理员/首管理员恢复策略。公开环境
仍只读，尚未配置真实提供方或创建真实主体/授权。下一步角色新增和全局管理员
恢复规则，然后中英文管理界面与真实管理员验收。完整里程碑仍未完成，
ROADMAP36/44=82%；七计划100/100/20/33/40/20/0，本次增量0。
细节见 [本地主体管理契约](principal-administration.md)。

## 本轮验收完成 — PR#10

功能提交5d43ea5、main合并c4be120；PR与精确合并提交的CI均通过：后端1612、
前端541，124个PostgreSQL模块用例及额外参数化PG用例无跳过；迁移往返通过。
Preview与正式Cloudflare发布成功，两环境各5项HTTP/SSR探针通过；API运行
0.18.32/0019，身份读取401、两个主体管理写入403 read_only_mode。
本地主体登记/停用已交付；角色新增、管理员恢复规则、双语管理UI及实际管理员
验收尚未完成。进度口径及后续顺序不变，本次增量0。

## 范围角色新增切片 — API0.18.33 / 2026-10-06

新增项目/软件精确角色登记：初始暂停，显式恢复后才生效；9种角色、范围拒绝、
旧请求重试、数据库唯一性、审计插入后回滚及身份停用并发纳入测试。全局角色、
首个管理员及恢复规则、中英文管理界面与实际管理员验收仍未完成。公开环境
保持只读，未配置真实提供方或新增实际授权。下一步全局管理员/恢复策略，
然后双语管理界面与真实验收；受控身份/目标、首批3项及全14项提交恢复、更正
和运营迁移的顺序保持。ROADMAP36/44=82%；七计划100/100/20/33/40/20/0，
本轮增量0。详见 [范围角色新增契约](membership-registration.md)。
