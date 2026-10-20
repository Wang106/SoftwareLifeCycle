# 生产追溯（Deployment / Changeover / Batch）事实更正设计审查

审查日期：2026-10-21（UTC+8）。状态：设计完成，尚未实现后端、迁移或浏览器协议。本包只产出设计审查与状态/交接/进度更新，不修改任何后端、迁移、Seed、界面、依赖、CI、调度、身份、密钥或提供方配置。

## 1. 结论与包边界

生产追溯链为 `Delivery → Distribution → Authorization → Deployment → Changeover → Batch`。本审查只定义其中三段的**追加式生产事实更正**边界：

- `Deployment`：实际刷写软件（actual release/snapshot）的更正；
- `SoftwareChangeover`：换型记录的更正；
- `ProductionBatch`：批次记录（起止时间、绑定换型、note）的更正。

核心结论：现有 `Deployment.actual` 已有一个**原地覆盖**式内联更正（`expected_version` + `correction_reason`，直接 UPDATE `deployments` 的 actual_* 字段并 `actual_version += 1`），它不是追加式，业务行被覆盖、只有审计 `before/after` 保留旧值；`Changeover` 与 `Batch` 则完全没有更正/撤销命令。本审查推荐把三段的更正统一为**追加式更正账本**：旧业务行不原地改写，新增更正行显式引用被更正记录并携带独立更正原因，读取统一投影"原记录值 + 当前更正值 + 是否被后续更正"。

明确不包含：

- 不改写 `release_chain_revocations` 的撤销语义（撤销链阻断的是"许可链"，本包是"已发生事实"的更正，二者正交）。
- 不撤销已发生的物理事实；更正记录的是"原录入有误/后来更准确"，不是"这批货不存在了"。
- 不新增浏览器提交协议、不开放真实提交、不配置身份/权限/秘密。
- 不把"更正"当作生产授权、量产批准或公司上线。

公共样例继续只读，OIDC、真实写入与内网部署保持关闭。

## 2. 当前事实与缺口

### 2.1 现状

- `Deployment`（`backend/app/models/production.py`）：`expected_release_id/snapshot_id`（创建时来自 Authorization）+ `actual_release_id/snapshot_id`（可空）+ `actual_version`（默认 0，每次 actual 报告 +1）+ `status`（`PENDING`/`MATCH`/`MISMATCH`）+ `deployed_at`。
- `SoftwareChangeover`：`from_release_id`/`to_release_id` + `status`（默认 `COMPLETED`）+ `changed_at` + `note`；创建时即写死 `to_release_id = deployment.expected_release_id`，无更正。
- `ProductionBatch`：`release_id`/`snapshot_id`（创建时取 deployment.expected）+ `changeover_id`（可空）+ `status`（默认 `ACTIVE`）+ `started_at`/`ended_at`（ended_at 目前无写入路径）+ `note`。

### 2.2 现有写入行为（`backend/app/services/production.py`）

- `report_actual`：支持 `request_id` 幂等 + `expected_version` 乐观并发 + `correction_reason`；首次报告 action=`ACTUAL_REPORTED`，后续覆盖 action=`ACTUAL_CORRECTED`。**关键缺口**：这是对同一 `deployments` 行的原地 UPDATE，`actual_version += 1`，旧 actual release/snapshot 值仅存于审计 `before`，业务行不可再查询历史实际值；且 `changeover_id`/批次对 `deployment.actual_*` 的既有绑定只比较当前值，一旦 actual 被更正，先前创建的批次与换型的"实际绑定"语义会漂移。
- `create_changeover` / `create_batch`：只有创建，无更正；`write_contracts.py` 中两者 `known_gap` 明确写 "no correction/revocation command"。
- 三张表均无 UPDATE/DELETE 拒绝 trigger（仅 `audit_events` 与 `release_decisions` 有 append-only trigger）。

### 2.3 缺口清单

1. `Deployment.actual` 的更正非追加式，历史实际值不可结构化查询；
2. `Changeover`、`Batch` 无任何更正命令；
3. `Batch.ended_at` 无写入路径（批次结束无法结构化记录）；
4. 三表无 append-only 防护，任何具备 DB 写入的代码路径都可原地改历史；
5. 消费者各自读取"当前"值（`production_catalog.observed`、`deployment_detail.actual`、`batch_detail` 的 actual 绑定），没有统一的"原值 + 更正 + 是否再被更正"投影，存在相互矛盾风险。

## 3. 精确业务语义

### 3.1 Deployment actual 更正

更正必须是**追加式**，不覆盖原 `deployments.actual_*`：

