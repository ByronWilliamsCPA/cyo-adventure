---
name: naive-ux-check
description: Surface the next unrun Claude-for-Chrome naive-user comprehension prompt (kid, guardian, or admin persona), and log the pasted-back response to a dated findings report. Use before a release, or whenever you want a fresh naive-user pass over the app.
---

# naive-ux-check

Organizes the naive-user comprehension prompt set
(`.claude/skills/naive-ux-check/scenarios.json`, 17 scenarios total: K0-K4,
G0-G7, A0-A3) and logs results. This skill does not drive a browser itself;
there is no Claude-for-Chrome tool available to this session, so it hands
you a prompt to paste into the extension by hand.

`scenarios.json` is the single source of truth for these scenarios; there
are no separate prose files to keep in sync. Each entry has: `id`,
`persona` (`kid` / `guardian` / `admin`), `name` (short scenario name),
`persona_text`, `task_text`, `report_back_questions[]`,
`requires_credentials`, `production_safe`, and `operator_notes` (an object
with `operator_setup[]`, `operator_note[]`, `persona_context[]`, and
`expected_observations[]`, all human-only, see step 4). The array order is
the selection order: kid scenarios (K0-K4) first, then guardian (G0-G7),
then admin (A0-A3), with each persona's auth-gate scenario (K0, G0, A0)
first within its group. The automated persona runner planned for D2b will
read the same file, so a manual and an automated run always test the same
scenarios.

`render.py` (`.claude/skills/naive-ux-check/render.py`) is the single
composer of the paste block; it is what step 4 below runs, and the same
module a D2b automated runner is expected to import rather than writing a
second composer. It reads an explicit allowlist of exactly three
model-facing fields (`persona_text`, `task_text`, `report_back_questions`)
off a scenario record: `operator_notes` (all four of its sub-keys) is never
read by it, by construction, and neither is any field added to the schema
later. `tests/unit/test_naive_ux_scenarios.py` imports this module directly
and asserts its output equals an independently-built reference, so a change
that made it read anything beyond the allowlist would fail that suite.

## What to do when invoked

1. Ask the user which target URL to test against. The default is the local
   dev frontend pointed at the staging Supabase project via `.env.staging`
   (the committed `.env.staging.example` documents the required variables,
   including the `VITE_*` pair the frontend needs). Staging is the default
   because the dedicated seeded test credentials (`SEED_GUARDIAN_EMAIL` /
   `SEED_ADMIN_EMAIL`, provisioned by `scripts/seed_staging.py`) live there;
   live production has no account this skill should use. Targeting live
   production is an explicit, occasional, deliberate choice the user must
   state up front, and it supports only the scenario whose data record has
   `production_safe: true`: K0, which observes the signed-out auth gate
   without ever signing in. Every other scenario has `production_safe:
   false`: it either signs in with the seeded credentials (which exist
   only on staging) or mutates content, and the standing rule still
   applies: the mutating personas (G4/G5/G6, A2/A3) submit, approve, or
   decline real content, so run them only against the seeded staging
   environment (or another disposable, seeded, non-production
   environment); never point them at production, where the browsing agent
   could approve or alter real stories.
2. Read `docs/qa/naive-ux-reports/` and find the most recent dated report, if
   any. Collect which of the 17 scenario ids (K0-K4, G0-G7, A0-A3) already
   have an entry in it.
3. Pick the first scenario, in `scenarios.json` array order (K0-K4, G0-G7,
   A0-A3, auth-gate scenarios first within each persona), whose `id` has no
   entry yet in the most recent report. If no report exists yet, that is the
   first entry, K0. Always hand off exactly one scenario per invocation
   (step 4); the user re-invokes for the next one (step 7).
4. Get the paste block by running the renderer, never by composing it
   yourself:

   ```text
   python3 .claude/skills/naive-ux-check/render.py <scenario id> <target URL from step 1>
   ```

   Its stdout is the block to paste, verbatim, in the shape:

   ```text
   Persona: <persona_text>

   Task: <task_text>

   Report back:

   1. <report_back_questions[0]>
   2. <report_back_questions[1]>
   ...
   ```

   `render.py` reads only `persona_text`, `task_text`, and
   `report_back_questions[]` off the scenario record; it never reads
   `operator_notes` (`operator_setup`, `operator_note`, `persona_context`,
   or `expected_observations`), by construction. Do not append, inline, or
   otherwise relay any `operator_notes` content into the pasted block
   itself; where any of it needs to reach the user at all, say it
   separately, in your own words to the user, outside the pasted text.
   Where the rendered task text carries `<EMAIL>` / `<PASSWORD>`
   placeholders, remind the user to fill them with the seeded credentials
   before pasting. Where `operator_notes.operator_setup` is non-empty,
   relay it to the user before they paste (it covers things like starting
   from a signed-out browser or signing in first).
5. Tell the user: "Paste this into the Claude-for-Chrome extension, then
   paste its response back here."
6. When the user pastes back a response, first REDACT it, then append one row
   to today's report at `docs/qa/naive-ux-reports/YYYY-MM-DD.md` (create the
   file with a one-line header if it doesn't exist yet for today). Redaction is
   mandatory because the browsing agent reports on-screen content that can
   include real children's and guardians' names, emails, and account details:
   replace emails, child/guardian display names, session tokens, and
   correlation ids with placeholders (`<email>`, `<child-name>`), and summarize
   rather than paste verbatim whenever the target is not localhost. Never commit
   an unredacted transcript. (The report directory is also gitignored, see
   `.gitignore`, so a report stays local until you deliberately sanitize and
   force-add it.)

   ```markdown
   ## <scenario id>: <scenario name>

   **Verdict:** pass | friction-found | dead-end

   <redacted summary of the pasted-back response>
   ```

   The scenario name for the heading is that scenario's `name` field.

7. Ask whether to continue with the next unrun scenario or stop here.

## Judging the verdict

- **pass**: the response's four answers show no confusion, no dead end, and
  no unexpected action.
- **friction-found**: at least one point of confusion or an unexpected
  result, but the persona ultimately succeeded or reached a sensible stop.
- **dead-end**: the persona could not proceed at all, or ended up somewhere
  clearly wrong (another family's content, an admin action with no visible
  gate, etc).
- For the auth-gate scenarios (K0, G0, A0) specifically: a clear, friendly,
  correctly-functioning auth gate (a real invitation to sign in or to find a
  grown-up, not an error page or a retry loop) is a **pass**, even though
  the persona cannot proceed past it without credentials or a grown-up. A
  gate that is confusing, mislabeled, or broken (like the pre-PR-#198
  "Oops, we hit a snag" loop) is still **dead-end** or **friction-found**
  under the rules above.

A **dead-end** means the persona could not proceed or landed somewhere clearly
wrong, so file it immediately as a GitHub issue (and consider a Track A
Playwright regression) on the first hit. A single **friction-found** result is
logged, not immediately escalated; only file or promote it if it reproduces on
a second run of the same scenario.
