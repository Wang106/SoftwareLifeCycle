# Default-off Web startup acceptance preparation

Date: 2026-11-11. Baseline main `95c662e226fd913ac8fb9453aebd1b76032d64b7`.
This package prepares a missing acceptance contract. It does not establish an
existing application defect or execute a container. It is not connected to any
workflow, dependency smoke or deployment entrypoint.

## Separate execution gate

The new `scripts/offline_web_startup_rehearsal.py` defaults to a redacted refusal;
help and import do not call Docker. Runtime needs separate explicit authorization
for this Web behavior and an independently trusted, reviewed, already prepared
local Web image. The earlier database/API authorization is not this permission.
After that authorization only, the exact command shape is:

```
python scripts/offline_web_startup_rehearsal.py --run --trusted-local-image --image-id sha256:<64hex> --source-commit <40hex>
```

These placeholders are not runnable inputs. The source must equal the clean
checkout HEAD, the immutable image ID must exist locally, and its revision label,
linux/amd64 platform, nonroot identity, inert entrypoint and bounded environment
must match. Labels and user-provided IDs check consistency, not authenticity.
There is no pull, build, push, image load, host port, user-data mount, API/database
startup, OIDC setup, company endpoint or permission/security configuration step.
The known dependency smoke remains unchanged and still does not start Next.

## Fixed runtime contract, not yet executed

The existing API custody class now has fixed class attributes for its runtime
command, environment, label and name prefix. Its API defaults and tests remain
unchanged. The separate Web class reuses CID-file validation, inspected ownership,
container isolation validation, one-shot create/start and ownership-only cleanup.
The existing bounded subprocess runner and clean same-source host checks are
reused. There is no shell, external target or configurable probe path.

The container uses `network=none`, UID/GID 65532, read-only root, no capabilities,
no-new-privileges, bounded memory/CPU/PIDs and a 16 MiB noexec private `/tmp` tmpfs.
No host port or bind mount is allowed. Its inspected immutable command is Node
running `next start --hostname 127.0.0.1 --port 3000`. Every identity/submission
gate in the operator preflight is disabled. `API_BASE_URL` is fixed to the absent
container-internal `http://127.0.0.1:8000`; public API fallbacks are empty. This
exercises failed reads rather than the empty-config shortcut.

The Node probe checks stable running container PID, PID1 Node executable,
Next 16.4.2's actual rewritten title, UID/GID, capability/seccomp settings and the
single IPv4 loopback listener on 3000. No listener on 8000 is accepted. Process
observations before/after the fixed HTTP cases cannot certify all future activity.

- GET `/` with the English language cookie must complete a 200 HTML stream within
  the absolute 20-second HTTP budget and 1 MiB body cap. The document must contain
  its closing HTML and settled unavailable-dashboard/current-release/activity
  fragments outside scripts, styles and comments. Streamed fragments after the
  closing HTML are allowed. A partial loading shell, truncated stream or text
  only in serialized Flight/script data does not pass. Hidden streamed server
  fragments are **not browser-visible hydration or click evidence**.
- POST `/auth/login` must return the current exact 503
  `{"error":"login_not_configured"}` response with private/no-store headers,
  no redirect and no cookie. This does not perform an OIDC exchange or login.
- Node sends only a fixed case receipt, never HTML, headers, process data or
  external error text. Docker output is bounded; stderr is discarded. Work has
  a 180-second shared budget plus 35 seconds reserved for cleanup. A killed host or
  Docker daemon can still leave uncertain state; no unconditional cleanup claim
  is made.

Cleanup re-inspects the exact owned CID, image, token, command and isolation
before one removal attempt. An uncertain result cannot be retried, looked up by
name or treated as removed. Private custody data is retained when removal is
unconfirmed; no prune or unrelated resource deletion is provided. Redacted
failure receipts never report success. Runtime receipts identify a runtime
attempt; mocked test receipts are not retained as executed-runtime evidence.

## Validation and limits

Regression-first: the new test module initially failed because the Web module
did not exist. The final 19 Web tests pass alongside 28 unchanged API startup tests.
Independent review found a short-read risk in the new proc reader: one read
could miss a later wildcard listener. Three offset-aware regressions failed
before repair, including the false-pass reproduction. The reader now loops to
explicit EOF with a 65,536-byte cap plus one overflow sentinel and closes its
descriptor on success and failure. Fragmented normal/prohibited reads and exact
cap/overflow cases pass. This corrects the new probe, not an existing app bug.
Tests inject fake Docker runners and use the exact JavaScript program in a Node VM
with fake proc files, HTTP responses and timers. No real socket, container, API or
database is started. Coverage includes explicit opt-in, exact image/source,
isolation/gates, rewritten process title, wrong listener, exited/changed PID,
complete streaming HTML, script-only false positives, truncation, size/deadline,
disabled login, child failure and cleanup uncertainty.

Local verification passed: 909 offline tests, 52 automation tests, 126 CI-guard
tests, Python compilation, Node syntax, progress consistency and whitespace checks. Full candidate CI, image build/startup, browser
hydration, real API integration, offline transfer and company acceptance remain
unexecuted. Existing workflow and branch-protection gates are unchanged. No
commit, upload, draft PR, review transition or merge has occurred at this
checkpoint. Independent final review passed, including 47 focused tests and nine
additional fragmented-read/boundary scenarios. Authorized draft publication and
full exact-candidate CI remain pending. Actual Web runtime still needs the
separate authorization and trusted same-commit prepared local image above.

Business 36/44=82%, delta 0; modules 100/100demo/100demo/100/89/60/17;
plans 100/100/20/33/40/40/0; browser stage 1/4 and finite plan 8/8 unchanged.
