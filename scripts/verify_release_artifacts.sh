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
# the repository root. It uses grep rather than `uv version --short` so the
# publish job does not need uv installed.
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
ACTUAL="$(grep -m1 -Po '^version = "\K[^"]+' pyproject.toml || true)"
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
# everything, so fail rather than publish a heading with no notes.
# #VERIFY awk captures the body between this version's heading and the next
# '## ' heading, and grep proves it holds a non-whitespace line.
SECTION_BODY="$(
  awk -v h="## [${NEXT}] - " '
    index($0, h) == 1 { in_sec = 1; next }
    in_sec && /^## / { exit }
    in_sec { print }
  ' CHANGELOG.md
)"
if ! printf '%s' "${SECTION_BODY}" | grep -q '[^[:space:]]'; then
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
if [ -n "${BASELINE_REF}" ]; then
  OLD_LINES="$(git show "${BASELINE_REF}:CHANGELOG.md" | wc -l)"
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
