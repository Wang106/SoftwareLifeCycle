# Offline npm dependency inventory and artifact-byte verification

Baseline: PR182 main `aa7fabb6638cef2010294e042ace41939acb7ee8` (2026-11-06 UTC+8).
This bounded package implements the dependency-input step of the
[offline rehearsal design](offline-readonly-image-rehearsal-design.md), not an
installer, image builder, npm cache importer or offline runtime acceptance.

## Usage and trust boundary

Run with Python standard library:

```sh
python scripts/offline_npm_inventory.py frontend/package-lock.json
python scripts/offline_npm_inventory.py frontend/package-lock.json --artifacts /operator/approved-tarballs
```

The first command produces deterministic JSON inventory and writes INVENTORY_ONLY
to stderr. The second requires a flat directory containing exactly the expected
`sha512-<128 lowercase hex>.tgz` regular files, checks all bytes against lockfile
SHA512, and writes ARTIFACT_BYTES_VERIFIED. JSON is emitted only after all requested
checks succeed. Neither status means dependencies installed, lifecycle scripts
executed, images built, vulnerabilities cleared, or deployment ready.

No network/download, archive extraction, npm execution, installation, Docker,
credential creation or company-server access occurs. Input files/directories are
read-only. Obtain artifacts separately from trusted reviewed sources with applicable
authorization. Do not put operator secrets or application data in this directory.
Hashes prove consistency with a trusted lockfile, not authenticity by themselves.

Secure filesystem reads require POSIX no-follow directory handles; unsupported
hosts fail closed. Parent symlinks, hardlinks and special files are rejected.
Bounds are 16 MiB lockfile, 20,000 packages, 500,000 JSON nodes/depth 64, 512 MiB per
artifact and 8 GiB total. These limits fail closed rather than truncate evidence.

The validator accepts the bounded npm lockfile v3/registry tarball shape, exact
package versions and canonical SHA512 integrity. It rejects ambiguous JSON/source/
path/integrity/cache inputs rather than silently normalizing them. All platform and
optional packages remain in the inventory; filtering to the current development
machine would omit inputs for the intended Linux build. Identical artifacts are
shared by digest while occurrence metadata is preserved. This flat artifact folder
is not npm's internal cache layout, and this tool does not promise npm can consume
it directly without a separately reviewed acquisition/install process.

At this baseline the lock has 412 nonroot package entries, 399 distinct resolved
URLs, 78 optional entries and 4 entries marked hasInstallScript. Preserve lifecycle
script metadata for later review. Lock tarballs alone do not prove that scripts,
native binaries, build tools or external downloads work with egress disabled.
Python requirements still contain only 7 direct version pins, without a complete
transitive/hash lock; they are not certified by this npm-specific tool.

## Acceptance and remaining work

Targeted regression tests cover inventory generation, valid synthetic artifact
bytes and malformed/untrusted/missing/tampered inputs. Synthetic fixtures are not
real installed packages. The repository lock inventory is validated separately;
no full set of real tarballs is downloaded or verified by this package.
Existing 15 offline configuration tests, browser guard/automation checks and normal
full exact-head CI remain mandatory. Publication and actual result records follow
verification; local tests cannot substitute for merged-main evidence.

The next dependency package should close Python transitive wheel/hash inputs and
plan verified artifact acquisition without exposing credentials. Dedicated pinned
image recipes and runtime/egress acceptance then require an authorized Docker
build/test environment, currently absent. Do not install or alter host security
silently to fill that gap. In parallel planning, prioritize local persistent logs,
rotation/capacity, health/disk diagnostics, database plus software-file backup and
isolated restore evidence. Existing backup utilities must be audited before adding
duplicates; none is company production backup acceptance.

Company VM/runtime installation, identity, real writes/data, retention/RPO/RTO and
operational acceptance remain separate. Business36/44=82%,delta0;
modules100/100demo/100demo/100/89/60/17; plans100/100/20/33/40/40/0;
browser-stage1/4 and finite-plan8/8 remain unchanged.

## Local candidate validation

All 15 new inventory tests and 15 existing offline preflight tests passed, with
126 browser guard and 52 automation contracts. Progress consistency, relative
links, whitespace, historical text and unchanged business groups passed. An
independent reviewer separately passed both 15-case suites, progress and whitespace
checks with no blocking findings. Real lock inventory returned 412 occurrences
and 399 artifacts, status INVENTORY_ONLY. No real artifact collection or container
execution occurred. Exact-head full CI remains pending publication.
