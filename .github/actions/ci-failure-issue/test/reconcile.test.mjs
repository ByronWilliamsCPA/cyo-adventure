// Executable contract for the alerting script in ../action.yml.
//
// Fourteen scheduled workflows delegate their only notification channel to that
// script. Before this file existed, every claim about it was untested: the
// pagination fix, the pull-request filter, the prefix matching, and the
// close-before-comment ordering were all asserted by comment. A scheduled
// workflow fails invisibly by construction, so a defect here does not turn a
// pull request red, it just means nobody is told. That is the outage this whole
// action was written to end, which makes an untested version of it the same
// class of risk as the copy-pasted code it replaced.
//
// Run: node --test .github/actions/ci-failure-issue/test/

import { strict as assert } from 'node:assert'
import { test, describe } from 'node:test'

import { extractScript, openEnv, issue, runScript } from './harness.mjs'

describe('the harness is actually testing the action', () => {
  // A harness that silently extracted nothing would make every test below
  // vacuous while reporting a full green run. These two assertions are what
  // separate "the script behaves correctly" from "no script was found".
  test('the extracted script is the real one', () => {
    const script = extractScript()

    assert.ok(script.length > 500, `extracted only ${script.length} chars`)
    assert.match(script, /process\.env\.CFI_MARKER/)
    assert.match(script, /github\.rest\.issues\.create\(/)
  })

  test('a valid open call reaches the API', async () => {
    const { github, failures } = await runScript({ env: openEnv() })

    assert.deepEqual(failures, [])
    assert.ok(github.countOf('create') === 1, 'the happy path must file an issue')
  })
})

describe('input validation refuses to act on an unusable call', () => {
  // Each of these asserts NO API call was made, not just that setFailed fired.
  // `core.setFailed` does not halt a github-script body: it records a failure
  // and execution continues. The `return` after each setFailed is therefore
  // load-bearing, and deleting one would leave the script marking the step
  // failed while still filing or closing an issue. Asserting on the call list
  // is the only way that shows up.
  const refuses = [
    ['an empty marker', { CFI_MARKER: '' }, /marker is required/],
    ['an empty label', { CFI_LABEL: '' }, /label must not be empty/],
    ['an unknown mode', { CFI_MODE: 'Resolve' }, /mode must be "open" or "resolve"/],
    ['a missing summary', { CFI_SUMMARY: '' }, /summary and body are required/],
    ['a missing body', { CFI_BODY: '' }, /summary and body are required/],
  ]

  for (const [name, overrides, expected] of refuses) {
    test(`${name} fails the step and writes nothing`, async () => {
      const { github, failures } = await runScript({
        env: openEnv(overrides),
        issues: [issue()],
      })

      assert.equal(failures.length, 1, `expected one failure, got ${failures}`)
      assert.match(failures[0], expected)
      assert.deepEqual(
        github.sequence.filter((call) => call !== 'listForRepo'),
        [],
        'a refused call must not create, comment, close, or assign',
      )
    })
  }

  test('an empty mode is refused rather than defaulting to open', async () => {
    // The input has a YAML default, so an empty value can only arrive by a
    // call site passing one explicitly. Treating that as `open` would file an
    // issue the caller did not ask for.
    const { failures } = await runScript({ env: openEnv({ CFI_MODE: '' }) })

    assert.equal(failures.length, 1)
    assert.match(failures[0], /mode must be "open" or "resolve"/)
  })
})

describe('finding the existing issue', () => {
  test('matches by prefix, so an edited title does not orphan the issue', async () => {
    const edited = issue({ number: 41, title: '[release] failing since 2026-08-17 (see #767)' })

    const { github, failures } = await runScript({ env: openEnv(), issues: [edited] })

    assert.deepEqual(failures, [])
    assert.equal(github.countOf('create'), 0, 'a prefix match must not file a duplicate')
    assert.equal(github.callTo('createComment').params.issue_number, 41)
  })

  // Two regressions hide behind the word "pagination" and they need different
  // backlog sizes to separate. Dropping `per_page` reverts to the API's default
  // of 30; dropping `github.paginate` stops walking pages at all. A backlog of
  // 95 cannot tell those apart, because one fat page and a full walk return the
  // same list. Each case below is sized so exactly one of the two fixes is
  // load-bearing, which a mutation run confirmed: seeding only 95 left the
  // `paginate` mutation undetected while the suite stayed green.
  const buried = (total, matchIndex) => {
    const backlog = Array.from({ length: total }, (_, i) =>
      issue({ number: i + 1, title: `[unrelated-${i}] noise` }),
    )
    backlog[matchIndex] = issue({
      number: matchIndex + 1,
      title: '[release] buried in the backlog',
    })
    return backlog
  }

  test('finds a match past the default page size of 30', async () => {
    // Fails if `per_page: 100` is dropped: the match sits at index 93, so a
    // default-sized request cannot see it.
    const { github, failures } = await runScript({ env: openEnv(), issues: buried(95, 93) })

    assert.deepEqual(failures, [])
    assert.equal(github.countOf('create'), 0, 'a duplicate here is self-amplifying')
    assert.equal(github.callTo('createComment').params.issue_number, 94)
  })

  test('finds a match past the FIRST page even at 100 per page', async () => {
    // Fails if `github.paginate` is dropped, even with `per_page: 100` intact.
    // This is the assertion the first version of this file was missing.
    const { github, failures } = await runScript({ env: openEnv(), issues: buried(145, 130) })

    assert.deepEqual(failures, [])
    assert.equal(github.countOf('create'), 0)
    assert.equal(github.callTo('createComment').params.issue_number, 131)
  })

  test('walks every page rather than stopping at the second', async () => {
    // A `paginate` that stopped early would satisfy the test above by luck if
    // the match happened to sit on page two. Counting requests pins the walk.
    const { github } = await runScript({ env: openEnv(), issues: buried(250, 240) })

    assert.equal(github.countOf('listForRepo'), 3)
    assert.equal(github.callTo('listForRepo').params.per_page, 100)
    assert.equal(github.callTo('createComment').params.issue_number, 241)
  })

  test('ignores a pull request that shares the title', async () => {
    // listForRepo returns PRs too. A PR absorbing the comments meant the real
    // issue was never found and every alert landed somewhere nobody reads.
    const decoy = issue({ number: 50, title: '[release] scheduled release proposal failing', pull_request: { url: 'x' } })

    const { github, failures } = await runScript({ env: openEnv(), issues: [decoy] })

    assert.deepEqual(failures, [])
    assert.equal(github.countOf('createComment'), 0, 'a PR must not absorb the alert')
    assert.equal(github.countOf('create'), 1, 'the real issue was missing, so file it')
  })

  test('matches a legacy title exactly when the marker does not match', async () => {
    const legacy = issue({ number: 302, title: 'Weekly mutation-testing run is failing' })

    const { github } = await runScript({
      env: openEnv({ CFI_MARKER: '[mutation]', CFI_LEGACY_TITLE: 'Weekly mutation-testing run is failing' }),
      issues: [legacy],
    })

    assert.equal(github.countOf('create'), 0)
    assert.equal(github.callTo('createComment').params.issue_number, 302)
  })

  test('an empty legacy title matches nothing', async () => {
    // `legacyTitle !== ''` guards this. Without it, `issue.title === ''` would
    // be evaluated for every call site that passes no legacy title, and an
    // untitled issue would absorb alerts from all fourteen workflows.
    const untitled = issue({ number: 7, title: '' })

    const { github } = await runScript({ env: openEnv(), issues: [untitled] })

    assert.equal(github.countOf('createComment'), 0)
    assert.equal(github.countOf('create'), 1)
  })

  test('a legacy title on the wrong label is still not matched', async () => {
    const elsewhere = issue({ number: 8, title: 'Weekly mutation-testing run is failing', labels: ['e2e-alert'] })

    const { github } = await runScript({
      env: openEnv({ CFI_LEGACY_TITLE: 'Weekly mutation-testing run is failing' }),
      issues: [elsewhere],
    })

    assert.equal(github.countOf('createComment'), 0)
  })
})

describe('the label scopes the lookup and the filing', () => {
  test('an issue under a different label is invisible', async () => {
    const other = issue({ number: 623, title: '[release] scheduled release proposal failing', labels: ['e2e-alert'] })

    const { github } = await runScript({ env: openEnv(), issues: [other] })

    assert.equal(github.callTo('listForRepo').params.labels, 'ci-failure')
    assert.equal(github.countOf('createComment'), 0)
    assert.equal(github.countOf('create'), 1)
  })

  test('a non-default label scopes both the lookup and the new issue', async () => {
    const { github } = await runScript({ env: openEnv({ CFI_LABEL: 'e2e-alert' }) })

    assert.equal(github.callTo('listForRepo').params.labels, 'e2e-alert')
    assert.deepEqual(github.callTo('create').params.labels, ['e2e-alert'])
  })

  test('a matching issue under the passed label is found', async () => {
    const match = issue({ number: 290, title: '[e2e-real-nightly] failing', labels: ['e2e-alert'] })

    const { github } = await runScript({
      env: openEnv({ CFI_LABEL: 'e2e-alert', CFI_MARKER: '[e2e-real-nightly]' }),
      issues: [match],
    })

    assert.equal(github.countOf('create'), 0)
    assert.equal(github.callTo('createComment').params.issue_number, 290)
  })
})

describe('filing a new issue', () => {
  test('composes the title from marker and summary and appends the footer', async () => {
    const { github } = await runScript({ env: openEnv() })
    const { params } = github.callTo('create')

    assert.equal(params.title, '[release] scheduled release proposal failing')
    assert.match(params.body, /^The propose job failed\./)
    assert.match(params.body, /Run: https:\/\/github\.com\/ByronWilliamsCPA\/cyo-adventure\/actions\/runs\/123456/)
    assert.match(params.body, /Date: \d{4}-\d{2}-\d{2} \(event: schedule\)/)
    assert.deepEqual(params.assignees, ['williaby'])
  })

  test('an empty assignee omits the key rather than sending an empty list', async () => {
    // `assignees: []` and no `assignees` key are not the same request, and the
    // spread is what keeps them distinct.
    const { github, failures } = await runScript({ env: openEnv({ CFI_ASSIGNEE: '' }) })

    assert.deepEqual(failures, [])
    assert.equal('assignees' in github.callTo('create').params, false)
  })

  test('the footer records the event name, so a manual run is distinguishable', async () => {
    const { github } = await runScript({
      env: openEnv(),
      context: { eventName: 'workflow_dispatch' },
    })

    assert.match(github.callTo('create').params.body, /\(event: workflow_dispatch\)/)
  })
})

describe('updating an issue that is already open', () => {
  test('comments and does not file a second issue', async () => {
    const open = issue({ number: 41, assignees: [{ login: 'williaby' }] })

    const { github } = await runScript({
      env: openEnv({ CFI_COMMENT_BODY: 'Attempt 3 failed the same way.' }),
      issues: [open],
    })

    assert.equal(github.countOf('create'), 0)
    assert.match(github.callTo('createComment').params.body, /^Attempt 3 failed the same way\./)
    assert.match(github.callTo('createComment').params.body, /Run: https:/)
  })

  test('an empty comment body falls back to a recurrence note', async () => {
    const open = issue({ number: 41, assignees: [{ login: 'williaby' }] })

    const { github } = await runScript({ env: openEnv(), issues: [open] })

    assert.match(github.callTo('createComment').params.body, /^This failed again\./)
  })

  test('does not re-assign an issue that already has an assignee', async () => {
    const open = issue({ number: 41, assignees: [{ login: 'someone-else' }] })

    const { github } = await runScript({ env: openEnv(), issues: [open] })

    assert.equal(github.countOf('addAssignees'), 0, 'a triaging human must not be overwritten')
  })

  test('self-heals an unassigned issue', async () => {
    const orphan = issue({ number: 41, assignees: [] })

    const { github, failures } = await runScript({ env: openEnv(), issues: [orphan] })

    assert.deepEqual(failures, [])
    assert.deepEqual(github.callTo('addAssignees').params.assignees, ['williaby'])
  })

  test('an issue whose response omits assignees entirely is still healed', async () => {
    // Some response shapes drop the key rather than sending []. The `?? []` is
    // what keeps that from throwing on `.length`.
    const orphan = issue({ number: 41 })
    delete orphan.assignees

    const { github, failures } = await runScript({ env: openEnv(), issues: [orphan] })

    assert.deepEqual(failures, [])
    assert.equal(github.countOf('addAssignees'), 1)
  })

  test('an empty assignee disables self-healing', async () => {
    const orphan = issue({ number: 41, assignees: [] })

    const { github, failures } = await runScript({
      env: openEnv({ CFI_ASSIGNEE: '' }),
      issues: [orphan],
    })

    assert.deepEqual(failures, [])
    assert.equal(github.countOf('addAssignees'), 0)
  })
})

describe('a dropped assignee fails the step', () => {
  // GitHub silently ignores assignees for a login without push access and
  // still returns 201. Assignment is the notification channel here, so an
  // undetected drop reproduces the original outage with the job reporting
  // green. These tests pin the #CRITICAL note in action.yml's header: a log
  // line is what made the first drop invisible, so the response has to be
  // read back and the step has to go red.
  test('an empty assignees array in the create response is caught', async () => {
    const { failures } = await runScript({
      env: openEnv(),
      createResponse: { assignees: [] },
    })

    assert.equal(failures.length, 1)
    assert.match(failures[0], /GitHub dropped assignee "williaby"/)
    assert.match(failures[0], /notifies nobody/)
  })

  test('a missing assignees key in the create response is caught', async () => {
    const { failures } = await runScript({
      env: openEnv(),
      createResponse: { assignees: undefined },
    })

    assert.equal(failures.length, 1)
    assert.match(failures[0], /GitHub dropped assignee/)
  })

  test('the failure names who was assigned instead', async () => {
    const { failures } = await runScript({
      env: openEnv(),
      createResponse: { assignees: [{ login: 'someone-else' }] },
    })

    assert.equal(failures.length, 1)
    assert.match(failures[0], /Assigned instead: \[someone-else\]/)
  })

  test('a drop on the self-heal path is caught too', async () => {
    // The self-heal call is a separate endpoint with the same silent-drop
    // behaviour, so verifying only the create path would leave every
    // pre-existing issue unprotected.
    const orphan = issue({ number: 41, assignees: [] })

    const { failures } = await runScript({
      env: openEnv(),
      issues: [orphan],
      addAssigneesResponse: { assignees: [] },
    })

    assert.equal(failures.length, 1)
    assert.match(failures[0], /self-heal on #41/)
  })

  test('a successful assignment does not fail the step', async () => {
    const { failures } = await runScript({
      env: openEnv(),
      createResponse: { assignees: [{ login: 'williaby' }, { login: 'bot' }] },
    })

    assert.deepEqual(failures, [])
  })

  test('an empty assignee is not treated as a drop', async () => {
    const { failures } = await runScript({
      env: openEnv({ CFI_ASSIGNEE: '' }),
      createResponse: { assignees: [] },
    })

    assert.deepEqual(failures, [])
  })
})

describe('resolving on a green scheduled run', () => {
  test('closes before commenting', async () => {
    // The two calls are not atomic. Commenting first means a failed close
    // leaves an open issue carrying a comment that says it was closed
    // automatically, which is a lie a human then has to disbelieve. This
    // order cannot lie: the worst case is a closed issue with no comment.
    const open = issue({ number: 41 })

    const { github, failures } = await runScript({
      env: openEnv({ CFI_MODE: 'resolve' }),
      issues: [open],
    })

    assert.deepEqual(failures, [])
    assert.deepEqual(
      github.sequence.filter((call) => call === 'update' || call === 'createComment'),
      ['update', 'createComment'],
    )
  })

  test('closes as completed rather than as not planned', async () => {
    const { github } = await runScript({
      env: openEnv({ CFI_MODE: 'resolve' }),
      issues: [issue({ number: 41 })],
    })

    assert.equal(github.callTo('update').params.state, 'closed')
    assert.equal(github.callTo('update').params.state_reason, 'completed')
  })

  test('is a no-op when no issue is open', async () => {
    const { github, failures, infos } = await runScript({
      env: openEnv({ CFI_MODE: 'resolve' }),
    })

    assert.deepEqual(failures, [])
    assert.deepEqual(github.sequence, ['listForRepo'])
    assert.match(infos.join('\n'), /No open ci-failure issue for \[release\]/)
  })

  test('names the passed label in the no-op message', async () => {
    const { infos } = await runScript({
      env: openEnv({ CFI_MODE: 'resolve', CFI_LABEL: 'e2e-alert' }),
    })

    assert.match(infos.join('\n'), /No open e2e-alert issue/)
  })

  test('does not require summary or body', async () => {
    const { github, failures } = await runScript({
      env: openEnv({ CFI_MODE: 'resolve', CFI_SUMMARY: '', CFI_BODY: '' }),
      issues: [issue({ number: 41 })],
    })

    assert.deepEqual(failures, [])
    assert.equal(github.countOf('update'), 1)
  })

  test('never files an issue', async () => {
    const { github } = await runScript({
      env: openEnv({ CFI_MODE: 'resolve' }),
      issues: [issue({ number: 41, title: '[other] something else' })],
    })

    assert.equal(github.countOf('create'), 0)
  })
})

describe('interpolated data cannot change the script behaviour', () => {
  // The #CRITICAL security note in action.yml claims a body carrying a
  // backtick, `${`, or a quote appears verbatim rather than executing. That
  // holds because the values arrive through env: rather than through a `${{ }}`
  // expansion inside the script source, and this is the assertion that keeps
  // the claim from being decoration.
  test('a body full of template syntax is passed through verbatim', async () => {
    const hostile = 'before `${process.exit(1)}` and ${{ github.token }} and "quoted" \\end'

    const { github, failures } = await runScript({ env: openEnv({ CFI_BODY: hostile }) })

    assert.deepEqual(failures, [])
    assert.ok(github.callTo('create').params.body.startsWith(hostile))
  })

  test('a marker full of regex metacharacters is matched literally', async () => {
    // startsWith, not a regex. A marker like `[release]` is a character class
    // if it ever reaches a regex constructor.
    const { github } = await runScript({
      env: openEnv({ CFI_MARKER: '[a-z]' }),
      issues: [issue({ number: 3, title: 'release something' })],
    })

    assert.equal(github.countOf('createComment'), 0, '[a-z] must not match "release"')
    assert.equal(github.countOf('create'), 1)
  })
})
