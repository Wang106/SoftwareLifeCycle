# Impact 撤销模型与迁移方案审查

审查日期：2026-10-11（Asia/Shanghai）。状态：仅设计文档；以下实现提案尚未授权。
执行：Codex 编程代理在 ChatGPT Work 云端，使用已连接 GitHub；没有启动付费 API 开发器、用户本地常驻 CLI 或上传登录缓存。

## 1. 事实基线与边界

本轮从实际远端 main `d13c42af3b6f95a3d4f31b5c060db3ac967b6316`（PR53）读取仓库指令、需求、路线图、进度账本、Plus 队列及最新交接，开始时没有开放 PR。PR47/48 Acceptance 两项已真实合并，不能重复执行：

| PR | 实际 merge SHA | 已完成能力 |
| --- | --- | --- |
| 47 | `88b578f8dbf20711a0078c7760f39a5fc2173b7c` | Acceptance 更正双语确认和原始结果 |
| 48 | `995366cd3c5a5b0d06722aa53d980f21cf709bd8` | Acceptance 手动导出与只读原审计恢复导入 |
| 50 | `0c622c54c4db9f7b1581752b44713192370759a0` | Impact SUPERSEDE 独立受控协议与原审计恢复 |
| 51 | `ebfac27a2086ec99245de02294e98f8b0ab79193` | Impact SUPERSEDE 双语界面及手动恢复 |

代码 API 为 0.18.40；实际 Alembic 单 head 是 `0022_acceptance_history`，其前驱为 `0021_impact_supersession`，required_db_revision 与之匹配。没有 Impact WITHDRAW 模型、写入或界面。
本包仅写本文件、DEVELOPMENT_STATUS.md、HANDOFF.md；不写后端、迁移、界面、测试、依赖、CI、队列或真实门控。下文的 API、字段、revision 和测试是下一包提案，不是已交付功能。
公共样例只读，OIDC/实际提交关闭，内网未部署；不配置实际身份、权限或秘密。

## 2. 已核对的模型与完整消费者清单

