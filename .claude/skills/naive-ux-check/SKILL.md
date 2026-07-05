---
name: naive-ux-check
description: Surface the next unrun Claude-for-Chrome naive-user comprehension prompt (kid, guardian, or admin persona), and log the pasted-back response to a dated findings report. Use before a release, or whenever you want a fresh naive-user pass over the app.
---

# naive-ux-check

Organizes the naive-user comprehension prompt set
(`.claude/skills/naive-ux-check/prompts/{kid,guardian,admin}.md`, 14 scenarios
total: K1-K4, G1-G7, A1-A3) and logs results. This skill does not drive a
browser itself; there is no Claude-for-Chrome tool available to this session,
so it hands you a prompt to paste into the extension by hand.

## What to do when invoked

1. Ask the user which target URL to test against (default: the local dev
   frontend, typically `http://localhost:5173`).
2. Read `docs/qa/naive-ux-reports/` and find the most recent dated report, if
   any. Collect which of the 14 scenario ids (K1-K4, G1-G7, A1-A3) already
   have an entry in it.
3. Pick the first scenario id, in the order K1-K4, G1-G7, A1-A3, that has no
   entry yet in the most recent report (or all 14, if no report exists yet).
4. Print that scenario's full prompt block from its persona file, with the
   `<URL>` placeholder replaced by the target URL from step 1.
5. Tell the user: "Paste this into the Claude-for-Chrome extension, then
   paste its response back here."
6. When the user pastes back a response, append one row to today's report at
   `docs/qa/naive-ux-reports/YYYY-MM-DD.md` (create the file with a one-line
   header if it doesn't exist yet for today):

   ```markdown
   ## <scenario id>: <short scenario name>

   **Verdict:** pass | friction-found | dead-end

   <the verbatim pasted-back response>
   ```

7. Ask whether to continue with the next unrun scenario or stop here.

## Judging the verdict

- **pass**: the response's four answers show no confusion, no dead end, and
  no unexpected action.
- **friction-found**: at least one point of confusion or an unexpected
  result, but the persona ultimately succeeded or reached a sensible stop.
- **dead-end**: the persona could not proceed at all, or ended up somewhere
  clearly wrong (another family's content, an admin action with no visible
  gate, etc).

Only findings that reproduce on a second run of the same scenario should be
filed as a GitHub issue or promoted into a Track A Playwright regression;
a single friction-found result is logged, not immediately escalated.
