# 身份状态提交代理与原请求重试控制器 — 2026-10-08
模式：Codex。此包新增服务器端代理及客户端内存控制器，尚未将发送按钮、结果组件或内存恢复交互接入身份详情页；准备/确认复制见 [principal-status-preparation.md](principal-status-preparation.md)。这不是实际身份或浏览器验收。

## 独立且默认关闭的门禁
新路由 POST /auth/principal-status；GET 返回405/Allow: POST。缺少完整批准配置时POST返回503 principal_submission_disabled，没有网络请求。门禁不复用授权状态或注册开关，不接受 NEXT_PUBLIC 配置：
- PRINCIPAL_STATUS_SUBMISSION_MODE=enabled（样例文件仍disabled）
- PRINCIPAL_STATUS_APPROVED_API_BASE_URL 必须精确等于已验证 session.apiBase
- PRINCIPAL_STATUS_APPROVED_APP_ORIGIN 必须精确等于已验证 session.origin
还需有效的 HTTPS OIDC/加密会话配置。空值、不同地址、尾随斜杠、仅开启既有授权/注册开关均不能启用。没有实际配置变量、身份、授权或秘密。未来页面能力必须使用同一函数并结合当前/me只读投影，但能力判断不替代后端管理员权限。

## 请求与凭据边界
只接受同源 POST 和 application/json；同时限制声明及流式请求正文8192字节，严格UTF-8，禁止额外字段。正文恰好五项：principal_id、event_no、expected_status、status、reason；UUID规范为小写，审计键1–50允许ASCII字符，状态ACTIVE/DISABLED且必须变化，trim后原因5–500 Unicode码点、拒绝C0/DEL。客户端不能提供URL/path/actor/token/issuer/subject/principal_type或保护/匹配标记。共享解析器同时守住代理和直接服务器函数入口。

当前唯一sealed cookie必须绑定原token、USER身份与注册browser_session_id；服务器再次读取/me，失效/重复cookie和只读身份不能POST。唯一后台路径 /api/v1/security/admin/principals/{uuid}/status，正文只含event_no/expected_status/status/reason；Bearer和X-Browser-Session只在服务器转发。固定API、no-store、redirect:error、5秒后台deadline和16384字节声明/流式响应限制沿用已验证的私有请求层。前端代理所有结果均private/no-store、Vary:Cookie、无referrer，不输出上游任意字段或秘密。

API独立核验当前ACTIVE GLOBAL PLATFORM_ADMIN、保护目标（包括已暂停PLATFORM_ADMIN关联）、精确expected_status、操作者绑定重试、原子审计和禁用时实际会话撤销。issuer匹配不增加新后端条件。启用不恢复旧cookie、授予角色或创建提供方账号；禁用可能撤销零个实际会话，不能凭读取推测数量。

## 精确回执及未知结果
200仅在目标UUID、审计编号、应用状态精确一致，当前状态为ACTIVE/DISABLED、replayed为布尔，revoked_browser_sessions为非负安全整数时成立；启用回执必须为零。后台UUID可规范大小写，代理输出小写；客户端要求已规范的精确UUID。额外credential/subject/payload字段投影掉。重放的applied_status和current_status可不同；撤销计数是原请求回执数据，不推断当前会话数。

401/403/422及已知409受控映射；409未知detail输出submission_conflict；404只有明确principal_not_found才映射身份不存在，普通旧API路由404视为未知/不可用。未知503、5xx、重定向、丢失/超时、断流、编码错误、大小超限或不匹配回执均502 outcome_unknown，绝不自动重试。

PrincipalSubmission只接受明确布尔确认且可重新生成的精确冻结预览。固定/auth/principal-status、same-origin credentials、no-store、redirect:error、15秒客户端deadline；同步sending锁防止重复点击，confirmed终态不再POST。未知后每次明确send保持原目标/编号/正文；随后登录失效/只读/保护拒绝或开关关闭也保留unknown，不能将之前可能已提交的操作说成失败。仅在内存保留原请求，不存凭据，不用localStorage/sessionStorage，不跨刷新恢复，不查询详情冒充原请求回执。每个新控制器独立，不能覆盖旧未知请求。

## 验证与下一步
新增16项解析/冻结/传输/回执/重试控制器回归、11项真实认证辅助函数的模拟代理回归；生产Next检查新增GET405/禁用POST503且private/no-store。4类型/状态传输组合及2服务器状态组合，原UUID/body、Unicode500码点、当前会话、后端拒绝、实际撤销数量、断流和两层响应界限均覆盖。完整CI证据记入HANDOFF；mock/生产SSR不代表真实浏览器或提供方验收。
69页面/API代码0.18.36/schema0020不变；公共样例只读/OIDC/提交通道继续关闭，内网尚未开始部署，后台线上部署和版本未独立核验，Render工作区未明确选择。进度36/44=82%，七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，增量0。
下一包接入双语身份状态发送按钮、精确结果组件、明确原请求重试和页面内存恢复；原详情/history只能独立观察。随后真实管理员/提供方/内网、首批与全部14业务提交、跨会话导入恢复、更正撤销、离线安装与运营迁移；VIN最后。
