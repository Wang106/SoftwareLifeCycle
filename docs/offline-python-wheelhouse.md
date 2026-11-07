# Python runtime wheelhouse: fixed Linux/CPython target

Baseline main: `213e969f6e97b4c7f4ec5acbca48074c26b76449` (2026-11-07).
This bounded implementation supplies the Python dependency input missing from the
[offline image design](offline-readonly-image-rehearsal-design.md). It does not
change the seven original [runtime pins](../backend/requirements.txt), application,
Dockerfiles, CI, database, identity, service configuration or acceptance percentages.

## Delivered and actually exercised

- [Hash lock](../backend/requirements-linux-cp312.lock): 30 exact distributions,
  one selected SHA256 per wheel, including the original `uvicorn[standard]`,
  `psycopg[binary]` and `PyJWT[crypto]` extras. This is not `pip freeze` output.
- [Inventory](../backend/offline-python-wheelhouse.json): original requirements
  SHA256, resolver report SHA256 and pip version, target, direct pins/extras, and
  each wheel's exact official URL, filename, version, size, SHA256 and wheel tags.
- [Validator](../scripts/offline_python_wheelhouse.py) and
  [regressions](../backend/tests/test_offline_python_wheelhouse.py): inspect bytes
  and ask pip itself to resolve the complete offline extras closure. They do not
  implement a dependency resolver or run package/application code.

Official PyPI resolution used pip 26.2.2 on CPython 3.12.14/Linux x86_64 with
explicit CPython 3.12/`cp312` and manylinux glibc floors 2.5 through 2.39, including
legacy manylinux1/2010/2014 aliases. All 30 real wheels were downloaded from exact
`https://files.pythonhosted.org/packages/...` URLs with SHA256 verification,
`--only-binary=:all:` and no source fallback: **23,939,029 bytes** total.

A fresh venv with `include-system-site-packages = false` and disabled user site
successfully installed the complete hash lock with pip 25.0.1, `--no-index`,
`--find-links`, `--require-hashes`, `--only-binary=:all:` and no dependency bypass.
`pip check` returned `No broken requirements found.` All seven direct package
imports and twelve native-extension imports succeeded from that new venv:
psycopg-binary, cryptography Rust bindings, pydantic-core, cffi, greenlet, httptools,
uvloop, watchfiles, websockets, PyYAML, MarkupSafe and SQLAlchemy. psycopg reported
its actual `binary` implementation. No application server or database was started.

The host was **glibc 2.41**, not Ubuntu 24.04/glibc 2.39. Restricted wheel tags
are compatibility inputs, not runtime proof on the intended target. `--no-index`
is not physical network disconnection; no firewall/network settings were changed.
The first resolver attempt mistakenly omitted the environment's existing network
variables and returned no candidates. The official index diagnostic returned
HTTP 200; preserving the existing network/certificate variables resolved that
local invocation problem. No private mirror, security bypass or network change
was used. The failed invocation and successful retry are retained separately.

## Trust, validation and limits

The trusted repository inventory/hash lock binds expected bytes. Hashes do not
prove package safety, publisher identity, license clearance, vulnerability status
or authenticity against a malicious replacement of both lock and inventory.
Only PyPI registry report sources with the exact HTTPS host/path shape are
accepted. Unreviewed reports/manifests are not a way to authorize downloads.

The validator rejects missing/extra artifacts, duplicate distributions/JSON keys,
source distributions, URL credentials/query strings, unexpected sources, changed
requirements/extras, mismatched version/tag/size/hash, newer glibc floors,
Windows/macOS/musl/other-architecture wheels and unqualified `linux_x86_64` wheels.
It uses pip's vendored `packaging` parsers/tags, not handwritten PEP rules.
ZIP metadata is read without extraction; its Name/Version/Tag must agree with
the inventory. Any direct URL in `Requires-Dist` is rejected before calling pip,
because `--no-index` alone would not prevent that kind of download.

Verification uses POSIX no-follow handles for every path component, rejects
symlinks/hardlinks/FIFOs/special files, checks for file changes during reads and
passes pip a private copy of the verified bytes. Limits: 256 distributions,
4 MiB JSON/metadata inputs, 128 MiB per wheel, 512 MiB total, 10,000 ZIP entries
per wheel and a 120-second pip closure timeout. A normal verify temporarily needs
one extra copy of the wheel bytes. Input folders are read-only; keep only wheels
in the wheelhouse and keep logs, reports and operator data elsewhere.

`inventory` checks an already downloaded set against a pip report and emits JSON;
it does not certify a dependency closure. `lock` emits the exact canonical lock.
`verify` checks the inventory, original input, canonical lock, metadata and bytes,
then invokes pip's real resolver with `--dry-run --ignore-installed --no-index
--require-hashes --only-binary=:all:` using only the snapshot. It rejects missing
transitive or extras dependencies, even when both are omitted from the inventory
and lock. It never uses installed packages or caches to satisfy the closure.
A result of `OFFLINE_PIP_CLOSURE_VERIFIED` means precisely that stage, not install
or runtime acceptance. Nonmatching host interpreters/platforms fail that stage.
Unexpected pip config and environment options are disabled. No offline bootstrap
installation of pip or its vendored parser is performed by the tool.

## Reproduce against an approved local artifact directory

Use an existing authorized Linux x86_64 CPython 3.12 installation with pip. Keep
wheel binaries, venvs, reports and logs **outside the git checkout**, in a fresh
controlled directory. Obtain the reviewed source bytes separately from official
PyPI with applicable download authorization. Never place secrets there.

An existing lock can be reacquired with pip, retaining the normal environment's
network/certificate variables while ignoring pip configuration/options:

```python
import os
from pathlib import Path
import subprocess
import sys