1. 使用全新 request UUID，引用被更正 Deployment 的精确 UUID；
2. 保留原 `actual_release_id/snapshot_id/actual_version/deployed_at/status` 作为"原记录事实"；
3. 新更正行携带新的 actual release/snapshot、独立的 `deployed_at`、非空 `correction_reason`（1..2000）、可信 actor 与完整规范请求；
4. 不推断"测试通过/物理刷写/量产批准"；actual 仍只是对现场软件的记录声明；
5. 只允许更正"当前生效"的 actual，不允许并发双写覆盖；旧更正被再次更正时，旧更正仍作为历史保留。

### 3.2 Changeover 更正

1. 引用被更正 Changeover 的精确 UUID；
2. 可更正 `from_release_id`、`changed_at`、`note`（`to_release_id` 仍绑定原 deployment.expected，不随更正漂移）；
3. 携带非空 `correction_reason`；
4. 原 `status=COMPLETED` 只表示"记录完成"，更正不制造"未完成"中间态，不推断换型是否真的物理发生。

### 3.3 Batch 更正

1. 引用被更正 Batch 的精确 UUID；
2. 可更正 `started_at`/`ended_at`（补齐缺失的结束时间）、`changeover_id`、`note`；
3. `release_id/snapshot_id` 保持创建时绑定的 deployment.expected，不随 actual 更正漂移；如需改批次软件归属，须显式更正并留痕；
4. 携带非空 `correction_reason`。

### 3.4 明确不包含

- 不把 `HOLD`/`REVOKE`/`CANCEL` 当作生产事实更正码；撤销链用 `release_chain_revocations` 独立处理许可链。
- 不删除/不物理回滚已提交的 Deployment/Changeover/Batch 行。
- 不修改 Authorization/Distribution/Delivery 记录。
- 不新增身份、权限、秘密或真实开关。

## 4. 推荐存储与迁移

下一实现包拟使用唯一迁移 `0027_production_trace_correction`，实际编码前必须确认 Alembic head 仍为 `0026_release_chain_revocation`（当前 API 0.18.45 / schema 0026）。

推荐新增三张 append-only 更正账本（或一张带 discriminant 的通用账本——见 §4.2）：

- `deployment_actual_corrections`：`id`(pk)、`deployment_id`(FK)、`actual_release_id`、`actual_snapshot_id`、`deployed_at`、`correction_reason`、`actor_*`、`request_id`、`created_at`；
- `changeover_corrections`：`id`、`changeover_id`、`from_release_id`、`changed_at`、`note`、`correction_reason`、`actor_*`、`request_id`、`created_at`；
- `batch_corrections`：`id`、`batch_id`、`started_at`、`ended_at`、`changeover_id`、`note`、`correction_reason`、`actor_*`、`request_id`、`created_at`。

约束要求：

- 每张账本均加 UPDATE/DELETE 拒绝 trigger（与 `release_decisions` 同款），保证追加式；
- 更正行与被更正行的 FK 精确绑定（deployment_id → deployments.id 等）；
- `correction_reason` trim 后长度 1..2000，非空；
- `request_id` 唯一，幂等重放按 request UUID 查原行与对应审计；
- 每张表建立 `(target_id, created_at, id)` 索引，供"当前生效更正"有界查询；
- downgrade 仅当不存在任何更正行时才允许删除，存在历史必须拒绝降级。

### 4.2 单表 vs 三表

倾向**三张独立账本**：三者字段不同（Deployment 绑定 actual release/snapshot、Changeover 绑定 from/changed_at、Batch 绑定起止时间与换型），单表 discriminant 会引入大量可空列与 XOR 校验，降低可读性与类型安全。三表各自清晰、迁移边界明确、测试矩阵可独立。代价是三套 trigger/服务/测试，但可复用既有 `retry_result`/`atomic_command`/`commit_with_audit` 基础设施。

### 4.3 迁移与 Seed

- 现有 `seed.py` 的 `EVT-0009 BATCH STARTED` 等演示审计不涉及新账本，保持 insert-only，不因新表出现而修补旧行。
- 真实 PG 必须覆盖：并发双更正同一 target、原子回滚（业务行 + 审计同事务）、旧库升级无改写、有更正历史拒绝降级、长历史有界查询、EXPLAIN 形状固定。

## 5. 写入、锁、幂等和原子审计

优先扩展现有 `POST /api/v1/deployments/{deployment_no}/actual` 的语义，使其从"原地覆盖"改为"追加更正"，并新增 Changeover/Batch 的更正端点，而不是复制第二套权限与锁逻辑。

统一处理顺序：

1. 先执行既有 `PRODUCTION_OPERATOR` 精确授权并解析可信 actor；
2. 按现有锁序（Deployment 行锁 → 必要时 Authorization 链锁）加锁，不引入反向锁序；
3. 锁内先按 request UUID 查原更正行与对应审计；重放必须匹配 target、字段、correction_reason、actor、原审计全部绑定，同 ID 换正文返回 409；
4. 新请求验证 target 存在、字段合法、correction_reason 非空；
5. 插入更正行 + 原子 AuditEvent，任一 flush/审计/commit 失败全部回滚。

