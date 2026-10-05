# 持续集成 / Continuous integration

GitHub Actions runs `.github/workflows/ci.yml` for every push to `main`, every
pull request and manual `workflow_dispatch`. Two independent validation jobs
check the backend/database and frontend; the stable `CI acceptance` job fails
unless both finish successfully (including failed/skipped/cancelled dependency
results). Branch protection is not configured
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

## 本轮整合 / Current integration — 2026-10-05

PR#1 is refreshed against main a18cc718. Current API0.18.27, schema0018,
fixed53 compatibility closure and all17 migrated consumers are preserved.
Report-gate regressions exercise process exit codes for failures, errors, skips,
missing PostgreSQL evidence, empty/malformed/missing reports; migration guard tests
prove remote/company/query-option targets never reach database connection.
The workflow needs no deployment/OIDC/company credentials. `CI acceptance` is a
stable candidate check name for a future protected-branch rule. Red CI does not
configure GitHub branch protection or stop existing independent Render/Cloudflare
automatic deploys. Actual main run evidence and seven-plan acceptance are recorded
in HANDOFF/PROJECT_STATUS after merge; no unmerged PR is counted as main completion.

## 2026-10-05 — CI integrated and verified on main

Mode: Codex cloud. Started from a18cc71816b89472f02e2b6a61fec50f5faed9a1.
PR#1 was reconciled with current main without restoring old API0.18.13 documents
or undoing the fixed53 compatibility closure. Updated feature c156d1e01fa41ea8062f05c899bdeb47d95df5da
passed PR run37248117693. Merge 479e0a292e921b1f325985038903d71edafa7a8c passed main push run37248330054.
See https://github.com/Wang106/SoftwareLifeCycle/actions/runs/37248330054.

Python3.12/PostgreSQL16 backend1204 passed, no skips (1191 existing +13 CI gate/
target-guard tests);129 real PostgreSQL cases are retained, including ordinary
module database fixtures. The report gate's named _postgres count is a narrower
classification, not the total real-database count. Single0018 head, full upgrade
and head downgrade SQL, isolated upgrade/downgrade/re-upgrade, report gate and
artifact upload pass. Node22 frontend465 passed and OpenNext production build pass.
The stable CI acceptance job requires both validations to succeed. Local execution
of all16 success/failure/skipped/cancelled dependency combinations allows only
both-success; process regressions reject malformed/missing/empty/failed/error/
skipped/no-PostgreSQL reports and prevent remote/company database connection.

Actions run on main push, PR and manual dispatch, with SHA-pinned actions,
read-only repository token, no persisted checkout credentials and disposable
PostgreSQL data. No deployment/OIDC/company credentials or grants were introduced.
This does not install branch protection or make independent Render/Cloudflare
automatic deployment wait for CI. CI failures make the workflow/check red;
merge/deployment enforcement and recovery remain separate operations work.

CI plan2 now4/4=100% (0→100); plans100/100/20/33/40/20/0 retain fixed denominators.
The ROADMAP CI item completes:36/44=82%, phases100/100-demo/100-demo/100/89/60/17.
Plan7 still0/6 because its fixed environment/restore/monitor/release/network/data
milestones are broader than adding CI. Read consumers17/17 and53=50+3 remain.
API0.18.27/schema0018 and public sample read-only remain; deployment health and
Cloudflare build evidence are recorded separately below.

Next: approved OIDC provider/controlled target configuration, browser session and
audited grant administration, then first authenticated submissions/recovery/results;
all14 commands, broader append-only corrections and operational acceptance follow.
No approved provider or company target is inferred from CI success. Backup/restore,
monitoring, environment separation, gated deploy/rollback and company network/data
acceptance are still incomplete. This is not a production-ready certificate.

## 只读线上访问证据 — 2026-10-06

新增手动工作流 frontend-access.yml（Read-only frontend access），调用
scripts/check_frontend.py。正式站/项目Preview HTTPS白名单；只发GET，无凭据、
无业务写入、不跟随重定向。准确检查中英文账户SSR、禁用态认证JSON、缓存
与状态，并保存14天JSON证据；失败返回非零。脚本用明确项目User-Agent，
不冒充真实浏览器，区分1010/1020边缘拦截与应用失败。自动CI仍仅运行其离线
回归测试，不依赖公共站点网络，不把构建成功等同于线上访问成功。
手动任务尚未触发；实际HTTP检查在本执行环境运行，详情见 cloudflare-1010.md。
