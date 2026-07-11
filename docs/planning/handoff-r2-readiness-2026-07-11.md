---
purpose: Comprehensive pre-R2 readiness review - full open-issue catalog, R1 debt-register audit, and the concrete gate list before starting Phase 6/8 (TestFlight) work
component: release planning, all open issues, r1-deferred-debt-register
source: R2 readiness review session 2026-07-11
---

# Handoff: R1 closeout verification and R2 (TestFlight) readiness

Written 2026-07-11. This doc answers one question comprehensively: what remains,
across every open issue and every deferred R1 item, before Phase 6/8 (the R2
TestFlight rung) can properly start. It supersedes the narrower R2-scoping pass
from earlier the same day (see memory `r2-testflight-readiness-2026-07-11`) with
a full review of all 23 open issues and the complete debt register, not just the
release-relevant subset.

Note the naming collision that recurs in this repo: "R2" means two different
things depending on context. On the **release ladder** (roadmap.md, ADR-008/009)
R2 is the TestFlight rung (Phase 6 + Phase 8). Separately, "R2" is shorthand for
**Cloudflare R2** object storage (PR #209/#210/#213), a already-merged, unrelated
piece of infrastructure. This doc is entirely about the release-ladder meaning.

## R1 status: verdict

**No genuine leftover R1 build work exists.** Both of Phase 4a's literal
acceptance criteria ("child sees only permitted stories," "guardian can assign
story to children") are delivered and merged. There is no R1 git tag, milestone,
or CHANGELOG release entry (only `v0.1.0`/backup tags exist, version is stuck at
0.1.0 due to issue #183/#157, see below) - R1's "done" status is asserted in
`roadmap.md`/`PROJECT-PLAN.md` prose, not in a formal release artifact, but the
underlying feature work checks out.

Two loose ends found, both documentation hygiene rather than functional gaps:

- **Issue #73** (401 interceptor never redirects to login) is cited in
  `PROJECT-PLAN.md` as a pending R1 release-readiness item. It is actually
  **closed** (completed 2026-07-06, superseded by the naive-UX inline-retry
  design). The `PROJECT-PLAN.md` citation is stale and should be corrected so a
  future reader doesn't chase a closed issue.
- Phase 4a's quality-gate checklist in `PROJECT-PLAN.md` still shows unchecked
  `[ ]` boxes (coverage, integration tests, security scan, lint/typecheck,
  pre-commit) despite the phase having merged through the required "CI Gate"
  aggregator. Read as a stale checkbox artifact, not unmet work - no open issue
  documents an actual Phase-4a gate failure. `[VERIFY]` if this matters before
  citing Phase 4a as complete in any external-facing doc.

**Issue #52** (sync `project-vision.md`/`tech-spec.md`/`roadmap.md` to Track 2 /
ADR-008-010) is open and real, but it is a documentation-sync task for the
public-launch track, not an R1 acceptance-criterion gap.

## Full open-issue catalog (23 issues, 2 PRs, reviewed 2026-07-11)

### Release-tooling / CI (5) - the closest thing to a true release blocker

| # | Summary | Gate relevance |
|---|---|---|
| #183 | `release.yml`'s `commit_parser` isn't a valid PSR v10 alias; every push fails | Root cause of version being stuck at 0.1.0 since project creation |
| #157 | Even after #183, semantic-release can't push version-bump commits (GH013, branch ruleset blocks direct push) | Same symptom, second blocking layer |
| #158 | PyPI publish step is dead code (app isn't a PyPI package) | Cleanup, do after #157/#183 |
| #187 | Promote Postman/newman `api-tests` into the required `ci-gate` once proven stable | Explicit, non-urgent gating condition |
| #172 | Codecov Bundle Analysis blocked by Vite 8 vs vite-plugin peer range 4-6 | CI nice-to-have, not blocking |

**These two (#183, #157) are the single clearest "must fix before a real release"
item in the whole catalog** - a TestFlight build needs a meaningful version tag,
and right now nothing can bump past 0.1.0.

### Security / RLS / auth (4)

| # | Summary | Gate relevance |
|---|---|---|
| #125 | Supabase RLS not enabled on 13 public tables (advisor-flagged critical) | Explicitly scoped as **R2 hardening in the issue body itself**, not an R1 blocker (backend already bypasses RLS via the `postgres` role, so this is defense-in-depth) |
| #138 | `FORWARDED_ALLOW_IPS` too broad (Docker bridge /12 range) | Security hardening, not release-gating on its own |
| #72 | `get_generation_job` leaks raw LLM `report` to guardians (contradicts ADR-007) | Should resolve before any surface guardians outside the current trust boundary can reach it |
| #71 | No app-wide rate limiting; intake UI polls unbounded every 8s | Matches Phase 5 (Hardening) scope, relevant once public/non-family traffic is possible |

### Known bugs (3)

| # | Summary |
|---|---|
| #144 | Stage-0 moderation classifiers handle NaN/Infinity asymmetrically (child-safety path, low reachability) |
| #137 | Auth/permission/empty-list states render one generic error (naive-UX finding F1; partially addressed by PR #198 on the kid surface per the design-sync handoff) |
| #67 | `coverage.py` under-reports `api/profiles.py` async-handler hits on CPython 3.12 (SonarCloud gate false negative) |

### Backlog / story-scale features (5) - not release-gating, longer-tail

#173 (`family_id` nullable, blocks WS-E catalog scope), #79 (corpus guard test),
#78 (`brief.length` propagation gap), #77 (off-matrix prompt guidance), #63
(`storybook_version.provider` column missing).

### Documentation / UX follow-ups (5)

| # | Summary | Note |
|---|---|---|
| #214 | Backfill pre-R2-migration cover URLs from Supabase Storage into Cloudflare R2 | Storage-R2 cleanup (the *other* R2), should close before calling that cutover finished |
| #204 | Redesign naive-ux-check scenarios against the real staging pipeline | Unblocked now (Supabase environments workstream complete); spec exists on unpushed local branch `docs/naive-ux-check-scenario-redesign-design`, see the design-sync handoff doc |
| #88 | Decide/document whether `generation_job.report` stays guardian-visible | Docs-vs-behavior mismatch, low urgency |
| #74 | Guardian console "Still processing" section inert for admins | Shipped intentionally as a safe placeholder |
| #52 | Sync vision/tech-spec/roadmap docs to Track 2 (ADR-008-010) | Real, but doc-hygiene not code |

### Dependency / chore (1)

#25 - Renovate Dependency Dashboard, auto-managed housekeeping meta-issue.

### Open PRs (2, both Renovate automation, re-verified 2026-07-11 after this doc's first draft)

- **#212** `chore(deps)!: Update dependency typescript to v7` - breaking-change
  label, `mergeStateStatus: BEHIND`, 3 failing checks among ~36. Needs a real
  look at what's failing before merge, not a rubber stamp.
- **#211** `chore(deps): Update GitHub Actions to 75537da` - `mergeStateStatus:
  UNSTABLE`, otherwise routine digest bump.

(PR #215, README refresh, was open during the first pass of this review and
merged mid-session at `3f09732` - confirms the open-PR list changes quickly;
re-check with `gh pr list` before acting on this section.)

## R1 deferred-debt-register: full inventory

Source: `docs/planning/r1-deferred-debt-register.md` (added via PR #197,
2026-07-11). Condensed here; read that file directly for full detail.

**R2 gate items** (the only ones that literally block Phase 6/8):
- **G1** - kid surface runs under the guardian's bearer token, no child-scoped
  session. **Open. This is the one hard R2 gate in the whole register.**
- G2 (admin-submit gap, issue #57) - **closed**, resolved via Task E4.
- G3 (control-character strip gap, issue #64) - **closed**, resolved via Task E4.

**Everything else in the register is either resolved, informational, or
explicitly scoped as R2-planning input rather than a blocker**: correctness
items C1-C5 (one resolved via PR #145), generation/safety GS1-GS2, UX items
U1-U4, test/tooling T1-T9 (two resolved), policy/architecture P1-P4, and the
story-lifecycle-redesign SL1-SL10 series (all merged 2026-07-10, all Low/Info
severity or v2-scoped). None of these carries a stated severity or gate above
"decide before/during R2," and none blocks starting Phase 6 work.

## The actual gate list: what must happen before Phase 6/8 work starts

In priority order:

1. **G1** - design and build child-scoped session/role separation for the kid
   surface. This is the one item everything else is downstream of; it's also
   the reason Phase 6 (P6-06 frontend auth) is only partially built.
2. **Issue #125** - enable Supabase RLS on all public tables. Independently
   corroborates G1 as the right first move: both are "don't expose the current
   trust model to non-family users" gates.
3. **Complete Phase 6** (P6-03 through P6-10 per `PROJECT-PLAN.md`) - frontend
   Keychain/Capacitor deep-link/401-retry work, plus whatever P6-03/04/07/08/10
   cover. Phase 6 blocks Phase 8 outright per the roadmap dependency graph.
4. **Start Apple Developer Program enrollment now** (P7-01) - it's filed under
   Phase 7 but is a hard prerequisite for TestFlight distribution and for
   P6-05; the lead time argues for starting it in parallel with #1-3, not
   after.
5. **Fix #183 then #157** - without these, there is no way to cut a version-
   tagged TestFlight build; this is pure release-tooling and can happen any
   time in parallel with the above.
6. **Issue #214** - finish the Cloudflare R2 cover-art backfill so the storage
   cutover is genuinely complete before more R2-storage-dependent work lands.

Everything else in this doc (the other 17 open issues, the rest of the debt
register) is real backlog worth triaging but does not block Phase 6/8 kickoff.

## Repo hygiene noted during this review (no dependency on the above)

- `docs/planning/handoff-design-sync-naive-ux-2026-07-11.md` is untracked in
  the working tree - it documents finished, already-merged work (design-sync
  promotions + naive-ux redesign follow-ons) and should be committed as-is,
  not treated as in-flight work.
- `.worktrees/lifecycle-debt-backlog` is stale (PR #197 already merged) - safe
  to remove.
- `.worktrees/naive-ux-spec` is active (issue #204 spec branch) - keep.
- `known-vulnerabilities.md`'s two dev-only entries (PYSEC-2022-42969,
  PYSEC-2026-89) hit their reassessment date 2026-07-20 - unrelated to R2 but
  close enough to flag.

## How to resume

Immediate next action: decide sequencing among the six gate items above -
recommend G1 (session separation) first since Phase 6's remaining frontend
work and the RLS decision both depend on knowing the target session model.

```bash
git fetch --all && gh issue list --state open && gh pr list --state open
```
Re-run this before acting - the open-PR list alone changed twice during this
review's writing.

## Gotchas

- Don't conflate the two "R2"s in conversation or in issue titles; #214 is
  about *storage* R2, everything else here is about *release* R2.
- `PROJECT-PLAN.md`'s citation of #73 as a pending R1 item is stale
  `[VERIFY]` - confirm before repeating it elsewhere.
- CodeRabbit skips PRs whose base isn't the default branch; a green check
  after rate-limiting does not mean a review ran (carried over from the
  design-sync handoff, still true).
