// SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
//
// SPDX-License-Identifier: MIT

/**
 * Artifact-upload safety checker.
 *
 * Why this exists, stated as the defect it closes rather than as a policy:
 *
 * `frontend/playwright.e2e-staging-sweep.config.ts` has set `trace: 'off'`,
 * `screenshot: 'off'` and `video: 'off'` for some time, and its published
 * `e2e-staging-traces` artifacts STILL carried a plaintext password. Each one
 * held exactly one file, `device-grant-sweep-staging-.../error-context.md`,
 * and inside it an accessibility-snapshot line of the form
 * `textbox "Password" ...: <value>`, unmasked.
 *
 * The mechanism: Playwright writes `error-context.md` into the test output
 * directory as part of its error reporting. That channel is governed by the
 * reporter and the output directory, NOT by the `trace` / `screenshot` /
 * `video` use-options. Turning those three off therefore closes nothing on its
 * own. #CRITICAL: security: the only control that actually closes the leak is
 * at the UPLOAD boundary: a workflow must not publish a Playwright output
 * directory wholesale.
 *
 * #VERIFY: the fixture arm in
 * `frontend/scripts/test/artifact-upload-safety.test.mjs` builds an
 * `error-context.md` carrying a password line and asserts `scanForCredentials`
 * reports it. If that arm ever passes on a directory it should have failed,
 * the oracle below is broken and every "clean" result it has ever produced is
 * worthless.
 *
 * The rules are deliberately allowlist-shaped, not denylist-shaped, and that
 * claim now holds for BOTH arms. A denylist of known-bad filenames stops
 * covering the next Playwright release that adds a new diagnostic file, and it
 * does so silently, which is the same class of defect as the one above. The
 * single-file exemption is therefore keyed on
 * :data:`NARROW_UPLOAD_ALLOWLIST`, an enumerated set of basenames, and every
 * other filename inside a Playwright output directory is refused. Until
 * 2026-08-29 that arm exempted ANY single file, `error-context.md` included,
 * which is to say it exempted the exact file that leaked the password. A
 * single-file artifact carries a live credential just as easily as a directory
 * does, so an arm bounded only by "names one file" was a check that could not
 * fail.
 *
 * Usage, from the repository root:
 *   node frontend/scripts/check-artifact-upload-safety.mjs
 *   node frontend/scripts/check-artifact-upload-safety.mjs <workflows-dir>
 *   node frontend/scripts/check-artifact-upload-safety.mjs --scan <dir>
 *
 * With no `--scan`, it checks `.github/workflows` (or the directory given) and
 * exits non-zero if any workflow that injects a repository secret publishes a
 * Playwright output directory. The `--scan` mode is what an owner runs against
 * a downloaded artifact, or against an output directory before deciding to
 * publish any part of it; it exits non-zero on the first credential-shaped
 * hit.
 *
 * CI runs the assertions rather than the CLI: the `alert-action` job in
 * ci.yml executes `frontend/scripts/test/artifact-upload-safety.test.mjs`
 * on every PR, and that suite asserts against the real
 * `.github/workflows` tree.
 */

import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'

/*
 * The three helpers below are the only filesystem calls in this file, so the
 * `security/detect-non-literal-fs-filename` justification is stated once
 * rather than repeated at every call site. This is a build-side CLI and test
 * helper: every path it touches comes from an argument the operator passed or
 * from a directory listing of that argument, never from a request, a webhook
 * payload, or any other untrusted channel. A recursive directory walk cannot
 * be expressed with literal paths, which is the shape the rule assumes.
 */

/**
 * @param {string} dir Directory to list.
 * @returns {string[]} Its entry names.
 */
function readDir(dir) {
  // eslint-disable-next-line security/detect-non-literal-fs-filename -- see the block comment above: operator-supplied root, build-side only
  return readdirSync(dir)
}

/**
 * @param {string} path Path to stat.
 * @returns {import('node:fs').Stats} Its stats.
 */
function statOf(path) {
  // eslint-disable-next-line security/detect-non-literal-fs-filename -- see the block comment above: operator-supplied root, build-side only
  return statSync(path)
}

