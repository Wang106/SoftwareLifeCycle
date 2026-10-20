# 发布链撤销受控提交与原审计恢复设计审查

本审查基于 main `74fa2e694c56da7ea7eeb4e0f0d080cde4a2fb21`（PR76），API `0.18.45`，唯一迁移头 `0026_release_chain_revocation`。只定义后续实现契约，不增加路由、迁移、提交入口或配置，不代表真实提供方/多用户验收。公共演示只读，OIDC、真实提交和公司部署保持关闭。

## 1. 实际实现与缺口

| 对象 | 现有 POST（前缀 `/api/v1`） | 实际范围角色 | 审计 action |
| --- | --- | --- | --- |
| RELEASE | `/releases/{target_id}/revocations` | DISTRIBUTION_AUTHORITY | RELEASE_REVOKED |
| DELIVERY_PACKAGE | `/deliveries/{target_id}/revocations` | DISTRIBUTION_AUTHORITY | DELIVERY_REVOKED |
| DISTRIBUTION | `/distributions/{target_id}/revocations` | PRODUCTION_AUTHORITY | DISTRIBUTION_REVOKED |
| AUTHORIZATION | `/authorizations/{target_id}/revocations` | PRODUCTION_AUTHORITY | AUTHORIZATION_REVOKED |

证据：`backend/app/api/revocations.py`、`backend/app/services/revocation.py`、`backend/app/models/revocation.py`、`backend/alembic/versions/0026_release_chain_revocation.py`。Delivery 使用精确包 UUID，不能以包号替代修订；授权类型名是 AUTHORIZATION。认证与范围授权仍由现有中间件及 authorize_* 执行，客户端不能声明角色。

当前正文只有 request_id/reason，Pydantic 默认忽略额外字段；服务 trim 原因并绑定 target_kind/target_id/reason 的原审计请求。根到叶锁序 Release→Package→Distribution→Authorization；精确重放在当前 eligibility/effective decision 检查前返回，原 actor 四字段必须匹配。同事务写唯一永久撤销账本与 `EVT-RCR-{request_id.hex}`，一目标最多一条，不复活、不制造子撤销、不改变已有生产事实。响应始终 201（包括重放），附带的是**当前** governance，不能拿它证明原请求的审核上下文。

当前新命令只检查当前有效 RELEASE 决策，没有调用方审核过的 snapshot/decision/祖先路径比较；提交前显示和锁内生效可能不同。现有 audit payload 有 revocation_id/release_id/snapshot_id/release_decision_id/reason/actor_source/request，但没有完整审核上下文、协议版本、内容哈希或完整父链。因此现有字段不能支持声称已实现的审核绑定。

`GET /api/v1/activity/{event_no}` 已返回完整原审计；不是缺少原审计 GET。`frontend/lib/browser-session.ts` 的 executeReleaseDecisionSupersessionCommand 已采用 session→可选 POST→精确 activity GET→projector 的模式；`browser-auth.ts` 提供独立开关、同源与流式上限。撤销尚无对应严格 projector/transport/proxy。复用基础设施，不新增通用任意 URL 代理，也不修改现有历史审计。

## 2. 推荐先补审核绑定，再做浏览器协议

比较两案：直接对现有 request_id/reason 做前端确认，改动少，但无法检测审核后决策变化；增加可选、版本化 expected_context 并在现有锁内比较，能提供明确冲突与可恢复原证据。选择后者。仅以展示时 GET 或 POST 后当前状态补验不具备原子性，不接受这种降级。

拟新增 API 可选 `expected_context` 对象（旧客户端省略时保留原语义；新浏览器必填）。对象严格 forbid extras，固定 `version: 1`，包含 release_id、snapshot_id、release_decision_id，以及 delivery_package_id、distribution_id、authorization_id 三个可空 UUID；按目标深度强制 null/非 null，目标 UUID 必须等于相应节点。所有 UUID canonical lowercase，正文 request_id/reason 及 expected_context 也 forbid extras。原因由准备层 trim 一次、1–4000 字符；浏览器禁止控制字符，后端仍独立校验，禁止静默截断。

