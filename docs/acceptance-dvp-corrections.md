# Acceptance–DVP relationship replacement and withdrawal

Updated: 2026-10-10 (Asia/Shanghai), Codex. API 0.18.40, schema 0022.

## Existing command, explicit history

`POST /api/v1/changes/{request_no}/acceptance-dvp-links` remains one of the
14 business commands. Existing request fields are unchanged. Optional `action`
defaults to `ASSIGN`; optional `supersedes_id` defaults to null. `reason` is the
required, trimmed explanation (1..4000 characters). Each operation has a new
`request_id`; identical retries return 200, new records 201.

| Action | Predecessor | DVP target | Effect |
| --- | --- | --- | --- |
| ASSIGN | Omit/null | Test in this SCR | Add an independent effective relationship |
| SUPERSEDE | Exact current effective relationship ID | Different test in this SCR | End predecessor and add replacement |
| WITHDRAW | Exact current effective relationship ID | Same test as predecessor | End relationship; withdrawal row is historical only |

Both criterion and DVP plan must belong to the URL's exact SCR. Replacement and
withdrawal keep the predecessor's criterion. Self/missing/foreign/already-ended
predecessors, mismatched withdrawal targets, same-target replacements and duplicate
effective criterion/test pairs return 409. Invalid action/predecessor pairs return
422. Missing requested criterion/test returns 404. A withdrawn record cannot be
replaced or withdrawn again; a deliberate independent ASSIGN can reassign the
same test using a new ID and reason after withdrawal/replacement.

The current exact ACTIVE project CONTRIBUTOR authorization (or existing global
administrator exception) is required for every action and retry. Trusted actor
identity and request declaration remain separate. Auth-disabled legacy local mode
is retained, not approved as production authentication.

## Atomic writes and retry evidence

All actions hold the same SCR row lock through business record, audit and commit.
Concurrent different IDs cannot end the same predecessor twice or create duplicate
effective pairs. Identical concurrent retries append one business/audit record.
Failure during audit rolls back the new relationship and leaves predecessor effective.

Original rows and original ASSIGN audit payloads are never changed. New audit events
retain `EVT-AC-{request_id}`, event type ACCEPTANCE_DVP and entity SoftwareChangeRequest;
action is SUPERSEDE or WITHDRAW. Payload includes original assignment/criterion/new
DVP IDs, `supersedes_id`, `previous_dvp_item_id`, `previous_action`, and actor source.
Reason is audit detail. Correction retry verifies row fields, trusted actor/declaration,
original entity, action, detail and full payload. Missing/malformed/tampered audit
conflicts. Ordinary legacy ASSIGN retry behavior stays compatible.

POST returns original operation fields plus action/predecessor and separately
observed `superseded_by_id`. Retrying an operation after its later replacement or
withdrawal returns the original operation; it never restores effectiveness. A receipt
proves an original operation, not the present relationship or test success.

## Effective reads and complete history

Effective relationships are non-WITHDRAW rows without any explicit successor.
Timestamp order does not choose effectiveness. Bounded SCR summaries/groups/items,
DVP profile/reverse criterion relations, and retained internal coverage helper use
the same SQL predicate. Multiple independent current test assignments remain valid.

The existing criterion assignments page retains every row with action, predecessor,
successor and `effective`. Total/selected `assignment_count` includes full history;
group `item_count` and coverage use only effective relationships. Forward/backward
links are scalar SQL subqueries across page boundaries; no growing ORM histories
or request-ID arrays are transferred. Current definitions/relationships remain live;
a selected frozen Snapshot pins execution evidence only, not old assignments.
Replacement/withdrawal cannot erase executions, rewrite release history, change
readiness gates or assert tests/acceptance passed.

## Migration and delivery limits

0022 adds default ASSIGN and nullable predecessor metadata, with no UPDATE/backfill
of old rows or audits. Same-criterion self-FK, unique successor and action/self checks
guard history; existing UPDATE/DELETE rejection triggers stay intact. The permanent
criterion/test unique is removed to permit deliberate reassignment; command-side
effective-pair uniqueness is enforced under the SCR lock. Direct arbitrary DB inserts
are not a supported business-command path. Downgrade refuses when any correction
exists; never remove history to make downgrade pass.

Bilingual coverage pages display read-only relationship history and exact independent
audit links. The ordinary ASSIGN frontend parser still rejects action/predecessor
fields and SUPERSEDE/WITHDRAW audit receipts. Controlled correction submission,
audit recovery/import and actual multi-user/browser acceptance remain pending.
Public sample remains read-only, OIDC/all submission gates disabled. Render online
API/schema deployment is unverified; Cloudflare build is frontend evidence only.
