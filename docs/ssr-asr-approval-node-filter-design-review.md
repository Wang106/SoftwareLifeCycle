# SSR/ASR 已记录审批节点筛选范围审查

日期：2026-10-23（Asia/Shanghai）。执行：Codex / ChatGPT Work。
基线：main `181d06776d35a24bc251ed85d313bdd14c0e8b34`（PR#112）。
本包仅审查和文档；未实现筛选、改变接口或取得新的现场验收。

## 结论与下一包

建议下一包 `ssr-asr-recorded-approval-node-filter`，仅在 `/demo/zfi` 的固定 Excel 样例家族内增加 GET 筛选，含义限定为“已记录的待审节点”。不扩展标准/应用发布全库目录，不生成待办任务、人员分工或审批操作。

当前响应不足以证明审批与当前冻结 Snapshot 一致。不得称为当前有效审批、已授权任务或正式发布筛选。若以后要求这些语义，必须另开后端契约包，明确审批 UUID、目标 Release UUID、Snapshot UUID/冻结状态、当前 Snapshot 对比及失配枚举；本包不批准该扩展。

## 实际代码核对

| 来源 | 已有行为 | 对范围的影响 |
| --- | --- | --- |
| `backend/app/api/release_demo.py` 的 `zfi_import` | 一个 GET 返回 manifest 固定20条 SSR/ASR，批量读取确定 ID 的审批和步骤；步骤数量、顺序和角色与预期路线匹配才输出 progress | 可在单次结果内筛选；不得逐行请求审批详情或扫描其他家族 |
| 同一函数的 `approval_progress` | 关闭态为 APPROVED/RETURNED/REJECTED/CANCELLED；首个 PENDING/WAITING 中仅 PENDING 可成为 current；计数为 APPROVED 步骤数 | WAITING 不等于当前待审；通过计数不能推断节点；null 不等于未开始 |
| 同一响应 | 包含 release_id、approval_no、approval_status、current_role、current_step_order、closed；没有审批 UUID、target_id、snapshot_id 或绑定状态 | 只能显示记录的投影；当前函数也未核验审批目标/快照，不能由 initialized 推断上下文一致 |
| `frontend/app/demo/zfi/page.tsx` | 单个 GET、15秒上限，先按 type/customer/status/q 取交集，再按10条分页；顶部计数为全家族 | 新节点条件必须在分页前与全部既有条件取交集，不能过滤当前页或改变顶部计数 |
| `backend/app/api/governance_catalog.py` | 审批目录支持 state/release_id/snapshot_id/approval_id/q，无节点筛选；summary 的 binding_state 检查原目标/冻结快照关系 | 不把现有目录称有节点查询能力；CONSISTENT 也不证明绑定最新 Snapshot |
| `frontend/app/approvals/[id]/page.tsx` | summary 后按精确 approval_id 读取分页步骤/动作；完整步骤窗口才显示全局进度和 active | 保留详情边界；部分页不能支持全局节点判断，不能借第一条可见步骤推断 |

SSR路线：电子工程师 → 电子经理 → 系统工程师 → 研发总监。
ASR路线：应用工程师 → 应用经理 → 系统工程师 → 项目经理。
角色名称只描述流程，不能映射为真实身份或岗位权限。相同步序在两类发布中的角色可能不同。

## 推荐前端契约（尚未实现）

新参数 `stage` 使用固定值 `1`/`2`/`3`/`4`/`UNKNOWN`；无值为全部。选择步序跨SSR/ASR时，界面同时展示两条原路线，避免把第2步统一称某个岗位。不使用可翻译角色文本作URL值。

| 情况 | 节点匹配规则 |
| --- | --- |
| 明确 PENDING，progress.closed 为 false，total_steps=4，approved_steps 为0至4整数，current_step_order 为1至4整数且 current_role 与该发布类型的原路线一致 | 可匹配对应 stage；显示“已记录待审节点”，不认证 Snapshot 或真实人员 |
| 已知关闭态，progress.closed=true 且节点/角色均为 null | 不匹配1至4；由原 status 筛选定位，不把关闭记录算 UNKNOWN |
| 缺少审批/进度、未知审批状态、类型/路线不符、字段类型或范围异常、状态与 closed 冲突、开放状态无显式节点 | 归入 UNKNOWN；仅表示节点无法确认，不能改称未开始、已完成、未导入或数据损坏 |
| WAITING、仅批准计数、记录状态 READY/RELEASED、相同版本号 | 均不能自行推导待审节点 |

