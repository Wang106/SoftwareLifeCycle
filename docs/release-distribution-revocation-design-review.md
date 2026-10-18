# 发布、交付、分发与生产授权追加式撤销设计审查

审查日期：2026-10-18（Asia/Shanghai）。状态：设计完成，尚未实现后端、迁移或浏览器提交。

## 1. 结论与范围

本审查建议增加独立的 `release_chain_revocations` 追加式账本，终止一个精确 Release、DeliveryPackage 修订、Distribution 或 SoftwareAuthorization 对未来许可型写入的效力。原对象、原状态、文件清单、接收方、审批、审计、Deployment、Changeover 和 ProductionBatch 均保持原样；祖先撤销只产生派生的 `BLOCKED_BY_ANCESTOR`，不把后代伪装成已被逐项撤销，更不声称已经收回外发文件或回滚物理刷写。

首个实现包只支持永久 `REVOKE`，不支持原地恢复。需要重新发布时创建新的 Release UUID；需要重新交付、分发或授权时创建新的修订或业务编号。这样不会因撤销记录被“撤销”而复活旧许可，也不需要改写正式历史。错误撤销的补偿/恢复必须以后续独立设计明确授权，不能在本包用状态 UPDATE、删除撤销行或通用 `ACTIVE` 覆盖完成。

本包仅修改本设计、开发状态、进度元数据和交接记录。API 仍为 `0.18.44`，Alembic head 仍为 `0025_release_decision_supersession`；下文的 `0026`、路由和字段均是下一实现包提案，不是当前已交付能力。公共演示继续只读，OIDC、真实写入、公司内网部署和生产配置保持关闭。

## 2. 已核对事实与缺口

| 实际区域 | 当前事实 | 撤销实现要求 |
| --- | --- | --- |
| `models/core.py` / `Release` | `status` 是可变字符串；正式决策另存于 append-only ReleaseDecision | 不改 `Release.status` 表达撤销；撤销精确绑定 Release UUID、当时有效决策和 Snapshot |
| `models/distribution.py` | DeliveryPackage、Distribution、SoftwareAuthorization 都只有记录状态，没有撤销历史 | 原行不更新；撤销账本用真实 FK 精确指向一种目标 |
| `services/release_decision.py` | 当前决策由共享有界 resolver 选择 | Release 撤销绑定 resolver 当时的有效决策；撤销后同一 Release 不得追加新正式决策 |
| `services/distribution.py` | Delivery 锁 Release；Distribution 只锁 Package；Authorization 按 Release→Package→Distribution | 所有许可型写入统一检查自身及祖先撤销；Distribution 补齐 Release→Package 锁序 |
| `services/production.py` | Deployment 锁 Authorization；Batch 锁 Deployment→Authorization；只检查 Authorization `APPROVED` | Deployment/Batch 必须检查完整撤销链并与撤销写入线性化；actual report 等事实补录不被抹除 |
| `seed.py` | 演示 Seed 会形成 RELEASE→READY/ACKNOWLEDGED→APPROVED 链 | 不增加撤销演示，不更新旧对象；重复 Seed 仍需精确幂等 |
| 读取 API | catalog、detail、Dashboard、Passport、Search、production provenance/manufacturing 各自展示原 `status` | 统一增加 recorded status、self revocation、ancestor blockers 和 future-work eligibility，不能各端点自行猜测 |
| 审计 | 创建命令已使用 request UUID、可信 actor 和原子 AuditEvent | 撤销也必须业务行+原审计同事务；HTTP 成功或当前状态不能替代原审计恢复 |

全量检索确认当前没有交付、分发或授权状态更新 API；`seed.py` 是这些状态的主要赋值者。仍不能据此给原表直接加 UPDATE trigger：未来授权批准历史尚未建模，且旧库存在既有状态。首包保护新增撤销账本，并用数据库插入 guard 阻止旧程序越过撤销继续创建下游记录；原目标表完整 append-only 化另行审查。

## 3. 精确业务语义

### 3.1 四种终端目标

| 目标 | 自身撤销后的未来阻断 | 不受影响的历史事实 | 合法替代 |
| --- | --- | --- | --- |
| Release UUID | 新 Snapshot、正式 ReleaseDecision、Delivery、Distribution、Authorization、Deployment、Batch | 原决策、审批、测试、Impact、既有下游及实际软件报告 | 新 Release UUID |
| DeliveryPackage UUID（含修订） | 从该包新建 Distribution、Authorization、Deployment、Batch | 原包文件、已存在 Distribution/Authorization/生产历史 | 新修订或新 package number，产生新 UUID |
| Distribution UUID | 从该记录新建 Authorization、Deployment、Batch | 已发送/签收字段、既有授权与生产历史 | 新 Distribution UUID |
| SoftwareAuthorization UUID | 新 Deployment、Batch | 原授权正文、既有 Deployment/Changeover/Batch、实际软件报告 | 新 Authorization UUID |

