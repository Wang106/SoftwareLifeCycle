# ReleaseDecision 追加式历史替代设计审查

审查日期：2026-10-17（UTC）。状态：设计完成，尚未实现后端、迁移或浏览器协议。

## 1. 结论与包边界

下一实现切片只为正式 `ReleaseDecision` 增加显式 `SUPERSEDE`：新记录精确引用当前正式决策，原决策、原审批流程和原审计保持不变。它不是对 `ApprovalStep` 或 `ApprovalAction` 的改写，也不是撤销、取消发布、撤回交付、撤回分发、撤回生产授权或物理刷写回滚。

本审查明确不把 `WITHDRAW` 放入同一迁移。撤销一个 `RELEASE` 决策需要分别定义既有 DeliveryPackage、Distribution、SoftwareAuthorization、Deployment、Changeover 和 ProductionBatch 的状态与追溯政策；这属于计划 6 的“发布/分发/授权更正撤销”和“生产更正”后续切片。当前替代只改变后续命令选择的有效正式决策，不追溯删除、失效或重写已经提交的下游事实。

公共样例继续只读，OIDC、真实写入和内网部署保持关闭。本包不选择身份提供方、不创建身份/权限/秘密，也不修改 Render、Cloudflare、Actions 或数据库配置。

## 2. 当前事实与缺口

当前 `release_decisions` 记录 `decision_no`、Release、冻结 Snapshot、ApprovalRequest、声明的 readiness、`decision`、可信操作者和说明。普通写入已经：

- 先锁 Release、再锁 ApprovalRequest，与交付/授权使用相同锁序；
- 要求 ApprovalRequest 为 `APPROVED`、目标为同一 Release、Snapshot 属于该 Release；
- 用 request UUID 作为行 ID，并将规范请求、可信 actor 和结果写入同事务审计；
- 允许同一 Release 追加多个决策，读取和新交付通常按 `decided_at`/ID 选择最新记录。

缺口是：记录间没有显式前驱关系，无法区分“新 Snapshot 的普通正式决策”和“对当前决策的更正”；数据库也没有 ReleaseDecision 的 UPDATE/DELETE append-only trigger。当前消费者各自实现“最新”排序，若只在一个服务里排除旧记录，会造成护照、演示状态、交付校验和来源追溯互相矛盾。

## 3. 精确业务语义

### 3.1 普通决策与替代

`DECIDE` 保持现有语义：经一个已批准且绑定精确冻结 Snapshot 的 ApprovalRequest，追加新的正式决策。新 Snapshot 的正式决策继续走 `DECIDE`，不伪装成更正。

`SUPERSEDE` 必须：

1. 使用全新 request UUID 和全新 `decision_no`；
2. 引用该 Release 当前全局有效决策的精确 UUID；
3. 与前驱使用同一 Release 和同一冻结 Snapshot；
4. 使用一个状态为 `APPROVED`、目标和 Snapshot 都匹配的 ApprovalRequest；它可以是重新评审产生的新 ApprovalRequest，不能借用其他 Release/Snapshot 的批准；
5. 提供独立、非空、最多 4000 字符的 `correction_reason`；
6. 完整给出新的 decision/readiness/notes，而不是补丁。

只允许替代当前全局有效决策，而不是任意历史叶节点。否则更正旧 Snapshot 会因“最新时间”突然重新成为未来交付依据。并发时只有一个请求能替代同一前驱；失败请求不得留下业务行或审计残片。

原请求重放是例外：已经成功的 request UUID 在后来又被替代后，仍返回那次原操作和原审计，不重新要求其前驱仍为当前，也不恢复其当前效力。当前认证和权限仍必须通过。

### 3.2 明确不包含的语义

