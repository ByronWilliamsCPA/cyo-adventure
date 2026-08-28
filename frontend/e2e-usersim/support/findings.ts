/**
 * JSONL findings emitter for the usersim walk tier.
 *
 * One finding is one JSON object, one line, with exactly the fields below.
 * `workflow` is REQUIRED (not optional) because leg A findings will
 * originate from two different workflows, and a finding with no workflow
 * field would be unattributable between them.
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
 * Deliberately not wired to a real file here: task 1 only needs the shape
 * and the JSONL formatting to be fixed and testable. Task 2/3 pass a real
 * writer (e.g. one that appends `line + '\n'` to a results file via
 * `node:fs`) once the walk that produces findings exists; passing a plain
 * callback here keeps this module usable from a unit test with no
 * filesystem dependency at all.
 */
export function createFindingsSink(write: (line: string) => void): FindingsSink {
  return {
    record(finding: UsersimFinding): void {
      write(formatFinding(finding))
    },
  }
}