| 实际路径 | 当前行为及撤销所需处理 |
| --- | --- |
| `backend/app/models/impact.py` | IssueImpactAssessment 的 decision 非空且只允许三种判断；supersedes_id 同上下文复合外键、唯一后继、更正原因配对及禁止自指。历史行不可更新。 |
| `backend/alembic/versions/0012_issue_impact_assessments.py` | 创建历史表和数据库 UPDATE/DELETE 拒绝 trigger。不得为新动作永久关闭 trigger。 |
| `backend/alembic/versions/0021_impact_supersession.py` | 保留原行追加替代；有替代历史时拒绝丢语义降级。 |
| `backend/alembic/versions/0022_acceptance_history.py`、`backend/app/services/acceptance_history.py` | Acceptance WITHDRAW 按 criterion 关系处理；不能直接照搬其排除 WITHDRAW 的 effective 条件到 Impact。 |
| `backend/app/services/impact_history.py` | successor_id 是关联标量；effective 只排除已有后继的行。多个独立根仍可成为 leaf，必须增加统一上下文终端解析。 |
| `backend/app/services/impact_assessment.py` | Issue FOR UPDATE；先查 request_id 重放，再校验新写 FROZEN、软件候选和同上下文当前前驱；flush 判断及原子审计，调用方 commit。ASSESS/SUPERSEDE 都必须使用新终端与排序。 |
| `backend/app/api/impact.py` | POST 判断仍有效；历史序列化、_contexts、assessment_history 与返回后继须区分原操作和当前效力。_contexts 当前把全部有效行加载到 Python，不能保留这条无界算法。 |
| `backend/app/api/issue_views.py` | candidates 的相关 latest 判断、judgments 历史、summary 历史计数、evidence_summary 都直接消费 Impact。分页之外独立解析上下文终端，不从当前页推断。components/verification 只读证据，不改其业务定义。 |
| `backend/app/api/compatibility_reads.py` | 旧 impact/evidence/assessments GET 已 410，指向 issue-views；POST 未退休。不重开旧 GET，不用死路径假称当前页面完成；保留函数若继续使用亦须统一终端语义。 |
| `backend/app/authorization.py`、`backend/app/actor.py` | authorize_issue_assessment 绑定 Release scope 与 Issue 所关联项目；认证 actor 来自可信 request.state。新撤销复用现有精确权限，不把历史前驱或声明 actor 当授权。 |
| `frontend/lib/issue-views.ts` | Judgment 假定 decision 为 string；新增撤销历史必须用判别类型，避免 null.replaceAll 崩溃及撤销被显示为普通判断。 |
| `frontend/app/issues/[id]/page.tsx`、`frontend/app/issues/[id]/impact/[releaseId]/page.tsx` | 候选、历史和精确冻结快照摘要；撤销需要明确状态、原历史与独立新判断入口，不能显示旧独立根作为当前判断。 |
| `frontend/components/impact-correction-history.tsx` | 无 successor 的历史行可准备替代，但不是当前效力证明；撤销后不能从旧根再次替代。新读取需明确 context terminal，后台仍重验。 |
| `frontend/components/impact-correction-workbench.tsx`、`frontend/components/impact-correction-result.tsx` | 仅 SUPERSEDE，互锁、unknown 和原结果已实现。当前包不扩展提交 UI。 |
| `frontend/lib/impact-correction-transport.ts`、`frontend/lib/impact-correction-audit.ts`、`frontend/lib/impact-correction-recovery.ts` | 原字节/前驱/actor/nullable 证据摘要、原审计白名单和同站点手动导入。v1 只接受 SUPERSEDE，不能偷偷把 WITHDRAW 塞进 v1。 |
| `frontend/app/auth/impact-correction/route.ts`、`frontend/app/auth/impact-correction-receipt/route.ts`、`frontend/lib/command-draft.ts` | 独立默认关闭的替代代理/原审计查询；普通 ASSESS 草稿走原 impact-assessments POST。新撤销提交及撤销后新判断准备需要后续单独协议包。 |

对 backend/app 全量搜索模型及 effective 引用，并检查 dashboard/search/asr_readiness/traceability：当前搜索只索引 Issue，Dashboard Issue 状态/严重度与追溯的 Issue–DVP 覆盖不是人工 Impact 判定。没有发现直接消费 IssueImpactAssessment 的发布就绪计算。
因此下一模型包不把撤销接成放行、关闭 Issue、通过测试、解除 readiness 阻塞、授权或批次追溯更改。今后若加入 Impact 下游政策，必须通过同一解析器并单独划定范围；不能宣称本审查实现了该政策。

## 3. 终端语义：先选上下文事件，再解释动作

上下文 K = (Issue UUID, Release UUID, frozen Snapshot UUID)。版本号相同只是候选线索；Snapshot 必须属于精确 Release，不能跨快照撤销。
存在两层不同信息：某历史行有没有显式后继，以及整个 K 的当前终端事件。后者才决定当前判断。
统一 resolver 返回 `terminal_event_id`、`terminal_action`、`context_state`、`assessment`：
- 无事件：UNASSESSED，assessment=null。
- 终端 ASSESS/SUPERSEDE：JUDGED，assessment 为该终端判断。
- 终端 WITHDRAW：WITHDRAWN，assessment=null，同时保留原撤销及目标判断的历史引用。

WITHDRAW 不是 NOT_AFFECTED 或 NEEDS_REVIEW，不产生新的技术判断，不删改原判断或原审计。先选包含 WITHDRAW 的全上下文终端，之后才投影 assessment；绝不能先过滤撤销，再找最新判断。