/**
 * @param {string} path File to read.
 * @returns {string} Its UTF-8 contents.
 */
function readText(path) {
  // eslint-disable-next-line security/detect-non-literal-fs-filename -- see the block comment above: operator-supplied root, build-side only
  return readFileSync(path, 'utf8')
}

/**
 * Directory names Playwright writes per-failure artifacts into.
 *
 * A path is treated as a Playwright output directory when any of its segments
 * matches one of these, so `frontend/test-results/`, `test-results/chromium/`
 * and `playwright-report/` are all covered.
 *
 * `playwright-json-report` is on the list because every Playwright config in
 * this repository writes one: `frontend/playwright.config.ts` and the three
 * `e2e-*` configs each set the `json` reporter's `outputFile` under that
 * directory name. Its failing-run JSON is not a summary; a `results[]` entry
 * carries `error.message`, `stdout`, `stderr` and `attachments`, so a login
 * step that fails with the typed value in the assertion message puts that
 * value in the report. Until 2026-08-29 a path under it classified
 * `unrelated`, which is to say the guard did not examine it at all.
 *
 * #CRITICAL: security: this set is what makes a path visible to the guard. A
 * segment missing here is not "allowed", it is UNCHECKED, and an unchecked
 * path produces a clean result indistinguishable from a safe one. #VERIFY:
 * `derives every Playwright output directory name from the configs themselves`
 * in `frontend/scripts/test/artifact-upload-safety.test.mjs` re-derives this
 * set from the `outputDir` and `outputFile` literals in
 * `frontend/playwright*.config.ts` and from every
 * `PLAYWRIGHT_JSON_REPORT_PATH:` override in `.github/workflows`, and fails
 * when either moves. That test is the discharge of the #CRITICAL above; the
 * prose #VERIFY it replaced was discharged by nobody, which is how
 * `playwright-json-report` stayed off this list while every path under it
 * classified `unrelated`.
 */
export const PLAYWRIGHT_OUTPUT_SEGMENTS = new Set([
  'test-results',
  'playwright-report',
  'playwright-json-report',
])

/**
 * Directory prefixes a Playwright output directory can appear under.
 *
 * Workflows declare upload paths relative to the repository root, and every
 * Playwright config in this repository runs with `frontend/` as its root, so
 * `frontend/test-results` is the spelling on disk. The empty root covers a
 * workflow whose `working-directory` is already `frontend/`, which declares
 * the same directory as `test-results`.
 *
 * This exists so :func:`classifyUploadPath` can answer a containment question
 * rather than a spelling question: `path: frontend` is an ANCESTOR of
 * `frontend/test-results`, publishes every `error-context.md` underneath it,
 * and named no output directory at all.
 */
const PLAYWRIGHT_OUTPUT_ROOTS = ['', 'frontend']

/**
 * @returns {string[][]} Every known output directory, as a segment array.
 */
function knownOutputDirs() {
  /** @type {string[][]} */
  const dirs = []
  for (const root of PLAYWRIGHT_OUTPUT_ROOTS) {
    for (const segment of PLAYWRIGHT_OUTPUT_SEGMENTS) {
      dirs.push(root === '' ? [segment] : [root, segment])
    }
  }
  return dirs
}

/**
 * Basenames a secret-bearing workflow may publish from a Playwright output
 * directory. Everything else there is refused.
 *
 * Derived from what the repository actually uploads today, not invented: the
 * only single-file upload out of a Playwright output directory anywhere in
 * `.github/workflows` is `e2e-staging.yml`'s
 * `frontend/test-results/leaked-device-grants.jsonl`.
 *
 * Why that one file is safe to publish, stated so a future reader can re-judge
 * it rather than inherit it: the sweep spec writes the ledger itself, one JSON
 * object per line of the shape `{"profileId", "confirmed"}`. It is not a
 * Playwright-authored diagnostic, so a Playwright release cannot change what
 * is in it; it carries no page snapshot, no trace, no request headers and no
 * form values, which are the four channels every credential in the incident
 * arrived by. A profile id is already a non-secret identifier the artifact
 * consumer needs in order to act on a leaked grant.
 *
 * #CRITICAL: security: adding a name here publishes that file from a workflow
 * holding real credentials. #VERIFY: before adding one, confirm the file is
 * written by our own test code rather than by Playwright, and run
 * `node frontend/scripts/check-artifact-upload-safety.mjs --scan <dir>` over a
 * real failing run's output directory.
 */
