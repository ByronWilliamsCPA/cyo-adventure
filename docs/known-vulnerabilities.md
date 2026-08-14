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

## CVE-2026-63879, CVE-2026-64530, CVE-2026-64531 | linux-libc-dev | High

| Field | Value |
|-------|-------|
| **CVE ID** | CVE-2026-63879 (no fix on the trixie track), CVE-2026-64530 and CVE-2026-64531 (**both RESOLVED 2026-08-02**) |
| **Package** | linux-libc-dev (Debian binary package from the `linux` kernel source package) |
| **Affected Version** | 6.12.96-1+dhi0 at discovery; base advanced to 6.12.100-1+dhi0 on 2026-08-02 via PR #547 (Debian 13 "trixie", DHI mirror build) |
| **Fixed Version** | Mixed, and this is the first `linux-libc-dev` entry here that is not uniformly "no fix". CVE-2026-64530 and CVE-2026-64531 are fixed in 6.12.100-1 (Debian tracker: `trixie-security` = `fixed`, DSA-6405-1) and no longer appear in scan output. CVE-2026-63879 has no fix on this track: `trixie` (6.12.94-1) and `trixie-security` (6.12.100-1) both record `vulnerable`; the fix is sid-only (7.0.12-1) |
| **Severity** | High (all 3, per Trivy/Aqua feed). At discovery `Total: 3 (HIGH: 3, CRITICAL: 0)`; as of 2026-08-02 `Total: 1 (HIGH: 1, CRITICAL: 0)` |
| **CVSS Score** | Not yet assigned in the scan output for any of the three as of 2026-08-02 |
| **Discovered** | 2026-08-01 |
| **Reassessment Due** | 2026-09-30 |
| **Blocking Release** | No |

### Description

Three kernel defects reported against `linux-libc-dev`'s tracked kernel source
version, surfaced by a Trivy vulnerability-database refresh on 2026-08-01. They
span unrelated subsystems: an AMD GPU DRM fix in `amdgpu_hmm_range_get_pages`
(CVE-2026-63879), a use-after-free in the network scheduler via a missing
handler (CVE-2026-64530), and an Open vSwitch oversized-nested-action rejection
(CVE-2026-64531).

This entry supersedes rather than extends the seven-CVE block above: the same
run that surfaced these three reports them as the image's only remaining
findings, so that block's seven no longer appear in scan output. The base-image
version is unchanged at 6.12.96-1+dhi0, so the turnover is a feed change, not an
image change.

**What is different about this set.** Every prior `linux-libc-dev` entry in this
document recorded "No fix available" for every CVE in it. Two of these three
carry a Fixed Version. That makes this set partly actionable rather than purely
a wait-for-upstream case: a base-image digest refresh onto a kernel-header build
at or above 6.12.100-1 clears CVE-2026-64530 and CVE-2026-64531 outright.

### Impact on This Project

The same structural argument as the three `linux-libc-dev` entries above, which
is a statement about what the package *is* rather than a judgement about
severity: it ships kernel UAPI headers used at compile time by userspace
programs, contains no kernel binary, and executes no kernel code at runtime. The
container serves a FastAPI web application under whatever kernel the Docker host
provides. Patching or removing this package would not change which kernel
actually runs.

Not overstating the case: two of the three name networking subsystems that can
plausibly exist on a container host rather than exotic hardware, namely
CVE-2026-64530 (`net/sched`) and CVE-2026-64531 (`net/openvswitch`), though
Docker's default bridge networking does not use Open vSwitch. Neither is
reachable *through this image or this package*; if the Docker host runs an
affected kernel, the remediation is host kernel patching, which is outside this
repository and unaffected by anything shipped in the image. CVE-2026-63879
targets AMD GPU hardware this deployment does not use at all. Exposure through
the application surface is negligible.

### Status update (2026-08-02): two of three resolved