- 不修改 ApprovalRequest、ApprovalStep 或 ApprovalAction；错误的审批流程需要新流程和新正式决策，旧动作仍是历史事实。
- 不允许 `WITHDRAW`、空 decision、删除、原地 UPDATE 或把 `HOLD` 当作通用撤销码。
- 不把声明的 `readiness_status` 当成重新计算的 Readiness；它仍是原正式决策的声明字段。
- 不使已有交付、分发、授权、部署、换型或批次自动失效；它们继续保留创建时审计绑定的原决策。
- 不把替代后的 `RELEASE` 等同于公司上线批准，也不授予当前用户额外权限。

## 4. 推荐存储与迁移

下一实现包拟使用唯一迁移 `0025_release_decision_supersession`，实际编码前必须再次确认 Alembic head 仍为 `0024_release_customer_scope`。

在 `release_decisions` 增加 nullable `supersedes_id` 和 `correction_reason`：

- 两列必须同时为空或同时非空；更正原因 trim 后长度 1..4000；
- `supersedes_id != id`；
- 通过 `(supersedes_id, release_id, snapshot_id)` 到同表 `(id, release_id, snapshot_id)` 的复合外键保证同上下文；
- `supersedes_id` 唯一，保证一个前驱只有一个显式替代；
- 增加 `(release_id, decided_at, id)` 及前驱查询所需索引；
- 增加 UPDATE/DELETE 拒绝 trigger，使正式决策与审计一样追加式；旧行不回填前驱或更正原因；
- downgrade 只有在不存在任何 `supersedes_id` 时才允许删除这些语义列和约束，存在替代历史必须拒绝降级。

迁移不能靠 SQL `CHECK` 的 UNKNOWN 放行；所有 paired/null 分支必须显式写 `IS NULL`/`IS NOT NULL`。SQLite 单元测试只能验证服务语义，复合外键、唯一竞争、trigger、升级/降级和长历史查询必须在隔离 PostgreSQL 中验收。

现有 demo seed 对已存在 `RD-0081` 赋值。启用 append-only trigger 前，下一实现包必须把它改成“缺失则插入、存在则逐字段验证完全相同、碰撞则失败”，不能继续把旧正式决策修补成期望值。独立 evidence seed 已是 insert-only，保持不变。

## 5. 写入、锁、幂等和原子审计

优先扩展现有 `POST /api/v1/approvals/{approval_no}/release-decision`，新增成对的可选 `supersedes_id`/`correction_reason`，而不是复制第二套权限和锁逻辑。严格输入拒绝未知字段；普通 DECIDE 不接受单边更正字段。

处理顺序：

1. 先执行现有 `RELEASE_AUTHORITY` 精确授权并解析可信 actor；声明 `decided_by` 只保留原文。
2. 按现有顺序锁 Release，再锁 ApprovalRequest，不能引入 Approval→Release 的反向锁序。
3. 锁内先按 request UUID 查原行与 `EVT-RD-{uuid}`。重放必须匹配 approval、decision_no、decision/readiness/notes、前驱、更正原因、可信 actor 和原审计全部绑定；同 ID 换正文或动作返回 409。
4. 新请求验证 ApprovalRequest/Release/FROZEN Snapshot；SUPERSEDE 再用共享 resolver 验证精确当前前驱和同 Snapshot。
5. 插入新 ReleaseDecision 和原子 AuditEvent；任一 flush/审计/commit 失败全部回滚。

SUPERSEDE 审计仍使用实体 `RELEASE_DECISION` 和新记录 UUID，但动作必须明确为 `DECISION_SUPERSEDED`。payload 至少绑定：新旧 decision UUID/number、Release/Snapshot UUID、snapshot_no/content_hash、旧新 decision/readiness、ApprovalRequest UUID/number、correction_reason、完整规范请求、principal/display/declared/source。原 `DECISION_RECORDED` 审计不修改。

## 6. 共享有效决策解析与消费者

必须先建立一个 SQL 有界的共享 resolver，再让所有“当前正式决策”消费者使用它：排除存在显式后继的记录后，按 `decided_at DESC, id DESC` 选择叶节点。旧记录都是独立根；最新未被替代的旧根继续兼容。新替代记录会成为新的叶节点。`decision_no` 只作显示/搜索，不参与时间先后。

