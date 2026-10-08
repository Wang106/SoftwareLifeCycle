# 首批业务提交与原操作回执恢复 — 2026-10-08
模式：Codex。本包完成Snapshot／实际软件报告／Batch的服务器代理、冻结传输控制器及模拟回归；`/commands` 页面仍只有请求准备和确认复制，发送/查询/结果按钮尚未接入。不是实际提供方、浏览器或内网验收。

## 独立默认关闭的门禁
`POST /auth/first-command`提交；`POST /auth/first-command-receipt`只查询原操作审计。GET均405/Allow: POST；缺少批准配置时POST均503 first_submission_disabled，无网络。
三个服务器变量：FIRST_COMMAND_SUBMISSION_MODE=enabled、FIRST_COMMAND_APPROVED_API_BASE_URL精确等于已验证session.apiBase、FIRST_COMMAND_APPROVED_APP_ORIGIN精确等于session.origin；样例文件保持disabled和空绑定。必须同时有有效HTTPS OIDC/加密会话配置。既有管理员/授权/注册或NEXT_PUBLIC开关不能开启；没有配置实际环境变量、身份、授权或秘密。
同源检查、精确application/json、声明及流式8192字节正文、严格UTF-8、独立字段白名单。唯一当前token-bound USER会话与/me必须通过；submit要求当前非只读，recover可以在只读切换后查询自己的已提交操作，不执行写入。实际权限与业务状态仍由后台独立验证。

## 原请求与三个固定路径
浏览器输入仅`{operation,target,body}`，operation只可snapshot/actual/batch；不允许URL/path/actor/token/issuer等额外字段。共享解析器重新生成既有prepare契约，UUID小写、业务编号安全编码、显式日历/时区校验；审计request_id必填，不支持较弱的旧无键语义。
- Snapshot：精确release UUID，body仅request_id；后台POST /api/v1/releases/{uuid}/create-snapshot。
- 实际报告：精确deployment业务编号；body为request_id、actual_release_id、actual_snapshot_id、expected_version、correction_reason、deployed_at。expected_version为0–2147483646整数，给PostgreSQL版本递增留空间；原因1–2000字符，不空白，保留原文；时间UTC规范或null。
- Batch：精确deployment业务编号；body为request_id、batch_no、changeover_id、started_at、note。可选UUID/时间/note保持null语义，非空note原文保留；批次不等于物理刷写事实。
Bearer与X-Browser-Session只在服务器固定批准API路径转发；no-store、redirect:error、5秒每个后台请求deadline，声明及流式16384字节响应界限。所有浏览器结果private/no-store、Vary:Cookie、no-referrer，不暴露任意后台字段或错误正文。

## 确认原操作，而非推断当前状态
提交收到正确HTTP状态（Snapshot/Batch201、实际报告200）后，还必须GET精确`/api/v1/activity/EVT-{SN|DA|PB}-{request_id.hex}`。丢失/非法POST响应不会自动重复写入，也不改查当前详情冒充确认。
核对原子审计的event_no、event/entity类型与action、实体ID/ref、当前principal UUID和AUTHENTICATED_PRINCIPAL来源，以及全部原request fingerprint字段。时间按后台UTC isoformat精确比较；缺字段/不同原因或目标/额外fingerprint字段均不能确认。
Snapshot核对request_id实体UUID、release UUID、原快照编号及64位hash；实际报告核对before版本、after版本=expected+1、原实际release/snapshot UUID、原MATCH/MISMATCH；Batch核对request_id实体UUID、batch_no、deployment、changeover及原ACTIVE和release/snapshot UUID。
回执只投影`operation,request_id,target,audit_event_no,result`；原审计的payload/操作者声明/任意秘密不传浏览器。回执没有编造replayed或current_status字段：它证明原操作的审计结果，不证明现时状态或是否本次POST首次创建。原结果可以与后来读取不同。

## 明确恢复与重试
FirstSubmission只接受明确布尔确认且可重构的冻结Review；同步sending/checking锁防双击和写入/查询并发，confirmed终态不再发送。固定浏览器代理路径、same-origin credentials、15秒deadline及16384字节响应界限；不存凭据或浏览器持久化。
明确recover只调用回执代理，后台只GET原审计，不POST业务接口。审计缺失/404、不支持、权限拒绝、断流/超限或原body/actor不匹配均保持outcome_unknown；“暂时查不到”不能证明未提交。查询失败不能转为原操作失败。
明确send重试保持原目标/key/body；未知后遭会话/权限/只读拒绝或门禁关闭，仍保留之前未知事实。首次明确拒绝只描述该次尝试，不证明历史上此key从未提交；需要时仍可recover。不自动重试，不查询任意URL，不以新编号覆盖未知操作。恢复只存控制器内存，跨刷新/会话导入及页面保护尚待接入。

## 验证与下一包
纯解析/冻结/回执/原审计/发送与恢复锁定回归；实际认证辅助函数的provider模拟代理回归，覆盖三类固定路径、当前会话、只读恢复、actor/body不匹配、权限/版本/key冲突和两层响应边界；Next生产禁用路由检查。完整CI和main/provider证据记录在HANDOFF。
69页面/API代码0.18.36/schema0020不变，无后台/schema改动。公开样例只读/OIDC和所有提交默认关闭，内网尚未安装，SSO/系统/架构未确认，真实管理员/浏览器/提供方与后台线上版本未验收。36/44=82%；模块100/100演示/100演示/100/89/60/17，七计划100/100/20/33/40/20/0，增量0。
下一包将首批三类已确认准备接入双语发送、原审计查询/原请求重试和精确结果链接；默认关闭且保护未知原请求。之后真实身份/内网、全部14业务提交、跨会话恢复、追加更正撤销、无Docker离线安装及运营；VIN最后。
