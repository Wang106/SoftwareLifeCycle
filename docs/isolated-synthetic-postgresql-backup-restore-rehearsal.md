# Isolated synthetic PostgreSQL backup / restore rehearsal

Status: PR #148 merged and exact-main native/provider evidence verified; see final comment6399485528. Native negative integration is implemented on the next feature branch, pending fresh exact-head CI. Not company recovery or production acceptance.
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

## Implemented rehearsal

`backend/app/ops/postgresql_backup_restore.py` is the single entry point. It accepts only literal `127.0.0.1` / `::1` PostgreSQL control connections, rejects hostnames, URL options, missing explicit credentials and the application/default database, generates `slc_rehearsal_<run-id>_source` and `slc_rehearsal_<run-id>_target` itself, and refuses an existing or equal database. Every psycopg/SQLAlchemy path fails closed when any inherited `PG*` libpq setting exists; native clients receive an environment with all inherited `PG*` values removed, an unusable default passfile and only the explicit URL password in `PGPASSWORD`. Command arguments, manifest and report contain no connection URL or password.

Before creation the rehearsal persists a run proof containing a random token and the exact local control identity. Each newly created database receives an exact run/role/token database comment; the proof records that database only after the marker and owner have been read back. Cleanup requires both the persisted record and matching live database marker/owner in the same control connection, so a same-role, same-name pre-existing database cannot be deleted merely because its owner matches.

The rehearsal creates and migrates the source, inserts one deterministic synthetic relationship chain and one audit event, runs native custom-format `pg_dump`, writes an archive manifest, verifies the archive size, SHA-256 and `pg_restore --list` catalog before creating the target, and restores with `--exit-on-error`. Source and target inventories must match on Alembic revision, table set, selected constraints/indexes/triggers, canonical row counts, and every inserted supplier/software/customer/project/release/audit field including foreign-key links and audit payload. The canonical values must also match the run-derived fixture, so equal counts cannot hide changed names or relationship corruption. A forbidden update against the restored audit event must be rejected by `trg_audit_events_append_only`; fresh reads then prove both source and target audit evidence remain unchanged.

Successful runs drop only the two exact run-owned databases after owner verification. Failed runs write a redacted report and retain owned databases for diagnosis. After reviewing the report, an operator can request cleanup by exact run ID; the command never terminates connections or uses forced drop.

Run from `backend` with a disposable local PostgreSQL whose role may create databases:

```bash
TEST_POSTGRES_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/postgres' \
  python -m app.ops.postgresql_backup_restore --evidence-dir ../ci-results
```

To clean a failed run after preserving its diagnostics:

```bash
TEST_POSTGRES_URL='postgresql+psycopg://USER:PASSWORD@127.0.0.1:5432/postgres' \
  python -m app.ops.postgresql_backup_restore \
    --evidence-dir ../ci-results --cleanup-run-id 0123456789ab
```

The complete backend suite executes the same native rehearsal in `test_postgresql_backup_restore_rehearsal.py` whenever `TEST_POSTGRES_URL` is configured. Existing CI already provides an ephemeral loopback PostgreSQL service and uploads `ci-results`; no workflow, credentials, scheduler or deployment configuration is changed. Unit coverage rejects hostnames/remote/default/optioned/uncredentialed connections, inherited libpq destination/service/options/password settings on every Python connection path, invalid or unowned names, equal/existing targets, missing/mismatched ownership proof or database markers, corrupt or mismatched manifests, missing archive objects, failed native restore, and equal-count canonical data/relationship corruption before the exact-head integration rehearsal runs.

This Work environment has neither PostgreSQL client binaries nor a local database, so it cannot supply native restore evidence locally. Local verification covers 23 fail-closed tests. The earlier exact-head CI artifact proved the native happy path and exact-head provenance, but an independent safety review required the additional environment, ownership and canonical-content protections above. A fresh exact-head backend CI artifact must re-prove the complete native dump/restore, run-marker cleanup and canonical comparison with no skipped test; missing clients, permissions, artifacts or any failed assertion fail the existing gate. Final exact head, CI, merge and provider evidence belongs in the package PR comment.

## Native negative integration extension (pending exact-head CI)

Package: `native-postgresql-restore-negative-integration`. User requested direct development; the current ChatGPT Work cloud task owns this feature branch, with the hourly executor excluded from duplicate work while it is active.

`test_native_postgresql_restore_negative_integration` performs a fresh native dump/restore under `ci-results/restore-negative-integration/`, then operates only on that run's newly created restored target. It proves three real negative scenarios without mocked database metadata/inventories: equal-count supplier content corruption; equal-count customer replacement plus project FK rewire with all constraints enabled; and a mismatched live DB marker preventing cleanup while preserving database/data/proof. Each scenario independently fingerprints all persisted fields from six source fixture tables before/after. The test reverses only its own synthetic changes and confirms the target fingerprint returns to baseline, archive bytes are unchanged, and original persisted creation proof permits safe final cleanup. It never restores over an existing database or disables constraints.

Run the existing PostgreSQL test module normally with TEST_POSTGRES_URL; no CI workflow change is needed. Fresh `negative-integration.json` reports source/checkout commits, per-case rejection evidence, counts/fingerprints and cleanup. On unexpected failure it marks failed and retains run-owned resources for diagnosis; follow the existing reviewed exact-run cleanup process. Expected asserted rejection is successful negative evidence, not an unexpected test failure. The main happy-path artifact remains separate at the parent ci-results path.

Local syntax was checked; this cloud environment lacks runtime dependencies and PostgreSQL tools. Fresh full CI and downloaded exact-head evidence are still required; no native result is claimed yet. Neither this extension nor PR148 alone completes retention, approved company disaster recovery or the ops-restore milestone.
