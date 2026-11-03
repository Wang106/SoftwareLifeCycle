# B2 双人生产授权：隔离浏览器设计与验收矩阵

日期：2026-11-03。基线 main `e9710f6e9a1b83b4a820367ff230f58826ce1be9`（PR173）。本包仅设计，不实现浏览器 harness、身份旁路或审批功能；没有运行新的 B2 浏览器用例。设计完成不计 B2 完成，浏览器技术阶段仍为1/4，总体36/44=82%，业务验收增量0。

## 现有证据与缺口

PR173 head `f0c2bb2976e7e2910bf11cda72d5e489345207e7` 的 [CI41470124325](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/41470124325) attempt1通过四个job：2069前端、2846后端＋26子测试、296 PG用例无跳过、84守卫契约、0029迁移往返和八条Chromium旅程。实际checkout是合成合并提交 `9cfb1b5c4584b140f1c6c516f9b5894663fe307e`。这些是PR173证据，不是本设计未来提交的CI。协调审查另核实新main [CI41575618360](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/41575618360) completed/success，Cloudflare production build `832b3f44-40c4-407c-953e-b9b17d771496` success，version `c4f7d68d-de22-4aa5-9975-8948c6bd58f4`；Actions deployment/continuation skipped，线上数据库与业务健康未验收。

双人规则与工作台已经实现。本包不再实现已有功能。当前 `frontend/tests/authorization-approval-workbench-ui.test.cjs` 使用静态渲染和模拟hooks，不是浏览器；后端真实PG测试也不证明浏览器或真实人员登录。原八条真实浏览器是匿名只读、合成API旅程，不是B2。

## 权限事实矩阵（以现有后端为准）

固定合成授权目标T属于项目P，可信创建者A，另一个批准者B。以下是未来用例的预期，不是新测试结果。

| 身份/条件 | 私有context / 首次approve / 原始receipt | 证据依据 |
| --- | --- | --- |
| A：ACTIVE USER，P的ACTIVE PRODUCTION_AUTHORITY，可信创建者 | 三者均拒绝自批相关访问，403 creator_cannot_approve | `_load`及`test_creator_admin_only_foreign_scope_and_service_cannot_approve` |
| B：另一ACTIVE USER，P的ACTIVE PRODUCTION_AUTHORITY，当前会话有效 | context要求DRAFT与有效链；approve还要求非只读和精确digest；receipt仅本人原始审计 | `_load`、`_context`、`approve`、`receipt` |
| C：只有平台管理员，无P角色 | 403 production_authority_required；不授予隐式例外 | 同上；管理员即使另有P角色也不能批准本人创建 |
| D：其他项目或其他角色、失效成员资格 | 拒绝；重放和receipt查询同样重新核验 | `test_current_identity_and_scope_required_before_original_replay` |
| SERVICE / inactive principal / 无身份 / OIDC关闭 | 拒绝；不得退回匿名或样例身份 | 服务及真实middleware测试 |
| 声明的浏览器会话过期/撤销/不匹配 | 拒绝；不能用历史请求或digest恢复当前权限 | `test_browser_session_revalidated_before_replay` |
| 未知创建者、伪造/不匹配创建审计的DRAFT | trusted_creator_required；不补写虚构provenance | `test_untrusted_or_missing_creator_evidence_fails_closed` |
| read_only_mode=true | 可在权限满足时读context/receipt，不可approve | `test_read_only_allows_private_context_but_never_approval` |
| 批准后上游撤销 | 不产生新批准；有效当前权限下可查询原始结果，但不表示当前可部署 | `test_historical_receipt_does_not_undo_later_revocation`及receipt测试 |

完整来源：[服务](../backend/app/services/authorization_approval.py)、[服务/路由测试](../backend/tests/test_authorization_approval.py)、[并发PG测试](../backend/tests/test_authorization_approval_postgres.py)、[回执测试](../backend/tests/test_authorization_approval_receipt.py)。`require_browser_session`的既有条件语义保留：浏览器链声明的会话必须重验，不将此表误解为修改所有非浏览器调用的政策。

可信创建证据必须是精确 `EVT-PA-{authorization UUID hex}`，包含已认证actor、原对象与原始业务事实；显示名称不是身份。digest只是并发条件，不授予权限。相同request UUID只能按原actor、目标、digest、reason精确重放；唯一审计和状态原子提交，不能以当前APPROVED状态冒充原始成功。旧seed/import APPROVED语义保留，不补造双人回执。

## 分层证据与推荐接续

1. **组件浏览器层（建议下一实施小包）**：仅测试产物中挂载现有真实React工作台、i18n和transport，真实Chromium DOM及事件，固定合成API响应。可证明交互、重复点击互锁、请求字节和历史结果文案；不能证明真实Next路由、OIDC、会话加密、FastAPI权限或PG原子性。合成A/B只是测试角色标签，不是已认证用户。
2. **现有协议/服务层**：真实前端handler组合与session协议单测，后端middleware/服务/PG测试承担相应边界。测试通过是分层证据，不得拼称一次完整端到端登录批准。
3. **完整Next认证链（独立后续设计）**：真实SSR页、加密cookie、代理、受控身份服务与API。需先决定可信HTTPS测试拓扑、会话建立方式和隔离证明，不在本设计内配置。未完成则B2完整身份链保持未验收。
4. **真实人员/提供方/公司目标**：另有明确目标、人员分配及授权；合成证据不能替代。保持未验收，不创建真实账号、角色或持久凭据。

