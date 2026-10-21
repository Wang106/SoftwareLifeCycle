Warning: truncated output (original token count: 131456)
Total output lines: 3979

# SoftwareLifeCycle Development Handoff

## 2026-10-21 SSR / ASR 四级审批进度总览（Codex / ChatGPT Work）

基线 main `e8ad3085f5d0284e111f85303211acd1d273259a`；启动时开放 PR 0，PR#100 合并后 main CI `39627326765` 三项必需 job 已全部 success，Actions deployment `39628577265` 与 continuation `39628577252` 为 skipped，不能称部署成功。独立分支 `codex/ssr-asr-approval-progress`，按用户要求暂停扩展生产更正，把主要精力放在 SSR/ASR 演示。

本包增强固定只读 `GET /api/v1/demo/zfi-import`：一次批量读取全部合成 ApprovalStep，不按 20 条发布逐行查询；仅当四步数量、顺序、岗位与 SSR/ASR 预期完全一致时返回 `approval_progress`，否则显式 null。返回已通过节点数、严格当前 PENDING 节点、关闭状态及两套路线。`/demo/zfi` 双语展示 SSR「电子工程师→电子经理→系统工程师→研发总监」、ASR「应用工程师→应用经理→系统工程师→项目经理」，每行显示进度/当前节点/退回或拒绝结果，保留原审批链接、筛选、检索、分页和只读限制；审批完成不等于正式 RELEASE。

无 migration、Seed、依赖、身份、CI、调度或 provider 配置改动；API 0.18.50 / schema 0029。定向前端 44 passed / 0 failed / 0 skipped；当前容器无 pytest，后端与真实 PG 待本包精确 CI，不能借用 PR#100 结果。实现提交/PR/head CI/合并/main/provider 证据待发布后在 PR 记录。36/44=82%；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/40/0。

SSR/ASR 预计后续 3–5 轮：本轮审批进度总览；下一轮标准/应用发布详情的当前 Snapshot→Readiness→审批→Decision 证据摘要；再一轮按供应商/基线 SSR 聚合 ASR 差异与阻断；最后 1–2 轮用于云端样例/API 与桌面、手机、中英文现场验收（真实浏览器/provider 权限具备时）。下一包应以本包精确 CI/合并证据为前提，优先 `ssr-asr-release-evidence-summary`，不回到无关生产账本扩展。

## 2026-10-21 生产换型与批次追加式更正写命令（DeepSeek，人工批准）

基线 main `80b00b62d2b2df2f20c405cb16a8895ece7df5fb`，开放 PR 0，独立分支 `codex/production-changeover-batch-correction-write`。承接 `docs/production-changeover-batch-history-design-review.md`（PR#96）§9 第二个小包，仅在人工批准后开放：新增两个更正写端点，完整 `request_id`/`expected_revision`/`predecessor_id`/`correction_reason` 协议；不新增迁移（复用 0029 四表），默认关闭浏览器提交、真实身份与内网验收。

实现：`correct_changeover`/`correct_batch`（锁 Deployment→目标行；幂等 keyed 重放核对 entity/action/actor/正文；revision/predecessor 链校验；`ended_at>=started_at`；缺失基线 IMPORTED_CURRENT 兜底；追加账本 + 原子 `EVT-CC-`/`EVT-BC-` 审计）。Changeover 只更正 from/changed_at/note（to 不可更正），Batch 只更正 started_at/ended_at/changeover/note（release/snapshot 软件归属不可更正）。端点 `POST .../changeovers/{no}/correction`、`POST .../batches/{no}/correction`，PRODUCTION_OPERATOR + resolve_actor。`write_contracts` 19→21；APP_VERSION→0.18.50；demo api_version 同步；两个 retirement 测试计数 19→21。

版本 API 0.18.50 / schema 0029。七计划 group6 `production-correction` complete → 100/100/20/33/40/40/0；业务 36/44=82% 不变。公共只读、OIDC/真实提交关闭、内网未部署。下一候选：真实身份/浏览器更正提交与内网验收（`correction-e2e` 及「全部 14 项命令」的 all-submit/all-recovery-results/all-e2e 里程碑）仍待批准环境，非后端代码包；后端下一候选 `production-changeover-batch-correction-e2e`（真实 PG 并发更正矩阵，若有）。

### 精确验收证据（PR#100）

实现提交 `a6054e1`；本地后端 SQLite 1699 passed / 654 skipped。PR head CI / 合并 / main CI / 部署证据待合并后回填。

## 2026-10-21 生产换型与批次追加式历史基线及只读投影（DeepSeek）

基线 main `787ee0928bf002e6727cd8c7a55b103d770a4838`，开放 PR 0，独立分支 `codex/production-changeover-batch-history-backend-read`。承接 `docs/production-changeover-batch-history-design-review.md`（PR#96）§9 下一小包：只新增基线/更正表与只读投影，不开放更正写命令（correction-write 仍为后续需人工批准的独立包）。

实现：`models/production_history.py` 追加 `ChangeoverBaseline`/`ChangeoverCorrection`（可更正 `from_release_id`/`changed_at`/`note`，`to_release_id` 绑定 expected）与 `BatchBaseline`/`BatchCorrection`（可更正 `started_at`/`ended_at`/`changeover_id`/`note`，`release_id`/`snapshot_id` 软件归属不可更正），复刻 Deployment 账本前驱/revision/唯一链/append-only；`batch_corrections` 增 `ended_at >= started_at`。迁移 `0029_changeover_batch_history`：建四表 + append-only trigger + 冻结物理列 guard + 捕获 `LEGACY_CURRENT` 基线；downgrade 有更正/`FIRST_RECORD` 基线时拒绝。投影 `effective_changeover`/`effective_batch`（+`_map`）head correction 覆盖基线派生有效值，缺口 `NOT_RECORDED`。消费者统一：`_deployment_detail`/`get_batch`/`production_catalog` 换型 `from_release` 与时间/note 用有效投影，软件归属保持记录值。`seed.py` `CO-0032`/`PB-1005-A` 改 insert-only 并捕获 `IMPORTED_CURRENT` 基线。

版本 `required_db_revision` → `0029_changeover_batch_history`、`APP_VERSION` → `0.18.49`、demo identities 与 status 断言改读契约。公共只读、OIDC/真实提交关闭、内网未部署。业务 36/44=82%；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0。下一候选 `production-changeover-batch-correction-write`（仅人工批准后）。

### 精确验收证据（PR#98）

实现提交 `a168936`、测试修复提交 `9ee00dc`；PR#98 最终 head `9ee00dcb16a141ec1a0fbefc22c9f4f63267aa23`。PR head CI 四项全绿（Backend/PostgreSQL/migrations、Frontend tests + Cloudflare production build、Workers Builds、CI acceptance）。受保护 squash 合并 `92fda758fbebcf16e816bf28e4cced5303a9c998`。main CI 四项 success（deploy/wake skipped）。Render `/health/ready` ready 0.18.49/`0029_changeover_batch_history`；Cloudflare `softwarelifecycle.whf969.com` HTTP 200。本地后端 SQLite 1686 passed / 654 skipped。



基线 main `e80598eb2c1ff05f349c39deaf53b43e9076c52e`（PR#95 证据回填后），开放 PR 0，独立分支 `codex/production-changeover-batch-history-design-review`。旧候选 `release-decision-supersession-backend-read` 已被 PR68/69/70 覆盖；按最新 HANDOFF 选 `production-changeover-batch-history-design-review`，承接 `production-trace-correction-design-review.md`（PR#85/86）「Changeover/Batch 自身更正账本随后另包」的约定，只审查、不实现写入。

本包只产出设计审查 `docs/production-changeover-batch-history-design-review.md`，无后端/迁移/Seed/界面/测试/依赖/CI/调度/身份/提供方配置改动。已核对真实模型与代码：`SoftwareChangeover`（from/to/changed_at/note/status，`to_release_id` 由服务层强制=expected，无 version/更正命令）与 `ProductionBatch`（release/snapshot/started_at/ended_at/note/status/changeover_id，`release/snapshot`=expected，`ended_at` 无任何写入路径、无结束批次命令、无更正命令）均「只创建、无更正」；`_create_changeover` 只锁 Deployment、`_create_batch` 锁 Deployment→lock_chain(AUTHORIZATION)；seed.py 551–582 对 CO-0032/PB-1005-A 即使已存在仍重新赋值（非 insert-only）。

设计要点：两张不可变基线表（changeover_baselines/batch_baselines，三来源语义）+ 两张类型明确更正表（changeover_corrections/batch_corrections，`EVT-CC-*`/`EVT-BC-*` 族，复刻 DeploymentActualCorrection 的前驱/revision/唯一链/append-only 约束）；`batch_corrections` 增 `ended_at >= started_at` 复合约束；§6 定位全部真实消费者；§8 给出真实 PG 最低矩阵；§9 把实现拆成两个后续小包（先 backend-read 只读投影，后 correction-write 写命令且需人工批准）。公共只读、OIDC/真实提交关闭、内网未部署。

业务 36/44=82% 不变；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0。API 0.18.48 / schema 0028 不变。下一候选 `production-changeover-batch-history-backend-read`（两张基线+两张更正表+迁移 0029+append-only trigger+只读投影+消费者统一，不开放写命令）。

### 精确验收证据（PR#96）

PR#96 head `efa23c13c3e1cb3ebeb5b29e5c3239a3d2334a80`；PR head CI `39598100225` 四项检查全绿（Backend/PostgreSQL/migrations success、Frontend tests + Cloudflare production build success、Workers Builds success、CI acceptance success）。受保护 squash 合并 `e1f918455cef0ec3f23bca135911851dbe7f1484`（PR#96）。main CI `39599671086` 四项检查 success；Actions deployment `39600805752`/continuation `39600805867` skipped（SLC_DEPLOY_ENABLED 未启用）。Render `/health/ready` ready 0.18.48/`0028_deployment_actual_guard`（纯文档包未触发后端重部署，符合预期）；Cloudflare `softwarelifecycle.whf969.com` HTTP 200（前端由 main CI build，非本包业务变更）。

## 2026-10-21 恢复 PR#93：合并升级后 main 并受保护合并（DeepSeek）

上一交接（依赖升级 PR#94）已完成并合并为 main `ba86d996cfaebc5e0ae03bdbfff882f1285421ca`，Next.js 15.5.24 支持窗口阻塞解除。本轮按交接恢复 PR#93 `codex/production-actual-history-ui-read`：将最新 main 以普通双父 merge 纳入该分支，仅三处文档冲突（DEVELOPMENT_STATUS.md / HANDOFF.md / docs/development-plan-progress.json），业务代码无冲突；未 force-push、未绕过门禁。

merge head `0fb6388854b39f7a0d38e223bb9ebafb92cf3b80`（双父 `204a355` + `ba86d996`）三项 CI 全绿（run `39590349063`）：Backend/PostgreSQL/migrations success（2331 passed / 253 PG module cases / 无 skip）；Frontend tests 1497 passed / 0 failed，Next.js 16.4.2 build 成功；CI acceptance success；Workers Builds success。受保护 squash 合并 `bbb0b9c5f1f0d7081658128175dd76570d60d2dd`（PR#93）。main CI `39591745406` 三 job 全绿；Cloudflare 生产 build `3dbb7e76-d472-4a55-acf1-67f766662c5f` success；Render `/health/ready` ready 0.18.48/0028；Cloudflare `softwarelifecycle.whf969.com` HTTP 200；Actions deploy/wake skipped。

业务 36/44=82%；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0。下一候选 `production-changeover-batch-history-design-review`（先只审查 Changeover/Batch 真实模型/消费者/并发与迁移边界，不直接实现写入）。公共只读、OIDC/真实提交关闭、内网未部署。

## 2026-10-21 受支持 Next.js / OpenNext 依赖升级（Codex / ChatGPT Work）

用户已授权升级包；当前独立 `codex/next-opennext-supported-upgrade`，基线 main `15093d0ff9afc3732ebc24ac91905f55293f48af`。PR#93 (`204a3555031e418382b519208ebaa9a6cc4f7a6c`) 仍开放，main CI39519151383及PR CI39531385542均在OpenNext版本检查失败；先修复共同依赖阻塞，不新建历史界面包。

Next16.4.2/OpenNext1.20.12/React19.3.1/Wrangler4.151.3，精确锁文件、Next16 TypeScript生成配置和 @node-minify/core 的 glob10.5.0 安全补丁；细节与回退见 `docs/next-opennext-upgrade.md`。无API/迁移/Seed/CI/调度/权限或真实门控变更。公共样例只读，OIDC/真实提交关闭。精确commit/PR/测试/合并/main/Cloudflare/Render/Actions证据验证后记入PR。

本地完整前端1494 passed/0 fail/0 skip；Next16/OpenNext生产Worker、cf:check、auth:check双语真实Next生产SSR/禁用路由、两层npm audit 0漏洞、进度/diff检查通过。后端/PG由本包精确CI证明，本地未执行。业务82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0不变。后续仍有批准provider真实多用户验收与Changeover/Batch更正设计。

精确证据（PR#94）：head `c924002339d206a168ef76959d3163188550d043`，PR head CI `39586695734` 三 job 全绿，squash 合并 `ba86d996cfaebc5e0ae03bdbfff882f1285421ca`；main CI `39588067933` 三 job 成功；Next.js 15.5.24 支持窗口阻塞解除，main 前端 build 恢复成功。

## 2026-10-21 生产实际软件历史双语只读界面与长历史有界读取（Codex / ChatGPT Work）

基线 main `15093d0ff9afc3732ebc24ac91905f55293f48af`，开放 PR 0，独立分支 `codex/production-actual-history-ui-read`。本包完成 Actual 历史只读收口：Deployment 详情双语展示 immutable baseline、history state、总更正数、最新 50 条、发生/入账时间与原审计链接；缺失历史明确 unknown，不提供提交控件、不推断生产许可。前端类型补齐时间字段。后端 `_actual_history` 对 Release/Snapshot 元数据集合预取，消除窗口 N+1；真实 PG 10,000 条链断言最新 50 条、顺序/总数及 <=12 SQL；前端覆盖中英文、截断、原文证据、审计链接、只读/未知态。

API 0.18.48 / schema `0028_deployment_actual_guard`，无 migration/Seed/依赖/权限/部署配置改动。公共演示继续只读，OIDC/真实提交关闭，内网未部署。检查点：PR#93 head `1034feb84b555281785874a765d409a792a1623b`，CI `39530257286`。Backend/PostgreSQL/migrations success（2331 passed、253 PG module cases、无 skip，Alembic 0028 SQL/PG round trip passed）；Frontend tests 1497 passed / 0 failed，但 OpenNext build 因 Next.js 15.5.24 已超支持期而拒绝，CI acceptance 随之失败。未加危险绕过参数，PR 未合并，main/Cloudflare/Render/Actions 无本包部署证据（PR#94 已解除该阻塞）。

未完成：批准 provider 的真实多用户浏览器验收；Changeover/Batch 独立更正语义与账本。下一候选 `production-changeover-batch-history-design-review`，只做模型、消费者、并发、迁移与拒绝丢语义降级审查，后端实现须按审查拆包。业务 36/44=82%；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0。

