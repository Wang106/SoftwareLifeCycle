Warning: truncated output (original token count: 72108)
Total output lines: 1105

# DEVELOPMENT_STATUS

## 2026-10-21 SSR / ASR 四级审批进度总览（Codex / ChatGPT Work）

基线 main `e8ad3085f5d0284e111f85303211acd1d273259a`（PR#100 已合并），开放 PR 0；独立分支 `codex/ssr-asr-approval-progress`。按用户最新优先级把主要精力切回标准发布（SSR）与应用发布（ASR），本包只增强脱敏 Excel 演示家族的只读审批进度，不扩大生产更正、真实身份或内网范围。

`GET /api/v1/demo/zfi-import` 现在以固定数量批量查询返回两套真实记录路线及逐发布进度：SSR「电子工程师→电子经理→系统工程师→研发总监」，ASR「应用工程师→应用经理→系统工程师→项目经理」；每条记录包含已通过节点数、严格当前 `PENDING` 节点及关闭状态。步骤数量、顺序或角色与预期不符时返回未知，不补造当前节点。页面 `/demo/zfi` 双语展示路线、逐行进度、当前节点及退回/拒绝关闭结果，并继续链接原审批详情；保持单次只读 API、筛选/检索/分页、无 POST 表单及「审批通过不等于正式发布」边界。

无 migration、Seed、依赖、身份、CI、调度或提供方配置变更；API 0.18.50 / schema 0029 不变，Seed 幂等语义不变。本地定向前端 44 passed；当前容器未安装 pytest，因此后端与真实 PostgreSQL 由本包精确 PR CI 验证，未运行不称通过。业务验收仍 36/44=82%；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/40/0，页面可见进度不提高真实身份或业务验收比例。

### 精确验收证据

实现提交、PR、精确 head CI、受保护合并、main CI 与 provider 证据待本包发布后记录于 PR；三项必需 CI 未成功前不合并。

## 2026-10-21 生产换型与批次追加式更正写命令（DeepSeek，人工批准）

基线 main `80b00b62d2b2df2f20c405cb16a8895ece7df5fb`（PR#99 证据回填后），开放 PR 0，独立分支 `codex/production-changeover-batch-correction-write`。承接设计审查 `docs/production-changeover-batch-history-design-review.md`（PR#96）§9 的第二个小包，仅在人工批准后开放：新增两个更正写端点，带完整 `request_id`/`expected_revision`/`predecessor_id`/`correction_reason` 协议，不新增迁移（复用 0029 已建四表），不开放浏览器提交、真实身份或内网验收。

实现：`services/production.py` 新增 `correct_changeover`/`correct_batch`。锁定顺序 `Deployment → Changeover/Batch 行`；幂等 `request_id`（`EVT-CC-`/`EVT-BC-` 族）重放须核对 entity/action/actor/正文，不一致 409；`expected_revision` 须等于当前 head（根为 0），`predecessor_id` 须等于当前 head id（根显式 null），跳号/分叉/错前驱拒绝；`correction_reason` 1..2000；Changeover 可更正 `from_release_id`/`changed_at`/`note`，`to_release_id`/deployment/authorization 不可更正；Batch 可更正 `started_at`/`ended_at`/`changeover_id`/`note`，`release_id`/`snapshot_id`（软件归属）不可更正，且 `ended_at >= started_at`；缺失基线时以 `IMPORTED_CURRENT` 兜底捕获。追加 `ChangeoverCorrection`/`BatchCorrection` 账本行 + 原子审计一次提交，失败全回滚。

`api/production.py` 新增 `POST /deployments/{no}/changeovers/{changeover_no}/correction` 与 `POST /deployments/{no}/batches/{batch_no}/correction`，`PRODUCTION_OPERATOR` 授权 + `resolve_actor`；新增 `ChangeoverCorrectionCreate`/`BatchCorrectionCreate` Pydantic 模型（request_id 必填、expected_revision ge=0、reason 非空白）。`write_contracts.py` 注册两条路由（19→21）并更新 changeovers/batches 的 known_gap 措辞。`APP_VERSION` 0.18.49→0.18.50；`demo-family-identities.json` api_version 同步；两个 retirement 测试的 `len(WRITE_CONTRACTS)` 19→21。

版本 API 0.18.50 / schema 0029 不变（无新迁移）。公共只读、OIDC/真实提交关闭、内网未部署。七计划 group6「追加式更正和撤销」`production-correction`（部署/更换/批次更正规则）标记 complete，七计划 100/100/20/33/40/40/0；业务 36/44=82% 不变（后端规则不提升真实供应商验收）。

### 精确验收证据（PR#100）

实现提交 `a6054e1`；本地后端 SQLite 1699 passed / 654 skipped（新增 13 个更正写命令测试）。PR head CI / 合并 / main CI / 部署证据待合并后回填。

基线 main `787ee0928bf002e6727cd8c7a55b103d770a4838`，开放 PR 0，独立分支 `codex/production-changeover-batch-history-backend-read`。承接设计审查 `docs/production-changeover-batch-history-design-review.md`（PR#96）§9 的下一小包：只新增基线/更正表与只读投影，不开放任何更正写命令（correction-write 仍为后续需人工批准的独立包）。

实现：`models/production_history.py` 追加四张表——`ChangeoverBaseline`/`ChangeoverCorrection`（可更正 `from_release_id`/`changed_at`/`note`，`to_release_id` 绑定 expected 不可更正）与 `BatchBaseline`/`BatchCorrection`（可更正 `started_at`/`ended_at`/`changeover_id`/`note`，`release_id`/`snapshot_id` 软件归属不可更正），复刻 Deployment 账本的前驱/revision/唯一链/append-only 约束；`batch_corrections` 增 `ended_at >= started_at` 复合检查。迁移 `0029_changeover_batch_history`：建四表 + append-only trigger + 冻结 `software_changeovers`/`production_batches` 物理列写入 guard + 捕获 `LEGACY_CURRENT` 基线；downgrade 在存在更正或 `FIRST_RECORD` 基线时拒绝。投影 `effective_changeover`/`effective_batch`（+`_map`）以 head correction 覆盖不可变基线派生有效值，缺口 `NOT_RECORDED`，不回退基线伪装当前值。消费者统一：`_deployment_detail` 换型/批次时间与 note、`get_batch` 时间/换型/note、`production_catalog` 换型 `from_release` 与 `recorded_at` 改用有效投影；软件归属（release/snapshot/to）保持记录值。`seed.py` 的 `CO-0032`/`PB-1005-A` 改为 insert-only 并捕获 `IMPORTED_CURRENT` 基线（re-seed 不覆盖、不重复）。

版本：`required_db_revision` → `0029_changeover_batch_history`，`APP_VERSION` → `0.18.49`，demo identities 快照与 status 页断言同步改为从契约读取。无身份/秘密/CI/调度/部署权限改动；未开放浏览器提交、未开放更正写端点。公共只读、OIDC/真实提交关闭、内网未部署。

### 精确验收证据（PR#98）

实现提交 `a168936`，测试修复提交 `9ee00dc`（status 页版本断言改读契约）；PR#98 最终 head `9ee00dcb16a141ec1a0fbefc22c9f4f63267aa23`。PR head CI 四项检查全绿（Backend/PostgreSQL/migrations、Frontend tests + Cloudflare production build、Workers Builds、CI acceptance 均 success）。受保护 squash 合并 `92fda758fbebcf16e816bf28e4cced5303a9c998`（PR#98）。main CI 四项检查 success（CI acceptance / Backend+PostgreSQL+migrations / Frontend tests + Cloudflare production build success；deploy/wake skipped，SLC_DEPLOY_ENABLED 未启用）。Render `/health/ready` ready、version `0.18.49`、database_revision `0029_changeover_batch_history`（合并触发重部署）；Cloudflare `softwarelifecycle.whf969.com` HTTP 200（前端由 main CI build）。本地后端 SQLite 1686 passed / 654 skipped。

业务 36/44=82% 不变；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0（只读投影与冻结不提高真实供应商验收）。API 0.18.49 / 唯一 schema head `0029_changeover_batch_history`。下一候选 `production-changeover-batch-correction-write`（仅当人工批准：`POST .../changeovers/{no}/correction`、`POST .../batches/{no}/correction` 与可能的结束批次命令，带完整 request_id/expected_revision/predecessor_id/correction_reason 协议，默认关闭浏览器提交与真实身份/内网验收）。



基线 main `e80598eb2c1ff05f349c39deaf53b43e9076c52e`，开放 PR 0；独立分支 `codex/production-changeover-batch-history-design-review`。本包只做设计审查，不实现写入：产出 `docs/production-changeover-batch-history-design-review.md`，把 `production-trace-correction-design-review.md`（PR#85/86）中「Changeover/Batch 自身更正账本随后另包」的约定落成精确边界。

已核对真实模型与代码：`SoftwareChangeover` 与 `ProductionBatch` 均「只创建、无更正」——前者 `to_release_id` 由服务层强制等于 `deployment.expected_release_id`（`services/production.py:343`）、后者 `release_id/snapshot_id` 强制等于 expected（451–452 行）、`ended_at` 全代码库无写入路径（无结束批次命令）；两表均无 version/前驱/更正账本。锁图：`_create_changeover` 只锁 Deployment，`_create_batch` 锁 Deployment→lock_chain(AUTHORIZATION)。`seed.py:551–582` 对 `CO-0032`/`PB-1005-A` 即使已存在仍重新赋值（非 insert-only），下一实现须改为只创建缺失行。

设计要点：两张不可变基线表（changeover_baselines/batch_baselines，LEGACY_CURRENT/IMPORTED_CURRENT/FIRST_RECORD 三来源）+ 两张类型明确更正表（changeover_corrections/batch_corrections，`EVT-CC-*`/`EVT-BC-*` 族，复刻 DeploymentActualCorrection 的前驱/revision/唯一链/append-only 约束）；`batch_corrections` 增 `ended_at >= started_at` 复合约束；§6 定位全部真实消费者（production_catalog 的 changeover/batch 绑定、_deployment_detail、get_batch、dashboard 下游、seed）；§8 真实 PG 最低矩阵；§9 拆成两个后续小包——先 `production-changeover-batch-history-backend-read`（只读投影，不开放写命令），后 `production-changeover-batch-correction-write`（写命令，需人工批准）。

无后端/迁移/Seed/界面/测试/依赖/CI/调度/身份/提供方配置改动。API 0.18.48 / 唯一 schema head `0028_deployment_actual_guard` 不变。业务 36/44=82%；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0（设计审查不提高真实供应商验收比例）。公共只读、OIDC/真实提交关闭、内网未部署。

### 精确验收证据（PR#96）

PR#96 head `efa23c13c3e1cb3ebeb5b29e5c3239a3d2334a80`；PR head CI `39598100225` 四项检查全绿（Backend/PostgreSQL/migrations、Frontend tests + Cloudflare production build、Workers Builds、CI acceptance 均 success）。受保护 squash 合并 `e1f918455cef0ec3f23bca135911851dbe7f1484`（PR#96）。main CI `39599671086` 四项检查 success；Actions deployment `39600805752`/continuation `39600805867` skipped（SLC_DEPLOY_ENABLED 未启用）。Render `/health/ready` ready 0.18.48/`0028_deployment_actual_guard`（纯文档包未触发后端重部署，符合预期）；Cloudflare `softwarelifecycle.whf969.com` HTTP 200（前端由 main CI build，非本包业务变更）。

## 2026-10-21 受支持 Next.js / OpenNext 依赖升级（Codex / ChatGPT Work）

用户已明确授权独立依赖升级包。基线 main `15093d0ff9afc3732ebc24ac91905f55293f48af`；已有 PR#93 head `204a3555031e418382b519208ebaa9a6cc4f7a6c` 保留，先修复其与 main 的共同构建阻塞。独立分支 `codex/next-opennext-supported-upgrade`，未重复历史界面开发。

升级 Next.js 16.4.2、OpenNext 1.20.12、React/React DOM 19.3.1、根目录与前端 Wrangler 4.151.3，更新两份锁文件及 Next16 生成的 TypeScript 配置。针对新增间接依赖 `@node-minify/core` 仅限定 glob 10.5.0 安全补丁；不添加 unsupported-version 绕过。兼容/恢复说明见 `docs/next-opennext-upgrade.md`。API0.18.48/schema0028/Seed不变；CI、身份、写入门控、部署权限及调度配置不变。

本地完整前端1494 passed/0 fail/0 skip；Next16/OpenNext生产Worker构建、cf:check、auth:check双语生产SSR/禁用路由、两层npm audit（0漏洞）、进度和diff检查通过。本地未重跑后端/PG；精确 PR head CI、合并、main CI 与提供方证据在本包 PR 验证后记录；旧 PR#93 后端2331/前端1497成功不复用为升级后验收。业务36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，均不因依赖维护提升。

精确证据（PR#94）：head `c924002339d206a168ef76959d3163188550d043`，PR head CI `39586695734` 三 job 全绿，squash 合并 `ba86d996cfaebc5e0ae03bdbfff882f1285421ca`；main CI `39588067933` 三 job 成功（head `ba86d996`）；前端 build 成功（Next16.4.2/OpenNext1.20.12），Next.js 15.5.24 支持窗口阻塞解除。

## 2026-10-21 生产实际软件历史双语只读界面与长历史有界读取（Codex / ChatGPT Work）

