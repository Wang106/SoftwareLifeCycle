# 身份激活／禁用请求准备 — 2026-10-08
本文保留PR#24准备切片的记录；当前新增默认关闭的代理及原请求重试控制器见 [principal-status-submission.md](principal-status-submission.md)。准备页面尚未接入发送按钮，真实管理员/提供方验收未完成。
模式：Codex。此包只实现准备、冻结预览、明确确认和复制，不提供发送路由或传输控制器。身份目录与私有读取契约见 [admin-principal-ui.md](admin-principal-ui.md) 和 [admin-principal-reads.md](admin-principal-reads.md)。

精确 UUID 详情页将本地身份类型、状态、独立 history.current_status、管理员保护与 issuer 匹配布尔投影给客户端，不传递 subject、issuer、token、actor 或会话列表。USER 和 SERVICE 使用相同状态端点，ACTIVE→DISABLED、DISABLED→ACTIVE；详情与历史状态不一致时无准备表单，要求刷新。观察到管理员保护时无准备表单，指向独立恢复流程；任何 PLATFORM_ADMIN 关联（包括 SUSPENDED）在后端均受保护。issuer 不匹配仅提示，不增加后端没有的身份状态约束，也不宣称配置已修复。

输入/生成 event_no 和原因→预览目标 UUID、类型、前后状态及精确 API 请求→勾选身份与会话影响确认→复制。未确认禁止复制；编辑编号或原因、生成另一编号、目标 UUID/类型/状态/history/保护或 issuer 标记刷新都撤销预览与确认。冻结对象使用字段白名单，隔离调用方的后续修改；重复导出保留同一个编号与正文。剪贴板失败保留手动复制的精确预览；复制中刷新目标会丢弃旧预览与过期完成提示。没有网络发送或浏览器持久化，也不提供跨刷新恢复。

请求：POST /api/v1/security/admin/principals/{canonical_uuid}/status；正文严格只有 event_no、expected_status、status、reason。event_no trim 后为1–50允许ASCII字符、首字符字母数字；reason trim 后5–500 Unicode码点，拒绝C0/DEL。API独立检查当前管理员权限、只读模式、保护规则、实际当前状态、精确重试与原子审计；准备及读取快照不证明允许操作或证明原请求成功。

禁用会由后端原子撤销该身份实际现存浏览器会话；本包不显示猜测的撤销数或成功回执。启用不会恢复旧会话、授予角色或创建提供方账号。后续独立默认关闭的代理/发送包必须绑定冻结目标与精确回执，未知结果只能保留原编号/正文供明确重试；不能把独立详情/history读取当原请求回执。

回归覆盖4个类型/状态契约、错误/受保护/快照不一致目标、issuer仅参考、审计键/Unicode边界、不可变重试正文、双语SSR、真实组件事件处理、编辑/刷新撤销确认、重复复制及剪贴板故障/并发刷新；详情页集成覆盖匹配快照准备和受保护阻断。模拟组件不是浏览器验收；CI完整结果另记 HANDOFF。

公共环境仍样例只读，OIDC及既有注册/授权提交通道默认关闭；不配置身份、授权或秘密。内部服务器尚未安装，SSO待定，人员由用户后续指定；无Docker离线安装/启动及实际运营尚未完成。后台线上部署/版本未独立验证，Render工作区未获得明确选择确认。69页面、API代码0.18.36/schema0020，36/44=82%；七模块100/100演示/100演示/100/89/60/17，七计划100/100/20/33/40/20/0，增量0。


本包后续已接入双语受控发送、精确回执、明确原请求重试和页面内存恢复，独立门禁默认关闭。当前实现见 [principal-status-submission.md](principal-status-submission.md)；上述PR#24准备验收保留为历史。
