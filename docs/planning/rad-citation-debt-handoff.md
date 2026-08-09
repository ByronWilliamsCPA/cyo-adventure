---
schema_type: planning
title: "Handoff: RAD #VERIFY Citation Debt (baseline D-2)"
description: "Work order for the separate team retiring the RAD #VERIFY citation baseline (136
  grandfathered stale citation sites across 121 distinct file/citation pairs): the derived
  numbers, the gate's real ceiling, the split between CI scope (whole tree) and hook scope
  (narrow), the one tree neither scans, the fix-one-row workflow with
  its shrink-only contract, and a suggested attack order."
tags:
  - planning
  - tooling
  - technical-debt
  - rad
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Assign the RAD citation backlog to a receiving team with the numbers derived rather
  than quoted, and with the gate's ceiling stated before the numbers, so nobody reads an empty
  baseline as proof that the RAD claims are verified. The document assigns the work; it fixes
  no row itself."
component: Tooling
source: "rad-citation-baseline.toml (136 grandfathered sites across 121 distinct file/citation
  pairs, parsed with tomllib on 2026-08-08);
  scripts/check_rad_citations.py module docstring, Deliberate non-goals;
  .pre-commit-config.yaml:398-399 (the hook's files: key and its scope regex, verified against
  the live config); .github/workflows/ci.yml (the rad-citations job, --all over the whole tree,
  shipped in d9a6a93e);
  CLAUDE.md Response-Aware Development section; src/cyo_adventure/CLAUDE.md RAD Assumption
  Tagging section. Gate shipped in 65ee8ffc on branch feat/persistent-characters-runtime."
---

# Handoff: RAD #VERIFY citation debt (baseline D-2)

Written 2026-08-08, at the point where the gate that stops new debt has just shipped and the
existing debt has just been counted and frozen. This document assigns the backlog; it does not
work any of it.

## The ceiling first, because it changes what "done" means

Before any numbers: fixing every row in `rad-citation-baseline.toml` does not mean the RAD
markers in this codebase are correct. It means every `#VERIFY` line names a test that exists.
Those are different claims, and the gap between them will not close on its own.

`scripts/check_rad_citations.py` can only check that a cited test resolves: the file is there,
or the function is defined in the file named. It cannot run the test, and it cannot ask whether
the test would fail if the assumption tagged above it were violated. A test named
`test_approve_stamps_resulting_storybook_id` that exists, imports cleanly, and passes every time
satisfies the checker completely whether or not it actually exercises the claim its citation sits
under. During the same workstream that built this gate, nine citations were written that named a
real, passing test proving nothing about the claim above it, and the checker passed all nine,
silently, because telling a discriminating test from a coincidentally-passing one is a human
judgment call, not a static check. It will pass the next nine just as quietly.

So the target state after this backlog is cleared is "every `#VERIFY` name refers to a real
test." It is not "every RAD claim is proven." Treat a row as closed only once a person has looked
at the assumption, looked at the test, and confirmed the test would actually fail if the
assumption stopped holding. A row where the citation now resolves but nobody made that check is
not fixed; it has just moved from "obviously wrong" to "silently unverified," which is worse
because nothing will ever flag it again.

## What the backlog is

This repository tags production-risk assumptions in source comments with `#CRITICAL`, `#ASSUME`,
or `#EDGE` markers, each paired with a `#VERIFY` line that names the test proving the assumption
holds. The convention is mandatory for anything touching async I/O, database access, external
APIs, auth, or concurrency (see `src/cyo_adventure/CLAUDE.md`). Over the life of the project, many
of those `#VERIFY` citations went stale: the named test was renamed, deleted, or was never written
in the first place, so the citation points at nothing. A stale citation is worse than no citation:
it reads as proof the assumption is guarded while the thing it names does not exist.

`scripts/check_rad_citations.py` now resolves every `#VERIFY` citation it can parse against the
repo's real test files and functions, and fails on anything unresolvable. It runs in two places
with two scopes: the `check-rad-citations` pre-commit hook (`.pre-commit-config.yaml:392`) over
staged files in the narrow pattern below, and the `rad-citations` CI job
(`.github/workflows/ci.yml`, shipped in `d9a6a93e`) over the whole tree with `--all`. CI is the
authoritative scope; see "What the gate does NOT cover" below. Because the
existing stale citations vastly outnumber what one commit could fix, they were captured into
`rad-citation-baseline.toml` as a grandfathered list: the gate does not fail on anything already
in that file, only on citations that are new or newly broken. That baseline file is this backlog.
It can only shrink; a row whose citation has been fixed but was left in the file is itself flagged
as an error (a "the checker reports rows that are no longer stale" failure), so debt cannot be
faked by leaving stale rows behind after fixing the underlying citation.

