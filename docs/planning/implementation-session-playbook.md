---
title: "Implementation session playbook"
schema_type: planning
status: active
owner: core-maintainer
purpose: "How an autonomous implementation session on this repository should orient, choose work,
  fan out agents, verify, record, and hand off, distilled from the lessons log and from the
  2026-09-05 session that repaired five long-red signals in one pass."
tags:
  - planning
  - process
  - tooling
component: Strategy
source: "docs/planning/authoring-lessons-log.md (process and tooling rows through AL-772); session
  2026-09-05 on branch claude/repo-value-focus-xzmq4k; CLAUDE.md Implementation Session Protocol"
---

# Implementation session playbook

> **Status**: Active | **Created**: 2026-09-05 | **Companion**: the condensed rules live in
> `CLAUDE.md` under "Implementation Session Protocol"; this document carries the reasoning and
> the worked procedure. When the two disagree, fix both in the same commit.

## 1. Why this document exists

The authoring lessons log holds hundreds of process and tooling rows, and most of them are the same
dozen failures wearing different clothes: a number in prose went stale, a check existed that nothing
invoked, a grep stood in for a predicate, a `#CRITICAL` comment described a fleet property that no
test enforced, two agents in one worktree destroyed each other's hunks, a fix was marked applied
while a sibling site kept the bug, "merged" was read as "deployed". Each was learned in a session,
recorded, and then re-learned in the next session because the log is where lessons go to be
remembered, not where a session starts.

The 2026-09-05 session repaired five signals that had been red for weeks (two scheduled jobs that had
never executed once, a mutation run that had never reached scoring, a nightly tier red 37 nights, a
safety eval red on class A) and found that every one of them had been visible the whole time in
`scheduled-health-rollup.yml`'s issue, and that the fix for each was small. What was missing was not
capability. It was a session that started by reading the signals and then treated its own first
diagnosis as a hypothesis to falsify rather than a result to ship. This playbook is that session's
procedure, written down so the next one does not depend on who runs it.

## 2. Orientation, in this order

Do these before choosing any work. Each takes minutes and each has, on this project, reversed a
plan made without it.

1. **Read the health signals, not the plan.** The open `ci-failure` and `e2e-alert` issues, and
   the `[health-rollup]` issue, are the only place a scheduled job's failure surfaces. A workflow
   that has never executed (parked in `waiting`, cancelled by the next cron) looks identical to a
   healthy one everywhere else. Pull the latest failing run's log for anything over the escalation
   bar; the cause is usually one line.
2. **Read the registers before the master documents.** `unscheduled-work-register.md` clusters L
   (live defects) and M (owner-gated) and the tail of `authoring-lessons-log.md` are newer and
   more specific than `roadmap.md` or `PROJECT-PLAN.md`, whose status headers have lagged the code
   by weeks more than once. Treat any dated claim in a master document as an allegation to verify.
3. **Establish what the session cannot do.** Cloud sessions have no Postgres, no Docker, no
   provider keys, no Supabase MCP authorisation, and no production access. Anything that needs
   them (the real-backend Playwright tiers, the live safety eval, the re-moderation sweep, a
   production query) can be prepared and reasoned about but not executed; say so in the report
   rather than describing the prepared thing as done.
4. **Bring the environment up once, completely.** `uv sync --all-extras`, then `npm ci` in
   `frontend/`. The pre-installed Playwright Chromium under `/opt/pw-browsers` is versioned for a
   different `@playwright/test` than the repo pins; alias it under the expected directory names
   (`chromium-<rev>/chrome-linux64/chrome`, `chromium_headless_shell-<rev>/chrome-headless-shell-linux64/chrome-headless-shell`)
   in a scratch `PLAYWRIGHT_BROWSERS_PATH` rather than downloading. Do not run `playwright install`.

## 3. Choosing work

Rank by what the absence of the work is costing today, not by how the plan phases it:

1. **Signals first.** A red or never-run check is worth more than any feature, because every
   other item's verification depends on it. Fixes here are usually small and compound.
2. **Safety-gate integrity second.** This product's promise is that nothing reaches a child
   unreviewed. Any finding that the gate attests less than it claims (a fail-safe stage read as a
   pass, a mock reviewer read as a real one, a hard block that does not block publish) outranks
   every roadmap item.
3. **The blocker the owner named third.** Register rows carrying `R1` or a milestone token.
4. **Then the plan.**

Separate owner-gated steps from engineering at the moment you find them and keep them in one list
for the report: environment and secret creation, stuck-run cancellation, key revocation, production
queries, rulings. Do not let an owner step block an engineering step that can land without it;
land the engineering side and name the owner side in the register (cluster M) and the report.

## 4. Fanning out agents

Parallel agents are the way to spend a high-capability session well, and the way to lose work if
the rules are loose. `AL-746` is the record of two agents in one worktree, one of whose
`pre-commit` stash-and-pop silently discarded the other's unstaged hunks; `git fsck` recovered
nothing because unstaged content is never an object.

- **Disjoint file ownership, stated in the brief.** Every agent prompt names the files it may
  edit and the files other agents own. When two tasks need the same file, serialise them or have
  one agent do both.
- **Agents never commit, stash, checkout, restore, or run `pre-commit run --all-files`.** The
  supervisor commits. Agents run hooks only on their own files.
