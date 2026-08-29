// Executable contract for `findTrackingIssue` in
// ../scheduled-health-rollup.yml's github-script step.
//
// Before this file existed, `findTrackingIssue` was covered by nothing: the
// workflow-level comment above it asserted "the Search API is a genuinely
// different endpoint, not a re-inlined copy" of the pattern
// test_no_workflow_re_inlines_the_lookup guards against, but nothing ran the
// function to check the claim. A search call that mis-scopes its query, does
// not paginate, or lets a pull request through would satisfy that grep
// forever while being wrong in exactly the way the grep exists to catch.
//
// The script is EXTRACTED from the workflow YAML at run time, the same way
// ../../actions/ci-failure-issue/test/harness.mjs extracts the composite
// action's script: a copied fixture would keep passing after the real script
// changed, which is indistinguishable from the script being correct.
//
// This also carries the regression test for the Finding-1 fix: an unguarded
// `github.rest.search.issuesAndPullRequests` call throws on the Search API's
// tight secondary rate limit (~30 req/min, against ~23 workflows surveyed
// per run) and must degrade only the failing workflow's tracking status,
// never abort the whole script and discard the escalation report.
//
// Run: node --test .github/workflows/test/health-rollup.test.mjs

import { strict as assert } from 'node:assert'
import { test, describe } from 'node:test'
import { mkdtempSync, mkdirSync, writeFileSync, rmSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { createRequire } from 'node:module'

import { extractScript, AsyncFunction } from '../../actions/ci-failure-issue/test/harness.mjs'

const HERE = dirname(fileURLToPath(import.meta.url))
const ROLLUP_YML = join(HERE, '..', 'scheduled-health-rollup.yml')
const REQUIRE = createRequire(import.meta.url)
const REPO = { owner: 'ByronWilliamsCPA', repo: 'cyo-adventure' }

/**
 * Expand one cron field to the exact set of values it matches.
 *
 * Handles every form GitHub's scheduler accepts in a numeric field: `*`, a
 * bare value, a comma list, a range (`1-5`), a step over the whole range
 * (`*\/2`), a step from a start value (`5\/2`), a step over a range
 * (`1-5\/2`), and any comma combination of those (`1-5,0`).
 *
 * Anything it cannot parse THROWS. Returning an empty set instead would make
 * the collision detector report "no overlap" for a cron it simply could not
 * read, which is the silently-unfailable check this whole file exists to
 * stop shipping.
 *
 * @param {string} field One cron field.
 * @param {number} lo Lowest legal value for that field.
 * @param {number} hi Highest legal value for that field; a bare value or a
 *   range may still name this value explicitly.
 * @param {number} [stepTop=hi] The top a step-from-a-start-value term (e.g.
 *   `5/2`) counts up to. Distinct from `hi` only for the day-of-week field:
 *   `expandCronDow` passes 6 here, because 7 is legal as an explicit alias
 *   for Sunday but is not a value a step should count up through (counting
 *   to it would invent a phantom Sunday that normalises out of a 0-6 step).
 * @returns {Set<number>} Every value the field matches.
 */
function expandCronField(field, lo, hi, stepTop = hi) {
  const values = new Set()
  for (const term of field.split(',')) {
    const [rangePart, stepPart] = term.split('/')
    const step = stepPart === undefined ? 1 : Number(stepPart)
    let from
    let to
    if (rangePart === '*') {
      from = lo
      to = hi
    } else if (rangePart.includes('-')) {
      const [startText, endText] = rangePart.split('-')
      from = Number(startText)
      to = Number(endText)
    } else {
      from = Number(rangePart)
      // `5/2` means "5 to stepTop, every 2"; a bare `5` is just 5.
      to = stepPart === undefined ? from : stepTop
    }
    const parsed = [from, to, step]
    if (
      !parsed.every((value) => Number.isInteger(value)) ||
      step < 1 ||
      from < lo ||
      to > hi ||
      from > to
    ) {
      throw new Error(
        `unparseable cron field term "${term}" in field "${field}" ` +
          `(legal range ${lo}-${hi}); extend expandCronField rather than ` +
          'letting the collision check read it as no-overlap.'
      )
    }
    for (let value = from; value <= to; value += step) values.add(value)
  }
  return values
}

/**
 * Expand a day-of-week field, normalising 7 to 0.
 *
 * Cron accepts both 0 and 7 for Sunday, so `0 6 * * 0` and `0 6 * * 7` name
 * the same slot and must be seen as colliding: a bare `7` or a range ending
 * in `7` (e.g. `5-7`) still means what it says. But a step term with an
 * implicit end (`5/2`) must stop at Saturday (6), not count up to a literal
 * 7: 7 is only an alias for a day already reachable as 0, not an eighth day
 * to step through, and counting up to it invents a Sunday the term never
 * named.
 *
 * @param {string} field The day-of-week field.
 * @returns {Set<number>} Days matched, with Sunday always as 0.
 */
function expandCronDow(field) {
  const days = new Set()
  for (const day of expandCronField(field, 0, 7, 6)) days.add(day === 7 ? 0 : day)
  return days
}

/**
 * @param {Set<number>} a One set.
 * @param {Set<number>} b The other set.
 * @returns {boolean} Whether they share at least one member.
 */
function setsIntersect(a, b) {
  for (const value of a) {
    if (b.has(value)) return true
  }
  return false
}

/**
 * Whether two cron expressions can fire in the same minute.
 *
 * Each field is expanded to the set of values it matches and the sets are
 * intersected, so ranges, steps and lists are all handled the same way in
 * every field, and the answer does not depend on argument order. The
 * previous version compared minutes with a bare `===` and split only hour
 * and day-of-week on commas, so `0 7 * * 1-5` read as "no Monday" and
 * `*\/15 7 * * 1` read as "no :00".
 *
 * Day-of-month and month are not expanded, only checked: every cron in this
 * directory sets both to `*`, and a detector that quietly ignored a real
 * day-of-month would be wrong in the direction that hides collisions.
 *
 * @param {string} a One cron expression.
 * @param {string} b The other cron expression.
 * @returns {boolean} Whether the two can start in the same minute.
 */
function cronsCollide(a, b) {
  const parse = (cron) => {
    const [minute, hour, dom, month, dow] = cron.trim().split(/\s+/)
    if (dom !== '*' || month !== '*') {
      throw new Error(
        `cron "${cron}" constrains day-of-month or month; cronsCollide only ` +
          'reasons about minute, hour and day-of-week. Teach it those fields ' +
          'rather than accepting an answer it cannot compute.'
      )
    }
    return {
      minutes: expandCronField(minute, 0, 59),
      hours: expandCronField(hour, 0, 23),
      days: expandCronDow(dow),
    }
  }
  const left = parse(a)
  const right = parse(b)
  return (
    setsIntersect(left.minutes, right.minutes) &&
    setsIntersect(left.hours, right.hours) &&
    setsIntersect(left.days, right.days)
  )
}

/**
 * A minimal workflow file the discovery regex recognises as scheduled.
 *
 * Matches the exact shape `scheduled-health-rollup.yml`'s own header comment
 * documents as the discovery contract: `schedule:` indented two spaces under
 * `on:`, followed by a quoted `cron:` line.
 */
function scheduledWorkflowYaml() {
  return [
    'name: fixture',
    'on:',
    '  schedule:',
    "    - cron: '0 7 * * 4'",
    'jobs:',
    '  noop:',
    '    runs-on: ubuntu-latest',
    '    steps:',
    '      - run: echo hi',
    '',
  ].join('\n')
}

/** Three completed, non-success runs: exactly THRESHOLD, enough to escalate. */
function threeFailingRuns(name = 'fixture') {
  return [
    { status: 'completed', conclusion: 'failure', name },
    { status: 'completed', conclusion: 'failure', name },
    { status: 'completed', conclusion: 'failure', name },
  ]
}

/**
 * A faithful-enough double for the two Octokit surfaces the script calls:
 * `actions.listWorkflowRuns` (via `paginate.iterator`, for computeStreak) and
 * `search.issuesAndPullRequests` (via `paginate`, for findTrackingIssue).
 *
 * The search filter re-derives what the real Search API does server-side
 * from the same `q` string the script builds, so a test can prove the query
 * actually scopes to the right repo/label/open-issues rather than merely
 * asserting the query string looks right.
 */
class FakeRollupGitHub {
  constructor({ runsByFile = {}, searchIssues = [], searchError } = {}) {
    this.runsByFile = runsByFile
    this.searchIssues = searchIssues
    this.searchError = searchError
    this.calls = []
    const record = (name, params) => this.calls.push({ name, params })

    this.rest = {
      actions: {
        listWorkflowRuns: async (params) => {
          record('actions.listWorkflowRuns', params)
          const perPage = params.per_page ?? 100
          const page = params.page ?? 1
          const runs = this.runsByFile[params.workflow_id] ?? []
          return { data: runs.slice((page - 1) * perPage, page * perPage) }
        },
      },
      search: {
        issuesAndPullRequests: async (params) => {
          record('search.issuesAndPullRequests', params)
          if (this.searchError) {
            throw this.searchError
          }
          const perPage = params.per_page ?? 30
          const page = params.page ?? 1
          const q = params.q
          const repoMatch = /repo:(\S+)/.exec(q)
          const labelMatch = /label:"([^"]+)"/.exec(q)
          const openIssuesOnly = /\bis:issue\b/.test(q) && /\bis:open\b/.test(q)
          const matching = this.searchIssues.filter((item) => {
            if (repoMatch && item.repo !== repoMatch[1]) {
              return false
            }
            if (labelMatch && !(item.labels ?? []).includes(labelMatch[1])) {
              return false
            }
            if (openIssuesOnly && (item.pull_request !== undefined || item.state !== 'open')) {
              return false
            }
            return true
          })
          return { data: matching.slice((page - 1) * perPage, page * perPage) }
        },
      },
    }

    const paginate = async (fn, params) => {
      const perPage = params.per_page ?? 30
      const out = []
      let page = 1
      for (;;) {
        const { data } = await fn({ ...params, page })
        out.push(...data)
        if (data.length < perPage) {
          return out
        }
        page += 1
      }
    }
    paginate.iterator = (fn, params) =>
      (async function* gen() {
        const perPage = params.per_page ?? 100
        let page = 1
        for (;;) {
          const { data } = await fn({ ...params, page })
          if (data.length === 0) {
            return
          }
          yield { data }
          if (data.length < perPage) {
            return
          }
          page += 1
        }
      })()
    this.paginate = paginate
  }

  countOf(name) {
    return this.calls.filter((call) => call.name === name).length
  }

  callsTo(name) {
    return this.calls.filter((call) => call.name === name)
  }
}