## 2026-10-21 生产实装旧写入保护与目录统一读取（DeepSeek，核验恢复并合并 PR#91）

基线 main `7bb4f58b5b88ff7a7e03d9573869c336aa69f598`，启动时开放 PR#91 `codex/production-actual-old-writer-guard-catalog-read`（前序遗留，CI 反复失败：先 13 failed+12 errors，后剩 12 setup errors）。本轮未新建重复工作，核验并补齐到可合并，squash 合并 `dd2438d9c8edd029b36a816f35865e63ddc62c23`（PR#91），最终 main `dd2438d9`。

本包：Alembic `0028_deployment_actual_guard` 冻结 Deployment 物理 actual 五元组（首次上报后拒绝非 no-op 覆盖/删除，`FIRST_REPORT` 须绑定同事务 immutable baseline + 一致 `ACTUAL_REPORTED` 原审计）；三个 production catalog 与 dashboard `application_release_downstream_summary`/`application_release_downstream` 统一读取 effective 追加式投影。API 0.18.48 / schema head `0028_deployment_actual_guard`。

本轮补齐（前序未闭环）：(1) `dashboard.py` 两处仍读物理列——summary 改 SQL effective 投影（`coalesce(head correction, baseline, physical)` 经 max-revision 子查询，保持 7 查询有界 count 契约），downstream 改 `effective_actual_map`；(2) `production.py::deployment_profile` 复用单次 `effective_actual`、`observed()` 改收有效值；(3) 五个测试文件适配——`test_actual_concurrency_postgres` 改用全新未报告 `DEP-A`/`DEP-B`（append-only 禁止 reset 共享 fixture 已报告行）、`test_manufacturing_views` seed 捕获 `IMPORTED_CURRENT` 基线、`test_release_downstream_summary` 用 keyed correction 构造 different_release、`test_security_model` 断言 0028、迁移测试接受 guard `OperationalError`(55000)。

精确证据：PR#91 head `4381b4a7b6cce460efad0989aa6ea87b3af5969d`；PR head CI `39515785419` 三 job 全绿（后端 2318 passed 无 skip）；squash 合并 `dd2438d9c8edd029b36a816f35865e63ddc62c23`；main CI `39516930782` 三 job 成功；Render `/health/ready` ready 0.18.48/0028（合并触发重部署）；Cloudflare `softwarelifecycle.whf969.com` HTTP 200；Actions deployment `39517821123`/continuation `39517821137` skipped。本地后端 SQLite 1682 passed / 648 skipped。

未完成边界：双语只读历史界面、真实 PG 长历史（10000）有界矩阵与批准供应商真实验收；Changeover/Batch 更正账本仍单独设计。下一包 `production-actual-history-ui-read`。业务 36/44=82%；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0。

## 2026-10-21 生产实绩历史一致性修复：核验、修测试并合并（DeepSeek）

基线 main `64b658919d614db169ffeb1578b63aaafa7c0efc`，核验并恢复上一轮开放 PR#89 `codex/production-actual-history-consistency-repair`（未新建重复工作）。启动核验发现两项未闭环并已修复：(1) PR head CI 卡死成僵尸 run、mergeable_state=blocked；(2) 两个真实测试缺陷——`test_production_actual_history.py` 的 SQLite 时区断言（`dep.deployed_at` 读回丢 tzinfo）与 `test_production_concurrency_postgres.py` 缺失 `effective_actual` import（真实 PG CI 下 `NameError`）。本轮追加两 commit `019430f`（时区归一化）、`158906d`（补 import），本地后端 SQLite 全量 1681 passed / 396 skipped。

PR#89 本体（前轮已写，本轮合并）：Deployment 首次 Actual 写物理列并建立基线；后续无键覆盖拒绝；带幂等键/期望版本/原因的更正只追加 `DeploymentActualCorrection` 与同事务审计。有效读取以基线 + 每 Deployment 最大 revision + 对应原审计事件为有界投影，更正时间由原审计 `occurred_at` 恢复；Deployment/Batch 详情和批次创建许可使用同一有效值。API 0.18.47 / schema 0027；无 migration、Seed、依赖、身份、CI 或部署权限改动。

精确证据：PR#89 head `158906de`；PR head CI `39497922487` 三 job 全绿（后端 2327 passed 无 skip）；squash 合并 `a82a3076ee13badbb9cdab94013d6444eb214bfc`；main CI `39499341572` 三 job 成功；Render `/health/ready` ready 0.18.47/0027（合并触发重部署）；Cloudflare `softwarelifecycle.whf969.com` HTTP 200；Actions deployment `39500744981`/continuation `39500745083` skipped。

未完成边界：数据库层旧写者 guard、production catalog 全消费者统一、双语只读历史界面、真实 PostgreSQL 并发/旧库升级降级/长历史及批准供应商验收。下一包 `production-actual-old-writer-guard-catalog-read`（数据库层旧写者冻结 trigger + catalog 全消费者统一），不得直接开始 Changeover/Batch 更正账本。业务 36/44=82%；模块 100/100演示/100演示/100/89/60/17；计划 100/100/20/33/40/20/0。


## 2026-10-21 生产实际历史追加账本与只读投影（DeepSeek）

基线 main `27f9b2470065bb8358f5db532868583b64c241ce`（PR86），开放 PR 0。独立分支 `codex/production-actual-history-backend-read`。旧候选 `release-decision-supersession-backend-read` 已被 PR68/69/70 覆盖；按设计 §9 收窄为仅 Actual 基线+追加更正+只读投影，Changeover/Batch 自身更正账本另包。

实现：新模型 `deployment_actual_baselines`（每已报告 Deployment 一行，source 区分 LEGACY_CURRENT/IMPORTED_CURRENT/FIRST_REPORT，recorded_actual_version/status/deployed_at）+ `deployment_actual_corrections`（id=request_id、target FK、predecessor_id、正整数 revision、完整替代值、correction_reason 1..2000、actor、request_json、audit_event_no、recorded_at，含 (deployment_id,revision)/(baseline_id,revision) 唯一与前驱唯一索引）。迁移 0027：升级捕获旧已报告行为 LEGACY_CURRENT；两表 UPDATE/DELETE 拒绝 trigger；降级仅在无更正且无 FIRST_REPORT 基线时允许。`_report_actual`：首次报告建 FIRST_REPORT（或 IMPORTED_CURRENT，若物理列已有值）基线 + 写物理列 + 原子审计；keyed 更正（request_id+expected_version+correction_reason）追加账本行、revision=前驱+1、物理列仍为当前值镜像。新增 `services/production_history.py::effective_actual`/`effective_actual_map`：有效值=baseline.recorded_actual_version + head revision，history_state 区分 NOT_RECORDED/LEGACY/IMPORTED/FIRST_REPORT(+_CORRECTED)/UNRESOLVED。详情/目录增 `actual_history`（history_state、recorded_baseline、correction_count、有界 corrections）与目录 `history_state`；前端 `production.ts` 增只读类型。Seed 对 DEP-0081 已报告行 insert-only 并建 IMPORTED_CURRENT 基线。API 0.18.46 / schema 0027。

边界：无键 legacy 覆盖本轮不变（设计「本轮尚未改变行为」），旧写者冻结 trigger 与无键 409 收紧留待后续 API 版本；未新增浏览器提交/身份/秘密/CI/调度/部署权限。下一包 `production-changeover-batch-history`（Changeover/Batch 自身更正账本 + 冻结），随后默认关闭浏览器提交、真实身份/内网验收、运营迁移、VIN。业务 36/44=82%；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0。精确 commit/PR head CI/合并/main/provider 证据追加本包 PR。

### 本包精确验收证据（PR87）

实现提交 `ada23cc`（FK 修复 `99f5ef1`、测试修复 `4e3e074`/`ef8d00e`），PR#87 最终 head `ef8d00e3cdda451ad1a199d3b9674e74cb9e553d`；PR head CI `39482340255` 三 job 全绿，后端 2324 passed / 无 skip。受保护 squash 合并 `3a33a1d8bb5edfddcbfa846e00407d7343b621cc`；main CI `39484008902` 三 job 成功。Render `/health/ready` ready 0.18.46/0027（合并触发重部署）；Cloudflare `softwarelifecycle.whf969.com` HTTP 200；Actions deployment `39485336857`/continuation `39485336931` skipped。

## 2026-10-21 生产事实更正设计契约补齐（Codex / ChatGPT Work）

当前包 `production-trace-correction-design-hardening`，独立分支 `codex/production-trace-correction-design-hardening`，基线main `c148c96a50a07167b714bf6b7649a55d96bd5eed`（PR85）。启动开放PR0；PR85的精确head36c7c0aa03854f4990882237b2392786b310c082、PR CI39464541840及main CI39465908034三项成功，已完成上一包核验，不重复设计初稿或ReleaseDecision实现。PR85的较新审查指出三处契约缺口，本轮只补四个文档文件。

设计统一旧库LEGACY_CURRENT与真正FIRST_REPORT，冻结基线不改旧审计；更正有显式前驱/revision及唯一链约束，重放原请求/actor/audit先于当前头；无键覆盖收紧、旧写者数据库拒绝、旧库部分/缺失证据和拒绝降级明确。§6逐个定位真实消费者及SQL聚合；§8覆盖真实PG并发双顺序、旧0026升级/原审计恢复、事务失败/降级/长历史/Seed更正后重跑。本轮不修改后端、Migration、Seed、界面、既有测试、依赖、CI、身份或提供方配置。API0.18.45/唯一head0026、Seed不变。

本地仅文档路径、进度和diff等必要检查，完整三项CI必须由本包精确PR证明，提交/PR/测试/合并/main/Cloudflare/Render/Actions最终证据追加本包PR；后续先核验真实PR，不因本文pending重复实现。启动Cloudflare生产aacb9481-5ed8-4030-b0c4-e5c14b5007f7/version f76d640f-6d7c-4487-ba2b-a8fd55c398df成功，Actions39467348427/39467348464 skipped；不是本包部署证据。

下一小包 `production-actual-history-backend-read` 只实施Actual基线、追加更正、所有actual读取/聚合和双语只读历史，精确路径/兼容收紧/PG验收见设计§9。Changeover/Batch更正再分包；不开新浏览器发送通道。先确认实际迁移仍0026，再新增唯一revision并同步配置，不照旧初稿批量实现三表。发现任一消费者仍读物理基线作当前值或Seed会重写正式行则不发布。业务36/44=82%；模块100/100演示/100演示/100/89/60/17；计划100/100/20/33/40/20/0不变。公共只读，OIDC/真实提交关闭，内网未部署，真实多用户/浏览器验收待批准环境。

## 2026-10-21 生产追溯事实更正设计审查（DeepSeek）

起点 main `8dbc24cb7474988146a6798ae69690fa98dbab1e`（PR84 已合并），开放 PR 0，无未完成开发。main CI `39460162355` 三 job 全绿。独立分支 `codex/production-trace-correction-design-review`。旧候选 `release-decision-supersession-backend-read` 已被 PR68/69/70 覆盖，不重复；按最新 HANDOFF 选 `production-trace-correction-design-review`。

本包只产出设计审查 `docs/production-trace-correction-design-review.md`，无后端/迁移/Seed/界面/依赖/CI/调度/身份/提供方配置变更。审查现有 `Deployment.actual` 原地覆盖式更正（`actual_version+=1`，历史值仅存审计 before）、`Changeover`/`Batch` 无更正命令、三表无 append-only trigger 三处缺口；推荐追加式更正账本（三张独立表 + UPDATE/DELETE 拒绝 trigger），`deployments.actual_*` 保留首次值、后续更正只追加、统一 resolver 派生"当前生效值"；不开放浏览器提交、不撤销已发生物理事实。详见设计文档 §1–§9。

业务 36/44=82%；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0。API0.18.45/schema0026 不变。精确提交/PR head CI/合并/main/provider 证据记录本包 PR。下一候选 `production-trace-correction-backend-read`（后端 + 迁移 + 追加式更正账本 + 统一只读投影，不开放浏览器提交）；其后默认关闭浏览器提交/原审计恢复、真实身份/内网验收、运营迁移，VIN 最后。

## 2026-10-21 发布链撤销双语确认与原审计恢复（Codex / ChatGPT Work）

当前包 `release-chain-revocation-ui-recovery`，独立分支 `codex/release-chain-revocation-ui-recovery-reviewed`，基线main `8eb25f4b90b506910837faf3b74690f27b66e9c1`（PR83）。开放PR0，PR80/81关闭、PR82/83合并；复用PR81草案并审查，未重复守卫或另启后台。精确实现提交/PR/CI/合并/main及provider结果追加在本包PR，后续会话必须先核对真实PR，不能凭本文pending重复开发。

新增双语workbench/result、精确同源规范恢复封装与行为测试；commands独立入口 `/commands?operation=release-chain-revocation`。四类UUID/审核上下文/reason/request_id确认后才可发送；默认关闭。准备/勾选/复制/导入不联网，import无send能力，unknown锁原命令仅查原审计，401/重复点击不二次POST；原原因转义显示，actor/时间通过精确原审计链接读取。修正PR81缺省kind与unknown提示。governance保持只读，详见 `docs/release-chain-revocation-ui-recovery.md`。

本地完整前端1494 passed/0 failed/0 skipped，Next/OpenNext、auth:check、cf:check成功；本地未重跑后台/真实PG，由精确PR完整三项CI证明，不伪造本地证据。API0.18.45/唯一迁移0026/Seed不变，幂等性不受影响，无CI/依赖/真实开关/权限/秘密/费用配置修改。进度与diff检查随本包执行。

基线main CI39455082138成功；GitHub Cloudflare检查证实生产build `f3928426-9756-42c5-aef5-a9c8910180cc`、Worker `4e1800ca-653a-4d18-a964-6ed6a081070b` 成功，旧“无token未验证”已补齐。Render既有live dep-dbbn73l9fdbs73ed2340为后台f221bdddc0e110fe61c9d72694408d78a64989b5；Actions39457194877/39457194880 skipped。这些是基线，不能复用为本包成功。

业务36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，不因UI/文档提升验收。公共只读、OIDC/真实提交关闭、内网未部署，批准环境真实多用户/桌面/手机/中英文验收仍待完成。下一候选 `production-trace-correction-design-review` 只审查Deployment/Changeover/Batch现有历史、消费者、锁/原子审计、旧库兼容和PG矩阵后划定实施包，实际身份/生产配置继续不触碰。

## 2026-10-20 发布链撤销 uncertain 后二次提交守卫（DeepSeek）

起点远端 main `489df90966a9a97ea76a67de005f602eee6fb64c`（PR79），开放 draft 检查点 PR80（记录 PR79 transport 反例，未合并）。独立 `codex/release-chain-revocation-unknown-submit-guard`。恢复 PR80 指出的 `release-chain-revocation-unknown-submit-guard` 优先任务，不并发 UI 包。

