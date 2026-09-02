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
be immediately remediated.

## Release Gate Policy

Two independent gates govern a release. Either one, on its own, is enough to hold it.

1. **Severity gate, recorded per entry in `Blocking Release`.** This field records one
   thing and one thing only: whether the vulnerability's own severity and reachability
   are judged severe enough to hold a release. `No` means "assessed as not
   release-blocking on the evidence gathered on the Discovered date, or on the date of
   the most recent reassessment." It is a dated verdict with an expiry, not a standing
   exemption.
2. **Process gate, derived per entry from `Reassessment Due`.** Every entry must be
   reassessed within 90 days. Once an entry passes its `Reassessment Due` date it blocks
   releases per the OpenSSF release gate policy, whatever its `Blocking Release` value
   says, because that value has expired and no longer rests on verified evidence.

**Ruling (2026-07-29).** Where the two gates appear to conflict, the process gate
governs. An overdue entry closes the release gate even when it reads
`Blocking Release | No`. The opposite reading, that `Blocking Release | No` exempts an
entry from the deadline, is rejected: it would let any entry opt out of reassessment
permanently and would drain the 90-day rule of any force. This resolves the
contradiction between the former preamble and the two entries that sat overdue and
non-blocking from 2026-07-20 to 2026-07-29.

**Where the dates live (2026-08-17).** Two files carry a date for each acceptance and they
must agree. `.trivyignore.yaml` carries `expired_at`, which is the *operative* date: Trivy stops
honouring a suppression once it passes, so the finding returns to the gate on its own rather than
waiting for anyone to notice. The `Reassessment Due` field in each entry below carries the same
date alongside the assessment that justifies it. `scripts/check_known_vulnerabilities.py` fails the
build if the two ever disagree, because a document describing a suppression that is not the one in
force is worse than no document. The 90-day maximum is shared with the org-wide
`ignore-expiry-horizon-days` default in the reusable container-security workflow, and this
repository pins it explicitly rather than inheriting it.

**Reopening the gate.** Reassess the entry: re-verify fix status, reachability, and
severity against current sources; record what was checked, on what date, and what
evidence would change the verdict; then set a new `Reassessment Due` date within 90 days
of that check. Bumping the date without new evidence is not a reassessment and does not
reopen the gate.