撤销不是 `HOLD`、`DRAFT`、`REJECTED`、`CANCELLED` 或 `MISMATCH` 的别名。原 `status` 必须以 `recorded_status` 展示；派生治理状态另名为 `governance_state`：`ACTIVE`、`REVOKED` 或 `BLOCKED_BY_ANCESTOR`。同一对象只能有一个终端撤销，后续相同 request_id 返回原操作，不同 request_id 再撤销返回 409。

### 3.2 级联只阻断未来，不改写过去

Release 撤销后，其已有 Delivery/Distribution/Authorization 仍是历史对象，且各自没有被自动逐项撤销。读取返回阻断来源列表，例如 `[{kind: "RELEASE", revocation_id: ...}]`；只有显式撤销后代时，后代才同时拥有 `self_revocation`。统计必须分别计算记录总数、自身撤销数和祖先阻断数，不能把阻断后代计作新增撤销事件。

Deployment 创建和 ProductionBatch 创建属于许可型写入，必须 fail closed。`report_actual` 及其更正是在记录已经发生的物理事实，即使授权后来撤销也继续允许，但结果必须显示当时/当前治理阻断信息，不能反推操作获准。Changeover 当前接口记录 `COMPLETED` 的物理事实而非授予许可，首包继续允许补录；它不解除撤销，也不能使 Batch 通过。是否把未来 Changeover 拆成“操作许可”和“事实报告”属于后续生产更正包。

Release 撤销后，ApprovalAction、DVP/Test、Impact 和审计仍可继续追加证据；唯有新 Snapshot 和正式 ReleaseDecision 被阻断，避免相同 Release UUID 被普通新决策无意复活。已有原请求重放仍只返回原结果，不因后来撤销改写成失败。

## 4. 存储方案比较与推荐

| 方案 | 优点 | 不接受的风险 |
| --- | --- | --- |
| 原表直接写 `REVOKED` | 查询简单 | 改写历史、丢失原状态/actor/reason，无法原请求恢复，祖先级联会伪造多个撤销 |
| 四张独立撤销表 | 每张可强 FK | 服务、审计、幂等、resolver 和测试重复，跨类型 request UUID 冲突难统一 |
| 一张表加裸 `target_type/target_id` | 写入统一 | 多态 target_id 没有真实 FK，孤儿或错类型只能依赖应用层 |
| 一张表加四个 nullable FK（推荐） | 一个请求命名空间和 resolver；每类目标保留真实 FK；可统一分页、审计和 downgrade | 需要严格 XOR check、部分唯一索引及上下文验证 trigger |

拟议 `0026_release_chain_revocations`（实现前重新核对唯一 head）新增：

- `id`：UUID 主键，等于 request_id；`revocation_no`：唯一业务编号。
- `target_kind`：`RELEASE | DELIVERY_PACKAGE | DISTRIBUTION | SOFTWARE_AUTHORIZATION`。
- 四个 nullable 目标 FK；使用 `num_nonnull(...) = 1`，并校验非空列与 `target_kind` 精确对应。
- `release_id`、`snapshot_id`、`release_decision_id`：冻结撤销时的完整正式上下文；Release 必须存在有效决策，Snapshot 必须属于 Release，Decision 必须是当时 resolver 选中的记录。下游目标还必须与其真实父链一致。
- `reason`、`revoked_by`、`revoked_at`；reason trim 后 1..4000。可信主体的完整字段仍存于原子 AuditEvent，声明名称不能冒充认证主体。
- 四个 `WHERE target_*_id IS NOT NULL` 的唯一索引，保证每个精确目标最多一个撤销；Release/context 和时间排序索引用于有界读取。
- UPDATE/DELETE 拒绝 trigger。FK 使用默认 RESTRICT，不允许删除目标来级联删除撤销。
- `BEFORE INSERT` 上下文 trigger 复核目标种类、真实父链、Release/Snapshot/Decision，防止绕过服务写错上下文；权限仍由服务处理。

同时增加数据库 permission-bearing insert guard，至少覆盖 `release_snapshots`、`release_decisions`、`delivery_packages`、`distributions`、`software_authorizations`、`deployments` 和 `production_batches`。guard 以实际父链查询撤销，不修改旧记录；因此迁移后尚未滚动完成的旧应用也不能越过已提交撤销继续产生许可型记录。Actual report 的 UPDATE 不在该 guard 中。

