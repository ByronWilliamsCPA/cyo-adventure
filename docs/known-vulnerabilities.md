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
   reassessed within 60 days. Once an entry passes its `Reassessment Due` date it blocks
   releases per the OpenSSF release gate policy, whatever its `Blocking Release` value
   says, because that value has expired and no longer rests on verified evidence.

**Ruling (2026-07-29).** Where the two gates appear to conflict, the process gate
governs. An overdue entry closes the release gate even when it reads
`Blocking Release | No`. The opposite reading, that `Blocking Release | No` exempts an
entry from the deadline, is rejected: it would let any entry opt out of reassessment
permanently and would drain the 60-day rule of any force. This resolves the
contradiction between the former preamble and the two entries that sat overdue and
non-blocking from 2026-07-20 to 2026-07-29.

**Reopening the gate.** Reassess the entry: re-verify fix status, reachability, and
severity against current sources; record what was checked, on what date, and what
evidence would change the verdict; then set a new `Reassessment Due` date within 60 days
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

## CVE-2026-43185 and 33 further kernel-header CVEs | linux-libc-dev | Critical/High

| Field | Value |
|-------|-------|
| **CVE ID** | CVE-2026-43185 (Critical); CVE-2013-7445, CVE-2019-19449, CVE-2019-19814, CVE-2021-3847, CVE-2021-3864, CVE-2024-21803, CVE-2024-58015, CVE-2025-22104, CVE-2025-38137, CVE-2025-38187, CVE-2025-38204, CVE-2025-38206, CVE-2025-38421, CVE-2025-38636, CVE-2025-39859, CVE-2025-39862, CVE-2025-39958, CVE-2026-23102, CVE-2026-23208, CVE-2026-23327, CVE-2026-31493, CVE-2026-31536, CVE-2026-31568, CVE-2026-43198, CVE-2026-43263, CVE-2026-46130, CVE-2026-46181, CVE-2026-46279, CVE-2026-52991, CVE-2026-53000, CVE-2026-53010, CVE-2026-53091, CVE-2026-53277 (High, 33 CVEs) |
| **Package** | linux-libc-dev (Debian binary package from the `linux` kernel source package) |
| **Affected Version** | 6.12.95-1+dhi0 (Debian 13 "trixie", DHI mirror build) |
| **Fixed Version** | No fix available |
| **Severity** | Critical (CVE-2026-43185); High (remaining 33) |
| **CVSS Score** | Not individually catalogued here; see per-CVE Aqua/NVD links below |
| **Discovered** | 2026-07-19 |
| **Reassessment Due** | 2026-09-17 |
| **Blocking Release** | No |

### Description

34 kernel defects reported against `linux-libc-dev`'s tracked kernel source
version, spanning unrelated subsystems: SMB/CIFS server `ksmbd` (including the
Critical signedness bug in `smb_direct_prepare_negotiation()`,
CVE-2026-43185, and a separate use-after-free, CVE-2026-53010), filesystems
(f2fs, exFAT, JFS), Bluetooth, GPU drivers (GEM, nouveau), wifi (ath12k,
mt76), RDMA (including efa and mlx4), ARM64 KVM, s390, netfilter, TCP, ALSA
usb-audio, dm-verity-fec, and several more. This breadth of unrelated
subsystems in a single package's finding set is itself the signal for this
package's known false-positive class (see Why Not Fixed Yet).

### Impact on This Project

`linux-libc-dev` ships kernel UAPI headers used at compile time by userspace
programs; it contains no kernel binary and executes no kernel code at
runtime. None of the 34 vulnerable code paths (ksmbd, f2fs, Bluetooth,
GPU/wifi drivers, RDMA, netfilter, and so on) run inside this container,
which serves a FastAPI web application under whatever kernel the Docker host
provides, not the kernel version recorded in this package's own metadata.
Exposure through the application surface, and through the container
generally, is negligible.

### Remediation Plan

