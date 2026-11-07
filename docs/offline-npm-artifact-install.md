# Real npm artifacts and isolated-cache installation

Baseline: main `33580defdb3e04d7240c1862ba26a7eb594be49d`, 2026-11-07
(UTC+8). This extends the [read-only transport inventory](offline-npm-dependency-inventory.md)
with real tarball bytes, archive metadata, and a separate local installation/build
rehearsal. It does not change dependencies, production configuration, CI or gates.

## Artifact evidence

[`frontend/offline-npm-artifacts.json`](../frontend/offline-npm-artifacts.json)
records all **412 lock occurrences, 399 distinct tarballs and 78 optional
occurrences**, without selecting only the current machine's platform. The
unchanged frontend lock SHA256 is
`2b1928116ece5d2902c304e213ee53d3e0a60847c90b63794013b598e3877e3d`.
All 399 exact HTTPS `registry.npmjs.org` URLs were downloaded and checked against
their lock SHA512: **785,874,731 compressed bytes**, **2,427,608,064 expanded
bytes**. No alternate registry or weaker digest was used. Binary artifacts,
runtime, cache, source copy, build output and logs remain outside the repository.

Each entry retains the existing URL, version, SHA512, filename and complete
occurrence metadata, plus measured size and metadata read from its real archive.
The manifest is deterministic and contains no machine-local paths or credentials.
Hash matching proves consistency with this trusted lock, not package safety,
upstream provenance signatures or vulnerability clearance.

The read-only audit can recreate the manifest:

```sh
python scripts/offline_npm_inventory.py frontend/package-lock.json --artifacts "$ARTIFACTS"
python scripts/offline_npm_artifacts.py frontend/package-lock.json "$ARTIFACTS" > "$RUN/recreated.json"
cmp frontend/offline-npm-artifacts.json "$RUN/recreated.json"
```

The first status is `ARTIFACT_BYTES_VERIFIED`; the second is
`ARTIFACT_BYTES_VERIFIED_METADATA_RECORDED`. Neither means installation, lifecycle
execution or network-isolated acceptance. The audit never downloads, extracts to
disk, installs or runs package code. It reuses secure no-follow, single-link reads
and the original 512 MiB/file and 8 GiB/collection bounds. Its additional limits
are 1 MiB/package.json, 50,000 JSON nodes/depth 64, 100,000 archive members,
64 KiB/PAX or GNU extension, 2 GiB expanded/archive and 32 GiB expanded/collection.
Sparse archives, links, special files, path aliases, duplicate paths, multiple
roots, malformed/truncated/missing terminal headers and nonzero data after tar
termination are rejected. Parsing is tested with
CPython 3.12.14 on POSIX; patched tarfile extension handling is part of that tested
toolchain, not a promise for every Python release. Implementations without the
required tarfile parsing hook are rejected before reading inputs.

Historical DefinitelyTyped archives use roots such as `react/` or
`node v22.20/`. The audit accepts exactly one safe root, records it and verifies
that root's package.json name/version. It does not require the root to be named
`package`. Platform constraints present in the lock must match the archive.
Archive libc metadata is retained even where the lock omits it.

## Lifecycle and native-package review

The four original `hasInstallScript` lock flags remain unchanged. The real
esbuild 0.28.2 and workerd 1.20261019.1 archives each declare
`postinstall: node install.js`. The two Darwin-only fsevents archives, 2.3.2 and
2.3.3, have the flag in the lock but contain neither an install lifecycle script
nor binding.gyp. They include a prebuilt fsevents.node. The manifest records both
discrepancies explicitly rather than inventing scripts or changing the lock.
Linux npm naturally excludes these incompatible optional packages, but their
tarballs stay in the complete collection.

`lifecycle_scripts` records preinstall/install/postinstall and prepare separately
from `binding_gyp`, `gypfile` and the default node-gyp candidate. These are static
observations, not evidence of actual execution on every platform.

Before installation, the following exact native inputs were present and their
bytes and Linux/x64 metadata checked:

- `@next/swc-linux-x64-gnu` 16.4.2, archive libc `glibc`.
- `@ast-grep/napi-linux-x64-gnu` 0.45.3, archive libc `glibc`.
- `@img/sharp-linux-x64` 0.35.5 and `@img/sharp-libvips-linux-x64` 1.3.4,
  archive libc `glibc`.
- `@esbuild/linux-x64` 0.28.2.
- `@cloudflare/workerd-linux-64` 1.20261019.1.

