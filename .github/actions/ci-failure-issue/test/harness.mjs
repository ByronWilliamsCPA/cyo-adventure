// Test harness for the `script:` block in ../action.yml.
//
// The script is EXTRACTED from action.yml at run time rather than copied here.
// A copied fixture is the failure mode this harness exists to prevent: it keeps
// passing after the real script changes, which is indistinguishable from the
// script being correct. If the extraction stops finding a script, that is a
// hard error, not an empty test run.
//
// Everything below is dependency-free on purpose. This runs under `node --test`
// with no package.json and no lockfile, so the gate that guards the alerting
// path adds no npm supply-chain surface of its own.

import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
export const ACTION_YML = join(HERE, '..', 'action.yml')

/**
 * Pull the github-script body out of action.yml.
 *
 * Deliberately not a YAML parse: the point is to run the exact text that
 * `actions/github-script` receives, and a parser that normalised the block
 * would put a transformation between the test and the thing under test.
 */
export function extractScript(path = ACTION_YML) {
  const lines = readFileSync(path, 'utf8').split('\n')
  const start = lines.findIndex((line) => /^\s*script:\s*\|\s*$/.test(line))
  if (start === -1) {
    throw new Error(`${path}: no \`script: |\` block found`)
  }
  const openerIndent = lines[start].match(/^\s*/)[0].length
  const body = []
  for (const line of lines.slice(start + 1)) {
    const indent = line.match(/^\s*/)[0].length
    if (line.trim() !== '' && indent <= openerIndent) {
      break
    }
    body.push(line)
  }
  const bodyIndent = Math.min(
    ...body.filter((l) => l.trim() !== '').map((l) => l.match(/^\s*/)[0].length),
  )
  const text = body.map((l) => l.slice(bodyIndent)).join('\n').trimEnd()
  if (text === '') {
    throw new Error(`${path}: the \`script:\` block is empty`)
  }
  return text
}

// github-script evaluates the body inside an async function, which is what
// makes the top-level `await`s in the script legal. Reproducing that wrapper is
// the only way to run the real text unmodified.
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor

/**
 * A faithful-enough Octokit double.
 *
 * `listForRepo` honours `page` and `per_page` and DEFAULTS TO 30, exactly as
 * the REST API does. That default is the whole reason this stub is written this
 * way: it means a regression from `github.paginate(...)` back to a bare
 * `listForRepo` makes a match past the first page genuinely invisible to the
 * script, so the pagination fix is asserted by behaviour rather than by
 * spying on which function was called.
 */
export class FakeGitHub {
  constructor({ issues = [], createResponse, addAssigneesResponse } = {}) {
    this.issues = issues
    this.createResponse = createResponse
    this.addAssigneesResponse = addAssigneesResponse
    this.calls = []
    this.nextNumber = 9000

    const record = (name, params) => this.calls.push({ name, params })

    this.rest = {
      issues: {
        listForRepo: async (params) => {
          record('listForRepo', params)
          const perPage = params.per_page ?? 30
          const page = params.page ?? 1
          const wanted = params.labels
          const matching = this.issues.filter(
            (issue) =>
              (wanted === undefined || (issue.labels ?? []).includes(wanted)) &&
              (params.state === undefined ||
                params.state === 'all' ||
                (issue.state ?? 'open') === params.state),
          )
          return { data: matching.slice((page - 1) * perPage, page * perPage) }
        },
        create: async (params) => {
          record('create', params)
          const number = this.nextNumber++
          return {
            data:
              this.createResponse === undefined
                ? { number, assignees: (params.assignees ?? []).map((login) => ({ login })) }
                : { number, ...this.createResponse },
          }
        },
        createComment: async (params) => {
          record('createComment', params)
          return { data: { id: 1 } }
        },
        update: async (params) => {
          record('update', params)
          return { data: { number: params.issue_number } }
        },
        addAssignees: async (params) => {
          record('addAssignees', params)
          return {
            data:
              this.addAssigneesResponse === undefined
                ? { assignees: (params.assignees ?? []).map((login) => ({ login })) }
                : this.addAssigneesResponse,
          }
        },
      },
    }
  }

  // Mirrors Octokit's paginate: walk pages until one comes back short.
  paginate = async (fn, params) => {
    const perPage = params.per_page ?? 30
    const out = []
    for (let page = 1; ; page += 1) {
      const { data } = await fn({ ...params, page })
      out.push(...data)
      if (data.length < perPage) {
        return out
      }
    }
  }

  /** Names of the API methods the script invoked, in order. */
  get sequence() {
    return this.calls.map((call) => call.name)
  }

  /** The first call to `name`, or undefined. */
  callTo(name) {
    return this.calls.find((call) => call.name === name)
  }

  countOf(name) {
    return this.calls.filter((call) => call.name === name).length
  }
}

/**
 * Run the real script once against doubles.
 *
 * Returns what the script did rather than what it returned: the failure
 * message, the info lines, and the ordered API calls. `setFailed` does NOT
 * halt execution in the real runtime either, so it is recorded rather than
 * thrown; the `return` statements that follow it in the script are what
 * actually stop the work, and a test that threw here would hide their removal.
 */
export async function runScript({ env = {}, issues = [], createResponse, addAssigneesResponse, context: ctx = {} } = {}) {
  const github = new FakeGitHub({ issues, createResponse, addAssigneesResponse })
  const failures = []
  const infos = []
  const core = {
    setFailed: (message) => failures.push(String(message)),
    info: (message) => infos.push(String(message)),
    warning: (message) => infos.push(`WARNING: ${String(message)}`),
    debug: () => {},
    notice: (message) => infos.push(`NOTICE: ${String(message)}`),
  }
  const context = {
    repo: { owner: 'ByronWilliamsCPA', repo: 'cyo-adventure' },
    serverUrl: 'https://github.com',
    runId: 123456,
    eventName: 'schedule',
    ...ctx,
  }

  const previousEnv = process.env
  process.env = { ...previousEnv, ...env }
  try {
    const fn = new AsyncFunction('github', 'context', 'core', 'require', extractScript())
    await fn(github, context, core, () => {
      throw new Error('the script must not require() anything')
    })
  } finally {
    process.env = previousEnv
  }

  return { github, failures, infos, context }
}

/** Env for a valid mode=open call, overridable per test. */
export function openEnv(overrides = {}) {
  return {
    CFI_MARKER: '[release]',
    CFI_LABEL: 'ci-failure',
    CFI_MODE: 'open',
    CFI_SUMMARY: 'scheduled release proposal failing',
    CFI_BODY: 'The propose job failed.',
    CFI_COMMENT_BODY: '',
    CFI_ASSIGNEE: 'williaby',
    CFI_LEGACY_TITLE: '',
    ...overrides,
  }
}

/** Build an issue as listForRepo would return it. */
export function issue({ number = 1, title = '[release] scheduled release proposal failing', labels = ['ci-failure'], assignees = [], pull_request, state = 'open' } = {}) {
  const out = { number, title, labels, assignees, state }
  if (pull_request !== undefined) {
    out.pull_request = pull_request
  }
  return out
}
