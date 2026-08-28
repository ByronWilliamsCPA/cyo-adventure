// SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
//
// SPDX-License-Identifier: MIT

/**
 * Extract failing spec file paths and test titles from a Playwright JSON
 * reporter report, formatted for embedding in a GitHub issue body.
 *
 * Why this exists: every scheduled e2e workflow's failure alert used to carry
 * only generic prose ("scheduled staging E2E failing") plus a run URL, so a
 * responder had to open the run and read the log to learn which spec failed.
 * `safety-eval.yml` names what failed because it has a machine-readable
 * report to parse; the Playwright tiers did not until the `json` reporter was
 * added alongside `list` in each config (task A7-i). This script is the
 * "consume it" half of that pair.
 *
 * #CRITICAL: security: THIS REPOSITORY IS PUBLIC and this script's output is
 * embedded verbatim into a world-readable GitHub issue body and comment. Only
 * `spec.file` and `test.title` are ever read off the report; `results[].error`
 * (which can quote response bodies and request state) and any `stdout`/
 * `stderr`/`attachments` are never touched, and the top-level `errors` array
 * (global setup/teardown failures) is counted but never quoted.
 * #VERIFY: a future edit that reads any field other than `file`/`title` off a
 * spec, or `message`/`stack` off anything, must be rejected in review.
 *
 * Usage: node scripts/extract-failing-specs.mjs <report-path> [--cap N]
 * Always exits 0 and always prints something usable: a missing or
 * unparseable report degrades to an explanatory line rather than throwing, so
 * a caller can safely use this script's stdout as alert body text without a
 * try/catch of its own. A failure to describe a failure must never become a
 * failure to report one.
 */

import { readFileSync } from 'node:fs'

const DEFAULT_CAP = 20

function parseArgs(argv) {
  const reportPath = argv[2]
  let cap = DEFAULT_CAP
  const capFlagIndex = argv.indexOf('--cap')
  if (capFlagIndex !== -1) {
    const raw = argv[capFlagIndex + 1]
    const parsed = Number.parseInt(raw ?? '', 10)
    if (Number.isFinite(parsed) && parsed > 0) {
      cap = parsed
    }
  }
  return { reportPath, cap }
}

/**
 * Walk a Playwright JSON report's suite tree (suites nest for `describe`
 * blocks) and collect every spec whose overall outcome was NOT ok, i.e. at
 * least one test on it ended `unexpected`. `spec.ok` already folds in
 * retries: a spec that failed then passed on retry (flaky) is `ok: true` and
 * is correctly excluded here, since the run's final verdict for it was pass.
 *
 * #EDGE: data-integrity: `title` is the spec's own title only, not the
 * enclosing `describe` chain, so `file > title` is in principle ambiguous
 * between two specs in the same file under different `describe` blocks with
 * the same title. Latent, not live: as of this writing the only intra-file
 * duplicate titles in the suite come from parameterized template literals
 * that resolve to distinct strings per case, so no real collision exists
 * today.
 * #VERIFY: if a real collision is ever introduced, prepend the describe
 * chain here (Playwright's own `titlePath()` on the reporter side, not
 * reconstructible from this JSON shape alone without also walking `suite.title`
 * up the tree) rather than treating `file > title` as a unique key elsewhere.
 */
function collectFailingSpecs(suite, out) {
  for (const spec of suite.specs ?? []) {
    if (spec.ok === false) {
      out.push({
        file: String(spec.file ?? 'unknown file'),
        title: String(spec.title ?? 'unknown test'),
      })
    }
  }
  for (const child of suite.suites ?? []) {
    collectFailingSpecs(child, out)
  }
}

function formatFailingSpecs(failing, cap, topLevelErrorCount) {
  const lines = []
  if (failing.length === 0) {
    lines.push(
      topLevelErrorCount > 0
        ? `The Playwright report parsed cleanly but recorded no failing spec; ${topLevelErrorCount} ` +
            'top-level error(s) were reported outside any spec (for example a global setup or ' +
            'webServer failure). See the run log for detail.'
        : 'The Playwright report parsed cleanly and recorded no failing spec.'
    )
    return lines.join('\n')
  }

  lines.push(`${failing.length} spec${failing.length === 1 ? '' : 's'} failed:`)
  const shown = failing.slice(0, cap)
  for (const { file, title } of shown) {
    lines.push(`- ${file} > ${title}`)
  }
  const omitted = failing.length - shown.length
  if (omitted > 0) {
    lines.push(`- ...and ${omitted} more not shown (capped at ${cap}).`)
  }
  return lines.join('\n')
}

