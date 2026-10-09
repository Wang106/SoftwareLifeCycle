# Test Release、Deployment、Changeover 提交与原审计恢复
更新：2026-10-09（Asia/Shanghai）；Codex。

## 独立默认关闭门控
POST /auth/production-command提交，POST /auth/production-command-receipt查询原审计；GET均405。只支持test-release/deployment/changeover。
PRODUCTION_COMMAND_SUBMISSION_MODE=disabled、PRODUCTION_COMMAND_APPROVED_API_BASE_URL、PRODUCTION_COMMAND_APPROVED_APP_ORIGIN。仅明确enabled、有效OIDC/加密会话和精确批准HTTPS API/应用绑定才开放；首批/治理/分发/管理员及NEXT_PUBLIC开关不能开放此通道。所有响应private/no-store。没有配置实际变量、身份、权限或秘密。
唯一当前token-bound USER复核/me；提交需非只读，恢复可在只读后查询自己的原操作。后台独立验证Release CONTRIBUTOR或精确PRODUCTION_OPERATOR范围；active_grant_counts和声明不授予权限。

## 固定请求、严格解析与原审计
外层严格operation/target/body，正文严格既有prepare字段和request_id；不允许caller URL/path/headers/credentials。
Test Release target是Release UUID，须匹配正文release_id；snapshot_id必须明确，purpose_scope只允许SOFTWARE_TEST/BATTERY_TEST/CUSTOMER_TEST。声明actor_name和reason按已有前后端契约去除两端空白；不以声明代替认证身份。
Deployment target是Authorization UUID，须匹配authorization_id；production_line_id和deployment_no明确。
Changeover target是已有Deployment编号，from_release_id必须明确；不从当前actual报告猜测上一版本。changed_at必须显式null或带秒和时区的合法时间，规范UTC；note保留原文或显式null，空字符串拒绝。
同源JSON/严格UTF-8、声明及流式正文上限8192字节；回复/审计读取16384字节，15秒、no-store、拒绝重定向。
后台固定路径：POST /api/v1/testing/releases、/api/v1/deployments、/api/v1/deployments/{原编号}/changeovers。
Test Release创建HTTP201，既有重放HTTP200；Deployment/Changeover均HTTP201。正确HTTP之后仍须原审计确认，不按HTTP200推断replayed，不按业务POST回复中的当前状态推断原结果。

## 精确原回执
只GET /api/v1/activity/{原事件编号}，不查询当前业务对象，不以POST回退恢复。
Test Release：EVT-TR-{带横线UUID}；核对当前principal UUID、AUTHENTICATED_PRINCIPAL、TEST_RELEASE/CREATE_DRAFT、原entity/key/编号、release/snapshot/purpose、declared_actor_name和detail。既有审计没有request字段，本通道按真实原字段校验，不伪造历史指纹。回执保留DRAFT、原冻结snapshot_no、原声明及原因；不代表测试通过、激活或分发/生产授权。
Deployment：EVT-DPLOY-{无横线UUID}；原request精确deployment_no/authorization_id/production_line_id，原结果PENDING与expected_release_id/expected_snapshot_id。创建期望不报告actual软件、不执行刷写。
Changeover：EVT-CO-{无横线UUID}；原request精确deployment_no/changeover_no/from_release_id/changed_at/note。request的UTC时间使用Python既有秒或六位微秒格式；null保持null。原结果COMPLETED、deployment/authorization/from/to及审计occurred_at，省略时间保留原服务器生成值。回执时间规范UTC并保留全部六位微秒；明确请求时间须精确相符，原from/to不得相同。COMPLETED仅证明记录，不证明物理刷写或更新actual报告；一般撤销/更正尚未完成。
只有白名单字段，无token/subject/任意payload/current_status/replayed。后台后来改变状态，不改变本回执的原应用值。

## 冻结控制器及限制
ProductionSubmission仅接受布尔确认及可重构的原path/trace/audit/body。两个UUID目标从正文取值，Changeover从既有固定路径恢复原Deployment编号；构造后验证全部链接及正文。
同步发送/查询互锁、confirmed终态、冻结原ID/target/JSON字节，无自动重试。明确查询只GET原审计，明确重试才重复原字节业务写入。丢失回复、未知HTTP、缺失/拒绝/不匹配审计保持unknown；后续门禁或业务拒绝不能抹除先前未知事实。
代理、严格解析/原回执及控制器和三类双语确认发送/原审计查询/明确重试/精确结果已接入 /commands。页面productionSubmissionConfigured独立门控和唯一当前USER会话只投影两个布尔能力；凭据不传客户端。其他命令门控不能开放本通道或覆盖未知原请求。原请求在表单、命令、上下文和能力刷新后冻结；只有confirmed或首次明确rejected允许重新准备。复制/发送/查询同步互锁，业务详情与原审计链接独立新标签读取，测试发布附原冻结Snapshot链接。结果保留原DRAFT/PENDING/COMPLETED与六位UTC微秒，不以当前详情推断原操作结果。仅页面内存，不支持跨卸载/刷新/会话导入恢复；beforeunload不能保证应用内路由提醒。十一类代理/控制器及十一类UI已有；剩余Impact/Acceptance/Resource代理及三类UI。
公共样例保持只读；OIDC及全部提交默认关闭，真实提供方/浏览器/管理员/内网验收未完成，内部服务器尚未安装，不重试被拒绝浏览器访问。SSO、人员、Windows无Docker及CPU架构仍待确认。