修复 `ReleaseChainRevocationSubmission.run`：`mode==='submit' && this.uncertain` 时锁定原 command/字节并直接返回当前状态，绝不二次业务 POST；后续 disabled/rejected/冲突不清除、不重发 uncertain 原请求；recover 保持只读原审计查询。新增独立反例测试（首次 lost 后二次 send 不再 POST、仅 recover 查询），调整 disabled/rejected 用例体现 uncertain 优先。红绿：移除守卫后反例 posts=2 失败，恢复后 6/6 通过。

本地前端完整 1484 passed/0 failed/0 skipped（新增 1 反例），tsc --noEmit 通过；本机 Next/OpenNext 构建与 auth:check 由精确 head frontend job 证明。无后端/API/schema/Migration/Seed/依赖/CI/调度/身份/提供方配置变更，API0.18.45/schema0026、Seed 幂等性不变。精确 PR/合并/main/Cloudflare/Render 最终证据记录本包 PR。

业务 36/44=82%；模块 100/100演示/100演示/100/89/60/17；计划 100/100/20/33/40/20/0。公共只读/OIDC/真实提交关闭。下一包 `release-chain-revocation-ui-recovery`：双语确认/结果 workbench、audit-only 导入/导出、i18n 与 commands 页独立入口，不启用真实开关；生产事实更正与 OIDC 提供方/多用户验收继续独立待定。

### 本包精确验收证据（PR82）

PR head CI `39449893219` 三 job 全绿，squash 合并 `d444c9ae3e034fd81754745793a5d59d05828d54`（PR82），main CI `39451566237` 三 job 成功，前端 1484 passed/0 fail/0 skip。Cloudflare 前端 HTTP 200 可达但本地无 token 未确认 Workers 已切 `d444c9ae`（未验收）；Render health ready 0.18.45/0026（纯前端未触发后端重部署）；Actions deployment `39453032788`/continuation `39453032728` skipped。

## 2026-10-20 发布链撤销受控提交浏览器协议（DeepSeek）

起点远端 main `f221bdddc0e110fe61c9d72694408d78a64989b5`（PR78），开放PR 0、无同包远端分支；独立 `codex/release-chain-revocation-browser-protocol`。已核对PR78/main CI三项成功（基线证据，本包精确head另验）。

本包实现严格 discriminated 撤销命令 `frontend/lib/release-chain-revocation-transport.ts`：四类 target_kind、expected_context v1（version 整数1、七 canonical lowercase UUID、按目标深度强制可空/非空且 target_id 等于对应节点）、reason 1–4000、envelope 按真实字节 24KiB 上限、四类固定路径与 action、Submission 状态机 lost 锁原字节/audit-only recover。`release-chain-revocation-audit.ts` 严格校验 `EVT-RCR-{hex}` 的 event_type/entity_type/entity_ref/action/detail/payload（revocation_id、三身份 UUID、reason、protocol_version=1、review_context、request）与 actor 绑定、declared_actor_name=null，不借当前状态推断原结果、不把 legacy 审计升级为 v1 回执。

新增两条同源代理 `/auth/release-chain-revocation`（submit）/`-receipt`（recover），仅 POST；`browser-auth.ts` 增三开关精确匹配 `releaseChainRevocationSubmissionConfigured` 与 `handleReleaseChainRevocation`（24KiB），`browser-session.ts` 增 `executeReleaseChainRevocationCommand`（一次 POST 后经原审计确认，审计响应 64KiB 上限，recover 允许只读会话）。`check-browser-auth.cjs` 增补两条路由禁用检查与环境变量。

本地前端完整 1483 passed/0 failed/0 skipped（新增 8 项），TypeScript `--noEmit` 通过；本机 Next/OpenNext 构建与 auth:check 因沙箱拦截 `.next` 写入未本地完成，须由本包精确 head frontend job 证明。无后端/API/schema/Migration/Seed/依赖/CI/调度/身份/提供方配置变更，API0.18.45/schema0026、Seed 幂等性不变。契约见 `docs/release-chain-revocation-submission-design-review.md`；精确 PR/合并/main/Cloudflare/Render 最终证据记录本包 PR。

业务 36/44=82%；模块 100/100演示/100演示/100/89/60/17；计划 100/100/20/33/40/20/0。公共只读/OIDC/真实提交关闭、内网未部署、真实多用户验收未完成。下一独立包 `release-chain-revocation-ui-recovery`：双语确认/结果 workbench、governance 页入口、i18n 与 audit-only 导入/导出，不启用真实开关；生产事实更正、OIDC 提供方/多用户验收继续独立待定。

## 2026-10-20 撤销审核上下文后台绑定（Codex / ChatGPT Work）

起点远端main `91ef88765d2bf666c6239b0359e8368a42efbc41`（PR77），开放PR 0、无同包远端分支；独立 `codex/release-chain-revocation-review-binding-backend`。已核对PR77/main CI39425287506三个job成功、Cloudflare生产961463a0-6c41-439e-8f1a-6429c6987422成功，Render既有live dep-dbah7n942hec73dkdv90仍对应后台943a342d；Actions39426311122/39426310917 skipped。旧候选ReleaseDecision实现已完成，不重做。

本包在现有四POST增加可省略但不可显式null的严格v1 expected_context；锁内精确比较审核决策/冻结Snapshot身份及完整父链。原actor/原正文重放先于当前资格检查，legacy审计不补写。新增protocol_version/review_context原子审计、专用GET精确target/context，以及严格字段/四角色范围/公共只读/长历史有界和真实PG竞态/重放/回滚回归。初次完整本地回归发现Deployment详情不应加载决策，已将审核读取限制在专用GET，原测试保留并重新验证。无新migration、Seed或浏览器能力，API0.18.45/schema0026不变；不修改0026、真实身份/开关/秘密/计费/CI/调度/部署权限。实现与验证说明见 `docs/release-chain-revocation-submission-design-review.md`；本地与精确PR/main/provider最终证据记录对应PR，不把PG skip算通过。

本地最终完整后端1671 passed/638 skipped（无真实PG地址）；撤销/Deployment定向41 passed。唯一head0026、离线SQL、进度和diff通过。真实PG并发/迁移及完整前端/Next/OpenNext由本包精确head CI证明；合并后main/provider另核验，最终精确提交/PR与证据记录PR。

业务36/44=82%；模块100/100演示/100演示/100/89/60/17；计划100/100/20/33/40/20/0。公共只读/OIDC和真实写入关闭，内网未部署，多用户/真实浏览器仍未验收。下一独立包 `release-chain-revocation-browser-protocol`：新增严格transport/audit projector及两条固定同源代理、独立默认关闭开关、unknown只查原审计；依据本设计新增v1字段，不能从当前治理状态确认原结果，不降级legacy审计为v1证明。再后 `release-chain-revocation-ui-recovery`，不在本包提前实施。

## 2026-10-20 发布链撤销受控提交设计审查（Codex / ChatGPT Work）

真实基线 main `74fa2e694c56da7ea7eeb4e0f0d080cde4a2fb21`（PR76），开放PR 0；独立分支 `codex/release-chain-revocation-submission-design-review`。PR76 main CI39421592004三个job成功，Cloudflare生产2925a4b4-b0e2-4486-8940-845bb48fad25成功；Render既有live dep-dbah7n942hec73dkdv90仍为后端943a342d，不是PR76部署；Actions39422865320/39422865279 skipped。已完成前序核验，没有重做撤销后台/只读页面。

本包只新增 `docs/release-chain-revocation-submission-design-review.md` 并更新状态/本交接/进度。核对实际四路由、角色、锁序、精确actor/请求重放、activity原审计读取和既有浏览器模式，识别审核上下文尚未绑定与旧审计字段不足；选择版本化expected_context锁内比较→默认关闭窄浏览器协议→双语确认/audit-only恢复三小包。旧请求重放保持，旧审计不得升级伪造审核证明，unknown不重发，无实际配置写入。完整测试矩阵及后续精确路径在设计中。本地验证、精确发布提交/PR、CI与合并后provider最终证据以本包PR记录为准，未把基线通过当本包结果。

API0.18.45/schema0026/Seed幂等性不变；业务36/44=82%；模块100/100演示/100演示/100/89/60/17；计划100/100/20/33/40/20/0。下一包 `release-chain-revocation-review-binding-backend`：四类撤销strict body、可选legacy兼容的v1审核context、锁内比较、完整原审计、精确治理context与真实PG回归；不开放浏览器写入，不改0026。后续 `release-chain-revocation-browser-protocol`、`release-chain-revocation-ui-recovery` 逐包推进。公共只读/OIDC与真实提交关闭，内网及批准提供方多用户验收未完成。

## 2026-10-20 发布链撤销只读页面（Codex / ChatGPT Work）

从PR75合并 main `b2e40426148bb4d3166effef417b9052ce5fa6f9` 创建 `codex/release-chain-revocation-browser-read-only`，无开放PR。基线main CI39418506472三个job、Cloudflare生产3fe95c2a-99c6-4397-b19d-8bd6a7368ae4成功已核对；Render既有live仍943a342d。新增四类精确UUID `/governance/{kind}/{targetId}`双语只读页和SSR/ASR/Delivery revision/Distribution/Authorization入口；一次固定GET/10秒超时、最多四节点，分清原status、自身撤销、祖先阻断、无法解析。未知/矛盾/重复/越界响应拒绝，原原因和记录者转义但不翻译；原审计链接使用UUID hex。不存在提交表单、浏览器发送协议或新身份配置。

本地完整前端1475 passed，新增12行为测试及自动新增1页面本地化覆盖；Next/OpenNext build成功。首次定向本地化仅缺Audit中文词条，补齐后重验。后台/PG本地未执行，不借基线成功作为本包验证；本包精确PR head完整CI、合并/main/provider最终证据在PR记录。无后端/API/schema/Migration/Seed/依赖/CI/调度/提供方变更，API0.18.45/schema0026，Seed幂等性不变。历史交接完整保留。

业务36/44=82%；模块100/100演示/100演示/100/89/60/17；计划100/100/20/33/40/20/0。公共只读/OIDC与真实提交关闭，内网未部署，真实桌面/手机多用户验收未完成。下一候选 `release-chain-revocation-submission-design-review`：独立默认关闭提交/原审计/未知结果恢复的设计审查；不直接开放实际写入，不更正已有生产事实。

## 2026-10-19 发布链永久撤销后端与统一读取（Codex / ChatGPT Work）

真实起点为远端 `main` `f571f296fcd61daad2cfe2da49f9baf1902503ba`，分支 `codex/release-chain-revocation-backend-read`，PR74 最终 head `f32de3c8d4b0c0df737a62bffa5d76717a9270d7`，受保护合并 main `943a342d80f3d229a790c93ae646dac76410ed86`。API 已提升至 `0.18.45`，Alembic 唯一 head 为 `0026_release_chain_revocation`。新增不可变 `release_chain_revocations` 账本、四类永久撤销 POST、统一 governance GET/详情投影、根到叶锁序、旧写者数据库 guard、原子审计和精确重放。撤销不改原 status、不制造子撤销、不删除既有 Deployment/Changeover/Batch；许可型新写入阻断，actual/Changeover 事实记录保留。

本地结果：相关回归 224 passed/1 skipped；完整后端 1643 passed/629 skipped，跳过项因没有真实 PostgreSQL 地址，未作为通过；前端 1462 passed；Next/OpenNext build 成功；迁移单一 head 已确认。PR 精确 head CI `39154785266` 与独立 main CI `39155649606` 的后端/PostgreSQL、前端/Cloudflare build、CI acceptance 均成功；两轮均为 2272 backend passed、233 PostgreSQL-module cases/no skips、1462/1462 frontend passed。

Cloudflare Preview deployment `d23b3bea-9e94-42a8-9e43-c7225939e995` 与 main Production build `061e181b-3551-4814-b7cf-9da6cf6818f5` 成功。Render `dep-dbah7n942hec73dkdv90` 已 live 并精确对应 `943a342d80f3d229a790c93ae646dac76410ed86`，验收窗口无 error 日志；未执行手工部署或配置写入。Actions deployment `39156415283` 与 continuation `39156415252` 为 skipped。完整回执见 `docs/release-chain-revocation-verification.md`。

安全边界未变：公共演示只读；OIDC、真实身份/业务写入、公司内网和生产配置关闭；未修改身份、密钥、凭据、计费、CI、调度器或部署权限。36/44=82%；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0。下一包 `release-chain-revocation-browser-read-only`：为四类治理状态和有界撤销历史提供中英文只读显示；不要开放提交。之后另包设计默认关闭受控提交与原审计恢复，再做批准提供方/多用户验收。

## 2026-10-18 发布链追加式撤销设计验收闭环（Codex / ChatGPT Work）

PR72 最终 head `2ce160adebeeb6e18aba561cb507cc14326fec6d`，精确 head CI `39131206270` 三项必需检查成功；受保护合并 main `7e18b9a6e4cc59fb4434187bf3c5b30de26420f9`，独立 main CI `39131785281` 三项成功。两轮均确认后端 2267 passed、真实 PostgreSQL 模块 230 cases 无 skip、迁移单一 head `0025_release_decision_supersession` 往返成功、前端 1462/1462 passed，以及 Next/OpenNext build 成功。

Cloudflare exact-head Preview `2a7da6f6-7821-4667-bd24-5d62b8433d89` success；main Production build `1292d2c5-f420-4ad4-a345-1bf930bf6034` success，version `64e580e3-bcbb-4ed4-b871-bf18683bd16a`。Actions deploy `39132510691` 与 continuation `39132510713` 明确 skipped。Render 后端服务未因 docs-only 变更部署；最新 live `dep-dba2n68ae00c739c31j0` 仍对应 `aad807cd1ec16afccdf1cb3bb124c22dec0cc90a`，观察窗口无 error 日志，不能把它称为 PR72/main `7e18b9a` 的部署。

安全门禁未变：公共只读，OIDC/真实提交/内网/生产配置关闭；未修改身份、密钥、计费、CI、调度器或部署权限。36/44=82%；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0。下一独立包 `release-chain-revocation-backend-read`；只实现后端、迁移、统一读取和双语只读展示，浏览器受控提交另包。

## 2026-10-18 发布链追加式撤销设计审查（Codex / ChatGPT Work）

真实基线为已合并 PR70 的 `main` `b1097a97c80cc27f58699d9606020ad93ab48b61`，启动开放 PR 0；独立分支 `codex/release-distribution-revocation-design-review`。本轮只新增 `docs/release-distribution-revocation-design-review.md` 并更新状态/进度/交接，不实现后端、迁移、Seed、界面提交、依赖、CI、身份、门控或提供方配置。

审查推荐独立 `release_chain_revocations` 追加式账本，以四个真实 nullable FK+XOR 约束精确撤销 Release、DeliveryPackage 修订、Distribution 或 SoftwareAuthorization。撤销不改原 status，不自动撤销后代，不删除或重写既有生产事实；统一 resolver 分开返回 recorded status、自身撤销、祖先阻断和未来写入资格。Release/包/分发/授权撤销分别阻断后续许可链；已有 Deployment/Changeover/Batch 及 actual report 保留，actual/Changeover 事实仍可补录但不能生成生产许可。

