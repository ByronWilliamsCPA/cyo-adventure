// SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
//
// SPDX-License-Identifier: MIT

// Executable contract for ../extract-failing-specs.mjs (task A7-i review,
// Important 2).
//
// Unlike ../../../.github/workflows/test/health-rollup.test.mjs and
// ../../../.github/actions/ci-failure-issue/test/reconcile.test.mjs, the
// script under test here is not a `script: |` block embedded in workflow
// YAML: it is a plain, directly-invokable `.mjs` file whose `main()` runs
// unconditionally at import time against `process.argv`. Importing it as an
// ES module would therefore run it immediately against THIS test runner's
// own argv rather than a fixture, so there is no `extractScript` step and no
// `AsyncFunction` wrapper here. Every case below instead spawns the real
// script as a child process, exactly as `e2e-staging.yml`,
// `e2e-real-nightly.yml`, and `e2e-prod.yml` do, and asserts against its
// real stdout and real exit code, never against internals reached by
// importing the module directly.
//
// Before this file existed, this script's two load-bearing properties were
// each held by nothing mechanical:
//   - the security property (only `spec.file`/`spec.title` are ever read off
//     a report; `results[].error` text, `stdout`/`stderr`/`attachments`, and
//     any top-level `errors[].message` are never emitted, since this
//     script's output is embedded verbatim into a world-readable GitHub
//     issue on a PUBLIC repository) was enforced only by the script's own
//     `#CRITICAL` comment saying a violation "must be rejected in review"
//   - the failure-discrimination property (`spec.ok === false` is the sole
//     failure signal; flaky-passed and skipped specs, both `ok: true`, are
//     excluded) was enforced by nothing at all
//
// This file also carries the regression test for Important 1: a report that
// parses as valid JSON but has the wrong shape (`{"suites": 5}`) must fall
// to the "did not have the expected shape" line, not be silently read as a
// valid, empty, all-passed report, and that must not regress the genuinely
// empty, validly-shaped case.
//
// Run: node --test frontend/scripts/test/extract-failing-specs.test.mjs

import { strict as assert } from 'node:assert'
import { test, describe } from 'node:test'
import { spawnSync } from 'node:child_process'
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const SCRIPT = join(HERE, '..', 'extract-failing-specs.mjs')

/** Build a minimal, real-shaped Playwright JSON report from spec descriptors. */
function report(specs, { errors = [] } = {}) {
  return {
    suites: [
      {
        title: 'fixture suite',
        specs,
        suites: [],
      },
    ],
    errors,
  }
}

/**
 * A spec entry as the Playwright JSON reporter would emit it. `error`, when
 * given, lands in `results[0].error.message`: a field this script must never
 * read, so tests use it to prove that, not to describe realistic failures.
 */
function spec({ file = 'e2e/fixture.spec.ts', title = 'fixture test', ok, error } = {}) {
  return {
    file,
    title,
    ok,
    results: error === undefined ? [] : [{ status: 'failed', error: { message: error } }],
  }
}

/**
 * Run the real script as a child process against a fixture report file.
 *
 * Returns both the exit status and stdout: the script's one documented
 * contract is "always exits 0 and always prints something usable", so a
 * test that only checked stdout could not catch a regression to a nonzero
 * exit, and vice versa.
 *
 * `reportContents === undefined` means "invoke with no report-path argument
 * at all" (the missing-argument branch), distinct from a report path that
 * points at a file that was never written (the absent-report branch, tested
 * separately below since it must NOT create that file).
 */
