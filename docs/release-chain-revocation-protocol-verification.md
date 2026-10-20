# 发布链撤销浏览器协议验收：阻塞

核验日期：2026-10-20（Asia/Shanghai）。本轮执行 Codex / ChatGPT Work；核验既有 PR79，不重新实现协议。事实基线 main `489df90966a9a97ea76a67de005f602eee6fb64c`，开放 PR 0。PR79 head `b904f5a872ecbeb9c6203327f01c52822ed63b5b`，已于15:05:08 UTC合并。历史执行标签按原交接保留，本轮只记录独立验收。

## 已核实的证据

| 项目 | 精确证据与结果 |
| --- | --- |
| PR CI | [39443378916](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/39443378916)，三个必需job success |
| 独立 main CI | [39445167814](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/39445167814)，三个必需job success |
| 两轮测试 | 各2309 backend passed、242 PostgreSQL-module cases/no skips；frontend1483 passed/0failed/0skipped；Next/OpenNext成功；唯一head0026、离线SQL及PG迁移往返通过 |
| Cloudflare Preview | PR79机器人记录部署6a007036-9b93-4da2-8353-6eaf6b53c7e9，精确head b904f5a，success |
| Cloudflare Production | main build eaeb2b3a-af57-4c88-8c14-d08c3e462e36 success，version be6d1e4e-5273-45dd-b2c8-994f87b1f57f |
| Render | dep-dbbn73l9fdbs73ed2340 live，commit仍f221bdddc0e110fe61c9d72694408d78a64989b5；前端包未新部署后端；健康ready/API0.18.45/schema0026；15:05:08–15:19:52 UTC所查error日志为空，不代表全面性能验收 |
| Actions | deployment39446609276、continuation39446609003 skipped，不能称执行成功 |

## 本地新增反例失败，不能接受协议完整性

实际 `frontend/lib/release-chain-revocation-transport.ts` 的 `ReleaseChainRevocationSubmission.run()` 只在 sending/checking/confirmed 时返回。第一次发送丢失响应后 uncertain=true、phase=unknown，但第二次 `send(true, fetcher)` 仍进入 submit 分支并调用 `/auth/release-chain-revocation`。这违反已合并设计“unknown 只能显式 audit-only recovery，禁止再发业务 POST”。现有request_id幂等保护不能代替浏览器不重发契约。

本地使用 Node 内置 TypeScript 类型移除和 VM 模块直接加载当前三个真实 TS 模块，无依赖安装、无源文件改写。构造合法 RELEASE 命令并明确确认，fake fetch 仅计数并抛出 `simulated response loss`：

```text
await submission.send(true, fakeFetch)
assert phase == unknown
await submission.send(true, fakeFetch)
observed businessSubmitCalls = 2
expected businessSubmitCalls = 1
assertion failed / exit 1
```

未发送真实业务POST。该反例不在现有1483项测试中；CI成功不证明此要求已通过。当前测试失败后停止验收发布，不合并本检查点，不进入UI、不改变身份/秘密/计费/CI/调度/部署权限。公共只读、OIDC/真实提交继续关闭，无新增migration/Seed/API/schema变化。

## 下一步的精确范围

先恢复此文档检查点，实施 `release-chain-revocation-unknown-submit-guard`，仅改 `frontend/lib/release-chain-revocation-transport.ts` 与新增对应状态机回归，以及本文件/DEVELOPMENT_STATUS/HANDOFF/进度。任何uncertain状态下send必须不触发fetch、不改变原command/字节、保持unknown；recover仍允许一次只读原审计检查。测试至少覆盖丢响应后send、recover未确认后send、导入恢复语义、关开关再开、拒绝/冲突后unknown不被清除、并发双击及成功confirmed后零重复发送。拒绝通过调用方按钮禁用替代transport保护。

修复后先通过以上反例与相关回归，再执行既有完整CI；精确head含最新main且三个必需job全绿后才可合并，合并后独立main/provider核验。不得削弱原测试/保护。之后再进入 `release-chain-revocation-ui-recovery`，真实多用户提供方验收仍单独待定。业务36/44=82%；七模块100/100演示/100演示/100/89/60/17；七计划100/100/20/33/40/20/0，均不提升。