下一实现建议 `release-chain-revocation-backend-read`：实现时从实际 0025 后创建唯一 0026，新增四类后台撤销、Release→Package→Distribution→Authorization 统一锁序、数据库旧写者 insert guard、原子审计/精确重放、统一有界读取、双语只读展示和真实 PG 并发/升级降级/长历史测试。该包不开放浏览器提交；受控浏览器协议和原审计恢复另包，生产事实更正再后。当前 API0.18.44/schema0025/Seed 不变。

本设计无业务验收增量：36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0。公共样例只读、OIDC/真实提交/内网仍关闭；真实多用户桌面/手机和中英文浏览器验收仍待人工授权环境。本包精确 PR head CI、合并 main、Cloudflare/Render/Actions 证据以 PR 最终记录为准，不复用 PR70 成功。
## 2026-10-18 ReleaseDecision 追加式替代浏览器协议验收闭环（Codex / ChatGPT Work）

PR70 最终 head `6b0400404f9aee69eab98ebdaed12f747480a126`；早期 head `969ef6e` 的本地化覆盖失败后已修复，失败提交未合并。最终精确 head CI `39107462789` 三项必需检查全绿，随后合并为 main `b1097a97c80cc27f58699d9606020ad93ab48b61`，独立 main CI `39108012123` 三项全绿。验收计数：后端 2267 passed、真实 PostgreSQL 模块 230 cases no skips、前端 1462/1462 passed，Next/OpenNext build 成功。

Cloudflare production build `a9bcc79f-187a-466d-b82c-b0a73765ab10` 成功，version `9920621e-153f-4f63-89a1-898919f9c98e`；Actions deploy `39108584069` 与 continuation `39108584068` 均明确 skipped。Render 后端服务因本包为纯前端、服务根目录为 `backend` 而未触发新部署；最新 live `dep-dba2n68ae00c739c31j0` 仍精确对应 `aad807cd1ec16afccdf1cb3bb124c22dec0cc90a`，只读日志持续 health 200。不要把该健康基线表述为 `b1097a9` 已部署到 Render。

安全门禁不变：公共只读，OIDC/真实提交/内网/生产配置关闭；未修改身份、密钥、计费、CI、调度器或部署权限。36/44=82%；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0。下一独立包：`release-distribution-revocation-design-review`；先形成追加式撤销/阻断设计审查，再分别实现后端读取与默认关闭浏览器协议。真实提供方与多用户浏览器验收仍需人工授权环境。
## 2026-10-18 ReleaseDecision 追加式替代浏览器协议（Codex / ChatGPT Work）

真实基线为已合并 PR69 的 `main` `aad807cd1ec16afccdf1cb3bb124c22dec0cc90a`，启动开放 PR 0；独立分支 `codex/release-decision-supersession-browser-protocol`。新增严格 transport/audit projector、独立默认关闭同源代理、双语准备/精确确认/结果 UI 和有效决策详情入口。命令固定新审批请求与 UUID、当前前驱、同 Release/冻结 Snapshot、完整新 decision/readiness/notes/correction_reason；代理向既有后端只转发准确业务 body。成功提交后仍以原 `DECISION_SUPERSEDED` 原子审计为唯一确认，不使用当前对象状态推断原结果；网络不确定会锁定请求，只提供 audit-only recovery，后续禁用/拒绝/冲突不能抹除未知状态。

开关要求 mode、批准 API base、批准 app origin 三项精确匹配；提交还要求非只读认证会话，公开演示仍禁用。没有修改后端、数据库、迁移、Seed、依赖、CI、身份、秘密、调度或部署配置；也没有触发真实业务写入。新增协议文档和 7 项定向测试，当前 7/7 passed；完整前端/Next/OpenNext、后端/真实 PG 必须由本包精确 PR head 三个 CI job 成功证明。PR、精确提交、合并后 main、Cloudflare 与 Render 证据在本包最终验收记录中补齐，不能复用 PR69 基线证据。

公共只读、OIDC/真实提交/内网仍关闭。36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0。下一小包建议 `release-distribution-revocation-design-review`：只定义发布、交付、分发和授权的追加式撤销/阻断语义，明确不改写历史生产事实；之后才分别实现后端/读取、浏览器协议和生产更正。真实提供方多用户、桌面/手机、中英文验收仍待人工授权环境。

## 2026-10-18 ReleaseDecision 追加式替代后端/读取实现（Codex / ChatGPT Work）

基线是已合并 PR68 的 `main` `16c791d11f59315f655d57d0314207f581dedb1c`；开放 PR 0，分支 `codex/release-decision-supersession-backend-read`。实现 `0025_release_decision_supersession`、ReleaseDecision append-only trigger、同上下文复合前驱、唯一后继、有历史拒绝降级和共享有效决策 SQL resolver。原 POST 路由增加成对 `supersedes_id`/`correction_reason`，只接受当前有效前驱、同 Snapshot、新 APPROVED ApprovalRequest；原请求/actor/审计重放和业务审计原子性保持。主要当前消费者统一使用 resolver，历史/生产来源保留原记录并暴露 predecessor/successor/effective；RD-0081 Seed 改为精确验证而非更新。API `0.18.44`，schema `0025_release_decision_supersession`。

ReleaseDecision 详情提供中英文只读关系，不开放浏览器提交。当前本地证据：1641 后端 passed、626 PG 模块因无 `TEST_POSTGRES_URL` skipped；针对性 93 passed/4 PG skipped；Alembic 全链离线 SQL成功；前端 1453/1453 passed，Next 15.5.24/OpenNext Cloudflare bundle 成功。远端精确 head 的三个 CI、真实 PG、PR/合并/main/provider 证据必须以本包最终记录为准，不能复用 PR68。Render 启动只读检查仍为旧 live `dep-db5sl1fgfhjc73eva640`/`9dba7e9`；没有手工触发部署。

公共演示只读，OIDC/真实提交/内网仍关闭。本包不撤销已有 Delivery/Distribution/Authorization/Deployment/Changeover/Batch。36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0。下一包：`release-decision-supersession-browser-protocol`，独立默认关闭、原审计恢复和双语确认；随后再划定发布/分发/授权撤销及生产更正。

## 2026-10-17 ReleaseDecision 追加式历史替代设计审查（Codex / ChatGPT Work）

真实基线为 PR67 merge `daa14183197eecb5590f973f45817be79f695444`，独立分支 `codex/release-review-history-design-review`。PR67 最终 head `8a254b93b449a470973932cdb9ebecd8dad061c6`、CI `39007389782` 三 job success；独立 main CI `39010669503` 三 job success，Cloudflare production build `b5ad9937-094a-482a-9e7e-cd6cc6c7ee98` success。Actions deploy `39011070086`/continuation `39011070091` skipped。

Render 只读检查复用已授权 My Workspace：free API 服务仍绑定 main，最新 live deploy `dep-db5sl1fgfhjc73eva640`/commit `9dba7e9`；未触发部署、重启、升级或配置写入。日志显示休眠前连续 health 200；首个 30 秒冷启动请求超时，第二次约 20 秒返回 200、API0.18.43/schema0024。该服务后端部署落后于当前前端 main，不能把现场健康响应称为 PR67 后端部署。

新增 `docs/release-decision-replacement-design-review.md`，只定义正式 ReleaseDecision 的追加式 SUPERSEDE。更正必须引用同 Release/同冻结 Snapshot 的当前全局有效前驱，使用新 request/decision_no、匹配的 APPROVED ApprovalRequest、完整新 decision/readiness/notes 和独立 correction_reason；原正式决策、ApprovalRequest/Step/Action 与原审计不修改。WITHDRAW 以及已有 Delivery/Distribution/Authorization/Deployment/Changeover/Batch 的撤销不在本包，留给计划6的独立下游政策，不能把 HOLD 或未来新写拒绝说成既有实物回滚。

下一实现建议：确认 Alembic head 后新增拟议0025；supersedes_id/correction_reason paired、同上下文复合FK、唯一后继、禁止自指、append-only trigger及有历史时拒绝降级；保持 Release→Approval 锁序；原重放全正文/actor/审计绑定；共享有界有效决策 resolver 覆盖 Approval、Distribution、governance、dashboard、passport、demo、production/activity；普通DECIDE兼容。现有主Seed须改为缺失插入/存在精确验证/碰撞失败，不能在append-only后修补旧决策。真实PG需覆盖双替代、替代与交付/授权提交顺序、原子回滚、迁移往返/trigger/长历史。

本包仅设计/状态/进度/交接文档，无业务代码、迁移、Seed、依赖、CI、调度、身份、门控或提供方配置变化；0025只是提案。公共样例只读、OIDC和真实提交关闭、内网未部署。36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，增量0。下一包 `release-decision-supersession-backend-read`，之后单独受控浏览器替代协议，再处理发布/分发/授权撤销、生产更正、真实身份/浏览器、内网与运营迁移，VIN最后。

## 2026-10-13 Excel 总览组合筛选与分页（Codex / ChatGPT Work）

基线真实 main `1d134dada149ceb2b70a9f18e46c04c7a826366e`（PR61已合并），开放PR为0。独立main CI38260714118三必需job success已核对：2262后端、228 PostgreSQL-module cases/no skips、1344前端及Next/OpenNext/disabled auth SSR；Cloudflare生产build23c53e09-d4c9-4b5f-bf76-28b8b64757eb success。Actions deploy/wake均skipped，不能称Actions部署启用。本包精确head/main CI及生产证据由本包PR最终记录独立核对，不复用基线。

继续最高优先级第四轮云端只读演示范围，/demo/zfi新增类型/客户/审批状态组合筛选、未记录审批筛选及每页10条分页。GET导航固定本站路径；更换筛选重置页码，翻页保留其他筛选，异常/重复页码归一化，超界整数定位末页；空交集明确显示无匹配，不回退其他客户。顶部统计继续使用完整当前API家族，列表统计独立，原版本/客户/项目/日期/审批/UUID链接不改、不把同版本客户合并。筛选组有选中状态与键盘焦点，链接可换行；总览表格支持移动端横向滚动。中文默认/English标签完整，页面无业务命令表单，不增加API请求或后端扫描。

首份提交e734221c的CI38396273162前端1365/0fail/0skip通过，但Next生成PageProps拒绝默认参数使FirstArg包含undefined，生产构建失败；未合并。改为非可选props类型及运行时可选读取，保留无参数既有调用；本地153定向重验，最终精确head完整CI必须另验，不将首轮前端测试当构建成功。

新增21项行为回归，旧实现17failed/4passed证明缺能力；新实现与既有总览/发布证据/完整本地化检查共153passed/0failed/0skipped。首轮本地化检查发现Release type/Approval status/Page词条缺失，补齐后通过；已有测试/断言未改。进度--check通过。本机GitHub DNS不可解析，通过授权GitHub连接恢复固定main前端源码；npm离线完整安装缺jose缓存，后以锁文件integrity读取既有TypeScript/React缓存，仅供定向测试。没有本地完整Next/OpenNext/后端/真实PG验证，必须由本包精确既有CI证明；未改依赖/锁文件/CI/迁移/Seed/后台/身份或门控。

Render初始兼容会话无工作区；后从较新用户记录确认2026-10-11已明确授权My Workspace及保持免费，复用tea-datl248u01pc739j09eg核验既有free服务srv-datm6o6k1f9s738r19gg。最新部署dep-db5sl1fgfhjc73eva640为live，精确旧main9dba7e948ac1d35d5544663e65d0b4686fc6babc；未新建/升级/重启或改配置。直接GET /health/ready因当前执行环境DNS不可解析失败，日志查询无健康记录，不声称本轮API版本/schema/样例已重验；旧2026-10-12观察不得当作本轮证明。已有My Workspace授权可延续，无需再次确认。浏览器既往403/1010仍保留，未绕过/重试拒绝；电脑/手机双语现场链路验收未完成，第四轮保持in_progress。公司内网未部署、公开样例只读、OIDC/真实提交关闭，无付费模型API或登录缓存上传。

业务验收增量0：36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0。下一步：本包精确CI成功后受保护合并、独立main/provider核对；随后在已授权Render工作区和恢复正常访问的浏览器中完成总览筛选分页→SSR/ASR→四级审批→当前Snapshot/Readiness/Decision/Passport链路。Excel文件/测试仍未提供，不自行合成或扩大Impact提交、身份/内网范围。

## 2026-10-12 Excel 演示总览与第四轮状态核对（Codex / ChatGPT Work）

从真实远端main 9dba7e948ac1d35d5544663e65d0b4686fc6babc开始，开放PR为0；PR60真实merged及独立main CI38160754690三必需job success已核对（2262后台/228 PostgreSQL-module cases无skip、1336前端/Next/OpenNext）。PR60最终记录覆盖旧“尚未合并或导入”；Excel测试库已导入20记录，未重复执行Seed或改历史。

新增 /demo/zfi 中英双语只读总览，消费既有GET /api/v1/demo/zfi-import：4SSR/16ASR及各行原编号、原版本、客户/项目、原发布日期、实际审批状态、UUID详情/审批导航和已提供文件/测试数。统计从当前API行计算，不硬编码15/3/1/1；同版本KUBO/VOL保留独立UUID。未导入/部分/无API/外来响应不显示成功家族，不补造证据；导入回执/原日期/合成审批不等于当前Readiness、实际人员审批或正式Decision。标准/应用目录与原证据页增加总览入口。

四轮账本更新第三轮completed_code（PR58/59已恢复），第四轮in_progress；本次实际API观察health ready0.18.43/schema0024，Excel initialized true/20，独立发布证据initialized true/3：SSR2.0与ASR-A2.0 READY+RELEASE/精确当前Snapshot确认，ASR-B2.0 APPROVED但NOT_READY+HOLD/不确认正式发布。该三例为先前独立合成家族，不能当成Excel版本真实测试证据。Render既有free服务dep-db5sl1fgfhjc73eva640 live精确旧main，Cloudflare旧main生产check成功。首次health30秒超时，后续read-only请求ready，未重启/升级服务。真实浏览器仍沿用历史403/1010阻碍，未绕过/重试拒绝访问；电脑/手机/中英文现场验收未完成。

本地7新增行为回归及既有6证据回归13通过；完整前端1344 passed/0 failed/0 skipped，生产Next/OpenNext与disabled auth SSR最终结果记录本PR。后台/API/迁移/Seed/依赖/既有测试/CI/身份/秘密均未修改；schema0024/API0.18.43及Seed幂等代码保持不变。本地未重跑完整后台/真实PG，精确feature完整CI成功后才合并，合并后main/provider另验；最终提交/CI/部署以本包PR记录为准。

本机fetch无及时结果，未覆盖旧未提交工作；独立目录以d84c363旧树加从当前main读取的15差异文件复原代码，发布树从真实main tree构建，只提交本包8个前端/计划/交接路径，不把历史差异再提交。Codex直接在ChatGPT Work通过GitHub连接，不调用付费模型API、不上传登录缓存/启用Actions开发；免费测试公开只读/OIDC及真实提交关闭，内网暂缓。

业务验收增量0，36/44=82%；七模块100/100演示/100演示/100/89/60/17，七计划100/100/20/33/40/20/0。下一步正常浏览器核对总览→SSR/ASR→审批节点→当前证据/成功阻断链接；未提供Excel组件/固件/测试，后续补齐须有资料或明确合成授权，不自行扩大为身份/内网/Impact提交实现。