准备上下文必须来自服务端解析：扩展既有精确 governance GET 以回显 target_kind/target_id 和 review_context（无有效 RELEASE 决策时不可提交）；既有字段不删除。resolver 最多四节点，不扫描整条发布历史；一次读取只提供观察，锁内仍须重读有效决策并比较全部 expected_context。Snapshot/decision UUID 是身份绑定，不把它称为文件内容 hash 校验。若以后需 hash，必须在另包明确冻结对象验证与审计字段，不能凭 UUID 伪造 hash。

服务顺序：锁定根到叶→按原 actor/原 request（包括 expected_context）查精确重放→新请求验证当前有效 RELEASE、活跃路径及 expected_context→插入账本→同事务追加完整审计→commit。精确旧重放不因后来祖先撤销、决策变化或当前资格变化失效；新 request_id 则重新检查。授权仍在进入服务前执行，失权后不能通过 POST 绕过授权。碰撞/上下文变化/审计失败回滚全部业务与审计，释放锁；保留原唯一约束与旧写者 guard。

新版本 payload.request 保存包含原 expected_context 的准确 canonical 请求；顶层保存相同上下文与 `protocol_version: 1`，并验证与账本 snapshot/decision、目标/父链一致。legacy 请求仍保存原三字段 request，不能无条件增加 null 键破坏原请求重放；旧审计没有新版本字段时不补写、不推断审核绑定。无需改账本列，预计无需新 migration；若实现发现需要改变约束，停止该实现包并单独评审迁移，不能修改 0026。

## 3. 默认关闭的窄浏览器协议

拟采用固定 kind→固定 API 路径映射，一个严格 discriminated command，禁止任意 URL/actor/roles/headers。command 只含 operation=`release-chain-revocation`、target_kind、target_id、body={request_id,reason,expected_context}；expected_context 为上节 v1。使用冻结对象；确认后任何编辑都须生成新审核而不是改动发送中的请求。

拟新增 `RELEASE_CHAIN_REVOCATION_SUBMISSION_MODE=enabled` 与 `RELEASE_CHAIN_REVOCATION_APPROVED_API_BASE_URL`、`RELEASE_CHAIN_REVOCATION_APPROVED_APP_ORIGIN` 三项独立精确匹配；默认缺失即关闭，不复用别的命令开关。本包和后续代码包都不配置这些真实值。沿用 authConfig、加密 httpOnly 会话 cookie、同源 POST、application/json、严格 UTF-8、Content-Length 和实际流式字节双上限、no-store、redirect:error 和超时。原因可达4000个多字节字符，完整 envelope 上限拟定24KiB（按真实编码字节），不可照抄8192导致合法中文边界不可提交。原审计响应上限独立有界，建议64KiB；测试最大合法中文正文及超限拒绝。

拟建 `/auth/release-chain-revocation` 和 `/auth/release-chain-revocation-receipt`，都只接受同源 POST，恢复正文不放 query。submit 必须存在有效认证会话且非 read-only；recover 允许有效只读会话作只读原审计检查，不能要求现时写权限来证明历史，但现有认证/读取策略仍有效。代理只向四条固定撤销 POST 发一次准确 body，然后读取一个固定 EVT-RCR；任何后端201/200都必须经严格原审计确认才输出 confirmed。接口 deny/角色策略不能由 UI 的 ACTIVE 状态替代。

## 4. 唯一成功证据与 unknown 状态

projector 校验：event_no=`EVT-RCR-{request_id.hex}`；event_type=RELEASE_CHAIN_REVOCATION；entity_type=target_kind；entity_id=target_id；action 为表中精确值；entity_ref=`RCR-{request_id.hex}`；payload.revocation_id=request_id；detail/reason/request.reason 与原原因完全相等；payload.request 精确字段/值包含原审核上下文；protocol_version=1；顶层上下文等于原 expected_context；actor_principal_id 等于当前认证 principal，actor_source=AUTHENTICATED_PRINCIPAL，declared_actor_name=null，actor 字符串/时间/UUID 有界合法。actor 来自 resolve_actor(request)，不由请求声明；恢复不要求与当前显示名相同，人员改名不能重写原 actor。输出只白名单原审计字段和原请求，不透传任意 payload、token 或 cookie。

当前治理状态、同目标其他人的撤销、同 UUID 不同原因/上下文、伪造 principal、缺失 request、新旧协议混淆均不能确认。旧三字段审计仅能作为明确标识的 legacy 历史展示；不得把它升级为 v1审核成功回执。恢复旧命令需独立 legacy projector 与明确标签，后续若未实现就返回 unsupported/unknown，不偷偷降级。

