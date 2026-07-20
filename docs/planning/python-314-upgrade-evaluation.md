<!--
SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
SPDX-License-Identifier: MIT
-->

# Python 3.14 Runtime Upgrade: Impact Evaluation (issue #295)

**Date:** 2026-07-18
**Scope:** issue #295 scope items 2-7. Scope item 1 (hardened
`dhi-python:3.14-debian13` image availability) is being evaluated separately by
the container images team and is a hard prerequisite for the production flip;
nothing in this document changes that.
**Verdict:** the codebase and its full dependency tree are compatible with
Python 3.14 today, verified empirically, not just by lock-file resolution.
The blocking work is operational (hardened image, CI gating, Renovate
lockstep), not code-level.

**Status update (2026-07-18, same day):** `dhi-python:3.14-debian13` was
published and the migration is implemented on this branch (rollout steps 1-5
below). Verified against the published image: `PYTHON_VERSION=3.14.6`
(matching the interpreter this evaluation tested), amd64/linux, digest
`sha256:5716c72a...`. One layout change surfaced by inspecting the image
layers: the interpreter moved from `/opt/python/bin/python3.12` (3.12 image)
to `/usr/bin/python3.14` (no `/opt/python` at all), so the Dockerfile's
builder mirror block and the `fips-image-floor` probe now target
`/usr/bin/python3.14`. The venv lockstep mechanism (symlink mirror plus
`UV_PYTHON`) was re-verified against the new path with the pinned uv 0.8.17:
`pyvenv.cfg` records `home = /usr/bin` and the venv's `python` symlink
points at the mirrored path unresolved. Remaining: merge-time CI (runs the
integration suite under 3.14 for the first time) and the staged deploy
(step 6).

---

## Method

All checks below were run against this repository at `main` (v0.15.0,
`4458457`) using CPython **3.14.6** (the current 3.14 patch release), with the
project's own frozen `uv.lock` (`uv sync --all-extras --frozen`). The analysis
environment is Linux x86_64 with no Docker daemon, so the
testcontainers-backed integration suite and the compose-based e2e/newman tiers
could not be exercised here; everything else ran for real.

## Empirical results (what actually ran under 3.14.6)

| Check | Command (3.14.6 env) | Result |
|---|---|---|
| Dependency install | `uv sync --all-extras --frozen` | All packages installed from binary wheels; zero source builds, zero resolution errors |
| Test suite (unit scope, mirrors `python-compatibility.yml`) | `pytest tests/ --ignore=tests/integration --ignore=tests/load -m "not slow and not integration"` | **2674 passed, 0 failed**, 2 deselected, in 59s |
| Coverage gate | same run | **86.94%** branch coverage, above the 80% gate |
| Lint | `ruff check .` | All checks passed |
| Type check (strict) | `basedpyright src` | **0 errors** (381 warnings, the pre-existing advisory `reportUnknown*` class, same as under 3.12) |
| Security scan | `bandit -c pyproject.toml -r src` | No findings |
| Vulnerability audit | `pip-audit` | No known vulnerabilities |
| FIPS compatibility | `python scripts/check_fips_compatibility.py` | PASSED: 0 errors, 0 warnings, 4 acknowledged findings unchanged |