## 2026-10-12 ZFI Excel 演示导入（Codex / ChatGPT Work）

基线真实main d84c363af1794fa953753eacff2d8b40d8528b1d，无开放PR；基线三个CI及Cloudflare生产success，Actions deploy/wake skipped。用户授权Excel导入，2供应商/2产品/2客户/4项目/4SSR/16ASR，固定UUID保留原版本与客户/项目。审批A7 z修正SSR02，孤立M22忽略。运行目录恢复丢失未推送内容后，已保存PR60检查点2e3c751c3984a09607d8e3250afa8c21aca9bda7；清单依据此前逐行核对内容恢复，不伪造不可用原附件字节哈希。

新增0024_release_customer_scope nullable客户scope与唯一索引；旧NULL记录、快照、审批、审计不回填。新增scopedASR由PG延迟触发器验证客户/项目/同产品SSR，客户身份不可改，有scoped记录拒绝丢语义降级。版本兼容读取歧义409，UUID目录保留明确消歧。API0.18.43，required head0024。新增GET /api/v1/demo/zfi-import固定20UUID读取当前对象与导入回执；导入回执不证明当前正式发布。

seed_zfi_demo独立opt-in、flush-only、调用方原子commit；PG advisory事务锁、固定UUID、规范化manifest哈希、碰撞拒绝、重复保留历…101456 tokens truncated…两类门控与首批三类互相独立，服务器唯一当前USER只向页面投影四个布尔能力。未知原请求跨编辑/上下文/能力/命令切换保持冻结。APPROVED步骤可仍为PENDING审批；决策/Readiness只展示原声明和精确冻结快照，不推断当前状态、replayed或授权下游。仅内存，不支持跨卸载/刷新/会话导入恢复。
69页面/API代码0.18.36/schema0020，36/44=82%；七模块100/100演示/100演示/100/89/60/17，七计划100/100/20/33/40/20/0，增量0。14业务/2自身会话/6管理员/离线操作分计，五类默认关闭提交通道有界面，九类仍只准备；不等于真实身份或14类全提交验收。
公共样例只读/OIDC及所有提交默认关闭；未配置实际变量/秘密/身份/授权，无真实浏览器/管理员/提供方/API在线探针/内网安装，不重试被拒绝浏览器访问。内网未安装，SSO/人员/Windows无Docker/系统架构待定。Render工作区/后台部署版本未核验，原SoftwareLifeCycle_12全文未取得。Mac部分快照/GitHub连接服务发布，完整套件来自Actions，无独立云端Codex任务；本地Node补正测试语法通过，进度账本未改、--check通过，全部交接历史保留。
下一包实现Delivery Package/Distribution/Production Authorization三类独立默认关闭的提交与原审计恢复契约、严格解析/精确原回执和冻结控制器，随后接入双语界面；剩余9业务通道还包括Test Release/Deployment/Changeover及Impact/Acceptance/Resource。之后真实身份及内网验收、跨会话导入恢复、追加更正撤销、无Docker离线安装及运营迁移，VIN最后。


## 2026-10-09 本轮开发：交付、分发及生产授权提交基础（Codex）
起点main 56c17665ea09a2cc1cfe8fa933743ef241ef56c9，精确CI37821889579三个任务成功（2071后端/172 PostgreSQL-module cases/no skips/855前端）、Cloudflare生产build8e905de2-2dbc-42af-a1f2-17d14bb11e14/version7d65cc6f-7bac-4867-9081-f43730567bd1成功、两次Actions部署skipped、开放PR0。本包提交后的精确head CI/provider待核对。
交付包/分发/生产授权三类独立默认关闭的提交与原审计恢复代理、严格正文/UUID目标绑定/不可变artifact集合/明确finite-null范围、actor/request绑定原审计投影及DistributionSubmission冻结原请求控制器已实现。三个POST成功HTTP201后仍须精确原审计；恢复只GET，不回退重写。回执保留原READY/DRAFT、精确修订、接收方、冻结证据和生产授权范围，不推断current/replayed/签收或量产批准。三类页面发送/查询/结果下一包，现有五类UI不重复实现。
新增传输/原审计/精确回执/控制器以及实际RSA OIDC代理行为回归，覆盖三类原字节提交、readonly只查询、完整原actor/body指纹、artifact集合与重复、修订/接收方/finite-null范围、UUID/正PG整数/UTF-8总界限、单次HTTP成功仍需审计、不同当前状态、失联明确重试、同步互锁、拒绝/缺失不能抹除unknown及禁止客户端凭据/path注入。两个新force-dynamic Node路由GET405/默认POST503加入实际Next禁用认证SSR检查。首批/治理/管理员既有行为及门控不改；没有直接启用真实变量/秘密/身份/授权。
本地Node测试语法及进度--check通过，Mac部分快照没有完整TypeScript/Node依赖；完整套件/类型/Next/Worker/真实PG/生产禁用SSR待Actions，不称本地全套通过。69页面/API代码0.18.36/schema0020不变，没有后台/schema改动。
公共样例只读/OIDC及全部提交默认关闭；内网未安装、SSO/人员/Windows无Docker/系统架构待定。真实浏览器/管理员/提供方/API在线探针/内网验收未进行，不重试被拒绝浏览器访问。Render工作区未选择、后台部署版本未核验；原SoftwareLifeCycle_12全文未取得，无另启独立云端Codex任务。仅内存，跨会话恢复未实现。
36/44=82%；七模块100/100演示/100演示/100/89/60/17，七计划100/100/20/33/40/20/0，增量全部0。14业务/2自身会话/6管理员/离线操作分计。八类业务已有代理/控制器，五类已有UI，九类UI尚待接入，不称全部14类真实提交验收完成。
下一包把Delivery Package/Distribution/Production Authorization既有准备接入双语确认发送、原审计查询、明确原请求重试和精确结果，采用独立distributionSubmissionConfigured及唯一当前USER只读投影，未知原请求跨命令/上下文/能力刷新不被覆盖。之后实现其余6业务通道及界面（Test Release/Deployment/Changeover、Impact/Acceptance/Resource），真实身份与内网验收、跨会话导入恢复、追加更正撤销、无Docker离线安装及运营迁移，VIN最后。
契约docs/distribution-command-submission.md。


## PR#32 验收 — 2026-10-09（Codex）
PR https://github.com/Wang106/SoftwareLifeCycle/pull/32 已合并，代码main c47048c40ccad73cd85477da299d26e3f912f7f3，最终feature 8e0a572bb6ecc1e6e5d9bf308439c12967ab4d29，起点main 56c17665ea09a2cc1cfe8fa933743ef241ef56c9。
精确feature CI37863767376三个任务全部成功：2071后端（410.11秒）、172 PostgreSQL-module cases/no skips；895前端0fail/0skip，原855新增24传输/解析/原审计/回执/冻结控制器和16实际RSA OIDC代理回归=40。0020单迁移头、SQL、隔离PG升降级往返、进度--check、类型检查、Next/Cloudflare Worker及中英文禁用认证SSR全部通过；两条新路由GET405/POST503，private/no-store。后端113605602650、前端113605602380、acceptance113607738388成功。Cloudflare feature Preview build64bfa355-e716-4cee-b457-85c9c0528a22成功；不是main生产部署证据。
首轮feature e6caa6e6d2bade66d337cfa5274926e954574f6d CI37863535031有4项新增测试断言失败：按任意输入对象JSON字段顺序比较，而发送正文来自已确认的规范化Review。已修正为比较原确认Review的冻结字节及后台POST全部字段内容，失联/明确重试逐字节一致检查保留，最终895全部通过；不是旧邮件的后台PG问题，不隐去已解决的首轮失败。
交付包/分发/生产授权三类独立默认关闭的提交与原审计恢复代理、严格正文/UUID目标绑定/不可变artifact集合/明确finite-null范围、actor/request绑定原审计投影及DistributionSubmission冻结原请求控制器已实现。三个POST成功HTTP201后仍须精确原审计；恢复只GET，不回退重写。回执保留原READY/DRAFT、精确修订、接收方、冻结证据和生产授权范围，不推断current/replayed/签收或量产批准。三类页面发送/查询/结果下一包，现有五类UI不重复实现。
严格UUID目标与正文绑定、正PG整数及finite/null范围、规范化后重复artifact拒绝和不可变集合、完整原actor/body指纹、HTTP201仍需原审计、原READY/DRAFT区别于后续状态、只读只查、同步双击/查询重试互锁、后续拒绝保留unknown、8KiB正文/16KiB回复及UTF-8边界均回归通过。固定三个collection路径；controller从原正文对应UUID构造target，不能沿用路径第4段猜测目标。客户端没有credentials/任意URL/path/headers注入；仅内存，没有跨会话导入或自动重试。
69页面/API代码0.18.36/schema0020不变，无后台/schema改动。公共样例只读/OIDC及所有提交默认关闭，未配置实际变量/秘密/身份/授权，无真实浏览器/管理员/提供方/API在线探针/内网安装，不重试已被拒绝浏览器访问。内网未安装，SSO/人员/Windows无Docker/系统架构待定；Render工作区/后台部署版本未核验，原SoftwareLifeCycle_12全文未取得。
代码main及此文档后的最新精确head CI/provider须另核对，不能复用feature Preview或旧pending。Actions deploy.yml独立门控目前skipped，不能把提供方自动构建成功当作Actions部署已启用。后续最新证据覆盖历史pending。
Mac部分快照/GitHub连接服务发布，本地Node测试语法及进度--check通过，全套测试为Actions，没有另外启动独立云端Codex任务。HANDOFF入口明确生成/回读，全部历史保留。
36/44=82%；七模块100/100演示/100演示/100/89/60/17，七计划100/100/20/33/40/20/0，增量全部0。14业务/2自身会话/6管理员/离线操作分计；八类代理/控制器、五类UI，尚有九类UI及六类代理，不称14类真实提交验收完成。
下一包把Delivery Package/Distribution/Production Authorization既有准备接入双语确认发送、原审计查询、明确原请求重试和精确结果，采用独立distributionSubmissionConfigured及唯一当前USER只读投影，未知原请求跨命令/上下文/能力刷新不被覆盖。之后实现其余6业务通道及界面（Test Release/Deployment/Changeover、Impact/Acceptance/Resource），真实身份与内网验收、跨会话导入恢复、追加更正撤销、无Docker离线安装及运营迁移，VIN最后。
契约docs/distribution-command-submission.md。


## 2026-10-09 交付、分发及生产授权双语提交界面（Codex）
起点 main 22ede3fa59794a35e4766ec8d655d10c18919720；精确 CI37864590056 后端、前端、acceptance 均成功，Cloudflare生产 build6faf172b-0f53-4cd6-81a6-962670a04462/version2ab583a4-b024-4c11-be83-ca73e4e53607 成功，Actions独立deploy跳过，开放PR0。
本轮接入Delivery Package/Distribution/Production Authorization双语确认发送、查询原审计、原请求明确重试及精确回执。三组独立默认关闭门禁通过唯一当前USER会话投影六个布尔值；凭据不传客户端。未知原请求跨表单/命令/上下文/能力刷新保持冻结，查询不重发业务写入，显式重试保持原ID和原字节，同步发送/查询/复制互锁。
结果保留原READY交付精确修订及冻结artifact集合、原READY分发及接收方、原DRAFT生产授权的customer/project/site/line/purpose、finite/null批次范围及原限制。精确业务详情/原审计链接独立新标签读取，交付附原snapshot链接；不推断发送文件、签收、量产批准、当前状态或replayed。
本地完整前端922通过/0fail/0skip（原895新增24组件事件/双语结果、2服务器门禁及1本地化覆盖，共27）；TypeScript --noEmit及进度--check通过。新增门禁测试先验证旧代码缺能力投影失败；实现后修正初次新UI测试使用同一target而未触发context变更的测试数据，未放宽断言。本地Next/OpenNext Cloudflare Worker构建及中英文禁用认证SSR成功；两条distribution路由GET405/POST503、private/no-store。保留既有autoprefixer mixed support警告，未修改无关CSS。本包精确head Actions/provider结果另记录；不复用旧main或Preview。
69页面/API代码0.18.36/schema0020不变；没有后台或迁移修改。八类代理/控制器及八类双语UI完成，剩余六类代理/UI（Test Release/Deployment/Changeover、Impact/Acceptance/Resource）；全部14类真实身份验收仍未完成。
仅页面内存，卸载/刷新/跨会话恢复导入待实现；beforeunload不保证应用内其他路由提醒。公共样例只读，OIDC及全部提交默认关闭，未配置实际身份/授权/秘密，真实浏览器/管理员/提供方/内网验收未进行。内网未安装，SSO/人员/Windows无Docker/系统架构待定。Render后台部署/版本未核验。原SoftwareLifeCycle_17全文检索服务报错，本轮按仓库最新交接继续；不是已经读取其全文。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，验收增量全部0；双语提交UI由5/14增至8/14。执行器为云端Linux完整checkout，Codex直接编写并运行本地前端测试；完整后端/真实PG回归由Actions验收。Git CLI没有推送凭据，通过已连接GitHub发布。
下一包实现Test Release/Deployment/Changeover独立默认关闭提交通道、原审计恢复、严格精确回执和冻结控制器，然后接入双语UI；再完成Impact/Acceptance/Resource、真实身份及内网验收、跨会话导入恢复、追加更正撤销、无Docker离线安装与运营迁移，VIN最后。
契约docs/distribution-command-submission.md。


## PR#33 验收 — 2026-10-09（Codex）
PR https://github.com/Wang106/SoftwareLifeCycle/pull/33 已合并；代码main 061c6ce8e0f8ddbdea2dd0d3205038fc4f8fdd17，精确feature e3aa442d9f2da5ff62a7fa713c0b72de41261f03，起点main22ede3fa59794a35e4766ec8d655d10c18919720。
feature完整CI37882061097三任务成功：2071后端（344.53秒，11417既有warnings），172 PostgreSQL-module cases/no skips；922前端/0fail/0skip（原895新增27）。0020单迁移头/SQL/隔离PG往返、进度--check、类型检查、Next/OpenNext Worker构建、中英文禁用认证SSR成功；两条distribution路由GET405/POST503、private/no-store。后端113663709326、前端113663709375、acceptance113665279770成功。Cloudflare feature Preview builde9ec67f1-6af4-4383-bba7-8e89eddbdcb0成功；不是main生产部署证据。首轮新增门禁测试证明旧代码缺能力投影，开发中修正缺失能力声明和未实际改变target的测试数据后通过，本PR云端首次完整CI即成功。
三类双语确认发送、原审计查询、原请求明确重试、精确回执已接入。六个布尔能力通过三组独立默认关闭门控和唯一当前USER投影，不传凭据；unknown跨命令/上下文/能力刷新冻结，只有confirmed或首次明确rejected允许新UUID。精确原READY/DRAFT、交付修订/冻结artifact集合、分发接收方及生产授权finite/null范围原文保留，不推断current/replayed/发送文件/签收/量产批准。八类代理及八类UI完成，六类仍准备/复制；仅内存，跨卸载/刷新/会话导入待完成。
本轮云端Linux完整checkout直接用Codex编写；本地922前端、TypeScript、进度、Next/Worker构建及禁用认证SSR成功，最终新组件24项单独通过。Git CLI无推送凭据，使用已连接GitHub发布。SoftwareLifeCycle_17全文检索两次均服务报错，按最新仓库交接承接；不称已读取全文。
69页面/API代码0.18.36/schema0020不变，没有后台/schema改动。公共样例只读，OIDC及全部提交默认关闭；实际身份/授权/秘密未配置，真实浏览器/管理员/提供方/内网验收未进行。内网未安装、SSO/人员/Windows无Docker/系统架构待定，Render后台部署/版本未核验。
本记录后的最新main精确head CI及Cloudflare生产另核对，不能用旧main或Preview代替；GitHub Actions独立deploy仍门控跳过。36/44=82%，七模块100/100演示/100演示/100/89/60/17，七计划100/100/20/33/40/20/0；验收增量0，提交UI覆盖5/14→8/14。
下一包实现Test Release/Deployment/Changeover独立默认关闭提交与原审计恢复、严格原回执和冻结控制器，随后双语UI；再完成Impact/Acceptance/Resource、真实身份与内网验收、跨会话导入恢复、追加更正撤销、无Docker离线安装与运营迁移，VIN最后。