基线真实 main `15093d0ff9afc3732ebc24ac91905f55293f48af`（PR#92），启动时开放 PR 0；独立分支 `codex/production-actual-history-ui-read`。本包只完成上一交接明确的 Actual 历史只读收口，不开放浏览器写入，不扩大到 Changeover/Batch 更正或身份/部署配置。

实现：Deployment 详情新增中英文“实际软件历史”面板，明确展示不可变基线、历史状态、更正总数、最新 50 条更正、业务发生时间与账本记录时间，并链接每条原子审计；原因、actor 与事件号保持原文，历史缺失时明确未知，不推断替代事实或生产许可。前端类型补齐 baseline/correction 的 `deployed_at`。后端 `_actual_history` 将 Release/Snapshot 元数据改为两次集合查询，消除随 50 条窗口增长的 N+1。真实 PostgreSQL 新增 10,000 条追加历史矩阵，断言只返回最新 50 条、降序、总数准确且 SQL 语句数 <=12；前端新增中英文、50 条截断、审计链接、时间区分、只读/未知态测试。

API 仍为 0.18.48，唯一 schema head 仍为 `0028_deployment_actual_guard`；无 migration、Seed、依赖、身份、CI、调度或部署权限改动，Seed 幂等语义不变。业务验收 36/44=82%；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0（只读与测试收口不提高真实供应商验收比例）。

检查点：PR#93 head `1034feb84b555281785874a765d409a792a1623b`，CI `39530257286`。Backend/PostgreSQL/migrations 成功：2331 passed、253 个 PostgreSQL 模块用例、无 skip，单一 Alembic head 0028 且 SQL/PG 往返通过；Frontend 测试 1497 passed / 0 failed，但随后 OpenNext 拒绝已超支持期的 Next.js 15.5.24，故该 job 与 CI acceptance 失败。未使用 `--dangerouslyUseUnsupportedNextVersion` 绕过；PR 保持开放且未合并，main 与 provider 未部署/未验收。本包发布被依赖升级决策阻塞（PR#94 已解除）。

### 恢复合并精确证据（DeepSeek，本轮）

PR#94 升级合并（main `ba86d996`）后，按交接将最新 main 以普通双父 merge 纳入 PR#93 分支，仅解决三处文档冲突（DEVELOPMENT_STATUS.md、HANDOFF.md、docs/development-plan-progress.json，业务代码文件无冲突），未 force-push。merge head `0fb6388854b39f7a0d38e223bb9ebafb92cf3b80`（父 `204a355` + `ba86d996`）。

新 head 三项 CI 全绿（run `39590349063`）：Backend/PostgreSQL/migrations success（2331 passed、253 PG module cases、无 skip）；Frontend tests 1497 passed / 0 failed，Next.js 16.4.2 build 成功（支持窗口阻塞解除）；CI acceptance success；Workers Builds success。受保护 squash 合并 `bbb0b9c5f1f0d7081658128175dd76570d60d2dd`（PR#93）。main CI `39591745406` 三 job 全绿；Cloudflare 生产 build `3dbb7e76-d472-4a55-acf1-67f766662c5f` success；Render `/health/ready` ready 0.18.48/0028；Cloudflare `softwarelifecycle.whf969.com` HTTP 200；Actions deploy/wake skipped（SLC_DEPLOY_ENABLED 未启用）。

尚未完成：批准身份提供方的真实多用户浏览器验收；Changeover/Batch 独立更正语义与账本。下一候选小包为 `production-changeover-batch-history-design-review`，先只审查真实模型/消费者/并发与迁移边界，不直接实现写入。

## 2026-10-21 生产实装旧写入保护与目录统一读取（DeepSeek，核验恢复并合并 PR#91）

基线 main `7bb4f58b5b88ff7a7e03d9573869c336aa69f598`，启动时开放 PR#91 `codex/production-actual-old-writer-guard-catalog-read`（前序运行遗留、CI 反复卡死/失败）。本轮未新建重复工作，核验并补齐该包到可合并状态，最终 squash 合并 `dd2438d9c8edd029b36a816f35865e63ddc62c23`（PR#91），main 推进到 `dd2438d9`。

本包内容：Alembic `0028_deployment_actual_guard` 冻结 Deployment 物理 actual 五元组（首次上报后拒绝非 no-op 覆盖/删除，`FIRST_REPORT` 须绑定同事务 immutable baseline 与一致 `ACTUAL_REPORTED` 原审计）；三个 production catalog 与 dashboard 的 `application_release_downstream_summary`/`application_release_downstream` 统一读取 effective 追加式投影（head correction > baseline > 冻结物理列），不再把物理基线误作当前值。API 0.18.48 / 唯一 schema head `0028_deployment_actual_guard`。

本轮补齐（前序未闭环）：(1) `dashboard.py` 两处仍读物理列，summary 改用 SQL effective 投影保持有界 count 契约（7 查询不变），downstream 改用 `effective_actual_map`；(2) `production.py::deployment_profile` 复用单次 `effective_actual` 并把 `observed()` 改为接收有效值；(3) 五个测试文件适配 guard/append-only——`test_actual_concurrency_postgres` 改用全新未报告 `DEP-A`/`DEP-B`（append-only trigger 禁止 reset 共享 fixture 的已报告行）、`test_manufacturing_views` seed 捕获 `IMPORTED_CURRENT` 基线、`test_release_downstream_summary` 用 keyed correction 构造 different_release、`test_security_model` schema head 断言 0028、迁移测试接受 guard 的 `OperationalError`(ERRCODE 55000)。

### 精确验收证据（PR#91）

PR#91 最终 head `4381b4a7b6cce460efad0989aa6ea87b3af5969d`；PR head CI `39515785419` 三 job 全绿（Backend/PostgreSQL/migrations、Frontend tests + Cloudflare production build、CI acceptance），后端 2318 passed / 无 skip。受保护 squash 合并 `dd2438d9c8edd029b36a816f35865e63ddc62c23`。main CI `39516930782` 三 job 成功。Render `/health/ready` ready、version 0.18.48、schema 0028（合并触发重部署）；Cloudflare `softwarelifecycle.whf969.com` HTTP 200；Actions deployment `39517821123`/continuation `39517821137` skipped（SLC_DEPLOY_ENABLED 未启用）。本地后端 SQLite 1682 passed / 648 skipped。

未完成边界：双语只读历史界面、真实 PostgreSQL 长历史（10000）有界矩阵与批准供应商真实验收；Changeover/Batch 自身更正账本仍须单独设计。下一包 `production-actual-history-ui-read`。业务验收 36/44=82%；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0。

## 2026-10-21 生产实绩历史一致性修复：核验、修测试并合并（DeepSeek）

基线真实 main `64b658919d614db169ffeb1578b63aaafa7c0efc`（PR88 已合并），恢复既有开放 PR#89 `codex/production-actual-history-consistency-repair`，未新建重复工作。启动核验发现上一轮 PR#89 遗留两项未闭环：(1) PR head CI 卡死 8 小时成僵尸 run（后端 "Run complete backend suite with real PostgreSQL" 挂起、日志 blob 已消失），mergeable_state=blocked；(2) 代码本体有两个真实测试缺陷——`test_production_actual_history.py::test_correction_occurrence_comes_from_original_audit_and_replays` 在 SQLite 下断言 `dep.deployed_at == first_at` 因 `DateTime(timezone=True)` 读回丢 tzinfo 而失败；`test_production_concurrency_postgres.py` 引用了 `effective_actual` 却未 import（真实 PG CI 下 `NameError`，3 例失败）。

本轮修复：将时区断言归一化为 `dep.deployed_at.replace(tzinfo=timezone.utc) == first_at`（commit `019430f`），补齐 `from app.services.production_history import effective_actual`（commit `158906d`）。本地验证：后端 SQLite 全量 1681 passed / 396 skipped（PG 用例需 CI 真实 PG），collect-only 无 import 错误。推送后取消旧僵尸 run 并由 concurrency 自动清理。

应用层一致性语义（PR#89 本体，前轮已写）：Deployment 首次 Actual 报告写物理列并建立不可变基线；此后无键覆盖返回冲突，带 `request_id + expected_version + correction_reason` 的更正仅追加账本与原子审计，不再重写物理事实；有效历史投影用基线、按 Deployment 聚合的最大 revision 及对应原审计事件有界读取；更正发生时间取原审计 `occurred_at`；Deployment/Batch 详情与批次创建校验统一使用有效 Actual。API 0.18.47 / schema 0027，无 migration、Seed 或依赖改动。

本包不扩大到数据库层旧写者 trigger、完整 production catalog 投影、双语历史界面或真实多用户验收。公共演示只读，OIDC/真实提交关闭，内网未部署。业务 36/44=82% 与七模块 100/100演示/100演示/100/89/60/17、七计划 100/100/20/33/40/20/0 不变（测试修复不提高真实验收）。

### 本包精确验收证据（PR89）

PR#89 最终 head `158906de30954437b391e330559d358d3aba4e4f`；PR head CI `39497922487` 三 job 全绿（Backend/PostgreSQL/migrations、Frontend tests + Cloudflare production build、CI acceptance），后端 2327 passed / 无 skip。受保护 squash 合并为 `a82a3076ee13badbb9cdab94013d6444eb214bfc`（PR#89）。main CI `39499341572` 三 job 成功。Render 后端 `/health/ready` 返回 `ready`、version 0.18.47、schema 0027（合并触发重部署成功）；Cloudflare 前端 `softwarelifecycle.whf969.com` HTTP 200 可达；Actions deployment `39500744981`/continuation `39500745083` skipped（SLC_DEPLOY_ENABLED 未启用）。


## 2026-10-21 生产实际历史追加账本与只读投影（DeepSeek）

基线真实 main `27f9b2470065bb8358f5db532868583b64c241ce`（PR86 已合并），开放 PR 0、无同包未完成分支；独立 `codex/production-actual-history-backend-read`。已核对 PR86 main CI `39473062703` 三 job（Backend/PostgreSQL、Frontend/Cloudflare build、CI acceptance）全绿、部署 `39474452277`/continuation `39474452450` skipped；旧候选 `release-decision-supersession-backend-read` 已被覆盖，按最新 HANDOFF 选 `production-actual-history-backend-read`（设计 §9）。

本包实现 Actual 追加式更正账本与只读投影：新增 `backend/app/models/production_history.py`（`deployment_actual_baselines` 不可变基线 + `deployment_actual_corrections` 追加式更正，前驱/revision/唯一链约束），迁移 `0027_production_actual_history`（升级捕获旧已报告行作 LEGACY_CURRENT 基线、两表 UPDATE/DELETE 拒绝 trigger、存在更正或 FIRST_REPORT 基线时拒绝降级）；`services/production.py::_report_actual` 首次报告建 FIRST_REPORT/IMPORTED_CURRENT 基线、keyed 更正追加账本行（前驱链、revision 递增），保留 `ActualReportResult` 与 POST 三字段响应；新增 `services/production_history.py` 有效值投影（baseline.recorded_actual_version + head revision，区分 NOT_RECORDED/LEGACY/IMPORTED/FIRST_REPORT/UNRESOLVED 及 CORRECTED）。详情/目录增 `actual_history`（history_state、recorded_baseline、correction_count、有界 corrections 列表），目录 deployments 增 `history_state`；前端 `production.ts` 增只读 `ActualHistory`/`ActualCorrection` 类型。Seed 改为对已报告正式行 insert-only（不再覆盖 actual_*/status/deployed_at）并建 IMPORTED_CURRENT 基线。API 0.18.46 / schema 0027 更新。

无键 legacy 覆盖行为本轮保持不变（设计 §4「本轮尚未改变行为」），旧写者冻结 trigger 与无键 409 收紧留待后续 API 版本；Changeover/Batch 自身更正账本仍为下一独立包。公共只读，OIDC/真实提交关闭，内网未部署，不开放浏览器提交。

本地：后端 1679 passed / 646 skipped（PG 用例需 CI 真实 PG），前端 1494 passed / 0 fail / 0 skip，tsc --noEmit 通过，Alembic 唯一 head 0027，进度 --check 通过。业务 36/44=82% 不变（追加账本/只读投影不提高真实验收）；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0。精确提交/PR head CI/合并/main/provider 证据记录本包 PR。

### 本包精确验收证据（PR87）

实现提交 `ada23cc`（+ FK 修复 `99f5ef1`、测试修复 `4e3e074`/`ef8d00e`），PR#87 最终 head `ef8d00e3cdda451ad1a199d3b9674e74cb9e553d`。PR head CI `39482340255` 三 job 全绿（Backend/PostgreSQL/migrations、Frontend tests + Cloudflare production build、CI acceptance），check-runs 含 `Workers Builds: softwarelifecycle` success；后端 2324 passed / 无 skip。受保护 squash 合并为 `3a33a1d8bb5edfddcbfa846e00407d7343b621cc`（PR#87）。main CI `39484008902` 三 job 成功。Render 后端 `/health/ready` 返回 `ready`、version 0.18.46、schema 0027（合并触发重部署成功）；Cloudflare 前端 `softwarelifecycle.whf969.com` HTTP 200。Actions deployment `39485336857`/continuation `39485336931` skipped（SLC_DEPLOY_ENABLED 未启用）。

## 2026-10-21 生产事实更正设计契约补齐（Codex / ChatGPT Work）

