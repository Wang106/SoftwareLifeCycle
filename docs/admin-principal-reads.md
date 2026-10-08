# 管理员身份私有读取（API 0.18.36）

本包增加身份目录、UUID 精确详情和身份状态历史。前端身份管理页面、激活/禁用请求准备与受控发送尚未接入。schema 仍为 0020；没有创建实际身份、授权或提供方配置。

## 契约

| GET 路径 | 查询 | 返回 |
| --- | --- | --- |
| /api/v1/security/admin/principals | principal_id(UUID)、principal_type(USER/SERVICE)、status(ACTIVE/DISABLED)、limit、offset | SQL 分页目录 |
| /api/v1/security/admin/principals/{principal_id} | 无 | UUID 精确单项 |
| /api/v1/security/admin/principals/{principal_id}/history | limit、offset | 状态历史分页及 current_status |

limit 默认50、范围1–100；offset 默认0、范围0–100000。未知查询项、无效枚举/UUID/范围返回422。目录按 UUID 升序，history 按 occurred_at/id 双降序；页外返回空 items、准确 total 和 next_offset=null。详情和历史未知身份返回404 principal_not_found；不会通过姓名、subject、邮箱或授权行推断 UUID。

目录直接从 SecurityPrincipal 投影，所以新注册的 DISABLED、尚无任何授权的 USER/SERVICE 也可检索。每项仅含 id、principal_type、display_name、status、created_at、issuer_matches_configuration、admin_principal_protected、status_history_supported。issuer_matches_configuration 只表示当前配置的 issuer 是否相同，不代表批准提供方、可登录、授权生效或可以修改。admin_principal_protected 查询任何 PLATFORM_ADMIN assignment，包括 SUSPENDED 历史授权，与现有状态命令保护一致；它是读取快照，提交时仍需独立检查。

history 只覆盖 PRINCIPAL_STATUS_CHANGED，同时匹配 entity_type=SECURITY_PRINCIPAL、entity_id 和字符串 entity_ref。注册事件、其他类型/目标/引用不会混入。每条仅含审计 id、event_no、action、occurred_at、actor_principal_id、actor_display_name、expected_status、status、reason、reason_truncated。未知 before/after 状态投影为 null；reason 在 SQL 截取至500字符。原始 payload、subject、issuer、邮箱、token、注册摘要和会话撤销总数不返回。该历史不宣称是完整身份生命周期或提供方审计。详情和历史分别读取，不保证同一事务快照；current_status 是读取时的本地状态，不能替代冻结 expected_status 的写入前置条件。

## 安全与验收边界

所有读取要求 OIDC 签名/受众校验、当前 ACTIVE 本地身份和 ACTIVE GLOBAL PLATFORM_ADMIN。没有演示读取回退。普通 bearer API 可以不携带浏览器会话；若携带 X-Browser-Session，则必须 UUID有效、属于本人、绑定同一 token、未过期且未撤销。返回 Cache-Control: private, no-store、Pragma: no-cache 与凭据相关 Vary，包括错误响应。read_only_mode 下授权管理员可读取，但不能凭读取放开写入。读取不写审计。

采用 SQL 标量投影、SQL count/limit/offset、相关 EXISTS 保护标记，不展开授权或审计 ORM 图。测试在 SQLite 和隔离真实 PostgreSQL 上覆盖签名/权限/会话、禁用无授权身份、精确过滤、分页、管理员保护、真实状态命令历史、噪声排除、字段截断、排序和增长。目录/详情/history 三次无会话头读取固定15查询，增长110身份/审计后保持相同。

API版本是代码版本；本包前端提供方部署证据不能证明后端真实部署或 API 0.18.36 在线。真实 OIDC/管理员/浏览器验收、内部服务器部署和离线安装演练均未完成。公共环境仍只读、OIDC和提交通道默认关闭。进度里程碑不提升。
