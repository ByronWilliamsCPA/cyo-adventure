// SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
//
// SPDX-License-Identifier: MIT

/**
 * Tests for `frontend/scripts/check-artifact-upload-safety.mjs`.
 *
 * The subject is a security control, so every arm here is written to answer
 * "does this go RED when the thing it guards breaks?", not "does it pass
 * today?". A control that passes both with and without the fix is the defect
 * class this suite exists to remove.
 *
 * The fixture values below are obviously-synthetic markers, never a real or
 * partial credential.
 */

import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import test from 'node:test'

import {
  classifyUploadPath,
  findSecretBearingWholesaleUploads,
  findWholesaleUploads,
  injectsSecrets,
  parseUploadSteps,
  scanForCredentials,
} from '../check-artifact-upload-safety.mjs'

const WORKFLOWS_DIR = new URL('../../../.github/workflows', import.meta.url).pathname
const CHECKER = new URL('../check-artifact-upload-safety.mjs', import.meta.url).pathname

/** An obviously synthetic stand-in. Never a real or partial credential. */
const FIXTURE_VALUE = 'ZZ-FIXTURE-NOT-A-REAL-CREDENTIAL-0000'

/*
 * `writeFixture` is the only filesystem write in this file, so the
 * `security/detect-non-literal-fs-filename` justification is stated once here
 * rather than at every call site: every path it builds is rooted at a
 * `mkdtempSync` directory created moments earlier in this same process, and
 * every relative path passed to it is a literal written below. No value
 * reaches it from a request, an argument, or the environment.
 */

/**
 * @param {string} dir Fixture root, from `mkdtempSync`.
 * @param {string} relativePath Literal path under that root.
 * @param {string} contents File contents.
 * @returns {void}
 */
function writeFixture(dir, relativePath, contents) {
  const full = join(dir, relativePath)
  const parent = dirname(full)
  if (parent !== dir) {
    // eslint-disable-next-line security/detect-non-literal-fs-filename -- see the block comment above: mkdtemp root plus a literal
    mkdirSync(parent, { recursive: true })
  }
  // eslint-disable-next-line security/detect-non-literal-fs-filename -- see the block comment above: mkdtemp root plus a literal
  writeFileSync(full, contents)
}

/**
 * @param {(dir: string) => void} populate Writes the fixture tree.
 * @returns {Array<{file: string, patternId: string}>} scanForCredentials output.
 */
function scanFixture(populate) {
  const dir = mkdtempSync(join(tmpdir(), 'artifact-safety-'))
  try {
    populate(dir)
    return scanForCredentials(dir)
  } finally {
    rmSync(dir, { recursive: true, force: true })
  }
}

test('the content oracle', async (t) => {
  await t.test(
    'reports an error-context.md carrying a password value, the file that actually leaked',
    () => {
      // This is the exact shape found inside three published
      // `e2e-staging-traces` artifacts, on a tier that already had
      // trace/screenshot/video all set to 'off'.
      const findings = scanFixture((dir) => {
        writeFixture(
          dir,
          'device-grant-sweep-staging-chromium/error-context.md',
          ['# Page snapshot', '```yaml', '- textbox "Password": ' + FIXTURE_VALUE, '```', ''].join(
            '\n'
          )
        )
      })
      assert.equal(findings.length, 1)
      assert.equal(findings[0].patternId, 'accessibility-snapshot-password-value')
      assert.match(findings[0].file, /error-context\.md$/)
    }
  )

  await t.test('reports a bearer header and a JWT', () => {
    const findings = scanFixture((dir) => {
      writeFixture(
        dir,
        'network.txt',
        'authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ6eiJ9.zzzz\n'
      )
    })
    const ids = findings.map((finding) => finding.patternId).sort()
    assert.deepEqual(ids, ['bearer-header', 'jwt'])
  })

  await t.test('reports a Supabase auth-token cookie', () => {
    const findings = scanFixture((dir) => {
      writeFixture(dir, 'state.json', '{"name":"sb-abcdefghij-auth-token","value":"x"}')
    })
    assert.deepEqual(
      findings.map((finding) => finding.patternId),
      ['supabase-auth-token-cookie']
    )
  })

  // Without these two arms the oracle could be vacuously red, which is just as
  // useless as vacuously green: it would flag every directory and so justify
  // nothing.
  await t.test('stays silent on the files a hardened tier actually leaves behind', () => {
    const findings = scanFixture((dir) => {
      writeFixture(dir, '.last-run.json', '{"status":"failed","failedTests":["abc"]}')
      writeFixture(dir, 'leaked-device-grants.jsonl', '{"profileId":"p1","confirmed":false}\n')
    })
    assert.deepEqual(findings, [])
  })

  await t.test(
    'stays silent on prose that merely mentions a password, and on a masked field',
    () => {
      const findings = scanFixture((dir) => {
        writeFixture(
          dir,
          'notes.md',
          [
            'The password is never written to this file.',
            '- textbox "Password"',
            'authorization: Bearer',
            '',
          ].join('\n')
        )
      })
      assert.deepEqual(findings, [])
    }
  )
})