基线真实main `c148c96a50a07167b714bf6b7649a55d96bd5eed`（PR85），开放PR0、无同包未完成分支；独立 `codex/production-trace-correction-design-hardening`。已读取最新需求/状态/交接并核对PR85精确head `36c7c0aa03854f4990882237b2392786b310c082`、PR CI39464541840及main CI39465908034三项success；生产Cloudflare build aacb9481-5ed8-4030-b0c4-e5c14b5007f7/version f76d640f-6d7c-4487-ba2b-a8fd55c398df成功，Actions39467348427/39467348464 skipped。以上为启动基线，本包另验精确提交。

只修订设计及状态/交接/进度四文件。旧库当前值明确为LEGACY_CURRENT而非首次报告，保留原审计与历史缺口；Actual独立冻结基线、三类更正前驱/revision/唯一约束、原证明先重放再校验当前头、无键覆盖明确拒绝、旧写者guard和拒绝丢语义降级均已定义。补齐真实消费者/SQL投影/锁图和旧库/并发/原子审计/长历史PG矩阵；发现Seed会给既有正式行重新赋值，将insert-only及更正后重跑列入下一包验收。本轮没有修改Seed或任何后端/迁移/界面/测试/依赖/CI/身份/提供方配置。

API0.18.45/唯一迁移0026不变，Seed幂等性不受本轮影响；只执行文档路径/进度/diff等必要本地检查，未伪称本地后端/PG/前端重跑。精确提交/PR/完整CI/合并及main/provider证据追加本包PR。业务36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，设计不提高验收。

下一包收窄为 `production-actual-history-backend-read`：仅Actual基线/追加更正、全部actual消费者、双语只读历史及真实PG验证；Changeover/Batch自身更正随后分包。精确路径与验收见设计§9，不能直接照旧PR85草案执行完整三类0027。公共只读、OIDC/真实提交关闭、内网未部署，真实提供方多用户验收仍待完成。

## 2026-10-21 生产追溯事实更正设计审查（DeepSeek）

从真实 main `8dbc24cb7474988146a6798ae69690fa98dbab1e`（PR84 已合并 `release-chain-revocation-ui-recovery`）建立独立 `codex/production-trace-correction-design-review`。启动时开放 PR 为 0，main CI `39460162355` 三 job（Backend/PostgreSQL、Frontend/Cloudflare build、CI acceptance）全绿，分支保护要求 backend + frontend 两项必需检查。无未完成开发，故按最新 HANDOFF 选择下一候选 `production-trace-correction-design-review`（旧候选 `release-decision-supersession-backend-read` 已被 PR68/69/70 覆盖，不重复）。

本包只产出设计审查 `docs/production-trace-correction-design-review.md` 并更新状态/交接/进度，不修改后端、迁移、Seed、界面、依赖、CI、调度、身份、密钥或提供方配置。审查结论：现有 `Deployment.actual` 的更正（`expected_version`+`correction_reason`）是原地 UPDATE，历史实际值不可结构化查询；`Changeover`/`Batch` 无任何更正命令；三表均无 append-only 防护。推荐统一为追加式更正账本（`deployment_actual_corrections`/`changeover_corrections`/`batch_corrections` 三张独立账本 + UPDATE/DELETE 拒绝 trigger），`deployments.actual_*` 保留首次报告值，后续更正只追加，统一 resolver 返回"首次值 + 当前更正链 + 最新生效值"。不新增浏览器提交，不开放真实提交。

业务 36/44=82%；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0，验收增量 0。公共只读/OIDC/真实提交关闭、内网未部署。API0.18.45/schema0026 不变，无迁移/Seed 变更。精确提交/PR head CI/合并/main/provider 最终证据记录本包 PR。下一候选 `production-trace-correction-backend-read`（后端 + 迁移 + 追加式更正账本 + 统一只读投影），不开放浏览器提交。

## 2026-10-21 发布链撤销双语确认与原审计恢复（Codex / ChatGPT Work）

从真实 main `8eb25f4b90b506910837faf3b74690f27b66e9c1`（PR83）建立独立 `codex/release-chain-revocation-ui-recovery-reviewed`。启动时开放PR为0；PR80/81均已关闭，PR82/83已合并，故不重复 uncertain 守卫修复。复用PR81未合并界面草案并重新审查，使用main的PR82守卫；修正缺省目标类型与unknown提示，增加独立commands入口、严格同源规范恢复、未知结果锁定和双击/401等行为回归。详见 `docs/release-chain-revocation-ui-recovery.md`。

四类目标精确UUID、审核父链、原因与request_id明示确认；准备/复制/导入不发送，导入wrapper仅支持显式原审计查询。unknown后锁原命令，禁止再次POST或新建请求；回执只显示原审计白名单并链接原事件，原因原文转义。公共环境默认禁用真实提交，governance仍只读。

本地完整前端1494 passed/0 failed/0 skipped，Next/OpenNext构建、auth:check、cf:check成功；完整后台/真实PG未在本地重跑，由精确PR CI另证。API0.18.45/schema0026不变，无Migration/Seed/依赖/CI/身份/提供方配置变更，Seed幂等性不受影响。进度与diff检查随本包执行；精确提交/PR head CI/合并/main/provider最终证据追加到本包PR，不预称成功。

已独立核对基线main CI39455082138三项成功、Cloudflare production build `f3928426-9756-42c5-aef5-a9c8910180cc` 成功（Worker version `4e1800ca-653a-4d18-a964-6ed6a081070b`），补齐此前无token未核验记录。Render既有live `dep-dbbn73l9fdbs73ed2340` 对应后台 `f221bdddc0e110fe61c9d72694408d78a64989b5`，非本包部署；Actions39457194877/39457194880 skipped。

业务36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，真实验收未完成故不提升。公共只读、OIDC/真实提交关闭、内网未部署、真实提供方多用户验收待定。下一候选 `production-trace-correction-design-review` 只审查生产事实追加更正边界和实施矩阵，不启用真实操作。

## 2026-10-20 发布链撤销 uncertain 后二次提交守卫（DeepSeek）

基线远端 main `489df90966a9a97ea76a67de005f602eee6fb64c`（PR79 已合并），开放 PR 为 draft 检查点 PR80（记录 PR79 验收发现的 transport 反例，未合并、未实现）。独立 `codex/release-chain-revocation-unknown-submit-guard`。恢复 PR80 的 `release-chain-revocation-unknown-submit-guard` 优先任务。

问题：PR79 的 `ReleaseChainRevocationSubmission` 在第一次 send 丢响应进入 unknown 后，再次 send 仍会调用业务代理 POST，违反设计审查第 4 节"unknown 锁住原字节、仅允许 audit-only recovery、绝不二次 POST"契约。PR80 用纯本地反例（观察 2 次 POST、期望 1 次）证明该缺陷，且未用按钮禁用或 request_id 幂等代替 transport 契约。

修复：`frontend/lib/release-chain-revocation-transport.ts` 的 `run` 在 `mode==='submit' && this.uncertain` 时直接返回当前状态，锁定原 command/字节，后续 disabled/rejected/冲突不得抹除或重发 uncertain 原请求；recover 保持只读原审计查询。新增独立反例 `an uncertain outcome blocks a second submit and only recovery may run`（首次 lost 后二次 send 不得再 POST、仅 recover 查询），并调整 `disabled and rejected attempts...` 用例以准确反映 uncertain 优先语义。红绿验证：临时移除守卫后反例失败（posts=2），恢复后 6/6 通过。

本地前端完整 1484 passed/0 failed/0 skipped（新增 1 项反例），TypeScript `--noEmit` 通过；本机 Next/OpenNext 构建与 auth:check 由精确 head frontend job 证明。无后端/API/schema/Migration/Seed/依赖/CI/调度/身份/提供方配置变更，API0.18.45/schema0026、Seed 幂等性不变。

业务 36/44=82%；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0，验收增量 0。公共只读/OIDC/真实提交关闭。精确 PR head 完整 CI、受保护合并及 main/Cloudflare/Render 证据记录本包 PR。UI 包 `release-chain-revocation-ui-recovery` 在守卫修复后另行推进。

### 本包精确验收证据（PR82）

精确 PR head CI `39449893219` 三必需 job 全绿：Backend/PostgreSQL/migrations、Frontend tests + Cloudflare production build、CI acceptance。受保护 squash 合并为 `d444c9ae3e034fd81754745793a5d59d05828d54`（PR82）；独立 main CI `39451566237` 三 job 同样成功。前端测试 1484 passed/0 failed/0 skipped。Cloudflare 前端 `softwarelifecycle.whf969.com` HTTP 200 可达，但本地无 CLOUDFLARE_API_TOKEN 无法确认 Workers 生产已切到 `d444c9ae`（部署：未验收，非成功）。Render 后端 health ready 0.18.45/0026，本包纯前端未触发后端重部署（符合预期，非"已部署 d444c9ae"）。Actions deployment `39453032788` 与 continuation `39453032728` 明确 skipped（SLC_DEPLOY_ENABLED 未启用，不能称 Actions 部署成功）。

## 2026-10-20 发布链撤销受控提交浏览器协议（DeepSeek）

基线远端 main `f221bdddc0e110fe61c9d72694408d78a64989b5`（PR78 已合并），开放 PR 0、无同包未完成分支。独立 `codex/release-chain-revocation-browser-protocol`。已核对 PR78/main CI 三项成功、Render 既有 live 与 Cloudflare 生产成功（基线证据，本包精确 head 另验）。

新增 `frontend/lib/release-chain-revocation-transport.ts`：严格 discriminated command `operation=release-chain-revocation`、四类 `target_kind`、`target_id` 与 `expected_context` v1（version 固定整数 1、七个 canonical lowercase UUID、按目标深度强制可空/非空且 target_id 等于对应节点）。reason 1–4000、禁控制字符与孤立代理项，完整 envelope 按真实字节 24KiB 上限（不照抄 8192 使合法中文边界无法提交）。四类固定路径映射 `/releases|deliveries|distributions|authorizations/{target_id}/revocations` 与四类 action `RELEASE|DELIVERY|DISTRIBUTION|AUTHORIZATION_REVOKED`。Submission 状态机 idle→sending→checking→confirmed/rejected/unknown，lost 响应锁原字节、recover 仅查询审计、禁用/拒绝不抹除未知结果。

新增 `frontend/lib/release-chain-revocation-audit.ts`：严格 `EVT-RCR-{request_id.hex}` projector，校验 event_type/entity_type/entity_ref/action/detail、payload.revocation_id/release_id/snapshot_id/release_decision_id/reason/protocol_version=1/review_context/request 及 actor_principal_id 绑定与 declared_actor_name=null，不借当前治理状态推断原结果、不把 legacy 三字段审计升级为 v1 回执。

新增两条同源代理 `/auth/release-chain-revocation`（submit）与 `/auth/release-chain-revocation-receipt`（recover），仅 POST；`browser-auth.ts` 新增三开关精确匹配的 `releaseChainRevocationSubmissionConfigured` 与 `handleReleaseChainRevocation`（24KiB 请求上限），`browser-session.ts` 新增 `executeReleaseChainRevocationCommand`（submit 一次 POST 后经 `/api/v1/activity/EVT-RCR-...` 原审计确认，审计响应独立 64KiB 上限；recover 允许只读会话查询）。`check-browser-auth.cjs` 增补两条路由的禁用检查与三项环境变量。

本地前端完整 1483 passed/0 failed/0 skipped（原 1475 新增 8 项定向 transport/wiring 回归），TypeScript `--noEmit` 通过。本机 Next/OpenNext 构建与 `auth:check` 因执行环境沙箱拦截 `.next` 深层目录写入未在本地完成，必须由本包精确 PR head 的 frontend job（npm test + cf:build + auth:check）证明，不以本地部分通过代替。无后端/API/schema/Migration/Seed/依赖/CI/调度/身份/提供方配置变更，API0.18.45/schema0026、Seed 幂等性不变。

业务 36/44=82%；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0，验收增量 0。公共只读/OIDC/真实提交关闭、内网未部署；真实多用户桌面/手机与中英文验收未完成。下一包 `release-chain-revocation-ui-recovery`：双语确认/结果 workbench、精确 governance 页入口、i18n 与 audit-only 导入/导出，不启用真实开关。精确 PR head 完整 CI、受保护合并及 main/Cloudflare/Render 证据记录本包 PR。

## 2026-10-20 撤销审核上下文后台绑定（Codex / ChatGPT Work）

基线远端main `91ef88765d2bf666c6239b0359e8368a42efbc41`（PR77），开放PR 0、相关远端分支无未完成同包。独立 `codex/release-chain-revocation-review-binding-backend`。启动核对main CI39425287506三项成功、Cloudflare生产961463a0-6c41-439e-8f1a-6429c6987422成功；Render既有live dep-dbah7n942hec73dkdv90仍对应后台943a342d；Actions39426311122/39426310917 skipped，未当成部署成功。

四类既有撤销POST增加可选严格v1 expected_context；根到叶锁内核对审核过的Release/Snapshot/有效决策/精确包修订UUID及父链。完整原请求与actor精确重放优先，之后祖先撤销/决策替代不覆盖原结果；旧三字段审计/重放保留。v1审计与账本同事务，保存审核上下文；专用治理GET回显精确target及可审核context，无有效RELEASE/不完整链/已撤销不提供context。既有详情/许可检查不加载审核决策，保留原查询契约。增加真实PG同key、父子许可和决策竞争、原审计重放与失败原子性测试，扩展四类范围授权/只读/严格字段/长历史有界回归。初次本地完整回归发现Deployment详情查询契约失败，已将审核查询限制在专用GET，保留原测试并重新验证。

