# Isolated synthetic PostgreSQL backup / restore rehearsal

Status: planned, not implemented or accepted. User approved this priority on 2026-10-25.
Package: `isolated-synthetic-postgresql-backup-restore-rehearsal`.

## Ownership and order
The existing sole Codex / ChatGPT Work executor must first resume any unfinished PR, exact-head CI, main CI or provider verification. Once this planning PR is closed and latest main still selects this package, implement one bounded package on a new feature branch. Do not create a second coding executor, scheduler or overlapping package. Do not default to another SSR/ASR parser edge-case or recursive documentation-only package without a concrete high-risk defect. A planning change is not a completed recovery exercise.

## Required safety boundary
- Use only disposable synthetic fixtures in a temporary local PostgreSQL instance / explicitly created temporary source database and a separately newly created temporary target database.
- Reject remote hosts, existing/default application databases (including the compose default), source equals target, unowned/non-temporary names, ambiguous connection options and any restore-over-existing-target operation before writes. Use an explicit rehearsal-only database name prefix plus a unique run identifier; no production/provider connection strings.
- No real company/customer data, identity/provider changes, secret or credential changes, paid API/quota purchases, CI/scheduler edits, deployment permission changes, production writes or user-local always-on CLI.
- Keep public/demo read-only and OIDC/real identity/business-write gates unchanged. Do not use the persistent compose volume or change existing seed behavior.
- Cleanup may affect only resources created and recorded as owned by this exact run. Preserve diagnostic evidence on failure; never drop arbitrary databases or terminate unrelated connections. Stop on permission, conflict, test failure or human-acceptance blocks.

## Implementation and verifiable deliverables
1. Reproducible preflight, fixture creation, backup and restore commands using PostgreSQL-native dump/restore, with nonzero/fail-closed handling. Migration upgrade/downgrade alone does not count as restore.
2. A manifest with run ID, exact source commit, PostgreSQL/client versions, schema revision, synthetic-fixture identity, archive size and checksum, timestamps and owned resource names. Redact secrets; do not log connection passwords.
3. Check archive integrity before restoring to a fresh isolated target. Verify schema/revision, expected tables/constraints/indexes/triggers, canonical data counts and content, relationships, and audit-event identities/payloads. Prove append-only audit protections still operate after restore, without mutating original evidence.
4. Test rejection of remote/default/existing/equal targets, corrupt or mismatched backup/manifest, failed restore and unsafe cleanup. Preserve existing assertions and full backend/PostgreSQL/frontend gates; do not weaken skips or change workflows to make tests pass.
5. Record repeatable commands and actual observed restore evidence, not just plans or previous CI results. If native client tools or temporary DB permissions are unavailable, record that exact blocker; do not silently substitute SQLite/schema round trips.
6. Update the three development ledgers and a runbook with precise PR/head/merge/CI/provider outcomes, limitations, and next acceptance step. Final post-merge evidence belongs in the package PR comment and the next substantive package's normal ledger update, rather than creating an endless evidence-only PR chain.

## Acceptance accounting
Business acceptance stays 36/44 (82%); seven module and seven plan percentages remain unchanged for this planning package. Do not tick the whole `ops-restore` milestone solely for a synthetic rehearsal: retention policy, approved environment/company disaster-recovery acceptance and any real data/network work remain separate, unaccepted and require appropriate authorization. Never call approval or a synthetic test a formal release.