test('the upload-path classifier', async (t) => {
  await t.test('calls a Playwright output directory wholesale', () => {
    assert.equal(classifyUploadPath('frontend/test-results/'), 'wholesale')
    assert.equal(classifyUploadPath('frontend/test-results'), 'wholesale')
    assert.equal(classifyUploadPath('frontend/test-results/**'), 'wholesale')
    assert.equal(classifyUploadPath('frontend/test-results/chromium/*.png'), 'wholesale')
    assert.equal(classifyUploadPath('playwright-report/'), 'wholesale')
  })

  // Important 2. Every Playwright config in this repository also writes a
  // `playwright-json-report/` directory: `frontend/playwright.config.ts` and
  // the three `e2e-*` configs each point the `json` reporter's `outputFile`
  // under that name. Its failing-run JSON carries `results[].error.message`,
  // `stdout`, `stderr` and `attachments`, which is the same disclosure surface
  // as the two segments already listed, yet a path under it classified
  // `unrelated` and so was never checked at all. An unchecked path is not a
  // safe one; it is one the guard cannot fail on.
  await t.test('recognises the json-report directory the configs actually write', () => {
    assert.notEqual(
      classifyUploadPath('frontend/playwright-json-report/'),
      'unrelated',
      'a json-report path must be classified, not skipped as unrelated'
    )
    assert.equal(classifyUploadPath('frontend/playwright-json-report/'), 'wholesale')
    assert.equal(classifyUploadPath('frontend/playwright-json-report'), 'wholesale')
    assert.equal(classifyUploadPath('frontend/playwright-json-report/*.json'), 'wholesale')
    assert.equal(
      classifyUploadPath('frontend/playwright-json-report/e2e-staging.json'),
      'wholesale',
      'no json-report basename is on the narrow allowlist, so a named report is refused too'
    )
  })

  await t.test('calls a single named file inside one narrow', () => {
    assert.equal(classifyUploadPath('frontend/test-results/leaked-device-grants.jsonl'), 'narrow')
  })

  // Defect 1. The hand-rolled reader does not strip a trailing `#` comment, so
  // the comment survived into the scalar, became the last `/`-segment, and any
  // `.` inside it (a sentence-ending period, a version number) read as a file
  // extension. A wholesale Playwright output directory then classified
  // `narrow` and the hard rule exempted it.
  await t.test('a trailing YAML comment cannot demote a wholesale path to narrow', () => {
    assert.equal(
      classifyUploadPath('frontend/test-results/ # everything the run left behind, see ADR-029.'),
      'wholesale'
    )
    assert.equal(
      classifyUploadPath('frontend/test-results/ # bumped to v2.1 while triaging'),
      'wholesale'
    )
    // The control: a comment with no `.` in it was already classified
    // correctly, so this arm alone could never have caught the defect.
    assert.equal(classifyUploadPath('frontend/test-results/  # keep for triage'), 'wholesale')
  })

  // Defect 2. The `narrow` arm was unbounded by filename: ANY single file
  // inside a Playwright output directory passed, including the one file that
  // actually leaked a password. A single-file artifact carries a live
  // credential just as easily as a directory does, so the arm as written was
  // a check that could not fail.
  await t.test('only an enumerated filename is narrow; any other single file is not', () => {
    assert.equal(classifyUploadPath('frontend/test-results/error-context.md'), 'wholesale')
    assert.equal(classifyUploadPath('frontend/test-results/0-trace.trace'), 'wholesale')
    assert.equal(
      classifyUploadPath('frontend/test-results/some-future-diagnostic.json'),
      'wholesale'
    )
    assert.equal(
      classifyUploadPath('frontend/test-results/chromium/leaked-device-grants.jsonl'),
      'narrow',
      'the allowlist is keyed on the basename, so a per-project subdirectory is still allowed'
    )
  })

  await t.test('leaves unrelated artifact paths alone', () => {
    assert.equal(classifyUploadPath('backend.log'), 'unrelated')
    assert.equal(classifyUploadPath('coverage/'), 'unrelated')
    assert.equal(classifyUploadPath('dist/'), 'unrelated')
  })
})