## The numbers (derived directly from the baseline file, not from its header count)

Parsed `rad-citation-baseline.toml` with `tomllib` rather than trusting header arithmetic. The
baseline was rewritten since this handoff was first drafted: it is now keyed **per grandfathered
site** rather than per distinct citation string, so a citation that is stale in three places in
one file now occupies three rows, not one. Two counts follow from that, and they answer different
questions, so keep them separate:

> **Correction (2026-08-08):** these figures previously read 137 sites / 122 pairs. That was the
> file's header comment, and it was stale by exactly one in both counts: someone had fixed one
> citation in `scripts/reset_e2e_real_state.py` and hand-deleted its row, as the workflow below
> requires, without re-running `--write-baseline` to regenerate the header that summarizes the
> body. Regenerating the baseline reproduced a byte-identical body and rewrote only the header
> comment, which is how the drift was confirmed to be in the comment, not the debt. The header is
> now correct; every count below reflects the live file.

- **136 grandfathered sites**, all in the `[python]` table; `[typescript]` is empty (0 rows). This
  is the file's row count today, and it is **the number the gate's `--assert-no-growth BASE_REF`
  ratchet compares against a base ref: it must only ever go down.** Treat 136 as the ceiling this
  backlog is measured against.
- **121 distinct (file, citation) pairs**: the count of distinct work items, each one a citation to
  repoint, write, or delete. At the point the per-site rewrite was verified, this count was 122,
  exactly the file's row count from before that rewrite, which is how we know the rewrite itself
  was purely additive duplication and grandfathered nothing new. One pair has since been fixed and
  its row deleted (the `scripts/reset_e2e_real_state.py` fix described in the correction above),
  bringing the live count to 121; that drop is a real fix landing, not baseline drift.
- The globally distinct citation **string** count is **120**, not 121: one citation string repeats
  across two different files (`test_reclaim_after_completed_run_does_not_re_execute`, shared by
  `src/cyo_adventure/generation/worker.py` and `src/cyo_adventure/generation/queue.py`). Do not
  write "121 distinct citation strings"; that number is the pair count, not the string count.
- **48 distinct files** carry at least one row: **45 under `src/`** (123 sites, 111 pairs) and
  **3 under `scripts/`** (13 sites, 10 pairs). There is no third tree; every baselined file is
  under `src/` or `scripts/`.
- **7 files contain a repeated citation string**, and those repeats contribute the **15 extra
  sites** (136 minus 121). Those seven, as pairs to sites:

  | Pairs | Sites | File |
  | --- | --- | --- |
  | 7 | 10 | `scripts/reset_e2e_real_state.py` |
  | 8 | 12 | `src/cyo_adventure/api/generation.py` |
  | 5 | 6 | `src/cyo_adventure/api/story_requests.py` |
  | 9 | 12 | `src/cyo_adventure/db/models.py` |
  | 1 | 2 | `src/cyo_adventure/generation/provider.py` |
  | 5 | 6 | `src/cyo_adventure/generation/worker.py` |
  | 3 | 5 | `src/cyo_adventure/moderation/classifiers.py` |

- Top files by **site** count, where the work concentrates (72 of 136 sites, just over half):

  | Sites | Pairs | File |
  | --- | --- | --- |
  | 12 | 8 | `src/cyo_adventure/api/generation.py` |
  | 12 | 9 | `src/cyo_adventure/db/models.py` |
  | 10 | 7 | `scripts/reset_e2e_real_state.py` |
  | 7 | 7 | `src/cyo_adventure/api/node_edit.py` |
  | 6 | 5 | `src/cyo_adventure/api/story_requests.py` |
  | 6 | 5 | `src/cyo_adventure/generation/worker.py` |
  | 5 | 5 | `src/cyo_adventure/api/device_grants.py` |
  | 5 | 3 | `src/cyo_adventure/moderation/classifiers.py` |
  | 5 | 5 | `src/cyo_adventure/moderation/rescreen.py` |
  | 4 | 4 | `src/cyo_adventure/api/flags.py` |

  Ranking by sites is not the same top ten as ranking by pairs: it brings in
  `src/cyo_adventure/moderation/classifiers.py` (3 pairs, 5 sites) and drops
  `src/cyo_adventure/api/profiles.py` (4 pairs, 4 sites).

