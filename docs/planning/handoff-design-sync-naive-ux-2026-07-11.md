---
purpose: Handoff for the two remaining post-UX-workstream efforts, design-system sync promotions and the naive-ux scenario redesign
component: frontend design system, naive-ux-check scenarios
source: UX workstream session 2026-07-11 (PRs 198, 206, 209, 210)
---

# Handoff: design-sync promotions + naive-ux scenario redesign

Written 2026-07-11 at the close of the UX workstream. All four workstream PRs
are merged to main (`f593650`): #198 kid auth-gate UX, #206 guardian console
refresh, #209 R2 cover storage, #210 illustrated avatar set (issue #65 phase 1
closed). This doc scopes the two follow-on efforts a fresh session should pick
up. They are independent; either can go first.

## Effort 1: design-system sync (@ds promotions)

PR #206 consolidated the guardian console CSS into shared `:is()`-grouped
patterns but deliberately did NOT promote them into the `@ds` design-system
workspace. The recorded promotion backlog:

- **Card**: the five card families (`.console-row`, `.profiles__card`,
  `.intake-request`, `.review-card`, `.books__row`) now share one grouped rule
  in `frontend/src/guardian/guardian.css`; promote to a `@ds` Card primitive.
- **FormField**: the four form-field stacks share grouped rules; promote.
- **Chip**: pill/chip styling (`.intake-chip` etc.); promote.
- **Text-tone utilities**: the ~11 error/notice/muted text rules.
- **Button ghost/primary contrast question (decide ONCE, cross-surface)**:
  bright `--color-amber` (#e07f2e) as text on parchment fails WCAG at 2.62:1;
  guardian surfaces moved failing uses to `--color-amber-deep` (#c17b2a). The
  shared `@ds` Button ghost variant still carries the bright amber and is used
  by BOTH kid and guardian surfaces. Decide the token change once at the @ds
  level rather than per-surface.
- **Maybe**: extract the Pip `Mascot` component to `@ds`. Related but separate:
  Pip pose variants (`welcome`/`empty`/`ending`) are #65 phase 2, currently
  untracked after #65 closed; open an issue if picking this up.

Constraints and context:

- **FlagBadge stays bespoke permanently** (ADR-005 safety semantics). Never
  promote it. Test-pinned class names that must not be renamed:
  `form.profile-form`, `.flag-badge--{tone}`, `.flag-badge--flag`.
- Per `~/.claude/rules/design.md`, design-system tooling is a mid-pipeline
  sync step after real components exist. That precondition is now satisfied;
  `/design-sync` is the correct stage.
- Tooling: the claude-design MCP server is configured per-UI-repo (see
  `~/.claude/standards/claude-design-setup.md`); the `.design-sync/` directory
  in `frontend/design-system/` holds config, previews, and `conventions.md`
  (AvatarCircle entries were removed in PR #210 when the orphaned @ds copy was
  deleted; do not restore them).
- The design-system workspace has its own vitest config, coverage run, and
  Codecov `design-system` flag (separate CI job).

## Effort 2: naive-ux scenario redesign (issue #204)

- **Spec and implementation are both in open PRs**: PR #216 pushes the spec
  (`docs/superpowers/specs/2026-07-10-naive-ux-check-scenario-redesign-design.md`,
  211 lines after revision; the branch history was rewritten, so any older SHA
  citation for `docs/naive-ux-check-scenario-redesign-design` no longer
  resolves), and PR #220 implements the redesigned scenarios. First step:
  review and land #216 then #220 (merges are owner-gated); do not restart from
  the spec.
- **The blocker is gone**: the spec was written when scenarios could only run
  against local dev. The Supabase environments workstream is COMPLETE:
  staging and prod are migrated, staging is seeded and sign-in verified. #204
  ("Redesign naive-ux-check scenarios on top of the staging environment") is
  fully unblocked.
- **What changed since the scenarios were written**: the auth-gate findings
  that motivated the redesign are largely FIXED. F1 (one generic error for
  auth/permission/empty states, tracked as issue #137, which remains open) was
  addressed on the kid surface by PR #198 (differentiated gates in
  ProfilePickerPage/LibraryPage via classifyApiError); the guardian surface
  already used classifyApiError. The redesigned
  scenarios must assert the NEW gate copy, not the old "Oops, we hit a snag".
  Known intentional behavior: admin gets 403 on profile-create BY DESIGN.
- Scenario tiers: mocked Playwright tier runs in CI (`frontend/e2e/`);
  `e2e-real/` is local-only. Route or copy changes must grep BOTH.
- Staging gotchas (from the infra session, see memory
  `supabase-environments-pipeline-state`): staging uses legacy `eyJ` keys and
  a different pooler host than prod; `uv run --env-file` never overrides
  shell-exported variables.

## Operational constraints (both efforts)

- Branch-first, worktrees at `.worktrees/<slug>`, `uv sync --all-extras` and
  `cd frontend && npm install` per worktree as needed.
- Signed conventional commits; commit at checkpoints autonomously, but every
  `git push` and PR-open is owner-gated. Merges go through the merge queue;
  CHANGELOG entry or `skip-changelog` label required.
- The main working tree is shared with concurrent sessions; never commit from
  it, and always `cd`/`-C` explicitly in background commands.
- The FIPS Compatibility PR comment ("5 errors, FAILED") is a known checker
  false positive (bare `seed` cipher-name match on `seed_staging.seed()`
  calls); the check itself passes. Ignore the comment; do not rename the
  functions (tracked in `docs/template_feedback.md`).
- CodeRabbit skips PRs whose base is not the default branch, and a green
  CodeRabbit check after rate-limiting does not mean a review ran.

## Kickoff prompt for the new session

> Read docs/planning/handoff-design-sync-naive-ux-2026-07-11.md, then pick up
> the two remaining efforts: (1) /design-sync promotions of the guardian
> console patterns into @ds (Card, FormField, Chip, text tones) plus the
> cross-surface Button amber-contrast decision; (2) the naive-ux scenario
> redesign per the spec in PR #216, with the implementation in PR #220
> (review and land those PRs first), now unblocked by the live staging
> environment (issue #204). Plan both,
> confirm sequencing with me, then execute with the usual worktree and
> owner-gated-push discipline.
