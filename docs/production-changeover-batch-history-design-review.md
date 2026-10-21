# 生产换型与批次事实更正设计审查

2026-10-21，DeepSeek；实际基线 `e80598eb2c1ff05f349c39deaf53b43e9076c52e`（main，PR#95 证据回填后）。本修订承接 `docs/production-trace-correction-design-review.md`（PR#85/86）中「Changeover/Batch 自身更正账本随后另包」的约定，把审查范围从 Deployment actual 收敛到 `SoftwareChangeover` 与 `ProductionBatch` 两张表。它是设计审查，不是功能实现或真实验收完成。

本包只改本文件、DEVELOPMENT_STATUS.md、HANDOFF.md、docs/development-plan-progress.json；无后端、Migration、Seed、界面、测试、依赖、CI、身份、费用或提供方配置改动。公共只读，OIDC/真实提交关闭，内网未部署；API 0.18.48 / 唯一 head `0028_deployment_actual_guard` 不变。

## 1. 实际代码与业务边界

`models/production.py` 现有两张表（字段已核对到行）：

- `SoftwareChangeover`：`changeover_no`（唯一）、`deployment_id`、`authorization_id`、`from_release_id`、`to_release_id`、`status`（默认 `PLANNED`，服务层固定写 `COMPLETED`）、`changed_at`、`note`。无 version、无更正账本、无 ended 字段。
- `ProductionBatch`：`batch_no`（唯一）、`deployment_id`、`changeover_id`（可空）、`authorization_id`、`release_id`、`snapshot_id`、`status`（默认 `PLANNED`，服务层固定写 `ACTIVE`）、`started_at`、`ended_at`、`note`。无 version、无更正账本。

`services/production.py` 现况（已核对到行）：

- `_create_changeover`（302–377）：只有创建。`to_release_id` 由服务层强制等于 `deployment.expected_release_id`（343 行），调用方无法指定目标；`from_release_id` 必须是既有 Release 且不等于 `deployment.expected_release_id`（335 行）；`status` 固定 `COMPLETED`；`changed_at` 可显式或取 `now(utc)`。无更正分支、无 `request_id` 的版本/前驱语义（`request_id` 仅作 `EVT-CO-` 幂等去重）。
- `_create_batch`（393–487）：只有创建。锁顺序 `Deployment` → `lock_chain(AUTHORIZATION)`；`effective_actual` 判 `MATCH` 才允许；`release_id/snapshot_id` 强制等于 `deployment.expected_*`（451–452 行）；`status` 固定 `ACTIVE`；`started_at` 可显式或 `now`；**`ended_at` 无任何写入路径**（无「结束批次」命令）；`changeover_id` 须属于同 Deployment、`to_release_id==expected`、`status==COMPLETED`（438–444 行）。无更正分支。

`api/production.py` 现况：只有 `POST /deployments/{no}/changeovers` 与 `POST /deployments/{no}/batches` 两条创建端点（496、514 行），**无 changeover/batch 的更正端点**（无 PATCH/PUT 更正、无结束批次端点）。`ChangeoverCreate`/`BatchCreate`（72–85 行）只有创建字段，无 version/reason/前驱。

结论与 `production-trace-correction-design-review.md` §1 一致：更正记录「原录入有误或获得更准事实」，不撤销物理生产、不改许可链、不取消既有批次。Changeover 只更正 `from_release_id`/`changed_at`/`note`，不改 `deployment/authorization/to`；Batch 只更正 `started_at`/`ended_at`/`changeover`/`note`，不改 `deployment/authorization/release/snapshot`。换型仍须属于同一 Deployment 且目标软件一致、完成；`ended_at` 不得早于 `started_at`。

## 2. 旧库基线不是首次事实（Changeover/Batch 各自成立）

与 Deployment actual 同理，旧库中 `SoftwareChangeover` 与 `ProductionBatch` 的物理字段只是「升级时记录的当前值」，不能改名为「首次报告」。为保持与 Deployment 基线一致的三来源语义，两张表各自需要不可变基线：

- `changeover_baselines`：每张已存在 Changeover 一行，捕获原 `from_release_id`/`to_release_id`/`changed_at`/`note`/`status` 及捕获时间；来源区分 `LEGACY_CURRENT`/`IMPORTED_CURRENT`/`FIRST_RECORD`。
- `batch_baselines`：每张已存在 Batch 一行，捕获原 `release_id`/`snapshot_id`/`started_at`/`ended_at`/`changeover_id`/`note`/`status` 及捕获时间；来源同上。

关键差异（相对 Deployment）：