function main() {
  const { reportPath, cap } = parseArgs(process.argv)

  if (!reportPath) {
    console.log(
      'No report path was given to extract-failing-specs.mjs; cannot name which spec failed.'
    )
    return
  }

  let raw
  try {
    // #ASSUME: external-resources: reportPath is a fixed, script-controlled
    // path passed by the calling workflow step (never user/event input), so
    // there is no path-traversal surface here.
    // #VERIFY: keep every call site passing a literal, non-interpolated path.
    // eslint-disable-next-line security/detect-non-literal-fs-filename -- reportPath is a caller-fixed literal, never event input
    raw = readFileSync(reportPath, 'utf8')
  } catch (error) {
    // #EDGE: external-resources: reachable whenever the run dies (crash,
    // timeout, OOM) before Playwright writes its JSON report at all.
    // #VERIFY: degrade to generic prose here rather than throwing; the
    // calling workflow step must never fail because this script did.
    console.log(
      `No Playwright JSON report found at ${reportPath} (${error.code ?? 'read error'}); the run likely ` +
        'died before Playwright finished writing one. Falling back to generic failure detail.'
    )
    return
  }

  let report
  try {
    report = JSON.parse(raw)
  } catch {
    console.log(
      `The Playwright JSON report at ${reportPath} could not be parsed; falling back to generic failure detail.`
    )
    return
  }

  // #EDGE: data-integrity: `report` parsed as valid JSON does not mean it has
  // the shape a Playwright JSON report actually has (a corrupted or
  // hand-edited file could parse to e.g. `{"suites": 5}`). A prior version of
  // this guard used `Array.isArray(report.suites) ? report.suites : []`,
  // which treats a non-array `suites` as an empty, ALL-PASSED report rather
  // than a shape violation: `{"suites": 5}` silently produced "The Playwright
  // report parsed cleanly and recorded no failing spec." instead of the shape
  // line below (task A7-i review, Important 1). That reads as "nothing
  // failed" on a run where the `playwright` step itself failed, which is the
  // wrongly-exclusive failure mode this script exists to avoid. The check
  // below requires `report` to be a non-null object with an actual array
  // `suites` before any iteration is attempted, so that case now falls to the
  // same explanatory line as a parse failure instead of being read as clean.
  // #VERIFY: `frontend/scripts/test/extract-failing-specs.test.mjs` (task
  // A7-i review, Important 2) runs this against `{"suites": 5}` and asserts
  // the shape line, not the "parsed cleanly" line, and separately asserts a
  // genuinely empty `{"suites": []}` report still reports clean. Keep both
  // assertions if this guard is ever touched again.
  if (report === null || typeof report !== 'object' || !Array.isArray(report.suites)) {
    console.log(
      `The Playwright JSON report at ${reportPath} did not have the expected shape; falling back to generic failure detail.`
    )
    return
  }

  // The outer shape is now confirmed, but an individual suite or spec entry
  // could still be a non-object (a `suites` array holding non-object
  // entries, e.g. `{"suites": [5, "bad", null]}`), which throws when
  // `collectFailingSpecs` reads a property off it. Wrapped so that degrades
  // to the same shape-violation line rather than an uncaught exception; this
  // is what makes "always exits 0" literally true rather than true only for
  // the report shapes seen in testing.
  try {
    const failing = []
    for (const suite of report.suites) {
      collectFailingSpecs(suite, failing)
    }
    const topLevelErrorCount = Array.isArray(report.errors) ? report.errors.length : 0

    console.log(formatFailingSpecs(failing, cap, topLevelErrorCount))
  } catch {
    console.log(
      `The Playwright JSON report at ${reportPath} did not have the expected shape; falling back to generic failure detail.`
    )
  }
}

main()
