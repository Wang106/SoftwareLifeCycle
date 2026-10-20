# 发布链撤销确认与原审计恢复界面

执行：Codex / ChatGPT Work。基线 `8eb25f4b90b506910837faf3b74690f27b66e9c1`（PR83）；复用关闭未合并的 PR81 `e5cd6dfeca337a0932822c5762259592f419137d` 界面草案，重新审查并使用 main 已合并的 PR82 transport uncertain 守卫，不重复实现后台协议。

## 入口与确认

`/commands?operation=release-chain-revocation` 是独立入口；普通 commands 页提供明确链接，不把永久撤销塞入通用命令表单。原 governance 页面仍为只读。支持 RELEASE、DELIVERY_PACKAGE、DISTRIBUTION、AUTHORIZATION，展示精确目标 UUID、request_id、审核的 Release/Snapshot/Decision 及所需父链 UUID、原因。缺省目标类型为 RELEASE；缺少上下文时严格校验失败。准备、勾选确认、复制、导入均不发送网络操作。

仅既有独立开关、有效身份和写入权限同时满足时显示提交按钮；默认关闭，可准备确认和复制。确认绑定原命令，准备后编辑使确认失效；进入提交或恢复流程后锁定原命令。原因作为原文转义展示，不交给词条翻译。确认回执只显示既有严格 projector 的白名单字段，并链接精确原审计；actor 与发生时间由原审计详情展示，不从当前治理状态补造回执。

## 不确定结果与恢复

复用 `ReleaseChainRevocationSubmission`，lost/未知结果后不显示再次提交或新建请求按钮，transport 本身也拒绝二次业务 POST。后续只可显式查询同一 request_id 的原审计，禁用/401 等恢复失败不能清除未知结果。双击由 controller 同步 in-flight 状态约束，不仅依赖 React 按钮禁用。

手工导出格式 `slc-release-chain-revocation-recovery` v1，精确同源绑定（HTTPS；本地开发仅允许 HTTP loopback），上限 49152 UTF-8 字节，包含严格原命令而不含凭据。仅接受 minified 或两空格规范 JSON；拒绝额外字段、凭据字段、跨站、错误上下文、非规范表示和超长输入。导入创建只有 state/recover 的冻结 wrapper，没有 send 能力；不自动联网、不把原请求转换为新草稿。复制内容是业务数据且不是执行证明，界面明确提醒妥善保存。

## 验证与边界

本地完整前端 1494 passed / 0 failed / 0 skipped；新增七项 UI 行为覆盖（中英文默认禁用、精确确认、未知结果锁定、401 后恢复、四类型规范导入、缺省类型、pending 重复点击），独立入口接线及自动本地化覆盖。Next15.5.24/OpenNext build、`auth:check`、`cf:check` 成功。SSR/React harness 不冒充真实浏览器或真实提供方验收。后台、真实 PostgreSQL 及迁移完整验证由本包精确 PR CI 另证；本地没有重跑，也不声称通过。

无 API、schema、Migration、Seed、依赖、CI、调度、身份或提供方配置变更。API0.18.45 / 唯一迁移0026，Seed 幂等性不受影响。公共只读，OIDC 和真实提交关闭，内网未部署。真实多用户/桌面/手机与中英文批准提供方验收仍待完成，进度不提升。

本包提交、PR 精确 head 三项 CI、合并与 main/provider 结果在本包 PR 追加，不以基线替代最终证据。基线 PR83 main CI39455082138 三项成功；GitHub Cloudflare check 证实 production build `f3928426-9756-42c5-aef5-a9c8910180cc` 成功，Worker version `4e1800ca-653a-4d18-a964-6ed6a081070b`，因此旧记录的“无本地 token 未验证”已由提供方检查补齐。Render 既有 live `dep-dbbn73l9fdbs73ed2340` 仍对应后台 `f221bdddc0e110fe61c9d72694408d78a64989b5`，不是本包重部署；Actions39457194877/39457194880 skipped。

## 下一包候选

`production-trace-correction-design-review`：先只审查实际 Deployment/Changeover/Batch 历史、消费者、锁序与现有 actual 更正边界，给出追加式更正、旧写者兼容、审计与真实 PG 验收矩阵及精确实施路径；不直接实现或启用生产写入。真实身份/多用户验收另待批准环境，不借设计或 UI 完成提高业务验收比例。