- Changeover/Batch 目前**根本没有「报告/更正」协议**，所以不存在 `FIRST_REPORT` 之外的 `_CORRECTED` 状态语义；基线来源在首次实现时只会有 `LEGACY_CURRENT`（迁移捕获）与 `IMPORTED_CURRENT`（样例导入）。真正 `FIRST_RECORD` 只有在将来新增带 `request_id` 的更正协议后才会出现。
- `changed_at`/`started_at`/`ended_at` 是「发生时间」，捕获时间不等于物理发生时间；`note` 是自由文本，不能作为事实判别依据。
- 部分字段矛盾（如 `ended_at < started_at`、`changeover_id` 指向他 Deployment）保留原值并显式 `UNRESOLVED`，不补猜、不推断。

迁移只捕获旧行当前值，不从审计拼造更正行/actor。旧 `EVT-CO-*`/`EVT-PB-*` 审计的 before/after 原样保留为旧历史与原请求证据，不自动升级为新账本；标记 `NOT_VERIFIED`。分页展示不等于全链验证。

## 3. 更正链、前驱与数据库约束（两张独立类型表）

选择两张类型明确的更正表 `changeover_corrections` / `batch_corrections`（另加上述两张基线表），可放 `models/production_history.py`（与现有 `DeploymentActualBaseline`/`DeploymentActualCorrection` 同文件，保持账本模型内聚）。不用只在 Python 校验的通用 JSON 账本。

每表字段对齐 `DeploymentActualCorrection` 的既有形态，但按各自可更正字段不同：

- `changeover_corrections`：`id=request_id`、`changeover_id` FK、`baseline_id` FK、`predecessor_id`（根 null）、正整数 `revision`、完整替代值 `from_release_id`/`changed_at`/`note`、`correction_reason`（trim 后 1..2000）、`actor_name`/`actor_principal_id`、`request_json`、`audit_event_no`、`recorded_at`。
- `batch_corrections`：`id=request_id`、`batch_id` FK、`baseline_id` FK、`predecessor_id`、`revision`、完整替代值 `started_at`/`ended_at`/`changeover_id`/`note`、`correction_reason`、`actor_*`、`request_json`、`audit_event_no`、`recorded_at`。

数据库要求（与 Deployment 相同，逐表复刻）：

- `(target_id, revision)` 唯一、每目标一个根（partial unique）、每前驱一个后继（partial unique），同目标复合 FK 排除跨 target 前驱；每表 `request_id` 与对应 `event_no` 唯一。
- `revision >= 1`；根 `revision=1`，后继 `=前驱+1`；FK/检查/trigger 拒绝跳号、自指、环、断链。
- `changeover_corrections`：`from_release_id` 非空（换型来源必须有）；`changed_at` 允许非空（更正可补填发生时间）。
- `batch_corrections`：`ended_at` 允许空（未结束）；若有 `ended_at` 与有效 `started_at`，加检查约束 `ended_at >= started_at`（跨基线与更正头的复合约束在 SQL 层做，见 §6 投影）。
- 索引 `(target_id, revision DESC)` 及前驱唯一索引；完整性异常返回 `UNRESOLVED`，不随意选最新值。

`request_id` 是命令族命名空间：Changeover 用 `EVT-CC-{hex}`、Batch 用 `EVT-BC-{hex}`（与既有 `EVT-CO-`/`EVT-PB-` 创建族、`EVT-DA-` 更正族区分）。回执必须核对固定族、target、action、正文、actor，不能用其他族事件证明成功。

## 4. 兼容写入、原重放与原子审计

当前 Changeover/Batch **没有**任何更正入口，所以「兼容收紧」不适用——不存在需要保留的旧 keyed 更正 body。真正需要收紧的是未来新增协议时的约束：

- 新 Changeover/Batch 更正 body 必须有 `request_id`、`expected_revision`、`predecessor_id`（根显式 null）、完整新值、`correction_reason`，禁止 extra 字段。
- 两个请求审核同一版本/前驱时，第一条成功，第二条 409；要再更正须重新读取并显式提交新判断。
- 无键覆盖一律 409（Changeover/Batch 从一开始就不允许无键更正）。

执行顺序（复用 `atomic_command`/`commit_with_audit`/actor 校验）：精确资源授权并解析可信 actor → 锁对应 Deployment（随后锁 Changeover/Batch 行）→ 查原命名空间证明 → 精确核对 target/正文/actor/action/result 并重放 → 新请求才验证当前版本/前驱、新值/关系/原因 → 业务/基线/更正/审计一次提交。缺失、损坏、legacy 非证明审计或账本/审计矛盾不能确认成功；已占用 key 返回冲突/原结果未知。

`flush`/审计/`commit` 任一失败必须全部回滚。不能禁用原审计约束适配新表。数据库 deferred 完整性检查验证事件存在且与 target/基线值一致。

