# Private review and evidence preparation contexts (P4)

## Scope and permission decision

This bounded package assists four existing `/commands` forms: approval action,
acceptance-to-DVP association, Issue impact assessment and resource-link registration.
It does not create another write command or change existing command authorization,
approval assignment, idempotency, audit or business rules.

The owner explicitly approved this private-read policy on 2026-10-28. These are new
minimum read contracts, not inferred permissions from public sample catalogues:

| Context | Required current project role | Exact boundary |
| --- | --- | --- |
| Approval current step | REVIEWER | Approval targets a RELEASE with an application project, or a SCR with a project |
| Acceptance criteria and DVP items | CONTRIBUTOR | Both belong to the exact selected SCR; no cross-SCR DVP selection |
| Issue release snapshots | REVIEWER | Explicit release's application project is among Issue-linked SCR projects, and release software is an existing linked-SCR candidate |
| Resource target | CONTRIBUTOR | Exact scoped object; an Issue requires membership in every nonempty linked project |

All require an authenticated current ACTIVE USER and current session validation.
PLATFORM_ADMIN alone never bypasses these new read checks. Missing, unsupported or
unauthorized target contexts return no candidate information. Supplier/customer and
objects without authoritative project scope are not exposed by the new resolver;
the existing deliberate manual preparation path remains available without changed
writer permissions. No real identities, grants, provider settings or secrets are configured.

## Fixed read interfaces

Under `/api/v1/evidence-selection-context`:

- `GET /approvals/{approval_no}/current-step`: exact approval UUID/reference,
  target type/UUID, project UUID, optional snapshot UUID and status; the single
  current step UUID/order/status/role label. No approver name or historical comments.
- `GET /changes/{request_no}/criteria`: bounded same-SCR criterion UUID/reference
  and description needed to distinguish the acceptance requirement.
- `GET /changes/{request_no}/dvp-items`: bounded same-SCR item UUID/reference/title
  and exact plan UUID/reference. A matching name is not sufficient affiliation.
- `GET /issues/{issue_no}/releases/{release_id}/snapshots`: bounded FROZEN snapshots
  of that explicit release, with UUID/reference/number/status. Neither the latest
  version string nor a shared software candidate automatically establishes impact.
- `GET /resources/{entity_type}/{entity_id}`: exact type/UUID, canonical reference
  and authorized project IDs only. Supported scoped types are PROJECT, RELEASE,
  SNAPSHOT, SCR, DVP_ITEM, TEST_RELEASE, DVP_EXECUTION and ISSUE.

Lists have bounded limits/offsets and deterministic ordering; they disclose no global
counts, unrelated entities, identities, resource locations, binary storage references
or historical audit details. Current-step role text is a business label, not an extra
identity assignment or permission. Closed approvals cannot become actionable by
selecting an old step. Reads do not emit business records or audit events.

## Browser boundary and deliberate selection

The independently default-off `PRIVATE_EVIDENCE_SELECTION_MODE` requires the exact
approved API base and application origin, existing authenticated USER/session checks,
and its fixed same-origin proxy. The proxy performs only the listed backend GETs.
The offline readonly inventory forces the mode disabled. There is no activation of
actual configuration, no added credential and no generic URL proxy.

Loading and applying are explicit actions. Raw references, descriptions and titles
remain untranslated inside bilingual labels. Target/type/release changes invalidate
unattempted selected context and confirmation; stale replies cannot overwrite a
new target. Deliberate manual fallback clears the selected-context indication.
Once a write has been attempted, its original request/body/key remain frozen,
including an unknown result. A selector cannot authorize a send, generate a replacement
request or overwrite that attempted payload.

These are bounded observations, not durable capabilities or frozen snapshots of all
mutable data. Existing command services independently enforce their current rules.
No new approval participant assignment, release-status requirement, cross-project
resource permission, same-name inference or automatic impact judgment is introduced.

## Validation and acceptance boundaries

Required evidence covers valid scoped contexts, inactive users/sessions/roles,
admin-only and foreign-parent denials, all-project Issue membership, exact software
and SCR relationships, minimal fields, no writes, stable bounded pages, current-step
changes, raw bilingual rendering and interrupted/repeated/unknown UI flows. Real
PostgreSQL tests must verify claimed concurrent lock behavior rather than relying on
SQLite or query compilation. Complete exact-head CI and fresh main/provider evidence
are mandatory before engineering closure.

Local synthetic backend/component/proxy tests do not establish actual browser,
real identity, multiuser or production acceptance. Overall36/44=82% stays unchanged
until its actual milestone criteria pass. VIN, actual AI, binary storage and company
operations remain separately unresolved; this package does not silently complete them.