该校验仅限制新筛选的解释，不宣称修复后端所有一致性问题；例如响应未携带全部步骤状态，无法证明先前步骤全通过或不存在第二个PENDING。不得把此投影升级为治理判断。

重复/非法 stage 需要双语参数提示，并保留原记录与其他筛选，不静默假装条件已应用；不触发额外GET、重试或写入。现有 type/customer/status/q 的解析规则保持不变。

链接、GET搜索表单和分页保留合法stage；改节点/搜索/其他筛选重置到第1页。清除全部删除stage与分页。节点变化后的空结果显示原空态，不补入其他客户/家族；API失败/不完整先显示原不可用态，不显示“0条符合”来伪称成功读取。

## 下一包允许路径与验收

允许改动：`frontend/app/demo/zfi/page.tsx`、必要的独立纯筛选辅助模块（放 `frontend/lib/`，仅本页消费）、`frontend/lib/i18n/zh.json`、新增 `frontend/tests/zfi-demo-stage-filter.test.cjs`，以及 DEVELOPMENT_STATUS/HANDOFF/进度账本。本包不改这些产品文件；路径依据当前树核对，实施前再次确认。

下一包保留旧测试和断言。新增行为回归应覆盖：

1. SSR与ASR四节点、共享系统工程师及第2/4步不同角色；未知/失配/缺失/越界/非整数/错误布尔值、关闭态与WAITING无节点；明确不得用批准计数推导。
2. 节点与type/customer/status/q取交集；超过10条时先过滤后分页；URL/GET搜索保留、变更归第一页、清除全部、重复及非法参数提示。
3. 完整家族摘要不变；无匹配、API不可用和未完整初始化分开；只执行原固定GET，精确Release UUID及审批编号链接不改。
4. 中文和English实际渲染、参数提示、标签关联/键盘操作/窄屏换行，用户文本转义；不新增POST、commands入口、轮询、缓存治理结论或真实身份请求。

先跑定向节点/原有搜索筛选/总览/本地化回归，再完整前端、Next/OpenNext构建和禁用认证SSR；保留现有完整后端/真实PostgreSQL CI门禁。新PR精确head包含最新main且三个必需检查成功才受保护合并。合并后独立核验main CI、Cloudflare、Render和Actions。真实设备点击与公网延迟另记，不用SSR测试替代。

## 本轮恢复证据与安全边界

PR#112 head `7584d44fda11db1382365110fcc1371ce20c3e80`，CI39944097290三项success，已合并到基线main。独立main CI39945729101：Backend120387796501为2368 passed、258 PostgreSQL-module cases/no skips，迁移0029/SQL/真实PG往返通过；Frontend120387796800为1517 passed/0failed/0skipped、生产构建及禁用认证SSR通过；CI acceptance120392315812 success。本轮重新读取检查和日志，不把这些归为新文档head结果。

Cloudflare同main check120388407538 success，build `4bebb7bf-7b35-489d-ac78-31179cf56a46`，version `7280d42d-a934-48cc-b817-fe2327e18be6`。Actions deploy39947115581/wake39947115492均skipped。

沿用已由用户确认的My Workspace `tea-datl248u01pc739j09eg`，请求级workspaceId只读查询Render：latest live仍 `dep-dbctfp7avr4c73d17apg`，source `87fdcda352179bcaf224393567580b3c3897027c`（PR#106）。当前会话fallback未选workspace，显式确认ID查询成功；未切换会话上下文，未触发部署。该结果不是本轮main后端部署或新HTTP健康/浏览器验收。

API0.18.50/schema0029不变。公共样例只读，OIDC/真实身份/实际业务提交关闭，公司内网未部署。不改身份、秘密、凭据、计费、CI/调度/部署权限、迁移或Seed；审批通过不等于正式发布。业务36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/40/0，验收增量0。