`seed.py` 现有 551–582 行即使找到 `CO-0032`/`PB-1005-A` 仍**重新赋值**（`changeover.deployment_id = ...`、`batch.release_id = ...` 等覆盖既有字段）。下一实现必须把这两段改为只创建缺失行、既有记录/更正/审计不更新；验证连续 Seed 两次及发生更正后重跑，不能只比总数。本设计包不改 Seed，当前幂等性不受影响。

## 5. 锁与下游边界

现状锁图（已核对到行）：

- `_create_changeover` 只锁 `Deployment`（313–316 行），随后写 Changeover。
- `_create_batch` 先锁 `Deployment`（396–399），再 `lock_chain(AUTHORIZATION)`（404–406）持锁读配额、写 Batch。

事实更正只锁既有 `Deployment`（随后锁对应 Changeover/Batch 行），不新增许可链锁。范围授权仍用既有 `authorize_deployment`（`PRODUCTION_OPERATOR`）；不能为证明现场事实新增反向等待。Changeover/Batch 更正与新批次校验共享 `Deployment` 线性化锁。

新批次持锁读取有效 actual 判 `MATCH`，维持许可/配额检查；更正先提交则重验，批次先提交则原事实/审计保留。Batch 更正不制造新批次、不重耗配额；`ended_at` 更正不改变 `release/snapshot` 归属。Changeover 更正不改 `to_release_id` 或既有 Batch 的 `changeover_id` 原绑定；撤销许可后记录更准事实，不产生新生产许可。

## 6. 已定位消费者与读取契约

以下均为基线真实路径/符号（已核对到行），无虚构迁移路径。路径相对 `backend/app`，前端除外。

| 消费者 | 现状 | 要求（引入更正账本后） |
| --- | --- | --- |
| `services/production.py::_create_changeover` | 直接写 `from/to/changed_at/status`，`to==expected` | 原证明重放；`to` 仍绑定 expected；有效 `from`/时间用投影 |
| `services/production.py::_create_batch` | `effective_actual` 判 MATCH；`release/snapshot==expected`；`changeover` 须 COMPLETED | 批次软件仍绑 expected；换型有效性用有效投影；配额/锁不变 |
| `api/production_catalog.py::production_catalog`（changeovers/batches） | `recorded`/`from_release`/`changeover` 直接读物理列；`changeover_binding`/`batch_actual_binding`/`batch_authorization_binding` 用 effective actual | 换型/批次「记录值」与「有效值」分离；绑定校验用有效投影；`recorded_at` 用 `changed_at`/`started_at` 有效值 |
| `api/production.py::_deployment_detail` | `changeovers[]`/`batches[]` 直接读 `from/to/changed_at`、`release/snapshot/started_at/ended_at/note` | 有效投影 + 记录基线区分；缺口显式 UNRESOLVED；不加载全链 |
| `api/production.py::get_batch` | 读 `started_at/ended_at/note/release/snapshot`，`matches.*` 用 effective actual | 批次软件归属（release/snapshot）仍记录值不改；时间/换型用有效投影 |
| `api/dashboard.py::application_release_downstream_summary` | `batches` 用 `ProductionBatch.release_id` 原计数；`changeovers` 用原计数 | 原数量不改算成 effective；`batch_release_observations` 仍记录值比较（原数量契约） |
| `api/dashboard.py::application_release_downstream` | `changeovers`/`batches` 直接列出记录 | 列表保留原记录；如展示发生时间用有效值 |
| `api/manufacturing_views.py`、`api/issue_views.py`、`api/impact.py`、`api/distribution.py`、`api/search.py`、`api/distribution_catalog.py` | 仅引 `ProductionBatch`/`SoftwareChangeover` 原数量或 status | 原数量/status 不改算成 effective，不加载更正历史 |
| `seed.py` 551–582 | 覆盖赋值 | 改为 insert-only（§4） |
| `frontend/lib/production.ts`、`components/...`、`app/deployments/[id]/page.tsx` | 双语展示换型/批次记录 | 区分记录基线/当前更正/发生时间，正文原文转义，不新增发送入口 |

resolver 必须提供可 join/filter/count 的有界 SQL 子查询及批量详情投影，不能只给单对象 Python helper。按 target/revision 索引取唯一头，先在 SQL 应用有效值再过滤/分页/计数，禁止取一页后 Python 过滤。历史独立 cursor 分页默认 50、最大 200；主详情不加载全部更正链；缺表/断链/矛盾明确 `UNRESOLVED`，不回退基线伪装当前值。本轮尚未发布这些 GET/POST。

## 7. 升级、旧审计恢复与拒绝降级

