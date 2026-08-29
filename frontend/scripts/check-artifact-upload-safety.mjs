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
 */
const PLAYWRIGHT_OUTPUT_SEGMENTS = new Set(['test-results', 'playwright-report'])

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
 * so a silently broken parser reddens instead of reporting a clean tree.
 *
 * @param {string} yamlText Raw workflow file contents.
 * @returns {Array<{name: string, paths: string[]}>} One entry per upload step.
 */
export function parseUploadSteps(yamlText) {
  const lines = yamlText.split('\n')
  const steps = []
  let current = null

  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i]
    if (/^ *- +[A-Za-z]/.test(line) && current !== null) {
      // A new list item begins, so the previous upload step is closed. Any
      // step-starting key resets it, not just `uses:`/`name:`, so a `path:`
      // belonging to a later step can never be attributed to this one.
      current = null
    }
    if (/uses:\s*actions\/upload-artifact/.test(line)) {
      current = { name: 'unnamed', paths: [] }
      steps.push(current)
      continue
    }
    if (current === null) {
      continue
    }
    const nameMatch = /^\s*name:\s*(.+?)\s*$/.exec(line)
    if (nameMatch !== null && current.name === 'unnamed') {
      current.name = nameMatch[1]
    }
    const inlinePath = /^\s*path:\s*(?!\|)(\S.*?)\s*$/.exec(line)
    if (inlinePath !== null) {
      current.paths.push(stripQuotes(inlinePath[1]))
      continue
    }
    if (/^\s*path:\s*\|\s*$/.test(line)) {
      const indent = (/^(\s*)/.exec(lines[i + 1] ?? '') ?? ['', ''])[1].length
      for (let j = i + 1; j < lines.length; j += 1) {
        const blockLine = lines[j]
        if (blockLine.trim() === '') {
          continue
        }
        const thisIndent = (/^(\s*)/.exec(blockLine) ?? ['', ''])[1].length
        if (thisIndent < indent) {
          break
        }
        current.paths.push(stripQuotes(blockLine.trim()))
      }
    }
  }
  return steps
}

/**
 * @param {string} value A YAML scalar that may be quoted.
 * @returns {string} The scalar with a single layer of quoting removed.
 */
function stripQuotes(value) {
  const match = /^(['"])(.*)\1$/.exec(value)
  return match === null ? value : match[2]
}

/**
 * Remove a trailing `#` comment from a YAML scalar.
 *
 * The reader above is hand-rolled and does not strip comments, so without
 * this the comment stayed glued to the scalar, became its last `/`-segment,
 * and any `.` inside it (a sentence-ending period, `ADR-029.`, a version
 * number) read as a file extension. `frontend/test-results/ # keep, see
 * ADR-029.` then classified `narrow` and the hard rule exempted a wholesale
 * Playwright output directory.
 *
 * In YAML a `#` opens a comment only at the start of the scalar or after
 * whitespace, so `a#b.txt` keeps its `#`. #ASSUME: data-integrity: this is not
 * full YAML fidelity. A `#` inside a QUOTED scalar is not a comment, and this
 * function cannot see the quotes because `stripQuotes` has already removed
 * them by the time a path reaches classification. The residual is
 * fail-CLOSED, which is why it is tolerated: truncating a scalar can only
 * remove path segments, never add one, so a truncated path can lose its
 * `test-results` segment (becoming `unrelated`, and only for a path that
 * names no output directory before the ` #`) or lose its allowlisted
 * basename (becoming `wholesale`). It can never turn a refusal into an
 * exemption. #VERIFY: if a legitimately-quoted upload path ever needs a ` #`
 * in it, parse the quoting here instead of widening the allowlist.
 *
 * @param {string} scalar A YAML scalar, already unquoted.
 * @returns {string} The scalar with any trailing comment removed.
 */
function stripTrailingComment(scalar) {
  const match = /(?:^|\s)#/.exec(scalar)
  return match === null ? scalar : scalar.slice(0, match.index)
}

/**
 * Classify one declared artifact path.
 *
 * `wholesale` means "this publishes something out of a Playwright output
 * directory that is not on the narrow allowlist": the directory itself, a
 * glob inside it, or a single file whose basename nobody enumerated.
 * `narrow` is reserved for a single file whose basename is in
 * :data:`NARROW_UPLOAD_ALLOWLIST`, which is to say a file our own test code
 * writes and whose contents are therefore known. Everything else is
 * `unrelated`.
 *
 * The allowlist is what makes this arm falsifiable. "Names one file" is not a
 * safety property: `error-context.md` names one file and carried a plaintext
 * password out of a tier that had trace, screenshot and video all off.
 *
 * @param {string} declaredPath The `path:` value from an upload step.
 * @returns {'wholesale' | 'narrow' | 'unrelated'} The classification.
 */
export function classifyUploadPath(declaredPath) {
  const trimmed = stripTrailingComment(declaredPath).trim()
  const segments = trimmed.replace(/\/+$/, '').split('/')
  const touchesOutputDir = segments.some((segment) => PLAYWRIGHT_OUTPUT_SEGMENTS.has(segment))
  if (!touchesOutputDir) {
    return 'unrelated'
  }
  const endsWithSlash = trimmed.endsWith('/')
  const hasGlob = trimmed.includes('*')
  const lastSegment = segments[segments.length - 1]
  const namesAnAllowedFile = !endsWithSlash && !hasGlob && NARROW_UPLOAD_ALLOWLIST.has(lastSegment)
  return namesAnAllowedFile ? 'narrow' : 'wholesale'
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
 * Whether a workflow injects a repository or environment secret.
 *
 * `${{ secrets.X }}` anywhere in the file is the signal that this tier can
 * type a real credential into a real login form, which is what turns a
 * wholesale upload from untidy into a disclosure. `secrets: inherit` is the
 * same signal by a different route: it grants the called workflow every
 * secret without naming one, so a rule keyed only on the literal
 * `${{ secrets.` would wave it straight through.
 *
 * @param {string} yamlText Raw workflow file contents.
 * @returns {boolean} True when the workflow references any secret.
 */
export function injectsSecrets(yamlText) {
  return SECRET_EXPRESSION.test(yamlText) || SECRETS_INHERIT.test(yamlText)
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
