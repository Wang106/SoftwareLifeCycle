## 当前检查点 — 2026-11-05（UTC+8）PR179已合并与分层证据审查

PR179已正常保护合并至main `a460d104880e9f0a8ba6ae99bb97d3b735537f18`。独立[main CI41998260330](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/41998260330) attempt1四job成功：2102前端、2846后端＋26子测试、296 PG无跳过、52自动化、126守卫、0029往返及真实原8条Next＋14条组件；严格报告零失败/跳过/重试、固定签名Chrome157.0.8103.39、sandbox=true。Cloudflare生产build `b4796164-c4bb-45fb-b1be-f348f4597cae` / version `0dfff69d-4093-4f2d-b9f9-d6f474a4d912`成功；Actions部署42000150093及continuation42000150130为skipped，不证明线上数据库/业务健康。

本包仅更新已完成证据、分层验收缺口和下一两条B3候选设计，不修改代码/测试/CI或身份配置；尚未上传。本轮文档自己的CI仍待后续授权发布，不借用上述main成功。下一候选是取消unknown态刷新后保留原状态，以及显式重试保持原字节/重复点击互锁；本包没有实现或执行这两条。详见[分层证据审查](browser-layer-evidence-review.md)。

B2组件子集、B3有限恢复和B4-A六条错误均已有真实组件浏览器证据，但完整Next身份链、实际权限/公司验收仍缺；浏览器阶段保持1/4，有限计划8/8。业务36/44=82%、增量0，模块100/100演示/100演示/100/89/60/17，计划100/100/20/33/40/40/0不变。下方“未上传/浏览器未执行”为历史快照，现由上述精确main证据取代。

---

# B4-A synthetic permission-error component tests

Date: 2026-11-05 (UTC+8). Independent implementation baseline:
`b25974543ad44bc46613a7b3582e5dabf4fd5bfe` (merged PR178); no open PR at start.
This is a local candidate, not uploaded and not browser-executed.

## Bounded implementation

Implements exactly the six cases in the
[B4-A design](browser-authorization-b4-permission-design.md):

1. Explicit context POST returns401/session_required.
2. Explicit context POST returns403/submission_forbidden.
3. Explicit context POST returns404/target_not_found.
4. Valid context and confirmed review followed by a first approval POST returning403/submission_forbidden.
5. Valid same-origin/exact-target audit-only import followed by an explicit receipt-proxy POST returning401/session_required.
6. The same recovery flow returning502/outcome_unknown.

Context errors assert generic fail-closed UI with no private context, reason,
review, confirmation or result, and exactly one target context request. First
submission denial asserts rejected phase, exact code/guidance, frozen command
and request ID, no receipt/link/send/retry, and enabled explicit query/reload.
Recovery errors assert unknown phase, exact code/guidance, unchanged complete
scope/command/digest/reason/request ID and exported envelope, no receipt/link or
preparation/reset/send/retry, with explicit query still enabled. All cases assert
exact request bodies and bounded no-automatic-request observation; shared guards
reject unexpected origins, paths, credentials, body shapes, page errors and server
violations. A200ms idle assertion is a bounded observation, not indefinite proof.

Only endpoint-specific test response overrides were added, reset before every
case. Existing hold/release and default responses are preserved. Original eight
component journeys and eight Next journeys are unchanged. The strict component
report now requires every one of fourteen exact title/file pairs; negative
contracts reject missing individual cases and old five/eight-case evidence even
if the claimed count is fourteen. Next reports remain eight. No production
code, server handler, cookie, identity provider, dependency, workflow, signed
browser candidate, sandbox setting or retry policy changed.

## Evidence and limitations

Local checks passed: full frontend2102/2102 with zero failures/cancellations/skips;
81 targeted workbench/transport/recovery/proxy/harness/report contracts;126 CI
guard contracts;52 automation contracts; TypeScript; component14 and Next8
discovery; progress consistency and whitespace checks. Independent read-only
review found no actionable bug or gate weakening and separately passed79
component/Next report contracts, TypeScript and14-case discovery. An initial
automation command targeted nonexistent scripts/tests and did not run tests;
using the repository workflow path scripts/automation/tests passed52. Playwright discovery
is not execution. This Linux workspace does not contain the required fixed signed
macOS Chrome application; actual browser execution and exact-head full CI remain
pending. No alternative executable or security relaxation is used. No new remote
commit/PR/CI, merge or provider deployment was performed. Backend/PostgreSQL and
Next/OpenNext builds are not rerun for this test-only package; baseline results
are not substituted for this candidate's checks.

These are rendered synthetic component responses, not proof of cookie expiry,
actual role identity, real backend scope enforcement or company acceptance.
Context404 means unavailable, not proven cross-project denial. Recovery502
models the actual proxy redaction of non200 backend receipt responses; it does
not claim a direct browser403/404 scope result. B4-A remains a subset, not full
B4 closure. Remaining B3 interruption cases and real-session/actor boundaries
are separate.

Business36/44=82%, increment0, modules100/100demo/100demo/100/89/60/17,
plans100/100/20/33/40/40/0, browser-stage1/4 and finite-plan8/8 are unchanged.
No real identity/business writes, company deployment, database rebuild or paid
resources were enabled. Next step: obtain publication permission, then verify
exact-head full CI and both strict8+14 browser reports before any later release
or merge decision.
