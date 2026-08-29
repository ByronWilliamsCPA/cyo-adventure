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
      const m = /^(\s*)uses:\s*\.\/\.github\/actions\/ci-failure-issue\s*$/.exec(lines[i])
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

  // Discover every scheduled workflow that calls the shared action to file
  // or update an issue (excludes `mode: resolve` call sites, which close
  // rather than open one).
  function discoverAdopters() {
    const adopters = {}
    for (const file of discoverScheduledWorkflows()) {
      const text = readFileSync(join(WORKFLOWS_DIR, file), 'utf8')
      if (!/uses:\s*\.\/\.github\/actions\/ci-failure-issue/.test(text)) continue
      const openSites = extractCallSites(text)
        .map(parseCallSite)
        .filter((site) => site.mode !== 'resolve')
      if (openSites.length === 0) continue
      adopters[file] = openSites[0]
    }
    return adopters
  }

  const script = extractScript(ROLLUP_YML)
  const knownAlerts = extractKnownAlerts(script)
  const adopters = discoverAdopters()

  test('every non-grandfathered adopter has a KNOWN_ALERTS entry', () => {
    for (const [file, site] of Object.entries(adopters)) {
      if (GRANDFATHERED.has(file)) continue
      assert.ok(
        knownAlerts[file],
        `${file} calls the shared ci-failure-issue action (marker ${site.marker}) but has no ` +
          'KNOWN_ALERTS entry in scheduled-health-rollup.yml; the rollup will report it as ' +
          'untracked even though it does file its own tracking issue.'
      )
    }
  })

  test("every discovered adopter's KNOWN_ALERTS entry (if any) matches its real marker and label", () => {
    // Covers grandfathered files too: if one later gains an entry, that
    // entry must still be correct, even though the ratchet test below will
    // also insist the file leave GRANDFATHERED at the same time.
    for (const [file, site] of Object.entries(adopters)) {
      const entry = knownAlerts[file]
      if (!entry) continue
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
    // `failure()` alone is FALSE for a cancelled run, and this workflow sets
    // `cancel-in-progress: true`, so cancellation is a routine outcome here.
    assert.match(
      alert,
      /^\s*if:\s*failure\(\)\s*\|\|\s*cancelled\(\)\s*$/m,
      'the alert job must be gated on `failure() || cancelled()`; `failure()` alone ' +
        'never fires for a cancelled run, and this workflow cancels itself by design.'
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
