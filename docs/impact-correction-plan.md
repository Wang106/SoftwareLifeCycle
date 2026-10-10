# Impact 更正与撤销：待审查切片计划

更新：2026-10-10（Asia/Shanghai）。模式：Codex / Work；没有启动本地 Plus CLI 或付费 API worker。

状态：**范围提案，尚未授权为启用开发任务**。本文件不改变 docs/automation/tasks.json 的 enabled/auto_merge、不启用调度或实际写入、不实现新协议或迁移。当前授权的 Acceptance 双语界面与手动恢复两项已通过 PR47/PR48 合并。下一阶段先审核具体切片，避免一次授权覆盖数据库迁移、撤销和全部下游政策。

## 已核对基线

- main：995366cd3c5a5b0d06722aa53d980f21cf709bd8（PR48）。
- Acceptance 更正双语确认、原结果、同站点手动导出/只读导入恢复已实现；真实跨会话/浏览器/提供方验收仍未完成。
- 后端 IssueImpactAssessment 已有 supersedes_id、correction_reason、同上下文复合自外键、唯一后继和非自引用检查；0021 已实现 SUPERSEDE，当前迁移头为 0022。
- record_assessment 持有 Issue 行锁，要求原关系是同 Issue/Release/FROZEN Snapshot 的当前有效判断；原行及原审计不修改。新请求 201、原请求/actor/审计完全相同重放 200，否则冲突。
- 原审计 EVT-IMPACT-{request_id} 是 ISSUE_IMPACT/SUPERSEDE；payload 包含原判断 ID、Release/Snapshot、原 snapshot_no、新 decision、supersedes_id、previous_decision、correction_reason、版本化 nullable evidence_ref 摘要及 actor_source。
- 普通 Impact 的 ASSESS 准备/回执/导入协议继续拒绝更正字段。withdrawal 未实现；不能将 NOT_AFFECTED 或 NEEDS_REVIEW 当作撤销。
- 公共样例只读、OIDC/实际提交门控关闭；69页面/API0.18.40/schema0022、14业务/2自身会话/6管理员/离线操作分计不变。

以上依据当前代码 backend/app/models/impact.py、backend/app/services/impact_assessment.py、backend/app/services/impact_history.py、backend/alembic/versions/0021_impact_supersession.py 与 docs/impact-judgment-corrections.md；不是对未来功能的完成声明。

## 推荐先授权 A：仅 SUPERSEDE 受控协议基础

不改数据库、后端写入模型、迁移、普通 ASSESS 协议、审批与下游读取；不接双语发送界面或导出导入。这是可独立回归的第一包。

| 范围 | 拟实现与验收 |
| --- | --- |
| 固定命令 | operation=impact-correction；target=Issue号；body 精确包含既有普通字段及 supersedes_id、correction_reason。完整新判断，而非补丁 |
| 原关系上下文 | predecessor 精确包含 id、release_id、snapshot_id、decision；与原 body 的上下文/前驱一致，新 request_id 与原 ID 不同，决策只允许三个现有值 |
| 文本与凭据 | reason 与 correction_reason 各自非空/各不超过4000字符；引用规范 nullable、声明最多120字符；整个规范命令≤8192 UTF-8字节，回复≤16384字节，两个原因虽各自合法仍须符合总字节上限。严格未知字段、Unicode、UUID、JSON；不接受调用者 URL/header/token |
| 原审计校验 | 当前 authenticated USER、Issue UUID/号、原声明/新 reason、新 decision、Release/Snapshot、原 snapshot_no、前驱 ID/previous_decision、更正原因、evidence 摘要版本和值必须全部匹配 |
| 回执 | 只显示原判断及审计里的冻结快照标签/关系；不能从最新状态、后继、replayed、当前覆盖/就绪情况确认原请求 |
| 独立代理 | 拟用 /auth/impact-correction 与 /auth/impact-correction-receipt；POST-only、同源、有限流式JSON、private/no-store、唯一加密Cookie与服务器当前 USER 复核 |
| 独立门控 | 拟新增 IMPACT_CORRECTION_SUBMISSION_MODE、批准 API 地址、批准应用 origin；三项服务器绑定精确匹配，默认关闭，不受普通 evidence/Acceptance 或 NEXT_PUBLIC 开关启用 |
| 发送与恢复 | 后端固定既有 Issue impact-assessments POST，200/201后查本人原审计；recover 只GET原审计，无当前对象回退。缺失/拒绝/错误/丢响应保持unknown，不自动重发 |
| 冻结控制器 | 明确确认、内存冻结原字节/请求ID；发送/查询同步互锁，confirmed终态；未知结果后门控/授权改变不抹掉原请求，显式重试保留原字节 |
| 回归 | 两种原前驱（普通/已替代）与全决策；每个原审计字段、nullable引用摘要、上下文/actor不符；独立门控、CSRF、重复Cookie、只读查询、lost响应、并发互锁、错误隐私 |
| 接受门槛 | 新增独立协议/代理测试，既有普通 ASSESS/Acceptance 回归全通过；类型/Next/OpenNext/禁用代理SSR、进度--check及精确head完整CI；main与provider分别验收 |

