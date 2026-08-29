/**
 * Findings formatter and sink for the usersim walk tier.
 *
 * One finding is one JSON object, formatted (`formatFinding`) as a single
 * JSON line. Nothing in this repo writes those lines to a file: the one
 * caller, walk-runner.ts's `runWalk`, wires `write` to `console.log` with a
 * `[usersim-finding]` prefix, so a finding reaches the job's own log at
 * `record()` time (task B3b review, Important 3). There is no findings file
 * on disk anywhere in this repository; see
 * docs/operations/runbook.md's usersim-a11y-weekly description for the same
 * correction. `workflow` is REQUIRED (not optional) because findings now
 * originate from three different workflow tags (walk.spec.ts's
 * `'usersim-walk'`, walk-real.spec.ts's `'usersim-walk-real'`,
 * walk-a11y.spec.ts's `'usersim-a11y-weekly'`; see invariants.ts's
 * `Workflow` type), and a finding with no workflow field would be
 * unattributable between them.
 */

export interface UsersimFinding {
  /** Which leg of the usersim tier produced this finding (e.g. 'A' for the seeded-random-walk leg). */
  leg: string
  /** Persona whose walk produced this finding, e.g. 'kid' | 'guardian' | 'admin'. */
  persona: string
  /**
   * The walk's numeric seed for a random-walk run, or a named scenario id
   * for a scripted one. Named `scenario_or_seed` (not just `seed`) because
   * leg A findings can originate from either kind of run.
   */
  scenario_or_seed: string | number
  /** The URL the walk was at when the invariant was checked. */
  url: string
  /** Which invariant fired, or the verdict it produced. */
  invariant_or_verdict: string
  /** Severity of this finding. */
  severity: string
  /** Path to saved evidence (screenshot, trace, console dump) for this finding. */
  evidence_path: string
  /** Which workflow produced this finding. REQUIRED: see the module doc above. */
  workflow: string
}

/** Render one finding as a single JSONL line (no trailing newline). */
export function formatFinding(finding: UsersimFinding): string {
  return JSON.stringify(finding)
}

export interface FindingsSink {
  /** Record one finding. */
  record(finding: UsersimFinding): void
}

/**
 * Build a findings sink around a line-writer callback.
 *
 * `write` decides where a formatted line goes. Every current caller
 * (walk-runner.ts's `runWalk`) passes `console.log` with a `[usersim-finding]`
 * prefix, so a finding reaches the job's own log at `record()` time, not a
 * results file; see the module doc comment above. Kept as a plain callback
 * rather than a hardcoded `node:fs` writer so this module stays usable from
 * a unit test with no filesystem dependency, and so a future caller that
 * does want a real file can supply one without a second, parallel emitter.
 */
export function createFindingsSink(write: (line: string) => void): FindingsSink {
  return {
    record(finding: UsersimFinding): void {
      write(formatFinding(finding))
    },
  }
}