本地最终完整后端1671 passed/638 skipped（无TEST_POSTGRES_URL，不计PG通过）；撤销及Deployment定向41 passed。Alembic唯一head0026、离线SQL、进度和diff检查通过。精确PR完整CI必须证明真实PG无skip及前端/Next/OpenNext；最终结果另记PR。

仅后台API/service、对应测试、设计说明与状态/交接/进度变更；API0.18.45/schema0026不变，无migration/Seed变更，幂等性不受影响。无前端或真实身份/写入/计费/CI/调度/部署权限配置变更。完整本地与精确PR/main CI、provider最终证据在本包PR记录，不把基线当成本包验证。业务36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，真实验收未完成故不提升。下一包 `release-chain-revocation-browser-protocol`：严格原审计projector、同源默认关闭提交及audit-only恢复；双语确认/导入UI随后独立实现。

## 2026-10-20 发布链撤销受控提交设计审查（Codex / ChatGPT Work）

本轮从真实 main `74fa2e694c56da7ea7eeb4e0f0d080cde4a2fb21`（PR76）创建独立 `codex/release-chain-revocation-submission-design-review`，开放PR 0。已核对 main CI `39421592004` 三项成功、Cloudflare生产 build `2925a4b4-b0e2-4486-8940-845bb48fad25` 成功；Render既有live `dep-dbah7n942hec73dkdv90` 对应后端 `943a342d80f3d229a790c93ae646dac76410ed86`，并非PR76重新部署。Actions deploy `39422865320`/continuation `39422865279` 为skipped。

新增 `docs/release-chain-revocation-submission-design-review.md`：按实际四路由/角色、原审计和重放顺序核对缺口，选择先补锁内审核上下文绑定与版本化审计，再实现独立默认关闭的窄提交/恢复协议，最后做双语确认和audit-only导入。明确旧三字段审计不能伪装新审核证明、201/current governance不是原回执、unknown不自动重发、中文正文按字节有界、真实PG竞态及兼容矩阵。仅文档/状态/交接/进度四文件变更；API0.18.45/唯一迁移0026/Seed不变。本包检查与精确PR/main/provider最终证据记录于PR，不复用基线作为本包通过。

业务36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，文档不提高验收。下一小包 `release-chain-revocation-review-binding-backend`，精确路径与验收见设计末节；公共只读、OIDC/真实提交关闭、内网未部署、真实多用户验收未完成。

## 2026-10-20 发布链撤销双语只读展示（Codex / ChatGPT Work）

基线为真实 main `b2e40426148bb4d3166effef417b9052ce5fa6f9`（PR75），开放 PR 为 0；独立分支 `codex/release-chain-revocation-browser-read-only`。启动前已独立核对 PR75/main CI `39418506472` 三项成功、2272 backend/233 PG cases 无 skip/1462 frontend、Cloudflare Production build `3fe95c2a-99c6-4397-b19d-8bd6a7368ae4` 成功；Render 仍为后端提交 `943a342d` 的既有 live。该证据是基线，本包精确 PR head 与合并后的 CI/provider 须分别核验。

新增 `/governance/{kind}/{targetId}` 双语只读页面，复用四类精确对象 GET，一次请求、10秒上限、不预取/轮询。SSR/ASR、精确 Delivery revision、Distribution、Authorization 详情用原 UUID 进入。原记录状态与 ACTIVE/REVOKED/BLOCKED_BY_ANCESTOR/UNRESOLVED 分开显示；自身撤销与祖先阻断分开，最多四节点历史，并链接精确 `EVT-RCR-{UUID hex}` 原审计。缺失、异常、矛盾、越界响应不显示有效许可，UNRESOLVED 不伪装成空历史；原因/记录者保留原文并转义。当前观察不等于审批、发布就绪、写入许可或提交回执。契约见 `docs/release-chain-revocation-browser-read-only.md`。

新增12项定向行为回归及1项自动页面本地化覆盖；本地完整前端1475 passed/0failed/0skipped，Next15.5.24/OpenNext1.20.6 build成功；进度/Worker/禁用认证SSR/diff检查按本包验证记录执行。初次定向本地化检查发现 Audit 中文词条缺失，已补齐；未削弱既有测试。后台/真实PG本地未重跑，完整三项CI必须由本包精确提交证明。本包无后台、API/schema、Migration、Seed、依赖、CI、调度、身份或提供方配置变更；API0.18.45/schema0026，Seed幂等性不受影响。最终提交/PR/合并/main/provider记录于本包PR。

业务仍36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0。公共只读、OIDC/真实提交关闭、内网未部署；真实多用户桌面/手机浏览器验收尚未完成。下一包 `release-chain-revocation-submission-design-review`：审查独立默认关闭受控提交、精确原审计证明与不确定结果恢复，生产事实更正继续另包。

## 2026-10-19 发布链永久撤销后端与统一读取（Codex / ChatGPT Work）

从远端最新 `main` `f571f296fcd61daad2cfe2da49f9baf1902503ba` 创建独立分支 `codex/release-chain-revocation-backend-read`；启动时开放 PR 为 0，未发现前序未完成实现。远端实现提交 `74bddd2915cc6caa626a8f902f359aa00b399f21` 新增唯一迁移 `0026_release_chain_revocation` 与 API `0.18.45`：四目标 XOR 追加式撤销账本、每目标唯一撤销、UPDATE/DELETE 拒绝、存在历史拒绝降级，以及针对 ReleaseDecision、DeliveryPackage、Distribution、SoftwareAuthorization、Deployment、ProductionBatch 的数据库旧写者 insert guard。

新增四个受范围授权的后台撤销端点和统一治理读取，严格绑定 `request_id=id`、`EVT-RCR-{request_id}`、原 actor/请求正文精确重放和同事务审计。服务统一采用 Release→Package→Distribution→Authorization 根到叶锁序；自身撤销显示 `REVOKED`，祖先撤销显示 `BLOCKED_BY_ANCESTOR`，原 `recorded_status` 与历史事实不改。新 ReleaseDecision、交付、分发、授权、Deployment 和 Batch 被阻断；actual report/更正与 Changeover 仍可记录物理事实。现有交付、分发、授权及 Deployment 详情增加只读 governance 投影，历史链断裂时 fail-closed 为 `UNRESOLVED`。公共环境仍只读，不增加浏览器提交能力。

本地验证：新增/相关回归 224 passed、1 skipped；完整后端 1643 passed、629 skipped（本地未提供 `TEST_POSTGRES_URL`，未把 skip 当作通过）；前端 1462/1462 passed；Next/OpenNext Cloudflare build 成功；Alembic 单一 head 为 `0026_release_chain_revocation`。PR74 最终 head `f32de3c8d4b0c0df737a62bffa5d76717a9270d7` 的精确 CI `39154785266` 三项必需检查全部成功，记录 2272 backend passed、233 PostgreSQL-module cases/no skips、1462/1462 frontend passed 与 Next/OpenNext build 成功。受保护合并提交为 `943a342d80f3d229a790c93ae646dac76410ed86`；独立 main CI `39155649606` 同样三项成功并记录相同计数。

Cloudflare exact-head Preview deployment `d23b3bea-9e94-42a8-9e43-c7225939e995` 成功；main Production build `061e181b-3551-4814-b7cf-9da6cf6818f5` 成功并精确绑定 `943a342d`。Render 自动部署 `dep-dbah7n942hec73dkdv90` 已为 live，精确对应同一 main 提交，验收窗口无 error 日志；未触发手工部署、重启、升级或配置写入。Actions deployment `39156415283` 与 continuation `39156415252` 明确 skipped，不能称其执行成功。完整回执见 `docs/release-chain-revocation-verification.md`。

业务验收仍为 36/44=82%；七模块仍为 100/100演示/100演示/100/89/60/17；七计划仍为 100/100/20/33/40/20/0。该里程碑继续保持未完成，待双语浏览器只读展示、默认关闭受控提交/原审计恢复和批准提供方多用户验收。下一独立包建议 `release-chain-revocation-browser-read-only`，只做双语只读可视化与有界历史，不启用提交。

## 2026-10-18 发布链追加式撤销设计验收闭环（Codex / ChatGPT Work）

PR72 最终 head `2ce160adebeeb6e18aba561cb507cc14326fec6d` 已合入当时最新 main，精确 head CI `39131206270` 的后端/PostgreSQL、前端/Cloudflare build、CI acceptance 三项必需检查全部成功。受保护合并提交为 `7e18b9a6e4cc59fb4434187bf3c5b30de26420f9`；独立 main CI `39131785281` 同样三项成功。精确测试证据为后端 2267 passed、PostgreSQL module 230 cases no skips、迁移单一 head `0025_release_decision_supersession` 往返通过、前端 1462/1462 passed，Next/OpenNext build 成功。

Cloudflare 精确 PR head Preview deployment `2a7da6f6-7821-4667-bd24-5d62b8433d89` 成功；main production build `1292d2c5-f420-4ad4-a345-1bf930bf6034` 成功，对应 version `64e580e3-bcbb-4ed4-b871-bf18683bd16a`。Actions deploy `39132510691` 与 continuation `39132510713` 均为 skipped。Render 因本包仅修改文档且服务 `rootDir=backend` 未触发新部署；最新 live 仍为 `dep-dba2n68ae00c739c31j0`，精确后端 commit `aad807cd1ec16afccdf1cb3bb124c22dec0cc90a`，验收窗口无 error 日志。该状态不能表述为 Render 已部署 PR72。

本包不增加业务验收点：36/44=82%；七模块仍为 100/100演示/100演示/100/89/60/17；七计划仍为 100/100/20/33/40/20/0。公共演示保持只读，OIDC、真实业务写入、内网部署与生产配置仍关闭。下一包为 `release-chain-revocation-backend-read`，按已审查语义实现 0026、四类后台撤销、统一有效读取和双语只读展示；不开放浏览器提交。

## 2026-10-18 发布、交付、分发与授权追加式撤销设计审查（Codex / ChatGPT Work）

从已合并 PR70 的真实远端 `main` `b1097a97c80cc27f58699d9606020ad93ab48b61` 开始，开放 PR 为 0，上一包精确 head 和独立 main 三个必需 CI job 及 Cloudflare 生产构建均已成功。本轮只做 `release-distribution-revocation-design-review`，核对 Release、DeliveryPackage、Distribution、SoftwareAuthorization、Deployment/Batch 的实际模型、写入锁序、审计与全部读取消费者；不修改后端、迁移、Seed、依赖、CI、身份、门控或提供方配置。

新增 `docs/release-distribution-revocation-design-review.md`，推荐一张带四个真实 nullable FK 和严格 XOR 约束的 `release_chain_revocations` 追加式账本。撤销永久终止精确对象的未来许可效力，祖先撤销仅派生 `BLOCKED_BY_ANCESTOR`，不修改原 status、不自动制造子撤销、不删除或重写既有 Delivery/Distribution/Authorization/Deployment/Changeover/Batch，也不声称收回文件或回滚刷写。新 Release/修订/分发/授权使用新 UUID；恢复另行设计。

设计明确统一 Release→Package→Distribution→Authorization 锁序、旧写者数据库 insert guard、原业务行与 AuditEvent 同事务、request/actor/正文精确重放、原审计 GET 恢复、旧库无回填和有记录拒绝降级。Deployment/Batch 属于许可型写入并被阻断；actual report/更正及 Changeover 作为物理事实仍可补录但不能授予权限。统一 resolver 必须覆盖目录/详情、Dashboard、ASR Passport、Search、生产来源、制造视图和 Activity，并保留原 `recorded_status`。

拟议下一包 `release-chain-revocation-backend-read` 使用实现时重新核对后的 `0026`，完成四类后台撤销、统一读取、双语只读展示及真实 PostgreSQL 并发/旧库升降级/原审计/长历史测试；不开放浏览器提交。当前 API 仍为 0.18.44、schema 仍为 0025，Seed 未改且幂等性不受影响。业务验收仍 36/44=82%；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0。
## 2026-10-18 ReleaseDecision 追加式替代浏览器协议验收闭环（Codex / ChatGPT Work）

PR70 最终 head `6b0400404f9aee69eab98ebdaed12f747480a126` 已包含当时最新 `main`；首个 head `969ef6e` 因本地化覆盖失败未合并，修复后精确 head CI `39107462789` 的后端/PostgreSQL、前端/Cloudflare build、CI acceptance 三项必需检查全部成功。合并提交为 `b1097a97c80cc27f58699d9606020ad93ab48b61`；其独立 main CI `39108012123` 同样三项成功。精确结果为后端 2267 passed、PostgreSQL module 230 cases no skips、前端 1462/1462 passed，Next/OpenNext build 成功。

Cloudflare production build `a9bcc79f-187a-466d-b82c-b0a73765ab10` 成功，对应 version `9920621e-153f-4f63-89a1-898919f9c98e`；Actions deploy `39108584069` 与 continuation `39108584068` 均为 skipped，不能称其执行成功。Render 因本包仅修改前端且服务 `rootDir=backend` 未触发新部署；最新 live 仍为 `dep-dba2n68ae00c739c31j0`，精确 commit `aad807cd1ec16afccdf1cb3bb124c22dec0cc90a`，只读健康日志持续返回 200。该状态说明后端内容未变化且健康，不等同于 Render 已部署 `b1097a9`。