| 操作序列（同 K） | 当前观察 | 后续限制 |
| --- | --- | --- |
| 独立根 A，独立根 B | B；A 保留原历史 | A 无显式后继也不等于当前有效判断 |
| A，B，B→S（SUPERSEDE） | S | 替代 A/B 的旧新请求应冲突；已提交原请求仍可重放 |
| A，B，B→W（WITHDRAW） | WITHDRAWN，assessment=null | A 不复活；不能以旧根为前驱再替代或撤销 |
| W 后新 ASSESS C | C，仅当请求显式确认当前 W | C 是独立的新判断，不是撤销 W、不修改 W，也不是 W 的伪判断后继 |
| W，C 后重放原 W 请求 | 返回 W 的原操作及原审计 | 不追加事件、不使 C 再被撤销、不返回 C 当原回执 |
| W 后不同 ID 再撤销 B | 409 | 撤销不能把已撤销的原判断重复当当前前驱 |
| 另一 Snapshot 有判断 D | 此 Snapshot 保持自己的状态 | 不跨快照回退或合并技术判断 |

显式新判断 C 必须用全新 request_id，并携带 `after_withdrawal_id` 等于当时 K 的终端 W；该字段只在从 WITHDRAWN 恢复为 JUDGED 时有效，其余上下文拒绝无关值。发送前的旧普通 ASSESS 草稿没有此确认，不能自动解除撤销。
原 ASSESS/SUPERSEDE/WITHDRAW 重放先检查已存在请求及原子审计绑定，不能再次要求其前驱仍是当前终端；但当前请求认证/权限仍须通过，历史成功不授予今天的访问权。

## 4. 两种存储方案比较与推荐

| 方案 | 优点 | 风险与必要配套 |
| --- | --- | --- |
| 扩展 issue_impact_assessments 为动作历史 | 原 ID/审计命名/同上下文复合外键/唯一后继和 append-only trigger 可复用；一个请求命名空间、一个终端 SQL，跨操作碰撞由主键阻断 | WITHDRAW 没有 decision，需可空且严格动作约束；历史 DTO/前端必须分型；旧行 action 不能粗暴全部回填 ASSESS；旧写版本不允许继续插入 |
| 独立 issue_impact_withdrawals 表 | 原判断 decision 非空保持，原判断表含义清晰 | 需要两个表联合排序、跨表请求 ID 与唯一后继仲裁、两个 append-only trigger、原判断替代和撤销竞争的统一 mutex；只 anti-join 被撤销行会复活旧根；所有读取仍须改，兼容收益不能代替统一语义 |

推荐第一方案，但采用无需更新旧历史正文的增量结构。该选择是可实施设计建议，不是对下一代码包的授权。

拟新增 `0023_impact_withdrawal_history`，down_revision=`0022_acceptance_history`（实际实现前重新核对 head，若已前进必须使用新的唯一 revision）。

- 新增 action 和 context_seq 两列，允许旧行同时为 NULL。旧行逻辑动作由 supersedes_id 是否为空推导 ASSESS/SUPERSEDE；保留原 ID、时间、actor、reason、evidence_ref、前驱及审计，禁止回填或改写原审计。
- 新行必须显式 action∈ASSESS/SUPERSEDE/WITHDRAW，context_seq 正整数；数据库 INSERT guard 拒绝新增 legacy NULL/NULL 行。旧行保留 NULL 仅用于兼容已存在数据，不能成为旧版本偷偷写入的通道。
- decision 仅 WITHDRAW 为 NULL；其余仍限三种非空判断。WITHDRAW 使用 supersedes_id 精确引用当前判断，correction_reason 为独立撤销原因；reason 为该次原请求说明，不能用原技术判断的 reason 冒充。WITHDRAW 不允许技术 evidence_ref；原目标证据引用从目标与原审计读取。
- ASSESS 无 supersedes_id/correction_reason；SUPERSEDE/WITHDRAW 两者非空并遵守现有 1–4000 限制、复合上下文 FK、唯一后继及禁止自指。新增 after_withdrawal_id 同上下文 FK，只用于 ASSESS 显式恢复；服务验证被引用行必须是当前 WITHDRAW。该关联不占用 supersedes_id 唯一后继，以区分新判断和撤销重放。
- 约束须用显式 IS NULL/IS NOT NULL 防止 SQL CHECK 的 UNKNOWN 放行：legacy 分支必须 action/context_seq 同时 NULL、decision 非空且满足旧配对约束；new 分支两者非空、动作与字段一致。恢复字段旧行必须 NULL。
- context_seq 在 K 内唯一（旧 NULL 不占序号），加 K/context_seq 排序索引；所有新动作在同一 Issue 锁下分配 MAX(non-null seq)+1。新序号总是优先于旧 NULL 行；纯旧上下文沿用 created_at DESC、id DESC 的现有确定性规则。
- 不用客户端时钟、UUID 大小或事务开始时间保证新操作次序。锁必须先获取，后分配序号；新行发布即覆盖该 K 所有旧独立根的当前位置。无需遍历或更新它们。
- INSERT guard、现有 UPDATE/DELETE trigger 和外键/唯一约束共同验证；数据库不能单靠 trigger 判断调用者项目权限，该项仍由受控服务处理。直接绕过服务的历史导入不在本方案允许范围。

