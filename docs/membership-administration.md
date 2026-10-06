# 项目／软件角色暂停与恢复 — API0.18.30

此包是审计授权管理的首个切片。仅变更已有 ProjectMembership 或
SoftwareMembership 的 ACTIVE/SUSPENDED 状态；角色、身份、项目／软件关系
及全局管理员分配不变。没有新增密码、提供方、首个管理员或公开管理页面。
公共测试环境保持只读，真实提供方和管理员操作验收仍待完成。

## HTTP 契约

`POST /api/v1/security/admin/memberships/{scope}/{membership_id}/status`

scope 只允许 PROJECT 或 SOFTWARE，membership_id 必须是已有授权行的 UUID，
不是用户 UUID 或项目 UUID。请求禁止额外字段和客户端指定操作者。

```json
{
  "event_no": "ADM-change-20261006-001",
  "expected_status": "ACTIVE",
  "status": "SUSPENDED",
  "reason": "暂停该项目角色以进行权限复核"
}
```

- 必须启用 OIDC、通过签名/issuer/audience/有效期检查，且当前身份为 ACTIVE。
- 每次操作（含重试）在事务中复核精确本地身份和 PLATFORM_ADMIN 分配。
  无管理员角色返回403；提供方未启用返回401，绝不退回演示写入。
- READ_ONLY_MODE=true 返回403 read_only_mode，管理员接口没有会话控制的例外。
- 如提供 X-Browser-Session，必须属于当前身份、绑定同一令牌且未过期/撤销。
- event_no 为1–50个字母数字及点/下划线/冒号/连字符；首字符字母或数字。
  reason 为去除首尾空白后的5–500个可打印字符，不应填写令牌或其他秘密。
- expected_status 和 status 只允许 ACTIVE/SUSPENDED，且必须不同。错误输入422。
  预期状态不匹配409 membership_status_conflict；不存在或错误scope的授权行404。
- 恢复 ACTIVE 时目标身份须仍为 ACTIVE，否则409 recipient_inactive；可暂停
  停用身份的遗留角色，但这不会重新启用身份。
- 响应和所有正常拒绝均 private,no-store、Pragma:no-cache、Vary:Authorization。

响应包含 membership_id、scope、applied_status、current_status、replayed 和
 audit_event_no。applied_status 是原请求的结果；current_status 是本次锁定行的
现状。首次变更replayed=false，完全相同请求重试true；不同操作者、目标或内容
复用同一event_no返回409 audit_event_conflict。命名键在整个审计表内唯一。
旧暂停请求在后续恢复后重试，仍报告原应用状态和当前ACTIVE，不能再次暂停。
没有独立管理结果查询API；重试本身可查询已提交事件。

## 数据和并发保证

事务先锁当前管理员身份及其全局分配，再锁精确授权行，状态变更与
MEMBERSHIP_STATUS_CHANGED 审计事件同事务提交。审计包含当前认证操作者UUID、
显示名、目标授权/身份/范围UUID、角色、前后状态及原因。无令牌、邮箱或
身份提供方subject复制。异常回滚状态和审计，失败后可原键重试。
不同管理员竞争同一授权行由PostgreSQL行锁串行化；后来的旧状态请求冲突。
这只是状态前提，不是单调版本号；经历ACTIVE→SUSPENDED→ACTIVE后，新的
ACTIVE前提请求仍可生效。暂停影响后续权限检查，不取消已经通过授权的在途
业务事务，也不撤销其他角色、全局管理员权限、实体刷写或提供方Bearer令牌。

无schema变更，仍为0019_browser_sessions。授权状态行是当前投影；审计事件
保持追加式历史，不能将直接SQL维护当作本接口的审计证据。

## 验证与后续

签名HTTP回归覆盖两种scope、状态冲突、目标/操作者/内容绑定、重试后恢复、
认证拒绝、禁用身份、只读门禁和审计故障回滚。独立真实PostgreSQL用两个
管理员和两个数据库事务证明阻塞、冲突及单条审计。CI必须无跳过。

下一切片：有界管理员授权目录与精确详情，随后身份登记/停用、授权新增、
全局管理员和首个管理员恢复策略；这些都需要审计、幂等和并发设计。
管理界面采用默认中文/可选英文，实际操作仅在批准的受控环境验收。
