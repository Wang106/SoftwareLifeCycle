# GitHub Actions 持续开发操作说明

模式：Codex。配置基线：2026-10-10 main `6f661fef4aad60642bfc533ba3ca121653cf75f0`，PR43 的 Acceptance 更正协议已完成。
本配置不提高产品验收进度（36/44=82%），不配置业务身份、实际授权或真实写入。

## 已实现的链路

`codex-dispatch.yml` 每小时 UTC 第17/47分钟（北京时间同分钟）以及手动触发。
默认变量未设置时只跑离线配置检查，不调用模型、不创建状态分支。
`dry_run=true` 即使开关已开也不调用模型、不写 GitHub。
开启后的控制器先核验最新 main 和精确 CI，再恢复未结束任务或预留一个新执行。
`codex-worker.yml` 是只供同仓库主线 dispatcher 调用的 reusable workflow，没有公开评论/Issue触发入口。
Codex 是开发 job 的最后一步，使用固定 CLI0.162.1、Action commit、workspace-write/drop-sudo；
依赖从控制 checkout 安装，不向模型 Runner 注入 GitHub App 或部署凭据。
官方 Action 的代理负责 API key；同 Runner 只有只读 GitHub token。

最终结构化结果携带 base64 补丁，干净 publish job 检查身份、基准 SHA、路径、模式、凭据形状和尺寸后
通过 GitHub Git Database API 提交分支、创建 PR。它不运行候选代码，不 force-push。
候选 JSON 不作为 shell 命令插入。48KiB 补丁上限使最终 JSON 小于 Linux 单个环境变量上限。
最多50文件/2500变更行，文件最多1MiB（现有 HANDOFF 已超过256KiB）。
不依赖共享 workspace 或临时 artifact 来恢复。

原 CI 新增标准库 unittest 门禁；原后端/PG/迁移/前端验收原样保留。
`codex-reconcile.yml` 在本仓库 CI 或实际 worker 完成后唤醒主线 dispatcher，
只读取运行元数据，不检出 triggering commit、不下载或执行其 artifact。
idle/dry-run 的 dispatcher 完成事件不会继续唤醒，避免事件空转循环。
定时扫描负责事件丢失恢复；GitHub schedule 可能延迟，不能承诺精确半小时运行。

## 启用前账户配置

以下账户设置没有保存在代码中；当前连接接口不支持 Secrets、Variables、App创建或分支保护设置。
仓库公开，不要把任何密钥写入仓库、任务状态、Issue、日志或聊天。

1. 在 OpenAI Platform 为该调度器使用独立 API 项目/服务账户，配置适当模型权限和费用限额。
   配置本项目 API key。API 计费独立；次数/时间限制不等于美元硬预算。
2. 在 GitHub 创建专用 App，只安装到 `Wang106/SoftwareLifeCycle`。
   Repository permissions：Contents Read & write，Pull requests Read & write，Actions Read，Checks Read，Metadata Read。
   不授予 Administration 或 Workflows write，不加入分支保护 bypass 名单。
   生成 private key 后使用下面列出的 secret 名称；App ID 使用 variable。
3. 在仓库 Settings → Secrets and variables → Actions 中配置：

| 类型 | 名称 | 值 |
| --- | --- | --- |
| Secret | OPENAI_API_KEY | 独立项目的 API key |
| Secret | CODEX_APP_PRIVATE_KEY | GitHub App PEM private key |
| Variable | CODEX_APP_ID | App ID（不是 Installation ID） |
| Variable | CODEX_AUTODEV_ENABLED | 初始 false；完成 dry-run 和账户配置后 true |
| Variable | CODEX_AUTODEV_DAILY_MAX | 1..6，默认6；按北京时间日期计数 |
| Variable | CODEX_REQUIRE_DEPLOYMENT | false 允许代码验收后继续；true 等待独立线上部署证据 |

4. 保护 main：要求 PR，禁止 force-push/删除，要求三个现有 CI checks：
   `Backend, PostgreSQL and migrations`、`Frontend tests and Cloudflare production build`、`CI acceptance`。
   建议要求分支保持最新；这些检查由 GitHub Actions 提供。
   如果保护规则要求人工 review，调度器会在该关卡停止；它不会自我批准、删除要求或越权合并。
   自定义规则照常保留。仓库 `allow_auto_merge=false` 不影响本方案的受保护 REST merge；无需打开 auto-merge 开关。
5. 在 Actions → Codex development dispatcher → Run workflow（main），先 `dry_run=true`。
   通过后置开关 true，再手动 `dry_run=false` 试运行一个小任务。
   检查完整 worker→publish→PR CI→merge→main CI 状态，之后 schedule 自动接力。

入口：
- https://github.com/Wang106/SoftwareLifeCycle/settings/secrets/actions
- https://github.com/Wang106/SoftwareLifeCycle/settings/variables/actions
- https://github.com/Wang106/SoftwareLifeCycle/settings/rules
- https://github.com/Wang106/SoftwareLifeCycle/actions/workflows/codex-dispatch.yml