const NARROW_UPLOAD_ALLOWLIST = new Set(['leaked-device-grants.jsonl'])

/**
 * Credential-shaped content patterns.
 *
 * Each entry names the concrete channel it came from, so a future reader can
 * tell whether a pattern is still load-bearing. These are shapes, not values;
 * no credential appears in this file.
 */
const CREDENTIAL_PATTERNS = [
  {
    id: 'accessibility-snapshot-password-value',
    // `error-context.md` and the trace's accessibility snapshot render a
    // password field's VALUE in plain text. This is the pattern that the live
    // e2e-staging-traces artifacts matched.
    pattern: /textbox\s+"[^"\n]*[Pp]assword[^"\n]*"[^\n:]*:\s*\S/,
  },
  {
    id: 'trace-fill-action-password-value',
    // `0-trace.trace`: the `fill` action records `params.value` verbatim.
    pattern: /"selector"\s*:\s*"[^"\n]*[Pp]assword[^"\n]*"[^\n}]*"value"\s*:\s*"[^"\n]+"/,
  },
  {
    id: 'trace-step-title-fill',
    // `test.trace`: the step title embeds the filled value.
    pattern: /Fill\s+\\?"[^"\n]+\\?"\s+getBy\w+\(\\?'[^'\n]*[Pp]assword/,
  },
  {
    id: 'jwt',
    pattern: /\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\./,
  },
  {
    id: 'bearer-header',
    pattern: /[Aa]uthorization\\?"?\s*:\s*\\?"?\s*Bearer\s+\S{8,}/,
  },
  {
    id: 'supabase-auth-token-cookie',
    pattern: /sb-[a-z0-9]+-auth-token/,
  },
]

/**
 * Split a workflow's steps into `actions/upload-artifact` declarations.
 *
 * Hand-rolled because the harness job this runs in installs no dependencies by
 * design (see ci.yml, "No `cache:` and no install step"), and Node has no
 * built-in YAML parser. That makes the parser itself a risk: a parser that
 * finds nothing is indistinguishable from a repository with no uploads.
 * #CRITICAL: data-integrity: the test suite therefore feeds this function
 * synthetic workflow text with a known upload in it and asserts it is found,
 * and does so once per YAML spelling this function claims to accept, so a
 * silently broken parser reddens instead of reporting a clean tree.
 *
 * Until 2026-08-29 five ordinary spellings produced a step with no paths, or
 * no step at all, and each one was a silent exemption rather than an error:
 * a quoted `uses: "actions/upload-artifact@..."` (the whole step invisible,
 * which ALSO defeated the `e2e-prod.yml uploads no artifact at all` control
 * that runs through this same function), the block-scalar indicators `|-`,
 * `|+`, `>`, `>-` and `>+`, a `# comment` after `path: |`, a flow-mapping
 * step written on one line, and a step whose `uses:` comes after its `with:`.
 * The last one is why this reads a whole list item into a buffer and resolves
 * it at the step boundary instead of streaming line by line: streaming cannot
 * attribute a `path:` to a `uses:` it has not seen yet.
 *
 * @param {string} yamlText Raw workflow file contents.
 * @returns {Array<{name: string, paths: string[]}>} One entry per upload step.
 */
export function parseUploadSteps(yamlText) {
  const lines = yamlText.split('\n')
  const steps = []
  /** @type {{indent: number, lines: string[]} | null} */
  let item = null
  const flush = () => {
    if (item !== null) {
      const step = readUploadStep(item.lines)
      if (step !== null) {
        steps.push(step)
      }
      item = null
    }
  }
  for (const line of lines) {
    const bullet = /^([ \t]*)-[ \t]+\S/.exec(line)
    // A list item at the SAME indent or shallower closes the current one. The
    // indent comparison is what keeps a `- entry` inside a block scalar (which
    // is indented deeper than its own step's bullet) from being mistaken for
    // the next step.
    if (bullet !== null && (item === null || bullet[1].length <= item.indent)) {
      flush()
      item = { indent: bullet[1].length, lines: [line] }
      continue
    }
    if (item !== null) {
      item.lines.push(line)
    }
  }
  flush()
  return steps
}