/**
 * Run the real, extracted rollup script against a disposable
 * `.github/workflows/` fixture directory and Octokit doubles.
 *
 * `fs.readdirSync('.github/workflows')` in the script is a real Node call
 * against `process.cwd()`, not something the script lets a caller inject, so
 * this chdirs into a temp fixture directory for the duration of the call
 * (never in parallel with another such call, since node:test runs a file's
 * top-level tests sequentially by default) rather than mocking `fs`.
 */
async function runRollupScript({ fixtureFiles = {}, runsByFile = {}, searchIssues = [], searchError, hardCap } = {}) {
  const dir = mkdtempSync(join(tmpdir(), 'health-rollup-'))
  const workflowsDir = join(dir, '.github', 'workflows')
  mkdirSync(workflowsDir, { recursive: true })
  for (const [name, contents] of Object.entries(fixtureFiles)) {
    writeFileSync(join(workflowsDir, name), contents)
  }

  const github = new FakeRollupGitHub({ runsByFile, searchIssues, searchError })
  const infos = []
  const warnings = []
  const failures = []
  const outputs = {}
  const core = {
    setFailed: (message) => failures.push(String(message)),
    info: (message) => infos.push(String(message)),
    warning: (message) => warnings.push(String(message)),
    debug: () => {},
    notice: (message) => infos.push(`NOTICE: ${String(message)}`),
    setOutput: (key, value) => {
      outputs[key] = value
    },
  }
  const context = {
    repo: REPO,
    serverUrl: 'https://github.com',
    runId: 123456,
    eventName: 'schedule',
  }

  const previousEnv = process.env
  const previousCwd = process.cwd()
  process.env = { ...previousEnv, HARD_CAP: hardCap ?? '' }
  process.chdir(dir)
  try {
    const fn = new AsyncFunction('github', 'context', 'core', 'require', extractScript(ROLLUP_YML))
    const result = await fn(github, context, core, REQUIRE)
    return { github, infos, warnings, failures, outputs, result }
  } finally {
    process.chdir(previousCwd)
    process.env = previousEnv
    rmSync(dir, { recursive: true, force: true })
  }
}

describe('the harness is actually testing the workflow script', () => {
  test('the extracted script is the real one', () => {
    const script = extractScript(ROLLUP_YML)

    assert.ok(script.length > 500, `extracted only ${script.length} chars`)
    assert.match(script, /async function findTrackingIssue/)
    assert.match(script, /github\.rest\.search\.issuesAndPullRequests/)
  })
})

