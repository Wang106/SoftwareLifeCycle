# SSR / ASR 云端演示：最高优先级四轮任务

授权：2026-10-11，用户明确优先演示标准发布、应用发布及审批。基线 main 985c7b2a516d58c11b63ded94c6e39d39d1331c2（PR55已合并）。Codex / ChatGPT Work；无需用户本地CLI或额外模型API。此计划优先于未授权的Impact浏览器撤销功能、本地部署和生产运营。

## 已确定的审批节点
| 顺序 | SSR | ASR |
| --- | --- | --- |
| 1 | 电子工程师 / Electronics Engineer | 应用工程师 / Application Engineer |
| 2 | 电子经理 / Electronics Manager | 应用经理 / Application Manager |
| 3 | 系统工程师 / Systems Engineer | 系统工程师 / Systems Engineer |
| 4 | 研发总监 / R&D Director | 项目经理 / Project Manager |

按序审批；退回/拒绝关闭本次请求，后续重新提交应建立新记录。审批绑定冻结Snapshot；全部通过不直接等于正式RELEASE。岗位标签是流程节点，不代表已配置实际岗位权限；现有通用REVIEWER权限不得伪称逐岗位限制。

## 四轮范围与验收
1. **release-demo-round-1：数据与审批样例**。独立版本化样例家族、两版SSR、两个客户ASR、Application/Bootloader/Calibration、明确base_component、真实冻结清单和hash；两套四级审批及进行中/通过/退回/拒绝。新增opt-in seed及SQLite/真实PG幂等、原历史隔离、事务回滚和顺序推进验证。不得更新现有冻结历史。代码/CI验收与线上注入分开。
2. **release-demo-round-2：双语页面**。SSR/ASR详情突出标准来源、组件文件差异及关联导航；审批详情突出四节点进度、当前节点、审批人/时间/意见、待开始与关闭状态；验证中英文与无API状态。保持只读，不增真实身份或写入门控。
3. **release-demo-round-3：审批到发布证据**。有意义的测试与Readiness、Snapshot/审批/Decision/Passport精确关联；成功和阻断样例、完整只读导航和10–15分钟演示脚本。禁止凭审批通过伪造就绪或正式发布成功。
4. **release-demo-round-4：云端演示验收**。核实Render工作区/测试API/schema、必要时向明确的测试库加载opt-in样例，核验Cloudflare API连接；电脑/手机/中英文、筛选分页和全链路链接。provider与真实浏览器证据独立，不绕过历史访问拒绝。缺少工作区或访问权限时保存检查点；不把SSR/HTTP当真实浏览器验收。

每轮独立PR，当前head包含最新main、三个必需CI成功后受保护合并，再检查main CI和provider。依赖顺序执行，已有相关PR优先恢复。进度见release-demo-plan.json及HANDOFF/PR精确证据，不提升原44项业务验收比例。

## 第一轮样例和使用
独立产品DEMO-RELEASE-BMS，供应商DEMO-RELEASE-SUP；DEMO-SSR-1.0（第二节点待审批）、DEMO-SSR-1.1（全部通过）、DEMO-ASR-A-1.0（第二节点退回）、DEMO-ASR-B-1.0（第二节点拒绝）。两个ASR均基于SSR1.1；Application/Bootloader继承基线hash，Calibration声明修改。所有release保持DRAFT，无正式ReleaseDecision，无真实文件下载、凭据或身份。

在已完成迁移的专用云端测试数据库环境运行：
```sh
cd backend
python -m app.seed_release_demo --sample-only
```
这是显式操作，不加入生产启动或原seed；未执行此命令不声称网站已有新样例。固定UUID与同事务构建，重复执行保留原记录及后来审批状态；同代码被其他产品占用时报错。样例审计标注sample_only，仅为合成演示历史，不是人员真实审批证据。真实岗位权限、现场提交演示及本地部署不属于本四轮范围。