/**
 * Turn one buffered YAML list item into an upload step, or `null`.
 *
 * @param {string[]} lines The list item's lines, bullet line first.
 * @returns {{name: string, paths: string[]} | null} The step, if it uploads.
 */
function readUploadStep(lines) {
  // The optional quote is load-bearing: `uses: "actions/upload-artifact@v4"`
  // is ordinary YAML, and without it the step is never opened at all.
  if (!/uses:[ \t]*['"]?actions\/upload-artifact/.test(lines.join('\n'))) {
    return null
  }
  /** @type {string[]} */
  const paths = []
  let name = 'unnamed'
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    const nameMatch = /^(?:[ \t]|- )*name:[ \t]*(.+?)[ \t]*$/.exec(line)
    if (nameMatch !== null && name === 'unnamed') {
      name = nameMatch[1]
    }
    // A flow mapping puts the key on a line that already carries other keys:
    // `- {uses: actions/upload-artifact@v4, with: {path: frontend/test-results/}}`.
    for (const flow of line.matchAll(/[{,][ \t]*path:[ \t]*([^,}\n]+)/g)) {
      paths.push(parsePathScalar(flow[1]))
    }
    // A `#` comment after the indicator is legal and does not end the block.
    // Removed with a separate pass rather than an optional group in the regex
    // below, because the optional group makes `security/detect-unsafe-regex`
    // (correctly) object to the nested quantifier.
    const blockOpen = /^([ \t]*)path:[ \t]*[|>][-+]?[ \t]*$/.exec(withoutLineComment(line))
    if (blockOpen !== null) {
      i = readBlockScalar(lines, i, blockOpen[1].length, paths)
      continue
    }
    const inline = /^[ \t]*path:[ \t]*(\S.*?)[ \t]*$/.exec(line)
    if (inline !== null) {
      paths.push(parsePathScalar(inline[1]))
    }
  }
  return { name, paths }
}

/**
 * Read a block scalar's body into `paths`.
 *
 * The body extent is decided by the `path:` KEY's indent, not by the first
 * body line's. Reading it from the first body line made a blank line directly
 * after `path: |` compute an indent of 0, which never terminated and swallowed
 * the rest of the file as paths.
 *
 * A `#` inside a block scalar is literal YAML content, never a comment, and so
 * is a quote character, so nothing is stripped or unquoted here. Both
 * directions are fail-closed: a body line `frontend/test-results/ # keep`
 * keeps a last segment nobody allowlisted, and a body line
 * `"frontend/test-results/leaked-device-grants.jsonl"` keeps its closing quote
 * on the basename and so misses the narrow allowlist. Unquoting it, which this
 * did until 2026-08-29, was the fail-OPEN direction: it granted the narrow
 * exemption to a path YAML does not read that way.
 *
 * @param {string[]} lines The step's lines.
 * @param {number} keyIndex Index of the `path:` line.
 * @param {number} keyIndent Indent of the `path:` key.
 * @param {string[]} paths Collector, appended to in place.
 * @returns {number} Index of the last line consumed.
 */
function readBlockScalar(lines, keyIndex, keyIndent, paths) {
  let last = keyIndex
  for (let j = keyIndex + 1; j < lines.length; j += 1) {
    const blockLine = lines[j]
    if (blockLine.trim() === '') {
      last = j
      continue
    }
    const indent = (/^([ \t]*)/.exec(blockLine) ?? ['', ''])[1].length
    if (indent <= keyIndent) {
      break
    }
    paths.push(blockLine.trim())
    last = j
  }
  return last
}

/**
 * @param {string} line A workflow line.
 * @returns {string} The line with any trailing `#` comment removed.
 */
function withoutLineComment(line) {
  const comment = /(?:^|[ \t])#/.exec(line)
  return comment === null ? line : line.slice(0, comment.index)
}