### Reproducing these numbers

Do not re-quote the figures above; re-derive them, the same way this correction was found. Either
command reads the live baseline rather than trusting a comment that can drift from it:

```bash
# Rewrites the header to match the body; diff the file afterward to see if anything moved.
uv run python scripts/check_rad_citations.py --write-baseline --all

# Or parse it directly without writing anything:
python3 -c "
import tomllib
with open('rad-citation-baseline.toml', 'rb') as f:
    py = tomllib.load(f)['python']
sites = sum(len(v) for v in py.values())
pairs = sum(len(set(v)) for v in py.values())
print(f'{len(py)} files, {pairs} pairs, {sites} sites')
"
```

`--write-baseline --all` is the authoritative form: it is the same command that generated this
file's body, so its header is definitionally correct against the body it just wrote. A header that
disagrees with a fresh `--write-baseline --all` run, with an unchanged body, is exactly the failure
mode this correction fixes: someone deleted a row by hand instead of running the regeneration
command afterward.

### Why the file is keyed per site, not per citation string

The baseline used to list each citation string once per file, so a citation that was stale in
three places in one file was grandfathered by a single row, and a fourth stale occurrence of that
same citation could be added later without the gate ever noticing, since the row already existed
and the checker was only confirming the string resolved somewhere in the file. Keying per site
closes that gap: every occurrence now needs its own row, so a new stale site is a new, uncovered
row rather than free coverage under an existing one. The practical consequence for the team
clearing this backlog is that one fix often clears several rows at once, since the seven files
above each repeat a citation string, so the row count will fall faster than the file or pair count
as work proceeds.

### Gate state, verified by running it

```bash
uv run python scripts/check_rad_citations.py --all
```

Exit code: **0**. The run printed **11 non-failing notes** and nothing else; there are currently
zero "stale" findings (a citation resolving to nothing) and zero "baseline drift" findings (a
baselined row whose citation has since been fixed and should have been deleted but was not). In
other words: the baseline accurately reflects the current backlog, no new debt has crept in since
it was written, and the file that has to shrink over the life of this workstream is doing so from
a clean starting line, not one that is already lying about its own count. See the "notes, not
failures" section below for what the 11 notes are; they are not part of this backlog's 121 pairs
(136 sites).

## What the gate does NOT cover (CI scope and hook scope are different)

The authoritative scope is CI, not the hook, and the two are deliberately different sizes. Read
them separately or you will understate the gate by two whole trees.

**CI scope: the whole tree.** As of `d9a6a93e` on this branch, the `rad-citations` CI job
(`.github/workflows/ci.yml`) runs `scripts/check_rad_citations.py --all` on every push, pull
request and merge_group, so the authoritative gate scope is the WHOLE TREE, including `tests/`
and `frontend/e2e/`. That job is also a required input to the `ci-gate` roll-up, so a stale
citation anywhere in those trees fails the build regardless of local hook state, and
`git commit --no-verify` no longer bypasses it.

**Hook scope: narrower, on purpose.** The pre-commit hook stays narrower: staged files within
`src/`, `scripts/`, `frontend/src/`, plus every baselined file. Its `files:` pattern, at
`.pre-commit-config.yaml:398-399`, is:

```text
^(src/.*\.py|scripts/.*\.py|frontend/src/.*\.tsx?|rad-citation-baseline\.toml)$
```

The narrowness is a latency choice for the commit path, not a statement about what is guarded.
CI is what guards.

**What is genuinely uncovered: `supabase/` (SQL) only.** `--all` walks Python, TypeScript and
TSX; it does not parse SQL, so `#VERIFY` markers inside `supabase/` migrations are the one tree
no run of this gate inspects. That, and only that, is scope this backlog does not cover and
would be new work. Do not restate `tests/` or `frontend/e2e/` as uncovered: `--all` walks them,
which the run quoted above demonstrates directly through its
`tests/integration/test_cover_service.py:78` note.

