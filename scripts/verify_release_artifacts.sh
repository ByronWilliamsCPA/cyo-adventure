#!/usr/bin/env bash
# Verify the release artifacts (pyproject version + CHANGELOG.md) for one version.
#
# Why this script exists (issue #364): release.yml's `propose` job asserted the
# release artifacts inline, but the `publish` job tagged and created the GitHub
# Release from pyproject.toml's version with no re-verification. Anything that
# lands between the two (a merge-queue rebase, a hand edit on the release branch,
# a reverted changelog splice) could ship a tag whose notes or version did not
# match. Both jobs now run this one script, so there is a single source of truth
# for what "a well-formed release" means and the publish leg fails loudly (no
# tag, no release) on the same conditions the propose leg does.
#
# Usage:
#   scripts/verify_release_artifacts.sh VERSION [--baseline-ref REF]
#
#   VERSION         the version the artifacts must describe (e.g. 1.4.0).
#   --baseline-ref  a git ref whose CHANGELOG.md is the "before" for the
#                   did-not-shrink check. In `propose` the edits are uncommitted,
#                   so the baseline is HEAD; in `publish` the merged release
#                   commit IS HEAD, so the baseline is HEAD~1. Omit the flag to
#                   skip the shrink check (e.g. no history is available).
#
# Reads pyproject.toml and CHANGELOG.md from the current directory; run it from
# the repository root. It uses awk and grep rather than `uv version --short` so
# the publish job does not need uv installed, and keeps every pattern POSIX so
# the macOS leg of the test matrix, whose BSD grep has no PCRE mode, runs it
# unchanged.
#
# #CRITICAL data-integrity: the version bump and the changelog splice ARE the
# release. If PSR silently no-ops (a config or template regression, an upstream
# default change) the GraphQL commit would still open a PR that tags and
# publishes an empty or wrong release, exactly the kind of silent stall this
# pipeline exists to prevent (cf. PR #241). Assert every artifact here, before
# the commit is built (propose) and again before the tag is cut (publish), so a
# malformed release fails loudly instead of shipping.
# #VERIFY each assertion below sets FAIL=1 and the script exits non-zero.
set -euo pipefail

usage() {
  echo "usage: $0 VERSION [--baseline-ref REF]" >&2
  exit 2
}

[ "$#" -ge 1 ] || usage
NEXT="$1"
shift
BASELINE_REF=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    --baseline-ref)
      [ "$#" -ge 2 ] || usage
      BASELINE_REF="$2"
      shift 2
      ;;
    *)
      usage
      ;;
  esac
done

FAIL=0
# #CRITICAL external-resources: this script runs on every CI platform in the
# matrix, including macOS, whose BSD grep implements no PCRE mode. Keep every
# pattern POSIX: awk -F'"' takes the first `version = "..."` line and exits,
# which is what the original GNU-only extraction did, without needing an
# escape BSD grep cannot parse.
# #VERIFY tests/unit/test_verify_release_artifacts.py::test_verify_script_uses_no_gnu_only_grep_flags
# scans this file and fails if a GNU-only grep flag reappears anywhere in it.
if [ ! -f pyproject.toml ]; then
  echo "::error::pyproject.toml not found; run this script from the repository root."
  exit 1
fi
ACTUAL="$(awk -F'"' '/^version = "/ { print $2; exit }' pyproject.toml)"
if [ "${ACTUAL}" != "${NEXT}" ]; then
  echo "::error::pyproject version is '${ACTUAL}', expected '${NEXT}'."
  FAIL=1
fi
if ! grep -qF "## [${NEXT}] - " CHANGELOG.md; then
  echo "::error::CHANGELOG.md has no '## [${NEXT}] - ' section heading."
  FAIL=1