/**
 * Read an inline `path:` scalar, honouring quoting before comments.
 *
 * This replaced a `stripTrailingComment` helper that ran at classification
 * time, after a separate `stripQuotes` pass had already removed the quoting,
 * and so could not tell a comment from a `#` inside a quoted scalar. That ordering had exactly one observable effect left once the
 * narrow allowlist landed, and it ran the wrong way: `path: "reports #
 * nightly/frontend/test-results"` classified `unrelated`, i.e. fully exempt,
 * where the unstripped scalar classifies `wholesale`. A helper whose only
 * remaining behaviour turns a refusal into an exemption is worse than no
 * helper, and its two regression tests could not fail against it. Deciding the
 * quoting here, where it is still visible, closes that direction and keeps the
 * comment stripping the tests actually need.
 *
 * #EDGE: data-integrity: a backslash-escaped quote inside a double-quoted
 * scalar ends the value early here. #VERIFY: the truncation can only shorten a
 * path, which drops segments rather than adding them, so an output-directory
 * path stays refused; if a real upload path ever needs an escaped quote, parse
 * the escape rather than widening the allowlist.
 *
 * @param {string} raw The text after `path:`, untrimmed.
 * @returns {string} The scalar value, unquoted and un-commented.
 */
function parsePathScalar(raw) {
  const value = raw.trim()
  const quote = value.charAt(0)
  if (quote === '"' || quote === "'") {
    const close = value.indexOf(quote, 1)
    // Anything after the closing quote is a comment, so it is discarded; a `#`
    // BEFORE it is data, so it is kept.
    return close === -1 ? value.slice(1) : value.slice(1, close)
  }
  const comment = /(?:^|\s)#/.exec(value)
  return (comment === null ? value : value.slice(0, comment.index)).trim()
}

/**
 * Classify one declared artifact path.
 *
 * `wholesale` means "this publishes something out of a Playwright output
 * directory that is not on the narrow allowlist": the directory itself, a
 * glob inside it, a single file whose basename nobody enumerated, or an
 * ANCESTOR of it. `narrow` is reserved for a single file, inside an output
 * directory, whose basename is in :data:`NARROW_UPLOAD_ALLOWLIST`, which is to
 * say a file our own test code writes and whose contents are therefore known.
 * Everything else is `unrelated`.
 *
 * The allowlist is what makes the narrow arm falsifiable. "Names one file" is
 * not a safety property: `error-context.md` names one file and carried a
 * plaintext password out of a tier that had trace, screenshot and video all
 * off.
 *
 * #CRITICAL: security: containment, not spelling, is what this answers.
 * `actions/upload-artifact` resolves `path:` as a glob root and walks the
 * subtree, so `frontend`, `frontend/**`, `.` and `frontend/test-results*` each
 * publish every `error-context.md` under `frontend/test-results/` while naming
 * no output directory segment at all. Until 2026-08-29 all four classified
 * `unrelated`, which is to say fully exempt from the hard rule. #VERIFY: the
 * `an ancestor of a Playwright output directory is not exempt` arm in
 * `frontend/scripts/test/artifact-upload-safety.test.mjs` pins each of those
 * spellings, and `leaves unrelated artifact paths alone` pins the other
 * direction so the ancestor rule cannot degenerate into "everything is
 * wholesale".
 *
 * An expression-valued path (`${{ env.OUT_DIR }}`) cannot be resolved here:
 * its value lives in the runner. It is substituted with `*` and classified as
 * the unknown it is, so `${{ github.workspace }}` and `frontend/${{ matrix.x }}`
 * come out `wholesale` while `outcome-${{ matrix.tier }}.tsv` (which cannot
 * name or contain an output directory whatever the expression expands to)
 * stays `unrelated`. Failing loud instead was the alternative; substitution is
 * chosen because it is the same fail-closed answer without a third exit code
 * for callers to mishandle, and because the loud version would fire on
 * `kws-delivery-health.yml`, which uploads a per-tier TSV and touches no
 * Playwright output.
 *
 * @param {string} declaredPath The `path:` value from an upload step.
 * @returns {'wholesale' | 'narrow' | 'unrelated'} The classification.
 */
