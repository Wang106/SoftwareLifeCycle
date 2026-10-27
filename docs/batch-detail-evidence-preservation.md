# Batch detail: preserve raw evidence across interface languages

## Reproduction and scope

On main `2ab0b65cd98d51c42b40a55050107122fc5b27ab`, the Batch detail page
passed business notes and identifiers directly to `Localized`. Actual React server
rendering with the real LanguageProvider, Localized and translation dictionary
reproduced `Note` becoming `备注`, `ACTIVE` becoming `有效`, and whitespace-padded
notes retaining whitespace but changing their content in Chinese. English retained
the original values. This was fixture-only local component SSR, not live browser QA.

The page now isolates raw note, Batch/deployment/authorization/changeover identifiers,
release versions and snapshot numbers inside element children. The existing localization
component translates direct strings, not nested React elements. Labels, status enums,
reference-consistency labels and missing-value explanations remain bilingual. Compound
fields separate raw identifiers from translated status labels. Existing null/empty
fallback behavior, timestamps, HTML escaping and encoded URLs remain unchanged.

No global translator, API, backend, stored data, authentication, default-off controls,
provider settings, dependencies, CI or branch-protection gates change. This repairs
presentation of evidence; it does not translate or mutate stored business facts.

## Verification

`tests/batch-detail-raw-evidence.test.cjs` renders the actual page and real localization
components with a read-only fixture API. Sixteen cases cover both languages, dictionary
collisions, whitespace, HTML escaping, record/software identifiers, separately translated
enums, encoded history/authorization links, numeric zero, missing context and unavailable
responses. Existing structural localization coverage remains unchanged.

Local focused and independent review runs:157 tests passed, zero skipped. Full frontend1701 passed0skip; typecheck, Worker configuration and production build
passed. Final exact evidence is recorded in the current handoff and PR. Fresh exact-head/full PostgreSQL CI and fresh main evidence
remain mandatory; prior main evidence cannot substitute for this package's acceptance.

Public403/browser restrictions were not retried or bypassed. Actual component SSR is not
live Cloudflare/Render visual acceptance. Completion remains36/44=82%, with no business
milestone increase. Future work must be a concrete verified defect or explicitly approved
external acceptance, not an invented follow-on package.