独立撤销表若在实现评审中被选取，也必须提供同等统一事件序号、跨表请求注册与后继唯一性，不接受功能较弱的降级方案。不得以“先做撤销表、消费者以后改”发布。

## 5. 写入、锁、原子审计与幂等恢复

拟新增 `POST /api/v1/issues/{issue_no}/impact-withdrawals`，严格 WithdrawalInput：request_id、release_id、snapshot_id、supersedes_id、actor_name、reason、correction_reason；没有 decision/evidence_ref。额外字段拒绝，UUID/trim/正文长度和请求 ID != 前驱保持严校验。普通 ASSESS 新增可选 after_withdrawal_id；现有 SUPERSEDE 字段语义不变。

处理顺序：
1. 路由执行现有精确权限及可信 actor 解析。认证主体、项目范围和业务候选是不同校验，不把当前历史页当授权。
2. 与 ASSESS/SUPERSEDE 共用 Issue FOR UPDATE，持续到 commit/rollback。沿用已有授权/会话锁顺序，不增加相反的 Issue→授权锁路径；首包不改为 context-only 锁或混用 advisory lock。
3. 在锁内先查全局 request_id。存在则比对 issue/context/action/全部规范化正文/可信原 actor 及对应完整原审计；同 ID 换操作、目标、原因、证据、恢复 ID 或主体必须 409，不能生成第二个动作。
4. 仅新请求检查 Release/Snapshot/FROZEN/软件候选，再通过统一 resolver 验证当前前驱；WITHDRAW/SUPERSEDE 只允许当前 JUDGED 的精确 ID。WITHDRAWN 后 ASSESS 必须匹配 after_withdrawal_id。
5. 分配 context_seq，flush 历史和 AuditEvent；路由同事务 commit。审计失败、约束失败或服务异常 rollback 两者并释放锁。服务不自行 commit；不得先提交正文后补审计。
6. 新建 201，原请求重放 200；409 表示请求冲突或当前上下文改变；保持现有认证、验证、事务错误响应原则。响应分别命名 original_operation 与 context_observation，不混为一次原成功结果。

审计 event_no 沿用 `EVT-IMPACT-{request_id}`，event_type=ISSUE_IMPACT、entity_type=Issue、entity_id 精确 Issue UUID、entity_ref 原业务编号，action=WITHDRAW。
绑定原 request_id、issue/release/snapshot/原 snapshot_no、目标 supersedes_id、previous_decision、撤销原因及说明、action、context_seq、after_withdrawal_id 规范空值与全部 trusted actor 字段（principal/display/declared/source）。保存带版本的规范正文指纹；新审计中 decision/evidence_ref 的空值须明确，不能靠缺字段与 NULL 等价。
可信 actor 由 resolve_actor 产生，actor_name 仅声明；认证主体来源必须绑定 AUTHENTICATED_PRINCIPAL。既有 legacy ASSESS 审计兼容不能被描述为已具备新协议保证，不伪造可信主体。