建议 A 的路径边界（拟授权，不是已启用队列）：
frontend/lib/impact-correction-transport.ts、frontend/lib/impact-correction-audit.ts；
frontend/lib/browser-auth.ts、frontend/lib/browser-session.ts；
frontend/app/auth/impact-correction/route.ts、frontend/app/auth/impact-correction-receipt/route.ts；
frontend/tests/impact-correction*.test.cjs、frontend/tests/fixtures/impact-correction*.cjs；
docs/impact-correction-submission.md、DEVELOPMENT_STATUS.md、HANDOFF.md。
部署样例默认关闭及真实Next禁用检查的必要配置变更应明确列入批准范围。既有测试文件需要加载新模块的调整应单独列明，不以新协议为由放宽旧断言。不包含 CI、调度、依赖、数据库迁移或实际环境配置。

## B：SUPERSEDE 双语确认、原始结果与手动恢复

A 的协议验收后另切一包：只读历史的准确前驱入口、独立更正准备/确认、默认中文/English、原字节发送/查询/重试、原结果/审计链接及严格同站点手动导出/只读导入。
普通 ASSESS 与更正独立；导入零网络、没有 send/retry 方法、不自动存储/查询；过期闭包、复制/发送/查询互锁、unknown保持及模拟新组件恢复须新增行为回归。
不在 A 中提前实现或宣称 B 完成。真实提供方、实际跨会话/浏览器验收另记，不因 mock/UI 回归提高里程碑。

## C：撤销模型与迁移单独审核

当前模型 decision 非空且只有 AFFECTED/NOT_AFFECTED/NEEDS_REVIEW，effective() 目前只检查有无后继。简单新增 WITHDRAW 决策或只过滤一个撤销行不够：
如果旧独立判断 A、新判断 B 共存，撤销 B 后不能因排序/leaf过滤使 A 自动重新变成当前判断。

必须先确定以下语义与实现，批准后才编写新的、接在实际最新迁移头后的迁移：

1. 撤销是新历史操作，引用同 Issue/Release/Snapshot 的当前判断和新请求ID；旧行/原审计不可变，原因必填，权限沿用精确 REVIEWER/平台管理员例外与 Issue 锁。
2. 撤销不等于 NOT_AFFECTED、NEEDS_REVIEW 或审批回滚；该上下文变成“没有当前有效判断”，readiness 必须重新要求判断，不能沿用旧结论。
3. 原当前判断的所有旧独立历史保留，但撤销不能复活旧行；必须引入明确的上下文终端操作/当前指针语义，所有消费者共用它，不能各自按时间挑旧leaf。
4. 后续用户显式提交全新的普通判断可以重新建立当前判断；旧撤销请求重放仅返回原历史事实，不能消除后来的新判断。
5. 候选设计需比较：既有历史表增加操作类型并配套上下文终端投影；或独立撤销操作表加统一上下文投影。比较复合外键/唯一前驱、原审计、普通旧行兼容、排序与查询预算、降级保护。尚未选定，不直接把 Acceptance action 字段复制到 Impact。
6. 确定撤销正文是否保留原 decision/reason/evidence 的历史副本或通过不可变前驱查询；回执显示历史值时必须标明不是新有效判断。原证据引用继续只记录规范摘要，不进入审计明文。
7. 审计须有唯一原事件、撤销动作、原 decision/前驱/完整上下文/原因/actor，业务与审计同事务；request_id 重试绑定全部原正文、身份、动作及原审计；撤销缺失审计时unknown。
8. 迁移保留全部旧数据、复合上下文外键与 append-only 保护；有撤销时拒绝丢语义的降级。至少做空库/旧样例库升降级、真实PostgreSQL并发替代vs撤销/撤销vs新判断/重复原请求、外上下文/自引用/失效前驱/审计中断、长历史有界查询回归。

数据库迁移 C 不因批准 A 自动获批。实现后的数据库迁移部署与 Render 在线 schema、内网实际安装分别验收，不以 frontend provider 构建代替。

## 执行顺序和后续限制

推荐 A → B → C 的模型/迁移审查 → 撤销后端与所有有效读取 → 撤销受控界面/恢复 → 发布评审/分发/授权/批次的下游更正规则。离线部署及运营迁移需 OS/CPU/安装条件和真实身份明确；VIN最后。

当前所有后续任务仍 disabled，auto_merge=false；不修改账户/角色/秘密，不开启付费 API 自动调度，不解除 main PR/严格CI/管理员保护。
评审本文件后只授权具体的一包及必要路径；下一包开始仍需核对最新main、开放PR、实际任务状态与精确CI/provider证据。
36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，本规划验收增量0。

