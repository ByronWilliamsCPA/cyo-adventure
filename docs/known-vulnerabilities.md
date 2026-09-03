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
| **Last Reassessed** | 2026-09-03 |
| **Reassessment Due** | 2026-09-17 |
| **Blocking Release** | No |

### Description

A denial-of-service defect in Expat through 2.8.3. It is the seventh Expat CVE
this project tracked and the only one still open; the other six were fixed in
`expat 2.8.2-1~deb13u1` (DSA-6404-1) and now sit under "Resolution detail: the
six Expat CVEs, `gawk` and `perl-base`" in Resolved Entries. It entered the feed
between two scheduled scans: the 2026-08-26 run reported 35 findings and did not mention it,
the 2026-09-02 run reports it against both `libexpat1` and `libexpat1-dev`.
Like the other six it requires processing attacker-controlled XML through Expat.

### Impact on This Project

Accepted on the same reasoning that covered the six now-resolved Expat CVEs.
`libexpat1`/`libexpat1-dev` ship in the production runtime base
image; the application does not call into Expat (no `xml.parsers.expat` usage
in this codebase) and parses no untrusted XML on any request path, because the
API speaks JSON only. Exposure through the application surface is negligible.

### Remediation Plan

- [ ] Monitor the [Debian security tracker](https://security-tracker.debian.org/tracker/source-package/expat)
  for a fixed `expat` package that flows into the next DHI mirror rebuild
- [ ] Once a fixed digest is published, remove this suppression and re-run the
  Container Security scan to confirm the finding is gone
- [ ] Reassess by 2026-09-17

### Why Not Fixed Yet

Debian has not released a patched `expat` build for the DHI mirror's Debian 13
snapshot. Checked directly on 2026-09-02 against both the previously pinned base
digest (`sha256:5bbd41ae`) and the digest now on `main` (`sha256:d66d6403`):
Trivy reports status `affected` with an empty Fixed Version on both, so the
digest refresh that cleared the other 42 CVEs in that round does not clear this
one. Re-confirmed on 2026-09-03 by reading the shipped package version out of
the pinned digest rather than trusting a scan verdict: `libexpat1` is at 2.8.3,
inside the affected range. The package comes from the hardened base image, which ships
no shell and no package manager, so there is no project-side upgrade path.

### References

- [Debian security tracker: CVE-2026-66046](https://security-tracker.debian.org/tracker/CVE-2026-66046), the
  authoritative source for the `affected`, no-fix-available status this
  entry records
- [Debian security tracker: expat](https://security-tracker.debian.org/tracker/source-package/expat)
- [CVE record CVE-2026-66046](https://www.cve.org/CVERecord?id=CVE-2026-66046)
- Aqua AVD has no page for this CVE yet, so the sibling entries'
  `avd.aquasec.com/nvd/<cve-id>` link is deliberately omitted here rather
  than added dead. Re-add it once AVD publishes; do not restore it blind,
  the link check treats a 404 as a build failure.
- Discovered by the Container Security workflow (Trivy) on
  [run 33601842565](https://github.com/ByronWilliamsCPA/cyo-adventure/actions/runs/33601842565)

---

## CVE-2026-11822, CVE-2026-11824 | libsqlite3-0 | High

| Field | Value |
|-------|-------|
| **CVE ID** | CVE-2026-11822, CVE-2026-11824 |
| **Package** | libsqlite3-0 (Debian binary package from the `sqlite3` source package) |
| **Affected Version** | 3.46.1-7+deb13u1+dhi2, as shipped by the pinned base image (SQLite before 3.53.2) |
| **Fixed Version** | No fix available on the trixie track; both recorded `affected` (re-verified on the Debian tracker 2026-09-03) |
| **Severity** | **High (both), as of the 2026-09-03 reassessment.** Recorded Medium on 2026-08-17; the Trivy/Aqua feed has since raised both |
| **CVSS Score** | Not carried in the advisory records consulted |
| **Discovered** | 2026-08-10 |
| **Last Reassessed** | 2026-09-03 |
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

**These two suppressions are live, and the note that said otherwise was wrong
by 2026-09-03.** From 2026-08-17 this entry read "these two suppressions are
currently inert", on the reasoning that both CVEs were Medium while the
Container Security workflow is called with `severity-threshold: CRITICAL,HIGH`.
That was true when written. It is not true now: Trivy 0.70.0's current feed
rates both **High**, so they are inside the threshold, they are reported, and
these two entries are the only thing keeping the scan green over them.

The correction is worth stating rather than quietly editing, because the
original reasoning was sound and still produced a stale claim. A severity is a
feed value that moves; an entry that argues from one needs a date attached and a
re-read at reassessment, which is what caught it. Keeping the entry "in case the
threshold widens" turned out to be the right call for the wrong reason: what
widened was the severity, not the threshold.

Two further `libsqlite3-0` CVEs appeared in the same feed and are **not**
accepted here: CVE-2026-50812 and CVE-2026-50813, both Medium, both with no
Debian fix. They stay below the scan threshold and are recorded only so a future
reader knows they were seen rather than missed.

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

**Provenance of this assessment (updated 2026-09-03).** Fix status was
originally read from Trivy's own Debian advisory records, which is the same data
source the Container Security workflow scans against and therefore not
independent corroboration; the entry recorded that gap honestly and left a
Debian-tracker check outstanding, because that host was unreachable from this
project's cloud sessions (issue #711, item 1).

**That check has now been done.** `security-tracker.debian.org` is reachable
again, and both CVEs were fetched individually on 2026-09-03:
`sqlite3` is `3.46.1-7+deb13u1` and **vulnerable on the trixie track for both**,
with no fixed version and no DSA. The Trivy reading was correct. The outstanding
corroboration item is discharged for this entry.

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
| **Last Reassessed** | 2026-09-03 |
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

**Provenance of this assessment (updated 2026-09-03).** Fix status was
originally read from Trivy's own Debian advisory records, which is the same data
source the Container Security workflow scans against and therefore not
independent corroboration; the entry recorded that gap honestly and left a
Debian-tracker check outstanding, because that host was unreachable from this
project's cloud sessions (issue #711, item 1).

**That check has now been done.** `security-tracker.debian.org` is reachable
again, and the CVE was fetched on 2026-09-03: `ncurses` is `6.5+20250216-2` and
**vulnerable on the trixie track**, with no fixed version. The Trivy reading was
correct. Trivy 0.70.0 reports the finding four times over, once for each of
`libncursesw6`, `libtinfo6`, `ncurses-base` and `ncurses-bin`, all at
`6.5+20250216-2+dhi4`; the single suppression covers all four because it matches
on CVE id rather than binary package. The outstanding corroboration item is
discharged for this entry.

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
| **Last Reassessed** | 2026-09-03 |
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

### Reassessment 2026-09-03

The three things the remediation plan asks a reassessment to confirm, each
checked rather than assumed, with Trivy 0.70.0 run over the base image's own
filesystem (extracted from the GHCR layers, so the numbers describe the image
this project actually pins rather than a scan report from a past run):

1. **The package is still present.** `linux-libc-dev 6.12.101-1+dhi0` on the
   pinned digest `sha256:5bbd41ae`.
2. **The policy still matches only what it should.** Every `linux-libc-dev`
   finding without a fixed version is suppressed, and nothing else is.
3. **No accepted CVE has quietly acquired a trixie-track fix while staying
   hidden.** It cannot, by construction, and the scan confirms the guard is
   doing real work rather than sitting idle: of the 736 `linux-libc-dev`
   findings on the pinned digest, **294 now carry a fixed version and are
   therefore NOT suppressed**, 38 of them HIGH. That is the
   `not input.FixedVersion` guard behaving exactly as designed, and it is the
   reason the Container Security workflow is currently red on `main`.

The remedy those 38 findings are asking for is the base-image digest refresh in
[PR #798](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/798). Measured
directly on the newer build (`3.14.7-debian13`, `linux-libc-dev 6.12.107-1`):
442 findings remain, **none of them fixable**, so the whole set falls inside
this acceptance and the guard has nothing left to hold open. The same refresh
takes the image from six fixable HIGH non-kernel findings to zero.

This is the case the 2026-08-02 precedent predicted in the abstract, now with a
number attached: a package-scoped acceptance that suppressed fixable findings
too would have hidden 294 of them, including the three `libuuid1` HIGHs and the
OpenSSL HIGH that no entry in this document covers.

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
| CVE-2025-59375   | libexpat1      | 2026-09-03    | Fixed by base expat 2.8.2-1~deb13u1+dhi0 (DSA-6404-1). |
| CVE-2026-25210   | libexpat1      | 2026-09-03    | Fixed by base expat 2.8.2-1~deb13u1+dhi0 (DSA-6404-1). |
| CVE-2026-45186   | libexpat1      | 2026-09-03    | Fixed by base expat 2.8.2-1~deb13u1+dhi0 (DSA-6404-1). |
| CVE-2026-56131   | libexpat1      | 2026-09-03    | Fixed by base expat 2.8.2-1~deb13u1+dhi0 (DSA-6404-1). |
| CVE-2026-56407   | libexpat1      | 2026-09-03    | Fixed by base expat 2.8.2-1~deb13u1+dhi0 (DSA-6404-1). |
| CVE-2026-56408   | libexpat1      | 2026-09-03    | Fixed by base expat 2.8.2-1~deb13u1+dhi0 (DSA-6404-1). |
| CVE-2026-40467   | gawk           | 2026-09-03    | Not applicable: `gawk` is not in the image.            |
| CVE-2026-40468   | gawk           | 2026-09-03    | Not applicable: `gawk` is not in the image.            |
| CVE-2026-40469   | gawk           | 2026-09-03    | Not applicable: `gawk` is not in the image.            |
| CVE-2026-40553   | gawk           | 2026-09-03    | Not applicable: `gawk` is not in the image.            |
| CVE-2026-8376    | perl-base      | 2026-09-03    | Not applicable: `perl-base` is not in the image.       |
| CVE-2026-42496   | perl-base      | 2026-09-03    | Not applicable: `perl-base` is not in the image.       |
| CVE-2026-42497   | perl-base      | 2026-09-03    | Not applicable: `perl-base` is not in the image.       |
| CVE-2026-48962   | perl-base      | 2026-09-03    | Not applicable: `perl-base` is not in the image.       |
| CVE-2026-9538    | perl-base      | 2026-09-03    | Not applicable: `perl-base` is not in the image.       |
| CVE-2026-53615   | libuuid1       | 2026-09-03    | Fixed by base util-linux 2.41.5-0+deb13u1+dhi2 (#798). |

The four `linux-libc-dev` rows were all cleared by a base-image digest refresh rather than
by a suppression. They are the precedent for the `not input.FixedVersion` guard in
`.trivy/ignore-policy.rego`: each carried a Debian fixed version, so each stayed visible to the
scan until the base moved. The package-scoped acceptance above deliberately does not cover that
case. Their original per-CVE entries were consolidated on 2026-08-16 and remain in git history.

Aliases: PYSEC-2022-42969 is CVE-2022-42969 and GHSA-w596-4wvx-j9j6 (duplicate OSV record
PYSEC-2022-43183); PYSEC-2026-89 is CVE-2025-69534 and GHSA-5wmx-573v-2qwq.

### Resolution detail: the six Expat CVEs, `gawk` and `perl-base` (2026-09-03)

Fifteen of the twenty per-CVE suppressions in `.trivyignore.yaml` were retired in one
pass on 2026-09-03. None of those fifteen needed a base-image change to retire: **every
one was already dead against the digest this project had pinned since 2026-08-22**.
(A sixteenth, `CVE-2026-53615` on `libuuid1`, was retired in the same pass for the
opposite reason: it was the one entry here that ever carried an upstream fix, and the
digest refresh in PR #798 is what delivered it. Its detail is below.) They were
suppressing findings that no longer existed, which is the failure mode a suppression file
is least able to report on itself, because a suppressed finding and an absent finding look
identical from the outside. The check that separates them has to be run deliberately, and
until 2026-09-03 it could not be: `security-tracker.debian.org` was unreachable from this
project's cloud sessions (issue #711, item 1), and it is reachable again.

**The six Expat CVEs were fixed by a base-image bump nobody noticed.** Debian fixed all
six in `expat 2.8.2-1~deb13u1` on the trixie-security track under DSA-6404-1, and the
pinned base image has shipped `2.8.2-1~deb13u1+dhi0` since before the current pin. The
entry meanwhile still recorded the affected version as `2.7.1-2+dhi5`, the version
observed when the entry was opened on 2026-07-19. The base moved, the document did not,
and the suppressions outlived their subject by weeks.

Verified three ways rather than inferred from the entry's own text:

- **Debian tracker, per CVE.** Each of the six fetched individually on 2026-09-03; all
  six give the trixie fixed version as `2.8.2-1~deb13u1`, DSA-6404-1, with
  trixie-security now at `2.8.3-1~deb13u1`.
- **The image itself.** The GHCR manifest and layers for the pinned digest
  `sha256:5bbd41ae` were fetched and unpacked; `var/lib/dpkg/status.d/libexpat1` reads
  `2.8.2-1~deb13u1+dhi0`.
- **A scan.** Trivy 0.70.0 over that filesystem reports none of the six.

**`gawk` and `perl-base` are not in the image at all.** Nine suppressions (four gawk, five
perl-base) name packages the runtime image does not contain. The DHI hardened base ships
50 packages, enumerated from `var/lib/dpkg/status.d/` across all five of its layers, and
neither package is among them; the runtime stage adds only `/app/.venv` and the repository
source on top, neither of which can introduce a Debian package. Trivy over the same
filesystem reports zero findings for both.

This one is worth reading twice, because the accepted reasoning was not merely stale, it
was never checked. The `perl-base` suppressions entered the tree undocumented in `d1907a8`
(PR #668, a frontend change) and were documented retrospectively on 2026-08-17 with a
careful non-reachability argument: the application never shells out, so it never invokes
perl. That argument is true and it is also beside the point, because there is no perl in
the image to invoke. The `.trivyignore.yaml` comment went further and asserted a positive
fact that is false: "the image ships gawk from the base layer". Nothing verified it. A
reachability argument is only as good as the premise that the vulnerable code is present,
and that premise is the cheapest one to check.

**What this changes about the process, not just the entries.** Every retired suppression
here was retired on evidence read out of the image, not out of a scan report. That
distinction is already written into this document for fix status ("queried directly rather
than inferred from scan absence, which suppression would have masked"); it applies just as
much to whether the package exists. The reason it took until now is that reading the image
was treated as harder than it is: the base image is anonymously pullable from GHCR, and
its package inventory is a `status.d` directory in one layer.

**Expat has not left the image, only these six CVEs have.** Trivy 0.70.0 reports
CVE-2026-66046 (High, no Debian fix) against `libexpat1` and `libexpat1-dev` on the pinned
digest and on the newer one alike, plus CVE-2025-66382, CVE-2026-76956 and CVE-2026-76957
at Medium. CVE-2026-66046 needs its own acceptance entry, and one is already written in
[PR #798](https://github.com/ByronWilliamsCPA/cyo-adventure/pull/798); it is deliberately
not duplicated here. **Merge order matters:** whichever of the two changes lands second
must keep PR #798's `CVE-2026-66046` block in `.trivyignore.yaml`, which this change's
deletion of the surrounding Expat section will otherwise conflict with.

Aliases and scope: these fifteen retirements remove entries and suppressions only. No
`.trivy/ignore-policy.rego` change is involved, and the four remaining suppressions
(`libsqlite3-0` ×2, `ncurses` ×1, `libuuid1` ×1) are unaffected.

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
| 2026-09-03  | Claude Code    | Reassessed all seven active entries against sources that were unreachable when they were written; `security-tracker.debian.org` is available from cloud sessions again, which discharges the standing corroboration caveat on the `libsqlite3-0`, `ncurses` and `perl-base` entries and closes issue #711 item 1. Retired 16 of the 20 per-CVE suppressions. Fifteen were already dead against the pinned digest: the six Expat CVEs (fixed in trixie-security by `expat 2.8.2-1~deb13u1`, DSA-6404-1, and the base has shipped `2.8.2-1~deb13u1+dhi0` for weeks) plus nine naming `gawk` and `perl-base`, neither of which is in the image at all. Evidence read out of the GHCR layers and a Trivy 0.70.0 run over the extracted filesystem, not out of a scan report, since a suppressed finding and an absent one are indistinguishable from the outside. Corrected two claims that had gone stale: `libsqlite3-0` CVE-2026-11822/11824 are now High, not Medium, so the entry's "currently inert" note was wrong and those two suppressions are load-bearing; and CVE-2026-53615 (`libuuid1`) is no longer unfixed, `util-linux 2.41.5-0+deb13u1` is on trixie-security and in the base image's current build. Its `Reassessment Due` was deliberately left at 2026-09-06 rather than extended, because the remedy was the digest refresh then open as PR #798 and a fixable finding should not buy another quarter of silence. PR #798 has since merged, so that sixteenth suppression is retired here and its entry moved to Resolved, discharging the plan it recorded. Re-verified on 2026-09-03 by reading the shipped package version out of the merged digest (`sha256:d66d6403`) rather than from a scan verdict: `libuuid1` is at 2.41.5, and `gawk` and `perl-base` are absent from all 118 packages. The same digest clears 38 fixable HIGH `linux-libc-dev` findings and 6 fixable HIGH findings in `libuuid1` and OpenSSL that no entry covers. CVE-2026-66046 (`libexpat1`) is the one Expat CVE the refresh does NOT clear: the image ships `libexpat1` 2.8.3, inside its affected range, so its suppression is retained. |