test('the workflow parser', async (t) => {
  // #CRITICAL: data-integrity: a hand-rolled YAML parser that silently matches
  // nothing reports a repository full of unsafe uploads as clean. These arms
  // feed it a known upload and assert it is found, so a broken parser reddens.
  await t.test('finds an inline path', () => {
    const steps = parseUploadSteps(
      [
        'jobs:',
        '  a:',
        '    steps:',
        '      - name: Upload Playwright trace on failure',
        '        uses: actions/upload-artifact@abc # v7.0.1',
        '        with:',
        '          name: some-traces',
        '          path: frontend/test-results/',
        '          retention-days: 7',
      ].join('\n')
    )
    assert.equal(steps.length, 1)
    assert.deepEqual(steps[0].paths, ['frontend/test-results/'])
  })

  await t.test('finds every entry of a block-scalar path', () => {
    const steps = parseUploadSteps(
      [
        '      - uses: actions/upload-artifact@abc',
        '        with:',
        '          path: |',
        '            frontend/test-results/',
        '            summary.md',
        '          retention-days: 14',
      ].join('\n')
    )
    assert.deepEqual(steps[0].paths, ['frontend/test-results/', 'summary.md'])
  })

  await t.test('does not attribute a later step\u2019s path to an upload step', () => {
    const steps = parseUploadSteps(
      [
        '      - uses: actions/upload-artifact@abc',
        '        with:',
        '          path: report.json',
        '      - name: Something else',
        '        uses: actions/cache@abc',
        '        with:',
        '          path: node_modules',
      ].join('\n')
    )
    assert.equal(steps.length, 1)
    assert.deepEqual(steps[0].paths, ['report.json'])
  })

  await t.test('finds no upload in a workflow that has none', () => {
    assert.deepEqual(parseUploadSteps('jobs:\n  a:\n    steps:\n      - run: echo hi\n'), [])
  })
})