## 5. 写入、锁序、幂等和原子审计

建议四个明确路由，共享一个 service，不使用客户端可选 target URL：

- `POST /api/v1/releases/{release_id}/revocations`
- `POST /api/v1/deliveries/{package_id}/revocations`
- `POST /api/v1/distributions/{distribution_id}/revocations`
- `POST /api/v1/authorizations/{authorization_id}/revocations`

正文固定 `request_id`、`revocation_no`、`reason`、声明 actor；路径决定 target kind/id，额外字段拒绝。Release/Delivery/Distribution 撤销分别复用 `DISTRIBUTION_AUTHORITY` 的精确 Release/Package scope；Authorization 撤销使用 `PRODUCTION_AUTHORITY` 的精确项目及分发双重 scope。PLATFORM_ADMIN 仍只是现有显式全局授权，不产生绕过审计的特殊路径。

统一锁序为 Release→DeliveryPackage→Distribution→SoftwareAuthorization，按目标取必要前缀并持有到 commit。现有许可写入需同步：

- Delivery 保持先锁 Release；
- Distribution 改为先解析并锁 Release，再锁 Package；
- Authorization 保持 Release→Package→Distribution；
- Deployment 先只读解析 Authorization 的 Release，锁 Release 后重读锁 Authorization，再锁 Site→Line；
- Batch 先只读解析 Deployment 的 Release，锁 Release→Deployment→Authorization 后再检查 quota；
- Release 撤销只需 Release 和当前有效 Decision；下游撤销按上述父链锁到目标。

锁内先查 request_id 及 `EVT-RCR-{request_id}`。原请求存在时校验 target、revocation_no、完整规范正文和可信 actor，匹配则返回原操作，即使后来出现更多下游事实；不匹配返回 409。新请求在锁内重新解析有效决策、目标父链、自身撤销和祖先阻断，再插入撤销及 AuditEvent。审计 action 分别为 `RELEASE_REVOKED`、`DELIVERY_REVOKED`、`DISTRIBUTION_REVOKED`、`AUTHORIZATION_REVOKED`，payload 绑定完整父链、原 recorded status、Snapshot/Decision、reason、request 和 actor。任一 flush/trigger/审计/commit 失败必须全部回滚。

成功新建返回 201，精确重放返回 200。原审计恢复只能 GET `EVT-RCR-{request_id}` 并逐字段投影原操作；不能用当前 `governance_state`、HTTP 200、对象存在或后来子记录推断原撤销成功。浏览器协议、unknown 锁定、手动导出/只读恢复是后续独立包，默认关闭。

## 6. 统一读取与完整消费者

共享 resolver 接受一个或一页精确对象，返回 `recorded_status`、`self_revocation`、`ancestor_revocations`、`governance_state` 和 `eligible_for_new_work`。使用 set-based CTE/批量 join，不为目录每行执行四次相关查询，不加载某 Release 的全部历史到 Python。

下一实现必须覆盖：

- 写者：`services/snapshot.py`、`services/approval.py`、`services/distribution.py`、`services/production.py`。
- 详情/目录：`api/distribution.py`、`distribution_catalog.py`、`dashboard.py` 的 downstream/detail/summary。
- 发布视图：`api/asr_passport.py`、`asr_policy.py`、应用 Release 详情与 Search。
- 生产来源：`api/production.py`、`production_catalog.py`、`manufacturing_views.py`；原 provenance 仍列原链，另显示当前阻断，绝不重写原来源。
- 审计：`api/activity.py` 和 audit catalog 可导航精确撤销；原创建事件仍独立存在。
- 前端：Delivery、Distribution、Authorization、ASR Passport、应用 Release、Deployment、Batch 的双语只读标签；不得出现公共提交按钮。

旧 GET 继续返回兼容 `status` 原值，同时新增明确字段；不能把 `status` 静默替换成派生状态。过滤器分别支持 `recorded_status` 与 `governance_state`，旧 `status` 参数保持原含义。Dashboard 计数与 Passport 历史保留所有记录，另给 blocked/revoked 数，不隐藏或删除行。

## 7. 升级、降级、Seed 与发布顺序

升级从真实 `0025_release_decision_supersession` 旧库执行，先建表/约束/索引/trigger，再安装旧写者 guard；旧对象及 AuditEvent 必须逐字段、计数和摘要不变，不回填“未撤销”行。部署顺序为暂停写入→迁移→验证 required revision/guard→启动新程序；不能假设健康检查会自动停止旧实例。

空撤销表允许安全降级到 0025。只要存在任意撤销行，downgrade 必须在同一 PostgreSQL 事务中拒绝，保留 revision、表、trigger、guard、目标和审计全部不变；不得删除撤销后降级、把目标 status 改成 `REVOKED` 或复制下游记录。SQLite 不能替代 FK、partial unique、trigger、锁和事务 DDL 验收。