公共演示继续只读；OIDC、真实业务写入、内网部署与生产级配置保持关闭。本次验收不替代批准提供方、多用户桌面/手机和中英文真实浏览器人工验收。业务验收仍 36/44=82%；七模块仍为 100/100演示/100演示/100/89/60/17；七计划仍为 100/100/20/33/40/20/0。下一包为 `release-distribution-revocation-design-review`，只做发布、交付、分发与授权撤销/阻断边界设计，不改写既有生产事实。
## 2026-10-18 ReleaseDecision 追加式替代浏览器协议（Codex / ChatGPT Work）

从已合并 PR69 的真实远端 `main` `aad807cd1ec16afccdf1cb3bb124c22dec0cc90a` 创建独立分支 `codex/release-decision-supersession-browser-protocol`；启动时开放 PR 为 0，旧实现分支仅为已完成历史。本包新增独立的 ReleaseDecision 替代浏览器协议：严格冻结新 APPROVED 请求、当前前驱、同 Release/冻结 Snapshot 与完整新决策；显式双语复核后才允许提交。成功响应不作为证明，必须读取 `EVT-RD-{request_id}` 原子审计并匹配认证主体、原请求、审批、前驱和实际结果；传输不确定后锁定原字节，仅允许查询原审计，不自动重放写入。

同源代理只接受有界 JSON POST，且必须同时显式配置 `RELEASE_DECISION_SUPERSESSION_SUBMISSION_MODE=enabled`、精确批准 API base 和 app origin；公开/演示环境默认关闭，read-only 身份只能恢复审计。有效决策详情只为当前有效且上下文完整的记录提供准备入口；不编辑前驱，不撤销已有 Delivery/Distribution/Authorization/Deployment/Changeover/Batch，也不把 HOLD 称为物理回滚或生产发布。新增协议说明及 7 项定向回归，当前 7/7 通过；完整仓库前端、Next/OpenNext、后端和真实 PostgreSQL 由本包精确 PR head CI 验收，未完成前不合并。

业务验收仍 36/44=82%；七模块仍为 100/100演示/100演示/100/89/60/17；七计划仍为 100/100/20/33/40/20/0。代码协议不替代批准提供方、多用户桌面/手机与中英文真实浏览器验收。下一包建议先做 `release-distribution-revocation-design-review`，划清发布/交付/分发/授权撤销与已有生产事实的边界；生产更正另包处理。

## 2026-10-18 ReleaseDecision 追加式替代后端与统一读取（Codex / ChatGPT Work）

从真实远端 `main` `16c791d11f59315f655d57d0314207f581dedb1c`（PR68）创建独立分支 `codex/release-decision-supersession-backend-read`；启动时开放 PR 为 0，未发现同名实现分支。新增 `0025_release_decision_supersession`：正式决策增加同 Release/同 Snapshot 复合前驱、唯一后继、成对非空更正原因、自指拒绝、有效读取索引和 PostgreSQL UPDATE/DELETE 拒绝 trigger；存在替代历史时 downgrade 明确拒绝。API 更新为 `0.18.44`，required schema 为 `0025_release_decision_supersession`。

既有 `POST /api/v1/approvals/{approval_no}/release-decision` 以可选成对字段 `supersedes_id`/`correction_reason` 支持显式 SUPERSEDE：保持 Release→Approval 锁序，只允许替代当前有效决策、同冻结 Snapshot 和新的 APPROVED ApprovalRequest；原请求全正文/可信 actor/原审计重放保持稳定，审计动作 `DECISION_SUPERSEDED` 与新旧绑定同事务写入。普通 DECIDE 兼容。共享有界 SQL resolver 已接入 Delivery、Dashboard 当前决策、ASR 护照、演示状态和旧版发布详情；治理目录、详情、Dashboard 历史和生产来源保留全部旧行并显示前驱、后继、更正原因和效力。Seed 的 RD-0081 改为缺失插入、存在精确验证、冲突失败，不再更新正式历史。

前端 ReleaseDecision 详情新增双语只读历史关系；不新增浏览器提交入口，公共样例仍只读。本地 1641 后端通过/626 真实 PostgreSQL 模块因无 `TEST_POSTGRES_URL` 跳过；针对性 93 通过/4 PG skip；Alembic 0001→0025 离线 SQL 成功；前端 1453/1453 通过，Next 15.5.24 与 OpenNext Cloudflare bundle 成功。精确 PR head 真实 PostgreSQL CI、合并后 main/Cloudflare/Render 证据在本包 PR 验收后补充。当前 Render 只读核验仍是旧 live deploy `dep-db5sl1fgfhjc73eva640`/commit `9dba7e9`，未触发部署，不能称本包在线。

业务验收仍 36/44=82%；七模块仍为 100/100演示/100演示/100/89/60/17；七计划仍为 100/100/20/33/40/20/0。代码完成不替代真实提供方多用户/浏览器验收。下一包为独立默认关闭的 `release-decision-supersession-browser-protocol`；之后另行定义发布/分发/授权撤销与生产更正，不能把本包 HOLD 替代称为既有实物撤回。

## 2026-10-17 ReleaseDecision 追加式历史替代设计审查（Codex / ChatGPT Work）

从已合并 PR67 的真实远端 `main` `daa14183197eecb5590f973f45817be79f695444` 创建独立分支 `codex/release-review-history-design-review`。PR67 精确 head `8a254b93b449a470973932cdb9ebecd8dad061c6` 的 CI `39007389782` 三个必需 job 成功：2262 后端、228 PostgreSQL-module cases 无 skip、1453 前端及 Next/OpenNext/disabled-auth SSR；合并后 main CI `39010669503` 三 job 成功，Cloudflare production build `b5ad9937-094a-482a-9e7e-cd6cc6c7ee98` 成功。Actions deploy `39011070086` 与 continuation `39011070091` 均 skipped，不称 Actions 部署成功。

Render 技能只读复核 `My Workspace` 中既有 free 服务 `softwarelifecycle-api-test`：仍为 main/自动部署、最近部署 `dep-db5sl1fgfhjc73eva640` live 在后端提交 `9dba7e9`；没有触发部署、重启、升级或配置变化。日志在休眠前连续 `/health/ready` 200，免费实例停机后首个 30 秒请求超时，第二次冷启动成功返回 API `0.18.43`、schema `0024_release_customer_scope`。该旧后端部署与当前前端 main 分开记录。

设计 `docs/release-decision-replacement-design-review.md` 将“release-review 历史替代”收窄为正式 `ReleaseDecision` 的显式 SUPERSEDE：精确当前前驱、同 Release/冻结 Snapshot、新 APPROVED ApprovalRequest、全量新决策和独立更正原因；原决策、审批步骤/动作及原审计不修改。WITHDRAW、既有交付/分发/授权撤销和物理回滚明确不在同一包，避免把未来写入阻断误称历史实物撤回。推荐下一实现包使用拟议 0025、append-only trigger、复合同上下文前驱、唯一后继、Release 锁和共享有效决策 resolver，统一 Distribution、治理目录、护照、演示状态及来源消费者；Seed 改为存在即精确验证而非修补历史。

本包只改设计/状态/进度/交接文档，不实现后端、迁移、Seed、前端提交、依赖、CI、身份或提供方配置；拟议 revision 不是现有 schema。业务验收仍 36/44=82%；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0。下一包 `release-decision-supersession-backend-read`；随后独立浏览器协议、发布/分发/授权撤销、生产更正、真实身份/浏览器、内网和运营迁移，VIN 最后。

## 2026-10-17 演示状态页读取超时保护（Codex / ChatGPT Work）

从真实 main `774f03bbd6c7df73ed2c1bae55133222fcf33f4c`（PR65已合并）开始，开放PR为0，独立分支 `codex/demo-status-read-timeout`。基线完整CI38569904417三个必需job success；Cloudflare生产build2eca89ad-a010-4617-82eb-10cf5ad5a0d2/versiond04dda23-ea8b-4fe7-a35a-64ba0d26e4fa success。Actions deploy/wake skipped。本包精确head完整CI、合并main和生产检查必须另核验，最终结果记录本包PR，不能用基线代替。

承接PR65交接中的状态页超时工作：仅 /demo/status 的三个固定并发GET各设置10000ms读取上限，覆盖响应头与JSON正文；超时返回原有未确认/不可用状态并取消请求，已成功的其他观察保留。即使上游取消后未及时settle，Promise竞争也释放页面；迟到响应不能改成成功，迟到拒绝有处理。每次人工重新读取各请求一次，无自动重试/轮询，不把超时推断成空库、未导入、配置错误或数据库故障。共享apiGet仅新增可选参数，其他调用保留原有行为；不修改后端/数据库/迁移/Seed/身份/门控/依赖/CI或提供方配置。

新增8项行为回归：卡住的响应头、正文、迟到成功/拒绝、成功/HTTP/网络/JSON失败清理、无配置、无效时限、原调用兼容及真实状态页与共享读取组合。定向44项通过；完整前端1436 passed/0 fail…42108 tokens truncated…2d9f2da5ff62a7fa713c0b72de41261f03，起点main22ede3fa59794a35e4766ec8d655d10c18919720。
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

## 2026-10-09 Resource 原请求摘要、提交与原审计恢复基础（Codex）
起点main ba49d2a0cc00bf68b1bc58008a74b79bd8eb3ec4；该main CI37894940845后端/前端/acceptance全部成功，Cloudflare production build a52c824d-9677-44b0-aa9d-bff4123674ad/version add85864-7529-41cc-94e1-b32eea642fdd成功；Actions独立deploy跳过，开放PR0。
本包Resource独立默认关闭提交/原审计查询代理、严格请求/目标绑定、摘要绑定精确回执与冻结控制器完成。旧审计不含完整标题/位置/描述，新增v1规范UTF-8请求SHA256摘要，不在活动payload保存位置或描述；与业务行/审计同事务，旧记录不补写。原审计缺摘要保持unknown，不以当前对象/POST结果伪造确认。HTTP201/200均须原审计，恢复只GET；仅证明资源登记，不证明存在/内容/分发权限。API代码0.18.37/schema0020，无迁移；线上API部署版本尚未核验，前端构建不替代后台部署。
十二类代理/控制器（11→12/14，86%），十一类双语UI不变；Resource UI及Impact/Acceptance代理/UI仍待完成。本地完整前端1015通过/0fail/0skip（原993新增22），Resource后端47、授权/审计定向合计76通过；新增2隔离真实PG摘要/原子回滚测试由Actions验收，本地无PG服务，不能声称已通过。新增摘要回归先验证旧实现缺request_sha256失败，补强后通过；TypeScript、Worker配置和进度--check通过；生产构建/禁用认证SSR结果和精确head CI/provider另记录。
本次SoftwareLifeCycle_20全文检索服务报错，未取得原文，依据仓库最新main交接继续。云端Linux完整checkout的Codex直接编写；未另启动独立Codex云任务。公共样例只读，OIDC及全部提交默认关闭；未配置真实身份/授权/秘密，无真实提供方/浏览器/管理员/内网验收，内网未安装，SSO/人员/Windows无Docker/CPU待定。仅内存，跨刷新/卸载/会话恢复待完成，不重试已拒绝浏览器访问。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，验收增量0；代理覆盖+1，UI增量0。下一包Impact/Acceptance独立提交及原审计恢复，随后补齐三类双语UI；再做跨会话恢复、更正撤销、真实身份/内网验收及离线运营迁移，VIN最后。契约docs/resource-command-submission.md。

## PR#36 验收 — 2026-10-09（Codex）
PR https://github.com/Wang106/SoftwareLifeCycle/pull/36 已合并；代码main b812e82d76b1c9ff7e70c67172a4a4d0c9f66e05，精确feature 581207d06ee25ea02cbf76a2ef7762876058d9ee，起点main ba49d2a0cc00bf68b1bc58008a74b79bd8eb3ec4。
feature CI37896920738三任务成功：2079后端（423.86秒、11443既有warnings），174 PostgreSQL-module cases/no skips；1015前端/0fail/0skip。后端113710265173、前端113710265441、acceptance113712567433成功；0020单迁移头/SQL/隔离真实PG往返、进度账本、TypeScript、Next/OpenNext Worker、中英文禁用认证SSR均通过。Resource两路由GET405/POST503、private/no-store。Cloudflare feature Preview build ed8dedc0-e873-400d-9884-e819a37f8c6f成功；不是main生产部署证据。本记录后的最新main精确CI/provider须另核对；Actions独立deploy仍默认跳过，不能声称已启用。
Resource请求v1 SHA256摘要与原子审计、独立默认关闭提交/只读原审计恢复、严格回执及冻结控制器完成。旧审计不含摘要保持unknown，不补写历史，不以当前资源详情或POST回执替代原请求证据。活动payload不保存位置/描述；原登记不证明文件存在、内容验证或分发权限。代码API0.18.37/schema0020，新增后台审计字段无迁移，在线Render后台部署/版本未核验，前端构建不能替代API部署。
代理/控制器11→12/14（86%）、双语UI仍11/14；Impact/Acceptance基础以及Resource/Impact/Acceptance三类UI待完成。本地完整前端1015、后端定向76、TypeScript、Worker配置/构建及禁用认证SSR通过；真实PG新2项由本PR Actions验收。本地无PG服务，不称本地PG已通过。新增摘要测试先证明旧实现缺request_sha256失败，补强后通过；没有新增未修复失败。云端Linux完整checkout的Codex直接编写；Git CLI无推送凭据，经GitHub连接发布并校验21文件blob SHA与本地一致，无另启独立Codex任务。
SoftwareLifeCycle_20原文检索服务报错，未取得全文，按main交接承接。公共样例只读、OIDC及所有提交默认关闭，未配置实际身份/授权/秘密；真实提供方/浏览器/管理员/内网验收未进行，不重试拒绝的浏览器访问。内网未安装，SSO/人员/Windows无Docker/CPU待定。恢复仅内存，刷新/卸载/跨会话导入仍待完成。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，验收增量全部0，代理覆盖+1，UI增量0。下一包Impact/Acceptance独立提交与原审计恢复，随后三类双语UI；再做跨会话恢复、更正撤销、真实身份/内网验收及离线运营迁移，VIN最后。契约docs/resource-command-submission.md。

