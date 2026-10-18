# ReleaseDecision supersession verification receipt

This receipt closes the automated CI and provider verification for pull request #70. It records exact evidence and does not enable any write path or represent production acceptance.

## Pull request and CI

- Final PR head: `6b0400404f9aee69eab98ebdaed12f747480a126`.
- An earlier head `969ef6e` failed localization coverage and was not merged.
- Exact-head workflow: `39107462789`; backend/PostgreSQL, frontend/Cloudflare build, and CI acceptance all succeeded.
- Merge commit: `b1097a97c80cc27f58699d9606020ad93ab48b61`.
- Independent main workflow: `39108012123`; the same three required jobs succeeded.
- Evidence counts: 2267 backend tests passed; 230 PostgreSQL-module cases ran without skips; 1462 frontend tests passed with zero failures or skips; Next and OpenNext builds completed.

## Provider state

- Cloudflare production build `a9bcc79f-187a-466d-b82c-b0a73765ab10` succeeded and produced version `9920621e-153f-4f63-89a1-898919f9c98e`.
- GitHub Actions deploy run `39108584069` and continuation `39108584068` were skipped, not successful deployments.
- Render did not start a new deployment because PR #70 changed only frontend paths while the service root is `backend`.
- Latest Render live deployment remains `dep-dba2n68ae00c739c31j0` at commit `aad807cd1ec16afccdf1cb3bb124c22dec0cc90a`; read-only health logs continued to return HTTP 200. This is a healthy unchanged backend, not evidence that merge `b1097a9` was deployed to Render.

## Safety and remaining acceptance

Public/demo operation remains read-only. OIDC, real business writes, internal-network deployment, and production configuration remain disabled. This receipt does not replace approved-provider multi-user, desktop/mobile, or bilingual browser acceptance.