**npm's offline flag is not physical egress isolation.** If their native optional
package is absent, esbuild/workerd installers can invoke nested npm and then
direct HTTPS downloads. Next can directly fetch missing SWC binaries/WASM.
These fallbacks do not all honor npm's offline setting. This rehearsal prechecked
native inputs and cleared inherited binary overrides and credentials; it did not
change host networking or prove that every subprocess was unable to reach the
network. No download messages in a log alone could prove that either.

## Reproduce acquisition and installation

Use a fresh private directory outside the checkout with sufficient disk space
for artifacts, npm cache, node_modules and build outputs. Do not reuse an old
node_modules, npm cache, HOME or build directory. Stop on errors, redirects,
hash/size mismatch or access restrictions; do not automatically switch sources,
retry a denied request or reduce verification. Obtain approval where the target
environment requires it.

1. Generate the inventory from the unchanged lock. Fetch every exact URL using a
   normal authorized HTTPS client, with redirects disabled, no credentials or
   cookies, a timeout, streamed SHA512 verification, exclusive creation of the
   digest-named output, 512 MiB/file and 8 GiB total limits. Keep acquisition logs
   outside the flat artifact directory, because that directory must contain only
   the 399 expected tarballs. The following standard-library example shows the
   bounded acquisition logic; it writes only a newly created directory and never
   retries:

   ```python
   import hashlib, json, pathlib, sys, time, urllib.request
   # inventory.json comes from offline_npm_inventory.py, not an untrusted URL.
   manifest = json.loads(pathlib.Path(sys.argv[1]).read_text())
   target = pathlib.Path(sys.argv[2])
   target.mkdir(mode=0o700)  # Must not already exist.
   class NoRedirect(urllib.request.HTTPRedirectHandler):
       def redirect_request(self, *args, **kwargs):
           raise RuntimeError("redirect refused")
   opener = urllib.request.build_opener(NoRedirect())
   total = 0
   for item in manifest["artifacts"]:
       digest, size, started = hashlib.sha512(), 0, time.monotonic()
       request = urllib.request.Request(item["url"], headers={"Accept-Encoding": "identity"})
       with opener.open(request, timeout=60) as response, (target / item["filename"]).open("xb") as output:
           assert response.status == 200 and response.url == item["url"]
           while chunk := response.read(min(1024 * 1024, 512 * 1024**2 + 1 - size)):
               size += len(chunk)
               total += len(chunk)
               assert size <= 512 * 1024**2 and total <= 8 * 1024**3
               assert time.monotonic() - started < 300
               digest.update(chunk)
               output.write(chunk)
       assert size > 0 and digest.hexdigest() == item["sha512"]
   ```

2. Run both independent read-only checks above. Review any script discrepancy
   and native inputs before executing any package code.