现有 `frontend/e2e/fixture-server.cjs` 把全部 `_MODE` 强制disabled，以 `/auth/session=503`作为ready；匿名HTTP loopback无法直接启用审批。真实审批页要求authConfig和resolveSession；`browser-session.ts`要求HTTPS API/app origin、加密绑定和当前身份，`browser-auth.ts`还要求OIDC HTTPS配置及精确审批approved origin/API。不能为测试放松这些限制、给生产页面直接注入USER、添加生产test-login路由、设置ignoreHTTPSErrors、禁用TLS校验或改变系统信任。

下一实施小包先验证独立组件harness是否能只用现有依赖构建，产物在临时目录且不进入Next/Worker生产输出。不可为了让构建通过改生产身份逻辑或偷偷增加依赖。若必须新增依赖/CI能力/可信HTTPS设置，应先报告差异并另界定范围。本包没有选择或实现具体构建器，因此不存在已完成harness的承诺。

## 下一实施小包的可执行验收设计

| 编号 | 浏览器操作与合成响应 | 必须观察到的证据 |
| --- | --- | --- |
| B2-C1 | A显式请求context，合成API返回后端对应403 | 展示拒绝；没有可确认批准体、无批准POST；只证明拒绝处理，不声称浏览器执行了后端自批判断 |
| B2-C2 | B加载固定T合法context，填写原文reason，准备并确认 | 17个scope/provenance字段正确；生成独立UUID并冻结digest、target、reason；未确认前无批准POST |
| B2-C3 | 批准POST被挂起时连续点击 | 仅一次组件到代理的批准POST、原字节不变；收到200且合法receipt后直接confirmed，不自动再查receipt。组件核对target/UUID/digest/reason、creator和不同于creator的合成approver UUID；不声称核验真实登录actor |
| B2-C4 | 显示原始APPROVED receipt，中英文切换 | 表明是历史批准，不证明当前有效、部署或正式生产；raw标识/reason不被翻译或HTML解释 |
| B2-C5 | 无能力或只读能力 | 默认关闭不自动访问；无写入能力，允许的恢复查询不得调用批准POST |

成功链须分层记录：`AuthorizationApprovalSubmission`调用`projectAuthorizationApprovalReceipt`时不传`principalId`，合法200回执直接进入confirmed；组件没有已认证actor依据。真实服务端`executeAuthorizationApprovalCommand`先resolveSession，向后端提交成功后再GET严格receipt，并两次使用`identity.principal.id`校验回执。该服务端GET不属于组件自动请求，未来组件fixture也不证明它实际发生。显式恢复另用组件receipt POST→服务端receipt GET，不能与成功提交计数混淆。

组件到same-origin代理的context与receipt请求本身使用POST，这是现有浏览器协议；到后端API的context/receipt才是GET。请求计数必须区分这两层，不能把所有POST都算业务写入，也不能放行通用POST。固定target及精确三条前端代理路径、静态资源白名单；未知方法/路径/外域/重定向/WebSocket即失败。合成接口不得连接真实API、数据库或提供方。日志只留固定合成标识、方法、次数和必要结果，不保存cookie/token/真实reason。

保留原八条真实Next浏览器用例、固定Chrome信任检查、sandbox=true、零重试及完整CI门禁。若新增组件suite，它必须独立明确标注报告，不能冒充或替换原Next用例。只有实际执行且严格报告通过才写浏览器通过；发现列表或静态编译不够。未知结果、取消、刷新、后退、导入恢复的扩展留B3，权限全面覆盖留B4，不无限扩大B2-C小包。

## 本设计通过条件与停止条件

- 文档引用的源码/测试实际存在；权限矩阵与服务一致；保留17个context事实和现有协议方法。
- 仅修改设计/交接/进度元数据，不改生产源、测试、依赖、迁移、CI、默认模式或安全设置。
- 运行进度账本检查、内部链接/范围检查及diff空白检查；记录未运行的浏览器/PG/完整CI，不能称全量验收。
- 用户随后批准本次6文件上传、创建草稿PR及现有CI运行；发布后核验精确head CI，保持草稿。合并、部署、B2实现和安全配置变更不在本次授权范围。
- 真实身份、公司目标、HTTPS信任或权限设置成为前提时停在设计，不隐含创建或放宽。

七模块100/100演示/100演示/100/89/60/17，七计划100/100/20/33/40/40/0，有限计划8/8不变。公共样例只读；旧库不保留、不重建；真实OIDC/业务写入关闭。参见[后端契约](production-authorization-dual-approval.md)、[工作台契约](production-authorization-approval-workbench.md)、[阶段计划](browser-validation-stage-plan.md)。

## 本地验证记录（2026-11-03）

- `python3 scripts/report_development_plan_progress.py --check`通过，验收groups与原main逐值相同，历史checkpoint链保留；当前main、PR173和本设计本地结果分别存储，不沿用旧job/provider check或旧本地完整测试记录。
- `python3 -m unittest discover -s scripts/ci/tests -v`：84通过，0跳过；仅合成守卫契约，无下载/原生Chrome执行。
- `python3 -m unittest discover -s scripts/automation/tests -v`：52通过；只验证既有自动化契约，不启动任何CI或自动开发。
- 本地精确基线、六个文档/元数据路径白名单、设计内相对链接和引用测试函数存在性检查通过；`git diff --check`通过。
- 未安装依赖、未运行前后端完整套件、PG、Next构建或新浏览器用例；本记录写入时尚未提交、上传或发布；后续发布/CI事实须另核验。上述结果不替代未来提交的完整CI。

独立审查修正：移除当前账本混入的旧main/PR172 job、2048前端数量和旧local_validation；按CI41575618360日志及精确main check-runs重新关联。B2-C3改为组件200合法回执直接confirmed，并明确服务端receipt GET与真实actor校验不属于组件层证据。修正只涉及文档/元数据，无生产行为变更。
