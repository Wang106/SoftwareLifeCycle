## 当前检查点 — 2026-11-04 PR175 已合并，B3恢复设计

PR175已合并至 main `43cbcc18d8020d892853d4fae30166fe274b7fef`。[main CI41655534460](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/41655534460)全部成功：2098前端、2846后端＋26子测试、296 PostgreSQL无跳过、86守卫、0029迁移往返；原8条Next＋新5条组件浏览器实际通过，两份严格报告均通过，sandbox=true、零重试。Cloudflare生产build `9ecdcef7-f2a0-4715-b715-770cc7ddb4f4` / version `9697d179-ead4-476e-a5e7-360d8983e6c3`成功。Actions部署/continuation仍skipped，不代表线上数据库或业务健康验收。

下方“仅本地/未执行/CI未接入”等为PR175发布前历史，不能据此重复开发或否认已通过的组件证据。组件套件已接入同一受信runner，仍不证明真实Next会话、FastAPI授权或真实双人身份链。本包仅收口证据并限定B3刷新后手动审计恢复设计，详见[证据与B3范围](browser-authorization-b3-recovery-design.md)。不修改生产代码、身份、CI或测试，不把设计当执行；整体36/44=82%、业务增量0、浏览器阶段保守维持1/4，待B2跨层边界收口再独立判定。

当前新文档包尚未发布，不能把以上基线CI当成本包CI。后续按精确head核验；真实身份/业务写入继续关闭，旧库不重建。此记录取代旧入口中的一次性等待步骤，不恢复历史授权。

---

# B2 component browser CI integration candidate

This local-only follow-on starts from PR #175 head
`a470a5f1ce1326c862fd9df08502accb1240b581`. Its existing CI run
`41637422663` succeeded: frontend 2098 tests, backend 2846 plus 26 subtests,
296 PostgreSQL cases without skips, original browser eight journeys, and
aggregate acceptance. That run did **not** execute the five component journeys.
The earlier component design and handoff describe that pre-integration snapshot.

## Minimal change

- Keep the existing `browser` job, macos-26 runner, pinned actions, fixed signed
  Chrome PKG preparation, sandbox, original eight journeys/report and aggregate
  dependency unchanged.
- After the original browser command succeeds, run the independent five-case
  component config, followed by its strict report validator. Normal GitHub
  Actions shell failure propagation stops the step on either failure. There is
  no skip condition, retry, continue-on-error, executable override or fallback.
- Save `frontend/component-browser-results/` as a separate
  `component-browser-evidence` artifact, with missing files treated as errors and
  14-day retention, following the existing non-cancelled evidence convention.
  The original `browser-evidence` artifact remains unchanged. Both suites use
  the same runner and already-verified browser, whose diagnostic record remains
  in the original artifact. No duplicate browser download or new job is added.
- The existing aggregate requires `browser=success`, so a component run, report
  or artifact failure blocks acceptance without changing branch protection.

The offline workflow contract checks exact command order, independent output,
mandatory report validation and unchanged aggregate. Negative controls reject
missing/duplicate steps, discovery-only execution, retries, conditions, relaxed
shell failure behavior, environment overrides and incorrect artifact settings.

## Validation boundary

Local checks on 2026-11-03: 86 CI guard contracts passed (including the new
positive contract and 15 negative mutations); 29 component harness/report
contracts passed with zero failures/skips; TypeScript noEmit passed; Playwright
discovered exactly five scenarios. Progress-ledger and whitespace checks passed.
Removing only the two added workflow steps restores the PR175 workflow
byte-for-byte. Independent read-only review found no blocking issue and reran
the 86 guard contracts and 24 report/config tests successfully.

This candidate has not been uploaded and has not triggered CI. Local discovery
is not execution. The five component journeys remain unexecuted until the
approved runner completes both execution and strict report validation.
Existing 15-minute browser timeout is preserved; actual runtime margin must be
checked after an authorized CI run rather than assumed from local contracts.

No production code, dependencies, real identity, business data, database writes,
browser security configuration or existing test/report gates are changed.
Synthetic component evidence still cannot prove authenticated actor correctness
or replace backend/real identity acceptance. B2 completion and milestone counts
remain unchanged.