## 2026-10-09 Test Release、Deployment、Changeover 提交基础（Codex）
起点main80772cd6cc2ac36b76f53e3da517ac3f2a7db8bb；完整CI37882684715三任务成功（2071后端/172 PostgreSQL-module cases/no skips，922前端），Cloudflare生产build3d981754-9799-4dfb-a9e8-758d3a67a896/versiond6a8566f-1fe9-4090-82c4-8b5ebb89768b成功，Actions独立deploy跳过，开放PR0。
新增独立默认关闭production-command提交/原审计恢复代理、Test Release/Deployment/Changeover严格正文与目标绑定、精确原回执和ProductionSubmission冻结控制器。Test Release原审计没有request，按原字段/声明/原因校验，HTTP201/200均需原审计；不推断replayed。Deployment原PENDING只表示期望，Changeover原COMPLETED只表示记录，原from/to、声明note及审计occurred_at保留，UTC六位微秒不丢失；不推断测试通过、物理刷写或actual报告。查询只GET原审计，重试保持原ID及原字节，unknown后拒绝仍unknown。
十一类代理/控制器已有（8→11/14，79%），双语UI仍8/14；三类页面按钮下一包接入，其余Impact/Acceptance/Resource代理尚待实现。69页面/API代码0.18.36/schema0020不变，没有后台/schema修改。
新增26传输/解析/原审计/精确回执/时间/冻结互锁及17实际RSA OIDC代理行为回归，43项定向通过；本地完整前端965通过/0fail/0skip、类型检查、Worker构建及中英文禁用认证SSR通过；两条新路由GET405/POST503、private/no-store。首轮旧session测试加载器白名单缺少两个新增模块，加入明确模块后全套通过，业务断言未放宽；最终规范UTC时间范围边界追加校验后，54项定向回归、965项完整前端及构建/禁用认证SSR再次通过。精确head Actions/provider证据另记录。迁移/后端回归由本包Actions核对，不能复用旧main。根目录误调用tsc未运行项目检查，随后在frontend正确运行；不修改依赖锁文件。本地完整checkout的Codex直接编写，Git CLI无推送凭据，使用GitHub连接发布。
公共样例只读，OIDC及全部提交默认关闭；不配置实际身份/权限/秘密，真实浏览器/管理员/提供方/内网验收未进行。内网未安装，SSO/人员/Windows无Docker/CPU架构待定，Render后台版本/部署未核验。仅内存，不支持跨卸载/刷新/会话恢复导入。
36/44=82%；七模块100/100演示/100演示/100/89/60/17，七计划100/100/20/33/40/20/0，验收增量0，代理/控制器覆盖+3。下一包将三类既有准备接入双语确认发送、原审计查询、原请求重试及精确结果，独立productionSubmissionConfigured和唯一当前USER只读投影，不以其他门控覆盖未知原请求；再做Impact/Acceptance/Resource、真实身份与内网验收、跨会话导入恢复、更正撤销、无Docker离线安装与运营迁移，VIN最后。契约docs/production-command-submission.md。


## PR#34 验收 — 2026-10-09（Codex）
PR https://github.com/Wang106/SoftwareLifeCycle/pull/34 已合并；代码main96ed9baf2f668254bb4fba44b9c39fcd08cd4b73，精确feature5a76488b1424a1f9838b901db1a26f10b7a29dfc，起点main80772cd6cc2ac36b76f53e3da517ac3f2a7db8bb。
完整feature CI37886860882三任务成功：2071后端（536.02秒、11417既有warnings），172 PostgreSQL-module cases/no skips；965前端/0fail/0skip（原922新增26传输及17代理回归）。后端113678703521、前端113678698538、acceptance113681136900全部成功。0020单迁移头、SQL、隔离真实PG往返、进度账本、类型检查、Next/OpenNext Worker及双语禁用认证SSR通过；production两条路由GET405/POST503、private/no-store。Cloudflare feature Preview build9ca59067-5b1b-4d20-b5e2-abfb81c35f89成功，不是main生产部署证据。本记录后的最新main精确CI和生产构建须独立核对；Actions独立deploy仍门控跳过，不能声称已启用。
Test Release/Deployment/Changeover独立默认关闭的提交、原审计恢复、严格目标/正文绑定、精确原回执及冻结控制器完成。Test Release原审计无request，按实际原字段/声明/原因校验；HTTP200/201均需审计，不推断replayed。Deployment原PENDING仅期望，Changeover原COMPLETED仅记录，原from/to和audit.occurred_at的六位UTC微秒保留，不推断测试通过、物理刷写或actual报告。未知请求查询只GET，明确重试原字节/ID不变，同步互锁，后续拒绝不抹除unknown。
十一类代理/控制器（11/14，79%）、八类双语UI（8/14）；本包三类UI尚未接入，Impact/Acceptance/Resource代理和UI尚待实现。本地965前端、54定向、TypeScript、进度--check、Worker构建及双语禁用SSR通过；旧session测试加载器加入两个明确新增模块后通过，未放宽业务断言。代码69页面/API0.18.36/schema0020不变，没有后端或schema变更。
执行模式为云端Linux完整checkout，Codex直接编写，本地前端及Actions完整后端/真实PG验收；Git CLI无推送凭据，使用GitHub连接发布。公共样例只读，OIDC及所有提交默认关闭；无实际身份/权限/秘密配置，真实浏览器/管理员/提供方/内网验收未进行，不重试被拒绝浏览器访问。内网未安装，SSO/人员/Windows无Docker/CPU架构待定，Render后台部署版本未核验。仅内存，跨卸载/刷新/会话恢复导入待完成。SoftwareLifeCycle_17全文检索此前两次服务报错，依据仓库交接承接，不称已读全文。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0；验收增量全部0，代理覆盖8→11/14。下一包接三类双语确认发送/原审计查询/明确原请求重试/精确结果，再做Impact/Acceptance/Resource、真实身份和内网验收、跨会话恢复、更正撤销、无Docker离线安装及运营迁移，VIN最后。契约docs/production-command-submission.md。


## 2026-10-09 Test Release、Deployment、Changeover 双语提交界面（Codex）
起点mainc96199aa3e09197a02d5eb7d4705b68d4866e443；精确CI37887811663三任务成功（2071后端/172 PostgreSQL-module cases/no skips、965前端），Cloudflare生产buildabac9292-38ab-43fe-a7de-2b7a31c382f8/version3cd22f99-fbf7-4e90-a5f5-4a610794699b成功，Actions两次独立deploy跳过，开放PR0。
三类现有准备已接入双语确认发送、原审计查询、原请求明确重试和精确结果。独立productionSubmissionConfigured和唯一当前USER会话投影两个布尔能力；四组门控只复核一次会话，凭据不传客户端。只读明确false才能发送，只读仍可查原审计。未知原请求跨表单/命令/上下文/能力刷新保持原ID和正文冻结，不借其他门控发送；复制/发送/查询同步互锁，无自动重试。
结果保留原DRAFT测试目的、声明原因及冻结Snapshot；原PENDING预期Release/Snapshot和生产线；原COMPLETED更换from/to、note/null及原六位UTC微秒。独立详情/原审计链接新标签读取；不推断测试通过、激活、实际安装、物理刷写或actual报告。十一类代理及十一类UI（8→11/14，79%），其余Impact/Acceptance/Resource仍准备/复制，下一包实现其独立默认关闭提交基础，再接双语UI。
本地完整前端993通过/0fail/0skip（原965新增25组件事件/双语结果、2页面门控和1新结果本地化，共28）；TypeScript --noEmit、Worker配置及进度--check通过。新增页面测试先证明旧代码缺production能力投影；初次定向测试夹具误把reason textarea当作命名input，修正真实textarea事件后完整通过，未放宽业务断言。本地Next/OpenNext Worker构建及中英文禁用认证SSR成功；production两条路由GET405/POST503、private/no-store。本包精确head Actions/provider待核对，不复用旧main。
69页面/API代码0.18.36/schema0020不变，没有后台/schema修改。仅页面内存，卸载/刷新/跨会话导入恢复未实现；beforeunload不保证应用内路由提醒。公共样例只读，OIDC及全部提交默认关闭；未配置实际身份/授权/秘密，真实浏览器/管理员/提供方/内网验收未进行，不重试被拒绝浏览器访问。内网未安装，SSO/人员/Windows无Docker/CPU架构待定，Render后台部署版本未核验。原SoftwareLifeCycle_17全文此前两次检索服务报错，本轮按仓库最新交接承接。
执行模式云端Linux完整checkout，Codex直接编写，本地前端及Actions完整后台/真实PG核验；Git CLI无推送凭据，通过GitHub连接发布。36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0；验收增量全部0，双语UI覆盖+3。之后Impact/Acceptance/Resource、真实身份和内网验收、跨会话恢复、更正撤销、无Docker离线安装及运营迁移，VIN最后。契约docs/production-command-submission.md。


## PR#35 验收 — 2026-10-09（Codex）
PR https://github.com/Wang106/SoftwareLifeCycle/pull/35 已合并；代码main49a87c996427dff5b5a7a8bdde5815d767d4a55f，精确feature0fa20b9d14ad4c080d7baf371ea0b8034c9d44cd，起点mainc96199aa3e09197a02d5eb7d4705b68d4866e443。
完整feature CI37894297853三任务成功：2071后端（314.79秒、11417既有warnings）、172 PostgreSQL-module cases/no skips；993前端/0fail/0skip（原965新增25组件事件/双语结果、2页面门控、1新结果本地化=28）。后端113701992909、前端113701992645、acceptance113703679919全部成功。0020单迁移头、SQL、隔离真实PG往返、进度账本、TypeScript、Next/OpenNext Worker、中英文禁用认证SSR通过；production两条路由GET405/POST503，private/no-store。Cloudflare feature Preview build48ade30b-a53c-4391-8dc3-099f12e7a61f成功；不是main生产部署证据。本记录后的最新main精确CI/provider另核对，不能复用旧main或Preview。Actions独立deploy默认门控跳过，不能声称已启用。
Test Release/Deployment/Changeover双语确认发送、原审计查询、原请求明确重试和精确结果已接入。四组独立默认关闭门控只复核一次当前USER会话，production只投影两个布尔能力；凭据不传客户端，只读可查询。unknown跨命令/上下文/能力刷新冻结，不借其他门控重写，复制/发送/查询同步互锁。原DRAFT测试目的/声明/原因/冻结Snapshot、原PENDING期望软件/产线、原COMPLETED来源/目标/原note-null和六位UTC微秒完整保留；独立详情与原审计链接新标签读取，不推断测试通过、激活、安装、物理刷写或actual报告。十一类代理/控制器及十一类UI（8→11/14，79%），剩余Impact/Acceptance/Resource。
本地993前端、TypeScript、Worker配置/构建、双语禁用认证SSR及进度--check通过。新增门控测试先验证旧代码缺能力投影失败；初次组件夹具误把textarea当命名input，改用真实textarea事件后完整通过，未放宽断言。本PR首次云端完整CI成功。执行为云端Linux完整checkout的Codex直接编写；Git CLI无推送凭据，通过GitHub连接发布，没有另启独立云端Codex任务。
69页面/API0.18.36/schema0020不变，无后台/schema改动。公共样例只读，OIDC及全部提交默认关闭；无实际身份/权限/秘密配置，真实浏览器/管理员/提供方/内网验收未进行，不重试被拒绝浏览器访问。内网未安装，SSO/人员/Windows无Docker/CPU架构待定，Render后台版本/部署未核验。仅页面内存，刷新/卸载/跨会话导入恢复待完成，beforeunload不保证应用内路由提醒。SoftwareLifeCycle_17全文此前两次检索服务报错，依据仓库最新交接承接。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，验收增量全部0，双语UI+3。下一包实现Impact/Acceptance/Resource独立默认关闭提交与原审计恢复基础，再接双语UI；之后真实身份/内网验收、跨会话恢复、更正撤销、无Docker离线安装及运营迁移，VIN最后。契约docs/production-command-submission.md。

## 当前开发包 — 2026-10-10 Acceptance 更正双语界面（Codex）
起点main 59581f3efd220c8de54dc8c94d3b8b46e6c4da52（PR46）；无开放PR，清洁完整checkout后创建codex/acceptance-correction-ui。本会话由Codex在Work环境直接修改仓库，没有启动独立本地Plus CLI/API worker，不使用付费API或上传登录缓存。
起点完整CI38026495717三个job均成功，Cloudflare生产build53b5ee1f-576d-4ae3-96ab-8d9da93aeaae/version3584169b-9d49-4fd6-8d77-9a3e30260ec0成功；Actions deploy/wake跳过。当前包精确CI/合并/提供方另核对，不复用起点证据。
有效Acceptance历史行新增绑定SCR/criterion/前驱/DVP/原动作的替代撤销入口；独立双语更正准备、精确确认、冻结原字节发送/明确重试/只读原审计查询及原结果链接完成。普通ASSIGN独立，原行及审计不改；unknown不因后来拒绝丢失，过期上下文/能力闭包及复制发送查询互锁。按更正上下文加载panel，同panel查询刷新不改已尝试请求；卸载/跨路由/刷新仍会丢内存，导出导入待下一包。
18项新行为回归及类型/进度--check通过。完整前端1206项/0fail/0skip通过；Next/OpenNext构建通过；双语禁用认证SSR/真实Next路由私有405/503检查通过；远端exact-head CI在验收记录补充。首次完整回归发现新增静态导入与旧页面测试模块桩不兼容、条件表达式本地化包装遗漏；改为按更正上下文动态加载并补齐Localized容器，145项相关回归通过，未修改已有测试/依赖/迁移/CI/调度配置。
契约docs/acceptance-correction-ui.md；69页面/API0.18.40/schema0022不变。14业务/2自身会话/6管理员/离线操作分计。36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，验收增量0。公共样例只读/OIDC及提交门控关闭，无实际身份/授权/秘密；Render live API/schema未核验，内网未部署，真实提供方/浏览器/管理员验收未完成。
下一包手动同站点导出与只读原审计恢复导入（已启用scope）；随后Impact撤销/评审下游/离线运营仍为待划定禁用scope，VIN最后。