**`--write-baseline` is not an escape hatch.** It is a maintenance command to pair with
`--assert-no-growth` review, never a way to clear a CI failure. Regenerating the baseline to make
a red job green re-grandfathers the very debt this workstream exists to retire, which is the
failure mode `AL-130` / `UW-C65` records after it happened once already.

## Workflow for fixing one row

1. **Find the citation site.** The baseline key is `(file, citation text)`, not a line number, by
   design (see the header comment in `rad-citation-baseline.toml`): unrelated edits above a
   citation must not churn the baseline. To find the actual line, `grep -n` the citation text (or
   a distinctive substring of it, since long names wrap across comment lines) inside the file the
   row names. For example, for the row `"src/cyo_adventure/api/deps.py"` is not itself baselined,
   but if it were, `grep -n "test_require_principal_child_branch_scopes" src/cyo_adventure/api/deps.py`
   would land you on the `#VERIFY` line.
2. **Read the assumption above the citation, not just the citation.** The `#CRITICAL` /
   `#ASSUME` / `#EDGE` line immediately above (or the docstring block it lives in) states the
   property being claimed. You cannot judge whether a test discriminates a claim you have not
   read.
3. **Decide among three outcomes:**
   - **Write the missing test.** No test with a plausible name or purpose exists anywhere for
     this assumption. Write one that would fail if the assumption were violated, name it, and
     update the citation to match.
   - **Repoint to an existing test that genuinely discriminates the claim.** Sometimes the named
     test was simply renamed and a near-identical, still-correct test exists under a new name
     (see the worked example below for exactly this case). Confirm it actually exercises the
     claimed property before repointing; do not repoint on name-similarity alone.
   - **Delete the marker.** The assumption no longer applies (the code path was removed, the
     invariant was superseded by a different design, the risk the marker was guarding against no
     longer exists). Delete the `#CRITICAL`/`#ASSUME`/`#EDGE` and `#VERIFY` lines together; do not
     leave an orphaned marker with no citation, and do not leave a citation with no marker.
4. **Delete the baseline row in the same commit as the fix.** This is not a cleanup step to defer;
   it is the contract the checker enforces. `check_rad_citations.py` re-scans every file the
   baseline mentions on every run (not just the files a given commit touches), specifically so it
   can tell when a baselined citation is no longer stale. If you fix the citation but leave its
   row in `rad-citation-baseline.toml`, the next run reports that row as baseline drift, an error
   telling you to delete it. The reason this is enforced rather than left to memory: a baseline
   that can silently keep rows nobody needs anymore is a baseline that can be gamed by fixing
   citations without ever shrinking the number the team is accountable for. Shrink-only, checked
   automatically, is what keeps 136 an honest number instead of a ratchet that only the last
   editor's memory prevents from drifting upward.

## Suggested order of attack

Work by file, not by scattering one-row fixes across the tree, because the "read the assumption,
decide, fix, delete the row" cycle has a fixed cost per file (open it, understand the surrounding
code) that amortizes over multiple rows in the same file. On that basis:

1. **Start with the concentration.** The ten files listed above hold 72 of 136 sites (just over
   half) in ten files instead of forty-eight. Clearing those first produces the fastest visible
   movement in the baseline's site count and front-loads the files where a single read of the
   surrounding code pays off the most times.
2. **Within that set, do `scripts/reset_e2e_real_state.py` early.** All 7 of its distinct citation
   strings name tests with no path at all (`test_reset_e2e_real_state_*`), suggesting a single test
   module was renamed or restructured wholesale; if so, one investigation likely resolves most or
   all of its 10 grandfathered sites at once rather than requiring 7 independent judgment calls.
3. **Treat `src/cyo_adventure/db/models.py` (12 sites, 9 pairs) and
   `src/cyo_adventure/api/generation.py` (12 sites, 8 pairs) as the two highest-value single files
   after that**, since they are the largest concentrations in `src/`.
4. **After the top ten, work the remaining 38 files in any order**, but prefer files with more
   than one row (there are more of them beyond the top ten) over the many files with exactly one
   row, for the same amortization reason.
