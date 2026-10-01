# SoftwareLifeCycle Development Handoff

## Handoff identity

- Date: 2026-10-01 (Asia/Shanghai)
- Repository: `Wang106/SoftwareLifeCycle`
- Branch: `main`
- Verified baseline: `3968f9f007e2a00a7268074e5e66cc1a0a8db2cc`
- Baseline subject: `feat: make snapshot and production batch writes retry-safe`
- Source of truth: GitHub `main`, followed by code, migrations, tests and live health checks

Before continuing, fetch `origin/main`, confirm the branch/working tree and read this file together with `PROJECT_STATUS.md`, `ROADMAP.md`, `ARCHITECTURE.md`, `API.md`, `DATABASE.md`, `SECURITY.md` and `docs/write-contracts.md`. Do not infer completion from a prior chat.

## Product and solution summary

SoftwareLifeCycle is an automotive BMS/ECU software-lifecycle governance platform. Its implemented trace chain is:

```text
SCR → DVP → Snapshot → Readiness → Approval → Release Decision
    → Delivery → Distribution → Production Authorization
    → Deployment → Changeover → Batch
```

The solution is evidence-oriented:

- formal relationships use stored UUIDs rather than matching display names or versions;
- release evidence is pinned to an exact frozen Snapshot;
- formal judgments and links are append-only where the schema provides protection;
- every current command writes its domain change and audit event in one transaction;
- OIDC mode resolves an ACTIVE local principal and exact software/project role before a write;
- the public environment contains demo data only and remains read-only.

## Architecture and deployment

| Layer | Current implementation | Current state |
| --- | --- | --- |
| Frontend | Next.js 15 / React 19, Cloudflare Worker through OpenNext | `https://softwarelifecycle.whf969.com`, verified HTTP 200 |
| API | FastAPI + SQLAlchemy services | Render API version `0.14.0`, health verified ready |
| Database | PostgreSQL 16 + Alembic | Required/verified revision `0016_authenticated_audit_actors` |
| Identity | Provider-neutral principals and scoped global/software/project roles | Implemented in code; approved OIDC provider not configured |
| Public-write protection | `READ_ONLY_MODE=true` | Verified write rejection: HTTP 403 `read_only_mode` |
| Engineering source | GitHub `main` | Baseline above was pushed successfully |

Runtime flow:

```text
Browser
  → Cloudflare-hosted Next.js
  → Render FastAPI
  → PostgreSQL
```

The frontend performs read-oriented catalog/profile workflows. Write APIs exist for controlled development, but no public write UI or non-read-only public target is approved.

## Development progress

Progress is the count of checked items in `ROADMAP.md`. It is a roadmap-completion measure, not a production-readiness certificate.

| Phase | Completed | Progress | Status |
| --- | ---: | ---: | --- |
| Phase 1 — Domain foundation | 5 / 5 | 100% | Complete |
| Phase 2 — Release governance | 5 / 5 | 100% | Complete for demo scope |
| Phase 3 — Distribution and production trace | 5 / 5 | 100% | Complete for demo scope |
| Phase 4 — Evidence, review and auditability | 8 / 9 | 89% | Compatibility-list migration remains |
| Phase 5 — Identity and authorization | 8 / 9 | 89% | Approved OIDC provider configuration remains |
| Phase 6 — Controlled write experience | 0 / 5 | 0% | Snapshot/Batch and Approval/Decision slices implemented; broad items partial |
| Phase 7 — Production operations | 0 / 6 | 0% | Not started |
| **Overall** | **31 / 44** | **70%** | Demo lifecycle is coherent; controlled writes and operations remain |

## Completed capabilities

- End-to-end release, governance, distribution and production trace with exact stored relationships.
- SSR/ASR profiles, component deltas, frozen manifests, snapshot history/comparison, release matrix and software passport.
- SCR, Issue and DVP catalogs; snapshot-scoped coverage, impact evidence and append-only judgments.
- Approval actions, release decisions, delivery revisions, distributions, production authorizations, deployments, changeovers and batches.
- Bounded/filterable DVP, distribution, production, governance and audit catalogs.
- PostgreSQL append-only protection for audit events, impact assessments, acceptance-to-DVP links and resource links.
- Explicit security/consistency contracts for all 14 write routes.
- OIDC validation and exact scoped authorization for all 14 write routes when OIDC mode is enabled.
- Trusted authenticated-actor binding and atomic audit events for all 14 current write routes.
- Snapshot and production-command rollback tests proving that an audit failure leaves no domain change.
- 49 backend test modules; the latest full run passed all 477 tests under Python 3.12, including 31 real PostgreSQL tests without skips.
- Optional request-ID replay and PostgreSQL serialization for Snapshot numbering and shared Production Batch quotas, without a new migration.

## Current limitations and risks

1. No approved OIDC issuer, audience or JWKS endpoint is configured in a target environment.
2. There is no audited principal/grant administration API or browser login/session flow.
3. Snapshot/Batch and Approval/Decision now provide optional request-ID idempotency; several other commands still lack it.
4. Snapshot numbering and shared production batch-limit checks are now serialized with PostgreSQL row locks. Approval actions and release decisions now share transaction locks; other commands remain unfinished.
5. Actual-software reporting is a mutable overwrite without an optimistic-concurrency token or explicit correction command, although every report is now audited.
6. Some legacy list/history endpoints remain unbounded.
7. CI, backup/restore, monitoring, alerting and incident runbooks are not present.
8. Public reads are suitable only for non-sensitive sample data; CORS is not access control.

## Recommended next development package