export function classifyUploadPath(declaredPath) {
  const trimmed = declaredPath.replace(/\$\{\{[^}]*\}\}/g, '*').trim()
  const normalized = trimmed.replace(/^(?:\.\/)+/, '').replace(/\/+$/, '')
  if (normalized === '' || normalized === '.') {
    // The whole workspace. Every output directory is under it.
    return 'wholesale'
  }
  const segments = normalized.split('/').filter((segment) => segment !== '')
  const insideOutputDir = segments.some((segment) => PLAYWRIGHT_OUTPUT_SEGMENTS.has(segment))
  if (!insideOutputDir) {
    return isAncestorOfOutputDir(segments) ? 'wholesale' : 'unrelated'
  }
  const endsWithSlash = trimmed.endsWith('/')
  const hasGlob = normalized.includes('*')
  const lastSegment = segments[segments.length - 1]
  const namesAnAllowedFile = !endsWithSlash && !hasGlob && NARROW_UPLOAD_ALLOWLIST.has(lastSegment)
  return namesAnAllowedFile ? 'narrow' : 'wholesale'
}

/**
 * Whether a declared path, which names no output-directory segment itself,
 * nonetheless has one underneath it.
 *
 * A glob segment matches a known directory name when the literal text before
 * its first `*` is a prefix of that name, so `test-results*` reaches
 * `test-results` and a bare `**` reaches everything.
 *
 * @param {string[]} segments The declared path's segments.
 * @returns {boolean} True when a known output directory lives under it.
 */
function isAncestorOfOutputDir(segments) {
  const globIndex = segments.findIndex((segment) => segment.includes('*'))
  const literal = globIndex === -1 ? segments : segments.slice(0, globIndex)
  const globPrefix =
    globIndex === -1 ? null : segments[globIndex].slice(0, segments[globIndex].indexOf('*'))
  return knownOutputDirs().some((dir) => {
    if (literal.length >= dir.length) {
      return false
    }
    for (let i = 0; i < literal.length; i += 1) {
      if (literal[i] !== dir[i]) {
        return false
      }
    }
    return globPrefix === null || dir[literal.length].startsWith(globPrefix)
  })
}

/**
 * Recursively scan a directory for credential-shaped content.
 *
 * Reads every regular file as UTF-8. Binary files (a trace zip, a screenshot)
 * decode to mojibake rather than throwing, and a zip's member names and any
 * stored-not-deflated text still show through, so a hit there is real; a miss
 * is NOT evidence of absence for a compressed archive. #ASSUME: data-integrity:
 * this is a text-level oracle. #VERIFY: for an archive, extract it first and
 * scan the extracted tree.
 *
 * @param {string} rootDir Directory to scan.
 * @returns {Array<{file: string, patternId: string}>} One entry per hit.
 */
export function scanForCredentials(rootDir) {
  const findings = []
  /** @param {string} dir */
  const walk = (dir) => {
    for (const entry of readDir(dir)) {
      const full = join(dir, entry)
      const stats = statOf(full)
      if (stats.isDirectory()) {
        walk(full)
        continue
      }
      if (!stats.isFile()) {
        continue
      }
      const contents = readText(full)
      for (const { id, pattern } of CREDENTIAL_PATTERNS) {
        if (pattern.test(contents)) {
          findings.push({ file: relative(rootDir, full), patternId: id })
        }
      }
    }
  }
  walk(rootDir)
  return findings
}

/**
 * Find every workflow that publishes a Playwright output directory wholesale.
 *
 * @param {string} workflowsDir Path to `.github/workflows`.
 * @returns {Record<string, string[]>} Workflow filename to wholesale paths.
 */
export function findWholesaleUploads(workflowsDir) {
  /** @type {Record<string, string[]>} */
  const result = {}
  for (const entry of readDir(workflowsDir)) {
    if (!entry.endsWith('.yml') && !entry.endsWith('.yaml')) {
      continue
    }
    const text = readText(join(workflowsDir, entry))
    const wholesale = parseUploadSteps(text)
      .flatMap((step) => step.paths)
      .filter((path) => classifyUploadPath(path) === 'wholesale')
    if (wholesale.length > 0) {
      result[entry] = wholesale
    }
  }
  return result
}