fi
# #ASSUME data-integrity: a heading alone is not a release; the section must
# carry actual entries. An empty section means the commit filter dropped
# everything, so fail rather than publish a heading with no notes. A bare
# sub-heading ('### Features' with nothing under it) is an empty section too:
# it is non-whitespace, so a whitespace test alone would pass it.
# #VERIFY awk captures the body between this version's heading and the next
# '## ' heading, and grep requires at least one markdown list item in it.
SECTION_BODY="$(
  awk -v h="## [${NEXT}] - " '
    index($0, h) == 1 { in_sec = 1; next }
    in_sec && /^## / { exit }
    in_sec { print }
  ' CHANGELOG.md
)"
if ! printf '%s' "${SECTION_BODY}" | grep -qE '^[[:space:]]*[-*+] [^[:space:]]'; then
  echo "::error::CHANGELOG.md section '[${NEXT}]' has a heading but no entries."
  FAIL=1
fi
# The paired heading + footer assertions jointly guarantee the injected footer
# link resolves to a real section: both key off ${NEXT}, so a footer with no
# section (or a section with no footer) fails here.
if ! grep -qF "[${NEXT}]: " CHANGELOG.md; then
  echo "::error::CHANGELOG.md has no '[${NEXT}]: ' compare-link footer."
  FAIL=1
fi
if ! grep -qF '<!-- version list -->' CHANGELOG.md; then
  echo "::error::CHANGELOG.md lost its '<!-- version list -->' insertion marker."
  FAIL=1
fi
# mode="update" splices; it must never truncate. Guard against a regression
# that regenerates (init mode) and drops prior history.
# #ASSUME data-integrity: "prior history is preserved" means every version
# section the baseline carried is still present. A total line count is only a
# proxy for that: a rewrite dropping ten old sections while adding twelve new
# lines grows the file and passes. Compare the version headings themselves, and
# keep the line-count check as a second signal for entries lost inside a section.
# Compare WHOLE heading lines with grep -qFx, not substrings. A substring search
# accepts a nested or quoted occurrence: a file that dropped the real
# "## [0.1.0] - ..." section but still mentions "### ## [0.1.0]" somewhere would
# pass while the released section is gone.
# #VERIFY tests/unit/test_verify_release_artifacts.py::test_verify_script_fails_when_a_prior_version_section_is_dropped
# removes one old section, keeps the file longer than the baseline, and asserts
# the script still fails.
# #VERIFY tests/unit/test_verify_release_artifacts.py::test_verify_script_rejects_a_nested_occurrence_of_a_removed_heading
# proves the substring form would have passed and the exact form does not.
if [ -n "${BASELINE_REF}" ]; then
  BASELINE_BODY="$(git show "${BASELINE_REF}:CHANGELOG.md")"
  MISSING=""
  while IFS= read -r heading; do
    [ -n "${heading}" ] || continue
    grep -qFx "${heading}" CHANGELOG.md || MISSING="${MISSING} ${heading}"
  done <<EOF
$(printf '%s' "${BASELINE_BODY}" | grep -E '^## \[[^]]+\] - ' || true)
EOF
  if [ -n "${MISSING}" ]; then
    echo "::error::CHANGELOG.md lost version section(s) present in" \
      "${BASELINE_REF}:${MISSING}; prior history may have been truncated."
    FAIL=1
  fi
  OLD_LINES="$(printf '%s\n' "${BASELINE_BODY}" | wc -l)"
  NEW_LINES="$(wc -l < CHANGELOG.md)"
  if [ "${NEW_LINES}" -lt "${OLD_LINES}" ]; then
    echo "::error::CHANGELOG.md shrank from ${OLD_LINES} to" \
      "${NEW_LINES} lines (baseline ${BASELINE_REF}); prior history may have been lost."
    FAIL=1
  fi
fi
if ! grep -qF '[0.1.0]: ' CHANGELOG.md; then
  echo "::error::CHANGELOG.md lost its history tail ('[0.1.0]:' link)."
  FAIL=1
fi
[ "${FAIL}" -eq 0 ] || exit 1
echo "Release artifacts verified for v${NEXT}."