5. **Do not save `scripts/mutate_skeleton.py`'s single row for last by accident.** It cites only a
   bare filename (`test_mutate_skeleton_cli.py`) with no function, which usually means the module
   itself is the missing artifact rather than one function in it; worth a quick look early since it
   may be fast to resolve one way or the other.

This order is a suggestion tuned for throughput, not a required sequence. Any row can be picked up
independently; the baseline key is per-citation, not per-file, so partial progress on a file is
fine to commit.

## Worked example (not fixed, walked through only)

Take the row that would exist for `src/cyo_adventure/api/deps.py` at line 613 (this exact file is
not currently in the baseline, since its citation happens to still resolve after a repoint that
already landed elsewhere in this branch's history, but the shape of the problem it shows up is
exactly what most of the 121 real (file, citation) pairs look like):

```python
# #CRITICAL: security: a child principal is scoped to EXACTLY its one
# profile; profile_ids is the singleton from the signed claim, never a
# family-wide set, so authorize_profile confines every downstream read to
# that single profile (a child cannot reach a sibling's library/reading).
# #VERIFY: test_child_session.py::test_require_principal_child_branch_scopes
# asserts profile_ids is the singleton; the integration suite asserts a
# child token is 403/404 on another profile's resource.
```

The citation names `test_require_principal_child_branch_scopes` inside
`tests/unit/test_child_session.py`. Grepping that file for test function names shows no function
by that exact name; the closest match is:

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_require_principal_child_branch_scopes_to_single_profile() -> None:
    """A child token resolves to a CHILD principal scoped to one profile."""
    principal = await deps.require_principal(
        _ExplodingSession(),  # pyright: ignore[reportArgumentType]
        authorization=f"Bearer {_mint()}",
    )
    assert principal.role is deps.Role.CHILD
    assert principal.profile_ids == frozenset({_PROFILE_ID})
    ...
```

at `tests/unit/test_child_session.py:325`. This is the "repoint" outcome, not "write a new test":
the function was renamed (a `_to_single_profile` suffix was added, probably for clarity) and the
citation was never updated to follow it. Fixing this row means:

1. Confirming the renamed test really does discriminate the claim: does it fail if the "singleton,
   never family-wide" invariant is violated? Reading the body, yes: it asserts
   `principal.profile_ids == frozenset({_PROFILE_ID})` against a session double
   (`_ExplodingSession`) that raises if the database is ever touched, which also backs the
   docstring's "no lookup" claim two paragraphs above. This is exactly the kind of check a human
   has to make; the checker will never do it.
2. Updating the `#VERIFY` line's citation text from
   `test_child_session.py::test_require_principal_child_branch_scopes` to
   `test_child_session.py::test_require_principal_child_branch_scopes_to_single_profile`.
3. Deleting the corresponding row from `rad-citation-baseline.toml` in the same commit (if this
   file were currently baselined, which as noted it is not).

Nothing above was changed as part of writing this handoff; this is a walkthrough of the mechanics
against a real citation site, offered as a template for the other 121 pairs.

## Notes, not failures: the 11 bare-name ambiguity notes

The `--all` run above printed 11 lines like this one, none of which count against this backlog's
121 pairs (136 sites):

```text
src/cyo_adventure/publishing/service.py:285: note: test_approve_stamps_resulting_storybook_id:
resolves against 2 same-named test functions (tests/integration/test_publishing_service.py,
tests/unit/test_publishing_service_unit.py); a bare citation cannot say which one actually
covers this assumption
```

These are not stale citations. Each one resolves successfully; the checker found a real test by
that name and is satisfied the citation is not broken. The note exists because the citation used a
bare name (just `test_cross_family_guardian_is_rejected`, no file path) and more than one test
function in the repo happens to share that name. The checker resolves bare names repo-wide by
design (a deliberately lenient choice that keeps false positives at zero), so it cannot tell which
of the look-alikes the author meant, and says so rather than silently picking one. Because the
citation still resolves, this never fails the gate and never blocks a commit.

These 11 are not part of this backlog and do not need a baseline row. But disambiguating them is
cheap while you are already in the area: change the bare name to a file-qualified one
(`tests/integration/test_authz_matrix.py::test_cross_family_guardian_is_rejected`) so a future
reader, and the checker, both know exactly which of the same-named tests is meant. If you touch
one of these files while working this backlog, it costs one extra line edit to fix the note
too; there is no requirement to go out of your way for the other 10.