3. Obtain the official **Node v22.23.4 Linux x64** archive and its
   [official SHASUMS256.txt](https://nodejs.org/dist/v22.23.4/SHASUMS256.txt),
   over HTTPS without redirects. The
   [runtime tar.xz](https://nodejs.org/dist/v22.23.4/node-v22.23.4-linux-x64.tar.xz)
   measured 31,029,996 bytes and matched SHA256
   `1805bcd35e6815559bd2eb97db438d3fdb0eb3a5e6a977b7c1badca76337e9ce`.
   The checksum document measured 3,981 bytes with SHA256
   `c90c3f1478fda8308b22cc1a1b0dc536169196444e67ee8b5c582fd351d02bce`.
   Verify the exact archive line before extracting into the private run directory
   with safe archive handling. Bundled npm is **10.9.9**. This was HTTPS plus
   official checksum verification, not a GPG-signature verification.

4. Copy tracked source files into a fresh private source directory. Exclude
   node_modules, .next, .open-next, .git, every .env* file, npmrc/.npmrc,
   auth.json and other credentials; refuse source symlinks/special files.
   Record source and lock hashes before the run. This run copied 922 tracked
   regular files and excluded the tracked .env.example; it did not use any
   checkout-local dependency symlink or real dotenv file.

5. Create new private HOME, cache and TMPDIR, and separate empty user/global npm
   configuration files. Launch commands with an allowlisted environment rather
   than inheriting environment variables. PATH must put the verified Node22 bin
   first. In particular do not inherit NODE_OPTIONS, NODE_PATH,
   ESBUILD_BINARY_PATH, NEXT_SWC_PATH, WORKERD_BINARY_PATH or Next test/native
   binding overrides. Set these values in that clean environment:

   ```text
   CI=true
   npm_config_cache=<new private cache>
   npm_config_userconfig=<new empty user.npmrc>
   npm_config_globalconfig=<new empty global.npmrc>
   npm_config_registry=https://registry.npmjs.org/
   npm_config_offline=true
   npm_config_fetch_retries=0
   npm_config_update_notifier=false
   npm_config_audit=false
   npm_config_fund=false
   NEXT_TELEMETRY_DISABLED=1
   WRANGLER_SEND_METRICS=false
   OPEN_NEXT_TELEMETRY_DISABLED=1
   API_BASE_URL=
   NEXT_PUBLIC_API_BASE_URL=
   NEXT_PUBLIC_API_URL=
   ```

6. In the source copy's frontend directory, pass all 399 verified local tgz paths
   to cache add, then install using the actual lifecycle scripts:

   ```sh
   npm cache add <all 399 local tgz paths> --offline --ignore-scripts --no-audit --no-fund
   npm cache verify --offline
   npm ci --offline --include=dev --include=optional --foreground-scripts --no-audit --no-fund
   ```

   `--ignore-scripts` applies only to cache import, never the final ci command.
   The flat artifact directory itself is not npm's internal cache.

7. Load the native SWC GNU binding and transform TypeScript; parse JavaScript
   with ast-grep GNU; create/decode a 2x2 PNG with sharp/libvips; transform
   TypeScript with esbuild; run workerd's version and a synthetic local HTTP
   response. The latter can use installed Miniflare's current workers/config/
   manifest API, with host 127.0.0.1, port 0, cf false and telemetry disabled.
   Dispose the runtime after asserting status 200 and the exact synthetic body.
   Do not substitute binary existence for an actual load/function check.

8. Run the existing frontend CI sequence without modified dependency versions,
   skipped Next build or unsupported-version bypasses:

   ```sh
   npm run cf:check
   npm test
   npm run cf:build
   npm run auth:check
   ```

   Do not run deploy, preview, populate-cache, migration or external API checks.
   Preserve command exit codes and logs privately. Compare tracked source/lock
   hashes afterwards and hash the generated Worker output.

## Local results and remaining acceptance

Acquisition, byte/metadata recreation, independent-cache import and cache verify
passed. `npm ci` installed 347 compatible packages and visibly executed the
esbuild and workerd postinstall scripts. It emitted existing deprecation warnings
for node-domexception and glob; this was not a vulnerability audit and no
dependency was upgraded to suppress them.

All six native inputs loaded/functioned. The first temporary Miniflare smoke
used outdated constructor options and failed validation before starting a Worker.
After adapting only the disposable smoke to the installed API, the real workerd
returned the expected synthetic 200 response. The failed attempt and successful
result are both retained; no project/dependency change was needed.

The production/Preview configuration check and **2,116 frontend tests** passed
with zero failures/skips. The complete `cf:build` (Next and OpenNext) and
`auth:check` both exited 0. The authentication check exercised the existing
disabled handlers and bilingual account/command SSR on loopback; it did not
contact a real API or enable identity/business writes. No skip-build or unsupported
version flags were used.

All 922 copied source files retained their pre-run SHA256, including package.json
and package-lock.json. `.open-next` contained 1,979 regular files totalling
30,248,650 bytes. Its 2,278-byte worker.js SHA256 was
`d05223bf4d44c84108a102ab62aa3bc9c5568f0c3ac2064c37be5cc65c64bc45`;
the full output inventory and command logs remain outside the repository.
These are observed outputs from this run, not a cross-machine reproducible-build
guarantee. The 30 new archive/manifest regressions and the original 15 inventory
tests passed. Initial missing-tool tests, malformed-archive cases and the three
real-format/extension fixes were observed failing before their implementation.
A final independent review reproduced stdlib-tolerated damaged terminal headers;
the new malformed/truncated/missing-header and unsupported-hook regressions failed
before the fixed-rejection change and passed afterwards. Actual manifest
recreation remained byte-for-byte identical; installation/build was not repeated
for this parser-only change.

This is Linux amd64, Node22.23.4/npm10.9.9 on Debian13/glibc2.41. It is not a
matched Ubuntu24.04/glibc2.39 execution, the Alpine/musl production image, a
container/image build, true egress-disabled installation, real company server
acceptance, production deployment, PostgreSQL/browser CI, or a restore exercise.
All-platform tarballs are retained but other platforms were not installed here.
Exact-head full CI and deployment evidence remain separate.

Business36/44=82%, delta0; modules100/100demo/100demo/100/89/60/17;
plans100/100/20/33/40/40/0; browser-stage1/4 and finite-plan8/8 remain unchanged.
