# 交付包、分发与生产授权提交及原审计恢复
更新：2026-10-09（Asia/Shanghai）；Codex。

## 范围与默认关闭门控
新增POST /auth/distribution-command（提交）及POST /auth/distribution-command-receipt（查询原审计），GET均405。只允许delivery/distribution/authorization，与首批、治理及管理员门控独立。
DISTRIBUTION_COMMAND_SUBMISSION_MODE=disabled、DISTRIBUTION_COMMAND_APPROVED_API_BASE_URL、DISTRIBUTION_COMMAND_APPROVED_APP_ORIGIN；仅明确enabled、有效OIDC/加密会话及精确批准HTTPS API/应用绑定才开放。NEXT_PUBLIC、FIRST/GOVERNANCE及管理员开关不开放此通道。所有托管响应private/no-store，实际变量/身份/授权/秘密未配置。
唯一当前token-bound USER需复核/me，提交要求非只读，恢复允许只读后查询自己的原操作。后台仍独立验证DISTRIBUTION_AUTHORITY/PRODUCTION_AUTHORITY精确范围及业务约束；声明或active_grant_counts不授予权限。

## 原请求与严格解析
外层严格operation/target/body，target是对应既存Release、DeliveryPackage精确修订或Distribution UUID；必须与正文相应UUID一致，不能改用业务编号或不同对象。
固定POST后台路径 /api/v1/deliveries、/api/v1/distributions、/api/v1/authorizations，三者成功HTTP均201，仍需精确原审计确认。
正文固定字段包括request_id；复用既有prepare，UUID规范小写、业务编号及声明边界、revision/有限batch_limit为明确正PostgreSQL整数1–2147483647。不接受字符串数字、缺失/隐式不限批次或额外token/path/headers。不限batch_limit必须显式null。
交付snapshot_artifact_ids是1–200个无重复UUID的不可变排序集合，数组类型/规范化后重复均校验；数组顺序等价不代表不同文件等价。created_by是原声明或null，不代替真实操作者。restriction_note保留原文或null，空字符串拒绝。冻结的是已确认Review的规范化正文，不承诺保留任意输入JSON的键顺序；正文和target绑定后，重试使用原请求ID和相同JSON字节。
同源JSON、严格UTF-8，声明及流式正文上限8192字节；数组及备注也受总字节上限约束，不承诺200个文件加任意声明总能容纳。响应与审计读取上限16384字节、15秒超时、no-store、拒绝重定向。

## 原子审计与精确结果
只GET /api/v1/activity/EVT-DP-{key无横线}、EVT-DS-{key无横线}或EVT-PA-{key无横线}；核对原事件类型/entity/action/key/业务编号、当前principal UUID及AUTHENTICATED_PRINCIPAL、完整原请求指纹。request不含request_id，交付artifact指纹按后台排序契约核对。
交付回执保留原READY、package_no/revision、release/snapshot、snapshot_no、decision_no/approval_no、recipient/purpose和精确artifact集合。
分发回执保留原READY、原DeliveryPackage UUID及package_no/revision、release/snapshot和接收方；创建记录不意味着发送文件、通知接收方或确认签收。
生产授权回执保留原DRAFT、原Distribution和DeliveryPackage、精确修订、release/snapshot、customer/project/site/line/purpose、明确finite/null批次范围及原限制声明；DRAFT不批准量产、创建Deployment或执行刷写。限制声明来自已核对的原request，不冒充当前限制或授予权限。
仅白名单结果，没有token、subject、任意payload、current_status或replayed推断。后台可以后来改变状态，当前详情不能代替原应用结果。

## 不确定性、明确重试与下一步
DistributionSubmission接受布尔确认且path/trace/audit/正文可重构的Review，固定浏览器代理路径。同步sending/checking互锁，confirmed终态。丢失回复、错误HTTP、缺失/拒绝/不匹配原审计均unknown，无自动重试或POST恢复回退；后续拒绝或门禁关闭不抹除早先未知事实。
明确恢复仅GET原审计；明确重试保持原key/target/body。大备注/文件列表使原审计超限时保持unknown，不表示未提交，需要受控诊断，不自动扩大读取范围或重复写入。
三类表单已接入双语确认发送、查询原审计、原请求明确重试及精确结果。页面使用独立distributionSubmissionConfigured与唯一当前USER只读投影，只有六个布尔能力传客户端；其他通道开关不能启用本通道。已尝试原请求不能被编辑、命令或上下文刷新替换；未知结果不允许新建请求。confirmed或首次明确rejected可重新复核并生成新UUID。原READY/DRAFT、修订、接收方与有限/null范围如实展示，业务详情、原审计及交付原Snapshot链接独立观察。仅内存、跨卸载/刷新/会话导入未实现。公共样例只读，真实身份/管理员/提供方/浏览器和内网验收未执行；内网未部署，SSO及系统架构待定，不重试已被拒绝的浏览器访问。