原审计恢复只 GET 精确原 event_no：验证 event UUID、动作、类型、实体 ID/ref、原主体、原声明、完整正文指纹/前驱及原结果。只投影该次 WITHDRAW 的原结果，不从当前 leaf、superseded_by_id、assessment=null、HTTP 200、replayed 或当前 readiness 推断成功。缺失、错绑或字段不完整保留 unknown；恢复不 POST、不自动重试。旧 W 重放即使当前为 C 也只确认原 W，不重验其“仍为当前”条件、不修改 C。
新 WITHDRAW 控制器/浏览器协议另包设计独立默认关闭入口；SUPERSEDE v1 手动恢复格式保持严拒未知动作，不冒充支持撤销。

## 6. 读取、旧库兼容与迁移降级

单一 resolver 用在 candidates、evidence_summary、新写前驱验证及保留的兼容实现；排序条件固定，不在不同端点各自实现“最新有效判断”。SQL 先定位 K 终端，随后解释动作；基于索引的相关 LIMIT 1 或有界上下文集合查询，不把所有 leaf/根加载进 Python。
历史按原事件完整分页（不隐藏 W），明确 action、原值、显式 successor 与单独 context_state；历史计数由“技术判断数”与“动作历史数”区分，不把撤销计作新增人工技术判断。不能用历史第一页/当前 offset 判断终端，也不能用纯 superseded_by_id=null 判断当前有效。
候选与证据摘要增加 context_state/terminal_event_id；withdrawn 下 decision/assessment=null，尚未判断也 null，但状态不同。旧判断字段仅在 JUDGED 返回；旧行推导动作并原样展示。前端只读类型与显示必须同包适配，不能让 null 到达 replaceAll。

升级验收从真实 0022 旧库开始，包含独立根、替代链、相同时间/UUID tie、nullable 证据、legacy 与 authenticated 审计。核对旧行及审计逐字段/哈希不变。新列逻辑默认不能把旧 SUPERSEDE 误标 ASSESS；旧 append-only trigger 始终存在，INSERT guard 与新约束安装后新程序方可写。
发布期间停止旧写版本，升级迁移并验证 required revision，再启动新程序/检查 readiness；不能仅凭健康路由期待所有旧实例自动停写。新 schema 下旧版本 INSERT 必须拒绝；禁止“先允许旧写、稍后修补语义”。

降级至 0022 前，若存在 WITHDRAW 或任何旧版本不能表达的 after_withdrawal 关系，立即抛错，在一个 PostgreSQL 事务内保持 schema、revision、历史、trigger、原审计原样。不可删撤销、复制旧判断、改审计或先丢列后检查。采用保守降级条件：只有全部记录仍是 legacy NULL action/NULL context_seq，且没有恢复关系时才允许移除新 INSERT guard/约束/元数据列并恢复 decision NOT NULL；不删除任何判断行或审计。有任何新序号动作（包括纯 ASSESS/SUPERSEDE）也拒绝降级，因为丢失 context_seq 后旧 created_at/id 排序未必保持同一终端，尤其旧库未来时间或 tie。不得只检查 WITHDRAW 就称无损。升级–安全降级–再升级必须保留旧 SUPERSEDE 和审计绑定。
任何部分降级都须通过真实 PG 验证；SQLite 不是 trigger/锁/迁移事务的验收替代。SEED 不增加撤销演示、不改旧判断或审计，仍需重复执行确认幂等。

## 7. 下一实现包测试矩阵（本轮未实施）