| 消费者 | 实现要求 |
| --- | --- |
| `ApprovalService` | 新写、重放、当前前驱、锁和原审计的唯一写者 |
| `DistributionService._latest_release_decision` | 新交付只接受 resolver 选出的有效 `RELEASE`；HOLD 替代先提交则拒绝新交付 |
| `dashboard` application decision | 当前卡片使用 resolver；历史保留全部行并显示 predecessor/successor/effective |
| `governance_catalog` | 决策目录/详情保留全部原记录，新增前后 UUID、原因和 `effective`，不能隐藏被替代行 |
| `asr_passport` | 默认选择有效决策；显式历史 pin 仍可查看原行，但显示是否有效，不能把历史 pin 当当前许可 |
| `release_demo` | 只在有效决策、精确当前 Snapshot、APPROVED 和实际 READY 同时满足时显示 confirmed |
| production/deployment provenance | 保留创建时相关的全部历史决策，不用今天的有效决策重写原来源；显式显示替代关系 |
| activity/audit | 旧新审计均可独立导航，不从当前 resolver 推断原操作成功 |

resolver 不能加载某 Release 的全部历史到 Python。PostgreSQL 增长测试需覆盖至少 10,000 个旧根和长替代链，在既有 CI statement timeout 内保持固定形状查询；历史分页只为当前页关联 predecessor/successor，不做逐行相关全表扫描。

## 7. 与下游并发的一致性边界

Release 锁是正式决策写入与新 Delivery/Authorization 校验的线性化边界：

- HOLD 替代先提交：随后新 Delivery/Authorization 必须看到 HOLD 并拒绝；
- 下游命令先提交：它保留原决策 UUID/number 的审计证据，后来 HOLD 不删除或伪造回滚；
- 两个替代竞争同一前驱：最多一个成功，另一个 409，不能依赖最后提交覆盖；
- 原替代请求在后续再次被替代后重放：只返回原结果，不改变当前 resolver；
- 不得在本包给既有下游行增加“revoked”推断字段。真正撤销需要下一政策包的新记录、权限、原因、审计和并发测试。

## 8. 实现拆分与验收矩阵

下一代码包只做后端、迁移、共享读取和双语只读历史；不同时开放浏览器提交。建议路径：

- `backend/app/models/approval.py`
- `backend/alembic/versions/0025_release_decision_supersession.py`
- `backend/app/services/approval.py` 及新的共享 resolver
- `backend/app/services/distribution.py`
- `backend/app/api/governance_catalog.py`、`dashboard.py`、`asr_passport.py`、`release_demo.py`、`production.py`、`activity.py`
- `backend/app/seed.py`
- 对应后端、真实 PostgreSQL、迁移和前端只读历史回归

最低验收矩阵：普通 DECIDE 兼容；精确当前前驱替代；旧/跨 Release/跨 Snapshot/自指/双后继拒绝；新 Approval 同上下文；同 ID 原字节重放与正文/actor 冲突；业务/审计原子回滚；UPDATE/DELETE trigger；旧库升级无改写；有替代历史拒绝降级；替代与交付/授权并发两种提交顺序；所有当前消费者一致；历史 pin 不授权；长历史有界 SQL；Seed 首次/重复/碰撞；中英文只读前后关系。

后续再分别划定默认关闭的受控浏览器替代协议和原审计恢复。只有批准提供方的多用户正反例、并发和真实浏览器验收完成后，计划 6 的“判断关系替代”里程碑才可完成；设计、模拟 HTTP 或只读页面均不提升当前百分比。

## 9. 当前进度与下一步

本审查不改变业务验收：仍为 36/44（82%）；七模块为 100/100演示/100演示/100/89/60/17；七计划为 100/100/20/33/40/20/0。

下一包：实现 `release-decision-supersession-backend-read`，完成后再单独设计默认关闭的浏览器提交/原审计恢复。其后依次处理发布/分发/授权撤销、生产更正、真实身份/浏览器、内网和运营迁移；VIN 最后。