describe('findTrackingIssue: a match is found', () => {
  test('an open issue with the marker label and matching title prefix is reported tracked', async () => {
    const { github, failures, outputs, result } = await runRollupScript({
      fixtureFiles: { 'release.yml': scheduledWorkflowYaml() },
      runsByFile: { 'release.yml': threeFailingRuns('Semantic Release') },
      searchIssues: [
        {
          number: 42,
          title: '[release] scheduled release proposal failing',
          labels: ['ci-failure'],
          state: 'open',
          html_url: 'https://github.com/ByronWilliamsCPA/cyo-adventure/issues/42',
          repo: `${REPO.owner}/${REPO.repo}`,
        },
      ],
    })

    assert.deepEqual(failures, [])
    assert.equal(outputs.has_escalations, 'true')
    assert.match(result, /Tracking: tracked by #42/)
    assert.equal(github.countOf('search.issuesAndPullRequests'), 1)
  })
})

describe('findTrackingIssue: no match', () => {
  test('no open issue with the marker label reports self-alerts-but-no-open-issue', async () => {
    const { outputs, result } = await runRollupScript({
      fixtureFiles: { 'safety-eval.yml': scheduledWorkflowYaml() },
      runsByFile: { 'safety-eval.yml': threeFailingRuns('Safety eval') },
      searchIssues: [],
    })

    assert.equal(outputs.has_escalations, 'true')
    assert.match(
      result,
      /files its own tracking issue on failure, but none is currently open/,
    )
  })

  test('an open issue with the right label but the wrong title prefix also reports no match', async () => {
    const { result } = await runRollupScript({
      fixtureFiles: { 'safety-eval.yml': scheduledWorkflowYaml() },
      runsByFile: { 'safety-eval.yml': threeFailingRuns('Safety eval') },
      searchIssues: [
        {
          number: 7,
          title: '[unrelated] something else entirely',
          labels: ['ci-failure'],
          state: 'open',
          repo: `${REPO.owner}/${REPO.repo}`,
        },
      ],
    })

    assert.match(
      result,
      /files its own tracking issue on failure, but none is currently open/,
    )
  })
})

describe('findTrackingIssue: pagination', () => {
  test('a match past the first page of search results is still found', async () => {
    // per_page is hardcoded to 100 in the script, so proving pagination
    // actually happens requires more than 100 matching results: exactly the
    // reasoning harness.mjs documents for FakeGitHub.listForRepo's own
    // default of 30, applied to this endpoint's fixed 100.
    const decoys = Array.from({ length: 104 }, (_, i) => ({
      number: i + 1,
      title: `unrelated issue ${i}`,
      labels: ['ci-failure'],
      state: 'open',
      repo: `${REPO.owner}/${REPO.repo}`,
    }))
    const match = {
      number: 999,
      title: '[db-backup] scheduled database backup failing',
      labels: ['ci-failure'],
      state: 'open',
      html_url: 'https://github.com/ByronWilliamsCPA/cyo-adventure/issues/999',
      repo: `${REPO.owner}/${REPO.repo}`,
    }

    const { github, result } = await runRollupScript({
      fixtureFiles: { 'supabase-backup.yml': scheduledWorkflowYaml() },
      runsByFile: { 'supabase-backup.yml': threeFailingRuns('DB backup') },
      searchIssues: [...decoys, match],
    })

    assert.equal(
      github.countOf('search.issuesAndPullRequests'),
      2,
      'expected 105 matching issues to span exactly two 100-per-page calls',
    )
    assert.match(result, /Tracking: tracked by #999/)
  })
})

describe('findTrackingIssue: query scoping', () => {
  test('a wrong repo, a closed issue, and a wrong label are all excluded', async () => {
    const { result } = await runRollupScript({
      fixtureFiles: { 'mutation-testing.yml': scheduledWorkflowYaml() },
      runsByFile: { 'mutation-testing.yml': threeFailingRuns('Mutation testing') },
      searchIssues: [
        {
          number: 1,
          title: '[mutation-testing] scheduled mutation testing failing',
          labels: ['ci-failure'],
          state: 'open',
          repo: 'someone-else/other-repo',
        },
        {
          number: 2,
          title: '[mutation-testing] scheduled mutation testing failing',
          labels: ['ci-failure'],
          state: 'closed',
          repo: `${REPO.owner}/${REPO.repo}`,
        },
        {
          number: 3,
          title: '[mutation-testing] scheduled mutation testing failing',
          labels: ['e2e-alert'],
          state: 'open',
          repo: `${REPO.owner}/${REPO.repo}`,
        },
        {
          number: 4,
          title: '[mutation-testing] scheduled mutation testing failing',
          labels: ['ci-failure'],
          state: 'open',
          html_url: 'https://github.com/ByronWilliamsCPA/cyo-adventure/issues/4',
          repo: `${REPO.owner}/${REPO.repo}`,
        },
      ],
    })

    assert.match(result, /Tracking: tracked by #4/)
    assert.doesNotMatch(result, /tracked by #1\b/)
    assert.doesNotMatch(result, /tracked by #2\b/)
    assert.doesNotMatch(result, /tracked by #3\b/)
  })
})

describe('findTrackingIssue: pull requests are excluded', () => {
  test('a pull request matching label, repo, and title is not reported as tracked', async () => {
    const { result } = await runRollupScript({
      fixtureFiles: { 'release.yml': scheduledWorkflowYaml() },
      runsByFile: { 'release.yml': threeFailingRuns('Semantic Release') },
      searchIssues: [
        {
          number: 55,
          title: '[release] scheduled release proposal failing',
          labels: ['ci-failure'],
          state: 'open',
          repo: `${REPO.owner}/${REPO.repo}`,
          pull_request: { url: 'https://api.github.com/repos/x/y/pulls/55' },
        },
      ],
    })

    assert.doesNotMatch(result, /tracked by #55\b/)
    assert.match(
      result,
      /files its own tracking issue on failure, but none is currently open/,
    )
  })
})

describe('findTrackingIssue: the Finding-1 failure path', () => {
  test('a throwing search call degrades only that workflow, and the report still ships', async () => {
    const { github, outputs, failures, warnings, result } = await runRollupScript({
      fixtureFiles: {
        'release.yml': scheduledWorkflowYaml(),
        'safety-eval.yml': scheduledWorkflowYaml(),
      },
      runsByFile: {
        'release.yml': threeFailingRuns('Semantic Release'),
        'safety-eval.yml': threeFailingRuns('Safety eval'),
      },
      searchError: new Error('secondary rate limit exceeded'),
    })

    // The escalation report is the safety signal; a cosmetic lookup failure
    // must never take it down. Both workflows still appear.
    assert.equal(outputs.has_escalations, 'true')
    assert.deepEqual(failures, [], 'a lookup failure must not fail the step')
    assert.match(result, /### `release\.yml`/)
    assert.match(result, /### `safety-eval\.yml`/)

    const trackingLines = result.match(/- Tracking: .+/g) ?? []
    assert.equal(trackingLines.length, 2)
    for (const line of trackingLines) {
      assert.match(line, /tracking unknown \(lookup failed\)/)
    }

    // Never "untracked" and never "tracked" on a failed lookup.
    assert.doesNotMatch(result, /\*\*NOT TRACKED\*\*/)
    assert.doesNotMatch(result, /tracked by #/)

    assert.equal(github.countOf('search.issuesAndPullRequests'), 2, 'both files attempted the lookup')
    assert.equal(warnings.length, 2)
    assert.match(warnings[0], /tracking lookup for .+ failed: secondary rate limit exceeded/)
  })

  test('an untracked workflow is unaffected by a throwing search call elsewhere', async () => {
    // security-analysis.yml has no KNOWN_ALERTS entry, so findTrackingIssue
    // returns 'untracked' before ever reaching the search call: it must not
    // be caught up in the failure path at all.
    const { result, github } = await runRollupScript({
      fixtureFiles: { 'security-analysis.yml': scheduledWorkflowYaml() },
      runsByFile: { 'security-analysis.yml': threeFailingRuns('Security analysis') },
      searchError: new Error('should never be called for an untracked workflow'),
    })

    assert.match(result, /\*\*NOT TRACKED\*\*/)
    assert.equal(github.countOf('search.issuesAndPullRequests'), 0)
  })
})

describe('escalation gating is unaffected by tracking lookups', () => {
  test('a workflow below the threshold never reaches findTrackingIssue', async () => {
    const { outputs, github, result } = await runRollupScript({
      fixtureFiles: { 'release.yml': scheduledWorkflowYaml() },
      runsByFile: {
        'release.yml': [
          { status: 'completed', conclusion: 'failure', name: 'Semantic Release' },
          { status: 'completed', conclusion: 'success', name: 'Semantic Release', run_started_at: '2026-08-01T00:00:00Z' },
        ],
      },
      searchError: new Error('should never be called below the escalation bar'),
    })

    assert.equal(outputs.has_escalations, 'false')
    assert.equal(result, undefined)
    assert.equal(github.countOf('search.issuesAndPullRequests'), 0)
  })
})

/**
 * Pull the `const KNOWN_ALERTS = { ... }` object literal out of the
 * extracted rollup script and parse it into a plain object.
 *
 * KNOWN_ALERTS is a local const inside the script's closure, not something
 * the script exports, so `runRollupScript` cannot hand it back directly.
 * Brace-counting (not a regex) finds the matching close brace, because the
 * literal itself contains nested `{ label: ..., titlePrefix: ... }` objects
 * a non-greedy regex would truncate at the first one. Reading it via
 * `extractScript` (not a hand-copied literal) is the same "run the real
 * thing" contract this file already relies on: a copied fixture would keep
 * passing after the real map changed.
 *
 * Parsed with a per-entry regex, not evaluated as code (no eval/Function):
 * every KNOWN_ALERTS entry in this repo, as of this writing, is a single
 * line of the shape `'file.yml': { label: 'x', titlePrefix: '[y]' }`, and
 * this only reads trusted, repo-owned source either way, but a parser that
 * cannot execute anything is the safer contract for a test file to hold.
 */
function extractKnownAlerts(scriptText) {
  const marker = 'const KNOWN_ALERTS = '
  const idx = scriptText.indexOf(marker)
  assert.notEqual(idx, -1, 'const KNOWN_ALERTS = {...} not found in the extracted rollup script')
  const braceStart = idx + marker.length
  assert.equal(scriptText[braceStart], '{', 'KNOWN_ALERTS is not declared as an object literal where expected')
  let depth = 0
  let end = braceStart
  for (; end < scriptText.length; end += 1) {
    if (scriptText[end] === '{') depth += 1
    if (scriptText[end] === '}') {
      depth -= 1
      if (depth === 0) {
        end += 1
        break
      }
    }
  }
  assert.equal(depth, 0, 'KNOWN_ALERTS object literal never closed (brace count did not return to zero)')
  const literal = scriptText.slice(braceStart, end)

  const entryPattern = /'([^']+\.ya?ml)':\s*\{\s*label:\s*'([^']*)',\s*titlePrefix:\s*'(\[[^\]]*\])'\s*\}/g
  const result = {}
  let match = entryPattern.exec(literal)
  while (match !== null) {
    const [, file, label, titlePrefix] = match
    result[file] = { label, titlePrefix }
    match = entryPattern.exec(literal)
  }
  assert.ok(
    Object.keys(result).length > 0,
    'no KNOWN_ALERTS entries parsed; the regex may be out of sync with the map shape'
  )
  return result
}

describe('KNOWN_ALERTS stays in sync with every ci-failure-issue adopter (repo-wide, ratcheted)', () => {
  // This replaces an earlier version of this test that hardcoded
  // 'dast-baseline-weekly.yml' as both the map key and the file path (task
  // D5, first review). That version was a real enforcing assertion for one
  // file, but it could not fail for the NEXT workflow that adopts the
  // shared action -- reproducing, inside the test suite, the exact defect
  // class this branch exists to find: a check that exists, reviews well,
  // and cannot fail when its subject breaks (task D5, second review).
  //
  // scheduled-health-rollup.yml's own header comment discovers its
  // scheduled-workflow population dynamically and says why: "so a newly
  // added `schedule:` trigger is covered automatically". Guarding a
  // dynamically discovered population with a hardcoded-filename test means
  // the guard's coverage does not grow with the thing it guards; every
  // future adopter would arrive untested, and silently, since the failure
  // mode is an `untracked` line in a rollup issue that reads like a known
  // gap rather than a regression.
  //
  // GRANDFATHERED is EMPTY, and the ratchet test below fails if it is not.
  //
  // It was seeded with four names -- e2e-staging.yml,
  // engagement-correlation.yml, usersim.yml, webkit-kid.yml -- on the claim
  // that they were "pre-existing gaps this task did not create". That claim
  // was false, and checkably so. At merge-base 1f121662 three of those files
  // DID NOT EXIST and the fourth, e2e-staging.yml, contained zero references
  // to ci-failure-issue. All four alerting call sites were added by this same
  // branch, which then exempted all four from the sync test it wrote to catch
  // exactly that omission. A ratchet whose starting notch is entirely debt
  // from its own commit records no inherited debt at all; it is the defect
  // wearing the remedy's clothes.
  //
  // All four now have correct KNOWN_ALERTS entries, so the set is empty.
  //
  // Keeping the empty set, rather than deleting the mechanism, is deliberate:
  // an escape hatch that is visible and asserted-against is safer than one
  // that gets reinvented ad hoc the next time a test is red on arrival. But
  // an empty set makes a `for (const file of GRANDFATHERED)` ratchet vacuous
  // -- it passes by iterating nothing, which is indistinguishable from
  // passing because the property holds. The assertion is therefore inverted:
  // it fails LOUDLY on a non-empty set rather than quietly on an empty one,
  // so the set can never grow, only stay at zero. Re-adding a name is not a
  // config change a reader might skim past; it is a red test that forces the
  // exemption to be argued for in a diff.
  const GRANDFATHERED = new Set([])

  const WORKFLOWS_DIR = join(HERE, '..')
  const SELF_FILE = 'scheduled-health-rollup.yml'

  // Same two-regex discovery contract scheduled-health-rollup.yml's own
  // "Discover scheduled workflows" comment documents and uses. Re-deriving
  // it here, rather than importing a shared helper, is deliberate: using
  // the rollup's OWN semantics (not a paraphrase of them) is what keeps
  // this test from drifting from its subject the way a copied fixture
  // would (see this file's top-of-file comment on why the script itself is
  // extracted rather than copied).
  function discoverScheduledWorkflows() {
    const files = readdirSync(WORKFLOWS_DIR).filter(
      (f) => /\.ya?ml$/.test(f) && f !== SELF_FILE && statSync(join(WORKFLOWS_DIR, f)).isFile()
    )
    const scheduled = []
    for (const file of files) {
      const text = readFileSync(join(WORKFLOWS_DIR, file), 'utf8')
      if (/^ {2}schedule:\s*$/m.test(text) && /cron:\s*['"][^'"]+['"]/.test(text)) {
        scheduled.push(file)
      }
    }
    return scheduled
  }

  // Slice each `uses: ./.github/actions/ci-failure-issue` call site at
  // greater indentation than the `uses:` line itself, stopping at the first
  // line that dedents back to or past it (the next step, or the end of the
  // job/file). Block-scoping the slice, rather than running `marker:` /
  // `label:` regexes over the whole file, is required, not a style choice:
  // a file-wide regex can match an unrelated field from a different step or
  // job (hit while prototyping this test; see the re-review).
  function extractCallSites(fileText) {
    const lines = fileText.split('\n')
    const sites = []
    for (let i = 0; i < lines.length; i += 1) {
      // `\s*$` was `$`-anchored against the bare path, so
      // `uses: ./.github/actions/ci-failure-issue # pinned` matched the
      // pre-filter in discoverAdopters but not here, yielding zero sites and a
      // `continue` that dropped the adopter silently. A trailing comment is
      // valid YAML and the repo pins other `uses:` lines exactly that way.
      const m = /^(\s*)uses:\s*\.\/\.github\/actions\/ci-failure-issue\s*(?:#.*)?$/.exec(
        lines[i]
      )
      if (!m) continue
      const usesIndent = m[1].length
      let end = lines.length
      for (let j = i + 1; j < lines.length; j += 1) {
        if (lines[j].trim() === '') continue
        const indent = /^(\s*)/.exec(lines[j])[1].length
        if (indent < usesIndent) {
          end = j
          break
        }
      }
      sites.push(lines.slice(i, end).join('\n'))
      i = end - 1
    }
    return sites
  }

  // The label character class needs digits: `e2e-alert`'s own literal
  // `e2e` contains a digit, so `[A-Za-z_-]` (no digits) silently fails to
  // match it (also hit while prototyping this test; see the re-review).
  function parseCallSite(block) {
    const markerMatch = /^\s*marker:\s*'(\[[^\]]+\])'/m.exec(block)
    const labelMatch = /^\s*label:\s*['"]?([A-Za-z0-9_-]+)['"]?\s*$/m.exec(block)
    const modeMatch = /^\s*mode:\s*['"]?([A-Za-z0-9_-]+)['"]?\s*$/m.exec(block)
    return {
      marker: markerMatch ? markerMatch[1] : null,
      label: labelMatch ? labelMatch[1] : 'ci-failure',
      mode: modeMatch ? modeMatch[1] : 'open',
    }
  }

  // The per-file half of discoverAdopters, split out so it can be exercised
  // against synthetic text. Neither shape the two tests below feed it exists in
  // the fleet today, so a fleet-only assertion could not fail on either defect.
  function openCallSites(fileText) {
    return extractCallSites(fileText)
      .map(parseCallSite)
      .filter((site) => site.mode !== 'resolve')
  }

  // Discover every scheduled workflow that calls the shared action to file
  // or update an issue (excludes `mode: resolve` call sites, which close
  // rather than open one).
  // `files` and `readText` are injectable so the adopter map itself can be
  // built over synthetic input. Without that, the truncation defect below was
  // unreachable by any assertion: every workflow in the fleet has exactly one
  // open call site, so keeping only the first was indistinguishable from
  // keeping all of them.
  function discoverAdopters(
    files = discoverScheduledWorkflows(),
    readText = (file) => readFileSync(join(WORKFLOWS_DIR, file), 'utf8')
  ) {
    const adopters = {}
    for (const file of files) {
      const text = readText(file)
      if (!/uses:\s*\.\/\.github\/actions\/ci-failure-issue/.test(text)) continue
      const openSites = openCallSites(text)
      if (openSites.length === 0) continue
      // Every open call site, not `openSites[0]`. A workflow with two
      // failure-reporting jobs files two different issues; keeping only the
      // first meant the second's marker and label were never checked against
      // KNOWN_ALERTS, and the rollup would report that issue as untracked
      // while every test here passed.
      adopters[file] = openSites
    }
    return adopters
  }

  const script = extractScript(ROLLUP_YML)
  const knownAlerts = extractKnownAlerts(script)
  const adopters = discoverAdopters()

  test('every non-grandfathered adopter has a KNOWN_ALERTS entry', () => {
    for (const [file, sites] of Object.entries(adopters)) {
      if (GRANDFATHERED.has(file)) continue
      const markers = sites.map((site) => site.marker).join(', ')
      assert.ok(
        knownAlerts[file],
        `${file} calls the shared ci-failure-issue action (markers ${markers}) but has no ` +
          'KNOWN_ALERTS entry in scheduled-health-rollup.yml; the rollup will report it as ' +
          'untracked even though it does file its own tracking issue.'
      )
    }
  })

  test("every discovered adopter's KNOWN_ALERTS entry (if any) matches its real marker and label", () => {
    // Covers grandfathered files too: if one later gains an entry, that
    // entry must still be correct, even though the ratchet test below will
    // also insist the file leave GRANDFATHERED at the same time.
    for (const [file, sites] of Object.entries(adopters)) {
      const entry = knownAlerts[file]
      if (!entry) continue
      // KNOWN_ALERTS holds ONE entry per file, so a file whose open call sites
      // disagree cannot be represented by it at all. Asserting the agreement
      // first is what makes the two comparisons below meaningful for every
      // site rather than for whichever one happened to be scanned first.
      const distinct = [...new Set(sites.map((site) => `${site.marker}|${site.label}`))]
      assert.equal(
        distinct.length,
        1,
        `${file} opens issues from ${distinct.length} different marker/label pairs ` +
          `(${distinct.join(' and ')}), but KNOWN_ALERTS can hold only one entry per file; ` +
          'the rollup will report every issue but the registered one as untracked.'
      )
      for (const site of sites) {
        assert.equal(
          entry.titlePrefix,
          site.marker,
          `${file}: KNOWN_ALERTS titlePrefix must match the marker it actually sets`
        )
        assert.equal(
          entry.label,
          site.label,
          `${file}: KNOWN_ALERTS label must match the label it actually sets`
        )
      }
    }
  })

  test('the grandfather list is empty and adding any name to it fails here (ratchet)', () => {
    // The ratchet, stated as the property it actually needs to hold rather
    // than as a loop over a list that is now empty. A per-file
    // `!knownAlerts[file]` loop over an empty set asserts nothing at all and
    // reports a pass, which is the exact "a check that exists, reviews well,
    // and cannot fail when its subject breaks" shape this branch exists to
    // remove.
    //
    // #VERIFY: add any filename to GRANDFATHERED and re-run this file; this
    // assertion must fail naming that file, whether or not the file has a
    // KNOWN_ALERTS entry, whether or not it exists, and whether or not it
    // adopts the shared action.
    assert.deepEqual(
      [...GRANDFATHERED].sort(),
      [],
      'GRANDFATHERED must stay empty. Every scheduled workflow that calls ' +
        '.github/actions/ci-failure-issue needs a KNOWN_ALERTS entry in ' +
        'scheduled-health-rollup.yml, or the rollup reports it UNTRACKED while its ' +
        'tracking issue sits open. Exempting a workflow instead of registering it ' +
        `is a deliberate regression in fleet coverage. Names present: ${[...GRANDFATHERED].join(', ')}`
    )
  })

  test('KNOWN_ALERTS has no entry for a file that is not a discovered adopter (deleted/renamed workflow)', () => {
    for (const file of Object.keys(knownAlerts)) {
      assert.ok(
        Object.prototype.hasOwnProperty.call(adopters, file),
        `KNOWN_ALERTS has an entry for ${file}, but it is not (or no longer) a discovered ` +
          'ci-failure-issue adopter; the entry is stale.'
      )
    }
  })

  // The discovery helpers themselves. Everything above asserts against the
  // live fleet, and the live fleet contains neither a commented `uses:` line
  // nor a two-issue workflow, so both defects these arms cover were invisible
  // to every fleet-scoped assertion in this file: discovery returned nothing
  // (or returned one of two), the loop iterated it, and the test passed.
  const TWO_SITE_FIXTURE = [
    'jobs:',
    '  alpha:',
    '    steps:',
    '      - name: File the alpha issue',
    '        uses: ./.github/actions/ci-failure-issue',
    '        with:',
    "          marker: '[alpha-alert]'",
    '          label: alpha-label',
    '  beta:',
    '    steps:',
    '      - name: File the beta issue',
    '        uses: ./.github/actions/ci-failure-issue',
    '        with:',
    "          marker: '[beta-alert]'",
    '          label: beta-label',
    '',
  ].join('\n')

  test('a call site whose uses: line carries a trailing YAML comment is still found', () => {
    const commented = TWO_SITE_FIXTURE.replace(
      'uses: ./.github/actions/ci-failure-issue\n        with:\n          marker: \'[alpha-alert]\'',
      "uses: ./.github/actions/ci-failure-issue # local composite\n        with:\n          marker: '[alpha-alert]'"
    )
    assert.notEqual(commented, TWO_SITE_FIXTURE, 'the fixture edit must have applied')
    const markers = openCallSites(commented).map((site) => site.marker)
    assert.deepEqual(markers, ['[alpha-alert]', '[beta-alert]'])
  })

  test('the adopter map keeps every open call site in a file, not just the first', () => {
    const synthetic = discoverAdopters(['two-issues.yml'], () => TWO_SITE_FIXTURE)
    assert.deepEqual(
      synthetic['two-issues.yml'].map((site) => site.marker),
      ['[alpha-alert]', '[beta-alert]']
    )
  })

  test('a file with two disagreeing call sites cannot be satisfied by one entry', () => {
    // The consequence of the arm above, stated as the property the KNOWN_ALERTS
    // comparison depends on. Without it a second, unregistered marker rides
    // along under the first one's entry.
    const sites = discoverAdopters(['two-issues.yml'], () => TWO_SITE_FIXTURE)['two-issues.yml']
    const distinct = [...new Set(sites.map((site) => `${site.marker}|${site.label}`))]
    assert.equal(distinct.length, 2)
  })

  // Two controls, so neither arm above can pass by matching everything.
  test('a resolve-mode call site is not an open one', () => {
    const resolving = TWO_SITE_FIXTURE.replace(
      "          marker: '[beta-alert]'",
      "          mode: resolve\n          marker: '[beta-alert]'"
    )
    assert.deepEqual(
      openCallSites(resolving).map((site) => site.marker),
      ['[alpha-alert]']
    )
  })

  test('a workflow calling a different action yields no call site', () => {
    assert.deepEqual(
      openCallSites(TWO_SITE_FIXTURE.replaceAll('ci-failure-issue', 'some-other-action')),
      []
    )
  })
})

/**
 * Every test above this point runs the EXTRACTED script and asserts on the
 * value it returns. That is the right contract for the script's logic, and it
 * is structurally blind to how the workflow YAML wires that value into an
 * issue. The rollup step returned a correct multi-line markdown string and
 * shipped it JSON-escaped for exactly that reason: fourteen passing tests, all
 * reading the raw return value, none of them able to see it.
 *
 * These tests read the YAML instead.
 */
describe('the YAML wiring around the script (invisible to every test above)', () => {
  const yamlText = readFileSync(ROLLUP_YML, 'utf8')

  /**
   * Block-scope each `uses: actions/github-script` step: from its `uses:` line
   * back up to the step's `- name:`, and forward to the first line that
   * dedents to or past the `- ` bullet. Same block-slicing reasoning as
   * extractCallSites above; a file-wide regex for `result-encoding` would be
   * satisfied by ANY step declaring it, which is precisely the assertion that
   * cannot fail when its subject breaks.
   */
  function githubScriptSteps(text) {
    const lines = text.split('\n')
    const steps = []
    for (let i = 0; i < lines.length; i += 1) {
      if (!/^\s*uses:\s*actions\/github-script@/.test(lines[i])) continue
      let start = i
      for (let j = i; j >= 0; j -= 1) {
        if (/^\s*- name:/.test(lines[j])) {
          start = j
          break
        }
      }
      const bulletIndent = /^(\s*)/.exec(lines[start])[1].length
      let end = lines.length
      for (let j = start + 1; j < lines.length; j += 1) {
        if (lines[j].trim() === '') continue
        if (/^(\s*)/.exec(lines[j])[1].length <= bulletIndent) {
          end = j
          break
        }
      }
      steps.push({ name: /^\s*- name:\s*(.*)$/.exec(lines[start])?.[1] ?? '?', block: lines.slice(start, end).join('\n') })
      i = end - 1
    }
    return steps
  }

  const steps = githubScriptSteps(yamlText)

  test('the step extraction found real github-script steps (anti-vacuity)', () => {
    // Without this, a broken extractor makes every assertion below iterate an
    // empty array and report a pass: the failure mode the brief's own
    // "vacuous discovery" note describes, reproduced one level up.
    assert.ok(steps.length >= 1, `expected at least one github-script step, found ${steps.length}`)
    assert.ok(
      steps.some((s) => /Compute the scheduled-workflow health rollup/.test(s.name)),
      `the rollup step was not among the extracted steps: ${steps.map((s) => s.name).join(' | ')}`
    )
  })

  test('every github-script step that returns a value declares result-encoding: string', () => {
    // github-script defaults to `result-encoding: json`, which sets the step
    // output to JSON.stringify(result). For a multi-line markdown body fed
    // straight into an issue that renders it as one double-quoted line of
    // literal \n. A bare `return;` (used here for the no-escalations early
    // exit) does not need the setting, so the detector requires a return WITH
    // a value rather than flagging the keyword.
    const valueReturning = steps.filter((s) => /^\s*return\s+[^;\s]/m.test(s.block))
    assert.ok(
      valueReturning.length >= 1,
      'no value-returning github-script step found; the `return <value>` detector is out of sync'
    )
    for (const step of valueReturning) {
      assert.match(
        step.block,
        /^\s*result-encoding:\s*string\s*$/m,
        `github-script step "${step.name}" returns a value but does not set ` +
          '`result-encoding: string`; its output will be JSON.stringify()d and any ' +
          'multi-line markdown will render as one escaped line.'
      )
    }
  })

  test('the issue body is fed from the step that sets result-encoding', () => {
    // Pins the two halves together. `result-encoding: string` on some other
    // step would satisfy the test above while `body:` still consumed a
    // JSON-encoded output from a different one.
    const rollup = steps.find((s) => /Compute the scheduled-workflow health rollup/.test(s.name))
    assert.ok(rollup, 'the rollup step disappeared')
    assert.match(rollup.block, /^\s*id:\s*rollup\s*$/m)
    assert.match(rollup.block, /^\s*result-encoding:\s*string\s*$/m)
    assert.match(yamlText, /body:\s*\$\{\{\s*steps\.rollup\.outputs\.result\s*\}\}/)
    assert.match(yamlText, /comment-body:\s*\$\{\{\s*steps\.rollup\.outputs\.result\s*\}\}/)
  })
})

/**
 * The watchdog needs a watchdog. Before this, the workflow had one job, no
 * failure alerting, and excluded itself from its own survey, so a single throw
 * would have made it red every Thursday forever with nobody notified: the
 * 32-consecutive-red-nights failure this branch exists to eliminate,
 * reproduced inside the thing built to eliminate it.
 */
describe('the rollup workflow alerts on its own failure', () => {
  const doc = readFileSync(ROLLUP_YML, 'utf8')

  function jobBlock(name) {
    const lines = doc.split('\n')
    const start = lines.findIndex((l) => new RegExp(`^  ${name}:\\s*$`).test(l))
    if (start === -1) return null
    let end = lines.length
    for (let j = start + 1; j < lines.length; j += 1) {
      if (lines[j].trim() === '') continue
      if (/^ {2}\S/.test(lines[j])) {
        end = j
        break
      }
    }
    return lines.slice(start, end).join('\n')
  }

  test('an alert job exists and is gated on failure() || cancelled()', () => {
    const alert = jobBlock('alert')
    assert.ok(alert, 'scheduled-health-rollup.yml declares no `alert:` job')
    // `failure()` alone is FALSE for a cancelled run. This workflow now sets
    // `cancel-in-progress: false`, so cancellation is no longer routine here,
    // but a manual cancel and a runner eviction still produce it, and neither
    // is reported by `failure()`.
    assert.match(
      alert,
      /^\s*if:\s*failure\(\)\s*\|\|\s*cancelled\(\)\s*$/m,
      'the alert job must be gated on `failure() || cancelled()`; `failure()` alone ' +
        'never fires for a cancelled run, and a cancelled survey is the outcome ' +
        'this workflow least wants to lose.'
    )
    assert.match(alert, /^\s*needs:\s*rollup\s*$/m)
  })

  test('the alert job actually files an issue, under its own marker', () => {
    const alert = jobBlock('alert')
    assert.match(
      alert,
      /uses:\s*\.\/\.github\/actions\/ci-failure-issue/,
      'the alert job must file a tracking issue; a red job nobody is notified about is ' +
        'the failure mode this workflow exists to end.'
    )
    // The SAME marker the report leg uses.
    // tests/unit/test_ci_failure_action_contract.py::test_each_workflow_uses_one_marker
    // enforces one marker per workflow repo-wide; a distinct
    // `[health-rollup-watchdog]` was tried first and that contract rejected it.
    assert.match(alert, /marker:\s*'\[health-rollup\]'/)
    assert.match(alert, /^\s*issues:\s*write\s*$/m)
  })
})

/**
 * The prose in scheduled-health-rollup.yml makes three claims about the fleet
 * that a reader would take at face value and that nothing read: how many
 * scheduled workflows exist, how many adopt the shared alert action, and which
 * ones adopt nothing. All three were wrong on arrival (23 surveyed against 28
 * scheduled, "fourteen" adopters against 20, "twenty-seven" against 28), and a
 * fourth claim, that Thursday carries no other weekly job, had been falsified
 * by dast-baseline-weekly.yml taking Thursday 08:20.
 *
 * A comment cannot be made to fail, so these tests re-derive each number from
 * the directory and compare. The prose is now a cache of a computed value,
 * with something that invalidates it.
 */
describe('cronsCollide sees every field syntax GitHub actually accepts', () => {
  // The detector that re-proves this workflow's cron slot is only worth the
  // line it occupies if it can SEE a collision. Its first version compared
  // the minute field with a bare `===`, and split the hour and day-of-week
  // fields on commas only, so a range or a step in any field read as "no
  // overlap" and the slot check silently passed. Each RED case below is a
  // cron GitHub schedules perfectly happily that the first version missed.

  describe('ranges', () => {
    test('a day-of-week range overlapping the self day is a collision', () => {
      // `1-5` is Mon-Fri; a Monday job is inside it.
      assert.equal(cronsCollide('0 7 * * 1', '0 7 * * 1-5'), true)
    })

    test('an hour range overlapping the self hour is a collision', () => {
      assert.equal(cronsCollide('0 7 * * 1', '0 6-8 * * 1'), true)
    })

    test('a minute range overlapping the self minute is a collision', () => {
      assert.equal(cronsCollide('30 7 * * 1', '15-45 7 * * 1'), true)
    })
  })

  describe('steps', () => {
    test('an hour step landing on the self hour is a collision', () => {
      // `*/2` is every even hour; 08:00 is one of them.
      assert.equal(cronsCollide('0 8 * * 1', '0 */2 * * 1'), true)
    })

    test('a minute step landing on the self minute is a collision', () => {
      // `*/15` is :00, :15, :30, :45.
      assert.equal(cronsCollide('0 7 * * 1', '*/15 7 * * 1'), true)
    })

    test('a range-with-step landing on the self value is a collision', () => {
      // `1-5/2` is Mon, Wed, Fri.
      assert.equal(cronsCollide('0 7 * * 3', '0 7 * * 1-5/2'), true)
    })

    test('a combination of list, range and step is a collision', () => {
      // The `1-5,0` shape: Mon-Fri plus Sunday. Saturday is the only day out.
      assert.equal(cronsCollide('0 7 * * 0', '0 7 * * 1-5,0'), true)
    })

    test('a day-of-week step from a start value does not invent a phantom Sunday', () => {
      // `5/2` is Friday, stepping by 2 from there; the count must stop at
      // Saturday (6), the highest real day, not run up to a literal 7. 7 is
      // only an alias for Sunday (already representable as 0), not an eighth
      // day to step through. Before the fix this returned {5, 0} because the
      // step counted up to hi (7) and 7 then normalised to 0, inventing a
      // Sunday the term "5/2" never named.
      assert.deepEqual([...expandCronDow('5/2')].sort(), [5])
    })

    test('a day-of-week step from a start value does not collide with Sunday', () => {
      // Same defect, seen through the public API: Friday-stepping-by-2 must
      // not read as sharing Sunday's slot.
      assert.equal(cronsCollide('0 6 * * 0', '0 6 * * 5/2'), false)
    })
  })

  describe('the minute field is treated exactly like the others', () => {
    test('a comma list in the minute field is a collision', () => {
      // Bare `===` made this the one field where a list could not match.
      assert.equal(cronsCollide('0 7 * * 4', '0,30 7 * * 4'), true)
    })
  })

  describe('detection does not depend on argument order', () => {
    test('a collision found one way round is found the other way round', () => {
      // The first version read the hour list off ONE side only, so whether a
      // collision was visible depended on which cron was passed first. The
      // fleet loop always passes self first, which is exactly how an
      // asymmetric bug survives: the one call site never exercises it.
      const self = '0 5,11,17,23 * * *'
      const other = '0 11 * * 4'
      assert.equal(cronsCollide(other, self), true, 'baseline direction')
      assert.equal(cronsCollide(self, other), true, 'reversed direction')
    })
  })

  describe('day-of-week 0 and 7 are both Sunday', () => {
    test('0 and 7 in the day-of-week field collide', () => {
      assert.equal(cronsCollide('0 6 * * 0', '0 6 * * 7'), true)
    })
  })

  describe('CONTROL: things that genuinely do not overlap stay non-collisions', () => {
    // Without these, the fix could degenerate into "everything collides",
    // which passes every RED case above and makes the fleet test useless in
    // the opposite direction.

    test('a day outside a range is not a collision', () => {
      // Saturday is not in Mon-Fri.
      assert.equal(cronsCollide('0 7 * * 6', '0 7 * * 1-5'), false)
    })

    test('an odd hour does not collide with an every-even-hour step', () => {
      assert.equal(cronsCollide('0 9 * * 1', '0 */2 * * 1'), false)
    })

    test('a minute outside a step series is not a collision', () => {
      assert.equal(cronsCollide('7 7 * * 1', '*/15 7 * * 1'), false)
    })

    test("the rollup's real slot does not collide with its nearest neighbour", () => {
      // Thursday 07:00 against dast-baseline-weekly's Thursday 08:20 and
      // supabase-backup's daily 08:00: same day, distinct hour.
      assert.equal(cronsCollide('0 7 * * 4', '20 8 * * 4'), false)
      assert.equal(cronsCollide('0 7 * * 4', '0 8 * * *'), false)
    })
  })

  describe('REGRESSION: the comma lists that already worked still work', () => {
    test('an hour comma list containing the self hour is a collision', () => {
      // kws-delivery-health.yml's real shape.
      assert.equal(cronsCollide('0 11 * * 4', '0 5,11,17,23 * * *'), true)
    })

    test('a day-of-week comma list containing the self day is a collision', () => {
      assert.equal(cronsCollide('0 7 * * 4', '0 7 * * 2,4'), true)
    })

    test('a wildcard day on either side is a collision', () => {
      assert.equal(cronsCollide('0 7 * * 4', '0 7 * * *'), true)
      assert.equal(cronsCollide('0 7 * * *', '0 7 * * 4'), true)
    })
  })

  describe('a field it cannot reason about is loud, not silently blind', () => {
    // The defect being removed here is a check that cannot fail when its
    // subject breaks. Returning `false` for an unparseable field would
    // rebuild exactly that, so these throw instead.

    test('an unparseable field throws rather than reporting no collision', () => {
      assert.throws(() => cronsCollide('0 7 * * 4', '0 7 * * MON'), /unparseable cron field/)
    })

    test('a non-wildcard day-of-month throws rather than being ignored', () => {
      assert.throws(() => cronsCollide('0 7 * * 4', '0 7 1 * *'), /day-of-month|month/)
    })
  })
})

describe('the fleet claims in the rollup workflow are true of the real fleet', () => {
  const WORKFLOWS_DIR = join(HERE, '..')
  const SELF_FILE = 'scheduled-health-rollup.yml'
  const yamlText = readFileSync(ROLLUP_YML, 'utf8')

  const NUMBER_WORDS = {
    zero: 0,
    one: 1,
    two: 2,
    three: 3,
    four: 4,
    five: 5,
    six: 6,
    seven: 7,
    eight: 8,
    nine: 9,
    ten: 10,
    eleven: 11,
    twelve: 12,
    thirteen: 13,
    fourteen: 14,
    fifteen: 15,
    sixteen: 16,
    seventeen: 17,
    eighteen: 18,
    nineteen: 19,
    twenty: 20,
    'twenty-one': 21,
    'twenty-two': 22,
    'twenty-three': 23,
    'twenty-four': 24,
    'twenty-five': 25,
    'twenty-six': 26,
    'twenty-seven': 27,
    'twenty-eight': 28,
    'twenty-nine': 29,
    thirty: 30,
  }

  /**
   * @param {string} word A number word as written in the workflow's prose.
   * @returns {number} Its value.
   */
  function wordToNumber(word) {
    const value = NUMBER_WORDS[word.toLowerCase()]
    assert.notEqual(
      value,
      undefined,
      `the rollup's prose uses the number word "${word}", which this test cannot ` +
        'read; extend NUMBER_WORDS rather than deleting the assertion.'
    )
    return value
  }

  /**
   * @returns {string[]} Every scheduled workflow filename except this one.
   */
  function scheduledExcludingSelf() {
    return readdirSync(WORKFLOWS_DIR)
      .filter(
        (f) => /\.ya?ml$/.test(f) && f !== SELF_FILE && statSync(join(WORKFLOWS_DIR, f)).isFile()
      )
      .filter((f) => {
        const text = readFileSync(join(WORKFLOWS_DIR, f), 'utf8')
        return /^ {2}schedule:\s*$/m.test(text) && /cron:\s*['"][^'"]+['"]/.test(text)
      })
  }

  /**
   * @param {string} file A workflow filename.
   * @returns {boolean} Whether it calls the shared alert action.
   */
  function callsSharedAction(file) {
    return /uses:\s*\.\/\.github\/actions\/ci-failure-issue/.test(
      readFileSync(join(WORKFLOWS_DIR, file), 'utf8')
    )
  }

  /**
   * @param {string} file A workflow filename.
   * @returns {string[]} Its cron expressions.
   */
  function cronsOf(file) {
    const text = readFileSync(join(WORKFLOWS_DIR, file), 'utf8')
    return [...text.matchAll(/cron:\s*['"]([^'"]+)['"]/g)].map((m) => m[1])
  }

  test('the discovery itself is not vacuous', () => {
    // Without this, every count assertion below could pass by comparing zero
    // to zero after a discovery regression.
    const scheduled = scheduledExcludingSelf()
    assert.ok(scheduled.length > 10, `expected a real fleet, found ${scheduled.length}`)
    assert.ok(scheduled.some(callsSharedAction), 'expected at least one adopter')
    assert.deepEqual(cronsOf(SELF_FILE), ['0 7 * * 4'])
  })

  test("this workflow's cron slot collides with no other scheduled workflow", () => {
    // The claim the cron-slot comment makes, re-derived. A collision is two
    // crons sharing minute, hour, and a day-of-week (`*` matching any day).
    const [selfCron] = cronsOf(SELF_FILE)
    const collisions = []
    for (const file of scheduledExcludingSelf()) {
      for (const cron of cronsOf(file)) {
        if (cronsCollide(selfCron, cron)) {
          collisions.push(`${file} (${cron})`)
        }
      }
    }
    assert.deepEqual(
      collisions,
      [],
      `this workflow's slot (${selfCron}) now starts alongside: ${collisions.join(', ')}. ` +
        'Move the slot, or the survey competes for a runner with the job it surveys.'
    )
  })

  test('the stated adopter count matches the real one', () => {
    const match = /\/\/ generic pattern\. ([A-Za-z-]+) scheduled workflows share this/.exec(
      yamlText
    )
    assert.ok(match, 'the adopter-count sentence is gone or reworded; update this test with it')
    const stated = wordToNumber(match[1])
    const actual = scheduledExcludingSelf().filter(callsSharedAction).length
    assert.equal(
      stated,
      actual,
      `the rollup says ${stated} scheduled workflows adopt the shared action; ${actual} do.`
    )
  })

  test('the stated non-adopter count and the named files match the real ones', () => {
    const match =
      /Only the following ([A-Za-z-]+) of the ([A-Za-z-]+) scheduled\s*\n\s*\/\/ workflows in this repo/.exec(
        yamlText
      )
    assert.ok(match, 'the non-adopter sentence is gone or reworded; update this test with it')
    const scheduled = scheduledExcludingSelf()
    const nonAdopters = scheduled.filter((f) => !callsSharedAction(f)).sort()
    assert.equal(
      wordToNumber(match[2]),
      scheduled.length,
      `the rollup says ${match[2]} scheduled workflows (excluding itself); there are ${scheduled.length}.`
    )
    assert.equal(
      wordToNumber(match[1]),
      nonAdopters.length,
      `the rollup says ${match[1]} file no tracking issue; ${nonAdopters.length} do not.`
    )
    // The list, not only its length: a swap of one name for another keeps the
    // count right and the claim wrong.
    const sentenceEnd = yamlText.indexOf('Keep this map in sync', match.index)
    assert.ok(sentenceEnd > match.index, 'the sentence terminator moved; update this test')
    const sentence = yamlText.slice(match.index, sentenceEnd)
    const named = [...sentence.matchAll(/([a-z0-9-]+\.ya?ml)/g)].map((m) => m[1]).sort()
    assert.deepEqual(
      [...new Set(named)],
      nonAdopters,
      'the workflows the rollup names as filing no tracking issue are not the ones that file none.'
    )
  })

  test('the workflow does not cancel its own weekly survey', () => {
    // #VERIFY: flip `cancel-in-progress` back to `true` in
    // scheduled-health-rollup.yml and re-run this file; this assertion must
    // fail. A `workflow_dispatch` fired mid-survey used to kill the cron run
    // outright, losing that week's report, which is the silence this workflow
    // exists to detect.
    assert.match(
      yamlText,
      /^\s*cancel-in-progress:\s*false\s*$/m,
      'scheduled-health-rollup.yml must set `cancel-in-progress: false`; a cancelled ' +
        'cron run produces no survey at all for that week.'
    )
    assert.doesNotMatch(yamlText, /^\s*cancel-in-progress:\s*true\s*$/m)
  })

  test('the prose about cancellation matches the setting', () => {
    // The three sentences that argued FROM `cancel-in-progress: true`. A
    // setting flipped without its rationale leaves a file that contradicts
    // itself, and a reader believes the prose.
    assert.doesNotMatch(
      yamlText,
      /cancel-in-progress: true/,
      'the workflow still argues from `cancel-in-progress: true` somewhere in its prose.'
    )
  })
})