repo = Path.cwd()
wheel_dir = Path("/operator/approved/new-wheelhouse")  # must be fresh
wheel_dir.mkdir()
platforms = [f"manylinux_2_{n}_x86_64" for n in range(39, 4, -1)] + [
    "manylinux2014_x86_64", "manylinux2010_x86_64", "manylinux1_x86_64"]
cmd = [sys.executable, "-I", "-m", "pip", "--isolated", "download",
       "--index-url", "https://pypi.org/simple", "--no-cache-dir",
       "--disable-pip-version-check", "--no-input", "--retries", "0",
       "--only-binary=:all:", "--require-hashes", "--no-deps",
       "--python-version", "3.12", "--implementation", "cp", "--abi", "cp312",
       "--dest", str(wheel_dir), "-r", str(repo / "backend/requirements-linux-cp312.lock")]
for tag in platforms:
    cmd.extend(["--platform", tag])
subprocess.run(cmd, env={**os.environ, "PIP_CONFIG_FILE": os.devnull}, check=True)
```

`--no-deps` is used only to acquire the already complete, individually hashed
transport set. It is forbidden for the following closure check and installation.
If PyPI offers a different wheel or a required source is unavailable, stop on the
hash/source error. Do not replace hashes, relax platform filters or build source.
A new dependency resolution must produce a separately reviewed report/lock.

```sh
python scripts/offline_python_wheelhouse.py verify \
  --requirements backend/requirements.txt \
  --manifest backend/offline-python-wheelhouse.json \
  --lock backend/requirements-linux-cp312.lock \
  --wheelhouse /operator/approved/new-wheelhouse
```

To generate a *new reviewed candidate*, resolve the unchanged seven inputs using
pip `install --dry-run --ignore-installed --report ...`, the official index,
`--only-binary=:all:` and all of the target options above. Use a matching Linux
CPython 3.12 host because pip's foreign-target options alone do not replace all
host environment marker evaluation. Download the report's exact wheel URLs and
hashes, preserving the original extras. Then create inventory and lock using:

```sh
python scripts/offline_python_wheelhouse.py inventory \
  --requirements backend/requirements.txt --report /operator/approved/resolver-report.json \
  --wheelhouse /operator/approved/new-wheelhouse > /operator/approved/new-inventory.json
python scripts/offline_python_wheelhouse.py lock \
  --requirements backend/requirements.txt --manifest /operator/approved/new-inventory.json \
  > /operator/approved/new-requirements.lock
```

Validate a new candidate with `verify` before installing it. Existing locks are
not silently regenerated. The tool emits no JSON/lock on validation failure and
uses a fixed error diagnostic without raw input/path/exception text.

For an authorized real install, create a fresh private venv (no
`--system-site-packages`), verify the wheel bytes again, and use:

```sh
python3.12 -I -m venv /operator/approved/new-venv
PIP_CONFIG_FILE=/dev/null /operator/approved/new-venv/bin/python -I -m pip --isolated install \
  --no-index --find-links /operator/approved/new-wheelhouse \
  --require-hashes --only-binary=:all: --no-cache-dir --disable-pip-version-check \
  -r backend/requirements-linux-cp312.lock
/operator/approved/new-venv/bin/python -I -m pip check
```

Use operator-controlled immutable inputs during installation; the validator's
private snapshot protects its own pip dry run, not a subsequent independent
install from a concurrently changing directory. Keep installation reports and
native import evidence. Do not invoke the application's startup/migration hooks.

## Local evidence and remaining acceptance

The local artifact directory contains `resolver-report.json`, exact resolve and
download commands/logs, `acquisition.txt`, all wheels, fresh `acceptance-venv`,
`install-report.json`, `pip-check.log`, `native-imports.log`, the initial failed
regression log, passing regression log and `evidence.json` containing artifact
sizes/hashes. These are workspace artifacts, not committed or uploaded. The
resolver report SHA256 is
`d1683b5abfcb3e0f75bfafc461acd45e6655325bdbc6836024cdbf51afa0b326`.
The 34 focused regressions pass locally, including real pip resolution of a
synthetic closure and real failure on omitted transitive/extra wheels. The first
regression run failed because the new validator did not yet exist. Synthetic
fixtures do not substitute for the real download/install evidence described above.
Independent review found one malformed-report URL diagnostic gap. Three CLI-layer
regressions reproduced invalid types reaching the URL parser before validation; a
pre-parse string/length check now returns only the fixed failure message, including
for numeric, boolean, null, list/object, floating-point, oversized and malformed URL
inputs. All 34 focused tests and the real 30-wheel closure recheck pass after this
change. The source policy, lock, inventory and dependency bytes are unchanged.
Full candidate CI, PostgreSQL and strict browser checks remain separate evidence.

Not included: Python interpreter/ensurepip/pip bootstrap artifacts, OS packages,
Docker/Compose, Node/npm dependencies, application/container images, PostgreSQL,
physical egress isolation, internal installation/transfer, company configuration,
identity, business data, application health or complete software/database restore.
There is no claimed security/license clearance. The next concrete runtime step
needs an authorized matching Ubuntu 24.04 environment and separately reviewed
runtime/bootstrap/image inputs, followed by actual disconnected acceptance.
Business 36/44=82%, delta 0; modules 100/100 demo/100 demo/100/89/60/17;
plans 100/100/20/33/40/40/0; browser-stage 1/4 and finite-plan 8/8 are unchanged.