审计动作建议：

- `ACTUAL_CORRECTED`（Deployment，追加行，保留旧行不动）、`CHANGEOVER_CORRECTED`、`BATCH_CORRECTED`；
- 现有 `ACTUAL_REPORTED`/`CHANGEOVER COMPLETED`/`BATCH STARTED` 审计不修改；
- 更正审计 payload 至少绑定：target 原值、新值、correction_reason、request、principal/display/declared/source。

关键：现有 `report_actual` 的原地 UPDATE 路径需保留兼容（legacy no-key 调用仍可覆盖），但**新** keyed 更正必须走追加账本；需明确区分"首次 actual 报告"（仍写 `deployments.actual_*`）与"后续更正"（追加 correction 行，`deployments.actual_*` 保留首次值不变，或改为"当前生效值"由 resolver 派生）。设计上推荐：`deployments.actual_*` 保留**首次**报告值不变，后续更正只追加账本，统一 resolver 返回"首次值 + 当前更正链 + 最新生效值"，避免原地覆盖导致历史丢失。

## 6. 共享解析与消费者

必须先建立有界 SQL resolver，再让所有"当前实际值"消费者使用它：

| 消费者 | 实现要求 |
| --- | --- |
| `production.py` `report_actual`/新更正端点 | 唯一写者；首次报告写 actual，更正只追加账本 |
| `production_catalog.observed` / `deployment_detail.actual` | 显示首次值 + 当前更正值 + `corrected` 标记，不隐藏历史 |
| `batch_detail` 的 `deployed_release/deployed_snapshot` | 用"当前生效" actual（resolver 派生）比较，但显式标注是派生值 |
| `deployment_profile` / `deployment_provenance` | 保留原来源，新增更正关系展示，不用今天的更正重写原来源 |
| `activity`/审计导航 | 旧新审计均可独立导航，不从 resolver 推断原操作成功 |

resolver 不加载某 target 全部历史到 Python；PostgreSQL 增长测试覆盖长更正链，在既有 CI statement timeout 内保持固定形状查询。

## 7. 与下游并发的一致性边界

Deployment 行锁是生产事实更正与批次/换型校验的线性化边界：

- actual 更正先提交：后续 `create_batch` 的 `deployment.status != "MATCH"` 判断基于"当前生效"值，必须重新校验；
- 批次/换型先提交：保留创建时绑定的原 expected 审计证据，后来 actual 更正不删除或伪造回滚；
- 两个更正竞争同一 target：最多一个成功，另一个 409；
- 原更正请求被再次更正后重放：只返回原结果，不改变当前 resolver；
- 不得在本包给既有批次/换型行增加"revoked/effective"推断字段；那些是撤销链/许可链语义，另包处理。

## 8. 实现拆分与验收矩阵

下一代码包只做后端、迁移、共享读取和双语只读历史展示；不同时开放浏览器提交。建议路径：

- `backend/app/models/production.py`（三张更正账本模型）
- `backend/alembic/versions/0027_production_trace_correction.py`
- `backend/app/services/production.py`（首次报告保留 + 追加更正 + 共享 resolver）
- `backend/app/api/production.py`（Changeover/Batch 更正端点）
- `backend/app/api/production_catalog.py`、`batch_detail`、`deployment_detail/profile/provenance`（统一投影）
- `backend/app/write_contracts.py`（补充更正命令契约）
- 对应后端、真实 PostgreSQL、迁移和前端只读历史回归

最低验收矩阵：首次 actual 报告不变；追加更正不覆盖原 actual；Changeover/Batch 更正端点；旧/跨 target/空 reason/自指拒绝；同 ID 原字节重放与正文冲突；业务+审计原子回滚；三表 UPDATE/DELETE trigger；旧库升级无改写；有更正历史拒绝降级；actual 更正与批次提交两种顺序；所有消费者一致；长历史有界 SQL；Seed 幂等；中英文只读更正关系。

后续再分别划定默认关闭的受控浏览器更正协议和原审计恢复。只有批准提供方的多用户正反例、并发和真实浏览器验收完成后，计划 6 的"生产事实更正"里程碑才可完成；设计、模拟 HTTP 或只读页面均不提升当前百分比。

## 9. 当前进度与下一步

本审查不改变业务验收：仍为 36/44（82%）；七模块为 100/100演示/100演示/100/89/60/17；七计划为 100/100/20/33/40/20/0。

下一包：实现 `production-trace-correction-backend-read`（后端 + 迁移 + 追加式更正账本 + 统一只读投影），完成后再单独设计默认关闭的浏览器提交/原审计恢复。其后依次处理真实身份/浏览器验收、内网部署和运营迁移；VIN 最后。