编码前重新确认唯一 head；若仍 `0028_deployment_actual_guard`，Changeover/Batch 小包才新增 `0029` 并更新 `required_db_revision`/API 版本。升级捕获旧 changeover/batch 当前值为基线；不改旧发生时间/actor/审计，不按时间排序生成历史。事务/表写锁建立捕获与旧写者 guard 的单一切换点，无旧进程写入空窗；超时/回填失败全部回滚，重启无重复基线。

旧完整 `EVT-CO-*`/`EVT-PB-*` 请求/actor 仍返回原值，后来更正不让原重放变成当前版本冲突。缺 request/actor/after 或矛盾证据仅保留为旧历史，不升级为可确认回执；旧审计永不改删。测试必须先由真正旧 schema 路径写入多次再升级，不能只在新 schema 造假旧数据。

任何更正行或升级后 `FIRST_RECORD` 基线存在时拒绝 downgrade。只有纯导入基线、无新业务历史才可移除结构，旧值/版本/审计逐项不变。拒绝必须在拆 trigger/表前发生，失败后 head/数据/guard 仍在；没有 force/drop-history 后门。

## 8. 真实 PostgreSQL 最低矩阵

| 场景 | 必须证明 |
| --- | --- |
| 双连接不同 key 审核同一 Changeover/Batch 头；同 key 双连接 | 一个成功另一 409；同 key 一个事实/审计另一原结果；真实连接，不用 SQLite 替代锁 |
| 原 key 重放/换 target/正文/actor/跨族审计（`EVT-CC` vs `EVT-BC` vs `EVT-CO`/`EVT-PB`） | 原证明先于当前头；原结果不漂移；占用冲突全回滚、族不混淆 |
| Batch 更正与新 Batch、换型更正与关联创建，双顺序 | Deployment 锁线性化、配额不超、不死锁、不回写原事实；lock/statement timeout 内完成 |
| 首次/更正 flush、审计、commit 失败 | domain/baseline/correction/audit 全回滚，无孤儿首次证明 |
| 旧 SQL/无键覆盖及直接 INSERT/UPDATE/DELETE | 冻结后拒绝覆盖删除；跳号/分叉/跨 target 前驱拒绝；`ended_at >= started_at` 约束生效 |
| 真旧库：样例换型/批次/部分值/时间矛盾 | 当前值原样、来源准确，不伪造首次；原审计原字节/原结果重放，缺失矛盾显式 |
| 升级并发旧写者、超时/失败重启 | 无捕获/guard 窗口，失败全回滚，重跑唯一基线 |
| 空新历史/有更正/有新 FIRST_RECORD 降级 | 纯导入无损往返；新历史在拆对象前拒绝且 guard 有效 |
| 1/1000/10000 历史、同时间戳/逆序 UUID | 跨消费者一致、页长有界；EXPLAIN/索引和既有 SQL timeout 证据 |
| Seed 两次及更正后再 Seed | 原行/更正/旧审计不变且不重复，不仅比较数量 |
| 双语只读与原回执 | 来源/缺口/有效值明确、原因原文转义不翻译、精确审计链接、无新发送入口 |

## 9. 下一实施包的精确边界

`production-trace-correction-design-review.md` §9 已把 Deployment actual 拆成独立小包并完成（PR#87/89/91/93）。本设计把 Changeover/Batch 更正账本再拆成**两个**后续小包，避免一次勾完三类里程碑：

- **下一小包 `production-changeover-batch-history-backend-read`**：只新增两张基线表 + 两张更正表 + 迁移 `0029` + append-only trigger（冻结 Changeover `from/to/changed_at/note/status`、Batch `release/snapshot/started_at/ended_at/changeover/note/status` 物理列）；`effective_changeover`/`effective_batch` 只读投影；§6 全部消费者统一；不新增浏览器提交、不开放更正写入命令。
- **再下小包 `production-changeover-batch-correction-write`**（仅当人工批准后）：新增 `POST .../changeovers/{no}/correction`、`POST .../batches/{no}/correction` 与可能的「结束批次」命令，带 `request_id`/`expected_revision`/`predecessor_id`/`correction_reason` 完整协议；默认关闭浏览器提交、真实身份/内网验收。

本设计包不做任何后端/迁移/Seed/界面/测试改动，只固化上述边界与验收矩阵。业务 36/44=82% 不变；七模块 100/100演示/100演示/100/89/60/17；七计划 100/100/20/33/40/20/0。API 0.18.48 / schema 0028 不变。公共只读、OIDC/真实提交关闭、内网未部署。真实批准提供方、多用户/桌面/手机验收仍待定；不改身份、秘密、CI/调度、依赖或真实开关。