test('the secret detector', async (t) => {
  await t.test('sees a secrets expression', () => {
    assert.equal(injectsSecrets('  X: ${{ secrets.SOME_PASSWORD }}\n'), true)
  })

  await t.test('does not see a hardcoded local literal', () => {
    assert.equal(injectsSecrets('  POSTGRES_PASSWORD: password\n'), false)
  })

  // The rule keyed on the literal `${{ secrets.` to decide whether a workflow
  // could disclose a credential. A reusable-workflow call with
  // `secrets: inherit` hands over EVERY secret the caller can see and contains
  // no such expression anywhere, so the hard rule waved it through. That is
  // the same mistake this whole file exists to remove: a control adopted
  // because it looks right, never tested against the thing it must stop.
  await t.test('sees a reusable-workflow call that inherits every secret', () => {
    assert.equal(
      injectsSecrets(
        [
          'jobs:',
          '  call:',
          '    uses: ./.github/workflows/inner.yml',
          '    secrets: inherit',
          '',
        ].join('\n')
      ),
      true
    )
  })

  await t.test('sees it with a trailing comment, and quoted', () => {
    assert.equal(injectsSecrets('    secrets: inherit # the whole store\n'), true)
    assert.equal(injectsSecrets("    secrets: 'inherit'\n"), true)
  })

  // Important 4. The detector keyed on `secrets.` alone, so a workflow whose
  // only credential arrives through a repository or environment VARIABLE, or
  // which mints a cloud token over OIDC, read as non-secret-bearing and could
  // then publish wholesale. Latent rather than live in this repository: `${{
  // vars.` occurs nowhere in `.github/workflows`, and the four workflows that
  // request `id-token` upload no Playwright output. Closed as prevention, so
  // the first workflow to take either route does not arrive unguarded.
  await t.test('sees a repository or environment variable expression', () => {
    assert.equal(injectsSecrets('  LOGIN_TOKEN: ${{ vars.STAGING_LOGIN_TOKEN }}\n'), true)
  })

  await t.test('sees an OIDC token request, at workflow level and at job level', () => {
    assert.equal(injectsSecrets('permissions:\n  contents: read\n  id-token: write\n'), true)
    assert.equal(
      injectsSecrets(
        ['jobs:', '  publish:', '    permissions:', '      id-token: write', ''].join('\n')
      ),
      true
    )
  })

  await t.test('sees the blanket write-all grant that implies an OIDC token', () => {
    assert.equal(injectsSecrets('permissions: write-all\n'), true)
    assert.equal(
      injectsSecrets(['jobs:', '  publish:', '    permissions: write-all', ''].join('\n')),
      true
    )
  })

  // Controls. Without these the widened rule could pass by calling every
  // workflow secret-bearing, which would make the hard rule unfalsifiable in
  // the other direction.
  await t.test('does not see the word inherit in prose or in a comment', () => {
    assert.equal(injectsSecrets('    # secrets: inherit\n'), false)
    assert.equal(injectsSecrets('  # this reusable call inherits nothing\n'), false)
    assert.equal(injectsSecrets('    with:\n      inherit: true\n'), false)
  })

  // The other direction of the widening. A detector that answers true for
  // every input is exactly as useless as one that answers false for every
  // input: it would make the hard rule fire on the whole repository and so
  // justify nothing. `id-token` is only a credential when it is granted
  // `write`; `none` is the value a workflow uses to REFUSE the token.
  await t.test('does not treat a non-write id-token permission as a credential', () => {
    assert.equal(injectsSecrets('permissions:\n  contents: read\n  id-token: none\n'), false)
    assert.equal(injectsSecrets('permissions:\n  id-token: read\n'), false)
    assert.equal(injectsSecrets('    # id-token: write\n'), false)
    assert.equal(injectsSecrets('  # this job needs id-token for the OIDC exchange\n'), false)
    assert.equal(injectsSecrets('  # and it must not mention vars. either\n'), false)
  })

  // Same direction for the blanket grant: `read-all` is the value that grants
  // no credential, so a detector matching it would call half the repository
  // secret-bearing on the strength of a read permission.
  await t.test('does not treat a read-all permission block as a credential', () => {
    assert.equal(injectsSecrets('permissions: read-all\n'), false)
    assert.equal(injectsSecrets('    # permissions: write-all\n'), false)
    assert.equal(injectsSecrets('  # write-all would be too broad here\n'), false)
  })
})

