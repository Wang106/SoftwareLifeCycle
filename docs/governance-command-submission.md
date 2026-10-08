# 审批动作与发布决策提交、原审计恢复契约
更新：2026-10-09（Asia/Shanghai）；Codex。

## 范围及默认关闭门控
新增 POST /auth/governance-command（提交）与 POST /auth/governance-command-receipt（查询原审计），两者 GET 返回405。只允许approval、decision两类操作；与首批三类业务提交及管理员通道分别门控。
三个服务器变量：GOVERNANCE_COMMAND_SUBMISSION_MODE=disabled、GOVERNANCE_COMMAND_APPROVED_API_BASE_URL、GOVERNANCE_COMMAND_APPROVED_APP_ORIGIN。只有明确enabled、OIDC/加密会话配置有效且批准HTTPS API/应用地址精确匹配才开放；NEXT_PUBLIC、FIRST_COMMAND、管理员开关不启用本通道。所有响应private/no-store，凭据不传入客户端。
唯一当前token-bound USER会话需复核/me；提交要求read_only_mode=false，恢复允许只读切换后查询自己的原记录。后台仍独立检查REVIEWER/RELEASE_AUTHORITY精确范围和业务约束，不凭active_grant_counts授权。只接受同源JSON，声明/流式8192字节界限和严格UTF-8；无任意URL/path/headers/token/actor principal注入。

## 请求、路径及原始正文
外层严格只有operation、target、body；target为安全、编码的审批业务编号，不能用审批UUID替代。内部重构既有prepare，UUID标准化、固定字段与声明文本校验；正文及编号冻结，编码后8192字节上限。
| 操作 | 固定后台路径 | 严格正文 | 后台成功HTTP |
| --- | --- | --- | --- |
| approval | /api/v1/approvals/{approval_no}/actions | request_id、expected_step_id、actor、action、comment | 200 |
| decision | /api/v1/approvals/{approval_no}/release-decision | request_id、decision_no、decided_by、readiness_status、decision、notes | 201 |
审批action只接受APPROVED/RETURNED/REJECTED；expected_step_id必填，不暴露旧无编号/无步骤路径。actor/decided_by为保留原文的声明，最多120字符，无控制字符；真实操作者由会话及后台绑定。decision_no最多50字符，readiness_status/decision最多30字符，保留其声明而不扩充为自动审批或就绪计算。comment/notes原文或null，不做隐式修剪；空字符串拒绝。

## 原审计回执
成功POST仍须GET /api/v1/activity/EVT-AP-{key无横线}或EVT-RD-{key无横线}，精确核对事件类型、entity/action、当前操作者principal与AUTHENTICATED_PRINCIPAL、原target及完整请求指纹。仅正确HTTP不能确认为成功；不以当前详情或当前流程状态冒充原回执。
审批事件entity_id是ApprovalRequest UUID（不是动作key）；payload.approval_action_id才是request_id。step_id和after_step_status绑定原步骤和动作；APPROVED动作的原审批结果可能为PENDING，表示后续步骤仍待完成，也可能APPROVED。RETURNED/REJECTED精确对应原审批结果。回执投影原approval_id/number、action UUID、step UUID/order/role、step状态、审批状态、target_type/UUID和可空snapshot UUID，不编造当前状态/replayed。
决策事件entity_id就是request_id；精确核对decision_no及payload.approval_no、approval_id、原decision/readiness_status与release/snapshot UUID、snapshot_no、SHA-256。原声明不等于重新计算的Readiness，记录决策不自动分发/授权/执行刷写。回执白名单不输出actor原数据、token、subject或任意payload。
回复/原审计声明和流式16384字节界限、严格JSON/UTF-8；更大或无效的原审计仍unknown，不代表未提交。大备注可能令审计超限，需要受控诊断，不自动扩大读取范围或重试写入。

## 不确定结果与控制器
GovernanceSubmission只接受明确布尔确认且path/trace/audit/正文可重构的冻结Review；固定浏览器代理路径、same-origin凭据、no-store、拒绝重定向和15秒超时。共享首批已验证的有界响应读取，不改首批操作门控或行为。
同步sending/checking锁阻止双击与发送/查询交叉；confirmed终态。丢失、断流、HTTP不确定或错回执都unknown，没有自动重试。明确send重试保持同一key/target/body字节；recover在服务器只GET原审计，不再次POST业务路径。缺失/拒绝/错actor或body不能证明没提交；后续步骤/编号/权限拒绝或门禁关闭保留此前unknown。首次明确拒绝可rejected，恢复查询后不把缺失当作可安全创建新请求。
当前控制器仅内存；双语页面按钮、结果及页面内存保留将在下一包接入，跨卸载/刷新/会话导入未实现。真实提供方/管理员/内网浏览器验收未执行，公开样例只读，未配置实际变量、身份、授权或秘密。