/** A `${{ secrets.NAME }}` expression, the ordinary way a secret enters a job. */
const SECRET_EXPRESSION = /\$\{\{\s*secrets\./

/**
 * `secrets: inherit` on a reusable-workflow call. Every secret the caller can
 * see is handed to the called workflow, and the file contains no
 * `${{ secrets. }}` expression at all, so the expression test above returns
 * false for a workflow with FULL access to the credential store.
 *
 * Deliberately NOT anchored to end-of-line. An `$`-anchored pattern is
 * defeated by a legal trailing `# comment`, which is the same defect
 * `.github/workflows/test/health-rollup.test.mjs`'s call-site regex carried.
 * Stopping at a word boundary after `inherit` covers the comment, a quoted
 * value, and trailing whitespace in one, with no nested quantifier for
 * `security/detect-unsafe-regex` to object to. The `^[ \t]*` anchor is what
 * keeps a commented-out `# secrets: inherit` from matching.
 */
const SECRETS_INHERIT = /^[ \t]*secrets:[ \t]*['"]?inherit\b/m

/**
 * A `${{ vars.NAME }}` expression. A repository or environment VARIABLE is not
 * masked in logs and is not meant for secrets, but it is a perfectly ordinary
 * place for a staging login identifier or a shared test password to end up,
 * and a tier that types one into a real login form discloses it through the
 * same channels a `secrets.` value would.
 */
const VARS_EXPRESSION = /\$\{\{\s*vars\./

/**
 * A request for an OIDC token: `id-token: write` in a `permissions:` block.
 *
 * The token is a credential the job mints at runtime rather than one written
 * in the file, so nothing matching `secrets.` or `vars.` need appear anywhere,
 * and a workflow exchanging it for a cloud session can hold access far broader
 * than any single repository secret.
 *
 * `write` is load-bearing. `id-token: none` is the value a workflow uses to
 * REFUSE the token, and treating it as a grant would make this detector answer
 * true for every workflow that spells its permissions out, which is a check
 * that always fires and therefore justifies nothing. The `^[ \t]*` anchor is
 * what keeps a commented-out `# id-token: write` and prose mentioning the
 * permission from matching, and the same anchor covers a workflow-level block
 * and a job-level one without needing to know which is which: both are an
 * indented `id-token:` line.
 *
 * The `[{,]` alternative and the optional quotes around the key are the flow
 * mapping: `permissions: {id-token: write}` and
 * `permissions: { contents: read, id-token: write }` are valid YAML, valid
 * GitHub Actions, and put the key mid-line where the `^[ \t]*` anchor cannot
 * see it. This is the house idiom rather than an exotic spelling: twelve
 * `permissions: {` lines exist in `.github/workflows` today. All twelve are
 * the benign `permissions: {}`, so this is prevention; the next author who
 * needs an OIDC token and writes it the way the surrounding twelve lines are
 * written would otherwise get a detector that answers false. `permissions: {}`
 * stays non-secret-bearing because `write-all` and `id-token` are still
 * required. #ASSUME: security: a `{` or `,` inside a COMMENT can now reach the
 * key alternative, so a comment quoting `{id-token: write}` reads as a
 * credential. #VERIFY: that direction is fail-closed (an extra violation a
 * human must clear), which is the direction to err in; the `^`-anchored
 * comment controls in the suite pin that ordinary commented-out lines are
 * still not matched.
 *
 * @see SECRETS_INHERIT for why the pattern is not anchored to end-of-line.
 */
const ID_TOKEN_WRITE = /(?:^[ \t]*|[{,][ \t]*)['"]?id-token['"]?:[ \t]*['"]?write\b/m

/**
 * The blanket grant: `permissions: write-all`, which includes `id-token`.
 *
 * A third route to an OIDC token, and the one a detector keyed on the literal
 * `id-token:` cannot see, because the workflow never spells the permission
 * out. GitHub expands `write-all` to every permission scope it offers, so a
 * job carrying it can mint the same token `ID_TOKEN_WRITE` exists to catch.
 *
 * Measured on 2026-08-29: zero occurrences in `.github/workflows`. Latent in
 * the same sense the other two widenings are, and here for the same reason.
 *
 * `read-all` is the sibling value that grants no credential, so the `write-`
 * prefix is load-bearing exactly as `write` is in `ID_TOKEN_WRITE`, and the
 * `^[ \t]*` anchor keeps a commented-out line from matching.
 *
 * @see ID_TOKEN_WRITE for why the key also matches after a `{` or `,`.
 */
const PERMISSIONS_WRITE_ALL = /(?:^[ \t]*|[{,][ \t]*)['"]?permissions['"]?:[ \t]*['"]?write-all\b/m

/**
 * Whether a workflow can reach a credential.
 *
 * `${{ secrets.X }}` anywhere in the file is the signal that this tier can
 * type a real credential into a real login form, which is what turns a
 * wholesale upload from untidy into a disclosure. `secrets: inherit` is the
 * same signal by a different route: it grants the called workflow every
 * secret without naming one, so a rule keyed only on the literal
 * `${{ secrets.` would wave it straight through. `${{ vars.X }}`, an OIDC
 * `id-token: write` grant, and the blanket `permissions: write-all` that
 * implies one are three more routes to the same place, none of which contains
 * the word `secrets`.
 *
 * The three widenings are PREVENTION, not a live finding. Measured on
 * 2026-08-29: `${{ vars.` occurs nowhere in `.github/workflows`, and the four
 * workflows that request `id-token` (scorecard, docs, slsa-provenance,
 * claude-baseline-review) publish no Playwright output, and no workflow
 * carries `permissions: write-all`. They are here so the first workflow to
 * take any of the three routes arrives guarded rather than exempt.
 *
 * @param {string} yamlText Raw workflow file contents.
 * @returns {boolean} True when the workflow can reach a credential.
 */
export function injectsSecrets(yamlText) {
  return (
    SECRET_EXPRESSION.test(yamlText) ||
    SECRETS_INHERIT.test(yamlText) ||
    VARS_EXPRESSION.test(yamlText) ||
    ID_TOKEN_WRITE.test(yamlText) ||
    PERMISSIONS_WRITE_ALL.test(yamlText)
  )
}

/**
 * @param {string} workflowsDir Path to `.github/workflows`.
 * @returns {string[]} Human-readable violations of the hard rule.
 */
export function findSecretBearingWholesaleUploads(workflowsDir) {
  const violations = []
  for (const [file, paths] of Object.entries(findWholesaleUploads(workflowsDir))) {
    const text = readText(join(workflowsDir, file))
    if (injectsSecrets(text)) {
      violations.push(
        `${file} injects a repository secret AND publishes ${paths.join(', ')}, which is ` +
          'a Playwright output directory, a glob inside one, or a file inside one that ' +
          'is not on the narrow allowlist. Such a directory carries the credential the ' +
          'tier types in, including in error-context.md, which trace: off does not ' +
          'suppress.'
      )
    }
  }
  return violations
}

const isMain =
  process.argv[1] !== undefined && import.meta.url.endsWith(process.argv[1].replace(/\\/g, '/'))
if (isMain) {
  const scanIndex = process.argv.indexOf('--scan')
  if (scanIndex !== -1) {
    const target = process.argv[scanIndex + 1]
    if (target === undefined) {
      console.error('--scan needs a directory')
      process.exit(2)
    }
    const findings = scanForCredentials(target)
    if (findings.length === 0) {
      console.log(`no credential-shaped content found under ${target}`)
      process.exit(0)
    }
    for (const finding of findings) {
      console.error(`CREDENTIAL-SHAPED: ${finding.file} matched ${finding.patternId}`)
    }
    process.exit(1)
  }
  const workflowsDir = process.argv[2] ?? '.github/workflows'
  const violations = findSecretBearingWholesaleUploads(workflowsDir)
  if (violations.length > 0) {
    for (const violation of violations) {
      console.error(`FORBIDDEN UPLOAD: ${violation}`)
    }
    process.exit(1)
  }
  console.log('no secret-bearing workflow publishes a Playwright output directory wholesale')
}
