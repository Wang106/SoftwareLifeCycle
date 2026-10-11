# SSR / ASR 云端只读演示脚本

第三轮：成功发布证据与阻断证据，约 12 分钟。该脚本用于测试样例；审批人、固件引用与审计均为合成记录。真实岗位授权、提交、交付、量产及公司内部部署不在此演示范围。

## 演示前提

前两轮代码已合并 PR56 / PR57。API 当前新增只读 `GET /api/v1/demo/release-evidence`，最多读取固定命名空间三个 Release，不扫描全站目录；计算使用原有 bounded Readiness，按实际当前 Snapshot UUID 查询，正式决策绑定独立展示。未安装样例返回 `initialized=false`；API 不可用时页面明确缺失，不提供静态成功替代。

第四轮需确认云端测试 API、数据库工作区和维护操作入口后才执行；本轮没有在提供方运行命令：

```bash
cd backend
python -m app.seed_release_demo --sample-only
python -m app.seed_release_evidence --sample-only
```

两者独立 opt-in，不接入启动 Seed。固定 UUID、调用方事务；重复运行保留已有审批/决策/执行/审计历史。不将命令用于公司数据库，不启用真实写入/OIDC，不输出数据库连接串。已有同 code 的外来产品会拒绝写入。检查健康状态、schema `0023_impact_withdrawal_history`、API 版本 `0.18.42` 与样例 API 返回后，再打开 `/demo/releases`。

## 讲解步骤

| 时间 | 页面与操作 | 要证明的行为 |
| --- | --- | --- |
| 0–2 分钟 | 标准发布目录→DEMO-SSR-1.0、DEMO-SSR-1.1 | 供应商基线；三组件/冻结文件；四级审批模板与实际历史分开。待审批和全通过两种状态 |
| 2–4 分钟 | 应用发布目录→DEMO-ASR-A-1.0、DEMO-ASR-B-1.0 | 两个客户/项目，均精确绑定 SSR；Application/Bootloader 继承、Calibration 显式修改；退回/拒绝请求关闭，无活动审批节点 |
| 4–6 分钟 | APR-DEMO-SSR-1.0 / 两个 ASR 审批详情，切换中文/English | SSR：电子工程师→电子经理→系统工程师→研发总监；ASR：应用工程师→应用经理→系统工程师→项目经理。记录 actor/意见/时间原样保留。模板不代表真实岗位权限 |
| 6–8 分钟 | `/demo/releases`→DEMO-EVIDENCE-SSR-2.0 / ASR-A-2.0，沿链接打开 Snapshot、SCR、三类 DVP、审批、Decision | 当前精确 Snapshot 三项测试 PASS；实际八项 Readiness 规则通过；四级审批 APPROVED；独立正式 RELEASE 决策绑定相同 Snapshot/Approval。READY 记录状态不等于正式发布 |
| 8–10 分钟 | DEMO-EVIDENCE-ASR-B-2.0→DVP 当前上下文，再选择历史 SNAP-DEMO-EVIDENCE-2-1 | 旧 Snapshot 有三项 PASS，当前 SNAP-DEMO-EVIDENCE-2-2 没有执行；两个 Snapshot 内容 hash 相同仍不能替代 UUID。审批 APPROVED，当前 NOT_READY，正式 HOLD：审批通过不足以释放软件 |
| 10–12 分钟 | 成功/阻断 ASR 的 Readiness 与 Passport，双语切换 | 护照显示相同精确当前 Snapshot/Decision/SSR 基线。无 Delivery/Distribution/Authorization 是未创建，不宣称已经交付/量产；展示与正式写入分开 |

## 验收与限制

桌面和移动端：中文/English 标题、节点、规则、关闭状态及缺失状态；文件 hash 长文本不溢出，表格可滚动；所有对象链接使用真实路由，DVP 使用条目 UUID 并固定 release_id/snapshot_no；不存在实际提交表单。API 不可用、未安装/不完整样例时无成功证据卡。

测试覆盖独立数据、旧历史不变、完整事务回滚、幂等 Seed、正反 Readiness、旧决策不匹配新快照、外来 Release 隔离、已有 Passport 与新只读 API 一致；真实 PostgreSQL 追加历史触发器与回滚/重复由既有完整 CI 执行。本机没有 PostgreSQL，不把 SQLite 当数据库触发器验收。

当前 Readiness 的 Verification 规则检查执行覆盖，不保证 FAIL 结果必定单独阻断；本演示仅证明“当前快照未执行”被阻断，不把它描述成已完成所有失败结果门控。未替换原规则/放宽门控。浏览器截图、提供方 API/schema 与实际样例安装均由第四轮独立验收；构建通过不能替代线上数据验收。