To add new entries, see the [known-vulnerabilities template](https://github.com/ByronWilliamsCPA/cyo-adventure/blob/main/.github/known-vulnerabilities-template.md)
in the `.github/` directory.

## Active Entries

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
(`ghcr.io/byronwilliamscpa/dhi-python:3.14-debian13`). The vulnerable code path
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

- [NVD CVE-2026-53615](https://nvd.nist.gov/vuln/detail/CVE-2026-53615)
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
(`ghcr.io/byronwilliamscpa/dhi-python:3.14-debian13`); the application does not
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

- [Aqua AVD CVE-2026-40468](https://avd.aquasec.com/nvd/cve-2026-40468)
- [Aqua AVD CVE-2026-40469](https://avd.aquasec.com/nvd/cve-2026-40469)
- [Aqua AVD CVE-2026-40467](https://avd.aquasec.com/nvd/cve-2026-40467)
- [Aqua AVD CVE-2026-40553](https://avd.aquasec.com/nvd/cve-2026-40553)
- [Debian security tracker: gawk](https://security-tracker.debian.org/tracker/source-package/gawk)
- Discovered by the Container Security workflow (Trivy) on
  [PR #256](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/256)

---

## CVE-2025-59375, CVE-2026-25210, CVE-2026-45186, CVE-2026-56131, CVE-2026-56407, CVE-2026-56408 | libexpat1, libexpat1-dev | High

| Field | Value |
|-------|-------|
| **CVE ID** | CVE-2025-59375, CVE-2026-25210, CVE-2026-45186, CVE-2026-56131, CVE-2026-56407, CVE-2026-56408 |
| **Package** | libexpat1, libexpat1-dev (Debian binary packages from the `expat` source package) |
| **Affected Version** | 2.7.1-2+dhi5 (Debian 13 "trixie", DHI mirror build) |
| **Fixed Version** | No fix available |
| **Severity** | High (all six, per Trivy/Aqua feed) |
| **CVSS Score** | Not individually catalogued here; see per-CVE Aqua/NVD links below |
| **Discovered** | 2026-07-19 |
| **Reassessment Due** | 2026-09-17 |
| **Blocking Release** | No |

### Description

Six memory-safety and information-disclosure defects in the Expat XML parsing
library: excessive dynamic-memory allocation on crafted input
(CVE-2025-59375), an integer-overflow information disclosure
(CVE-2026-25210), a denial of service via crafted XML (CVE-2026-45186), a
missing handler call-depth limit (CVE-2026-56131), and two further integer
overflows in `doProlog`/`copyString` (CVE-2026-56407, CVE-2026-56408). All six
require processing attacker-controlled XML input through Expat.

### Impact on This Project

`libexpat1`/`libexpat1-dev` ship in the production runtime base image
(`ghcr.io/byronwilliamscpa/dhi-python:3.14-debian13`). The application does not
call into Expat directly (no `xml.parsers.expat` usage in this codebase) and
does not parse untrusted XML on any request path. Exposure through the
application surface is negligible.

### Remediation Plan

- [ ] Monitor the [Debian security tracker](https://security-tracker.debian.org/tracker/source-package/expat)
  for a fixed `expat` package that flows into the next DHI mirror rebuild
- [ ] Once a fixed digest is published, remove these six `.trivyignore`
  entries and re-run the Container Security scan to confirm
- [ ] Reassess by 2026-09-17 whether a fixed Debian package or NVD analysis is
  available

### Why Not Fixed Yet

Debian has not released a patched `expat` build for the DHI mirror's Debian 13
snapshot (Trivy reports an empty Fixed Version with status `affected` for all
six CVEs against `2.7.1-2+dhi5`). The package is provided by the hardened base
image, not managed by this project's dependency set, so no project-side
upgrade path exists: the DHI runtime image ships no shell and no package
manager, so it cannot run `apt-get` itself (confirmed directly against this
project's Dockerfile runtime stage). The identical CVE set was independently
found on `dhi-python:3.12-debian13`'s Renovate-proposed digest refresh while
reviewing PR #296, confirming this is a mirror-wide regression across the
`debian13` tag family rather than something specific to the Python 3.14
upgrade in PR #299.

### References

- [Aqua AVD CVE-2025-59375](https://avd.aquasec.com/nvd/cve-2025-59375)
- [Aqua AVD CVE-2026-25210](https://avd.aquasec.com/nvd/cve-2026-25210)
- [Aqua AVD CVE-2026-45186](https://avd.aquasec.com/nvd/cve-2026-45186)
- [Aqua AVD CVE-2026-56131](https://avd.aquasec.com/nvd/cve-2026-56131)
- [Aqua AVD CVE-2026-56407](https://avd.aquasec.com/nvd/cve-2026-56407)
- [Aqua AVD CVE-2026-56408](https://avd.aquasec.com/nvd/cve-2026-56408)
- [Debian security tracker: expat](https://security-tracker.debian.org/tracker/source-package/expat)
- Discovered by the Container Security workflow (Trivy) on
  [PR #299](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/299)

---

## CVE-2026-66046 | libexpat1, libexpat1-dev | High

| Field | Value |
|-------|-------|
| **CVE ID** | CVE-2026-66046 |
| **Package** | libexpat1, libexpat1-dev (Debian binary packages from the `expat` source package) |
| **Affected Version** | 2.8.3-1~deb13u1+dhi2 (Debian 13 "trixie", DHI mirror build) |
| **Fixed Version** | No fix available |
| **Severity** | High (per Trivy/Aqua feed) |
| **CVSS Score** | Not carried in the Trivy/Aqua feed as of 2026-09-02 |
| **Discovered** | 2026-09-02 |
| **Reassessment Due** | 2026-09-17 |
| **Blocking Release** | No |

### Description

A denial-of-service defect in Expat through 2.8.3. It is a seventh Expat CVE on
top of the six tracked in the entry above, and it entered the feed between two
scheduled scans: the 2026-08-26 run reported 35 findings and did not mention it,
the 2026-09-02 run reports it against both `libexpat1` and `libexpat1-dev`.
Like the other six it requires processing attacker-controlled XML through Expat.

### Impact on This Project

Identical to the six Expat CVEs in the entry above, and accepted on the same
reasoning. `libexpat1`/`libexpat1-dev` ship in the production runtime base
image; the application does not call into Expat (no `xml.parsers.expat` usage
in this codebase) and parses no untrusted XML on any request path, because the
API speaks JSON only. Exposure through the application surface is negligible.

### Remediation Plan

- [ ] Monitor the [Debian security tracker](https://security-tracker.debian.org/tracker/source-package/expat)
  for a fixed `expat` package that flows into the next DHI mirror rebuild
- [ ] Once a fixed digest is published, remove this suppression together with
  the six in the entry above and re-run the Container Security scan to confirm
- [ ] Reassess by 2026-09-17, deliberately the same date as the six sibling
  Expat CVEs, so the whole Expat acceptance is reviewed in one pass instead of
  drifting into seven separate dates

### Why Not Fixed Yet

Debian has not released a patched `expat` build for the DHI mirror's Debian 13
snapshot. Checked directly on 2026-09-02 against both the previously pinned base
digest (`sha256:5bbd41ae`) and the newer digest this change ships
(`sha256:d66d6403`): Trivy reports status `affected` with an empty Fixed Version
on both, so the digest refresh that clears the other 42 CVEs in this round does
not clear this one. The package comes from the hardened base image, which ships
no shell and no package manager, so there is no project-side upgrade path.

### References

- [Aqua AVD CVE-2026-66046](https://avd.aquasec.com/nvd/cve-2026-66046)
- [Debian security tracker: expat](https://security-tracker.debian.org/tracker/source-package/expat)
- Discovered by the Container Security workflow (Trivy) on
  [run 33601842565](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/runs/33601842565)

---

## CVE-2026-8376, CVE-2026-42496 and 3 further CVEs | perl-base | Critical/High

| Field | Value |
|-------|-------|
| **CVE ID** | CVE-2026-8376, CVE-2026-42496 (Critical); CVE-2026-42497, CVE-2026-48962, CVE-2026-9538 (High) |
| **Package** | perl-base (Debian binary package from the `perl` source package) |
| **Affected Version** | As shipped by the pinned base image (Debian 13 "trixie", DHI mirror build) |
| **Fixed Version** | No fix available on the trixie track. CVE-2026-42496, CVE-2026-42497 and CVE-2026-9538 are recorded `fix_deferred`; CVE-2026-8376 and CVE-2026-48962 are `affected` |
| **Severity** | Critical (CVE-2026-8376, CVE-2026-42496); High (CVE-2026-42497, CVE-2026-48962, CVE-2026-9538) |
| **CVSS Score** | Not carried in the advisory records consulted |
| **Discovered** | 2026-08-10 |
| **Reassessment Due** | 2026-11-08 |
| **Blocking Release** | No |

### Description

Five defects in Perl and its bundled modules: path traversal via crafted
symlinks in `Archive::Tar` (CVE-2026-42496), arbitrary file modification via
crafted hardlinks during archive extraction (CVE-2026-42497), denial of service
via a crafted tar header with a large entry size (CVE-2026-9538), arbitrary
code execution via an attacker-controlled output glob in `IO::Compress`
(CVE-2026-48962), and a heap buffer overflow when compiling regular expressions
**on 32-bit builds** (CVE-2026-8376).

These were suppressed in `.trivyignore` without documentation on 2026-08-10, in
commit `d1907a8` (PR #668, "publish public privacy and support pages"). That
provenance is recorded because it is the lesson: eight suppressions entered the
tree inside an unrelated frontend change, carrying no assessment, no severity
and no reassessment date, and nothing detected that for a week.

### Impact on This Project

The application never shells out. `grep -rn "subprocess\|os.system" src/`
returns nothing across the whole package, so no runtime code path can invoke
another program at all, let alone one of these. The container runs a single
uvicorn process as `USER 1000:1000`.

Nothing in the image invokes perl. The application is Python; `perl-base` is
present only because the Debian base layer ships it. Every one of these defects
requires perl to process attacker-controlled input: a crafted tar archive for
the three `Archive::Tar` CVEs, an attacker-controlled output glob for
`IO::Compress`, an attacker-controlled regular expression for CVE-2026-8376.
The application feeds perl nothing, because it never runs perl.

CVE-2026-8376 is additionally **not applicable by architecture**: the defect is
specific to 32-bit builds, and both the base image and this project's build are
`linux/amd64` only (the `ByronWilliamsCPA/container-images` catalog declares
`platform_compatibility.supported: [linux/amd64]` for `dhi-python-314`, and CI
builds with a plain `docker build` on an amd64 runner).

The two Critical ratings are why this entry exists rather than a shrug. A
Critical CVE accepted silently is the failure mode the Release Gate Policy was
written to prevent, and until today these two were accepted with no written
justification at all.

### Remediation Plan

- [ ] The durable fix is upstream: `perl-base` has no role in a Python runtime
  image. Removing it from `dhi.io/python:3.14-debian13` would close this entry
  and shrink the attack surface. Same routing as the `linux-libc-dev` ask: the
  mirror is `disposition: mirror_only`, so this is an ask to Docker.
- [ ] Re-verify fix status against the Debian security tracker from a session
  with network access to it, and record the result here (issue #711 item 1).
- [ ] Reassess by 2026-11-08.

### Why Not Fixed Yet

Debian records no fixed version on the trixie track for any of these. Three of
the perl-base CVEs carry Debian's `fix_deferred` status, which is not an absence
of a decision but an explicit one: the security team has ruled the defect will
not be fixed in the current stable release. The package is provided by the
hardened base image (`ghcr.io/byronwilliamscpa/dhi-python:3.14-debian13`), not
by this project's dependency set, and the DHI runtime image ships no shell and
no package manager, so it cannot upgrade itself even once a fix exists upstream.

**Provenance of this assessment, stated plainly.** Fix status and severity were
read from Trivy's Debian advisory records (Trivy 0.70.0's vulnerability
database, queried directly on 2026-08-17 rather than inferred from scan
absence, which suppression would have masked). That is the same data source the
Container Security workflow scans against, so it is not the independent
corroboration the earlier `linux-libc-dev` entries carried:
`security-tracker.debian.org`, `api.osv.dev`, `salsa.debian.org` and the Debian
mirrors are all unreachable from this project's cloud sessions (issue #711,
item 1). The reachability analysis below is independent of that source and is
the load-bearing part of the verdict. Confirming fix status against the Debian
tracker from a networked session remains outstanding.

### References

- [Debian security tracker: perl](https://security-tracker.debian.org/tracker/source-package/perl)
- Individual CVEs follow the `security-tracker.debian.org/tracker/<CVE-ID>` pattern
- Suppressed without documentation in commit `d1907a8`; documented 2026-08-17

---

## CVE-2026-11822, CVE-2026-11824 | libsqlite3-0 | Medium

| Field | Value |
|-------|-------|
| **CVE ID** | CVE-2026-11822, CVE-2026-11824 |
| **Package** | libsqlite3-0 (Debian binary package from the `sqlite3` source package) |
| **Affected Version** | As shipped by the pinned base image (SQLite before 3.53.2) |
| **Fixed Version** | No fix available on the trixie track; both recorded `affected` |
| **Severity** | Medium (both). **Below the scan threshold**, see below |
| **CVSS Score** | Not carried in the advisory records consulted |
| **Discovered** | 2026-08-10 |
| **Reassessment Due** | 2026-11-08 |
| **Blocking Release** | No |

### Description

Memory corruption in SQLite before 3.53.2 (CVE-2026-11822) and a heap-based
buffer overflow in the same range (CVE-2026-11824). Exploitation requires
SQLite to parse attacker-controlled SQL or a crafted database file.

### Impact on This Project

The application never shells out. `grep -rn "subprocess\|os.system" src/`
returns nothing across the whole package, so no runtime code path can invoke
another program at all, let alone one of these. The container runs a single
uvicorn process as `USER 1000:1000`.

This project does not use SQLite. Persistence is PostgreSQL over async
SQLAlchemy with `asyncpg` (`core/database.py`); `grep -rn -i sqlite src/`
returns a single hit, a comment in `generation/worker_main.py` about a test
limitation, and no import. CPython's stdlib `sqlite3` module links this library
but is never imported by the application, so the vulnerable parser is never
handed input.

**These two suppressions are currently inert.** The Container Security workflow
is called with `severity-threshold: CRITICAL,HIGH`, and both are Medium, so
Trivy never reports them and the ignore entries suppress nothing. They are
documented rather than deleted because the threshold is a caller input that
could reasonably widen, and an undocumented entry that becomes live later is the
exact failure this document exists to prevent. If the threshold is ever widened
to Medium, this entry is already in place.

### Remediation Plan

- [ ] Monitor for a trixie-track `sqlite3` at 3.53.2 or later; on arrival, let
  it flow in via a base-image digest refresh and delete both entries.
- [ ] Re-verify fix status against the Debian security tracker from a networked
  session (issue #711 item 1).
- [ ] Reassess by 2026-11-08.

### Why Not Fixed Yet

Debian records no fixed version on the trixie track for either CVE; both are
recorded `affected`, not `fix_deferred`, so Debian has neither shipped a fix nor
ruled one out. The package is provided by the
hardened base image (`ghcr.io/byronwilliamscpa/dhi-python:3.14-debian13`), not
by this project's dependency set, and the DHI runtime image ships no shell and
no package manager, so it cannot upgrade itself even once a fix exists upstream.

**Provenance of this assessment, stated plainly.** Fix status and severity were
read from Trivy's Debian advisory records (Trivy 0.70.0's vulnerability
database, queried directly on 2026-08-17 rather than inferred from scan
absence, which suppression would have masked). That is the same data source the
Container Security workflow scans against, so it is not the independent
corroboration the earlier `linux-libc-dev` entries carried:
`security-tracker.debian.org`, `api.osv.dev`, `salsa.debian.org` and the Debian
mirrors are all unreachable from this project's cloud sessions (issue #711,
item 1). The reachability analysis below is independent of that source and is
the load-bearing part of the verdict. Confirming fix status against the Debian
tracker from a networked session remains outstanding.

### References

- [Debian security tracker: sqlite3](https://security-tracker.debian.org/tracker/source-package/sqlite3)
- Suppressed without documentation in commit `d1907a8`; documented 2026-08-17

---

## CVE-2025-69720 | ncurses (libncursesw6, libtinfo6, ncurses-base, ncurses-bin) | High

| Field | Value |
|-------|-------|
| **CVE ID** | CVE-2025-69720 |
| **Package** | ncurses family (Debian binary packages from the `ncurses` source package) |
| **Affected Version** | As shipped by the pinned base image (Debian 13 "trixie", DHI mirror build) |
| **Fixed Version** | No fix available on the trixie track; recorded `affected` |
| **Severity** | High |
| **CVSS Score** | Not carried in the advisory records consulted |
| **Discovered** | 2026-08-10 |
| **Reassessment Due** | 2026-11-08 |
| **Blocking Release** | No |

### Description

A buffer overflow in ncurses that may lead to arbitrary code execution.
Exploitation requires an ncurses-linked program to process attacker-controlled
terminal description data (a crafted `terminfo` entry, typically reached via
`TERM` or `TERMINFO` pointing at attacker-supplied content).

### Impact on This Project

The application never shells out. `grep -rn "subprocess\|os.system" src/`
returns nothing across the whole package, so no runtime code path can invoke
another program at all, let alone one of these. The container runs a single
uvicorn process as `USER 1000:1000`.

Nothing in the image links or calls ncurses at runtime. There is no terminal
user interface: `grep -rn "import curses" src/` returns nothing, and the DHI
hardened runtime image ships **no shell at all**, which is both why the
Dockerfile uses a numeric `USER 1000:1000` and why the compose files must
override the command rather than relying on shell expansion. The container's
only process is uvicorn serving HTTP, with no controlling terminal and no
attacker-influenced `TERM` or `TERMINFO`.

### Remediation Plan

- [ ] Monitor the Debian security tracker for a fixed `ncurses` on the trixie
  track; on arrival, let it flow in via a base-image digest refresh and delete
  the entry.
- [ ] Re-verify fix status against the Debian security tracker from a networked
  session (issue #711 item 1).
- [ ] Reassess by 2026-11-08.

### Why Not Fixed Yet

Debian records no fixed version on the trixie track for this CVE, which is
recorded `affected`, not `fix_deferred`, so Debian has neither shipped a fix nor
ruled one out. The package is provided by the
hardened base image (`ghcr.io/byronwilliamscpa/dhi-python:3.14-debian13`), not
by this project's dependency set, and the DHI runtime image ships no shell and
no package manager, so it cannot upgrade itself even once a fix exists upstream.

**Provenance of this assessment, stated plainly.** Fix status and severity were
read from Trivy's Debian advisory records (Trivy 0.70.0's vulnerability
database, queried directly on 2026-08-17 rather than inferred from scan
absence, which suppression would have masked). That is the same data source the
Container Security workflow scans against, so it is not the independent
corroboration the earlier `linux-libc-dev` entries carried:
`security-tracker.debian.org`, `api.osv.dev`, `salsa.debian.org` and the Debian
mirrors are all unreachable from this project's cloud sessions (issue #711,
item 1). The reachability analysis below is independent of that source and is
the load-bearing part of the verdict. Confirming fix status against the Debian
tracker from a networked session remains outstanding.

### References

- [Debian security tracker: ncurses](https://security-tracker.debian.org/tracker/source-package/ncurses)
- Suppressed without documentation in commit `d1907a8`; documented 2026-08-17

---

## linux-libc-dev kernel UAPI headers (package-scoped acceptance) | linux-libc-dev | High

| Field | Value |
|-------|-------|
| **CVE ID** | Not enumerated by design. This entry accepts a *package*, not a CVE list; 61 individual CVEs have been absorbed so far and are recorded below for the audit trail |
| **Package** | linux-libc-dev (Debian binary package from the `linux` kernel source package) |
| **Affected Version** | Whatever the pinned base image ships; 6.12.101-1+dhi0 as of 2026-08-16 (Debian 13 "trixie", DHI mirror build) |
| **Fixed Version** | Not applicable. This acceptance covers ONLY findings with no fixed version on the trixie track. A `linux-libc-dev` CVE that carries a fixed version is NOT accepted here and still fails the scan |
| **Severity** | High (per Trivy/Aqua feed); no Critical has appeared in this package to date |
| **CVSS Score** | Rarely assigned; the Debian tracker has shown no CVSS for the large majority of these |
| **Discovered** | 2026-07-19 (first kernel-header entry); consolidated into this entry 2026-08-16 |
| **Reassessment Due** | 2026-09-17 |
| **Blocking Release** | No |

### Description

`linux-libc-dev` ships the Linux kernel's userspace API (UAPI) headers. Debian
tracks vulnerabilities against the `linux` source package, so every kernel CVE
Debian records is reported by Trivy against this binary package, whether or not
the defect has anything to do with headers.

This entry replaces eight separate per-CVE entries written between 2026-07-19
and 2026-08-14. Each was researched independently, each verified against the
Debian security tracker, and each reached the same conclusion. That is the
evidence for treating this as one finding: over nine rounds in four weeks the
verdict never once varied, because it does not depend on which kernel subsystem
a given CVE names. Continuing to enumerate CVE IDs was recording a single
judgment 61 times, and leaving the Container Security workflow red for days
between rounds while the paperwork caught up.

### Impact on This Project

The package contains no kernel binary and executes no kernel code. It is a set
of C headers consumed at compile time. The container runs a FastAPI application
on whatever kernel the Docker host provides, which is unrelated to the version
recorded in this package's metadata; patching or removing the package would not
change which kernel actually runs.

Stated without overclaiming: some of these CVEs name subsystems that plausibly
exist on a container host (`proc`/`ptrace`, `virtio-net`, `net/sched`,
`mac80211`, x86 speculative-execution mitigations), while others name hardware
this deployment does not have at all (ARM64 pKVM, s390 `pkey`, AMD GPU DRM,
`drm/panthor`, `ath6kl` Wi-Fi). The distinction does not change the assessment,
because neither group is reachable *through this image or this package*. Where
a host kernel is genuinely affected, the remediation is host patching, which is
outside this repository and unaffected by anything shipped in the image.

### How This Acceptance Is Enforced

`.trivy/ignore-policy.rego`, wired through `trivy.yaml`, carries two guards:

```rego
ignore {
	input.PkgName == "linux-libc-dev"
	not input.FixedVersion
	time.now_ns() < time.parse_rfc3339_ns("2026-09-17T00:00:00Z")
}
```

The third guard is the expiry, and it is what stops this acceptance outliving
its own justification. Trivy evaluates the date itself, so once
`Reassessment Due` passes, the rule stops matching and every suppressed finding
returns to the scan. Without it the documented date could lapse, the
release-gate checker could go red over it, and the scan would still report
zero, leaving the Security tab and every push, schedule and manual inventory
silent on an acceptance nobody had renewed. That date and this entry's
`Reassessment Due` are cross-checked by
`scripts/check_known_vulnerabilities.py`, so they cannot drift apart, and the
same script fails the build if the rule ever loses its expiry.

The second guard is what keeps this honest, and it is not decorative. On
2026-08-02 the base image advanced to 6.12.100-1+dhi0 and cleared
CVE-2026-64530 and CVE-2026-64531, which Debian had fixed (DSA-6405-1). Those
two were actionable, a blanket package suppression would have hidden them, and
under this policy they would still have failed the scan and prompted exactly
the digest refresh that resolved them. Fixable kernel-header findings remain
release-relevant; unfixable ones do not.

`tests/unit/test_trivy_ignore_policy.py` pins both guards, including that a
fixable `linux-libc-dev` finding survives the policy.

### Remediation Plan

- [ ] The real fix is upstream and outside this repository: `linux-libc-dev` is
  a `-dev` package with no purpose in a runtime image that has no compiler.
  Removing it from `dhi.io/python:3.14-debian13` would end this class outright.
  The `ByronWilliamsCPA/container-images` mirror cannot do this: its catalog
  entry is `disposition: mirror_only`, a byte-for-byte copy of upstream, so
  this is an ask to Docker rather than a mirror change.
- [ ] Until then, no per-CVE action is expected or useful. New unfixed
  kernel-header CVEs are absorbed by the policy without a documentation change,
  which is the entire point of consolidating.
- [ ] Any `linux-libc-dev` CVE that DOES acquire a fixed version will fail the
  scan on its own; handle it by requesting a base-image digest refresh, as
  `bb89468` did for CVE-2026-64564.
- [ ] Reassess by 2026-09-17: confirm the package is still present in the base
  image, that the policy still matches only what it should, and that no
  accepted CVE has since acquired a trixie-track fix.

### Why Not Fixed Yet

Verified consistently across all eight superseded entries and not assumed:
Debian records these as vulnerable on both `trixie` and `trixie-security`, with
fixes landing only in `sid`, which this base image does not track. Trivy's empty
Fixed Version column is therefore accurate for the release track in use, not a
feed gap. The package comes from the hardened base image rather than this
project's dependency set, and the DHI runtime image ships no shell and no
package manager, so it cannot upgrade itself even once a fix exists upstream.

**Why `Blocking Release | No`.** No fixed package exists on the trixie track for
anything this entry covers, so holding a release buys no remediation. Per the
Release Gate Policy this is a dated verdict, not a standing exemption. The
2026-09-17 date is deliberately the *earliest* reassessment date carried by any
of the eight entries this replaces, not a fresh 90-day window: consolidating
records must not silently extend a deadline that was already running.

### CVEs Absorbed To Date

Recorded so the audit trail survives consolidation, and so a future reader can
confirm that a given CVE was assessed rather than never seen. This list is a
historical record, not a suppression list; the policy matches by package and
does not read it. New unfixed kernel-header CVEs will not be appended.

| CVE-2013-7445 | CVE-2019-19449 | CVE-2019-19814 | CVE-2021-3847 | CVE-2021-3864 | CVE-2024-21803 |
| CVE-2024-58015 | CVE-2025-22104 | CVE-2025-38137 | CVE-2025-38187 | CVE-2025-38204 | CVE-2025-38206 |
| CVE-2025-38421 | CVE-2025-38636 | CVE-2025-39859 | CVE-2025-39862 | CVE-2025-39958 | CVE-2025-68174 |
| CVE-2025-68735 | CVE-2026-23102 | CVE-2026-23208 | CVE-2026-23327 | CVE-2026-31493 | CVE-2026-31536 |
| CVE-2026-31568 | CVE-2026-43185 | CVE-2026-43198 | CVE-2026-43263 | CVE-2026-46130 | CVE-2026-46181 |
| CVE-2026-46279 | CVE-2026-52991 | CVE-2026-53000 | CVE-2026-53010 | CVE-2026-53089 | CVE-2026-53091 |
| CVE-2026-53109 | CVE-2026-53118 | CVE-2026-53277 | CVE-2026-53330 | CVE-2026-63879 | CVE-2026-63970 |
| CVE-2026-64017 | CVE-2026-64283 | CVE-2026-64287 | CVE-2026-64364 | CVE-2026-64375 | CVE-2026-64434 |
| CVE-2026-64534 | CVE-2026-64552 | CVE-2026-64558 | CVE-2026-64561 | CVE-2026-68159 | CVE-2026-68166 |
| CVE-2026-68198 | CVE-2026-68264 | CVE-2026-68291 | CVE-2026-68337 | CVE-2026-68409 | CVE-2026-68426 |
| CVE-2026-68480 |  |  |  |  |  |

### References

- [Debian security tracker: linux](https://security-tracker.debian.org/tracker/source-package/linux)
- Individual CVEs follow the `security-tracker.debian.org/tracker/<CVE-ID>` and
  `avd.aquasec.com/nvd/<cve-id>` URL patterns
- Superseded entries and their individual verification evidence remain in git
  history: `git log -p --follow docs/known-vulnerabilities.md`
- Most recent discovery: Container Security workflow (Trivy v0.70.0),
  [workflow run 31954204801](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/runs/31954204801)
  on 2026-08-16, which reported CVE-2025-68174 and CVE-2025-68735

## Resolved Entries

| CVE              | Package        | Resolved Date | Resolution                                             |
|------------------|----------------|---------------|--------------------------------------------------------|
| PYSEC-2022-42969 | py             | 2026-07-29    | Withdrawn upstream as disputed. See detail below.      |
| PYSEC-2026-89    | markdown       | 2026-07-29    | Not affected; 3.10.2 carries the 3.8.1 fix. See below. |
| CVE-2026-53399   | linux-libc-dev | 2026-07-30    | Fixed by base 6.12.96-1+dhi0.                          |
| CVE-2026-64600   | linux-libc-dev | 2026-07-30    | Fixed by base 6.12.96-1+dhi0.                          |
| CVE-2026-64530   | linux-libc-dev | 2026-08-02    | Fixed by base 6.12.100-1+dhi0 (DSA-6405-1).            |
| CVE-2026-64531   | linux-libc-dev | 2026-08-02    | Fixed by base 6.12.100-1+dhi0 (DSA-6405-1).            |

The four `linux-libc-dev` rows were all cleared by a base-image digest refresh rather than
by a suppression. They are the precedent for the `not input.FixedVersion` guard in
`.trivy/ignore-policy.rego`: each carried a Debian fixed version, so each stayed visible to the
scan until the base moved. The package-scoped acceptance above deliberately does not cover that
case. Their original per-CVE entries were consolidated on 2026-08-16 and remain in git history.

Aliases: PYSEC-2022-42969 is CVE-2022-42969 and GHSA-w596-4wvx-j9j6 (duplicate OSV record
PYSEC-2022-43183); PYSEC-2026-89 is CVE-2025-69534 and GHSA-5wmx-573v-2qwq.

### Resolution detail: PYSEC-2022-42969 (`py`)

Reassessed 2026-07-29 (overdue from 2026-07-20). The advisory was retracted by both
sources that carried it:

- **GHSA-w596-4wvx-j9j6 was withdrawn 2025-08-01**, with the stated ground that
  "evidence does not suggest that CVE-2022-42969 is a valid, reproducible
  vulnerability."
- **PYSEC-2022-42969 was withdrawn 2026-06-09**, as was its duplicate record
  PYSEC-2022-43183. Both post-date the 2026-05-21 assessment, which is why the entry
  was opened in good faith at the time.

Confirmed live-finding status rather than relying on the advisory metadata alone:

- An OSV version query for `py` 1.11.0 returns no live advisory.
- `uv run pip-audit` reports "No known vulnerabilities found."
- `osv-scanner scan source -L uv.lock` reports "No issues found." This is not a
  suppression artifact: `osv-scanner.toml` has no active `[[IgnoredVulns]]` entries, and
  neither this advisory nor any alias appears in `.trivyignore`.

Both scans are clean with `py` still pinned at 1.11.0, so the clean result reflects the
retraction, not a version change. The dependency itself is unchanged and still reachable
in the dev tree only: `py` 1.11.0 arrives via `interrogate` 1.7.0, which is still the
latest release (2024-04-07) and still declares `py` in its `requires_dist`. No newer
`interrogate` drops it, so no upgrade path exists, and with the advisory withdrawn none
is needed. Replacing `interrogate` was evaluated and rejected as unjustified: it is
wired into pre-commit at two scopes (`scripts/` at 85 percent, `src/` at 80 percent) and
swapping it would trade a working, pinned quality gate for churn against a
non-vulnerability.

**What would reopen this:** a re-publication of the advisory as non-disputed, or a new
advisory against `py` 1.11.0. The residual concern is maintenance, not security:
`interrogate` has had no release since April 2024 and pins an unmaintained transitive
dependency. That belongs in the debt register, not here.

### Resolution detail: PYSEC-2026-89 (`markdown`)

Reassessed 2026-07-29 (overdue from 2026-07-20). The prior entry recorded that the fix
landed in 3.8.1 but was not carried into the 3.9+ series. That is incorrect as of this
check, and the correction was verified at source rather than taken from advisory
metadata.

Advisory state, from two independent records:

- **GHSA-5wmx-573v-2qwq** (not withdrawn; modified 2026-06-06) gives the affected range
  as `introduced 0` to `fixed 3.8.1`, with no later re-introduction event.
- **PYSEC-2026-89** (not withdrawn; modified 2026-06-10) gives the range as
  `introduced 0` to `last_affected 3.8`, and enumerates 54 affected versions, none of
  them in the 3.9, 3.10, 3.11, or 3.12 series.

Both records were modified after the 2026-05-21 assessment, so an amended affected range
is the likely origin of the earlier reading.

Source-level verification, which is the decisive evidence here: the two guards
introduced in 3.8.1 are present verbatim in the installed 3.10.2
(`markdown/htmlparser.py`):

1. `parse_html_declaration` routes a `<![` prefix that is not `<![CDATA[` to
   `parse_bogus_comment`, with the upstream comment referencing issue 1534 and CPython
   `gh-77057` intact.
2. `parse_starttag` treats `</>` as literal data, paired with the
   `htmlparser.starttagopen` monkeypatch that lets `</>` reach it.

Confirmed by scanners as well: an OSV version query for `markdown` 3.10.2 returns no
advisory; `pip-audit` and `osv-scanner` are both clean with 3.10.2 still pinned. A
dynamic reproduction attempt was run against 3.8 and 3.10.2 on CPython 3.11.15 and did
not discriminate (both parsed the malformed inputs cleanly), which is consistent with the
crash depending on the CPython point release; it is recorded here as inconclusive and
carries no weight in this verdict. The source diff does.

Because 3.10.2 is not affected, the pin-to-3.8.2 option in the prior remediation plan is
moot and was not pursued; downgrading would move the tree onto an affected version.

**What would reopen this:** a new advisory naming a 3.9+ version, or removal of either
guard in a future release.

### Reachability findings common to both (verified 2026-07-29)

Recorded because both entries rested on a dev-only reachability claim, and that claim was
re-verified rather than carried forward:

- **Neither package reaches production.** `uv export --no-dev` resolves neither `py` nor
  `markdown`; both are reachable only through the `dev` extra (`py` via `interrogate`,
  `markdown` via `mkdocs`, `mkdocs-material`, `mkdocstrings`, `pymdown-extensions`, and
  `properdocs`).
- **Neither ships in the container image.** The Dockerfile's runtime stages install with
  `uv sync --frozen --no-dev --extra api`, which excludes the dev extra.
- **No runtime code parses Markdown.** There is no import of the `markdown` package
  anywhere in `src/`. The matches for the string "markdown" are docstrings, prompt text,
  and `measurement/report.py::render_markdown`, which emits Markdown by string
  templating and parses none.
- **No CI workflow renders untrusted Markdown.** No workflow reads
  `github.event.pull_request.body`, `github.event.issue.body`, or
  `github.event.comment.body`. The only Markdown-rendering workflow is `docs.yml`, which
  builds MkDocs over repository-controlled files under `docs/`.

## Review History

| Review Date | Reviewer       | Notes                                                                 |
|-------------|----------------|-----------------------------------------------------------------------|
| 2026-05-21  | Byron Williams | Initial creation (date taken from the first entries' assessment date). |
| 2026-07-08  | Byron Williams | Added CVE-2026-53615 (libuuid1, runtime base image; no upstream fix). |
| 2026-07-14  | Byron Williams | Added gawk CVE-2026-40467/40468/40469/40553 (runtime base image; no upstream fix). |
| 2026-07-19  | Byron Williams | Added libexpat1/libexpat1-dev CVE-2025-59375/2026-25210/45186/56131/56407/56408 (runtime base image; no upstream fix; same mirror regression independently found via PR #296). |
| 2026-07-19  | Byron Williams | Added linux-libc-dev CVE-2026-43185 (Critical) plus 33 further kernel CVEs (runtime base image; kernel UAPI headers only, no running kernel code; no upstream fix). |
| 2026-07-24  | Byron Williams | Added 8 further linux-libc-dev kernel-header CVEs from PR #394 Trivy: 6 no-fix (53089/53109/53118/53330/63970/64017) plus 2 tracked-with-fix in 6.12.96-1 not yet in the dhi-python base (53399/64600). |
| 2026-07-29  | Byron Williams | Reassessed 2 overdue entries; resolved both; added gate ruling.       |
| 2026-07-30  | Byron Williams | Added 7 further linux-libc-dev kernel-header CVEs from the PR #494 Trivy run (64287/64364/64375/64434/64534/64552/64558); all High, none fixed on the trixie track (fix only in sid 7.1.5-1). Tracked in issue #505. Base advanced to 6.12.96-1+dhi0, which clears CVE-2026-53399/64600 from the prior entry. |
| 2026-07-30  | Byron Williams | Suppressed the 7 new CVEs in .trivyignore per that file's stated scope (base-image OS-package CVEs with no upstream fix, each paired with an entry here). Resolved CVE-2026-53399/64600: removed their .trivyignore block, whose own removal condition (base ships 6.12.96-1) is met; verified fixed in trixie-security 6.12.96-1 on the Debian tracker rather than inferred from scan absence, which suppression would have masked. |
| 2026-08-04  | Byron Williams | Added linux-libc-dev CVE-2026-64561 (KVM x86 MMU) from the PR #597 Trivy run; High, empty Fixed Version, base version unchanged at 6.12.100-1+dhi0, so a feed refresh rather than an image change (main's run 3.5h earlier was clean). Verified on the Debian tracker before accepting into .trivyignore: trixie and trixie-security both vulnerable at 6.12.100-1, fix is sid-only (7.1.6-1). Reassessment aligned to 2026-09-30 with CVE-2026-63879. |
| 2026-08-08  | Byron Williams | Added linux-libc-dev CVE-2026-68480 (x86 SRSO Safe-RET) from the PR #644 Trivy run (run 31262431949); High, empty Fixed Version, and the run's only finding. Established it as a feed refresh rather than a PR regression by pinned-digest identity across main and head plus the last executing run (30973596262, 2026-08-05) being clean, since main's own tip shows the job `skipped` and proves nothing either way. Verified on the Debian tracker before accepting into .trivyignore: trixie (6.12.94-1) and trixie-security (6.12.101-1) both vulnerable, fix is sid-only (7.1.7-1). Confirmed the pinned GHCR digest is still the live one, so a base-image re-pin was not an available remedy. Reassessment aligned to 2026-09-30 with CVE-2026-63879 and CVE-2026-64561. |
| 2026-08-14  | Byron Williams | Added linux-libc-dev CVE-2026-64283/68159/68166/68198/68264/68291/68337/68409/68426 from the PR #709 Container Security run (run 31760080363); all High, empty Fixed Version, status `affected`, base advanced to 6.12.101-1+dhi0 at digest `sha256:5bbd41ae...`. Established as a feed refresh rather than a PR regression: no container file in the diff, Dockerfile untouched since `bb89468`, base commit `20e26221` green 2026-08-13T00:05, the scheduled 2026-08-12 run already red on main, and 0 findings across every Python package. Verified on the Debian tracker before accepting into `.trivyignore`, each CVE fetched individually: all nine vulnerable in trixie (6.12.94-1) and trixie-security (6.12.101-1), fix is sid-only (7.1.8-1), which rules out a base-image re-pin as an alternative remedy. Confirmed the pinned GHCR digest still resolves (HTTP 200); the `3.14-debian13` tag did not resolve from that session, noted as unconfirmed rather than assumed. Reassessment aligned to 2026-09-30 with CVE-2026-63879, CVE-2026-64561 and CVE-2026-68480. Closes item 1 of issue #711. |
| 2026-08-16  | Byron Williams | Consolidated all eight `linux-libc-dev` per-CVE entries (61 CVEs) into a single package-scoped acceptance, enforced by `.trivy/ignore-policy.rego` via `trivy.yaml` rather than by 61 `.trivyignore` lines. The policy suppresses only findings with NO fixed version, so the CVE-2026-64530 / CVE-2026-64531 case (cleared by a base-image bump) would still surface today. Reassessment set to 2026-09-17, the earliest date carried by any superseded entry, so consolidation extends no deadline. Removed the duplicate CVE-2026-68480 block introduced on 2026-08-08. Corrected the libuuid1 and gawk entries, which named the 3.12 base image while the project has run 3.14 since #295, and replaced the placeholder creation date (UW-K02). Reassessment dates are now machine-enforced by `scripts/check_known_vulnerabilities.py`; two entries surfaced by the 2026-08-16 scan (CVE-2025-68174, CVE-2025-68735) are covered by the policy without individual entries. Answers item 2 of issue #711: the reusable workflow exposes no `ignore-unfixed` input, and none is needed. |
| 2026-08-17  | Byron Williams | Reassessment window widened from 60 to 90 days, aligning this document with the org-wide `ignore-expiry-horizon-days` default in `ByronWilliamsCPA/.github` PR #293 so the repository and the reusable container-security workflow cannot disagree about how long a suppression may live. Added a `Last Reassessed` field: the window now runs from the last time evidence was gathered, so renewing an entry no longer requires editing `Discovered`. Closed UW-D31 by documenting the eight suppressions that entered the tree undocumented in `d1907a8` (PR #668, a frontend change): perl-base (5, including two Critical), libsqlite3-0 (2, both Medium and therefore inert at the CRITICAL,HIGH scan threshold) and ncurses (1). Fix status read directly from Trivy 0.70.0's Debian advisory records rather than inferred from scan absence; three perl CVEs carry Debian's `fix_deferred` status. Independent Debian-tracker corroboration is still outstanding and is recorded as such in each entry, since that host is unreachable from cloud sessions (#711 item 1). `known-vulnerabilities-baseline.toml` deleted: no grandfathered debt remains. |
| 2026-08-17  | Byron Williams | Migrated `.trivyignore` to `.trivyignore.yaml`, adopting the org revisit-date format from `ByronWilliamsCPA/.github` PR #293 and bumping the reusable workflow pin to v10.1.0 (`07f56c2`). All 19 per-CVE suppressions now carry a `statement` and an `expired_at`; the plain-text format could not express an expiry, so every entry in it was permanent by construction. Verified both directions against Trivy 0.70.0: an unexpired entry suppresses, an expired one lets the finding back into the gate. The org's own `check_trivy_ignore_expiry.py` passes on the new file (19/19 within 90 days), and would have failed the bump had the plain file remained. Adopted `ignore-unfixed` scoped by trigger so only fixable findings gate a merge while push, schedule and manual runs keep the full inventory and the Security tab. Pinned `central-checker-ref` to a SHA rather than the default floating `main`, which would otherwise execute a moving third-party script in this repository's CI. Declined `python-container-revisit.yml`: its per-CVE tracker issue would rebuild the enumeration the 2026-08-16 consolidation removed. |