The first Phase 6 package below is implemented for Snapshot and Production Batch. Continue with **delivery/distribution/authorization/deployment/changeover retry safety and actual-software conflict control**, and keep public staging read-only. The original scope and acceptance criteria remain below for traceability.

### Scope

1. Inspect existing request-ID patterns used by impact assessments, acceptance-to-DVP assignments, test releases and resources; reuse their conflict semantics where appropriate.
2. Design explicit idempotency contracts for snapshot creation and production batch creation without breaking existing controlled-development clients unnecessarily.
3. Serialize Snapshot number allocation using the owning Release row or an equally explicit PostgreSQL locking strategy.
4. Serialize production batch-limit evaluation and creation using the relevant authorization/deployment rows.
5. Decide and document the retry contract for duplicate business numbers versus a client-generated request ID.
6. Add real PostgreSQL concurrency coverage where SQLite cannot demonstrate row-lock behavior.
7. Update the executable write contracts and all affected API/database/security/status documentation.

### Acceptance criteria

- Identical retried requests return the original result without a second domain record or audit event.
- Reusing an idempotency key with different content returns a conflict.
- Two concurrent Snapshot requests cannot allocate the same number.
- Concurrent batch requests cannot exceed a finite authorization batch limit.
- Domain and audit changes remain atomic on every failure path.
- Existing authorization and authenticated-actor guarantees remain intact.
- The complete backend suite passes; migration head and generated PostgreSQL SQL are validated if the schema changes.
- `PROJECT_STATUS.md`, `ROADMAP.md`, `API.md`, `DATABASE.md`, `SECURITY.md`, `docs/write-contracts.md` and `CHANGELOG.md` are synchronized as applicable.
- Changes are committed and pushed to GitHub `main`; public staging remains read-only and is rechecked after deployment.

## Verification commands

Use Python 3.12, matching `backend/Dockerfile`.

```bash
cd backend
pytest -q
```

If dependencies are not installed locally, use the repository requirement files without changing their pins. For a schema change, also verify the single Alembic head and PostgreSQL SQL generation. Run the frontend production build only when frontend code or its contracts change.

After a push, verify:

```text
GET  https://softwarelifecycle-api-test.onrender.com/health/ready
POST https://softwarelifecycle-api-test.onrender.com/api/v1/deployments
GET  https://softwarelifecycle.whf969.com
```

Expected public state after this package deploys: API `0.15.0`, exact required database revision, POST rejected with `403 read_only_mode`, frontend HTTP 200.

## Working-tree caution

At handoff time, `frontend/app/activity/page 2.tsx` is an unrelated untracked duplicate file. It was not used, edited, committed or deleted by the completed work. Preserve it unless ownership is explicitly resolved.

## Completion and handback protocol

At the end of the cloud development task:

1. Review the final diff and exclude unrelated files.
2. Run proportional tests and record exact results/warnings.
3. Update `PROJECT_STATUS.md` and `CHANGELOG.md`, plus contract documents affected by the change.
4. Commit and push the scoped result.
5. Report development mode (Codex or ChatGPT), changed files, behavior, migrations, tests, commit hash, push/deployment state, evidence-based module percentages with unfinished content, and remaining development steps.

Fast handoff commands remain:

- `规划：<目标>` — decide scope and acceptance criteria.
- `开发：<任务>` — implement, test, document, commit and push.
- `检查：<范围>` — evidence-backed review without implicit mutation.
- `汇总：SoftwareLifeCycle 当前状态` — reconstruct status from repository evidence.
- `继续：下一阶段` — resume the highest-priority ready item.

## Phase 6 first-package verification — 2026-10-01

Starting main: `a5db39eccb0a5a73ea3232f455a9167f1af835a4`. API code is `0.14.0`;
schema remains `0016_authenticated_audit_actors`. Complete backend run: 421 passed,
1384 warnings, no skips; 13 tests use real PostgreSQL 16.15 migrated schemas and
independent sessions. Single Alembic head and PostgreSQL SQL generation passed.
No frontend change/build and no schema migration were needed. Optional-key/no-key,
actor/scope and transaction details are in `docs/write-contracts.md`. Deployment
verification: Render `dep-dauvf1m417fc73fq13dg` is live for commit
`3968f9f007e2a00a7268074e5e66cc1a0a8db2cc`; API health returned 200 / `0.14.0` /
`0016_authenticated_audit_actors`, harmless deployment POST returned
403 `read_only_mode`, and frontend returned HTTP 200 with a rendered Dashboard.
The unrelated duplicate frontend file was absent in this checkout and untouched.

## Phase 6 second package — development report

Development mode: **Codex**. API code is `0.15.0`; schema head remains
`0016_authenticated_audit_actors`, with no migration. Approval Action supports
optional request UUID plus required exact expected step for keyed calls. Release
Decision supports optional request UUID. Shared ApprovalRequest locks serialize
step transitions and decisions, and atomic audit evidence preserves original replay
results. No-key clients and distinct decision-number history stay compatible.

Use the current-progress section of ROADMAP.md for module percentages and unfinished
steps. Request-ID/row-lock coverage is 8/14 (57%); exact scope, actor and atomic audit
coverage is 14/14 (100%). Broad roadmap progress stays 31/44 (70%), not production
readiness. Complete test and deployment evidence is recorded after verification.

Second-package verification: Python 3.12 full backend run **477 passed, 1646 warnings, no skips**, including **31 real PostgreSQL 16.15 tests**. Single Alembic head `0016_authenticated_audit_actors` and PostgreSQL SQL generation passed. No new migration or frontend change/build. Deployment verification follows the scoped push.