The base image advanced from 6.12.96-1+dhi0 to 6.12.100-1+dhi0 in
[PR #547](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/547), a Renovate
digest bump of `ghcr.io/byronwilliamscpa/dhi-python:3.14-debian13`. That is exactly the
action this entry's remediation plan called for, and it arrived on its own rather than
by request, so the plan is recorded as satisfied rather than executed.

**Measured effect**, comparing the Container Security run on `main` at `ea3970c8`
against the run on PR #547 (workflow run 30733734393):

| Scan                 | linux-libc-dev  | Trivy result                      |
|----------------------|-----------------|-----------------------------------|
| `main` @ `ea3970c8`  | 6.12.96-1+dhi0  | `Total: 3 (HIGH: 3, CRITICAL: 0)` |
| PR #547 @ `c296e63c` | 6.12.100-1+dhi0 | `Total: 1 (HIGH: 1, CRITICAL: 0)` |

CVE-2026-64530 and CVE-2026-64531 cleared outright and are recorded in
[Resolved Entries](#resolved-entries). CVE-2026-63879 remains, reported with an empty
Fixed Version and status `affected`, and is now carried in `.trivyignore` under its own
`6.12.100-1+dhi0` block.

**Independent Debian verification** (2026-08-02), which this entry previously flagged as
the outstanding gap in its evidence base:

| CVE            | `trixie`               | `trixie-security`                  | sid              |
|----------------|------------------------|------------------------------------|------------------|
| CVE-2026-63879 | vulnerable (6.12.94-1) | **vulnerable** (6.12.100-1)        | fixed (7.0.12-1) |
| CVE-2026-64530 | vulnerable (6.12.94-1) | **fixed** (6.12.100-1, DSA-6405-1) | fixed (7.1.5-1)  |
| CVE-2026-64531 | vulnerable (6.12.94-1) | **fixed** (6.12.100-1, DSA-6405-1) | fixed (7.1.5-1)  |

This closes the caveat recorded under "Why Not Fixed Yet" below: 6.12.100-1 was in fact
reachable on this release track, via `trixie-security` rather than `trixie`. It also
establishes that CVE-2026-63879's fix is sid-only and therefore genuinely unreachable
for this base image, which is the condition the `.trivyignore` policy requires before an
entry may be accepted there.

### Remediation Plan

- [x] Confirm each CVE's status on the [Debian security tracker](https://security-tracker.debian.org/tracker/source-package/linux)
  for the `trixie` and `trixie-security` tracks. **Done 2026-08-02**; results in the
  status update above. The Trivy feed's Fixed Version was corroborated for
  CVE-2026-64530 and CVE-2026-64531 and refined for CVE-2026-63879, whose fix exists
  only in sid.
- [x] Once `linux-libc-dev >= 6.12.100-1` reaches the trixie track, request a
  base-image digest refresh from the `ByronWilliamsCPA/container-images` mirror
  pipeline. **Satisfied 2026-08-02** by the Renovate digest bump in PR #547; no manual
  request was needed.
- [x] Re-run the Container Security scan to confirm CVE-2026-64530 and
  CVE-2026-64531 have cleared. **Confirmed 2026-08-02**, workflow run 30733734393.
- [ ] Close [issue #505](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/505)
  if its seven CVEs remain absent from scan output. The condition is now met (the
  2026-08-02 run's only finding is CVE-2026-63879), but the issue is still open; closing
  it is a follow-up.
- [ ] Narrow [issue #535](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/535)
  to CVE-2026-63879 only, now that the other two are resolved.
- [ ] Reassess CVE-2026-63879 by 2026-09-30, checking whether the sid fix (7.0.12-1) has
  been backported to `trixie-security`.

### Why Not Fixed Yet

For CVE-2026-63879, Trivy reports no fix. For the other two a fix exists
upstream, but the package is provided by the hardened base image
(`ghcr.io/byronwilliamscpa/dhi-python:3.14-debian13`), not managed by this
project's dependency set, and the DHI runtime image ships no shell and no
package manager, so it cannot upgrade itself. The only path in is a base-image
digest refresh from the `ByronWilliamsCPA/container-images` mirror pipeline,
which this project consumes rather than controls, and which in turn depends on
the trixie track carrying 6.12.100-1.

**Why `Blocking Release | No` on the evidence of 2026-08-01.** The exposure is a
compile-time header set with no kernel code path in the image, and the running
kernel is the host's, so holding a release would not reduce exposure; it would
only stall delivery. This verdict rests on a narrower evidence base than the
entries above, which is recorded here rather than glossed: the Debian tracker
was not consulted, so whether 6.12.100-1 is actually reachable on the trixie
track is unconfirmed. That does not change the reachability argument, which does
not depend on fix availability, but it is the first thing to check at
reassessment. Per the Release Gate Policy above this is a dated verdict, not a
standing exemption: it expires on 2026-09-30, at which point the process gate
closes the release until the entry is reassessed against fresh evidence.

### References

- [Aqua AVD CVE-2026-63879](https://avd.aquasec.com/nvd/cve-2026-63879)
  (the other 2 follow the same `avd.aquasec.com/nvd/<cve-id>` URL pattern)
- [Debian security tracker: linux](https://security-tracker.debian.org/tracker/source-package/linux)
- Discovered by the Container Security workflow (Trivy) on
  [PR #529](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/529),
  [workflow run 30711029139](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/runs/30711029139).
  The immediately preceding run on `main` (16:33 UTC, same day) passed, and the
  branch changes no dependency, lockfile, or Dockerfile, which is what
  identifies this as a feed refresh rather than a change introduced by that PR.

## CVE-2026-64561 | linux-libc-dev | High

| Field | Value |
|-------|-------|
| **CVE ID** | CVE-2026-64561 |
| **Package** | linux-libc-dev (Debian binary package from the `linux` kernel source package) |
| **Affected Version** | 6.12.100-1+dhi0 (Debian 13 "trixie", DHI mirror build) |
| **Fixed Version** | No fix on the trixie track. Trivy reports an empty Fixed Version with status `affected`; the Debian tracker records `trixie` (6.12.94-1) and `trixie-security` (6.12.100-1) as `vulnerable`, with the fix only in sid (7.1.6-1) |
| **Severity** | High (per Trivy/Aqua feed) |
| **CVSS Score** | Not assigned in the scan output as of 2026-08-04 |
| **Discovered** | 2026-08-04 |
| **Reassessment Due** | 2026-09-30 |
| **Blocking Release** | No |

### Description

A KVM defect in the x86 MMU: the root-validity check for an invalid or obsolete
root runs *before* pages are made available rather than after, per the CVE
title reported in the scan output ("KVM: x86: Check for invalid/obsolete root
*after* making MMU pages available"). It reached this image the same way the
entries above did, through a Trivy vulnerability-database refresh rather than
any change in the image: the base image version is unchanged at
6.12.100-1+dhi0, the same build PR #547 introduced on 2026-08-02.

**Why this is a feed refresh and not a regression introduced by PR #597.** The
Container Security run on `main` at 2026-08-04T17:28:49Z passed with no
findings. The run on the PR branch roughly three and a half hours later
reported `Total: 1 (HIGH: 1, CRITICAL: 0)`. The branch changes no dependency,
no lockfile, and no Dockerfile, so the same finding will appear on `main` at its
next scheduled scan. This is the same discrimination test applied to the
CVE-2026-63879 entry above.

### Impact on This Project

The same structural argument as every `linux-libc-dev` entry in this document,
which is a statement about what the package *is* rather than a judgement about
severity: it ships kernel UAPI headers used at compile time by userspace
programs, contains no kernel binary, and executes no kernel code at runtime. The
container serves a FastAPI web application under whatever kernel the Docker host
provides. Patching or removing this package would not change which kernel
actually runs.

Being specific rather than waving at the general rule: this defect is in KVM's
shadow-paging MMU, code that only executes when the host is running virtual
machines through `/dev/kvm`. This deployment runs application containers on a
homelab Docker host; the image neither contains a hypervisor nor requests KVM
device access. Exploitation requires the ability to drive KVM ioctls from a
process on the host, which is a host-privilege boundary this container does not
sit on either side of. Exposure through the application surface is nil.

### Remediation Plan

- [x] Confirm the CVE's status on the [Debian security tracker](https://security-tracker.debian.org/tracker/source-package/linux)
  for the `trixie` and `trixie-security` tracks before accepting it into
  `.trivyignore`. **Done 2026-08-04**: `bookworm` (6.1.176-1) vulnerable,
  `bookworm-security` (6.1.180-1) vulnerable, `trixie` (6.12.94-1) vulnerable,
  `trixie-security` (6.12.100-1) vulnerable, `sid` (7.1.6-1) fixed. This
  satisfies the `.trivyignore` precondition that no fix be reachable on this
  base image's track.
- [ ] Reassess by 2026-09-30, checking whether the sid fix (7.1.6-1) has been
  backported to `trixie-security`. Deliberately aligned with the
  CVE-2026-63879 date above so one review pass covers both of this image's
  open kernel-header findings, and comfortably inside the 60-day ceiling from
  the 2026-08-04 discovery.
- [ ] Fold into [issue #535](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/535)
  at reassessment, which already tracks the open `linux-libc-dev` set.

### Why Not Fixed Yet

No fix exists on the trixie track, confirmed above rather than inferred from
Trivy's empty Fixed Version field. Even once one lands, this project cannot
apply it directly: the package is provided by the hardened base image
(`ghcr.io/byronwilliamscpa/dhi-python:3.14-debian13`), not by this project's
dependency set, and the DHI runtime image ships no shell and no package manager,
so it cannot upgrade itself. The only path in is a base-image digest refresh
from the `ByronWilliamsCPA/container-images` mirror pipeline, which this project
consumes rather than controls.

Per the Release Gate Policy above, `Blocking Release | No` here is a dated
verdict, not a standing exemption: it expires on 2026-09-30, at which point the
process gate closes the release until the entry is reassessed against fresh
evidence.

### References

- [Aqua AVD CVE-2026-64561](https://avd.aquasec.com/nvd/cve-2026-64561)
- [Debian security tracker: linux](https://security-tracker.debian.org/tracker/source-package/linux)
- Discovered by the Container Security workflow (Trivy) on
  [PR #597](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/597),
  [workflow run 30950314291](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/runs/30950314291).

## CVE-2026-68480 | linux-libc-dev | High

| Field | Value |
|-------|-------|
| **CVE ID** | CVE-2026-68480 (AMD-SN-7061) |
| **Package** | linux-libc-dev (Debian binary package from the `linux` kernel source package) |
| **Affected Version** | 6.12.100-1+dhi0 (Debian 13 "trixie", DHI mirror build) |
| **Fixed Version** | No fix on the trixie track. Trivy reports an empty Fixed Version with status `affected`; the Debian tracker records `trixie` (6.12.94-1) and `trixie-security` (6.12.101-1) as `vulnerable`, with the fix only in sid (7.1.7-1) |
| **Severity** | High (per Trivy/Aqua feed) |
| **CVSS Score** | Not assigned in the scan output as of 2026-08-08 |
| **Discovered** | 2026-08-08 |
| **Reassessment Due** | 2026-09-30 |
| **Blocking Release** | No |

### Description

A defect in the x86 Safe-RET mitigation for SRSO (Speculative Return Stack
Overflow) on affected AMD parts, reported by Trivy as "kernel: AMD-SN-7061: Safe
RET Interrupt Vulnerability". Per the upstream commit message, an attacker who
injects interrupts while the Safe-RET sequence is executing can neutralize that
sequence, potentially leaking data through speculative execution; the fix
emulates the sequence's register state on return from the interrupt so no `RET`
is executed afterwards.

**Why this is a feed refresh and not a regression introduced by PR #644.** The
base-image digest is pinned and byte-identical on `main` and the PR head
(`sha256:f4a77e21...`), and `linux-libc-dev` is unchanged at 6.12.100-1+dhi0,
the build PR #547 introduced on 2026-08-02. The most recent run that actually
executed this job, run 30973596262 on 2026-08-05, was clean. PR #644 changes
three lockfiles and no Dockerfile, and neither package it bumps (`gitpython`,
`nanoid`) appears anywhere in the scan output; `nanoid` is a frontend
dependency that is not in this image at all. The same finding will therefore
appear on any branch whose Container Security run executes.

One caution specific to this repository, recorded so the next reassessment does
not misread it: `main`'s tip shows this job as `skipped`, because
`container-security.yml` skips on `chore(release):` tips. A green `main` is not
evidence that the finding is absent there, which is why the discrimination test
above rests on the last *executing* run rather than on main's check status.

### Impact on This Project

The same structural argument as every `linux-libc-dev` entry in this document,
which is a statement about what the package *is* rather than a judgement about
severity: it ships kernel UAPI headers used at compile time by userspace
programs, contains no kernel binary, and executes no kernel code at runtime. The
container serves a FastAPI web application under whatever kernel the Docker host
provides. Patching or removing this package would not change which kernel
actually runs, nor which CPU mitigations that kernel applies.

Being specific rather than waving at the general rule: this defect lives in the
kernel's CPU-mitigation path for a speculative-execution side channel. Whether
Safe-RET is robust is decided entirely by the host kernel and the host CPU, on
the far side of a boundary this container does not sit on either side of.
Exploitation additionally requires the ability to inject interrupts during the
mitigation sequence, a host-privilege primitive that no request reaching this
FastAPI application can reach. Exposure through the application surface is nil.

### Remediation Plan

- [x] Confirm the CVE's status on the [Debian security tracker](https://security-tracker.debian.org/tracker/CVE-2026-68480)
  for the `trixie` and `trixie-security` tracks before accepting it into
  `.trivyignore`. **Done 2026-08-08**: `bullseye` (5.10.223-1) vulnerable,
  `bullseye-security` (5.10.262-1) vulnerable, `bookworm` (6.1.176-1)
  vulnerable, `bookworm-security` (6.1.180-1) vulnerable, `trixie` (6.12.94-1)
  vulnerable, `trixie-security` (6.12.101-1) vulnerable, `forky` (7.1.6-1)
  vulnerable, `sid` (7.1.7-1) fixed. This satisfies the `.trivyignore`
  precondition that no fix be reachable on this base image's track.
- [x] Confirm no newer base-image digest is available to bump to instead of
  accepting the CVE. **Done 2026-08-08**: the live GHCR manifest digest for
  `ghcr.io/byronwilliamscpa/dhi-python:3.14-debian13` is
  `sha256:f4a77e21fb25b71ccb183a25a53a1e87db2a3c11b422941b25708c2b5f3b1b13`,
  identical to the digest already pinned in the Dockerfile. The tag has not
  moved, so a re-pin is not an available remedy.
- [ ] Reassess by 2026-09-30, checking whether the sid fix (7.1.7-1) has been
  backported to `trixie-security`. Deliberately aligned with the CVE-2026-63879
  and CVE-2026-64561 dates above so one review pass covers all of this image's
  open kernel-header findings, and inside the 60-day ceiling from the 2026-08-08
  discovery.
- [ ] Fold into [issue #535](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/535)
  at reassessment, which already tracks the open `linux-libc-dev` set.

### Why Not Fixed Yet

No fix exists on the trixie track, confirmed above rather than inferred from
Trivy's empty Fixed Version field. Even once one lands, this project cannot
apply it directly: the package is provided by the hardened base image
(`ghcr.io/byronwilliamscpa/dhi-python:3.14-debian13`), not by this project's
dependency set, and the DHI runtime image ships no shell and no package manager,
so it cannot upgrade itself. The runtime stage runs no `apt-get install`, so the
package cannot be dropped from this repository either. The only path in is a
base-image digest refresh from the `ByronWilliamsCPA/container-images` mirror
pipeline, which this project consumes rather than controls, and which the digest
check above confirms has not yet published one.

Per the Release Gate Policy above, `Blocking Release | No` here is a dated
verdict, not a standing exemption: it expires on 2026-09-30, at which point the
process gate closes the release until the entry is reassessed against fresh
evidence.

### References

- [Aqua AVD CVE-2026-68480](https://avd.aquasec.com/nvd/cve-2026-68480)
- [Debian security tracker: CVE-2026-68480](https://security-tracker.debian.org/tracker/CVE-2026-68480)
- Discovered by the Container Security workflow (Trivy) on
  [PR #644](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/644),
  [workflow run 31262431949](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/runs/31262431949).

## CVE-2026-64283 and 8 further kernel-header CVEs | linux-libc-dev | High

| Field | Value |
|-------|-------|
| **CVE ID** | CVE-2026-64283, CVE-2026-68159, CVE-2026-68166, CVE-2026-68198, CVE-2026-68264, CVE-2026-68291, CVE-2026-68337, CVE-2026-68409, CVE-2026-68426 (High, 9 CVEs, none reporting a fix) |
| **Package** | linux-libc-dev (Debian binary package from the `linux` kernel source package) |
| **Affected Version** | 6.12.101-1+dhi0 (Debian 13 "trixie" 13.6, DHI mirror build), at base digest `sha256:5bbd41aef3ca86147ef389f3f0d944aa89bbae0d6c3ee31417e7bed15342aadf` |
| **Fixed Version** | None on the trixie track. Empty for all nine in the Trivy report, status `affected`; corroborated on the Debian tracker 2026-08-14, which records source package `linux` vulnerable in both `trixie` (6.12.94-1) and `trixie-security` (6.12.101-1) for all nine, fixed only in `sid` (7.1.8-1), which this base image does not track |
| **Severity** | High (all 9, per the Trivy/Aqua feed; the report summary shows 9 vulnerabilities for target `cyo_adventure:scan (debian 13.6)`) |
| **CVSS Score** | Not catalogued, consistent with every prior `linux-libc-dev` entry in this file: the applicability question is answered by reachability (kernel UAPI headers, no running kernel code), not by score |
| **Discovered** | 2026-08-14 |
| **Reassessment Due** | 2026-09-30 (aligned with CVE-2026-63879, CVE-2026-64561 and CVE-2026-68480) |
| **Blocking Release** | No |

### Description

Nine further kernel defects reported against `linux-libc-dev`'s tracked kernel source
version, newly surfaced after the sets documented in the blocks above. Like those sets
they span unrelated kernel subsystems: KVM `guest_memfd` memslot binding offset/size
handling (CVE-2026-64283), a libceph stack out-of-bounds write (CVE-2026-68159),
arbitrary code execution (CVE-2026-68166), a use-after-free in the ath6kl Wi-Fi driver
(CVE-2026-68198), a `drm/xe/pt` `current_op` reset (CVE-2026-68264), an idpf driver
null-pointer dereference (CVE-2026-68291), a denial of service in BPF redirect
(CVE-2026-68337), a use-after-free in mac80211 (CVE-2026-68409), and a stale
`skb->prev` after async crypto in xfrm (CVE-2026-68426).

None of the nine appears in `.trivyignore`, which is how they surfaced: the 69 CVEs
already listed there were correctly suppressed in the same run, so the ignore
mechanism is working and these are genuinely new to the feed.

### This is a feed refresh, not a PR regression

Established the same way the 2026-08-04 and 2026-08-08 entries were, and recorded here
because a reader's first question is whether PR #709 caused it:

- **PR #709 touches no container input.** Its file list matches no `Dockerfile`,
  `docker-compose*`, or `.dockerignore`.
- **The base digest is unchanged.** The last commit to touch `Dockerfile` is `bb89468`
  (2026-08-11, "bump dhi-python runtime digest to clear CVE-2026-64564").
- **The same base commit passed.** PR #709's base is `20e26221` (v0.78.2), whose own
  Container Security run succeeded on 2026-08-13T00:05, roughly 25 hours earlier.
- **Every Python package scanned reports 0 vulnerabilities.** The only findings in the
  whole image are these nine OS-package CVEs.

The scheduled run on 2026-08-12T08:08 had also already failed on `main`, so this class
of failure predates the PR independently.

One correction this run produced: the base has advanced past what the 2026-08-08 entry
records. That entry pins digest `sha256:f4a77e21...` with `linux-libc-dev`
6.12.100-1+dhi0; the Dockerfile now pins `sha256:5bbd41ae...` and Trivy reports
6.12.101-1+dhi0.

### Impact on This Project

The rationale is identical to every `linux-libc-dev` entry above, and is now the
finding rather than the expectation: the package ships kernel UAPI headers used at
compile time, contains no kernel binary, and executes no kernel code at runtime. The
container serves a FastAPI web application under whatever kernel the Docker host
provides, not the kernel version recorded in this package's metadata. Exposure through
the application surface is negligible, and the listed subsystems (Wi-Fi drivers, DRM,
KVM, network offload) are not reachable from this workload at all.

What the tracker check changed is the remedy, not the impact. Because all nine are
vulnerable in `trixie-security` and fixed only in `sid`, a base-image digest refresh on
the trixie track would ship the same nine, so suppression is the only available action
rather than the convenient one.

### Remediation Plan

- [x] **Corroborated all nine on the Debian security tracker** on 2026-08-14, each CVE
      fetched individually. All nine record source package `linux` as vulnerable in
      `trixie` (6.12.94-1) and `trixie-security` (6.12.101-1), and fixed only in `sid`
      (7.1.8-1). Closes item 1 of issue [#711](https://github.com/ByronWilliamsCPA/cyo-adventure/issues/711).
- [x] **Confirmed the pinned GHCR digest is still live** on 2026-08-14: the manifest for
      `sha256:5bbd41ae...` resolves (HTTP 200). The `3.14-debian13` tag itself did not
      resolve from that session, so whether a newer digest exists is unconfirmed; it does
      not change the outcome, because the tracker rules out any trixie-track digest
      carrying a fix.
- [x] **Confirmed unfixed, so suppressed:** the nine were added to `.trivyignore` in the
      format of the CVE-2026-68480 block, this entry left draft, the reassessment date
      set, and a Review History row added.
- [x] **No fix exists on the trixie track**, so the base-image digest refresh branch does
      not apply. A refresh from the `ByronWilliamsCPA/container-images` mirror pipeline
      (as `bb89468` did for CVE-2026-64564) would ship the same nine.

### Why Not Fixed Yet

It follows the established pattern exactly. Debian has not released a patched
`linux-libc-dev` on the trixie track: `trixie-security` still ships 6.12.101-1 and
records all nine as vulnerable, with the fix landing only in `sid` (7.1.8-1), which this
base image does not track. Because the DHI runtime image ships no shell or package
manager, a fix could only arrive through a base-image digest refresh from a mirror
pipeline this project consumes rather than controls, and no such refresh can help while
the trixie track itself carries the defects.

### References

- [CVE-2026-64283](https://security-tracker.debian.org/tracker/CVE-2026-64283) ([Aqua AVD](https://avd.aquasec.com/nvd/cve-2026-64283))
- [CVE-2026-68159](https://security-tracker.debian.org/tracker/CVE-2026-68159) ([Aqua AVD](https://avd.aquasec.com/nvd/cve-2026-68159))
- [CVE-2026-68166](https://security-tracker.debian.org/tracker/CVE-2026-68166) ([Aqua AVD](https://avd.aquasec.com/nvd/cve-2026-68166))
- [CVE-2026-68198](https://security-tracker.debian.org/tracker/CVE-2026-68198) ([Aqua AVD](https://avd.aquasec.com/nvd/cve-2026-68198))
- [CVE-2026-68264](https://security-tracker.debian.org/tracker/CVE-2026-68264) ([Aqua AVD](https://avd.aquasec.com/nvd/cve-2026-68264))
- [CVE-2026-68291](https://security-tracker.debian.org/tracker/CVE-2026-68291) ([Aqua AVD](https://avd.aquasec.com/nvd/cve-2026-68291))
- [CVE-2026-68337](https://security-tracker.debian.org/tracker/CVE-2026-68337) ([Aqua AVD](https://avd.aquasec.com/nvd/cve-2026-68337))
- [CVE-2026-68409](https://security-tracker.debian.org/tracker/CVE-2026-68409) ([Aqua AVD](https://avd.aquasec.com/nvd/cve-2026-68409))
- [CVE-2026-68426](https://security-tracker.debian.org/tracker/CVE-2026-68426) ([Aqua AVD](https://avd.aquasec.com/nvd/cve-2026-68426))
- [Debian security tracker: linux](https://security-tracker.debian.org/tracker/source-package/linux)
- Discovered by the Container Security workflow (Trivy v0.70.0) on
  [PR #709](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/709),
  [workflow run 31760080363](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/runs/31760080363).

## Resolved Entries

| CVE              | Package        | Resolved Date | Resolution                                             |
|------------------|----------------|---------------|--------------------------------------------------------|
| PYSEC-2022-42969 | py             | 2026-07-29    | Withdrawn upstream as disputed. See detail below.      |
| PYSEC-2026-89    | markdown       | 2026-07-29    | Not affected; 3.10.2 carries the 3.8.1 fix. See below. |
| CVE-2026-53399   | linux-libc-dev | 2026-07-30    | Fixed by base 6.12.96-1+dhi0. See entry above.         |
| CVE-2026-64600   | linux-libc-dev | 2026-07-30    | Fixed by base 6.12.96-1+dhi0. See entry above.         |
| CVE-2026-64530   | linux-libc-dev | 2026-08-02    | Fixed by base 6.12.100-1+dhi0 (DSA-6405-1). See above. |
| CVE-2026-64531   | linux-libc-dev | 2026-08-02    | Fixed by base 6.12.100-1+dhi0 (DSA-6405-1). See above. |

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
| 2026-08-04  | Byron Williams | Added linux-libc-dev CVE-2026-64561 (KVM x86 MMU) from the PR #597 Trivy run; High, empty Fixed Version, base version unchanged at 6.12.100-1+dhi0, so a feed refresh rather than an image change (main's run 3.5h earlier was clean). Verified on the Debian tracker before accepting into .trivyignore: trixie and trixie-security both vulnerable at 6.12.100-1, fix is sid-only (7.1.6-1). Reassessment aligned to 2026-09-30 with CVE-2026-63879. |
| 2026-08-08  | Byron Williams | Added linux-libc-dev CVE-2026-68480 (x86 SRSO Safe-RET) from the PR #644 Trivy run (run 31262431949); High, empty Fixed Version, and the run's only finding. Established it as a feed refresh rather than a PR regression by pinned-digest identity across main and head plus the last executing run (30973596262, 2026-08-05) being clean, since main's own tip shows the job `skipped` and proves nothing either way. Verified on the Debian tracker before accepting into .trivyignore: trixie (6.12.94-1) and trixie-security (6.12.101-1) both vulnerable, fix is sid-only (7.1.7-1). Confirmed the pinned GHCR digest is still the live one, so a base-image re-pin was not an available remedy. Reassessment aligned to 2026-09-30 with CVE-2026-63879 and CVE-2026-64561. |
| 2026-08-14  | Byron Williams | Added linux-libc-dev CVE-2026-64283/68159/68166/68198/68264/68291/68337/68409/68426 from the PR #709 Container Security run (run 31760080363); all High, empty Fixed Version, status `affected`, base advanced to 6.12.101-1+dhi0 at digest `sha256:5bbd41ae...`. Established as a feed refresh rather than a PR regression: no container file in the diff, Dockerfile untouched since `bb89468`, base commit `20e26221` green 2026-08-13T00:05, the scheduled 2026-08-12 run already red on main, and 0 findings across every Python package. Verified on the Debian tracker before accepting into `.trivyignore`, each CVE fetched individually: all nine vulnerable in trixie (6.12.94-1) and trixie-security (6.12.101-1), fix is sid-only (7.1.8-1), which rules out a base-image re-pin as an alternative remedy. Confirmed the pinned GHCR digest still resolves (HTTP 200); the `3.14-debian13` tag did not resolve from that session, noted as unconfirmed rather than assumed. Reassessment aligned to 2026-09-30 with CVE-2026-63879, CVE-2026-64561 and CVE-2026-68480. Closes item 1 of issue #711. |