Supporting signal already in CI: `sonarcloud.yml` deliberately runs the
coverage measurement interpreter as **Python 3.14** on every PR (it was chosen
because 3.12's coverage.py silently dropped async handler bodies), so the test
suite has been executing under 3.14 in GitHub Actions on every PR already,
just not as a required gate.

## Dependency wheel audit (scope item 5)

Parsed from `uv.lock` wheel filenames, then confirmed by the actual install
above.

- **Runtime closure** (main dependencies plus the `api` extra, transitively):
  81 packages. Every one is pure-Python, `abi3`, or ships native
  `cp314` manylinux x86_64 wheels. Notably all the compiled hot spots:
  `asyncpg 0.31.0`, `pydantic-core 2.46.4`, `sqlalchemy 2.0.51`,
  `greenlet 3.5.3`, `uvloop 0.22.1`, `pillow 12.3.0`, `cffi 2.0.0`,
  `httptools 0.8.0`, `rpds-py`, `jiter`, `watchfiles` all publish `cp314`
  (and `cp314t`) wheels. `cryptography 49.0.0` ships `cp311-abi3` wheels,
  which cover 3.14 by definition.
- **Dev closure** (the `dev` extra, transitively): 212 packages. The only
  entries without cp314-capable Linux wheels are irrelevant here:
  `pywin32`/`pywinpty` (Windows-only), and `pyyaml-ft` (marker-gated to
  `python_full_version == '3.13.*'` via libcst, so it is simply not installed
  under 3.14). `watchdog` and `nodejs-wheel-binaries` ship universal Linux
  wheels.
- No `requires-python` change is needed; `>=3.11` stands, per the issue's
  non-goals.

## Code-level compatibility

- No `sys.version_info` branches anywhere in `src/`, `tests/`, or `scripts/`.
- No usage of PEP 594 removed modules, `datetime.utcnow`, or
  `asyncio.get_event_loop` in `src/`.
- The one known 3.14-specific interaction (google-genai tripping the
  `_UnionGenericAlias` stdlib DeprecationWarning) is already dispositioned in
  `pyproject.toml` `filterwarnings` with a documented ignore.
- `py313plus`/`py314plus` pytest markers exist; no test currently needs them.
- `noxfile.py` already includes 3.14 in the `test`, `lint`, and `typecheck`
  matrices.

## Version touchpoints that must move together (scope item 3)

The #288 incident happened because these are independently bumpable strings.
A 3.14 migration commit must change all of them atomically:

1. `Dockerfile:11` builder `FROM python:3.12-slim-bookworm`
2. `Dockerfile:44-45` the `/opt/python/bin/python3.12` symlink mirror and
   `UV_PYTHON` (the `#CRITICAL` venv-lockstep block)
3. `Dockerfile:74` runtime `FROM ghcr.io/byronwilliamscpa/dhi-python:3.12-debian13`
   (pending the container team's 3.14 image)
4. `.github/workflows/fips-compatibility.yml:309` hardcoded
   `--entrypoint /opt/python/bin/python3.12` runtime-image probe, and the
   `python:3.12-slim-trixie` job container at line 239
5. `.github/workflows/ci.yml:43` (required gate `python-version`), plus the
   3.12 pins in `pr-validation.yml`, `e2e-real-nightly.yml`,
   `slsa-provenance.yml`, `sbom.yml`, `mutation-testing.yml`,
   `security-analysis.yml`, `docs.yml`, `release.yml`,
   `dependency-provenance-weekly.yml`, `validate-cruft.yml`
6. `docker-compose*.yml` if/where they build from the same Dockerfile
   (no independent version strings found)
7. Cosmetic: the `Programming Language :: Python :: 3.12` classifier in
   `pyproject.toml`, and the "3.12 is the primary local target" language in
   `CLAUDE.md`

## CI gating gap and recommendation (scope item 2)

Today no required, merge-blocking job tests 3.14: `ci.yml` (required) is 3.12
only, `python-compatibility.yml` stops at 3.13, and the SonarCloud 3.14 run is
advisory on PRs. Recommended sequence:

1. **Now (pre-flip):** add `'3.14'` to the `python-version` matrix in
   `python-compatibility.yml`. One-line change, immediately closes the
   "nothing enforces 3.14 before merge" gap for the unit scope.
2. **At flip time:** change `ci.yml` `python-version` to `"3.14"`. That single
   input moves the full required gate (unit, integration, security buckets,
   coverage combine, bandit) to 3.14, and keeps 3.12 covered via the
   compatibility matrix. This also runs the integration suite under 3.14,
   closing the one gap this evaluation could not test locally.
3. Keep the SonarCloud interpreter at 3.14 (it is already there).

## Renovate lockstep rule (scope item 6)

`renovate.json` on `main` currently groups `dockerfile`/`docker-compose`
updates into one "Container base images" PR but does **not** prevent a
version (as opposed to digest) bump of one `FROM` line without the other;
that is exactly the class of change that broke #288, and the planned rule from
that PR's follow-up has not landed on `main` yet. Recommended rule: for
`matchDatasources: ["docker"]` with `matchPackageNames` covering `python` and
`ghcr.io/byronwilliamscpa/dhi-python`, set
`matchUpdateTypes: ["major", "minor"]` to `enabled: false` so Renovate only
ever proposes digest/patch updates for the two stage images, and
major/minor interpreter moves are always a deliberate human PR that bumps
both lines together.

## Security tooling revalidation (scope item 4)

Bandit, pip-audit, and the FIPS checker all pass clean under 3.14.6 (table
above). Two items remain image-side rather than code-side, and land with the
container team's work:

- The OpenSSL ML-KEM floor probe
  (`fips-compatibility.yml:309`) asserts `OPENSSL_VERSION_INFO >= (3, 5)`
  against the runtime image's interpreter; the `dhi-python:3.14-debian13`
  image must satisfy the same floor.
- `cryptography 49.0.0` binds OpenSSL via its own abi3 wheel; the
  FIPS-provider activation remains a host/image property, exactly as the
  existing acknowledged finding documents.

## Residual risks (what this evaluation could not verify)

1. **Integration suite under 3.14** (Postgres via testcontainers, Redis/RQ
   reclaim, schema parity): not runnable in this environment (no Docker
   daemon). Mitigated by CI recommendation step 2, or a local
   `uv run nox -s "test-3.14"` before the flip.
2. **Hardened runtime image**: `dhi-python:3.14-debian13` does not exist yet;
   the container images team's call. The interim alternative (vanilla
   `python:3.14-slim`) would regress the ~95% CVE reduction and reintroduce a
   shell, and is not recommended.
3. **Fuzzing toolchain**: Atheris (fuzz-only dependency, not in the lock)
   historically lags new CPython releases; `cifuzzy.yml` runs on
   ClusterFuzzLite's own base images, so this does not block the runtime flip.
4. **Free-threading (`python3.14t`)**: explicitly out of scope per the issue;
   the standard GIL build is the target. (Many deps already ship `cp314t`
   wheels, so the option stays open.)

## Recommended rollout order (scope item 7)

1. Land the Renovate lockstep rule (independent, prevents recurrence now).
2. Add 3.14 to `python-compatibility.yml` (advisory-to-required unit signal).
3. Container team publishes `dhi-python:3.14-debian13`; verify the OpenSSL
   >= 3.5 floor and the `/opt/python/bin/python3.14` interpreter path.
4. Single migration PR: all Dockerfile touchpoints (builder FROM, symlink,
   UV_PYTHON, runtime FROM) plus `fips-compatibility.yml` paths, atomically;
   `docker run --rm <image> rq --version` and `uvicorn --version` smoke checks
   per the Dockerfile's `#VERIFY` block.
5. Flip `ci.yml` to 3.14 in the same PR (or immediately after), making the
   required gate match the runtime.
6. Staged deploy: dev compose stack, then the homelab staging stack, watching
   the worker (the original crash-loop surface) and `/health/live`; rollback
   is a revert of the single migration PR since the image digests are pinned.
7. Post-flip cleanup: classifiers, CLAUDE.md primary-target language, and
   `python-compatibility.yml` keeps 3.11-3.13 for backward-compat coverage.