| 类别 | 必测用例 | 验收证据 |
| --- | --- | --- |
| 终端语义 | A/B 独立根→B 替代→撤销；只有 A→撤销；另一 snapshot 隔离；W→显式 C→旧 W 重放；无确认旧草稿拒绝 | current assessment 不复活 A，原历史完整；所有实际读端一致 |
| PG 相同请求并发 | 同 W 请求重叠；同 ID 改原因/actor/动作；不同 ID 竞争撤销/替代同前驱 | 两独立 connection 与同步屏障，1 历史+1 原审计；冲突方无记录 |
| PG 混合并发 | WITHDRAW 对 ASSESS、WITHDRAW 对 SUPERSEDE、两个显式恢复 C、不同 K/同 Issue、不同 Issue | 最终序号与 commit 锁序一致；显式恢复 ID 被原子重验；无交叉上下文/死锁 |
| PG 事务故障 | 历史 flush 后、审计 flush 后、commit 失败；请求取消/回滚后重试 | 两者全回滚，旧终端保持，锁可复用；不能将单边记录当成功 |
| DB 防护 | UPDATE/DELETE，空动作/序号、非法 NULL 组合、跨 K/自指、重复前驱/序号、旧版本 INSERT | 真迁移 PG 直接 SQL 拒绝，原 trigger 未绕过；非法请求服务同样拒绝 |
| 旧库升级 | 0022 数据含旧根/链、timestamp tie、nullable 证据、原认证/legacy actor | 逐字段与审计摘要相同；新增动作胜过全部旧根；唯一新 head |
| 安全降级 | 纯旧根/替代：upgrade→downgrade→upgrade；含新序号判断/W/恢复行：downgrade 拒绝（包括未来旧时间及 tie） | 原数据/审计完全保留；拒绝后 revision/列/trigger 仍一致，无部分 DDL |
| 原审计恢复 | W→C 后恢复 W；错实体/actor/body/前驱/空值/指纹版本；审计缺失；原 ASSESS/SUPERSEDE 回归 | 只确认原操作，错绑 unknown/409，GET 恢复零写入 |
| 有界长历史 | 10,000+ 独立根与长替代链；终端在分页外；多快照、相同旧时间、offset 边界 | SQL limit 生效、无 Python 全历史 materialization、查询次数/结果规模随页面及上下文有界；PG EXPLAIN/索引证据，不以小 fixture 时间断言冒充 |
| API/只读 UI | UUID pin/冻结上下文/401/403/409/422；JUDGED/WITHDRAWN/UNASSESSED 中英 SSR | action 判别/null 安全、原历史可读；退休 GET 仍410，所有真实门控保持关闭 |
| 集成基线 | Seed 两次、offline SQL、隔离 PG 往返、全后端/真实 PG、全前端、Next/OpenNext、禁用认证 SSR | 既有断言不削弱、必需三个 CI 精确 head 全 success、PG 无 skip；再独立 main/provider |

## 8. 待授权下一实现包的精确范围

建议包名 `impact-withdrawal-history-backend-read`；一次交付模型/受控后台写入/统一读取/只读显示及真实 PG 证明，不含浏览器撤销发送或新的真实门控。授权前保持停工。

拟修改既有文件：
- `backend/app/models/impact.py`、`backend/app/services/impact_history.py`、`backend/app/services/impact_assessment.py`、`backend/app/api/impact.py`、`backend/app/api/issue_views.py`、`backend/app/core/config.py`。
- `frontend/lib/issue-views.ts`、`frontend/app/issues/[id]/page.tsx`、`frontend/app/issues/[id]/impact/[releaseId]/page.tsx`、`frontend/components/impact-correction-history.tsx`：仅动作历史/终端状态读取与双语展示，不接撤销发送。
- `frontend/lib/i18n/zh.json`：只增加撤销/未判断/终端历史只读文案，中英切换继续复用现有 `frontend/lib/i18n.ts`，不改翻译机制。
- `docs/impact-withdrawal-design-review.md`、`API.md`、`DATABASE.md`、`DEVELOPMENT_STATUS.md`、`HANDOFF.md`：记录实际实现契约与精确验收。

拟新增文件：
- `backend/alembic/versions/0023_impact_withdrawal_history.py`（须再次核对真实 head）。
- `backend/app/services/impact_withdrawal.py`。
- `backend/tests/test_impact_withdrawal.py`、`backend/tests/test_impact_withdrawal_postgres.py`、`backend/tests/test_impact_withdrawal_reads.py`。
- `frontend/tests/impact-withdrawal-read.test.cjs`。

