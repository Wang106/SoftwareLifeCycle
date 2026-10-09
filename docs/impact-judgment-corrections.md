# Impact judgment historical replacement

Updated: 2026-10-09 (Asia/Shanghai), Codex. API 0.18.39, schema 0021.

## Scope

The existing `POST /api/v1/issues/{issue_no}/impact-assessments` accepts an
explicit correction. It remains one of the fourteen business command routes,
not a fifteenth route. Public read-only protection and exact REVIEWER scope
(or the exceptional PLATFORM_ADMIN override) are unchanged. In OIDC mode the
authenticated actor, not `actor_name`, is the operator; declarations are retained.
Auth-disabled legacy/local mode remains compatible, not approved production access.

This slice implements **supersession**, not withdrawal, release approval reversal,
test-result correction, Acceptance–DVP replacement or physical flashing reversal.
It does not change any frozen snapshot, DVP result, release decision or batch.

## Explicit original-record precondition

In addition to every ordinary assessment field, supply both:

```json
{
  "supersedes_id": "<current-effective-assessment-UUID>",
  "correction_reason": "Why the original judgment must be replaced"
}
```

Use a new `request_id` and the same Issue, Release and frozen Snapshot as the
predecessor. Supply the complete new decision/reason/evidence reference/declaration;
it is a new judgment, not a patch or a copied current state. `correction_reason`
is normalized nonblank text, at most 4000 characters, distinct from the judgment's
business `reason`. One field without the other is 422; both omitted/null retain
the ordinary append behavior. A malformed UUID is 422.

The Issue row lock serializes ordinary writes, corrections and retries through
business and audit commit. The predecessor must be the latest effective leaf for
that exact context at write time. A missing, foreign, self-referential, already
superseded or stale predecessor returns 409 without business/audit partial writes.
This UUID is the optimistic precondition; never silently retarget a stale request.

201 creates a new row; exact normalized request/actor replay returns that original
row with 200 and no new audit. Changing predecessor, correction reason, any ordinary
field or trusted actor under the same key conflicts. Exact replay remains possible
after another correction, subject to current authorization; it never makes the
replayed judgment current again. A correction replay also requires matching original
SUPERSEDE audit relationship metadata. Authorization and validation still run.

## Preserved audit and reads

The original row/event are never updated/deleted. A new `EVT-IMPACT-{request_id}`
atomic `ISSUE_IMPACT/SUPERSEDE` event records new decision, predecessor UUID,
previous decision and correction reason, plus the existing actor/snapshot bindings
and normalized nullable evidence-reference digest. Reference text is not copied to
activity payload. Original ASSESS events/receipts remain original facts, not claims
about current impact. The correction reason is visible in audit/history: do not
put credentials or unnecessary confidential data into it.

Current bounded candidate/evidence reads and internal legacy helper reads exclude
explicitly superseded rows in SQL before applying existing latest-time/UUID ordering
to remaining leaves. Independent historical judgments without an explicit predecessor
remain independent; they are not retroactively relabeled as corrections. New frozen
snapshots never inherit an earlier snapshot's judgment.

Paginated historical assessments keep every row and expose `supersedes_id`,
`correction_reason` and `superseded_by_id`. Successor resolution is SQL-bounded,
including when the successor is on another page. Summary counts count history, not
only effective leaves. The POST response retains original judgment fields; its
`superseded_by_id` is a separately observed relationship, not the original receipt.
The bilingual history/evidence UI shows UUIDs and independent predecessor/replacement
audit links. Lack of a supersession marker does not prove a row is the latest judgment.

## Migration and deployment boundary

`0021_impact_supersession` adds nullable predecessor/reason fields without updating
legacy rows. A composite self-FK enforces identical Issue/Release/Snapshot, a unique
predecessor constraint prevents branches, and checks reject self-links and incomplete
or blank/oversized correction metadata. Existing append-only UPDATE/DELETE triggers
remain. Backward links to existing immutable rows and no self-link prevent cycles.

Downgrade refuses while any correction exists, so dropping metadata cannot silently
resurrect old judgments. Do not delete history to force downgrade. Use the approved
backup/recovery procedure with matching schema/application versions instead.
Readiness requires 0021; deploying code alone against 0020 is not successful API
deployment. Render online API/schema/deployment are not independently verified here.

Frontend relationship fields are optional for compatibility with older read APIs.
Existing `/commands` prepare/send/recovery parsers still reject correction-only fields
and cannot confirm a SUPERSEDE event as an ordinary ASSESS receipt. No correction
submission/retry/import UI, credentials, provider gates or actual identities are enabled.
Actual provider/multi-user/browser and internal environment acceptance remain pending.

## Verification and next slice

SQLite/handler tests cover preservation, exact replay after a newer correction,
stale/foreign context, actor/role denials, rollback, effective read parity and bounded
growth. Isolated migrated PostgreSQL tests cover blocked concurrent correction/retry,
branch/shape/context constraints, atomic interruption, append triggers and guarded
migration downgrade. Bilingual compiled UI tests retain exact UUIDs/reasons/links;
ordinary receipt tests reject correction protocol confusion.

Next: Acceptance–DVP relationship replacement/withdrawal, then controlled correction
submission and original-audit recovery, impact withdrawal and release-review/downstream
correction policies. Full judgment-correction and correction-E2E milestones stay pending.