function run(reportContents, extraArgs = []) {
  const dir = mkdtempSync(join(tmpdir(), 'extract-failing-specs-'))
  try {
    const args = []
    if (reportContents !== undefined) {
      const reportPath = join(dir, 'report.json')
      // #ASSUME: security: reportPath is built from a directory this test just
      // created with mkdtempSync, never from user/event input; the "non
      // literal" flag here is the fixture path, not attacker-controlled data.
      // #VERIFY: keep this write scoped to a freshly minted temp directory.
      // eslint-disable-next-line security/detect-non-literal-fs-filename -- reportPath is this test's own freshly minted temp path, never event input
      writeFileSync(reportPath, reportContents)
      args.push(reportPath, ...extraArgs)
    }
    const result = spawnSync(process.execPath, [SCRIPT, ...args], { encoding: 'utf8' })
    return { status: result.status, stdout: result.stdout }
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
}

describe('the harness is actually testing the real script', () => {
  test('the script file exists at the expected path and runs', () => {
    const { status, stdout } = run(JSON.stringify(report([])))
    assert.equal(status, 0)
    assert.match(stdout, /parsed cleanly/)
  })
})

describe('failure discrimination: spec.ok === false only', () => {
  test('a genuine failure is reported; flaky-passed and skipped specs are not', () => {
    const r = report([
      spec({ file: 'e2e/a.spec.ts', title: 'fails', ok: false }),
      spec({ file: 'e2e/b.spec.ts', title: 'flaky then passed', ok: true }),
      spec({ file: 'e2e/c.spec.ts', title: 'skipped', ok: true }),
    ])
    const { status, stdout } = run(JSON.stringify(r))

    assert.equal(status, 0)
    assert.match(stdout, /^1 spec failed:/m)
    assert.match(stdout, /- e2e\/a\.spec\.ts > fails/)
    assert.doesNotMatch(stdout, /flaky then passed/)
    assert.doesNotMatch(stdout, /skipped/)
  })

  test('a failing spec nested under a describe chain (a child suite) is still found', () => {
    const nested = {
      suites: [
        {
          title: 'outer describe',
          specs: [],
          suites: [
            {
              title: 'inner describe',
              specs: [spec({ file: 'e2e/nested.spec.ts', title: 'nested fails', ok: false })],
              suites: [],
            },
          ],
        },
      ],
      errors: [],
    }
    const { status, stdout } = run(JSON.stringify(nested))

    assert.equal(status, 0)
    assert.match(stdout, /- e2e\/nested\.spec\.ts > nested fails/)
  })
})

describe('the cap', () => {
  test('more failures than the cap yields exactly the cap plus an explicit omitted count', () => {
    const specs = Array.from({ length: 5 }, (_, i) =>
      spec({ file: `e2e/f${i}.spec.ts`, title: `fails ${i}`, ok: false })
    )
    const { status, stdout } = run(JSON.stringify(report(specs)), ['--cap', '3'])

    assert.equal(status, 0)
    assert.match(stdout, /^5 specs failed:/m)
    const shown = stdout.match(/^- e2e\/f\d+\.spec\.ts >/gm) ?? []
    assert.equal(shown.length, 3, `expected exactly 3 listed, got ${shown.length}`)
    assert.match(stdout, /- \.\.\.and 2 more not shown \(capped at 3\)\.$/m)
  })

  test('fewer failures than the cap are never truncated and carry no omitted-count line', () => {
    const specs = [spec({ file: 'e2e/only.spec.ts', title: 'fails', ok: false })]
    const { stdout } = run(JSON.stringify(report(specs)), ['--cap', '20'])

    assert.doesNotMatch(stdout, /not shown/)
  })
})

describe('degraded paths', () => {
  test('a missing report-path argument prints an explanatory line and exits 0', () => {
    const { status, stdout } = run(undefined)
    assert.equal(status, 0)
    assert.match(stdout, /No report path was given to extract-failing-specs\.mjs/)
  })

  test('an absent report file falls back and exits 0', () => {
    const dir = mkdtempSync(join(tmpdir(), 'extract-failing-specs-absent-'))
    const missing = join(dir, 'does-not-exist.json')
    let result
    try {
      result = spawnSync(process.execPath, [SCRIPT, missing], { encoding: 'utf8' })
    } finally {
      rmSync(dir, { recursive: true, force: true })
    }

    assert.equal(result.status, 0)
    assert.match(result.stdout, /No Playwright JSON report found at/)
    assert.match(result.stdout, /Falling back to generic failure detail/)
  })

  test('unparseable JSON falls back and exits 0', () => {
    const { status, stdout } = run('{not json')
    assert.equal(status, 0)
    assert.match(stdout, /could not be parsed; falling back to generic failure detail/)
  })

  describe('wrong shape (Important 1 regression)', () => {
    test('{"suites": 5} is reported as the wrong shape, not a clean empty report', () => {
      const { status, stdout } = run(JSON.stringify({ suites: 5 }))
      assert.equal(status, 0)
      assert.match(
        stdout,
        /did not have the expected shape; falling back to generic failure detail/
      )
      assert.doesNotMatch(stdout, /parsed cleanly/)
    })

    test('a suites array holding non-object entries falls back to the same shape line', () => {
      const { status, stdout } = run(JSON.stringify({ suites: [5, 'bad', null] }))
      assert.equal(status, 0)
      assert.match(
        stdout,
        /did not have the expected shape; falling back to generic failure detail/
      )
    })

    test('a top-level JSON array is reported as the wrong shape', () => {
      const { status, stdout } = run(JSON.stringify([1, 2, 3]))
      assert.equal(status, 0)
      assert.match(
        stdout,
        /did not have the expected shape; falling back to generic failure detail/
      )
    })

    test('a genuinely empty, validly-shaped report is still reported clean, not a shape violation', () => {
      const { status, stdout } = run(JSON.stringify({ suites: [] }))
      assert.equal(status, 0)
      assert.match(stdout, /^The Playwright report parsed cleanly and recorded no failing spec\.$/m)
    })
  })
})

describe('security: only file/title ever reach stdout', () => {
  test('a results[].error message on a failing spec never reaches stdout', () => {
    const secret = 'DO-NOT-LEAK-THIS-RESPONSE-BODY-abc123'
    const r = report([
      spec({
        file: 'e2e/leaky.spec.ts',
        title: 'fails with a loud error',
        ok: false,
        error: secret,
      }),
    ])
    const { status, stdout } = run(JSON.stringify(r))

    assert.equal(status, 0)
    assert.match(stdout, /e2e\/leaky\.spec\.ts > fails with a loud error/)
    // A plain substring check, not a constructed RegExp: the point is that
    // this exact literal text never appears, and a fixed string search says
    // that directly without building a pattern out of test data.
    assert.equal(stdout.includes(secret), false)
  })

  test('top-level errors are counted but their message text is never quoted', () => {
    const secretSetupError = 'webServer failed to start: DATABASE_URL=postgres://leak-me'
    const r = report([], { errors: [{ message: secretSetupError }, { message: secretSetupError }] })
    const { status, stdout } = run(JSON.stringify(r))

    assert.equal(status, 0)
    assert.match(stdout, /2 top-level error\(s\) were reported/)
    assert.doesNotMatch(stdout, /leak-me/)
    assert.doesNotMatch(stdout, /DATABASE_URL/)
  })
})