Seed 不创建撤销、不修补原对象，也不因祖先阻断删除或跳过既有演示历史；重复执行继续精确验证原链。测试可使用独立 fixture 创建撤销，不能污染固定 Demo。API 版本拟升至 `0.18.45`，required revision 拟升至 `0026_release_chain_revocations`，以实际实现时 main 为准。

## 8. 真实 PostgreSQL 与回归矩阵

| 类别 | 必测场景 | 必须证明 |
| --- | --- | --- |
| 同目标并发 | 两个 request 撤销同 Release/Package/Distribution/Authorization | 仅一行+一审计；另一请求 409，无残片 |
| 撤销/下游竞争 | Release vs Delivery/Distribution/Authorization/Deployment/Batch；各父级 vs 直接子写入 | 两独立连接和同步屏障；提交顺序决定“子先成功保留事实”或“撤销先成功后子被拒绝” |
| quota 竞争 | Authorization 撤销与最后一个 Batch 并发 | Release→Deployment→Authorization 锁序无死锁；不能越过 batch_limit 或撤销 |
| 原请求重放 | 撤销后出现子事实、祖先/后代撤销，再重放原 ID；同 ID 换 target/body/actor | 只返回原撤销；换内容冲突，不新增记录 |
| 原子故障 | 撤销 flush 后、审计 flush 后、commit 失败、连接取消 | 撤销和审计同时回滚，旧写者 guard 不误判未提交行 |
| DB 防护 | UPDATE/DELETE 撤销；XOR/空 reason/错 context；迁移后旧程序直接 INSERT | 真 PG 直接 SQL 拒绝；服务和数据库双层 fail closed |
| 事实补录 | 授权撤销后 actual report/更正及 Changeover；新 Deployment/Batch | 事实可记录且显示阻断；新许可型写入拒绝，不把事实称为授权 |
| 旧库升级 | 0025 含多决策、多个 package revision、分发/授权/部署/批次及原审计 | 零回填、逐字段不变、guard 生效、唯一新 head |
| 降级 | 空表 round-trip；四类任一撤销后 downgrade | 空表无损；有记录时整事务拒绝且 schema/data/trigger/audit 未变化 |
| 全消费者 | 详情、目录、Search、Dashboard、Passport、生产来源、制造视图、Activity | 原 status/history 不消失；所有端点对同一阻断链一致 |
| 长历史有界 | 10,000+ Release/包/分发/授权与混合撤销，终端在分页外 | 页面查询/结果随页大小有界，EXPLAIN 使用索引，无 N+1 或 Python 全历史 materialization |
| Seed | 首次、重复、目标碰撞、存在撤销后重复 Seed | 固定数据幂等且不更新/删除撤销或历史 |

所有 PostgreSQL 模块必须在 CI 报告为实际执行、零 skip；完整后端、前端、Next/OpenNext 和 migration 往返同时成功。模拟 HTTP、SQLite 或文档检查不代替真实 PG。

## 9. 下一实现包精确范围

建议下一包 `release-chain-revocation-backend-read`：实现拟议 0026、四类后台撤销、统一 resolver、未来写入阻断、双语只读展示及真实 PG 测试；不开放浏览器提交，也不实现恢复或生产事实更正。

主要路径：

- 新增 `backend/app/models/revocation.py`、`backend/app/services/release_chain_revocation.py`、`backend/app/api/revocations.py`、`backend/alembic/versions/0026_release_chain_revocations.py`。
- 修改模型导出、`main.py`、`core/config.py`、`write_contracts.py`，以及第 6 节列出的写者和消费者。
- 新增 backend service/read/真实 PostgreSQL/migration 测试；更新 API/DATABASE 文档。
- 前端仅增加现有详情和目录的中英文只读治理状态、阻断来源及撤销详情链接；不增加发送表单、环境变量或代理路由。
- 更新 DEVELOPMENT_STATUS、HANDOFF 和进度元数据；业务百分比在真实身份/浏览器验收前保持不变。

该实现完成后再单独划定默认关闭的浏览器撤销协议与原审计恢复；再后处理生产事实更正、真实身份/多用户浏览器、内网和运营迁移，VIN 最后。

## 10. 当前进度

本设计没有业务验收增量：仍为 36/44（82%）；七模块仍为 100/100演示/100演示/100/89/60/17；七计划仍为 100/100/20/33/40/20/0。文档、CI 或 Cloudflare 构建不能替代批准身份提供方的真实多用户操作与公司环境验收。