不要复制登录缓存给 Runner，也不要以未核实的 ChatGPT Plus 额度替代 API 项目配置。
Codex模型使用固定 CLI 的默认配置；API项目必须允许该默认模型。若需选择模型，独立评审修改工作流，不由候选任务改动。

## 任务状态与恢复

main 是需求/代码/已验收进度唯一事实源。首次启用创建 `codex-state` 分支，
其中 `automation-state.json` 保存 task、branch、attempts、run_id、work_sha、head_sha、base_main_sha、pr、
CI run+SHA、merge_sha、main CI、deployment、原因和最近50事件。状态文件无秘密/业务数据。
专用分支从 main 创建，代码文件不是另一套开发基线，唯一使用文件是状态 JSON。
CAS 保存使用原 blob SHA；并发争用失败，不覆盖未知状态。主线 dispatcher 使用统一 concurrency，
从任务预留到 worker/publisher 结束一直持锁。GitHub可能合并/替换等待中的触发，cron负责重新核对状态。

| 状态 | 下一动作 |
| --- | --- |
| developing | 先查原 Actions run，仍运行则等待；已结束才恢复 |
| ready | 从上次 task branch 提交继续，扣除新一次尝试 |
| waiting_ci | 核验精确 SHA/branch/workflow 和三个必需 job；失败进入修复 |
| merged_pending | 单独核验 merge SHA 的 main CI；不复用 PR/旧 main 成功 |
| done_code | 实现与精确主线 CI 已验收；不代表生产部署/真实业务验收 |
| blocked | 记录原因，全队列停止，人工处理后按新 task 或状态恢复 |

每任务最多3次模型执行（包括首次、修复、超时、checkpoint），每日总次数1..6。
预留时先落盘再启动模型；失败/超时也计次数。不使用无限递归或自动增加预算。
输出 ready/checkpoint 都提交分支；checkpoint 不创建完成 PR，而是下一轮恢复。
突然中止可能丢失本轮尚未导出的修改；会从最近已发布检查点重做，不能保证每字节恢复。
提交成功但 state/PR 更新中断时，从带 task/run 标记的分支提交恢复，不重复模型调用。
PR合并成功但状态写入中断时，从真实 PR merge_commit_sha 恢复，不重复合并。
main变化时通过非破坏性 merge同步任务分支，并重新验收新 SHA；冲突停止，不 force-push。
其他开放 PR 或未拥有的同名分支阻止新任务，避免与另一聊天窗口重复开发。

block处理：关闭 `CODEX_AUTODEV_ENABLED`，查看对应 Actions/PR 与 state.reason，先修复原因。
保持原测试/提交证据；不要仅清空次数强行重试。未合并任务可通过独立已批准 PR修复或完善scope；
在没有运行中的worker时，由仓库管理员在 state 分支对准确 task 做一次有记录的恢复（ready/blocked、reason），
已耗尽3次的任务需要审核后建立新的任务 ID，并保留旧记录。重新开启前再执行 dry-run。
已合并 main CI失败应先在独立修复 PR修复，不盲目还原生产数据库。

## 部署与真实验收的限制

保留原 `deploy.yml` 与 `SLC_DEPLOY_ENABLED`，不填入/改变提供方凭据。
既有 Actions部署仍可能 skipped，Cloudflare独立提供方自动部署可能早于main CI完成；本配置不宣称已统一门控。
当前 deploy.yml 的 Render步骤只证明请求被接收，不能证明live API/schema、迁移和健康。
默认 `CODEX_REQUIRE_DEPLOYMENT=false` 时完成状态为 done_code，deployment明确 unverified，后续任务可继续。
设为true时在 merged_pending 停住；自动live部署验收适配器尚未实现，不能通过“deploy job绿色”自动解锁。
它是严格暂停开关，不是已完成的Cloudflare/Render部署验收器。
真实身份、管理员、跨会话/浏览器、内网及生产运营验收仍是独立里程碑。

当前自动启用队列仅两个已细分UI任务，后续Impact/评审/离线运营任务禁用并保留待定验收标准，
不会从模糊标题自行扩大权限或执行数据库迁移。需要配置范围和审核后再开放。
自动候选不能修改 CI/调度器/部署/依赖/迁移/进度账本/已有测试，只能按scope新增测试。

## 本地无凭据验收

```bash
python -m unittest discover -s scripts/automation/tests -v
python scripts/report_development_plan_progress.py --check
```

回归覆盖去重、依赖、预算、SHA及job绑定、fork/上下文拒绝、恢复运行/检查点、推送/状态中断、
main同步、合并拒绝、部署未知、真实git补丁作用域/模式/凭据拒绝、state CAS。
账户配置与付费试运行未完成时，不能将这些离线回归记成长期无人值守系统已验收。
