# Codex repository instructions

Repository: Wang106/SoftwareLifeCycle. Use the current main branch as the baseline; preserve unrelated local changes.

## GitHub Actions bounded development
See docs/automation/README.md and docs/automation/tasks.json. Missing
CODEX_AUTODEV_ENABLED/credentials means inactive, not configured success.
The model runner returns a bounded data-only patch; a clean publisher handles
GitHub writes and an independent controller validates exact-head CI/merge/main.
Within that runner, do not execute the publish/merge instructions below yourself.
Never alter the scheduler/CI/deployment, existing tests, dependencies or migrations
from a queued candidate. New scoped tests are allowed. Resume codex-state only
after checking the original run and remote branch; do not rely on chat history.
done_code is code acceptance only; live provider/schema and real acceptance are
separate evidence. Two scoped UI tasks are approved in the initial queue;
subsequent broader tasks remain disabled until their scope is reviewed.

## Start each new session
Read START_HERE.md, REQUIREMENTS.md, DEVELOPMENT_STATUS.md, ROADMAP.md and docs/development-plan-progress.json.
Read the current-entry section and newest dated records in HANDOFF.md; it also contains historical states.
Check actual branch/head, open pull requests, relevant CI and deployment evidence before proceeding. Latest verified evidence supersedes older pending records.
Do not assume the prior chat or this desktop workspace is available. Report missing repository access or dependencies accurately.

## Development and validation
Use Codex, an isolated feature branch, targeted meaningful regression coverage and existing CI. Follow frontend/package.json and .github/workflows/ci.yml for actual commands.
Run python scripts/report_development_plan_progress.py --check when updating progress. Do not raise milestones solely because code or documentation was added.
Publish the change, verify its exact head CI, and merge successful changes to main under the user's existing instruction to continue development and automatically commit/deploy.
Check main CI and provider deployment separately. An unverified or skipped deployment is not success. Do not force-push or overwrite unrelated changes.
Update DEVELOPMENT_STATUS.md and append HANDOFF.md with changes, exact commit/PR/test/deployment evidence, limitations and the next concrete package.
Report all seven module percentages and seven development-plan percentages, remaining work and actual checks.

## Current operating boundaries
Public environment is sample-only/read-only; OIDC and grant-status submission remain disabled.
Internal server deployment has NOT started; no internal service, database, installation or real browser acceptance is complete.
SSO/OIDC is undecided. Administrator, release-approval and production-authorization personnel are assigned by the user later.
Possible internal target is offline, Windows or without Docker; exact OS/version/architecture and installation constraints are unconfirmed.
Do not provision identities, grants, provider secrets or enable real writes as part of routine feature development.
The browser previously denied site access; do not bypass that denial. HTTP/SSR tests do not substitute for real browser acceptance.
GitHub Actions deploy.yml is independently gated and currently skipped. Existing provider automatic deployment does not prove an Actions deployment gate.
Keep 14 business commands, 2 own-session controls, 6 administrator commands and offline operator modes separately counted.
Original SoftwareLifeCycle_12 chat text has not been retrieved; repository requirements are the available baseline, not a completed transcript reconciliation.
