# 授权状态服务器提交通道

新增 POST /auth/grant-status，仅作为服务器端基础；授权详情页面仍只准备/确认/复制，不提供实际发送。它代理既有6管理员命令中的3类授权状态路径，不新增后端业务命令或数据库迁移。

## 默认与门禁
默认返回503 grant_submission_disabled，不调用后端。仅当以下服务器配置全部匹配时才进入身份/输入检查：
- GRANT_STATUS_SUBMISSION_MODE=enabled。
- 既有 BROWSER_OIDC_MODE=code、BROWSER_SESSION_MODE=encrypted 和完整有效提供方/会话配置。
- GRANT_STATUS_APPROVED_API_BASE_URL 与 sessionConfig 的规范 API_BASE_URL 完全相等。
- GRANT_STATUS_APPROVED_APP_ORIGIN 与会话应用 origin 完全相等。

批准变量只是部署者的显式配置确认，不是替代公司审批的技术证明。未设置任何真实环境变量、秘密或身份。不得在公共演示启用。GET 返回405 Allow: POST。响应 private,no-store / Pragma:no-cache / Vary:Cookie / no-referrer / nosniff，无开放跨源授权。

## 请求与身份
同源 URL、Origin 和 Sec-Fetch-Site 检查；same-site/cross-site 拒绝。只接收 application/json，声明和流式正文限制8192字节，拒绝额外字段。正文仅包含：
```json
{"scope":"PROJECT","grant_id":"12345678-1234-1234-1234-123456789abc","event_no":"grant-state-001","expected_status":"ACTIVE","status":"SUSPENDED","reason":"Reviewed exact grant"}
```
scope 只能 GLOBAL/PROJECT/SOFTWARE，目标是精确UUID；状态只能 ACTIVE/SUSPENDED且必须改变；审计编号1–50 ASCII字符；原因修剪后5–500 Unicode码点，无C0/DEL。浏览器不能提供 actor、token、URL 或 session ID。

服务器读取唯一加密会话cookie，复核 token-bound 后端会话与当前 USER 身份，read_only_mode 拒绝。服务器向固定API路径附带自己的 Bearer 和 X-Browser-Session；不把凭据返回浏览器。后端仍独立执行管理员权限、actor/issuer/session、并发预期状态、actor绑定幂等、最后管理员保护和原子审计。grant count 不作为写权限判断。

## 回执与未知结果
成功回执校验 scope、目标UUID、原审计编号、applied_status 与 replayed；仅投影 grant_id、scope、audit_event_no、applied_status、current_status、replayed。当前观察状态可以与原请求应用状态不同，二者不能合并解释。
401/403/404/422与白名单409返回通用/受控原因；不泄露后端自由文本。POST后的超时、网络故障、5xx、重定向、过大/无效/不匹配回执均返回502 outcome_unknown，不主张未发生写入，不自动重试。
后续UI恢复应保留冻结原编号和正文；可由仍有权限的同一管理员重放确认。新编号可能产生第二次操作，不用于未知结果自动恢复。自身管理员暂停后重放/读取可能被拒绝；不能承诺同一人始终可恢复，需要其他管理员或既有审计离线恢复。

## 验证范围
加入模式/目标、同源、输入、会话撤销/重复cookie、只读、3路径凭据隔离、后端拒绝/冲突、回执替换、Unicode和未知结果/重放测试；生产构建后的禁用路由也纳入 auth:check。
真实提供方、实际管理员、实际浏览器和内网部署未验收；内部服务器尚未开始部署。CI证据见 DEVELOPMENT_STATUS.md 和 HANDOFF.md 最新记录。