## 2026-10-09 Impact、Acceptance 提交与原审计恢复基础（Codex）
起点main 68e7491513b0e6676323652f14ac32f7d88ef590；精确CI37897837744后端/前端/acceptance全部成功（2079后端、174 PG模块无skip、1015前端），Cloudflare生产build965910f1-7e36-427e-87b3-71680f5e9ec4/version1f803cdf-9f4e-4926-8a42-a933068d92b1成功；Actions独立deploy跳过、开放PR0。
两类独立默认关闭提交/原审计恢复代理、严格正文/目标绑定、原回执与EvidenceSubmission冻结控制器已实现。Impact新增v1规范UTF-8 nullable evidence_ref SHA256摘要，引用不放入活动payload；缺摘要的旧审计包括原null仍unknown，不补写、不查询当前对象。Acceptance实际旧审计已完整，按原assignment/criterion/DVP、声明/原因/实体校验，不伪造历史指纹。两类HTTP201/200都需原审计确认，recover只GET，unknown后拒绝不抹除未知，明确重试原ID/字节不变。原Issue/SCR UUID与assessment/assignment UUID分开；原Snapshot标签来自审计而非请求，不推断当前状态、测试通过、验收完成或下游许可。
代理/控制器12→14/14（100%）；双语UI仍11/14，Impact/Acceptance/Resource三类UI下一包。69页面；API代码0.18.38/schema0020，无迁移，在线Render后台版本/部署未核验。资源独立门控不变；EVIDENCE_COMMAND三变量门控独立且默认关闭，唯一token-bound USER复核、非只读才提交、只读可查询本人原审计、凭据不传客户端。
本地完整前端1055通过/0fail/0skip（原1015新增40），Impact/Acceptance/actor/授权定向46与审计/账本27项通过；TypeScript、Worker配置及Next/OpenNext构建/双语禁用认证SSR通过；新两路由GET405/POST503、private/no-store。精确head CI/provider另记录。新增4隔离真实PG原actor/原证据/重放不改审计/原子回滚测试由Actions核验，本地无PG服务。新增Impact摘要测试先证明旧审计缺字段失败，补强后通过；初次前端定向误把服务器原审计snapshot_no当作请求字段，改为非法空标签校验并新增原标签保留回归，最终40通过。
云端Linux完整checkout由Codex直接编写，未另启独立Codex任务；Git CLI无推送凭据，使用GitHub连接发布。公共样例只读、OIDC和全部提交默认关闭，未配置真实身份/授权/秘密，无实际提供方/浏览器/管理员/内网验收，不重试拒绝的浏览器访问。内网未安装，SSO/人员/Windows无Docker/CPU待定。仅页面内存，刷新/卸载/跨会话导入恢复待完成。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，验收增量0；代理覆盖+2，UI增量0。下一包补齐Impact/Acceptance/Resource独立门控及三类双语确认发送/原审计查询/原请求明确重试/精确结果；随后跨会话恢复、更正撤销、真实身份/内网验收、离线运营迁移，VIN最后。契约docs/evidence-command-submission.md。

## PR#37 验收 — 2026-10-09（Codex）
PR https://github.com/Wang106/SoftwareLifeCycle/pull/37 已合并；代码main ce220e8dcdcea4b17f929609cdca08590d92bf22，精确feature fd3dd0b0c101cc097eb51c3a523c26761bfa3d85，起点main 68e7491513b0e6676323652f14ac32f7d88ef590。
feature CI37899889085全部成功：2085后端（301.35秒、11469 warnings）、178 PostgreSQL-module cases/no skips、1055前端/0fail/0skip。后端113719712769、前端113719713082、acceptance113721433758成功；0020单迁移头/SQL/隔离真实PG往返、进度账本、TypeScript、Next/OpenNext Worker及中英文禁用认证SSR通过。两类evidence路由GET405/POST503、private/no-store。Cloudflare feature Preview build0320f49a-c816-4c34-962d-e2a22e65b1f5成功，不能替代main生产部署证据。本记录之后最新main的精确CI/provider另核对；Actions独立deploy默认门控跳过。
Impact/Acceptance独立默认关闭提交与原审计恢复、严格目标/正文/声明绑定、冻结控制器完成。Impact新增v1 nullable evidence_ref SHA256，旧缺摘要审计仍unknown，不补写；Acceptance按已有完整原审计确认，不伪造历史摘要。HTTP200/201均须原审计，恢复只GET；未知后的拒绝保持未知、明确重试保持原字节/ID。原Issue/SCR实体UUID与assessment/assignment原请求UUID分开；Snapshot标签来自原审计，不作为调用者字段，不推断当前状态、测试通过或验收完成。API代码0.18.38/schema0020，无迁移，Render在线后台部署/版本未核验。
本地1055完整前端、73后端定向、类型/Worker配置/构建/双语禁用认证SSR及进度检查通过；4项新增真实PG审计/重放/原子回滚用例由本PR Actions通过，本地无PG服务。云端Linux完整checkout由Codex直接开发，GitHub连接发布并逐一核对21文件blob与本地一致；未另启独立Codex任务。SoftwareLifeCycle_20全文此前检索服务报错，按仓库交接承接。公共样例只读、OIDC及全部提交默认关闭，无实际身份/授权/秘密配置，真实提供方/浏览器/管理员/内网验收未进行，不重试拒绝的浏览器访问；内网未安装，SSO/人员/Windows无Docker/CPU待定。恢复仅页面内存，跨刷新/卸载/会话导入待完成。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，验收增量全部0。代理/控制器12→14/14（100%）；双语UI仍11/14（79%）。下一包接入Impact/Acceptance/Resource独立默认关闭能力及双语确认发送/原审计查询/原请求明确重试/精确结果，unknown跨上下文和能力刷新冻结；随后跨会话恢复、更正撤销、真实身份/内网验收、离线运营迁移，VIN最后。契约docs/evidence-command-submission.md。

## 2026-10-09 Impact、Acceptance、Resource 双语提交界面（Codex）
起点main a34d09da5e331188c96655f6b607dc372e5a496a；精确CI37900763051全部成功（2085后端、178 PostgreSQL-module cases无skip、1055前端），Cloudflare生产build9e914984-04be-48f9-8454-ebfc08b90769/version6b87d364-240b-4516-b01c-f35868666b90成功，Actions独立deploy跳过、开放PR0。
三类已有代理/冻结控制器接入独立evidence/resource能力投影、双语确认发送/原审计查询/原字节明确重试/精确结果。六组门控只复核一次当前USER会话，仅12个布尔值到客户端；明确非只读才发送，只读仍可查原审计。未知请求跨命令/目标/上下文/门控刷新冻结，不借另一组能力，复制/发送/查询同步互锁，成功后不重复写入。Impact保留原nullable evidence_ref/判断/冻结Snapshot及原snapshot_no链接；Acceptance保留原criterion/DVP关联及精确DVP链接；Resource保留原target_ref/标题/位置/描述，仅文本，不打开或获取位置。原结果不推断测试通过、当前影响、验收完成、文件存在或分发权限；详情/history/原审计独立新标签。
双语UI11→14/14（100%），代理/控制器14/14；69页面/API代码0.18.38/schema0020不变，无后台或迁移变更。完整本地前端1087通过/0fail/0skip（原1055新增29组件行为/双语结果、2页面门控、1新组件本地化=32）；41定向、TypeScript、Worker配置/Next/OpenNext构建通过。新增6实际Next命令中英文SSR、禁用认证/路由检查通过，三类只显示准备且无发送能力；evidence/resource四路由GET405/POST503、private/no-store；本包精确head完整CI/provider另核对，不能复用起点main。先新增页面回归证明旧代码无evidence/resource能力失败；初次新UI夹具切换到Resource后关掉原Evidence gate，修为明确重新开放原组再重试，另加关闭门控不借用回归；Resource描述夹具改用真实textarea事件，未放宽业务断言。
执行为云端Linux完整checkout的Codex直接开发，无另启独立任务，Git CLI无推送凭据，使用GitHub连接。公共样例只读、OIDC和全部提交默认关闭，无实际身份/授权/秘密配置；无真实提供方/浏览器/管理员/内网验收，不重试拒绝的浏览器访问。内网未安装，SSO/人员/Windows无Docker/CPU待定；Render在线后台部署/版本未核验，Cloudflare不能代替后台部署。恢复仅页面内存，刷新/卸载/跨会话导入待完成；beforeunload不保证应用内路由提醒。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，验收增量全部0，UI覆盖+3。下一包严格原请求导出/跨刷新卸载会话导入并只查本人原审计，不自动发送；再做追加更正撤销、真实身份/内网验收、离线部署/运营迁移，VIN最后。契约docs/evidence-command-submission.md、docs/resource-command-submission.md。

## PR#38 验收 — 2026-10-09（Codex）
PR https://github.com/Wang106/SoftwareLifeCycle/pull/38 已合并；代码main d5bdee2f4e56173df3ce4fc5a019b199a5c76d1d，精确feature b60e7a0e93a765d5d01819bd5123287ef4602a4a，起点main a34d09da5e331188c96655f6b607dc372e5a496a。
feature CI37902904446全部成功：2085后端（419.51秒、11469 warnings）、178 PostgreSQL-module cases/no skips、1087前端/0fail/0skip。后端113729384952、前端113729385124、acceptance113731913021成功。0020单迁移头/SQL/隔离真实PG往返、进度账本、TypeScript、Next/OpenNext Worker及中英文禁用认证SSR通过；新增6实际Next命令中英文SSR无发送能力，evidence/resource四路由GET405/POST503、private/no-store。Cloudflare feature Preview buildaf7458b8-ed06-47b7-b161-58ed271e82a9成功，不能替代main生产证据。本记录后的最新main精确CI/provider另核对；Actions独立deploy仍默认跳过。
Impact/Acceptance/Resource独立evidence/resource能力投影、确认发送、原审计查询、原字节明确重试与双语精确结果完成；六组门控只复核一次当前USER会话，12布尔能力不含凭据；只读可查询，非只读才提交。未知结果跨上下文/命令/能力刷新锁定，不能借另一组门控或开始新请求，复制/发送/查询同步互锁。Impact保留原nullable引用/判断/冻结Snapshot，Acceptance保留原criterion/DVP关联，Resource保留原target_ref/标题/位置/描述且位置为文本；精确详情、DVP、快照与原审计独立新标签。不推断测试通过、当前影响、验收完成、文件存在或分发权限。
本地1087完整前端、41定向、类型/Worker配置/构建/禁用认证SSR及进度检查通过；32新增=29组件行为/双语结果+2页面门控+1新组件本地化。先新增页面回归证明旧代码缺能力失败；新测试夹具原组gate重新明确开放后才可重试，另外验证关闭不借用；Resource描述使用真实textarea事件修复，未放宽业务断言。本包只有前端/文档，69页面/API代码0.18.38/schema0020不变；完整后端/PG核验由Actions完成，本地无PG。云端Linux完整checkout由Codex直接开发，未另启独立任务；GitHub连接发布并核对14文件blob和整棵tree与本地一致。
公共样例只读、OIDC及全部提交默认关闭，无实际身份/授权/秘密配置；真实提供方/浏览器/管理员/内网验收未进行，不重试拒绝的浏览器访问。内网未安装，SSO/人员/Windows无Docker/CPU待定；Render在线后台版本/部署未核验。恢复仅页面内存，跨刷新/卸载/会话导入待完成，beforeunload不保证应用内路由提醒。SoftwareLifeCycle_20全文此前检索服务报错，依据仓库交接承接。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，验收增量全部0。双语UI11→14/14（100%），代理/控制器14/14。下一包严格原请求导出与跨刷新/卸载/会话导入恢复，只查询本人原审计、不自动写入；随后追加式更正撤销、真实身份/内网验收、离线部署/运营迁移，VIN最后。契约docs/evidence-command-submission.md、docs/resource-command-submission.md。