- [ ] Monitor the [Debian security tracker](https://security-tracker.debian.org/tracker/source-package/linux)
  for the DHI mirror to rebuild against a newer kernel-headers snapshot
- [ ] Once a fixed digest is published, remove these 34 `.trivyignore`
  entries and re-run the Container Security scan to confirm
- [ ] Reassess by 2026-09-17

### Why Not Fixed Yet

Debian has not released a patched `linux-libc-dev` build for the DHI mirror's
snapshot (Trivy reports an empty Fixed Version with status `affected` for all
34 CVEs). The package is provided by the hardened base image, not managed by
this project's dependency set, so no project-side upgrade path exists: the
DHI runtime image ships no shell and no package manager (confirmed directly
against this project's Dockerfile runtime stage), so it cannot run
`apt-get` itself even if a fix existed upstream. This is the same
mirror-wide Debian 13 base-layer regression documented in the libexpat entry
above, independently corroborated via PR #296's unrelated review of the
`dhi-python:3.12-debian13` digest; it traces to the
`ByronWilliamsCPA/container-images` mirror pipeline, where every
`debian13`-tagged image has Trivy-failed on this same package family since
around 2026-06-28 with no fix currently in flight there.

### References

- [Debian security tracker: linux](https://security-tracker.debian.org/tracker/source-package/linux)
- [Aqua AVD CVE-2026-43185](https://avd.aquasec.com/nvd/cve-2026-43185) (Critical; the remaining 33 CVEs follow the same `avd.aquasec.com/nvd/<cve-id>` URL pattern)
- Discovered by the Container Security workflow (Trivy) on
  [PR #299](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/299)

---

## CVE-2026-53089 and 7 further kernel-header CVEs (2 since resolved) | linux-libc-dev | High

> **Partially resolved 2026-07-30.** CVE-2026-53399 and CVE-2026-64600, the two
> "fix-available-but-not-yet-shipped" CVEs in this entry, are **closed**: the
> `dhi-python:3.14-debian13` base advanced from `linux-libc-dev` 6.12.95-1+dhi0
> to 6.12.96-1+dhi0, which is the version Debian records as fixing both. See
> "Resolution of the 2 fixable CVEs" below. The 6 no-fix CVEs remain **open**
> and keep their 2026-09-24 reassessment date.

| Field | Value |
|-------|-------|
| **CVE ID** | Open, no fix (6): CVE-2026-53089, CVE-2026-53109, CVE-2026-53118, CVE-2026-53330, CVE-2026-63970, CVE-2026-64017. Resolved 2026-07-30 (2): CVE-2026-53399, CVE-2026-64600 |
| **Package** | linux-libc-dev (Debian binary package from the `linux` kernel source package) |
| **Affected Version** | 6.12.95-1+dhi0 at discovery (Debian 13 "trixie", DHI mirror build); the base now ships 6.12.96-1+dhi0 |
| **Fixed Version** | The 6 open CVEs report no fix available. CVE-2026-53399 and CVE-2026-64600 are fixed in `linux-libc-dev` 6.12.96-1, which the base image now ships |
| **Severity** | High (all 8, per Trivy/Aqua feed) |
| **CVSS Score** | Not individually catalogued here; see per-CVE Aqua/NVD links below |
| **Discovered** | 2026-07-24 |
| **Reassessment Due** | 2026-09-24 (the 6 open no-fix CVEs). The 2 fixable CVEs were resolved on 2026-07-30 and no longer carry a date |
| **Blocking Release** | No |

### Description

Eight further kernel defects reported against `linux-libc-dev`'s tracked kernel
source version, newly surfaced after the 34-CVE set documented in the block
above. Like that set they span unrelated kernel subsystems and follow the same
`linux-libc-dev` false-positive class (kernel UAPI headers, not a running
kernel binary). Six report an empty Fixed Version with status `affected`. Two
(CVE-2026-53399, CVE-2026-64600) had an upstream fix in `linux-libc-dev`
6.12.96-1 that the base image had not yet picked up at discovery; it has since
picked it up, and those two are resolved (see below).

### Resolution of the 2 fixable CVEs (2026-07-30)

CVE-2026-53399 and CVE-2026-64600 are **resolved**. The condition this entry set
for closing them, that the `dhi-python:3.14-debian13` base advance to a build
carrying `linux-libc-dev` 6.12.96-1, has been met: the Container Security run on
[PR #494](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/494)
([run 30580773808](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/runs/30580773808))
reports the installed package as **6.12.96-1+dhi0**, up from the 6.12.95-1+dhi0
recorded at discovery. The Debian security tracker records both CVEs as `fixed`
in `trixie-security` 6.12.96-1, so the DHI rebuild of that version carries the
fix. Their `.trivyignore` entries have been removed accordingly.

One caveat recorded deliberately, because it affects how this was verified:
neither CVE appears in the PR #494 scan output, but that alone proves nothing,
since both were suppressed by `.trivyignore` at the time of that run and would
have been hidden whether fixed or not. The closure rests on the two facts above,
the installed version and Debian's `fixed` status for it, not on their absence
from the output. The next Container Security run after the suppressions are
removed will confirm it directly.

### Impact on This Project

Identical to the 34-CVE `linux-libc-dev` entry above: the package ships kernel
UAPI headers used at compile time, contains no kernel binary, and executes no
kernel code at runtime. The container serves a FastAPI web application under
whatever kernel the Docker host provides, not the kernel version recorded in
this package's metadata. Exposure through the application surface is negligible.

### Remediation Plan

- [x] **CVE-2026-53399, CVE-2026-64600 (tracked, fix exists): DONE 2026-07-30.**
  These were a tracked suppression, not a permanent dismissal, and the track has
  now closed. The base advanced to `linux-libc-dev` 6.12.96-1+dhi0, the version
  Debian records as fixing both, and their `.trivyignore` entries have been
  removed. See "Resolution of the 2 fixable CVEs" above.
- [ ] **The 6 no-fix CVEs:** monitor the
  [Debian security tracker](https://security-tracker.debian.org/tracker/source-package/linux)
  for the DHI mirror to rebuild against a newer kernel-headers snapshot; remove
  the entries once a fixed digest is published. Reassess by 2026-09-24.

### Why Not Fixed Yet

For the 6 no-fix CVEs: same reason as the 34-CVE block above; Debian has not
released a patched `linux-libc-dev` for the DHI mirror snapshot, and the base
image is not managed by this project's dependency set. These 6 remain open.

For the 2 fixable CVEs, this section is now historical: an upstream fix existed
(6.12.96-1) but had not propagated into the `dhi-python:3.14-debian13` digest
this project pinned, and the DHI runtime image ships no shell or package
manager, so the fix could only arrive via a base-image digest refresh from the
`ByronWilliamsCPA/container-images` mirror pipeline, which this project consumes
rather than controls. That refresh has since happened, which is exactly the
predicted path, and both CVEs are resolved.

### References

- [Aqua AVD CVE-2026-53399](https://avd.aquasec.com/nvd/cve-2026-53399) and [Aqua AVD CVE-2026-64600](https://avd.aquasec.com/nvd/cve-2026-64600) (the fixable pair; the 6 no-fix CVEs follow the same `avd.aquasec.com/nvd/<cve-id>` URL pattern)
- [Debian security tracker: linux](https://security-tracker.debian.org/tracker/source-package/linux)
- Discovered by the Container Security workflow (Trivy) on
  [PR #394](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/394)

---

## CVE-2026-64287 and 6 further kernel-header CVEs | linux-libc-dev | High

| Field | Value |
|-------|-------|
| **CVE ID** | CVE-2026-64287, CVE-2026-64364, CVE-2026-64375, CVE-2026-64434, CVE-2026-64534, CVE-2026-64552, CVE-2026-64558 (High, 7 CVEs, none with a fix on the trixie track) |
| **Package** | linux-libc-dev (Debian binary package from the `linux` kernel source package) |
| **Affected Version** | 6.12.96-1+dhi0 (Debian 13 "trixie", DHI mirror build) |
| **Fixed Version** | No fix available. Debian's tracker records `trixie` and `trixie-security` (6.12.96-1) as `vulnerable` for all seven; the fix landed only in `sid` (7.1.5-1), which this base image does not track |
| **Severity** | High (all 7, per Trivy/Aqua feed; `Total: 7 (HIGH: 7, CRITICAL: 0)`) |
| **CVSS Score** | Not yet assigned; the Debian tracker shows no CVSS for any of the seven as of 2026-07-30 |
| **Discovered** | 2026-07-30 |
| **Reassessment Due** | 2026-09-28 |
| **Blocking Release** | No |

### Description

Seven further kernel defects reported against `linux-libc-dev`'s tracked kernel
source version, newly surfaced after the 34-CVE and 8-CVE sets documented in the
two blocks above. Like those sets they span unrelated kernel subsystems: ARM64
KVM pKVM hyp vCPU flushing (CVE-2026-64287), HID multitouch out-of-bounds bit
access (CVE-2026-64364), `proc` `ptrace_may_access()` locking on FD links
(CVE-2026-64375), a Bluetooth L2CAP use-after-free in channel timeout
(CVE-2026-64434), an `nvmet-tcp` digest error path (CVE-2026-64534), a
`virtio-net` length check in `receive_big()` (CVE-2026-64552), and an s390 `pkey`
handler length check (CVE-2026-64558). All seven report an empty Fixed Version
with status `affected`. This is the same `linux-libc-dev` false-positive class as
the two blocks above: kernel UAPI headers, not a running kernel binary.

Note on the block above: the base image has since advanced from 6.12.95-1+dhi0
to 6.12.96-1+dhi0, so CVE-2026-53399 and CVE-2026-64600 (the "fix-available"
pair in the 8-CVE entry) no longer appear in the scan output. That entry's
fixable subset is closed by the same run that surfaced these seven; the run
reports these seven as the image's only remaining findings.

### Impact on This Project

Identical to the two `linux-libc-dev` entries above: the package ships kernel
UAPI headers used at compile time by userspace programs, contains no kernel
binary, and executes no kernel code at runtime. The container serves a FastAPI
web application under whatever kernel the Docker host provides, not the kernel
version recorded in this package's own metadata, so patching or removing this
package would change nothing about which kernel actually runs.

Not overstating the case: two of the seven name subsystems that plausibly exist
on a typical container host rather than exotic hardware, namely CVE-2026-64375
(`proc`/`ptrace`) and CVE-2026-64552 (`virtio-net`). Neither is reachable
*through this image or this package*; if the Docker host runs an affected
kernel, the remediation is host kernel patching, which is outside this
repository and unaffected by anything shipped in the image. The remaining five
(ARM64 pKVM, HID multitouch, Bluetooth L2CAP, `nvmet-tcp`, s390 `pkey`) address
hardware and subsystems this deployment does not use at all. Exposure through
the application surface is negligible.

### Remediation Plan

- [ ] Monitor the [Debian security tracker](https://security-tracker.debian.org/tracker/source-package/linux)
  for a trixie-track `linux-libc-dev` carrying these fixes, and for the DHI
  mirror to rebuild against that snapshot. As of 2026-07-30 the fix exists only
  in `sid` (7.1.5-1), so there is nothing for the mirror to pick up yet.
- [ ] Once a fixed digest is published, re-run the Container Security scan to
  confirm the seven have cleared, and remove any suppression added for them.
- [ ] Tracked in [issue #505](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/505)
- [ ] Reassess by 2026-09-28

### Why Not Fixed Yet

Same reason as the two blocks above, and confirmed independently rather than
assumed: Debian's tracker records both `trixie` (6.12.94-1) and
`trixie-security` (6.12.96-1) as `vulnerable` for all seven, with the fix
present only in `sid` (7.1.5-1). Trivy's empty Fixed Version column is therefore
accurate for the release track this base image follows, not a feed gap. The
package is provided by the hardened base image
(`ghcr.io/byronwilliamscpa/dhi-python:3.14-debian13`), not managed by this
project's dependency set, and the DHI runtime image ships no shell and no
package manager, so it cannot upgrade itself even once a fix exists upstream.
The only path in is a base-image digest refresh from the
`ByronWilliamsCPA/container-images` mirror pipeline, which this project consumes
rather than controls.

**Why `Blocking Release | No` on the evidence of 2026-07-30.** No fixed package
exists on the trixie track, so holding a release would not buy a remediation; it
would only stall delivery while the exposure stayed exactly where it is. The
exposure itself is a compile-time header set with no kernel code path in the
image, and the running kernel is the host's. Per the Release Gate Policy above
this is a dated verdict, not a standing exemption: it expires on 2026-09-28, at
which point the process gate closes the release until the entry is reassessed
against fresh evidence.

### References

- [Aqua AVD CVE-2026-64287](https://avd.aquasec.com/nvd/cve-2026-64287) (the remaining 6 CVEs follow the same `avd.aquasec.com/nvd/<cve-id>` URL pattern)
- [Debian security tracker: linux](https://security-tracker.debian.org/tracker/source-package/linux)
- [Debian security tracker: CVE-2026-64287](https://security-tracker.debian.org/tracker/CVE-2026-64287)
  (trixie and trixie-security both `vulnerable`; the other 6 follow the same
  `security-tracker.debian.org/tracker/<CVE-ID>` URL pattern and show the same status)
- Discovered by the Container Security workflow (Trivy) on
  [PR #494](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/494),
  [workflow run 30580773808](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/runs/30580773808)

## Resolved Entries

| CVE              | Package        | Resolved Date | Resolution                                             |
|------------------|----------------|---------------|--------------------------------------------------------|
| PYSEC-2022-42969 | py             | 2026-07-29    | Withdrawn upstream as disputed. See detail below.      |
| PYSEC-2026-89    | markdown       | 2026-07-29    | Not affected; 3.10.2 carries the 3.8.1 fix. See below. |
| CVE-2026-53399   | linux-libc-dev | 2026-07-30    | Fixed by base 6.12.96-1+dhi0. See entry above.         |
| CVE-2026-64600   | linux-libc-dev | 2026-07-30    | Fixed by base 6.12.96-1+dhi0. See entry above.         |

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
| 2026-MM-DD  | Byron Williams | Initial creation.                                                     |
| 2026-07-08  | Byron Williams | Added CVE-2026-53615 (libuuid1, runtime base image; no upstream fix). |
| 2026-07-14  | Byron Williams | Added gawk CVE-2026-40467/40468/40469/40553 (runtime base image; no upstream fix). |
| 2026-07-19  | Byron Williams | Added libexpat1/libexpat1-dev CVE-2025-59375/2026-25210/45186/56131/56407/56408 (runtime base image; no upstream fix; same mirror regression independently found via PR #296). |
| 2026-07-19  | Byron Williams | Added linux-libc-dev CVE-2026-43185 (Critical) plus 33 further kernel CVEs (runtime base image; kernel UAPI headers only, no running kernel code; no upstream fix). |
| 2026-07-24  | Byron Williams | Added 8 further linux-libc-dev kernel-header CVEs from PR #394 Trivy: 6 no-fix (53089/53109/53118/53330/63970/64017) plus 2 tracked-with-fix in 6.12.96-1 not yet in the dhi-python base (53399/64600). |
| 2026-07-29  | Byron Williams | Reassessed 2 overdue entries; resolved both; added gate ruling.       |
| 2026-07-30  | Byron Williams | Added 7 further linux-libc-dev kernel-header CVEs from the PR #494 Trivy run (64287/64364/64375/64434/64534/64552/64558); all High, none fixed on the trixie track (fix only in sid 7.1.5-1). Tracked in issue #505. Base advanced to 6.12.96-1+dhi0, which clears CVE-2026-53399/64600 from the prior entry. |
| 2026-07-30  | Byron Williams | Suppressed the 7 new CVEs in .trivyignore per that file's stated scope (base-image OS-package CVEs with no upstream fix, each paired with an entry here). Resolved CVE-2026-53399/64600: removed their .trivyignore block, whose own removal condition (base ships 6.12.96-1) is met; verified fixed in trixie-security 6.12.96-1 on the Debian tracker rather than inferred from scan absence, which suppression would have masked. |
