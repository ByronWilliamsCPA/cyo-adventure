# Trivy ignore policy for the CYO Adventure container image.
#
# Scope: ONE package-level judgment, expressed once, instead of the same
# judgment re-litigated per CVE. See docs/known-vulnerabilities.md, entry
# "linux-libc-dev kernel UAPI headers (package-scoped acceptance)".
#
# Why this exists. Between 2026-07-19 and 2026-08-16 the Container Security
# workflow surfaced 61 distinct HIGH `linux-libc-dev` CVEs across nine separate
# rounds. Every round reached the identical verdict: the package ships kernel
# UAPI headers used at compile time, the image contains no kernel binary and
# executes no kernel code, and the container runs on whatever kernel the Docker
# host provides. The finding is a property of the package, not of any individual
# CVE, so enumerating CVE IDs in .trivyignore was recording the same conclusion
# 61 times and going red for four days between each round.
#
# Rego dialect: Trivy 0.70.0 evaluates this as Rego v0. Do NOT add the v1 `if`
# keyword before a rule body; it fails to parse with
# "rego_parse_error: var cannot be used for rule name".
#
# #CRITICAL: security: this rule suppresses a whole package, so its narrowness
# is the only thing keeping it honest. Two guards do that work:
#   1. `input.PkgName` is matched exactly, so no other package is affected.
#      Every non-kernel acceptance stays enumerated per-CVE in .trivyignore
#      with its own documented reachability assessment.
#   2. `not input.FixedVersion` restricts this to findings Debian has NOT
#      fixed on the tracked release. A linux-libc-dev CVE that DOES carry a
#      fixed version still fails the scan, which is the signal that a
#      base-image digest refresh is available. That case is real: on
#      2026-08-02 CVE-2026-64530 and CVE-2026-64531 were cleared exactly that
#      way (issue #535), and a blanket package ignore would have hidden them.
# #VERIFY: tests/unit/test_trivy_ignore_policy.py asserts both guards against a
# fixture report, including that a fixable linux-libc-dev finding survives.
#
# `FixedVersion` is `omitempty` in Trivy's JSON, so an absent fix is an ABSENT
# KEY, not an empty string. `input.FixedVersion == ""` silently never matches
# and would make this rule a no-op; `not input.FixedVersion` is the correct
# test. Verified against Trivy 0.70.0 on 2026-08-16.
#
# Removal condition: this policy goes away entirely if `linux-libc-dev` stops
# shipping in the runtime base image. It is a `-dev` package with no purpose in
# an image that has no compiler, and the upstream ask is tracked alongside the
# documented entry.

package trivy

default ignore = false

ignore {
	input.PkgName == "linux-libc-dev"
	not input.FixedVersion
}
