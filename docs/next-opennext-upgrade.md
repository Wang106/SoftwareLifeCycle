# Next.js / OpenNext supported dependency upgrade

Reviewed on 2026-10-21 with Codex / ChatGPT Work. User explicitly authorized this dependency package after PR #93 and main CI both failed the OpenNext Next.js support check.

## Version selection

| Package | Previous | Selected |
| --- | --- | --- |
| Next.js | 15.5.24 | 16.4.2 |
| OpenNext Cloudflare | 1.20.6 | 1.20.12 |
| React / React DOM | 19.0.0 | 19.3.1 |
| Wrangler (root and frontend) | 4.142.0 range/pin | 4.151.3 exact pin |

Registry metadata for OpenNext 1.20.12 requires Next.js `>=15.5.28 <16 || >=16.4.1` and Wrangler `^4.148.0`; the selected stable versions satisfy those constraints. Next.js 16.4.2 requires Node >=20.9.0; existing Node 22 CI and Docker images satisfy it. No prerelease or unsupported-version bypass is used.

The previous build error is evidence about the adapter's version validation, not proof that every Next.js 15 release is unsupported. The official October 14 security release also lists 15.5.28 as Maintenance LTS. This authorized package selects the current stable Next.js 16 line and validates the application against it.

## Compatibility changes

- Accept Next.js 16 generated TypeScript configuration: `jsx=react-jsx`, development generated-type include, and root-parameter declaration import.
- Regenerate both npm lockfiles and verify clean `npm ci` installation.
- Scope a `glob=10.5.0` override only to `@node-minify/core`. OpenNext's new AWS adapter transitively pins vulnerable glob 10.3.3; the same-major patch fixes GHSA-5j98-mcp5-4vw2. Keep existing PostCSS/Undici overrides.
- Preserve dynamic request rendering (`connection()`), API runtime variables, public sample read-only behavior and all disabled authentication/submission controls.
- Existing Next.js production build uses the Next.js 16 default bundler. No application API, schema, Seed, CI gate, provider permission or identity configuration changes.

## Validation and recovery

Run frontend tests, `cf:check`, `cf:build`, `auth:check`, root/frontend npm audit, progress ledger check and the existing full three-job CI. `auth:check` exercises real local production Next handlers and bilingual SSR with all submission gates disabled; it is not real-provider/browser acceptance.

Merge this dependency PR only after its current head contains current main and all three required jobs succeed. Check main CI, Cloudflare and Render separately after merging. Then merge current main into PR #93 without force-push and validate its new head; its old successful test counts do not establish compatibility with this upgrade. Rollback must use a reviewed revert PR and pass protected checks; reverting to 15.5.24 would restore the known failed support check.

## Primary references

- https://nextjs.org/support-policy
- https://nextjs.org/docs/app/guides/upgrading/version-16
- https://nextjs.org/blog/nextjs-security-update-october-14-2026
- https://github.com/opennextjs/opennextjs-cloudflare/releases
- https://github.com/advisories/GHSA-5j98-mcp5-4vw2

Exact commit, PR, CI and provider evidence is recorded in the PR and HANDOFF after verification. Business acceptance remains 36/44 (82%); dependency maintenance does not complete provider, multi-user or operational acceptance milestones.