状态机 idle→sending→checking→confirmed/rejected/unknown；网络超时、重定向、5xx、坏JSON、审计缺失/不匹配一律 unknown，不推断未写入。unknown 锁住 request_id/原因/目标/上下文；仅允许显式 audit-only recovery，一次 session检查及一次精确 GET，绝不 POST、自动重发、轮询、重新分配 UUID。原审计404表示本次未找到证据，不证明未提交；之后禁用/失权/冲突仍保持 unknown，不清空原命令。明确未发送的本地拒绝可 rejected；发送后不确定不得被后续拒绝覆盖。

中英文确认页分别显示目标种类、精确 UUID/包修订、原状态、永久撤销后果、上下文与原原因；结果写“原撤销已记录”，不能写“正式发布”“可生产”。审计恢复显示原记录时间/actor和原上下文，当前状态另栏且不得充当回执。导出/导入仅包含版本化原 command，无凭据；导入总是 audit-only，不能恢复成可发送草稿，重载/换会话不自动提交。真实多用户桌面/手机与中英文验收需批准提供方环境，mock或SSR不替代。

## 5. 验证矩阵与实施顺序

| 范围 | 必须验证的正反例 |
| --- | --- |
| 后端兼容 | legacy精确重放、空白规范化、v1严格字段、四种角色及跨范围拒绝；未授权/只读无写入；父链或决策变化409、目标/上下文错配拒绝 |
| 原子审计 | v1全部原字段/actor绑定；同key改原因/上下文/actor冲突；审计异常回滚无孤立账本；同请求仅一账本一审计 |
| 真实 PostgreSQL | 两独立连接同key并发；不同key同目标竞态；祖先撤销与后代许可竞争；审核后决策替代与撤销串行化；最终赢家审计与锁顺序一致，无skip |
| 重放与历史 | 后来祖先撤销/决策变化后原请求重放仍准确；legacy审计不改写；当前状态变化不改变原回执；长无关历史下仅有界四节点+精确事件 |
| schema/Seed | 唯一头0026；旧库→head/空历史降级→升级及有撤销拒绝降级既有完整CI继续执行；Seed重复不写历史；无新迁移时不可宣称执行了新迁移 |
| 代理与transport | 关闭三开关任一缺失零上游写入；跨源/GET/错误类型/UTF8/字节超限拒绝；四路径白名单；假成功/receipt字段缺失/异人actor拒绝；recover零业务POST；unknown禁止send |
| 双语UI与恢复 | 精确确认、重复点击、编辑失效、超时、404保持unknown、关开关/失权后原command保留；转义原因/actor；导入只读且不泄露凭据；最长中文正文通过 |
| 完整验收 | 精确PR head包含最新main，backend/PG、frontend/Next/OpenNext、CI acceptance三job成功；合并后另核main CI、Cloudflare、Render；skip明确标识 |

下一包 **release-chain-revocation-review-binding-backend**：仅 `backend/app/api/revocations.py`、`backend/app/services/revocation.py`、`backend/tests/test_release_chain_revocation.py`、`backend/tests/test_release_chain_revocation_postgres.py`，必要的API版本 `backend/app/core/config.py`，以及本设计/状态/交接/进度。验收上表后端、原子、PG、legacy重放、resolver有界及既有迁移完整CI；不做浏览器、身份或配置写入。治理GET须回显精确目标及可审核context，POST须锁内比较，v1审计可独立恢复。

随后独立包 **release-chain-revocation-browser-protocol**：新增 `frontend/lib/release-chain-revocation-transport.ts`、`frontend/lib/release-chain-revocation-audit.ts`，修改 `frontend/lib/browser-auth.ts`、`frontend/lib/browser-session.ts`，新增上述两条 `frontend/app/auth/.../route.ts`，对应transport/proxy/audit测试和禁用路由检查（若检查器须变更，明确仅扩展覆盖、不削弱门禁）。后台契约未通过前不开始。再以 **release-chain-revocation-ui-recovery** 实现双语 workbench、精确 governance页入口、i18n、audit-only导入/导出和UI测试。三个小包不得并发覆盖同一工作；任何包不启用真实开关。生产事实更正、OIDC提供方/真实多用户验收继续独立待定。
