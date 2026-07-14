---
title: "Known Vulnerabilities"
schema_type: common
status: published
owner: core-maintainer
purpose: "Tracks CVEs and advisories that cannot be immediately remediated."
tags:
  - security
  - dependencies
  - compliance
---

This document tracks CVEs and security advisories that have been identified but cannot
be immediately remediated. Entries must be reviewed within 60 days of the Discovered
date. Any entry older than 60 days without reassessment blocks releases per the OpenSSF
release gate policy.

To add new entries, see the [known-vulnerabilities template](https://github.com/ByronWilliamsCPA/cyo-adventure/blob/main/.github/known-vulnerabilities-template.md)
in the `.github/` directory.

## Active Entries

## PYSEC-2022-42969 | py | Medium

| Field | Value |
|-------|-------|
| **CVE ID** | PYSEC-2022-42969 |
| **Package** | py |
| **Affected Version** | 1.11.0 |
| **Fixed Version** | No fix available |
| **Severity** | Medium |
| **CVSS Score** | 7.5 |
| **Discovered** | 2026-05-21 |
| **Reassessment Due** | 2026-07-20 |
| **Blocking Release** | No |

### Description

ReDoS (Regular Expression Denial of Service) vulnerability in the `py` package's
`path.LocalPath` function via crafted input to the `svnwc.status` method.

### Impact on This Project

The `py` package is a transitive dependency of `interrogate` (a docstring coverage
tool) used only in the development environment. It is never present in production
runtime dependencies. The vulnerable `svnwc.status` code path is exercised only
when parsing Subversion repository info, which this project does not do.

### Remediation Plan

- [ ] Monitor upstream `py` package for a fix release (package is largely unmaintained)
- [ ] Evaluate replacing `interrogate` with an alternative docstring coverage tool
  if no fix arrives by 2026-07-20 (reassessment due)

### Why Not Fixed Yet

The `py` package has no released fix version. The package is largely unmaintained.
`interrogate` has not released a version that drops the `py` dependency.

### References

- [PYSEC-2022-42969](https://osv.dev/vulnerability/PYSEC-2022-42969)
- [GitHub Advisory GHSA-w596-4wvx-j9j6](https://github.com/advisories/GHSA-w596-4wvx-j9j6)

---

## PYSEC-2026-89 | markdown | High

| Field | Value |
|-------|-------|
| **CVE ID** | PYSEC-2026-89 |
| **Package** | markdown |
| **Affected Version** | 3.10.2 |
| **Fixed Version** | Fixed only in 3.8.1-3.8.2; no fixed release available for >=3.9 as of 2026-05-21 |
| **Severity** | High |
| **CVSS Score** | 7.5 |
| **Discovered** | 2026-05-21 |
| **Reassessment Due** | 2026-07-20 |
| **Blocking Release** | No |

### Description

DoS via malformed HTML-like sequences that cause `html.parser.HTMLParser` to raise
an unhandled `AssertionError` during Markdown parsing. Python-Markdown does not
catch this exception, so any application parsing attacker-controlled Markdown may
crash. Enables remote unauthenticated Denial of Service in web applications,
documentation systems, CI/CD pipelines, and any service rendering untrusted Markdown.
Also known as CVE-2025-69534 and GHSA-5wmx-573v-2qwq.

### Impact on This Project

The `markdown` package is a transitive dependency of `mkdocs`, `mkdocs-material`,
and related documentation tools. It is present only in the development environment
(docs tooling). This project does not parse attacker-controlled Markdown input at
runtime. The vulnerability is not exploitable in production. Dev-only impact.

### Remediation Plan

- [ ] Monitor the `markdown` package for a release that fixes PYSEC-2026-89 in
  the 3.9+ series
- [ ] Evaluate pinning `markdown` to `3.8.2` if compatible with `mkdocs` and
  `mkdocs-material` dependencies
- [ ] Reassess by 2026-07-20 whether a fixed version is available or whether
  mkdocs has migrated to a safe markdown version

### Why Not Fixed Yet

The fix landed in `markdown` 3.8.1, but the package subsequently released 3.9 and
3.10.x without incorporating the fix (or re-introduced the vulnerable code path).
As of 2026-05-21, no version in the 3.9+ series resolves this CVE. Downgrading to
3.8.2 may conflict with `mkdocs-material` and other tooling that requires 3.9+.

### References

- [PYSEC-2026-89](https://osv.dev/vulnerability/PYSEC-2026-89)
- [GitHub Advisory GHSA-5wmx-573v-2qwq](https://github.com/advisories/GHSA-5wmx-573v-2qwq)

---

## CVE-2026-53615 | libuuid1 (util-linux) | High

| Field | Value |
|-------|-------|
| **CVE ID** | CVE-2026-53615 |
| **Package** | libuuid1 (Debian binary package from the `util-linux` source package) |
| **Affected Version** | 2.41-5 (Debian 13 "trixie") |
| **Fixed Version** | No fix available |
| **Severity** | High (per Trivy/Aqua feed) |
| **CVSS Score** | Not yet assigned (NVD status RESERVED as of 2026-07-08) |
| **Discovered** | 2026-07-08 |
| **Reassessment Due** | 2026-09-06 |
| **Blocking Release** | No |

### Description

Integer overflow or wraparound in util-linux's libblkid DOS partition-table
parser (`libblkid/src/partitions/dos.c`). Trivy reports the finding against the
`libuuid1` binary package because Debian tracks vulnerabilities per source
package (`util-linux`); the vulnerable code lives in libblkid, not in the UUID
library itself.

### Impact on This Project

`libuuid1` ships in the production runtime base image
(`ghcr.io/byronwilliamscpa/dhi-python:3.12-debian13`). The vulnerable code path
is libblkid's parsing of DOS partition tables on block devices. The application
container never probes or parses block-device partition tables: it runs a
FastAPI web service with no raw device access, and libblkid's partition APIs
are not exercised by any runtime dependency. Exposure through the application
surface is negligible.

### Remediation Plan

- [ ] Monitor the [Debian security tracker](https://security-tracker.debian.org/tracker/CVE-2026-53615)
  for a fixed `util-linux` package in trixie
- [ ] Once a fix ships, let the patched package flow in via the runtime stage's
  `apt-get upgrade` on the next image rebuild, then remove the `.trivyignore`
  entry
- [ ] Reassess by 2026-09-06 whether a fixed Debian package or NVD analysis
  (CVSS, exploitability detail) is available

### Why Not Fixed Yet

Debian has not released a patched `util-linux` for trixie (Trivy reports an
empty Fixed Version with status `affected`). The package is provided by the
hardened base image, not managed by this project's dependency set, so no
project-side upgrade path exists until Debian ships a fix.

### References

- [Aqua AVD CVE-2026-53615](https://avd.aquasec.com/nvd/cve-2026-53615)
- [Debian security tracker CVE-2026-53615](https://security-tracker.debian.org/tracker/CVE-2026-53615)
- Discovered by the Container Security workflow (Trivy) on
  [PR #165](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/165)

---

## CVE-2026-40467, CVE-2026-40468, CVE-2026-40469, CVE-2026-40553 | gawk | Critical/High

| Field | Value |
|-------|-------|
| **CVE ID** | CVE-2026-40468, CVE-2026-40469 (Critical); CVE-2026-40467, CVE-2026-40553 (High) |
| **Package** | gawk (Debian binary package from the `gawk` source package) |
| **Affected Version** | 1:5.2.1-2+b1 (Debian 13 "trixie") |
| **Fixed Version** | No fix available |
| **Severity** | Critical (CVE-2026-40468, CVE-2026-40469); High (CVE-2026-40467, CVE-2026-40553) |
| **CVSS Score** | Not yet assigned (NVD status RESERVED as of 2026-07-14) |
| **Discovered** | 2026-07-14 |
| **Reassessment Due** | 2026-09-12 |
| **Blocking Release** | No |

### Description

Four memory-safety defects in GNU Awk reported against the `gawk` binary
package: integer overflows in `builtin.c` (CVE-2026-40468, CVE-2026-40469), a
use-after-free in `io.c` (CVE-2026-40467), and a buffer overflow
(CVE-2026-40553). Exploitation requires processing an attacker-controlled awk
program or crafted input through gawk.

### Impact on This Project

`gawk` ships in the production runtime base image
(`ghcr.io/byronwilliamscpa/dhi-python:3.12-debian13`); the application does not
install it and does not invoke it. The container runs a FastAPI web service
that never shells out to `gawk` nor feeds it untrusted input, so none of the
vulnerable code paths are reachable through the application surface. Exposure
is negligible.

### Remediation Plan

- [ ] Monitor the [Debian security tracker](https://security-tracker.debian.org/tracker/source-package/gawk)
  for a fixed `gawk` package in trixie
- [ ] Once a fix ships, let the patched package flow in on the next image
  rebuild, then remove the four `.trivyignore` entries
- [ ] Reassess by 2026-09-12 whether a fixed Debian package or NVD analysis
  (CVSS, exploitability detail) is available

### Why Not Fixed Yet

Debian has not released a patched `gawk` for trixie (Trivy reports an empty
Fixed Version with status `affected` for all four CVEs). The package is
provided by the hardened base image, not managed by this project's dependency
set, so no project-side upgrade path exists until Debian ships a fix.

### References

- [Debian security tracker: gawk](https://security-tracker.debian.org/tracker/source-package/gawk)
- Discovered by the Container Security workflow (Trivy) on
  [PR #256](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/256)

## Resolved Entries

| CVE | Package | Resolved Date | Resolution |
|-----|---------|---------------|------------|

## Review History

| Review Date | Reviewer       | Notes                                                                 |
|-------------|----------------|-----------------------------------------------------------------------|
| 2026-MM-DD  | Byron Williams | Initial creation.                                                     |
| 2026-07-08  | Byron Williams | Added CVE-2026-53615 (libuuid1, runtime base image; no upstream fix). |
| 2026-07-14  | Byron Williams | Added gawk CVE-2026-40467/40468/40469/40553 (runtime base image; no upstream fix). |