## 当前开发包 — 2026-10-10 Acceptance 更正手动恢复（Codex）
在PR47已提交的双语确认/原结果界面基础上准备第二个已启用scope：同站点手动导出与只读原审计恢复导入。公共样例仍只读，未启动独立Plus本地CLI/API worker，无付费API调用或登录缓存上传。PR47已在精确head9e2bef610be52d0608ecb5fbf52bbbe41f069d52/CI38027348828三个job成功后受保护合并到main88b578f8dbf20711a0078c7760f39a5fc2173b7c；2180后端（324.97秒）、203 PostgreSQL-module cases/no skips、1206前端，Cloudflare feature Preview build5071f8f0-9df6-4a33-9921-f9bf1ee72981成功。新包基于此合并main，本包精确head CI/provider另核对，不以Preview代替main生产部署。
规范slc-acceptance-correction-recovery/version1文本绑定origin/原body/原actor声明/精确前驱/请求ID。严格compact/pretty字段顺序与字节、格式/版本/重复键/Unicode/长度/同站点/凭据隔离校验；导入零网络，unknown只读facade无send方法，界面隐藏发送/重试，只显式查询原审计。原controller不可被导入替换，过期导入/复制/发送/查询互锁，后来拒绝不丢未知状态。明确导出提供剪贴板和可手动复制文本，无自动查询/重试/存储；模拟新组件恢复保留原字节及ID。
13项新格式/控制器/UI/双语回归，既有18更正UI回归未改；完整前端1219/0fail/0skip、类型、Worker配置、Next/OpenNext生产构建、双语禁用认证SSR/真实Next路由私有405/503、进度--check和diff检查通过。无后端/schema/迁移/依赖/调度/CI或既有测试改动。完整后端/真实PG/本包精确CI及main生产提供方另核验；本地未重跑后端，不复用旧成功称本包验收。
契约docs/acceptance-correction-recovery.md覆盖上一包memory-only限制。69页面/API0.18.40/schema0022不变，14业务/2自身会话/6管理员/离线操作分计。实际跨会话/提供方/浏览器/管理员验收仍待，内网未部署/OIDC未定，无真实身份/授权/秘密配置。Render live API/schema未核验，Actions deploy独立门控。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，业务验收增量0，不因模拟UI回归提升里程碑。两项启用UI任务实现，待本包受保护合并；后续Impact撤销/提交、评审下游和离线运营scope仍禁用，需具体划定范围，VIN最后。

## 2026-10-11 Impact SUPERSEDE 双语界面与手动恢复 B（Codex）
用户10:19“继续”承接下一包B；仅实现既有SUPERSEDE的双语确认/原结果/手动导出与只读原审计恢复导入，不扩大到C撤销/数据库迁移或宽泛disabled队列。Codex在Work直接开发，未启动用户本地Plus CLI或付费API worker，无登录缓存上传。
基线main0c622c54c4db9f7b1581752b44713192370759a0（PR50），无开放PR/工作区清洁。核验精确main CI38058331160成功：2180后端446.87秒/203 PostgreSQL-module cases无skip、1277前端；backend114231271610/frontend114231271424/acceptance114232825373。生产Cloudflare builda21a67f1-f6bd-4985-a01d-aa4604b48fb1/check114231558199/version49343597-3549-4dd4-a709-abb9f4e5f677成功；Actions deploy/wake跳过。本包精确head/main CI及生产须独立核验，最终证据记录本包PR描述，不复用基线成功。
独立/按上下文惰性加载工作台、明确完整前驱入口与确认、默认中文/English、原字节发送/明确重试/查询互锁、原回执及精确原审计/冻结快照链接。普通ASSESS与Acceptance更正隔离，历史入口不是当前效力或权限证明，API重验当前前驱/FROZEN上下文。slc-impact-correction-recovery/version1绑定精确站点/原body/前驱/声明/ID，32768字节限额且严格compact/pretty原语法；导入零网络、无send/retry方法，只明确查询原审计。unknown保留、过期闭包/复制/发送/查询互锁、手动复制失败有可选原文本，无自动存储/查询/重试。
新增36协议/行为/SSR/集成回归；相关81项及完整1315前端/0fail/0skip、类型、Worker配置、进度/diff检查通过；最终Next/OpenNext及实际禁用路由/双语SSR检查通过，auth:check新增实际Impact更正页面中英双语SSR200/no-store/独立禁用表单与只读导入验证。既有测试/断言未改；首次新增测试桩缺少server-only替身、语言提供方按钮误判及新增集成fixture的Issue UUID引用已修正。契约docs/impact-correction-ui-recovery.md。本地不重跑后端，完整后端/真实PG以本包精确云端CI另验收。
69页面/API0.18.40/schema0022、14业务/2自身会话/6管理员/离线操作分计不变，无后端/迁移/依赖/CI/调度/真实身份配置变化。36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，验收增量0。公共样例只读/OIDC/真实提交关闭，Render live API/schema未核验；实际浏览器/提供方/跨会话/内网验收未做，不绕过之前拒绝访问。内网未安装，SSO/人员/OS/CPU/Windows无Docker未定；SoftwareLifeCycle_20原文未取得。
基线PR49 main的SQLite UUID读浮点故障与成功重跑已记录PR50（1failed2179passed→2180passed/203PG无skip），未修复，不因本包前端成功隐藏。下一包先审查C撤销终端语义/模型/迁移，不把旧独立判断复活或NOT_AFFECTED当撤销；随后评审/下游政策、真实身份/内网及离线运营，VIN最后。宽泛自动队列/API调度保持禁用。

## 2026-10-11 Plus 自动开发启动前检查（Codex）
基线main ebfac27a2086ec99245de02294e98f8b0ab79193（PR51），开放PR为0，精确main CI38105904092 success；Actions deploy/continuation跳过。本包仅完善Plus本地启动/恢复，不启动付费API或实际用户CLI，不扩大disabled业务范围。
新增 --check 只读工具/Node22/origin/gh目标仓库写入权限/开放PR检查；正常启动及恢复先检查。外部检查15秒超时，不输出原始错误或凭据；本地改动仅提醒、保留，不fetch/stash/reset。检查失败退出2，不调用模型；不声称验证Plus登录/额度/Git推送/沙箱。指令更新为跳过已合并PR47/48的Acceptance任务，启用队列完成即停止。
本地46项调度/启动器标准库回归通过（新增8项），进度 --check、prompt预览和diff检查通过；实际 --check 检出codex/gh缺失及Node版本不符并退出2，未启动模型。本包完整远端精确head CI、受保护合并及main/provider证据另核验并记录PR描述；不以基线成功代替。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，增量0。公共样例只读，OIDC/真实提交关闭，内网未部署；Render live API/schema、真实浏览器及用户本机Plus/gh/跨会话验收未完成。下一步用户机器 --check 后启动或恢复；启用任务代码已完成，后续Impact撤销模型/迁移须单独划定，API调度关闭。

## 2026-10-11 Plus 独立任务清单与下一审查包（Codex）
基线main cb95a53f1aa2b630c817843f74dea67312bcfcd6（PR52），精确feature4a5312024995333488966fc0f4e0a6965c0011bb/CI38106971532三个必需job成功（46自动化、2180后端/203PG无skip、1315前端），已受保护合并；此后main CI38108763320/provider另核验，不复用feature或旧main证据。
当前Plus任务事实源改为docs/automation/plus-tasks.json，旧docs/automation/tasks.json仍是未启用API队列。重新核验PR47/48真实merged及合并SHA，记录Acceptance两项completed；新增pending Impact撤销模型/迁移方案审查，只改docs/impact-withdrawal-design-review.md及开发/交接文档，不实现后端/迁移/界面。审查需比较模型、上下文终端/统一消费者、锁/原审计/请求重放、旧库/降级与PG测试矩阵，给下一实现包精确范围，完成后停止。
启动器新增 --show-tasks，无工具/网络/模型查看清单；--check/启动/恢复先校验模式/证据/依赖/文档边界。52项标准库回归通过（新增6队列测试），任务/prompt预览、进度--check和diff检查通过。清单只是本地结构检查，真实远端合并/CI/较新HANDOFF须在会话内再核验，不把旧pending或模拟测试当完成。
仍由用户在自己机器启动；当前Work未安装codex/gh、未验收用户Plus登录/实际CLI/Git推送/沙箱/跨会话，不称无人值守自动开发已运行。无API调用、凭据上传、账户/真实门控变更；API调度关闭。本包精确head完整CI/合并/main/provider证据另记PR描述。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，增量0。公共样例只读、OIDC/提交关闭、内网未部署；Render live API/schema及真实浏览器/提供方验收待做。用户下一步 --show-tasks/--check 后启动或恢复，先复核当前证据，再执行文档审查。

## 2026-10-11 Impact 撤销设计审查（Codex / ChatGPT Work 云端）