## 2026-10-09 十四类原请求导出及跨会话审计恢复（Codex）
起点main e1ef9b285eb05ea34a575c0a8222e36843c7d32f；精确CI37904011706全部成功（2085后端、178 PostgreSQL-module cases无skip、1087前端），Cloudflare生产build6c5f8a76-9752-48e5-93c7-619256cbcdf2/version42eb9584-20fe-4569-94b4-8bd1a13a08ec成功，Actions独立deploy默认跳过、开放PR0。
新增slc-business-recovery/v1规范恢复文本，精确origin/operation/target/原body，支持全14类业务请求。确认后明确复制或手动复制，后续同站点会话粘贴并显式暂存，暂存零网络且初态unknown/outcome_unknown。导入控制器只有recover无send，UI隐藏重试，门控后来开放也不能写；仅原页面控制器仍有原字节明确重试。显式查询经独立组门控/当前USER/本人原审计确认，只读可查；缺失/拒绝不证明未提交，旧unknown不能被导入替换。确认可开始独立新请求。复制/导入/编辑/发送/查询同步互锁、过期上下文及处理函数失效。
只接受规范紧凑/两空格JSON（外围空白可有），固定版本和字段、精确同origin；原正文不得经trim/大小写/日期/字段排序改写。拒绝重复键/额外凭据URL回执/不支持命令/UTF8超限/孤立代理字符；总文本32768字节、原命令仍8192字节。原null、ID、时间、声明和artifact集合不变。不是签名/执行证明，仍由后台原actor审计验证；不从文件信任身份或授权，不查询资源路径。HTTPS及显式loopback开发origin；不证明该origin的后台未改变。手动文本包含业务详情/私有路径，须安全保存，不导出凭据，不自动读剪贴板/写浏览器存储/下载上传/联网。旧method/path/body复制并非恢复格式；未导出的内存状态仍会丢失。
本地完整前端1136通过/0fail/0skip（原1087新增30协议/控制器+19实际编译UI行为和双语=49），49定向通过；Worker配置/Next/OpenNext构建及禁用认证SSR通过。新增SSR检查6个中英文命令页存在只读恢复入口。第一次并行TypeScript与构建争用.next生成目录报TS6053，构建结束后单独重跑TypeScript通过，不放宽类型/业务断言。本包精确head CI/backend/真实PG/provider另核对，本地无PG服务。69页面/API0.18.38/schema0020不变，无后台或迁移修改。
云端Linux完整checkout由Codex直接开发，未另启独立任务；Git CLI无推送凭据，GitHub连接发布。公共样例只读、OIDC/全部提交默认关闭，无真实身份/授权/秘密配置；真实提供方/浏览器/管理员/内网及跨会话验收未进行，不重试拒绝的浏览器访问。内网未安装，SSO/人员/Windows无Docker/CPU待定；Render线上后台版本/部署未核验。SoftwareLifeCycle_20全文此前检索服务报错，按仓库交接承接。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，验收增量全部0。14/14代理与14/14双语UI已有；本轮跨会话审计恢复实现覆盖14/14，不代表实际环境验收。下一包追加式更正撤销，优先影响判断/验收-DVP关联历史替代契约；随后真实身份/跨会话/内网验收、离线部署和运营迁移，VIN最后。契约docs/business-request-recovery.md。

## PR#39 验收 — 2026-10-09（Codex）
PR https://github.com/Wang106/SoftwareLifeCycle/pull/39 已合并；代码main dc7d8c77e67eda020aa2e8c4ba6595cf9f717526，精确feature acc4bac21fdb7a9e860c410fd4b7da28a67753ae，起点main e1ef9b285eb05ea34a575c0a8222e36843c7d32f。
feature CI37916281195全部成功：2085后端（417.73秒、11469既有warnings）、178 PostgreSQL-module cases无skip、1136前端/0fail/0skip。后端113773140847、前端113773141114、acceptance113775748687成功。0020单迁移头/SQL/隔离真实PG往返、进度账本、TypeScript、Next/OpenNext Worker及中英文禁用认证SSR通过，6实际Next命令页均有只读恢复入口，无发送能力。Cloudflare feature Preview builde6bd6ac5-4315-4e55-83ca-d89859108545成功，不替代main生产证据。本记录后的最新main精确CI/provider另核对；Actions独立deploy仍默认跳过，Render线上API版本/部署未核验。
十四类原请求手动导出及规范同站点跨会话导入完成，导入零网络/无send/无重试；显式查询原actor原审计，缺失/拒绝仍unknown。恢复文本不是签名或执行证明，业务详情/私有路径须安全保存；不自动保存浏览器数据或读剪贴板。49新增协议/编译UI行为测试通过，实际身份/浏览器/跨会话验收未进行。69页面/API0.18.38/schema0020不变。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，验收增量全部0。公共样例只读、OIDC与所有提交默认关闭，无真实身份/授权/秘密配置。下一包追加式更正撤销，优先影响判断与验收-DVP关联的历史替代契约；随后真实身份/跨会话/内网验收、离线部署和运营迁移，VIN最后。

## 2026-10-09 Impact 原判断绑定的追加式替代（Codex）
起点main 9f3b158c9492ec2ba4c846049f90b03a6a2449d0；精确main CI37917324331全部成功（2085后端、178 PostgreSQL-module cases无skip、1136前端），Cloudflare生产buildf24c43b8-7723-4d2f-a948-85995a307524/version63f10325-e4c7-4db6-ac26-b9ea559da3b4成功；Actions独立deploy门控跳过，无开放PR。
既有Impact POST增加paired supersedes_id/correction_reason，新request_id、同Issue/Release/冻结Snapshot、当前有效原判断ID前置条件；原判断和ASSESS审计不修改。Issue锁串行化原写入/替代/重试，同ID不同正文或actor冲突，精确重试在后来替代后仍返回原应用事实、不恢复当前效力。SUPERSEDE原子审计绑定原ID/原decision/新decision/更正原因、精确actor和证据引用摘要，更正重试须完整匹配原审计。身份/权限正反例保留精确REVIEWER项目角色或PLATFORM_ADMIN例外。
0021迁移增加nullable前驱/原因，不回填旧行；复合同上下文自外键、前驱唯一、非自引用和paired非空长度约束，原append-only触发器保留。存在替代记录禁止丢失关系的降级，不删除历史强行回退。API代码0.18.39/schema0021；Render线上API/schema/部署未核验，代码构建不替代API迁移部署。
当前有界候选/冻结证据SQL先排除显式被替代判断再按既有时间/UUID选择剩余叶节点；独立旧判断不追认更正，不向新Snapshot继承判断。历史保留所有记录和前后ID/更正原因，有界SQL关联后继（可在另一页），摘要计历史总数，增长固定查询形状/标量读取。双语只读UI显示前后UUID和独立审计，不开放更正提交、撤销或把测试PASS等同影响/发布许可；现有普通ASSESS准备/恢复拒绝更正字段或SUPERSEDE审计，原回执仍只证明原操作。
先新增回归证明旧实现缺supersedes_id失败，再实现。最终本地定向71通过/1真实PG deselected；最终较大范围1539通过/593 deselected（139.79秒，无PG服务）；完整后端/PG由精确CI核验。完整前端1143通过/0fail/0skip（原1136新增4历史/双语UI、2普通协议隔离和1组件本地化=7）；类型/Worker配置/Next/OpenNext构建/禁用认证中英文SSR、0021单迁移头及升降级SQL、进度--check通过。35新增单元/处理器回归及12新增隔离真实PG测试，共47后端新增；2132 tests collect通过，精确head完整CI及PG另核验。
本包仅先交付影响判断替代，不称完整更正撤销完成；评审决策历史替代、Acceptance-DVP替代/撤销、Impact撤销和受控更正提交/恢复UI尚未完成。69页面、14业务/2自身会话/6管理员/离线操作分计不变。36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，验收增量全部0，账本只追加未完成里程碑的实现证据。
云端Linux完整checkout由Codex直接开发，无另启独立任务；GitHub连接发布，不创建身份/授权/秘密，不开启OIDC或任何提交。公共样例只读，内网未安装，SSO/人员/系统与CPU/Windows无Docker待定。真实提供方/浏览器/跨会话/管理员/内网验收未做，不重试被拒绝浏览器访问。SoftwareLifeCycle_20全文此前检索服务报错，按仓库交接承接。
下一包Acceptance–DVP历史关系替代/撤销，再补受控更正提交/原审计恢复、Impact撤销及评审/下游更正规则；随后真实身份/内网验收、离线运营迁移，VIN最后。契约docs/impact-judgment-corrections.md。

## PR#40 验收 — 2026-10-09（Codex）
PR https://github.com/Wang106/SoftwareLifeCycle/pull/40 已合并；代码main dd79defafa0027e93dc5a412e14edd2b6c9afde3，精确feature dc663a77f86e59b55169b9fb57dc3e0bc42dd1bb，起点main 9f3b158c9492ec2ba4c846049f90b03a6a2449d0。
feature CI37920958776全部成功：2132后端（502.38秒、11636弃用warnings）、190 PostgreSQL-module cases无skip、1143前端/0fail/0skip。后端113788496661、前端113788496935、acceptance113791614709成功。新增35单元/处理器和12隔离真实PG=47后端回归，新增7前端回归；0021单迁移头/SQL/隔离真实PG升降级往返、进度账本、TypeScript、Next/OpenNext Worker与双语禁用认证SSR通过。Cloudflare feature Preview buildeb8c9b68-7baf-466a-9c03-b866d62c5167成功，不替代main生产证据。本记录后的最新main精确CI/provider另核对，Actions独立deploy仍门控跳过。
Impact同Issue/Release/冻结Snapshot的原判断ID绑定追加式替代、完整actor/正文/原SUPERSEDE审计重试、Issue串行锁和前驱唯一/同上下文复合外键完成。旧判断/旧ASSESS审计不修改，有效读取排除显式被替代记录，历史显示前后UUID/更正原因/独立审计；分页增长固定SQL/标量读取。旧普通准备/发送/恢复协议仍拒绝更正字段和SUPERSEDE回执，不开放更正提交/撤销UI。0021保留旧行，存在更正时拒绝丢失关系的降级。
69页面/API代码0.18.39/schema0021；Render线上API/schema/部署未核验，前端构建不证明后台迁移部署。公共样例只读、OIDC/全部提交默认关闭，无实际身份/授权/秘密配置，真实提供方/浏览器/跨会话/管理员/内网验收未做；内网未安装，SSO/人员/系统与CPU/Windows无Docker待定。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，验收增量全部0。本包只完成Impact替代切片，不称全部更正撤销里程碑通过。下一包Acceptance–DVP历史关系替代/撤销，再补受控更正提交/原审计恢复、Impact撤销及评审/下游更正规则；随后真实身份/内网验收及离线运营迁移，VIN最后。

## 2026-10-09 Impact 审计动作中英文本地化复核（Codex）
已验收起点main 757655d16c92659308d09a9405f26693fb399b66，精确main CI37922122235全部成功：2132后端（466.14秒）、190 PostgreSQL-module cases无skip、1143前端。Cloudflare生产build35a8fc1d-8df9-4811-9c14-5e0f43ef36a1/version57cc0094-d4ef-4950-9180-7b495cb0a6de成功；Actions独立deploy跳过，Render线上API/schema/部署仍未核验。
最终复核发现新SUPERSEDE审计动作码缺中文显示；先新增翻译/实际双语SSR/原始JSON保留回归证明旧显示失败，再补字典“替代”。英文/原始action值/JSON证据不改，后端/路由/契约/API0.18.39/schema0021不变；不新增提交能力或身份授权。
本地完整前端1144通过/0fail/0skip（新增1审计动作本地化回归），Next/OpenNext生产构建通过；单独类型/禁用认证SSR通过。本包精确head CI/provider另核对。Impact替代基础及只读历史已验收，Acceptance–DVP关系替代/撤销、更正提交/恢复和完整撤销仍未完成。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，增量全部0。公共样例只读、OIDC及所有提交默认关闭，无实际身份/授权/秘密配置；真实提供方/浏览器/管理员/跨会话/内网验收未做，不重试拒绝浏览器访问。内网未部署，SSO/人员/系统与CPU/Windows无Docker待定。下一包仍为Acceptance–DVP历史关系替代/撤销，再做更正UI/原审计恢复、Impact撤销和评审/下游政策，随后真实环境验收、离线运营迁移，VIN最后。

## PR#41 验收 — 2026-10-09（Codex）
PR https://github.com/Wang106/SoftwareLifeCycle/pull/41 已合并；代码main e3d4f5ca16f0bfe12f9dd7136e6ead901bf9a393，精确feature 2ff793c751bb576af390faaff22e1d212e3362c8，起点main 757655d16c92659308d09a9405f26693fb399b66。
feature CI37923596146全部成功：2132后端（477.95秒、11636 warnings）、190 PostgreSQL-module cases无skip、1144前端/0fail/0skip。后端113797161030、前端113797161365、acceptance113800078966成功。0021单迁移头/SQL/隔离真实PG往返、进度账本、类型/Next/OpenNext/双语禁用认证SSR通过。Cloudflare feature Preview builda1e33a40-0a38-4973-8bf3-517deb559304成功，不替代main生产证据；本记录后的最新main精确CI/provider另核对，Actions独立deploy仍跳过。
补齐SUPERSEDE审计动作中文“替代”，英文和原始action/JSON证据保持不变；先新增实际双语SSR/JSON保留回归证明旧译文失败，修补后本地1144完整前端/类型/构建/禁用认证SSR通过。后端/API0.18.39/schema0021不变；PR#40的Impact原判断绑定追加式替代、原子审计/Issue锁/唯一同上下文前驱/有界有效读取及降级保护已完成，不称完整更正撤销完成。
PR#41合并后本地执行环境的同步及只读状态命令未返回结果；中止等待，不重复合并或覆盖文件。已通过原GitHub连接确认main/merge及三个文档基准内容，后续验收记录从核验过的远端内容追加。最新本地checkout状态未确认；下一窗口先核对工作区与远端main、保护未提交改动后同步，不把旧本地head当成最新事实。
69页面，14业务/2自身会话/6管理员/离线操作分计不变；公共样例只读、OIDC/所有提交默认关闭，无真实身份/授权/秘密配置。Render线上API/schema/部署未核验，前端构建不等于API迁移部署；真实提供方/浏览器/跨会话/管理员/内网验收未做，不重试拒绝访问。内网未安装，SSO/人员/系统与CPU/Windows无Docker待定。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，验收增量全部0。下一包Acceptance–DVP历史关系替代/撤销，再做受控更正提交/原审计恢复、Impact撤销及评审/下游更正规则；随后真实身份/内网验收、离线运营迁移，VIN最后。


