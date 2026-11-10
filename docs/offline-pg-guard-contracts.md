# Selected 0029 function and trigger contracts

## Verified baseline and purpose

PR214 merged as main `86e3fba3d3f8c5b5334ecb1cfd683b952272195b`.
[Main CI42794359157](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42794359157)
passed: 3626 backend tests, 2857 subtests, 308 PostgreSQL-module cases without skips,
2274 frontend tests and strict 16+16 browser journeys. Cloudflare production build
`dc3a54b5-3f7b-4f68-abdd-c0fff808f3ba`, version
`f594eec4-a7d1-4e19-a25c-4b2f6e587a89`, succeeded for that commit. Actions deployment
and continuation were skipped; Render was not verified.

The separately approved actual [joint run42798938628](https://github.com/Wang106/SoftwareLifeCycle/actions/runs/42798938628)
passed once, attempt1, at the same commit. Its single lifecycle receipt records
application_started/database_ready=true, five API cases, 0029 single head,
VARCHAR(64), selected seven tables/three functions/six triggers and four empty
business-table counts. Two preparation and three joint containers were confirmed
removed; no artifacts were uploaded. Complete-schema, SELECT-only-role and provenance
flags remain false. That run did not use this new comparison and is not its runtime
acceptance. Historical "unpublished/unexecuted" entries describe their earlier stages.

Counts alone cannot detect a changed function body or incorrectly bound trigger.
This package reuses the existing catalog collector and fixed manifest to compare
only three functions and six triggers. It does not add another collector, alter
the manifest or claim the complete 120-fact public checklist.

## Catalog observation v2

`offline_pg_catalog_evidence.collect` retains its caller-owned active read-only,
repeatable-read transaction and seven fixed SELECTs. It adds only these trigger
count/length/presence fields:

- argument_count from tgnargs;
- argument_bytes from octet_length(tgargs);
- has_when from tgqual IS NOT NULL.

The output format is now `slc-pg16-catalog-observation-v2`. Old v1 reports lack
the evidence and are rejected by the new comparison, not filled with defaults.
Existing raw definition text is preserved and can still contain literal trigger
arguments and the WHEN expression. The new fields do not add those payloads, but
the full catalog report must remain with its authorized caller. Definition text is
not parsed or normalized. Namespace,
transaction ownership, timeouts, record/output limits and fixed-error behavior remain.
Existing consumers are the isolated catalog, API/PG and migration-SQL CI tests;
the manual image lifecycle does not call this collector.

## Fixed, bounded comparison

`offline_pg_guard_contracts.check_observation(document, namespace)` does no
network, SQL, process, container or application work. Import does not read evidence.
Calling it reads only the existing fixed local manifest through its bounded loader,
which verifies the manifest's exact SHA256 and metadata. There is no alternative
expected checklist, database target, file input CLI or execution option.

The entire observation envelope and all six groups are validated against the
collector's types, field sets, namespace, row/text/array limits and 512KiB output
bound before comparison. Duplicate records, malformed digests, bool/integer aliases,
missing v2 fields or other malformed input return UNKNOWN without raw diagnostics.
Absent valid observations or different selected properties return GUARD_CONTRACT_MISMATCH.

The nine checks compare:

- Functions: exact selected names, no-argument identity, trigger return type,
  plpgsql, non-SECURITY-DEFINER and original prosrc UTF-8 SHA256 from the fixed
  manifest. Same-name overloads cannot substitute for the unique expected function.
- Triggers: exact table/function binding in the explicitly supplied namespace,
  no function arguments, BEFORE/ROW DELETE+UPDATE type bits27, enabled O,
  non-internal/non-constraint, zero argument count AND bytes, and no WHEN.

The fixed manifest's public namespace is the reference template domain. Actual
observations and function references must remain in the caller's exact namespace;
nothing is renamed to public or passed to the 120-fact checker. The result never
uses STRUCTURE_CHECKLIST_MATCHED. Missing/duplicate/overloaded or incorrectly bound
objects cannot match. Nonselected objects are outside coverage, not proved absent.

body_bytes is checked only as strict bounded metadata, not independently authenticated
against source. The fixed SHA256 binds the expected original body bytes, while the
input hash/length can both be fabricated. No AST extractor or loose deparse parser
is introduced. Other function/trigger properties and actual behavior remain outside
this finite comparison, including function configuration/dependencies and replication
session effects. Raw trigger definition text is not an additional contract.

All results keep database_verified, complete_schema_verified, readonly_role_verified,
provenance_authenticated and transaction_completed false. A matching report does
not establish origin, freshness, completed collection/rollback, privileges, behavior,
API readiness or deployment. KeyboardInterrupt/SystemExit propagate unchanged.

## Verification and execution boundary

Initial capability tests ran before implementation: 18 methods, 17 failures and one
existing fail-closed control pass. Local work uses synthetic observations and mock
connections only. Tests cover valid/absent/duplicate/overloaded objects, function
body/metadata and trigger binding/events/WHEN/arguments, strict v2 and namespace,
resource/type bounds, immutable inputs and sanitized failures.

Existing real PG CI tests call the same comparison after their existing original
migration in a newly owned random schema. Within that same disposable fixture,
the existing disabled-trigger case also observes a WHEN filter and nonempty trigger
argument; the changed-function case must mismatch. No external target, new service,
role, GRANT/REVOKE or public-schema operation is introduced. These SQL cases are
prepared, not run locally; exact-candidate full CI must establish their result.

No new manual rehearsal is dispatched. The old lifecycle entrypoint, helpers,
Dockerfiles, dependencies, migrations, permissions and CI gates are unchanged.
Integrating this comparison with an actual image lifecycle remains a separate step.
Business 36/44=82%, increment0; modules100/100demo/100demo/100/89/60/17;
plans100/100/20/33/40/40/0; browser1/4 and finite plan8/8 unchanged.

Local final checks: 21 focused, 26 collector, 784 full offline, 52 automation and
126 CI guards pass, along with in-memory compilation, progress and whitespace checks.
Independent final review passed 21+26 cases and 1293 extra synthetic assertions,
with no blocker. Its documentation correction makes clear that preserved raw trigger
definitions can contain arguments/WHEN text. Exact-candidate CI remains pending.