当前包仅 impact-withdrawal-design-review，三份文档；PR[#54](https://github.com/Wang106/SoftwareLifeCycle/pull/54)，首份文档提交44d78d97246c2b5e5903c5a4c03c1a51c2e1bcd3，最终精确head/CI/合并证据见PR；基线远端 main d13c42af3b6f95a3d4f31b5c060db3ac967b6316，开始无开放PR。已核对真实合并PR47/48及PR50/51，较新代码覆盖旧pending，不重复Acceptance或Impact SUPERSEDE。
设计见 [docs/impact-withdrawal-design-review.md](docs/impact-withdrawal-design-review.md)：比较扩展动作历史与独立撤销表；推荐增量动作历史、旧行不回填正文、统一上下文终端与锁内序号。WITHDRAW不等于NOT_AFFECTED，不复活旧独立根；显式新判断确认当前撤销，旧撤销重放只确认原操作。列出完整消费者、锁/原子审计/actor与全正文绑定、旧库无损及拒绝丢语义降级、真实PG/恢复/长历史有界矩阵和下一包精确路径。
本轮Codex直接在Work云端使用GitHub连接；未调用付费API、未启动用户本地常驻CLI、无登录缓存上传。历史本地CLI限制不代表云端连接不能开发。
API0.18.40/schema0022不变；没有后端/迁移/界面/测试/依赖/CI/队列或真实门控修改，Seed代码未变。新revision0023仅设计提案。公共样例只读、OIDC/真实提交关闭、内网未部署。
本地进度 --check、52项既有标准库回归及diff/三文件边界检查通过；未本地重跑后端/PG/Next/OpenNext。Render只读list_services返回未选择工作区，live API/schema/部署仍未核验，不自行选择。精确PR head完整CI、合并/main/provider状态分开记录：最终精确证据以本包PR描述为准，未核验和skipped不称成功。合并证据覆盖plus-tasks旧pending，队列不在允许路径内所以不修改。所有已授权任务完成后暂停当前自动任务；下一实现包impact-withdrawal-history-backend-read尚未授权，不自行扩大范围。
业务验收增量0：36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0。真实提供方/浏览器/管理员/内网验收仍未完成。

## 2026-10-11 Impact 撤销历史后台与只读展示（Codex / ChatGPT Work）

真实PG首轮完整CI38114318903（head634819cdbaa7dfb58e4faac43105ceb24ebc2216）检出长历史分页的逐行相关终端子查询超时：1 failed/2230 passed/no skips；前端1319/Next/OpenNext/禁用认证SSR与Cloudflare Preview成功。未合并、不调高10秒statement_timeout、不缩减11,024旧事件测试。已将终端标记计算移到分页之后，只查询当前页的去重快照上下文，结果仍带is_context_terminal；既有长历史测试与断言保持不变，修复精确head须重新完整CI。最终PR记录成功或阻塞及main/provider；失败证据不隐藏。

用户明确授权 `impact-withdrawal-history-backend-read`；从真实 main `1615ab72c0b11deea21674f2bfe8a91dde3c8197`（PR54 已合并审查）开始，无开放 PR。独立分支 `codex/impact-withdrawal-history-backend-read`，不直接推 main、不改保护或 force-push；本包 PR [#55](https://github.com/Wang106/SoftwareLifeCycle/pull/55)，实现提交 `4f387649e611be2aca1daaa180462a33e954a5e2`；首次完整 CI `38114147873` 启动，最终 head/完整 CI/合并与提供方证据记录于 PR，未核验不得称成功。
实现增量 `0023_impact_withdrawal_history`（前驱 `0022_acceptance_history`），API `0.18.41`。旧判断/原审计逐字段保留，旧 action/seq 为 NULL，仅读取时推导；新行必须显式 ASSESS/SUPERSEDE/WITHDRAW 和锁内上下文序号。WITHDRAW 无技术 decision/evidence，不复活旧独立根；新判断明确确认当前撤销 UUID，新 request_id。原撤销重放只返回原操作和独立当前观察，不再撤销后来判断。
新增 POST `/api/v1/issues/{issue_no}/impact-withdrawals`：当前 Issue/Release/FROZEN Snapshot/前驱检查、Issue FOR UPDATE、统一写者序号、同事务审计、actor/完整规范化请求指纹绑定；返回 201/200/409。既有 POST assessment 新增 after_withdrawal_id。共享上下文终端 SQL 覆盖当前证据、候选、兼容读取、完整历史分页；JUDGED/WITHDRAWN/UNASSESSED 与技术判断分离，history_count 与 assessment_count 分计。Issue/Impact/候选/历史双语只读展示保留原 UUID、原因和原审计链接，不增加撤销浏览器提交/恢复协议或真实门控。
同步真实消费者 `frontend/components/issue-collections.tsx` 和写接口契约清单（15 业务命令），API 版本；已有 3 个固定计数/head 测试仅更新精确常量，既有 PG 迁移测试改在旧 schema 写旧行，避免把新序号行伪称旧数据，原断言全部保留。Seed 与依赖/CI/调度/身份配置未改。
本地新增 31 撤销语义/正文与原审计回归、3 统一读取/快照隔离/只读 OIDC 门控、4 双语只读 SSR；新增 17 真实 PG cases（并发各写者/原审计原子回滚/旧库往返/拒绝语义丢失降级/数据库约束/10,000旧根+1,024旧链/EXPLAIN 与有界结果）。本地没有 PG，17 cases 跳过明确不算验收，必须由既有完整 CI 的 PostgreSQL16、no skips 报告证明；精确结果以 PR 检查点为准。
迁移 head 和 offline SQL、前端类型/Worker 配置与 Next/OpenNext 已运行；末次本地完整后端1615 passed/616 unavailable DB skips；完整前端初版1318 passed/0skip，另新增撤销后新判断原审计展示回归，当前精确CI前端总数另记PR；末次本地禁用认证SSR通过。最终结果以本包 PR 逐项记录。初次前端完整测试检出撤销组件标点未包裹 Localized，已修复组件并重跑，未削弱测试。首次本地后端全套运行遇到旧 14-command/0022 常量，已同步真实新接口/head 后单独验证，不隐瞒首次结果；真实 PG 的新测试尚待 CI。
Codex 在 ChatGPT Work 云端直接开发并使用已授权 GitHub 连接，不调用付费 API，不上传登录缓存，不依赖旧 checkout/本地常驻 CLI。公共样例只读，OIDC/真实业务提交关闭、内网未部署。Seed 代码未变，幂等性须以真实 CI 重复 Seed 证明。Cloudflare、Render、Actions 和 main CI 在合并后独立核验；skipped/unverified 不称上线成功。
业务验收增量 0：36/44=82%；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0。实现包验收不等于真实身份/浏览器/生产验收。下一待划定包为浏览器撤销受控协议、双语确认与手动原审计恢复；不自动扩大范围，已授权实现完成后暂停。


## 2026-10-13 Excel 总览文字检索（Codex / ChatGPT Work）

基线真实 main `41082521da876a384977d8b6dd095f6b7484771b`（PR62真实merged），开放PR为0。本轮独立核对主线CI38398333766三个必需job success，Cloudflare生产check115299850651/build1afa373c-4d4b-40d7-9858-c3962fd0ce5a success。PR62最终记录2262后端/228真实PG cases无skip、1365前端/Next/OpenNext；这些是基线证据，本包精确head另验。Actions deploy38399512846/continuation38399512936 skipped。

/demo/zfi 新增本站GET文字检索：版本、Excel编号、软件、客户、项目、发布UUID、审批编号；不区分大小写，多关键词全部匹配，原记录/链接/全家族统计不改。检索与三类筛选取交集；检索重置页码且保留筛选，筛选/翻页保留关键词，清除筛选移除关键词；空结果不补造其他客户。标签/说明中英双语，语义label与帮助关联，输入/按钮键盘焦点，窄屏换行。仅读取原单个固定家族API，不增加后端请求或扫描。

新增16项回归，旧实现13failed/3passed，新实现与既有总览/筛选/发布证据/全站本地化共169passed/0failed/0skipped。两处既有“无任何form”断言按实际新增GET检索语义改为仅一个固定本站GET search，追加禁止POST，原业务命令/operation拒绝检查及证据断言保持；未以删除测试掩盖写入。首次断言误假设React属性顺序，修正为属性无关检查后169通过。进度--check通过。本地Worker配置检查因wrangler缺失未完成；Next/OpenNext/完整前端/后端/真实PG以本包精确现有CI验收，不借基线成功替代。

当前目录为空/GitHub DNS不可解析，独立复制上一轮可读前端快照并按固定main Git blob核验；仅发布本包白名单路径，以远端完整tree为base，保留缺失本地后台/其他文件。Codex直接在ChatGPT Work开发并通过已授权GitHub连接发布，不启动独立用户CLI/付费API、不上传登录缓存。Render已授权My Workspace复用，既有free服务srv-datm6o6k1f9s738r19gg，最新dep-db5sl1fgfhjc73eva640仍live在旧main9dba7e9；不改提供方配置/秘密/身份/后端/迁移/Seed/依赖/CI。API0.18.43/schema0024代码不变；本轮未重新证明live健康/样例数据。

36/44=82%；七模块100/100演示/100演示/100/89/60/17，七计划100/100/20/33/40/20/0，业务验收增量0。公共只读/OIDC/真实提交关闭；公司内网未部署。第四轮仍in_progress，既往403/1010不绕过或重试；桌面/手机/中英真实浏览器链路验收、当前API/schema现场验收待完成。下一步本包精确CI成功后受保护合并及独立main/provider核对，再按检索筛选→精确SSR/ASR→四级审批→当前Snapshot/Readiness/Decision/Passport核对。Excel固件/测试未提供不合成；不扩大Impact提交/身份/内网范围。最终head/PR/CI/合并/生产证据记录本包PR。


## 2026-10-13 双语只读演示状态页（Codex / ChatGPT Work）

基线真实main `e1ef6f8dd81e8c7aeab4da85fc8f30b2b1efd387`（PR63已合并），开放PR为0。上一包精确feature60d75d61/CI38405929302及独立main CI38407375978三必需job success已核对：2262后端、228真实PG-module cases/no skips、1381前端/Next/OpenNext/disabled-auth SSR。Cloudflare生产check115331189126/build9db8308a-1981-4f13-b308-b506b214063a/version0147762a-f02e-46d6-b610-9c89a4daa87d success，精确同main。Actions deployment38408642852/continuation38408644370 skipped。较新PR63最终证据覆盖旧文字检索pending；本包精确CI/main/provider必须另验。

新增 /demo/status：当前前端API配置下并发读取固定GET /health/ready、/api/v1/demo/zfi-import、/api/v1/demo/release-evidence；force-dynamic和原apiGet no-store，不自动轮询、安装Seed、重试或写入。不暴露API配置地址/秘密/原始异常，不查询私有身份。UTC读取时间、手动普通GET重新读取、API预期与观察版本/schema、Excel和独立合成家族分开呈现；两个总览有明确入口且禁用该入口预取。数据确认不等于真实浏览器验收、实际审批或正式发布。

严格检查API0.18.43/schema0024、20固定Excel UUID/原编号/类型/原审批/合成与导入标记，以及3独立证据UUID/原版本/类型。缺失、异常、不完整、契约不匹配分别显示；不因initialized或同版本字符串把外来/重复行计为完整，不用独立家族补Excel固件/测试。三次观察不是同一数据库事务，不保证后来状态；刷新重新观察，不产生正式治理结论。预期健康契约与后端声明、固定UUID与后端namespace有交叉校验。

新增36项检查器/页面/响应/双语回归；初始旧能力缺失31failed/0passed，补充严格健康类型、命名空间与长度回归后，本地与总览/筛选/检索/发布证据/全站本地化共206passed/0failed/0skipped。检查器strict TypeScript/JSON模块编译及进度--check通过。原既有测试/断言未修改；本地依赖仍只够React/TypeScript定向验证，完整前端/Next/OpenNext/后台/真实PG由本包精确现有CI验收，成功后才普通受保护合并。无后台/迁移/Seed/依赖/锁文件/CI/身份/门控/提供方配置修改，API代码0.18.43/schema0024不变。

Codex直接在ChatGPT Work编写，通过已授权GitHub连接发布；复用独立前端快照，12个白名单文件从远端完整tree构建，不覆盖缺失本地后台或旧差异。无付费模型API/用户登录缓存上传，不启动用户本机常驻CLI。上包Render已授权My Workspace核验既有free服务/旧main9dba7e9 live；当前网络GET及备用公开读取仍未取得live健康/家族数据，不能把新状态页代码称为现场验收。此前Cloudflare403/1010不绕过或重试。

36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，业务验收增量0。四轮账本第四轮仍in_progress。公共样例只读/OIDC/真实提交关闭，公司内网未部署，未提供Excel固件/测试不合成。下一步精确CI/受保护合并/独立main-provider，再由正常授权访问读取状态页和总览→SSR/ASR→四级审批→当前Snapshot/Readiness/Decision/Passport，在桌面/手机/中英文核对；若读取失败，保留未确认状态并按配置/网络/就绪逐项定位，不推断失败原因。更广身份/Impact提交/内网范围不扩大。最终head/PR/CI/合并/生产证据记录本包PR。


## 2026-10-14 标准发布供应商折叠布局与详情文件/审批（Codex / ChatGPT Work）

用户最新范围：只改页面显示，不改数据库。以真实main c8503fe116eaa8299e2b41f83ae4361d4eb16da4（PR64）为基线，独立分支 codex/standard-release-supplier-layout。PR64精确feature34f7acb1/CI38411209993、main CI38491157105及Cloudflare build8d33e64f-137f-41dd-abdd-29dfbba37ad0/version80de571e-cea0-4021-b566-4a0309799178 success已核对，覆盖旧pending；此包CI与provider另核验，最终完整SHA/PR/结果记录于本包PR。

标准发布改为竖向供应商方格，默认展开；内层每个原SSR UUID为独立标准软件方格，显示软件名称及SSR版本，默认收缩。供应商按原code分组，不合并同名供应商或同版本发布。展开列出该精确基线关联ASR，保留API created_at倒序（不按版本字符串重排）；标准软件名称和应用版本名称链接原UUID详情。保留GET筛选/父分页；每个软件10条ASR分页，显式翻页后只展开对应软件。分组仅覆盖当前筛选页面，不称全库供应商总数；每页最多100个SSR，关联读取并发上限4，不扫描所有子页。

标准详情直接显示现有Snapshot文件清单；应用详情复用原冻结清单并标为软件文件。两种详情直接显示原审批记录、提交者/时间/步骤/操作数量，并链接完整审批详情。文件分页固定snapshot UUID/编号和release UUID，审批精确target/release校验；独立分页保留文件快照和原页面参数。无文件/无审批与不可用分开显示，不伪造文件、下载链接、审批结果或正式发布。新增中英标签、原生details键盘折叠、窄屏换行及横向表格滚动。

新增8项目录/详情/分页/外来UUID/有界并发/实际双语回归；既有SSR collections测试仅增加新子组件mock，原断言保持。完整本地前端最终1428passed/0failed/0skipped（新增8项行为回归及2项全站覆盖检查）；首次测试中修正测试loader未指定ES2021导致Map展开为空及新增双语标签缺失，未删除或弱化断言。Next/OpenNext、Worker配置、disabled-auth SSR均通过。真实生产Next SSR接本地mock：中文/英文默认折叠、精确链接、样例顺序、内联文件/审批均通过，20次GET/0写入；不是实际浏览器点击或现场数据验收。当前容器缺少Playwright浏览器可执行文件，未完成桌面/手机真实点击验收；不绕过先前Cloudflare访问拒绝。

无backend/迁移/Seed/依赖/锁文件/CI/认证/提供方配置修改，API0.18.43/schema0024不变。原状态页读取超时测试单独保留，不混入本包。Render仅只读复核既有free服务旧main9dba7e9 live；现场health/ready和两个家族GET均超时，未取得响应不能推断0记录。未重启、升级或更改服务。

36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，业务验收增量0。公共只读/OIDC及真实提交关闭，内网未部署；第四轮仍in_progress。下一步本包精确CI通过后受保护合并，并核对独立main CI/provider；正常授权浏览器后检查桌面/手机/中英文供应商→软件→详情文件/审批，再继续状态页超时工作。最终发布证据以本包PR为准。


## 2026-10-17 演示状态页读取超时保护（Codex / ChatGPT Work）

从真实 main `774f03bbd6c7df73ed2c1bae55133222fcf33f4c`（PR65已合并）开始，开放PR为0，独立分支 `codex/demo-status-read-timeout`。基线完整CI38569904417三个必需job success；Cloudflare生产build2eca89ad-a010-4617-82eb-10cf5ad5a0d2/versiond04dda23-ea8b-4fe7-a35a-64ba0d26e4fa success。Actions deploy/wake skipped。本包精确head完整CI、合并main和生产检查必须另核验，最终结果记录本包PR，不能用基线代替。

承接PR65交接中的状态页超时工作：仅 /demo/status 的三个固定并发GET各设置10000ms读取上限，覆盖响应头与JSON正文；超时返回原有未确认/不可用状态并取消请求，已成功的其他观察保留。即使上游取消后未及时settle，Promise竞争也释放页面；迟到响应不能改成成功，迟到拒绝有处理。每次人工重新读取各请求一次，无自动重试/轮询，不把超时推断成空库、未导入、配置错误或数据库故障。共享apiGet仅新增可选参数，其他调用保留原有行为；不修改后端/数据库/迁移/Seed/身份/门控/依赖/CI或提供方配置。

新增8项行为回归：卡住的响应头、正文、迟到成功/拒绝、成功/HTTP/网络/JSON失败清理、无配置、无效时限、原调用兼容及真实状态页与共享读取组合。定向44项通过；完整前端1436 passed/0 failed/0 skipped；Worker配置、进度--check和diff检查通过。Next/OpenNext生产构建和disabled-auth SSR/实际禁用路由检查通过，精确云端最终结果见本包PR。未在本地重跑后台/真实PG；完整云端CI需独立成功后才受保护合并。模拟超时/SSR不算电脑或手机真实浏览器验收，也不证明线上API就绪。

业务验收仍36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0。公共只读/OIDC及真实提交关闭，内网未部署。第四轮仍in_progress：待正常授权浏览器完成桌面/手机/中英文供应商→软件→详情文件/审批和总览→当前发布证据链验收；不重试或绕过此前Cloudflare拒绝访问。Excel固件/测试未提供不合成，不扩大Impact撤销提交、身份或内网范围。本包成功后继续核对当前API/schema/样例读取；无法取得响应就保留未确认状态。
## 2026-10-17 Impact 撤销受控界面与手动恢复（Codex / ChatGPT Work）

真实起点main `774f03bbd6c7df73ed2c1bae55133222fcf33f4c`，分支 `codex/impact-withdrawal-browser-protocol`，开始无未提交用户修改。发布时main已前进到PR66 merge `e5601a1b73042414589113450cfd2660d3cd50f7`，本包重放后重新验收，保留状态页超时保护。Render只读复核确认服务live、PG18.6可读、无近7天错误/失败；现场health返回API0.18.43/schema0024，两个家族GET及Cloudflare状态页成功，20 Excel/3独立证据均确认。旧超时当前不可复现，未重启、升级、改配置或数据库。

新增独立默认关闭Impact撤销浏览器协议、两个Node代理路由、双语确认/结果、精确历史撤销入口、手动导出及同站点audit-only导入恢复。命令严格无decision/evidence；WITHDRAW不等于NOT_AFFECTED、不复活旧判断、不授予发布许可。独立环境开关、唯一当前token-bound USER、只读拒写/本人原审计可查、原字节重试、unknown保留、发送/查询互锁、原子审计全字段绑定和凭据隔离均落实；普通ASSESS和SUPERSEDE协议不接受撤销包。契约 `docs/impact-withdrawal-ui-recovery.md`。

新增17项回归并保留既有断言；重放PR66后前端完整1453 passed/0failed/0skipped，TypeScript、Next、OpenNext、Worker配置、disabled-auth真实生产SSR及进度--check通过。首次完整测试仅因依赖未安装导致65个文件加载失败，npm ci后重跑全绿；不把环境失败说成业务失败。首次SSR检查对同页普通Impact工作台使用了过宽的字段排除，撤销正文边界继续由严格解析、代理及组件回归证明。PR67首个完整CI39007229476在业务/PG前因Plus队列pending被直接改completed而违反52项固定恢复契约失败；已恢复旧队列记录，最新完成证据继续由AGENTS/HANDOFF覆盖，最终新head须重新完整验收。不能复用PR65/66成功。

无backend/迁移/Seed/依赖/锁文件/CI/调度/真实配置变更，API0.18.43/schema0024及14业务命令计数不变；公共只读/OIDC/真实提交关闭、内网未部署。36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0。判断关系里程碑仍因release-review历史替代和批准提供方多用户真实验收未完成；下一包先审查release-review历史替代精确范围，随后分发/授权撤销、生产更正、真实身份/内网与运营迁移，VIN最后。