test('the hard rule, end to end', async (t) => {
  // The unit arm above proves the detector; this proves the RULE consumes it.
  // A detector fixed in isolation while findSecretBearingWholesaleUploads kept
  // its own copy of the old test would look fixed and stop nothing.
  const INHERITING_UPLOADER = [
    'name: Inheriting tier',
    'jobs:',
    '  call:',
    '    uses: ./.github/workflows/inner.yml',
    '    secrets: inherit',
    '  publish:',
    '    steps:',
    '      - uses: actions/upload-artifact@abc',
    '        with:',
    '          name: traces',
    '          path: frontend/test-results/',
    '',
  ].join('\n')

  /**
   * @param {string} contents Workflow file contents.
   * @returns {string[]} findSecretBearingWholesaleUploads output.
   */
  function ruleOver(contents) {
    const dir = mkdtempSync(join(tmpdir(), 'artifact-safety-wf-'))
    try {
      writeFixture(dir, 'tier.yml', contents)
      return findSecretBearingWholesaleUploads(dir)
    } finally {
      rmSync(dir, { recursive: true, force: true })
    }
  }

  await t.test(
    'a secrets: inherit workflow publishing test-results wholesale is a violation',
    () => {
      const violations = ruleOver(INHERITING_UPLOADER)
      assert.equal(violations.length, 1)
      assert.match(violations[0], /tier\.yml/)
      assert.match(violations[0], /frontend\/test-results\//)
    }
  )

  await t.test('the same workflow without the inherit line is not a violation', () => {
    // The discriminating control: one line apart. Without it the arm above
    // could be passing because the upload alone trips the rule, which would
    // make the secret half of the rule untested.
    assert.deepEqual(ruleOver(INHERITING_UPLOADER.replace('    secrets: inherit\n', '')), [])
  })

  await t.test('a secrets: inherit workflow with no wholesale upload is not a violation', () => {
    assert.deepEqual(
      ruleOver(
        INHERITING_UPLOADER.replace(
          '          path: frontend/test-results/',
          '          path: summary.md'
        )
      ),
      []
    )
  })

  /**
   * Run the CLI itself, not just the exported function, over a fixture tree.
   *
   * The exported-function arms above cannot see a defect that lives between
   * the function and the process exit code, and CI's real consumer of this
   * control is the process.
   *
   * @param {string} contents Workflow file contents.
   * @returns {{status: number | null, stderr: string}} The CLI's result.
   */
  function cliOver(contents) {
    const dir = mkdtempSync(join(tmpdir(), 'artifact-safety-cli-'))
    try {
      writeFixture(dir, 'tier.yml', contents)
      const run = spawnSync(process.execPath, [CHECKER, dir], { encoding: 'utf8' })
      return { status: run.status, stderr: run.stderr }
    } finally {
      rmSync(dir, { recursive: true, force: true })
    }
  }

  // Defect 1, end to end. A trailing prose comment on the `path:` scalar made
  // the classifier read the comment's sentence-ending period as a file
  // extension, so a wholesale Playwright output directory was exempted and
  // the CLI exited 0 on a secret-bearing workflow publishing it.
  await t.test('the CLI rejects a wholesale upload carrying a trailing prose comment', () => {
    const commented = INHERITING_UPLOADER.replace(
      '          path: frontend/test-results/',
      '          path: frontend/test-results/ # everything the run left behind, see ADR-029.'
    )
    const run = cliOver(commented)
    assert.notEqual(run.status, 0, 'a commented wholesale path must still be a violation')
    assert.match(run.stderr, /FORBIDDEN UPLOAD/)
    assert.match(run.stderr, /tier\.yml/)
  })

  await t.test('the CLI exits 0 on the same tree with the upload removed', () => {
    // The discriminating control for the arm above: without it, an arm that
    // is red for any reason at all would read as a pass.
    const run = cliOver(
      INHERITING_UPLOADER.replace(
        '          path: frontend/test-results/',
        '          path: summary.md'
      )
    )
    assert.equal(run.status, 0, run.stderr)
  })

  // Defect 2. The `narrow` exemption was unbounded by filename, so the ONE
  // file that actually leaked a plaintext password passed the hard rule.
  await t.test('a secret-bearing workflow uploading error-context.md is a violation', () => {
    const violations = ruleOver(
      INHERITING_UPLOADER.replace(
        '          path: frontend/test-results/',
        '          path: frontend/test-results/error-context.md'
      )
    )
    assert.equal(violations.length, 1)
    // Matched with its directory prefix on purpose: the boilerplate half of
    // the message names `error-context.md` too, so a bare match would pass on
    // any violation at all.
    assert.match(violations[0], /frontend\/test-results\/error-context\.md/)
  })

  await t.test('a filename nobody enumerated is a violation, so the allowlist fails closed', () => {
    const violations = ruleOver(
      INHERITING_UPLOADER.replace(
        '          path: frontend/test-results/',
        '          path: frontend/test-results/some-future-diagnostic.json'
      )
    )
    assert.equal(violations.length, 1)
    assert.match(violations[0], /some-future-diagnostic\.json/)
  })

  // Important 2, end to end. `playwright-json-report/` was invisible to the
  // rule, so a secret-bearing workflow could publish a whole tree of
  // failing-run JSON (error messages, stdout, stderr, attachment paths) and
  // the CLI would exit 0 on it.
  await t.test('a wholesale json-report upload from a secret-bearing workflow is refused', () => {
    const violations = ruleOver(
      INHERITING_UPLOADER.replace(
        '          path: frontend/test-results/',
        '          path: frontend/playwright-json-report/'
      )
    )
    assert.equal(violations.length, 1)
    assert.match(violations[0], /frontend\/playwright-json-report\//)
  })

  // Important 4, end to end. A workflow whose ONLY credential reference is a
  // variable expression, or an OIDC token grant, read as non-secret-bearing
  // and could publish wholesale. `NO_CREDENTIAL_UPLOADER` is the same fixture
  // with the inherit line taken out, so each arm below differs from a proven
  // clean tree by exactly the credential route under test.
  const NO_CREDENTIAL_UPLOADER = INHERITING_UPLOADER.replace('    secrets: inherit\n', '')

  await t.test(
    'the credential-free fixture is clean, which is what makes the next two mean something',
    () => {
      assert.deepEqual(ruleOver(NO_CREDENTIAL_UPLOADER), [])
    }
  )

  await t.test('a vars-only workflow publishing wholesale is a violation', () => {
    const violations = ruleOver(
      NO_CREDENTIAL_UPLOADER.replace(
        '  publish:',
        ['  publish:', '    env:', '      LOGIN_TOKEN: ${{ vars.STAGING_LOGIN_TOKEN }}'].join('\n')
      )
    )
    assert.equal(violations.length, 1)
    assert.match(violations[0], /tier\.yml/)
  })

  await t.test('an OIDC-only workflow publishing wholesale is a violation', () => {
    const violations = ruleOver(
      NO_CREDENTIAL_UPLOADER.replace(
        '  publish:',
        ['  publish:', '    permissions:', '      contents: read', '      id-token: write'].join(
          '\n'
        )
      )
    )
    assert.equal(violations.length, 1)
    assert.match(violations[0], /tier\.yml/)
  })

  await t.test('a workflow that REFUSES the OIDC token is not a violation', () => {
    // The direction that keeps the widening from becoming a check that always
    // fires. Identical to the arm above but for `none` in place of `write`.
    assert.deepEqual(
      ruleOver(
        NO_CREDENTIAL_UPLOADER.replace(
          '  publish:',
          ['  publish:', '    permissions:', '      contents: read', '      id-token: none'].join(
            '\n'
          )
        )
      ),
      []
    )
  })

  await t.test('the one enumerated ledger filename is still accepted', () => {
    // The control that keeps the allowlist from being vacuously closed. This
    // is what `e2e-staging.yml` actually uploads: a JSONL ledger the sweep
    // writes itself, one `{"profileId","confirmed"}` record per row, with no
    // page snapshot, no trace and no request headers in it.
    assert.deepEqual(
      ruleOver(
        INHERITING_UPLOADER.replace(
          '          path: frontend/test-results/',
          '          path: frontend/test-results/leaked-device-grants.jsonl'
        )
      ),
      []
    )
  })
})

test('the real repository', async (t) => {
  await t.test(
    'no workflow that injects a secret publishes a Playwright output directory wholesale',
    () => {
      // The hard rule. This is what closes the e2e-prod and e2e-staging
      // credential exposure, and it goes red the moment either upload is
      // re-added, because both workflows inject `${{ secrets.* }}`.
      assert.deepEqual(findSecretBearingWholesaleUploads(WORKFLOWS_DIR), [])
    }
  )

  await t.test('the set of wholesale uploads has not widened', () => {
    // A tripwire, not an approval. These six tiers run against a local or
    // mocked backend and type a hardcoded local literal rather than a
    // repository secret, so they fall outside the hard rule above; they are
    // still on the owner's list to narrow. Pinning the exact set means a
    // SEVENTH workflow, or a widened path in one of these, cannot be added
    // without this assertion failing and forcing the decision into review.
    const expected = {
      'accessibility-compliance-weekly.yml': ['frontend/test-results/'],
      'cross-device-e2e.yml': ['frontend/test-results/'],
      'e2e-real-nightly.yml': ['frontend/test-results/'],
      'e2e-real-pr-smoke.yml': ['frontend/test-results/'],
      'usersim.yml': ['frontend/test-results/'],
      'webkit-kid.yml': ['frontend/test-results/'],
    }
    assert.deepEqual(findWholesaleUploads(WORKFLOWS_DIR), expected)
  })

  await t.test('e2e-prod.yml uploads no artifact at all', () => {
    // The prod tier signs a REAL production account in through the real login
    // form. Nothing it produces may be published from a public repository.
    const text = readWorkflow('e2e-prod.yml')
    assert.deepEqual(parseUploadSteps(text), [])
    assert.equal(injectsSecrets(text), true, 'the premise of the assertion above must still hold')
  })
})

/**
 * @param {string} name Workflow filename.
 * @returns {string} Its contents.
 */
function readWorkflow(name) {
  // eslint-disable-next-line security/detect-non-literal-fs-filename -- name is a literal in this file, never external input
  return readFileSync(join(WORKFLOWS_DIR, name), 'utf8')
}
