# SSR/ASR release-evidence type drift safety

## Scope

This package changes only the read-only `/demo/releases` presentation. It does not change the API, database, sample installation, identity, authorization, writes, CI, schedules, or provider configuration.

The evidence endpoint normally supplies `STANDARD` and `APPLICATION`. The UI must nevertheless fail closed if a future, malformed, or drifted value reaches the page:

- exact `STANDARD` maps to the SSR detail route;
- exact `APPLICATION` maps to the ASR detail, readiness, and passport routes;
- every other value remains visible with its exact version and raw type;
- an unrecognized value must not be mapped to either SSR or ASR and must not receive an invented release, readiness, or passport route.

Snapshot, approval, decision, change, and DVP evidence remains visible because hiding the record would conceal the drift. Those records remain observations only and do not prove release authority or a formal release.

## Verification

The release-evidence component test renders the real server component in English and Chinese. It verifies the two known mappings and injects `FUTURE` to prove that the record and bilingual warning remain visible while all type-derived release links are absent.

Local checkpoint:

- targeted component tests: 8 passed;
- complete frontend suite: 1,550 passed, 0 failed, 0 skipped;
- Next.js 16.4.2 production build: passed;
- Worker configuration check: passed;
- disabled-auth bilingual SSR check: passed.

The protected PR still requires its exact-head Backend/PostgreSQL/migrations, Frontend/build, and CI acceptance checks. After merge, main CI and Cloudflare, Render, and Actions evidence must be checked independently.
