# Release-chain revocation read-only display

The page `/governance/{kind}/{targetId}` reads the existing exact-UUID
`GET /api/v1/governance/{KIND}/{targetId}` once, with a ten-second timeout.
Kinds are RELEASE, DELIVERY_PACKAGE, DISTRIBUTION and AUTHORIZATION. Invalid kinds
or UUIDs perform no API request. Standard/application release and exact delivery
revision, distribution and authorization details link their own stored UUIDs.
Entry links and manual reread links disable prefetch. No write proxy, form,
automatic polling, submission capability or identity configuration is added.

The page separates recorded object status from ACTIVE, REVOKED,
BLOCKED_BY_ANCESTOR and UNRESOLVED. ACTIVE means no revocation was observed on this
path; it is not readiness, approval, permission or a write receipt. UNRESOLVED,
unavailable and malformed responses do not imply active authority or confirmed
empty history. Own revocation and ancestor blockers are displayed separately;
neither rewrites the original status or existing production facts.

The existing permanent ledger admits one revocation per exact object, so an
authority path has at most four records, including at most three ancestors.
This is bounded path history, not all downstream events or a truncated global
history. Response validation checks target-kind hierarchy, unique node kinds and
event UUIDs, record number/UUID binding, field lengths, valid timestamps and
state/eligibility consistency. It rejects oversized arrays rather than silently
truncating them. The existing API does not echo the requested target UUID; the
page relies on the fixed exact-target endpoint contract, without claiming that it
independently verifies the server's parent foreign keys.

Each event links `/activity/EVT-RCR-{event_uuid_without_hyphens}`, matching the
backend audit-key rule. Reason and recorded actor remain escaped original text
in both languages. Labels are Chinese by default and English on selection; UTC
timestamps and original UUIDs are retained. Audit navigation is a read of the
original operation, not proof inferred from current governance state.

API 0.18.45, schema 0026_release_chain_revocation and Seed are unchanged. New
behavior tests cover all four targets, exact GET/timeout and zero-read invalid
paths, bilingual own/ancestor display, raw evidence escaping, missing/unresolved
and contradictory data, array bounds and exact entry/audit links. Existing full
CI remains required, including PostgreSQL, migration and frontend build jobs.
These tests do not establish real desktop/mobile or multi-user acceptance.

Next package: separately review and implement a default-disabled revocation
submission protocol and original-audit recovery. Real identity, write gates,
production-fact correction and internal deployment remain separate work.