## 2026-10-10 Acceptance–DVP原关系替代与撤销（Codex）
起点main ec12176a23dac49af752d0cfd974b69c956d6973、CI37925224881及Cloudflare生产已核验成功，无开放PR。恢复后的云端Linux完整checkout由Codex直接开发，清洁状态快进同步后使用独立feature；上轮本地未确认限制已解除，未覆盖用户改动。
现有Acceptance POST增加action默认ASSIGN、SUPERSEDE/WITHDRAW及supersedes_id，原关系/原审计不修改。替代/撤销必须新请求ID、同criterion当前有效前驱和原因；替代选不同同SCR测试，撤销保留原测试；当前有效pair重复、失效/外域前驱409，不完整动作422。SCR锁串行化所有动作、完全actor/原审计校验重试；后续替代后的原操作重试不恢复关系。0022同criterion复合FK/唯一后继/动作检查保留append-only triggers，旧行默认ASSIGN，存在更正拒绝降级；永久pair唯一改为SCR锁下有效pair检查，撤销后可明确重新分配。
有界覆盖汇总/选定组/DVP反向关联和内部legacy报告共用有效谓词；完整分页历史保留所有行、scalar前后ID/有效性、双语动作和精确独立审计链接，增长SQL/ORM/页大小受控。普通ASSIGN准备/发送/导入/恢复仍拒绝更正字段及SUPERSEDE/WITHDRAW回执，更正提交/恢复UI未开放。契约docs/acceptance-dvp-corrections.md。
新增35后端单元/处理器/权限/有界历史回归本地通过，13隔离真实PostgreSQL并发/迁移/审计回滚/数据库约束回归由CI验收，本地无PG服务。完整前端1147通过/0fail/0skip，新增2历史/实际双语SSR及1协议分离测试；TypeScript、Worker配置、Next/OpenNext构建、禁用认证双语SSR、进度--check及0022单迁移头/升降级SQL通过。首次alembic入口缺app导入路径，改用python -m alembic后SQL验证成功。本地完整非PG/非operator_db后端1574通过/606 deselected（186.69秒），完整2180已收集；本包精确head CI/provider证据后续验收条目补充，不复用起点或Preview。
69页面/API代码0.18.40/schema0022；14业务/2自身会话/6管理员/离线操作分计不变。公共样例只读、OIDC/所有提交默认关闭，无实际身份/授权/秘密配置，Render线上API/schema/部署未核验，前端构建不证明后台迁移。真实提供方/浏览器/管理员/跨会话/内网验收未完成，不重试拒绝访问；内网未安装，SSO/人员/OS与CPU/Windows无Docker待定。SoftwareLifeCycle_20原文未取得，按仓库需求和交接继续。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，增量0。下一包Acceptance更正/撤销受控提交与原审计恢复协议，再接双语确认/结果/导入恢复；随后Impact更正提交与撤销、评审/下游政策、真实身份/内网验收、离线部署及运营迁移，VIN最后。

## PR#42 验收 — 2026-10-10（Codex）
PR https://github.com/Wang106/SoftwareLifeCycle/pull/42 已合并；代码main 51c9219921baca4c9a8cf05a0c71d9c5a6587909，精确feature 6097534187e2d5df79133f0eaf41894a5838b6a1，起点main ec12176a23dac49af752d0cfd974b69c956d6973。30个发布blob及完整tree与本地逐一核对一致（本地feature89473e8/tree b20f6ff302687506baa65ba7cb27b5eff698abcb）；本地main已安全快进同步到合并提交。
精确feature CI38007402472全部成功：2180后端（506.97秒、11806既有弃用warnings）、203 PostgreSQL-module cases无skip、1147前端/0fail/0skip。后端114079259778、前端114079259824、acceptance114081458352成功；0022单迁移头/SQL/隔离真实PG往返、进度账本、类型/Next/OpenNext/双语禁用认证SSR成功。新增35非PG后端+13隔离真实PG=48，前端新增3。本PR首次完整云端CI成功，Cloudflare feature Preview builda4012cd6-4330-4b4e-8863-f46b7bf4f3b9成功；不是main生产部署。此文档提交后的最新main精确CI/provider另核对，Actions独立deploy仍跳过。
Acceptance–DVP同criterion当前有效原关系绑定替代/撤销、原因/actor/全原审计重试、SCR锁和同criterion复合外键/唯一后继完成；原行/原ASSIGN审计不修改，后续重试不恢复旧效力。覆盖统计及DVP反向关系仅有效行，完整分页历史保留动作/前后ID/有效性与双语独立审计。0022默认旧行为、保留append-only triggers及降级保护；SCR锁下有效pair约束支持明确重新分配。普通ASSIGN传输/导入/恢复仍拒绝更正字段及更正回执，更正提交/恢复UI待下一包。
本地1574非PG/非operator_db后端、1147完整前端、155定向前端、35新增后端、类型/Worker配置/构建/禁用认证SSR/进度检查通过。首次alembic脚本缺app导入路径，改用python -m alembic后升降级SQL通过；首次远端update_ref不能创建不存在的分支，随后明确create_branch成功后才建PR，没有覆盖其他ref。本地执行环境恢复，清洁checkout同步确认，无另启独立Codex任务。
69页面/API代码0.18.40/schema0022；公共样例只读，OIDC/所有提交默认关闭，无实际身份/授权/秘密配置。Render在线API/schema/部署未核验，前端构建不证明后台迁移；真实提供方/浏览器/管理员/跨会话/内网验收未完成，不重试拒绝访问。内网未安装，SSO/人员/OS与CPU/Windows无Docker待定。14业务/2自身会话/6管理员/离线操作分计。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，验收增量0。下一包Acceptance更正/撤销受控提交与原审计恢复协议，再接双语确认/结果/导入恢复；随后Impact更正提交与撤销、评审/下游政策、真实身份/内网验收、离线部署及运营迁移，VIN最后。契约docs/acceptance-dvp-corrections.md。

## 当前入口 — 2026-10-10 Acceptance更正受控协议（Codex）
起点main 9c15808ed41d5cb5c5de79b68eba16c9fd59b0da已核验，精确CI38008222373成功：2180后端、203 PostgreSQL-module cases无skip、1147前端；Cloudflare生产build157e8884-3328-4fdd-b091-792cf1151888/version91c5a882-2b0e-4e34-a66a-5c0b8ea51652成功。工作区清洁，创建codex/acceptance-correction-transport；无开放PR，无另启独立Codex任务。
新增Acceptance SUPERSEDE/WITHDRAW严格原关系上下文、独立默认关闭代理/原审计恢复、原始回执白名单及冻结内存控制器。原body/前驱ID/criterion/测试/动作/原因/当前token-bound USER及原审计全绑定；不读当前效力推断原结果。恢复只GET原审计，unknown保留，显式重试同字节/ID，互锁且确认终态。普通ASSIGN仍隔离，14业务/2自身会话/6管理员/离线操作分计不变。契约docs/acceptance-correction-submission.md。
本地新增39协议/代理回归、1186完整前端/0fail/0skip、类型/Worker配置/Next/OpenNext及禁用认证真实Next路由/双语SSR/进度检查全部通过。最初代理测试函数引用命名不一致，修正后完整通过；无后端本地重跑，精确云端完整CI待验收。本包精确head CI/provider待核对，不能用起点CI证明。本轮无后端/schema变更，69页面/API代码0.18.40/schema0022；双语更正确认/结果及手动导出/只读导入恢复仍待接入。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，验收增量0。公共样例只读，OIDC及所有提交默认关闭，无实际身份/授权/秘密配置。Render在线API/schema/部署未核验，Actions独立deploy跳过；真实提供方/浏览器/跨会话/管理员验收未做，不重试拒绝访问。内网未安装，SSO/人员/OS/CPU及Windows无Docker约束待定，SoftwareLifeCycle_20原文未取得。
下一包Acceptance更正双语确认/结果/手动导出与只读审计恢复导入；随后Impact更正提交与撤销、评审/下游政策、真实身份/内网验收、离线部署及运营迁移，VIN最后。

## PR#43 验收 — 2026-10-10（Codex）
PR https://github.com/Wang106/SoftwareLifeCycle/pull/43 已合并；代码main 2ed38c8cd55d5c1ce9f65efaf2e44141f46ee2db，精确feature f56e01200e0b8ebb875c5e8e95dc2643234b5db3，起点main 9c15808ed41d5cb5c5de79b68eba16c9fd59b0da。18个发布blob及完整tree b8cb88defc974d80500cf780d93a9688778b5979与本地逐一核对一致（本地feature cb4a8e2ab65000507df944062102d9ccf3e75203），本地main清洁快进同步到代码合并提交。
精确feature CI38015391790全部成功：2180后端（473.96秒、11806既有弃用warnings）、203 PostgreSQL-module cases无skip、1186前端/0fail/0skip。后端114104392202、前端114104392023、acceptance114106074341成功；0022单迁移头/SQL/隔离真实PG往返、进度账本、类型/Next/OpenNext/双语禁用认证SSR及新增两路GET405/POST503/private-no-store通过。本PR首次完整云端CI成功；Cloudflare feature Preview builde82683ea-63db-4d1b-8ab0-998e7d9e86be/check114104703260成功，不能替代main生产部署。此验收文档提交后的最新main精确CI/provider另核对，Actions独立deploy仍跳过。
Acceptance SUPERSEDE/WITHDRAW独立默认关闭受控提交与原审计恢复协议、严格前驱上下文/原actor/原因/请求/全审计绑定、回执白名单、冻结内存控制器及互锁完成。原请求字节/ID重试、原审计恢复只GET、unknown保留、确认终态；不从当前后继/效力/覆盖状态推断原操作成功。普通ASSIGN仍隔离。契约docs/acceptance-correction-submission.md，新增39协议/代理回归。
本地1186完整前端、39新增协议/代理、类型/Worker配置/Next/OpenNext/禁用认证SSR/进度检查通过；后端本地未重跑，完整后端/PG以上述本包精确云端证据验收。最初代理测试函数命名不一致已修正；新远端分支用create_branch成功创建，未覆盖其他ref。生成的tsbuildinfo已清理，无用户改动覆盖，无另启独立Codex任务。
69页面/API代码0.18.40/schema0022不变；本包无后端/schema改动，双语更正确认/结果/手动导出与只读审计恢复导入仍待下一包。公共样例只读，OIDC及所有提交默认关闭，无实际身份/授权/秘密配置。Render在线API/schema/部署未核验，前端构建不证明后台迁移；真实提供方/浏览器/管理员/跨会话/内网验收未完成，不重试拒绝访问。内网未安装，SSO/人员/OS/CPU/Windows无Docker待定。14业务/2自身会话/6管理员/离线操作分计；SoftwareLifeCycle_20原文未取得。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，验收增量0。下一包Acceptance更正双语确认/原始结果/手动导出与只读审计恢复导入；随后Impact更正提交与撤销、评审/下游政策、真实身份/内网验收、离线部署及运营迁移，VIN最后。

## 2026-10-10 最新主分支验收与 Impact 待审查计划（Codex）
已同步最新main 995366cd3c5a5b0d06722aa53d980f21cf709bd8（PR48），无开放PR，本地起点清洁；PR47双语更正确认/原结果及PR48手动导出/只读恢复导入已实现，不能重做。精确main CI38028319364成功：2180后端（439.15秒）、203 PostgreSQL-module cases无skip、1219前端/0fail/0skip；backend114143787316、frontend114143787207、acceptance114145137113成功。Cloudflare生产build38f23945-5639-46b4-989a-a84ea2563fd2/check114144078704成功，version21926ecc-a74a-45be-895d-aae7d329e3a9；Actions deploy/wake跳过。以上覆盖旧PR48记录的pending，不是本规划分支的CI。
启用队列的两项Acceptance任务已完成；AGENTS要求后续disabled范围先审查，本轮未擅自启用或实现Impact/数据库迁移。独立分支codex/impact-correction-plan形成docs/impact-correction-plan.md：建议先授权A仅现有SUPERSEDE的独立默认关闭协议/原审计恢复/冻结控制器，无schema变化；B再接双语UI/手动恢复；C撤销模型与迁移独立审核。核对实际模型/锁/原审计字段；撤销不能伪装为NOT_AFFECTED/NEEDS_REVIEW，也不能使旧独立判断复活，统一上下文终端语义须先评审。
本轮仅文档与验收交接，无业务代码/迁移/调度/依赖/已有测试/任务启用变更；进度--check及diff检查，本规划精确CI另核对。将发布待评审规划PR，不作为已获批功能或已部署业务变更。Codex在Work直接维护仓库；未启动用户本地Plus CLI/API worker，无付费API调用/登录缓存上传。
69页面/API0.18.40/schema0022及14业务/2自身会话/6管理员/离线操作分计不变；36/44=82%，七模块100/100演示/100演示/100/89/60/17，七计划100/100/20/33/40/20/0，本轮增量0。公共样例只读/OIDC与提交关闭，无真实身份/授权/秘密；Render live API/schema未核验，真实浏览器/提供方/跨会话与内网验收未做。内网未安装，SSO/人员/OS/CPU/无Docker待定，VIN最后；SoftwareLifeCycle_20原文仍未取得。
下一步须审查并授权具体Impact切片；推荐仅A，无数据库迁移，不自动启用整个后续队列。
