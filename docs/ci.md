# 持续集成 / Continuous integration

GitHub Actions runs `.github/workflows/ci.yml` for every push to `main`, every
pull request and manual `workflow_dispatch`. Two independent required-to-pass jobs
validate the backend/database and frontend. Branch protection is not configured
by this workflow; a green run is test evidence, not a production approval.

## 检查范围 / Checks

| Job | Runtime | Checks |
| --- | --- | --- |
| Backend, PostgreSQL and migrations | Python 3.12, disposable PostgreSQL 16 service | Existing pinned development requirements; single Alembic head matches runtime settings; full upgrade SQL and head downgrade SQL; fresh schema upgrade, head downgrade and re-upgrade; complete pytest suite; report rejects any skipped/failed/error case or absence of PostgreSQL-module cases |
| Frontend tests and Cloudflare production build | Node 22, `frontend/package-lock.json` | `npm ci`, all Node tests, `npm run cf:build` (Next.js type checks/production build and OpenNext Worker bundling) |

The backend job stores JUnit and generated migration SQL as `backend-evidence`
for 14 days, including failed-run reports when available. Failed checks fail their
job; no `continue-on-error` is used. Cancelling superseded runs saves runner time.
GitHub Actions must be enabled for the repository for runs to execute.

## 数据边界 / Data boundary

The service password in YAML is an ephemeral local test value, not a deployment
secret. No repository/environment secrets, Render/Cloudflare credentials, OIDC
tokens or staging/company database URLs are used. Checkout credentials are not
persisted. Actions are pinned to verified full commit SHAs and token permissions
are limited to `contents: read`. Pull requests use `pull_request`, never
`pull_request_target`. CI executes contributor code only on disposable hosted
runners and has no deployment step.

`check_migrations.py` accepts only a loopback PostgreSQL database named
`software_lifecycle_ci` with no URL options. It creates/removes its own random
schema; existing PostgreSQL tests likewise migrate disposable schemas. It does
not seed public/company data or modify public staging. PostgreSQL absence or
skips cannot silently produce a green full-suite result.

## 本地复现 / Reproduce locally

Provision a disposable local PostgreSQL 16 database named `software_lifecycle_ci`
whose test user may create schemas. Then, from the repository root:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements-dev.txt
export TEST_POSTGRES_URL='postgresql+psycopg://slc_ci:slc_ci_ephemeral@127.0.0.1:5432/software_lifecycle_ci'
export DATABASE_URL="$TEST_POSTGRES_URL"
export AUTH_MODE=disabled READ_ONLY_MODE=false SEED_ON_STARTUP=false
cd backend
../.venv/bin/python ../scripts/ci/check_migrations.py
../.venv/bin/python -m pytest -q --junitxml=../ci-results/backend.xml
../.venv/bin/python ../scripts/ci/check_backend_report.py ../ci-results/backend.xml
cd ../frontend
npm ci
npm test
NEXT_TELEMETRY_DISABLED=1 API_BASE_URL='' NEXT_PUBLIC_API_BASE_URL='' NEXT_PUBLIC_API_URL='' npm run cf:build
```

查看结果 / Inspect results: the repository **Actions → SoftwareLifeCycle CI**
page shows both jobs, failing steps and downloadable evidence. Existing public
deployment integrations remain separate; this workflow does not make deployment
wait for CI, create branch protections or certify a live deployment.

Remaining operations work includes backup/restore drills, retention policy,
monitoring/alerts, environment separation and approved company network/data use.