新增测试复用真实迁移 PG fixture/重叠事务工具，不修改已有测试以降低通过门槛。已核对 `scripts/ci/check_backend_report.py` 按 classname 中 `_postgres` 自动识别，新增 `test_impact_withdrawal_postgres.py` 应被纳入，无需修改 CI/报告器；完整报告必须显示新 PG 用例，无 skip。
验收需落实第3–7节全部规则、旧消费者/null安全、0022旧库无损与拒绝降级、原审计重放、完整CI及独立main/provider。单纯模型能插入 W 或前端出现按钮不构成验收。尚未授权实施，revision仍0022。
随后浏览器 WITHDRAW 受控协议/双语确认/手动恢复为另一个待划定包；实际身份/公司部署、评审下游政策和运营恢复亦独立，VIN最后。本审查无业务验收增量：36/44=82%；七模块100/100演示/100演示/100/89/60/17，七计划100/100/20/33/40/20/0。

## 9. 发布与恢复检查点

独立分支 `codex/impact-withdrawal-design-review`，基线见第1节。执行进度 --check、既有标准库自动化回归、diff/仅三文件检查；完整后端/PG/前端构建由新 PR 精确 head 的既有 CI 证明，不把基线成功当本包测试。
本地实际执行进度 --check、52 项既有标准库自动化回归（全部通过）、diff --check 与仅三文件边界核对；本地未运行后端/PG/Next/OpenNext，不冒称本地构建通过。
Render monitor 技能的只读 list_services 检查返回 no workspace selected，不能自行选择或把历史服务当本次验收；当前 Render live API/schema/部署未核验。该限制不阻断本包文档与 GitHub CI，不增加部署权限。
本包 PR 为 [#54](https://github.com/Wang106/SoftwareLifeCycle/pull/54)，首份文档提交 `44d78d97246c2b5e5903c5a4c03c1a51c2e1bcd3`；随后收紧无损降级条件并补充此检查点，最终精确 head 及 CI/merge 以 PR 记录为准。
PR 描述记录最终 head、三个 job、真实 merge SHA、独立 main CI、Cloudflare/Render/Actions 的实际状态。HANDOFF 顶部及末尾保存本包，远端合并证据覆盖 plus-tasks 的旧 pending；该队列不在本包允许文件范围，故不编辑。
本包真实合并并核验后暂停当前自动任务；不重复执行已完成审查，也不把下一实现提案当成自动授权。skipped/unverified 不称部署成功。

## 10. 已授权实现检查点 — 2026-10-11

PR54 真实合并到 1615ab72c0b11deea21674f2bfe8a91dde3c8197 后，用户明确授权 impact-withdrawal-history-backend-read，覆盖第8节旧“待授权”描述。本实现采用扩展动作历史方案，revision 0023_impact_withdrawal_history、API0.18.41；原历史和审计不回填，锁内 sequence、新 WITHDRAW、显式 after_withdrawal_id、原请求 actor/全正文指纹/原审计重放均落实。当前 Package 的最终精确 head/真实 PG/full CI/merge/main/provider 证据以其 PR 为准，不复用审查包成功。

实际消费者额外包括 frontend/components/issue-collections.tsx；新增路由必须同步 backend/app/write_contracts.py 及 main.py API 版本。3 个既有测试精确计数/head 常量从14/0022更新到15/0023；旧迁移测试在0022插入旧数据再往返，不用新写者伪造旧行，不移除旧断言。其余既有迁移、依赖、CI、真实门控未修改。新增数据库测试含10,000旧独立根、1,024旧替代链、原审计逐字段恢复、真实锁争用及EXPLAIN/索引/有界结果检查。

2026-10-17 后续包已实现独立、默认关闭的浏览器撤销协议、双语确认/原结果和同站点手动恢复，契约见 `docs/impact-withdrawal-ui-recovery.md`；生产身份、实际写入门控、真实多用户浏览器及内网部署仍未实施。公共样例只读、OIDC/真实提交关闭，不因协议/UI测试提高36/44业务验收。