- **Agents never edit the ledgers.** `unscheduled-work-register.md` and
  `authoring-lessons-log.md` are single files every task wants to append to; agents propose rows
  in their report and the supervisor writes them, so the row ids are allocated once.
- **Model to the task.** Verification of claims against code, mechanical edits with a clear
  spec, and inventory work go to Sonnet agents (`Explore` for read-only, `general-purpose`
  otherwise). Root-cause investigation, anything touching the safety gate's semantics, and the
  synthesis of what the agents report stay with the supervisor.
- **Expect rate limits and plan for resumption.** Five concurrent frontier-model agents hit the
  account limit inside the hour on 2026-09-05 and four died mid-task. Run two or three at a time;
  when an agent dies, `git status` shows what it left, and the resumed brief should name those
  files and ask the agent to evaluate them on their merits rather than start over.
- **Read the report, not the transcript.** An agent's final report is the deliverable; ask it for
  verbatim verification output and file:line evidence, and spot-check one claim per agent against
  the tree before relying on the rest.

## 5. The verification bar

These are the failure modes the lessons log records most often. Each has a cheap counter-move.

| Failure mode | Lessons | Counter-move |
|---|---|---|
| The environment that failed is not the environment you tested in | `AL-765` (mutmut's `mutants/` copy), `AL-762` (CI-only drift guard), `AL-761` (cwd-relative path) | Reproduce the failing environment locally before declaring a fix: rebuild the copied tree, run from the same cwd, run the CI-only check by hand. One `-x` failure shows one cause per run; run without `-x` once to see the whole list. |
| A check existed and nothing invoked it | `AL-726` (guard battery), `AL-293`, `AL-305`, `AL-764` (workflow trap in a comment) | When you add or find a gate, add the test that fails if no workflow, hook, or nox session invokes it. A `#CRITICAL` comment that describes a property of the fleet (every scheduled workflow, every alert step) is the specification for a check, not a substitute for one. |
| A number in prose went stale | `AL-481`, `AL-551`, `AL-745`, `UW-G24` | Never transcribe a count into prose; cite the generated page (`catalog-census.md`) or date the number and name what re-derives it. |
| A grep stood in for a predicate | `AL-747`, `AL-481` | Verify a claim about derived behaviour by calling the function that derives it, never by searching for a symbol name. |
| The fix landed at one site and the lesson said applied | `AL-763`, `AL-759` | When a lesson quantifies over a class of call sites, `applied` requires enumerating the class in the applying commit and citing the enumeration in the `Ref`. |
| Merged read as deployed | roadmap M4.1 corrections, `UW-L07` | Production state is the deployed image revision (`org.opencontainers.image.revision`), never the merge. Say "merged, not confirmed deployed" until the revision is read. |
| A test passed for the wrong reason | `AL-055`, `AL-763`, `AL-757` | Falsify the test against the pre-fix tree before trusting it; a test that has never failed has proved nothing. |
| A mock or a default read as the real thing | `AL-624` (mock reviewer), `AL-769` | Any posture change on the moderation or provider path is followed by a review of every fixture and spec that pinned the old posture. |
| Two agents, one worktree | `AL-746` | Section 4 above. |

## 6. Recording

Every landing writes three things in the same commit series: the code, the register or lesson
rows, and the plan correction if a plan claim was found stale.

- A lesson qualifies when it cost real iteration, when tooling let a defect through, or when the
  next person would re-learn it. `applied`, `rejected`, and `superseded` need a `Ref` that proves
  it. An `open` lesson needs a `UW-C*` row citing it. Run `scripts/check_lessons_log.py` and
  `scripts/check_work_linkage.py` before committing; both are pre-commit hooks and CI checks.
- A register row's `Status` is one of `unscheduled`, `blocked`, `decision`, `verify`, `done`;
  there is no "in progress". Progress goes in the item text with a date; `done` needs evidence.
- A plan claim found stale is corrected in a dated note where it sits, not silently rewritten, and
  the roadmap's phase-status table must stay consistent with `plan-manifest.toml`'s two-axis
  `shipped`/`usable` model, which the linkage check enforces.
- Commit in units a reviewer can read: one signal fix per commit, ledgers in their own commit,
  Conventional Commits, signed. Push after each unit; a cloud session's container is ephemeral.

## 7. Reporting and handoff

The final message and any handoff document carry, in this order: what landed and where the proof
is, what could not be verified in this environment and exactly what will verify it (the next
scheduled run, a production query), the owner action list with commands, and the lessons recorded.
A handoff document follows the existing `handoff-*.md` shape: what the session was, what is
committed and citable, the resume runbook, the interruptions, the things a reader is likely to
get wrong, environment notes, lessons.

## 8. Related documents

- [CLAUDE.md](../../CLAUDE.md), "Implementation Session Protocol": the condensed rules.
- [Authoring lessons log](./authoring-lessons-log.md): the evidence behind section 5.
- [Unscheduled work register](./unscheduled-work-register.md): where owner-gated steps live
  (cluster M) and where open lessons get a phase home (cluster C).
- [Plan manifest](./plan-manifest.toml): the two-axis status model the roadmap table must match.
- [Roadmap](./roadmap.md) and [Project plan](./PROJECT-PLAN.md): the master documents, read
  after the registers, never instead of them.
