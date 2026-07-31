---
title: "Story personalization: staged execution plan (P3 to P11)"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Executable, staged task plan for the remaining ADR-023 work (P3 leak guards through
  P11 compliance artifacts), sequenced behind the section-3.4 sentinel-survival GO/NO-GO gate
  and the counsel gate on OD-1/OD-5. P1+P2 are already merged (PR #418); this plan verifies
  that state against origin/main and covers only what remains."
tags:
  - planning
  - implementation
  - privacy
  - generation
  - frontend
component: Strategy
source: "ADR-023; story-personalization-implementation-plan.md (the design plan this executes);
  owner decisions 2026-07-28 (section-3.4 staged gate; R20 accepted for v1); code-state
  verification against origin/main 9901832 on 2026-07-28"
---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

## Goal

Ship the remaining ADR-023 story-personalization work (design-plan phases P3 through P11):
leak-surface guards, the data model and consent records, the API surface, the client-side
resolver, ring-2 cross-family delivery, the dedication overlay, guardian and kid UI, catalog
migration, and the compliance artifacts, all behind the survival-measurement and counsel gates.

## Architecture (one paragraph)

The server always stores and serves one generic, sentinel-bearing blob (`{~HERO:Explorer~}`),
byte-identical for every viewer. A small per-profile values payload is fetched separately and
resolved client-side at render time. Real child data never reaches a provider, never lands in
`storybook_version.blob`, and never rides a server-side response except the values endpoint,
whose authorization is the highest-consequence new surface (risk R19). Read
[ADR-023](./adr/adr-023-story-personalization-slots.md) and the
[design plan](./story-personalization-implementation-plan.md) before executing any stage; this
document deliberately does not restate their reasoning, only their build steps.

## Current state (verified 2026-07-28 against origin/main 9901832)

**Done and merged (PR #418, squash `d99e26d`), do not rebuild:**

| Artifact | Where |
|---|---|
| Sentinel helpers: `SENTINEL_RE`, `wrap`, `strip_sentinels`, `find_sentinels`, `find_malformed_sentinels` | `src/cyo_adventure/storybook/sentinels.py:59-198` |
| `SlotSpec.kind: Literal["theme", "personalizable"]`, `PERSONALIZATION_FIELDS`, `REAL_PERSON_PERSONALIZATION_FIELDS`, contract validators | `src/cyo_adventure/storybook/theme_contract.py:67-88, :125-211, :296-330` |
| Integrity checks Variant A (`check_sentinel_integrity`) and Variant B (`..._at_rest`) | `src/cyo_adventure/validator/sentinel_integrity.py:549, :699` |
| Fail-closed wiring: worker fill path, moderation entry, repair adoption, rescreen strip-before-classify, node-edit at-rest re-check, import path | `generation/worker.py:1004`, `moderation/pipeline.py`, `moderation/rescreen.py`, `api/node_edit.py:465-495`, `generation/import_story.py` |
| Tri-state personalizable-slot resolver | `src/cyo_adventure/moderation/personalizable_slots.py` |
| Measurement instrument (offline, standalone, no DB) | `src/cyo_adventure/measurement/`, `scripts/measure_sentinel_survival.py` |

**Update 2026-07-29:** Stage A is done and merged (PR #449): the P3 title/prompt strips, the
leak-guard tests, and the G1 measurement (verdict STOP) are on main. Branch
`feat/personalization-reinsertion-prototype` (PR #466) carries the re-insertion prototype
(`measurement/reinsertion.py`, `--save-fills`, analyzer script) **and, since the Stage R
re-plan, Stages R and B**: the worker's strip-all-then-reinsert step, both persistence tables
(`child_profile_personalization`, `personalization_disclosure_consent`, RLS enabled with
service-role-only policies), and the personalization API routes. Still not started: all
frontend work, all UI, the Route A copy wiring, the catalog migration, and the compliance
artifacts. No `.contract.json` on disk
declares a personalizable slot, so every merged check is currently a structural no-op: the
first contract that declares one is the feature's power switch and is deliberately sequenced
late (Task D4).

**PR #416 has merged**, so the authoring-lessons directive is live: any task below that touches
validator or authoring behaviour appends its lessons to
[authoring-lessons-log.md](./authoring-lessons-log.md) and validates with
`uv run python scripts/check_lessons_log.py`.

## Gates and owner decisions

| Gate | What it blocks | Condition to pass |
|---|---|---|
| **G1: survival GO/NO-GO** | Stage B onward (everything after leak guards) | Task A1's measured clean-pass rate at or above ~95% is GO; 80-95% means iterate the prompt/delimiter and re-measure before proceeding, with the retry cost line made explicit; below ~80% is STOP: prototype deterministic post-fill re-insertion instead and re-plan Stage B+. **FIRED 2026-07-28: measured 3.3% (1/30) on the primary provider; verdict STOP. Stage B+ as written is void pending a re-plan around deterministic post-fill re-insertion (design plan 3.4, MEASURED block). RESOLVED by the Stage R re-plan of 2026-07-29: gate G1-R (Stage R exit) now blocks Stage B onward** |
| **G1-R: re-insertion round-trip** | Stage B onward (replaces the fired G1) | Task R4: round-trip integrity 100% through the production fill path; per-slot coverage profile recorded; owner acknowledges the coverage posture (third-party slots high-90s, HERO partial-by-voice, dedication guaranteed). **SATISFIED 2026-07-29: verify_manifest 30/30 (100%) on fresh fills (Task R4 CONFIRMED block); owner acknowledged the coverage posture and approved Stage B the same day. Stage B is unblocked. The vocative nudge experiment ran and was REJECTED the same day (HERO coverage fell to 4.9%, AL-062); it adjusted the coverage profile only, never this gate, and the template edit was reverted before commit.** |
| **G2: counsel on OD-1/OD-5** | **Shipping** P7 (ring-2) and P9 (consent UI); building them is not blocked | Counsel confirms the ring-2 separate disclosure consent design and the sibling/pet-name raise. **SATISFIED 2026-07-29 by owner review (no external counsel exists at this scale): OD-1 closed as separate consent, chosen for conservatism; OD-5 closed conditionally for R1 (immediate family) with mandatory reassessment at every deployment-phase boundary and a hard revisit before iOS/commercial use. ADR-023 flipped Proposed to Accepted the same day; the regulatory classification (COPPA-deferred, GDPR-K contingent) is recorded in its OD-5 closure block. Shipping P7/P9 is unblocked at R1 scope only.** |
| **G3: Route A copy precedes the flag** | Enabling `VITE_FEATURE_PERSONALIZATION` anywhere a real family can reach | Task D1 (toggle-aware Route A copy) merged. **Task D1 AUTHORIZED by owner 2026-07-29; the gate passes when it merges.** |

Owner decisions recorded 2026-07-28 (this plan is their record; Task A6 propagates them into
the design plan):

- **Section 3.4 measurement runs as Stage A work, and Stage B+ stays gated on its result** (the
  design plan's own P4-waits-on-P2 rule, confirmed).
- **R20 (shared-device IndexedDB isolation of values payloads): accepted for v1.** A shared
  family device is a shared trust boundary; no per-profile encryption, no in-memory-only mode.
  The acceptance must be recorded in the DPIA/privacy-model entry (Tasks A6, B7), not silently
  inherited.

Owner decisions recorded 2026-07-29 (post-Stage-C review of draft PR #489):

- **OD-1: separate disclosure consent confirmed**, chosen for conservatism (minimal work,
  reduced risk). **OD-5: self-verification accepted for R1 only**, reassessed at every
  deployment-phase boundary, hard revisit before iOS/commercial; regulatory classification
  (COPPA-deferred, GDPR-K contingent) recorded in ADR-023's OD-5 closure block. Together these
  satisfy G2 at R1 scope, and ADR-023 flipped Proposed to Accepted.
- **Task D1 authorized** (G3 passes when it merges).
- **`personalization_eligible` exposure scheduled** as Task D8 (was Stage C open question 2).
- **Vocabulary decisions** (proposal doc `personalization-closed-vocabularies-proposal.md`):
  `favorite` ships **split** (Option B: `favorite_color`/`favorite_food`/`favorite_hobby`, the
  schema migration accepted knowingly), NOT flat; `pet_species`, `kinship_label` (+`dedication`
  sharing its list), and `home_type` accepted as proposed; **no case normalization** anywhere
  (stored and matched exactly as listed); **no "none" sentinel** (story-flow impacts are hard
  to overcome; absence stays "slot unset"). Implementation is Task D6.
- **New feature: vocabulary-expansion requests.** A guardian can request a new entry for a
  closed vocabulary; an admin validates appropriateness and expands the list. Scheduled as
  Task D7; cite the capability register IDs it serves when it is speced.

## Standing constraints (apply to every task)

- **Never modify** `src/cyo_adventure/generation/pii.py`. No carve-outs, no new parameters.
- **Never modify** `src/cyo_adventure/story_requests/interpretation.py` except in Task D1,
  whose exact three-edit shape is specified there.
- Base every branch on **origin/main** (local `main` is known to run stale in this working
  tree; fetch first). Work in a worktree under `.worktrees/`; other sessions share the main
  tree and switch branches under you.
- Signed commits (`git commit -S`), Conventional Commits, no em-dash characters in any output.
- Any backend route or Pydantic model change regenerates the OpenAPI client **in the same
  commit** (`cd frontend && npm run generate-client` against a running backend, then
  `git add frontend/src/client`); the CI `contract` job fails otherwise.
- Line numbers in this plan were verified 2026-07-28 and drift; each stage's first step
  re-verifies the anchors it uses.
- Local commands that need app settings run with `ENVIRONMENT=local` (the VS Code terminal
  injects `.env`, and non-local guard families trip otherwise). Note `Settings` in
  `core/config.py` declares **no `env_file`**: it reads the process environment only, so in a
  bare shell or a worktree you must source the env yourself
  (`set -a; . ./.env; set +a`) and symlink `certs/` (relative `OLLAMA_CA_BUNDLE` paths resolve
  against the cwd). Worktrees share git, not untracked files.

---

## Stage A: measurement plus leak guards (no gates; executable now)

Branch: `feat/personalization-p3-leak-guards` off origin/main.

### Task A0: worktree and baseline

- [ ] **Step 1: create the worktree**

Run:

```bash
cd /home/byron/dev/CYO_Adventure
git fetch origin
git worktree add .worktrees/personalization-p3 -b feat/personalization-p3-leak-guards origin/main
cd .worktrees/personalization-p3
uv sync --all-extras
```

Expected: worktree created, deps synced.
Abort if: `git status` in the worktree is not clean.

- [ ] **Step 2: baseline the gate**

Run: `ENVIRONMENT=local uv run pytest tests/unit -q -x -k "sentinel or covers or recommendations"`
Expected: PASS on the selected tests (no `--timeout` flag: pytest-timeout is not installed
here). The global 80% coverage gate FAILS on any filtered run; that failure is expected noise,
judge only the test outcomes.

- [ ] **Step 3: copy this plan into the worktree and commit it**

```bash
cp ../../docs/planning/story-personalization-execution-plan.md docs/planning/
git add docs/planning/story-personalization-execution-plan.md
git commit -S -m "docs(planning): staged execution plan for ADR-023 P3-P11"
```

### Task A1: run the section-3.4 sentinel-survival measurement (GO/NO-GO input)

The instrument is standalone: no DB, no backend, reads `skeletons/` from disk, writes
`report.json` and `report.md` under `results/sentinel-survival/<run-slug>/`. Provider
credentials come from `core.config.settings`, which reads the **process environment only**
(`Settings` has no `env_file`); `.env` reaches it via VS Code terminal injection or
docker-compose, never directly. In a worktree, source it explicitly:
`bash -c 'set -a; . ./.env; set +a; export ENVIRONMENT=local; exec uv run python scripts/measure_sentinel_survival.py ...'`
and symlink `certs/` into the worktree (`ln -s ../../certs certs`) because `OLLAMA_CA_BUNDLE`
is a cwd-relative path. A missing key surfaces as `ConfigurationError`.

- [ ] **Step 1: mock smoke run (free, proves the harness)**

Run: `ENVIRONMENT=local uv run python scripts/measure_sentinel_survival.py --providers mock --count 5`
Expected: a run directory with `report.json` and `report.md`. The mock provider echoes a
fixed canned story unrelated to any specimen, so its clean-pass rate is 0% by construction;
this step proves only the plumbing (specimen build, provider dispatch, report writing), not
survival. Judge the run by "report produced", never by the mock rate.
Abort if: the script errors before producing a report (fix the harness before spending money).

- [ ] **Step 2: real measurement on the primary route**

Confirm `OPENROUTER_API_KEY` (as named by `core/config.py`) is set in the process env first.
(As executed 2026-07-28: the Anthropic direct leg was dropped by owner decision, all
generation routes through OpenRouter, so this step measures the single primary
`anthropic/claude-haiku-4.5` route; the fallback `anthropic/claude-sonnet-4.6` leg is optional
re-plan input, run separately if needed.) Then:

Run: `ENVIRONMENT=local uv run python scripts/measure_sentinel_survival.py --providers openrouter --count 30 --slots-per-story 4`
Expected: per-provider clean-pass rate plus the failure taxonomy (dropped, duplicated,
relocated, mutated wrapper, mutated inner text) in `report.md`.
Abort if: `ConfigurationError` (missing key), or provider spend is not authorized. Cost is
roughly 30 frontier fill calls for this primary-route run; the optional fallback-model leg
would add another 30. Approve the spend before this step, not after.

- [ ] **Step 3: record the numbers where the next reader looks**

  - Append the measured rates and taxonomy counts to
    `docs/planning/story-personalization-implementation-plan.md` section 3.4, under a dated
    "Measured 2026-MM-DD" note.
  - Append a lessons row to `docs/planning/authoring-lessons-log.md` (this is validator/
    authoring work under the PR #416 directive); validate with
    `uv run python scripts/check_lessons_log.py`.

- [ ] **Step 4: apply the gate table**

| Clean-pass rate (worst provider) | Verdict |
|---|---|
| >= ~95% | **GO**: proceed to Stage B after Stage A merges |
| ~80-95% | Iterate `fill_bound.md` wording or the delimiter, re-run Step 2, and surface the retry cost line to the owner before declaring GO |
| < ~80% | **STOP**: do not start Stage B. Prototype deterministic post-fill re-insertion (match the generic-default string in filled prose) and re-plan |

- [ ] **Step 5: commit the doc updates**

```bash
git add docs/planning/story-personalization-implementation-plan.md docs/planning/authoring-lessons-log.md results/ 2>/dev/null || true
git commit -S -m "docs(planning): record sentinel-survival measurement (ADR-023 section 3.4)"
```

(If `results/` is gitignored, commit only the doc updates; the reports stay local.)

### Task A2: strip sentinels from the cover-art prompt

**Files:**
- Modify: `src/cyo_adventure/covers/prompt.py` (title read at `:58-61`, `subject` at `:77`,
  `_opening_excerpt` truncation at `:40`)
- Test: the existing covers-prompt test module (locate: `grep -rl build_cover_prompt tests/`);
  create `tests/unit/covers/test_prompt_sentinels.py` only if none exists.

The ordering trap: `_opening_excerpt` truncates to 240 chars **before** any strip could run, so
stripping afterwards can leave half a token (`{~HERO:Expl`) that no longer matches
`SENTINEL_RE` and survives as garbage. Strip **inside** `_opening_excerpt`, before the slice.

- [ ] **Step 1: write the failing tests**

```python
from cyo_adventure.covers.prompt import _opening_excerpt, build_cover_prompt
from cyo_adventure.storybook.sentinels import wrap


def test_cover_prompt_contains_no_sentinel_markers() -> None:
    token = wrap("HERO", "Explorer")
    blob = {"title": f"The {token} Chronicles", "nodes": []}
    prompt = build_cover_prompt(blob, protagonist_name=token)
    assert "{~" not in prompt
    assert "~}" not in prompt
    assert "Explorer" in prompt  # stripped to the generic default, not deleted


def test_opening_excerpt_strips_before_truncation() -> None:
    token = wrap("HERO", "Explorer")
    # Position the token so a strip-after-truncate would bisect it at 240 chars.
    body = ("x" * 235) + f" {token} tail"
    blob = {"nodes": [{"body": body}]}
    excerpt = _opening_excerpt(blob)
    assert "{~" not in excerpt
```

(Adjust the `nodes` fixture shape to whatever `_opening_excerpt` actually reads; confirm by
reading `covers/prompt.py:19-40` first. The assertion is the contract; the fixture must satisfy
the strictest consumer, which here is `_opening_excerpt` itself.)

- [ ] **Step 2: run to verify both fail**

Run: `ENVIRONMENT=local uv run pytest tests/unit -q -k "cover_prompt_contains_no_sentinel or opening_excerpt_strips"`
Expected: FAIL (tokens present in output).

- [ ] **Step 3: implement**

In `covers/prompt.py`, import once and apply at the three read points:

```python
from cyo_adventure.storybook.sentinels import strip_sentinels
```

- title: `title = strip_sentinels(title_val) if isinstance(title_val, str) and title_val else "a children's story"`
- subject: `subject = strip_sentinels(protagonist_name) if protagonist_name else "the main character"`
- `_opening_excerpt`: strip the assembled body string **before** the `[:limit]` slice.

- [ ] **Step 4: run tests, then the module's full suite**

Run: `ENVIRONMENT=local uv run pytest tests/unit/test_cover_prompt.py -q`
Expected: PASS, no regressions. (Select by file path: `-k covers` matches nothing because the
test file is `test_cover_prompt.py`. The coverage-gate failure on a filtered run is expected.)

- [ ] **Step 5: commit**

```bash
git add src/cyo_adventure/covers/prompt.py tests/
git commit -S -m "feat(covers): strip personalization sentinels from cover-art prompts (ADR-023 P3)"
```

### Task A3: strip sentinels from recommendation, reading-history, and notification titles

`depends-on: TaskA2 [completion]` (same helper, independent files; parallelizable).

**Files:**
- Modify: `src/cyo_adventure/api/recommendations.py:79-94` (`_book_title`)
- Modify: `src/cyo_adventure/api/reading_history.py:89-100` (`_book_title`; the duplication is
  deliberate per its docstring, so patch both rather than extracting)
- Modify: `src/cyo_adventure/api/notifications.py:121-133` (title and body serialization)
- Test: the existing unit test modules for each router (locate with
  `grep -rl "_book_title\|notifications" tests/unit/`).

- [ ] **Step 1: failing tests** (one per surface; same shape as A2's title test: feed a
  `wrap("HERO", "Explorer")`-bearing title/body through the helper or serializer and assert no
  `{~` in the output and `Explorer` present).

```python
def test_book_title_strips_sentinels() -> None:
    token = wrap("HERO", "Explorer")
    assert _book_title({"title": f"{token} and the Map"}, "sb-1") == "Explorer and the Map"
```

- [ ] **Step 2: run, expect FAIL.**
- [ ] **Step 3: implement**: in both `_book_title` helpers change the return to
  `return strip_sentinels(title) if isinstance(title, str) and title else storybook_id`; in
  `notifications.py` wrap the title/body strings with `strip_sentinels(...)` at the
  serialization point.
- [ ] **Step 4: run the three routers' unit suites, expect PASS.**
- [ ] **Step 5: commit** (`feat(api): strip sentinels from title-bearing feeds (ADR-023 P3)`).

### Task A4: library titles strip; version blob explicitly does NOT

`depends-on: TaskA2 [completion]`.

**Files:**
- Modify: `src/cyo_adventure/api/library.py` (`_library_item` title at `:240`)
- Test: library unit/integration tests.

- [ ] **Step 1: failing tests**

```python
def test_library_item_title_is_stripped(): ...   # same shape as A3

async def test_version_endpoint_returns_blob_verbatim(client, seeded_sentinel_book):
    # GET /api/v1/storybooks/{id}/versions/{v} is the artifact the client
    # resolves against; sentinels MUST survive it untouched.
    body = (await client.get(f"/api/v1/storybooks/{sid}/versions/{ver}")).json()
    assert "{~" in json.dumps(body)
```

- [ ] **Step 2: run, expect the first to FAIL** (the second may already pass; keep it as the
  regression pin either way).
- [ ] **Step 3: implement**: `title = strip_sentinels(title)` after the `_str_field` read at
  `library.py:240`. Touch nothing in `get_storybook_version` (`:401-420`).
- [ ] **Step 4: run library suites, expect PASS.**
- [ ] **Step 5: commit** (`feat(api): strip sentinels from library titles, keep version blob raw (ADR-023 P3)`).

### Task A5: structural regression pins (R2, R3)

`depends-on: TaskA4 [completion]`.

**Files:**
- Create: `tests/unit/test_title_strip_registry.py`
- Create/extend: an integration test asserting the version response is identical across
  profiles.

- [ ] **Step 1: the R2 registry test.** Every response field in `api/schemas.py` that a story
  blob is projected into must carry an explicit strip decision, so the 29th router cannot
  forget.

  **As delivered, this keys on `(model, field)`, not on the model alone.** The original
  sketch here scanned for models with a field named `title`; that shape has a blind spot
  wide enough to miss a guard point this workstream had to add, since
  `NotificationView.body` is composed from a story title and needs stripping but carries no
  `title` field. The same blind spot hid `GuardianBookItem.themes` and `FlaggedPassage.prose`.

```python
# tests/unit/test_title_strip_registry.py (shape only; see the file for the full table)

# The reviewable knob: response field names a storybook blob is projected into.
# Scanning every string-bearing field instead sweeps in 224 pairs of ids, enums and
# URLs, which would be classified by guesswork.
_BLOB_TEXT_FIELDS = frozenset({"title", "body", "themes", "prose"})

# Closed reason vocabulary; a bare "raw" is rejected, so a future developer cannot
# silence a failing scan with one unexamined word.
DECIDED: dict[tuple[str, str], str] = {
    ("LibraryItem", "title"): "strip",
    ("NotificationView", "body"): "strip",
    ("FlaggedPassage", "prose"): "raw:review-surface",
    ("NodeEditBody", "body"): "raw:legal-sentinel-surface",
    ("ConceptBrief", "title"): "raw:adult-authored",
    # ... one row per scanned pair; set equality makes it fail closed both ways
}

# Each "strip" row additionally names the builder that enforces it and the test that
# proves it, and a further test asserts both of those still exist.
```

- [ ] **Step 2: the R3 byte-identity test** (integration): fetch the same
  `storybook_id@version` as two different child profiles in one family; assert
  `resp_a.content == resp_b.content`. This pins the offline `id@version` cache-key contract.
- [ ] **Step 3: run both, expect PASS** (fill `DECIDED` from the scan output on first run).
- [ ] **Step 4: commit** (`test: pin title-strip registry and blob byte-identity (ADR-023 R2/R3)`).

### Task A6: propagate the 2026-07-28 owner decisions into the design docs

- [ ] **Step 1:** in `docs/planning/story-personalization-implementation-plan.md`: mark open
  question 3 (R20) resolved ("2026-07-28, owner choice: accepted for v1; record in DPIA"), and
  update risk R20's mitigation cell accordingly.
- [ ] **Step 2:** run `pre-commit run --files docs/planning/story-personalization-implementation-plan.md`.
- [ ] **Step 3: commit** (`docs(planning): record R20 acceptance and measurement scheduling (ADR-023)`).

**Stage A exit:** full gate green (`uv run ruff check .`, `uv run basedpyright src/`,
`ENVIRONMENT=local uv run pytest`), PR opened against main, G1 verdict recorded. Stage B does
not start on a NO-GO. **Exit reached 2026-07-28: PR #449 merged; G1 verdict STOP; Stage R
below is the resulting re-plan and now owns the path to Stage B.**

---

## Stage R: deterministic re-insertion pipeline (re-plan of 2026-07-29; replaces prompt-preserved survival as the token supply)

**Why this stage exists.** G1 fired STOP twice (3.3%, then 0/30 prompt-preserved survival),
and the re-insertion prototype run (`20260729T010024Z`, fills persisted, aggregate committed
at
[evidence/sentinel-reinsertion/20260729T010024Z-reinsertion-dev.md](evidence/sentinel-reinsertion/20260729T010024Z-reinsertion-dev.md))
showed the strict per-node expectation was itself wrong: the corpus is
second-person, so the HERO name structurally cannot appear in most node bodies (42% node
coverage, absent entirely from 11/30 stories) while named third-party slots re-insert at
94-99%. The design that survives the data is **derive-not-prescribe**: after the fill, strip
every model-emitted token, deterministically re-insert wherever the generic inner word
occurs, record the multiset that re-insertion actually produced as the version's
`sentinel_manifest`, and verify blob-matches-manifest everywhere integrity is checked today.
Coverage becomes a soft quality floor; the dedication overlay (Task C5, promoted to
mandatory below) plus the stripped title rules guarantee at least one personalized surface
per story regardless of prose. Prototype code (pure transform, round-trip-verified against
`check_sentinel_integrity`) is on branch `feat/personalization-reinsertion-prototype`
(`src/cyo_adventure/measurement/reinsertion.py`).

Branch: `feat/personalization-reinsertion-pipeline` off origin/main after the prototype
branch merges. First step: re-verify every anchor below against then-current main.

### Task R1: matcher hardening, measured offline (no provider spend)

**DONE 2026-07-29** (commit 8916c2d): sentence-start widening recovered 76 of 1,027 misses
(120 occurrences wrapped verbatim); the plural counter measured **0 bare plurals corpus-wide**,
so the "72 inflected" bucket was a heuristic artifact (possessives, already handled by the
word-boundary matcher) and plural matching is dropped from the lift menu (AL-060).

**Files:**
- Modify: `src/cyo_adventure/measurement/reinsertion.py` (`_word_boundary_pattern`,
  `_count_in_node_surfaces`, `_wrap_all_in_node`)
- Test: `tests/unit/test_measurement_reinsertion.py`

Two targeted widenings, each behind its own predicate so the strict matcher remains the
default path and each widening is separately attributable in the report:

1. **Sentence-start case**: a lowercase multi-word value (`the pup`, `the grown-up`) also
   matches its sentence-initial capitalization (`The pup`). Only the first character folds;
   `THE PUP` and mid-sentence `The pup` still miss. 82 of 1,026 measured misses.
2. **Possessive**: `Explorer's` already matches via `\b`; add coverage proving it, and
   decide plural policy from data rather than assumption: report (do not yet match)
   occurrences of `<value>s` so the next run quantifies whether plurals are the character
   or a common noun. 72 "inflected" misses were measured with a crude prefix heuristic and
   need this decomposition before any matcher change.

- [ ] **Step 1:** failing tests for both widenings (sentence-start hit; mid-sentence `The
  pup` still a miss; `Explorer's` hit; `Explorers` counted in the new plural-report field
  but NOT wrapped).
- [ ] **Step 2:** implement; run `ENVIRONMENT=local uv run pytest
  tests/unit/test_measurement_reinsertion.py -q`. Expected: PASS (coverage-gate failure on
  a filtered run is expected noise).
- [ ] **Step 3:** re-run the analyzer offline on the saved fills, zero provider spend:
  `ENVIRONMENT=local uv run python scripts/prototype_sentinel_reinsertion.py
  results/sentinel-survival/20260729T010024Z`. Record the new per-slot rates next to the
  2026-07-29 numbers in the design plan's section-3.4 block (expected direction: lowercase
  descriptive slots approach the third-party 94-99% band; HERO moves little, its misses are
  structural).
- [ ] **Step 4: commit** (`feat(measurement): sentence-start and possessive-aware
  re-insertion matching (ADR-023 Stage R)`).

### Task R2: promote the transform into the domain package

`depends-on: TaskR1 [output]`.

**DONE 2026-07-29** (commit 3fbf080): `storybook/reinsertion.py` public API is
`reinsert_storybook(bound_skeleton, filled_document) -> ReinsertionOutcome`
(document, manifest, token_outcomes) plus `build_manifest` and `verify_manifest` (delegates
to `check_sentinel_integrity`). Manifest keying: node id for the body surface,
`<node_id>::ending_title` for the ending title, sorted keys, JSON-serializable. Analyzer
output on the saved fills was byte-identical before and after the move.

**Files:**
- Create: `src/cyo_adventure/storybook/reinsertion.py` (beside `sentinels.py`; the pure
  transform and its result types move here, measurement keeps only aggregation/reporting
  and imports the domain module)
- Modify: `src/cyo_adventure/measurement/reinsertion.py` (re-export or thin wrapper; no
  behaviour change, proven by the untouched test suite)
- Test: `tests/unit/test_storybook_reinsertion.py` (moved tests keep their names)

The transform's contract, stated once here because Stage R and Stage B both depend on it:
`reinsert(bound_skeleton, filled_document) -> (document, manifest, outcomes)` where
`manifest` is the per-node token multiset the transform actually inserted (the DERIVED
expectation), and `check_sentinel_integrity(document, manifest)` passes by construction
(round-trip property, already tested in the prototype).

- [ ] TDD steps as above; `uv run basedpyright src/cyo_adventure/storybook/` 0 errors.
  Commit (`refactor(storybook): promote sentinel re-insertion into the domain package`).

### Task R3: wire re-insertion into the fill path and re-point all six integrity sites

`depends-on: TaskR2 [output]`.

**DONE 2026-07-29** (commit a63c06e; full unit suite 5,225 passed, 0 failed). Site audit
outcomes vs the plan text:

- Worker fill path and the import/resume path (the two Variant A prescription sites) now run
  `reinsert_storybook`, carry the transform's document forward, and fail closed on
  `verify_manifest` (transform bug) plus `check_sentinel_integrity_at_rest` (forged/malformed
  leftovers). `GenerationOutcome.sentinel_manifest` carries the manifest in memory only; the
  DB column remains Task B2.
- Moderation entry, repair adoption, and node-edit needed NO change: the at-rest variant was
  already deliberately corruption-only (unknown slot, malformed, choice label, title) and
  never prescribed per-node placement, so it is derive-compatible as built.
- Rescreen's documented placeholder was wired to `check_sentinel_integrity_at_rest`, closing
  the "when the manifest lands" TODO.
- Deviation, accepted: the zero-coverage soft floor is a structlog WARNING in the worker, not
  a validator PL code, because the deterministic gate runs over the pre-reinsertion document
  (one stage earlier than the manifest exists). Gate-order note: validating pre-reinsertion is
  semantically equivalent because every gate consumer strips sentinels before scoring and
  re-insertion only wraps words in place; the plan's "fill -> reinsert -> validate" ordering
  is therefore not required and was not imposed.
- The mutated-sentinel worker test changed meaning by design: a forged token no longer fails
  the job; it is stripped and the document repaired
  (`test_run_skeleton_fill_sentinel_integrity_forged_value_not_reinserted`).

**Files:**
- Modify: `src/cyo_adventure/generation/worker.py` (fill path; Variant A call at `:1004`,
  re-verify anchor)
- Audit and re-point: the six fail-closed wiring sites listed in Current state (worker fill
  path, moderation entry, repair adoption, rescreen strip-before-classify, node-edit
  at-rest re-check, import path)
- Test: the existing wiring tests per site, plus new derived-manifest cases.

Order in the pipeline **as built**: fill -> deterministic validator gate -> **strip-all-then-reinsert**
-> moderation. This line originally read `fill -> reinsert -> validator gate -> moderation`; the
accepted deviation above (see "the zero-coverage soft floor is a structlog WARNING") moved the gate
ahead of re-insertion, and the two statements sat in contradiction until this correction. Placing the
gate first is semantically equivalent, not a weakening: every gate consumer strips sentinels before
scoring, and re-insertion only wraps already-scored words in place.
Semantics change at each site from "blob matches the skeleton-prescribed multiset" (fails
on ~100% of real fills) to "blob matches the version's derived `sentinel_manifest`":

- Worker fill path: run the transform immediately after a successful fill; persist the
  manifest with the version (Task B2's `sentinel_manifest` column, whose description is
  re-scoped below); Variant A verifies the round-trip property and fails closed only on
  transform bugs, not on model paraphrase.
- Repair adoption and node-edit: re-run the transform on the edited/repaired body and
  REPLACE that node's manifest entry (an edit can legitimately add or remove a generic-word
  occurrence); at-rest checks then compare against the updated manifest.
- Rescreen and moderation entry: unchanged strip-before-classify behaviour; they now read
  the manifest instead of recomputing expectations from the contract.
- Import path: imports run the transform like a fill does.

Soft floor (report, never gate): when a personalizable contract is active and the HERO
token appears in zero nodes of a version, emit a validator WARNING naming the dedication
as the guaranteed surface, mirroring how PL-level warnings report today. A zero-coverage
story remains publishable; the warning exists so a human sees the posture.

- [ ] **Step 1:** per-site failing tests first (fill produces a manifest; a mutated blob
  fails at-rest against the manifest; node edit updates the manifest; zero-HERO fill emits
  the warning and still passes).
- [ ] **Step 2:** implement; full gate (`uv run ruff check .`, `uv run basedpyright src/`,
  `ENVIRONMENT=local uv run pytest tests/unit -q`). Expected: PASS.
- [ ] **Step 3: commit** (`feat(generation): derive-not-prescribe sentinel re-insertion in
  the fill path (ADR-023 Stage R)`).

### Task R4: end-to-end re-measurement and the Stage R exit record (one provider run)

`depends-on: TaskR3 [output]`.

**PARTIAL 2026-07-29** (commit a12c1a3 added the two gate metrics as permanent report
fields). Preliminary G1-R evidence over the existing 30 real fills, via the same promoted
transform the worker calls: **verify_manifest_ok 30/30 (100%)**. Per-slot coverage is now a
permanent report table: the widening lifted COMPANION from 84% to 98.4%; named third-party
slots sit at 94.6-99.1%; HERO holds at 42.4% (structural, second-person voice); the
remaining soft spot is small-sample lowercase relational slots (KIN 58.3%, CHAPERONE 63.9%,
THRESHOLD 70.0%, COMPANION_KIND 75.0%, ENTRANCE 80.0%). **The confirmatory fresh-fills run
is BLOCKED: OpenRouter returned HTTP 402 on both models on 2026-07-29 (account out of
credits; zero spend occurred; the Ollama fallback leg 404s on an unpulled model). Rerun
after a top-up.** The optional vocative nudge was not exercised; it is an owner spend
decision and the feature does not depend on it.

**CONFIRMED 2026-07-29** (fresh run `20260729T042510Z`, 30 unseen fills through the
production route after the credit top-up): **verify_manifest_ok 30/30 (100%)**, the G1-R
gate requirement, met on data the matcher was never tuned against. The run directory
`results/sentinel-survival/20260729T042510Z/` is gitignored, so the aggregate report is
committed at
[evidence/sentinel-reinsertion/20260729T042510Z-g1r-confirmatory.md](evidence/sentinel-reinsertion/20260729T042510Z-g1r-confirmatory.md)
and a reader can check these numbers rather than take them on trust.
Second finding, load-bearing for how the record must be read: per-slot coverage varies
materially run to run (HERO 26.8% here vs 42.4% on the dev fills; FOUNDER 78.6% vs 94.6%;
CHAPERONE 30.6% vs 63.9%; LISTENER/OPERATOR stable near 100%). Coverage is a property of
each fill, not of the transform, which is why it is a soft floor and the integrity check is
the hard gate (AL-061). Exit-record coverage posture, stated as cross-run ranges: named
third-party slots roughly 79-100%, HERO roughly 27-42% (structural, second-person voice),
lowercase relational slots roughly 30-90% small-sample. **Stage R technical exit is met;
the remaining G1-R clause is the owner's acknowledgment of this coverage posture.**

- [ ] Run the survival instrument once more (30 stories, `--providers openrouter --count 30
  --slots-per-story 4 --save-fills`; env recipe in Task A1). The instrument stays offline
  and standalone, but after Task R2 it exercises the SAME promoted domain transform the
  worker calls, so its numbers are representative of the production path. The number that
  gates Stage B is no longer model survival; it is **round-trip integrity: required 100%**
  (any failure is a transform or wiring bug, deterministic and fixable), plus the recorded
  coverage profile per slot. The worker-side wiring itself is covered by Task R3's tests,
  not by this run.
- [ ] Record both in the design plan's section-3.4 block with date; append lessons rows;
  `uv run python scripts/check_lessons_log.py`.
- [x] Optional, cheap, separately committed: a one-line vocative nudge in `fill_bound.md`
  (address the hero by name in dialogue at least once); re-run the analyzer offline on the
  new fills and record the HERO coverage delta. Adopt only if the delta is material; the
  feature does not depend on it. **MEASURED AND REJECTED 2026-07-29: HERO coverage fell to
  4.9% (72/1458) versus the 26.8-42.4% baseline range because the nudge's rationale clause
  was executed as an instruction (design plan section 3.4 block; AL-062). Template edit
  reverted, never committed; the run is `20260729T054004Z`, aggregate report committed at
  [evidence/sentinel-reinsertion/20260729T054004Z-vocative-nudge-rejected.md](evidence/sentinel-reinsertion/20260729T054004Z-vocative-nudge-rejected.md)
  because `results/` is gitignored.**

**Stage R exit (gate G1-R, replaces the fired G1 for Stage B onward):** round-trip
integrity 100% on the production path; per-slot coverage profile recorded; owner
acknowledges the coverage posture (third-party slots high-90s, HERO prose coverage
partial-by-voice, dedication as the guaranteed surface). Then Stage B proceeds unchanged
except the three re-scoped points marked **[Stage R re-scope]** below.

**EXIT MET 2026-07-29.** All three clauses closed: integrity 100% (Task R4 CONFIRMED
block), coverage profile recorded as cross-run ranges (AL-061), and the owner acknowledged
the posture and approved Stage B on 2026-07-29. The owner also approved the optional
vocative nudge experiment, which was never a Stage B precondition; it ran the same day and
was rejected on its measured result (Task R4 checklist, AL-062).

---

## Stage B: data model and API (blocked on Stage R exit / gate G1-R)

Branch: `feat/personalization-p4-p5-data-api` off origin/main, after the Stage R PR merges.
First step of the stage: re-verify every file/line anchor below against the then-current main.

### Task B1: migration 1, the slot-value store and profile toggles

**Files:**
- Create: `supabase/migrations/<timestamp>_add_child_profile_personalization.sql`
- Modify: `src/cyo_adventure/db/models.py` (new ORM model + two booleans on `ChildProfile`
  next to `tts_enabled`/`reduce_motion` at `:446-450`)
- Test: schema-parity suite (migration-built vs ORM-built), plus a vocab drift guard.

Migration content (follow the repo's idempotent-header convention shown in
`20260727000000_add_book_unassigned_to_pipeline_event.sql`):

```sql
-- ADR-023 P4: per-(profile, slot) personalization values and ring flags.
-- #CRITICAL: security: ring ceilings are DB CHECKs, not API validation, so the
-- taxonomy's ring-1-only rows (pronoun_set, dedication) are structurally
-- incapable of carrying ring2_enabled = true.
-- #VERIFY: tests/unit/test_personalization_vocab_drift.py pins both lists
-- against storybook.theme_contract.PERSONALIZATION_FIELDS.

CREATE TABLE IF NOT EXISTS child_profile_personalization (
    child_profile_id UUID NOT NULL REFERENCES child_profile(id) ON DELETE CASCADE,
    slot_type VARCHAR(32) NOT NULL CHECK (slot_type IN (
        'protagonist_first_name', 'pronoun_set', 'sibling_name', 'pet_species',
        'pet_name', 'kinship_label', 'favorite', 'home_type', 'dedication')),
    value_text TEXT,
    value_enum VARCHAR(64),
    value_profile_id UUID REFERENCES child_profile(id) ON DELETE CASCADE,
    ring1_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ring2_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (child_profile_id, slot_type),
    CONSTRAINT ck_cpp_exactly_one_value CHECK (
        (value_text IS NOT NULL)::int + (value_enum IS NOT NULL)::int
        + (value_profile_id IS NOT NULL)::int = 1),
    CONSTRAINT ck_cpp_ring2_ceiling CHECK (
        NOT ring2_enabled OR slot_type IN (
        'protagonist_first_name', 'sibling_name', 'pet_species', 'pet_name',
        'kinship_label', 'favorite', 'home_type'))
);

ALTER TABLE child_profile
    ADD COLUMN IF NOT EXISTS real_name_ring1_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS real_name_ring2_enabled BOOLEAN NOT NULL DEFAULT FALSE;
```

- [ ] **Step 1:** write the vocab drift-guard test first (both CHECK lists equal
  `PERSONALIZATION_FIELDS` and the ring-2 subset respectively; mirror the pattern in
  `tests/unit/test_pipeline_event_check_vocab.py`). Run: FAIL (table absent).
- [ ] **Step 2:** write the migration and the ORM model (`__table_args__` mirrors every CHECK
  by name; copy the `#CRITICAL`/`#VERIFY` marker style from `Rating` at `db/models.py:812-820`).
- [ ] **Step 3:** run the schema-parity test and the drift guard: PASS.
- [x] **Step 4: commit** (`feat(db): child_profile_personalization store and ring toggles (ADR-023 P4)`).

**DONE 2026-07-29 (commit 920d7db, on the Stage R branch per the owner's proceed
instruction; the off-origin/main branch note above is superseded for B1-B3).** Two
deviations from the printed DDL, both forced by empirical failures: (1) table references
schema-qualified as `"public"."..."`, because the baseline migration empties `search_path`
session-wide and every post-baseline migration already qualifies for that reason; (2) the
four boolean columns carry `server_default=sa_text("false")` in the ORM, matching
`User.is_admin`, because Python-side-only defaults fail schema parity against the DDL's
`DEFAULT FALSE`. Drift guard 5/5, schema parity green, failing-first proof recorded.
**OPEN owner decision: `child_profile_personalization` has no RLS enabled, unlike most
tables; it holds child-identifying values, so its ADR-021/ADR-022 tiered-scoping policy
needs a deliberate decision rather than silent omission. No test fails today (the RLS
suite iterates only rowsecurity=true tables).**

### Task B2: migration 2, consent evidence, viewer switch, subject link, eligibility

`depends-on: TaskB1 [completion]`.

**Files:** second migration + `db/models.py`.

Contents, per design-plan 5.3/8.2/8.6 (all shapes are settled there; this is transcription):

- `personalization_disclosure_consent`: surrogate UUID PK; `child_profile_id` FK CASCADE;
  `family_connection_id` FK **SET NULL** (evidentiary tombstone, never CASCADE);
  `connected_family_label VARCHAR(200)`; `covered_slot_types JSONB`;
  `sibling_authority_attested BOOLEAN NOT NULL DEFAULT FALSE`; the four consent columns with
  the all-null-or-all-set pairing CHECK copied from `FamilyConnection`
  (`db/models.py:547-554`); `revoked_at TIMESTAMPTZ`; partial unique index on
  `(child_profile_id, family_connection_id) WHERE family_connection_id IS NOT NULL`.
- `family.personalization_receive_enabled BOOLEAN NOT NULL DEFAULT TRUE` (the 8.6 viewer-side
  switch; default on because connection consent already implies receive-willingness).
- `storybook.personalization_subject_profile_id UUID` FK to `child_profile` **SET NULL**.
- On the storybook-version row: `personalization_eligible BOOLEAN NOT NULL DEFAULT FALSE`,
  `pronoun_parameterized BOOLEAN NOT NULL DEFAULT FALSE`, `sentinel_manifest JSONB`
  **[Stage R re-scope]**: the per-node token multiset that deterministic re-insertion
  actually produced (Task R3), written at re-insertion time, NOT the contract-prescribed
  expectation; rescreen and at-rest checks read this column so they never re-derive
  expectations from the contract, and node-edit/repair adoption update it in place.
  Verify the exact version-table model name in `db/models.py` before writing the DDL.

- [x] Steps: same TDD rhythm as B1 (parity test + tombstone-behaviour unit test first, then
  migration + ORM, then PASS, then commit
  `feat(db): ring-2 consent evidence, viewer switch, subject link (ADR-023 P4)`).

**DONE 2026-07-29 (commit 45da866).** Design-plan sections 5.3/8.2/8.6 matched this text
exactly; the only drift was the StorybookVersion line anchor (moved to :761 after B1's
insertion). Tombstone behaviour proven by integration test (connection delete leaves the
consent row with a NULL connection FK; profile delete removes it); schema parity green;
no vocab-drift extension needed because `covered_slot_types` is an open JSONB array, not
a closed CHECK vocabulary. B1's schema-qualification and server_default lessons applied.

### Task B3: deletion drill and export

`depends-on: TaskB2 [output]`.

**Files:**
- Modify: `tests/integration/test_deletion_drill.py` (seed helpers at `:46`/`:82`; the two
  tests at `:115` and `:208`)
- Modify: `src/cyo_adventure/api/me.py::_assemble_family_export` (`:93-175`, hand-assembled,
  new tables are NOT picked up automatically) and `GET /api/v1/me/export` (`:235`).

- [ ] **Step 1:** extend both drill tests: seed a personalization row and a consent row, assert
  both vanish on profile/family delete. Add the new case: deleting a **connection** leaves the
  consent row as a tombstone (`family_connection_id IS NULL`, `revoked_at` set); deleting the
  profile then removes it.
- [ ] **Step 2:** export gains, per profile: every personalization row (sibling slot as id AND
  display name), the two `real_name_*` booleans, and every consent row **including tombstoned
  ones**. Test: export of a family with one of each contains all three groups.
- [x] **Step 3:** commit (`feat(api): export and deletion coverage for personalization data (ADR-023 P4)`).

**DONE 2026-07-29 (commit 87ac0e3).** Drill extensions passed first-run because both new
FKs were already CASCADE (coverage confirmation, not a gap); the connection-tombstone case
is proven in test_personalization_consent_tombstone.py and referenced, not duplicated.
Export gap proven failing-first (KeyError on real_name_ring1_enabled), then closed:
personalization rows (sibling slot as id plus display name), both real_name booleans, and
consent rows including tombstones. FamilyExportView is an untyped dict blob by design, so
no OpenAPI contract change and no client regeneration; only its docstring was updated
(api/schemas.py, docstring-only extra file).

### Task B4: pipeline event types

`depends-on: TaskB2 [completion]`.

**Files:** `src/cyo_adventure/events/models.py` (EventType members),
`events/writer.py::_PAYLOAD_ALLOWLIST` (`:17`), a CHECK-vocab migration (wholesale-replace
pattern; read `20260727000000_...sql`'s header for why), and
`tests/unit/test_pipeline_event_check_vocab.py`.

New entries, keys only, never values (house contract at `writer.py:14-16`):

```python
EventType.PERSONALIZATION_TOGGLED: frozenset({"slot_type", "ring", "action"}),
EventType.RING2_CONSENT_GRANTED: frozenset({"connected_family_id", "slot_type_count"}),
EventType.RING2_CONSENT_REVOKED: frozenset({"connected_family_id"}),
```

- [x] TDD steps as above, plus one test asserting a value-bearing key (e.g. `pet_name`) is
  rejected by the allowlist. Commit
  (`feat(events): personalization consent/toggle event types (ADR-023 P3/P4)`).

**DONE 2026-07-29 (commit 0ede8917).** One deviation beyond the four named files:
`db/models.py::_PIPELINE_EVENT_TYPE_VALUES` (the hand-maintained CHECK mirror embedded in
the ORM CheckConstraint) gained the three values in the same commit, matching every prior
EventType addition and keeping test_schema_parity.py green. New superset test parses the
migration file directly, stripping `--` comment lines first because prose apostrophes in
house-style headers corrupt a naive quoted-string regex.

### Task B5: write-time validation service

`depends-on: TaskB1 [output]`.

**Files:**
- Create: `src/cyo_adventure/storybook/personalization_values.py` (validation lives with the
  domain, importable by both the write route and the payload builder)
- Test: `tests/unit/test_personalization_values.py`.

Every value passes, at write time AND again at payload-build time (names set before this
feature existed were never checked, risk R4):

1. `validator.slots.structural_value_violations` (`slots.py:496-514`),
2. `validator.slots.denylisted_bundles` against `band_mandatory_bundles(profile.age_band)`,
3. enum slots: membership in the shipped closed vocabulary (one module-level dict,
   `CLOSED_VOCABULARIES: dict[str, frozenset[str]]`, keyed by slot_type; seed pet_species,
   kinship_label, home_type, favorite lists from ADR-023 rows 4a/5/6/7),
4. sibling slot: `value_profile_id` in the same family (reuse `authorize_family`,
   `api/deps.py:743-754`),
5. `display_name` gets checks 1 and 2 on profile write too (`api/profiles.py:102-103`, `:286`).

- [x] TDD steps; include one test per rejection class and one asserting the render-time
  fallback contract (invalid value at build time means the slot is omitted from the payload,
  never an error). Commit (`feat(storybook): personalization value validation (ADR-023 5.2)`).

**DONE 2026-07-29 (commit 92fd602d), with one OPEN product decision.** ADR-023 rows 4a/5/6/7
name categories and examples, not exhaustive lists, so `CLOSED_VOCABULARIES` ships all four
keys as empty frozensets (fail-closed: every enum-slot value is rejected until real lists
are supplied). RAD-tagged in the module; B6 can proceed because omission, not error, is the
contract. Sibling authorization is a pure function taking the caller-supplied family roster
(no api/ or DB imports); the route layer resolves the roster via authorize_family. Item 5
(display_name checks on profile write) is NOT in this module and remains for B6's route work
to confirm or add at `api/profiles.py:102-103`.

### Task B6: routes (ring 1) and the authz matrix

`depends-on: TaskB5 [output]`.

**Files:**
- Create: `src/cyo_adventure/api/personalization.py`, wired in `app.py`
- Modify: `api/schemas.py` (request/response models exactly per design-plan 6.1, replace-not-
  patch PUT body; the two `real_name_*` booleans write through this route in one transaction)
- Modify: `tests/integration/test_authz_matrix.py::_ROUTE_SPECS` (completeness gate at
  `:944-949` forces this anyway)
- Test: `tests/integration/test_personalization_api.py`.

Routes: `GET/PUT /api/v1/profiles/{profile_id}/personalization` (guardian);
`POST /api/v1/profiles/{profile_id}/ring2-consent` and
`DELETE .../ring2-consent/{connection_id}` (sharer-side guardian; `consent_ip` and
`consent_accepted_at` stamped server-side; `sibling_authority_attested` required true when
`covered_slot_types` includes `sibling_name`);
`GET /api/v1/storybooks/{storybook_id}/personalization-values` returning the **ring-1** payload
in this stage (subject in caller's family) and an empty payload otherwise; ring 2 lands in C4.
Response carries `sentinel_pattern` (the `SENTINEL_RE` pattern string) so the generated client
never re-derives it (risk R9).

- [x] TDD steps; RouteSpec rows follow the dataclass at `test_authz_matrix.py:377-398` (copy
  the `PATCH /admin/profiles/{id}` row shape at `:445-451`). Empty payload, never 403, on any
  gate miss. Commit, then **regenerate the OpenAPI client in the same commit** (standing
  constraint). (`feat(api): personalization settings, consent, and ring-1 values routes (ADR-023 P5)`).

**DONE 2026-07-29 (commit e9ebe2c5).** 380 integration tests green (personalization API,
authz matrix, schema parity, event vocab). Deviations recorded: (1) latent production bug
found and fixed, `pipeline_event.entity_type` is String(32) so the consent entity logs as
`personalization_consent` (35-char natural label would overflow); both new entity types
added to the CHECK mirror with parity migration `20260729030000` (idempotent,
schema-qualified). (2) Local client regeneration injected a `baseURL: localhost:8000` line
into `client.gen.ts` that CI's static-dump generation never produces; hand-reverted before
commit. (3) The frontend-eslint/frontend-prettier local hooks failed on ANY commit staging
the generated client (eslint ignore-warning under --max-warnings=0; client is raw generator
output by design so never prettier-clean); root-caused and fixed by excluding
`frontend/src/client/` from both hooks (commit ec60c89b). (4) B5's open item closed:
display_name on profile create/update now runs structural + bundle checks
(`api/profiles.py:189-190`). `_RING1_POLICY_VERSION` is a sentinel constant, not a policy
registry, per plan scope.

### Task B7: privacy-model classification entries

`depends-on: TaskB2 [completion]`. Docs only: the four entries from design-plan 5.6 into
`docs/planning/privacy-model.md` ("Data Classification" and "If Shared Beyond Family"),
including the R20 acceptance sentence for the client-held values payload. Commit
(`docs(privacy): classify personalization data categories (ADR-023 5.6)`).

**DONE 2026-07-29 (commit b6769486).** All four classification entries landed (slot-value
rows at the child_profile tier, consent rows citing db/models.py, client-held payload with
the R20 acceptance sentence verbatim), plus a "Ring-2 disclosure (existing,
guardian-authorized)" subsection; privacy-model version 0.2 to 0.3.

**Stage B exit:** full gate green, contract job green, deletion drill green, PR merged.

---

## Stage C: client resolution and ring 2 (blocked on Stage B; shipping blocked on G2/G3)

Branch: `feat/personalization-p6-p7-client`.

### Stage C status (completed 2026-07-29)

C1 through C5 are done on `feat/personalization-p6-p7-client`, executed from the detailed
Stage C implementation plan (committed beside this document as
`story-personalization-stage-c-implementation-plan.md`). Commits, by task:

- **C0 (prerequisites, added by the implementation plan; see deviation 1):** `4f3ad847`
  (slot-id to field map in `generation/binding.py`), `556ebc5d` (story-scoped
  `moderation/personalizable_slots.py` resolver), `ca50cbc5` (`sentinel_pattern` and
  `slot_bindings` shipped on the values payload), `f03c7fdc` (`dedication` joins
  `CLOSED_VOCABULARIES`, fail-closed).
- **C1 (resolver):** `82d52f93` (`frontend/src/player/personalization.ts`), `3d8cb6e1`
  (cross-language fallback-pattern pin, risk R9), `e1440b71` (`isPersonalizationEnabled()`
  flag helper, default off).
- **C2 (offline store):** `377de008` (`personalization_values` store at `DB_VERSION` 4),
  `6e7bc145` (purge and reconcile triggers in `offline/revocation.ts`), `55c04e00`
  (sign-out purge in `AuthContext`).
- **C3 (render sites, behind the flag):** `31a27834` (values fetch adapter), `7d7ffdc7`
  (passage, ending title, and read-aloud resolution; includes the C3f flag-off strip pin),
  `cd794071` (ReaderPage threading), `8df1f9ce` (ReaderRoute flag-gated cache-first port),
  `20f69463` (admin review-surface marker-visibility pin).
- **C4 (ring 2):** `97c2fead` (the review's five coverage gaps closed in
  `tests/integration/test_personalization_api.py`; every test passed first try), `37deeb67`
  (client ring-agnosticism pin).
- **C5 (dedication overlay):** `0ca97333` (`DedicationOverlay` component), `b0043c15`
  (opening-screen-only render).
- **C6 (stage exit):** `3cce7859` (authoring lessons AL-066..AL-068 plus UW-C20).

The flag (`VITE_FEATURE_PERSONALIZATION`) remains **off**; gate G3 is still open (it passes
when Task D1 merges), G2 was closed by owner review on 2026-07-29 (see the gates table:
satisfied at R1 scope, ADR-023 flipped to Accepted), and Stage C never enables any shipping
surface.

**Deviations from this section as written, each with its reason:**

1. **C0 added** as a prerequisite task group. The values payload lacked `sentinel_pattern`
   (named in two plan documents, never implemented) and any slot-id to slot-type join
   (`slot_bindings`), and `dedication` was absent from `CLOSED_VOCABULARIES`. All three were
   unimplementable-client or fail-open defects that had to land before C1. Lessons AL-066,
   AL-067, AL-068.
2. **C4's server half was already merged** in PR #466. `authorize_via_connection` was not
   added (the connection resolves inline in `_resolve_ring2_view`, per the house convention
   this section itself cites) and `test_personalization_ring2.py` was not created (the tests
   live beside the ring-1 ones in `test_personalization_api.py`). C4 became test-list closure
   plus a client ring-agnosticism pin.
3. **The offline store is keyed by `storybook_id`, not `subject_profile_id`** as `:917`
   specifies: the subject id is unknowable offline (it appears in no offline artifact), and a
   subject-scoped purge scans the bounded per-book key set instead
   (`purgePersonalizationValues`).
4. **The fetch is not gated on `personalization_eligible`:** that boolean is in no API
   response, and exposing it would mean either mutating the immutable version blob or adding
   a response wrapper. The design plan frames the gate as an optimization, so one cheap extra
   GET per book open was accepted instead (open question 2 below).
5. **Choice labels are not resolved:** `generation/binding.py` renders choice labels with the
   bare value always, and a sentinel in a choice label is treated as corruption by the
   at-rest check, so there is nothing there to resolve.
6. **The marker strip is unconditional; only the fetch is flag-gated.** ADR-023 section 10
   forbids a marker on any kid-facing surface without exception, and the strip is a pure
   synchronous pass, so `resolvePersonalization(text, null)` runs even with the flag off.
   This is a deliberate flag-OFF behavior delta the post-Stage-C review re-surfaced: a
   sentinel-bearing blob that previously showed raw markers now shows each marker's generic
   word even with `VITE_FEATURE_PERSONALIZATION` off (deliberate strengthening; the Task C3f
   flag-off strip pin in `frontend/src/player/personalization.test.ts` asserts it).
7. **The dedication renders `For {NAME}` when no kinship value is available**, which is
   today's only possible path given the empty vocabulary (C0e fails closed). The Stage R
   "dedication guaranteed" clause is satisfied by the name half alone.
8. **An ending with an empty-string title now renders "The End" instead of nothing**
   (`Reader.tsx`, the ending heading's `endingTitle === '' ? 'The End' : endingTitle`
   fallback). A second deliberate flag-OFF behavior delta the post-Stage-C review surfaced
   as undocumented: the fallback also fires when the resolver strips an ending title that
   was nothing but a marker, so a child never sees a blank ending heading, flag on or off.

**Open questions carried out of Stage C** (recorded, not guessed at; none blocked the stage):

1. **Where should the slot-id to slot-type map be computed?** Stage C computes it per request
   from the book's theme contract on disk (two JSON reads inside the book-open call). The
   alternative is persisting it on `storybook_version` beside `sentinel_manifest` at
   re-insertion time: one migration plus one generation-path edit, no request-path disk read,
   and the map survives alongside the blob it describes. Reversible either way; owner input
   wanted, not required.
2. **Should `personalization_eligible` be exposed so the reader can skip a pointless fetch?**
   Design plan 8.3 assumes it is on the library and version responses; it is on neither, and
   the version route returns the raw immutable blob. The cheapest correct shape is a new
   `LibraryItemView` field threaded from `LibraryPage` into the reader's route state, which
   is Stage D-sized. Stage C skips the optimization (deviation 4). **ANSWERED 2026-07-29:
   scheduled as Task D8.**
3. **The dedication kinship vocabulary is still empty**, so the "love {KINSHIP}" half of the
   template is unreachable until the owner supplies the list, which belongs in a design-plan
   update or ADR-023 amendment, not hand-added to the Python dict (its own `#VERIFY` marker
   says so). **Owner input required** before the overlay can render its full template.
   **ANSWERED 2026-07-29: lists accepted (with `favorite` split) in
   `personalization-closed-vocabularies-proposal.md`; implementation is Task D6.**

### Task C1: the resolver

**Files:** create `frontend/src/player/personalization.ts` + `personalization.test.ts` (the
directory's existing test discipline applies).

```ts
export interface ValuesPayload {
  subject_profile_id: string
  ring: 1 | 2
  policy_version: string
  resolved_at: string
  sentinel_pattern: string           // carried from the API, never re-derived
  values: Record<string, string>
}

/** Pure, total, synchronous: null/missing payload or key -> the generic default. */
export function resolvePersonalization(text: string, payload: ValuesPayload | null): string
```

- [ ] TDD: table-driven tests covering resolve-hit, missing-key fallback to inner generic
  word, null payload, malformed-token passthrough-as-stripped, and idempotence on already-
  resolved text. Run `cd frontend && npm run test:coverage` (per-file 70% floor), not just
  `test:run`. Commit.

### Task C2: offline store and purges

`depends-on: TaskC1 [completion]`.

**Files:** `frontend/src/offline/db.ts` (`DB_VERSION` 3 to 4, new `personalization_values`
store keyed by `subject_profile_id`, following the cumulative `if (oldVersion < N)` upgrade
contract at `:92-116` and the `blocked/blocking` handling with its `#CRITICAL` ARCH-M5 note);
`frontend/src/offline/revocation.ts` (new `purgePersonalizationValues()`, **separate from**
`reconcileOfflineCache`, whose `#CRITICAL` fetch-precondition contract must not be overloaded);
sign-out purge beside `clearReadingStates` (`db.ts:198-201`).

Purge triggers: ring flag off, consent revoked, connection revoked, profile deactivation,
guardian sign-out/device handover, policy-version change. The offline-device residue window is
documented in code, mirroring `revocation.ts:16-25`.

- [ ] TDD (fake-indexeddb tests exist for this module; extend them), commit.

### Task C3: apply at render sites, behind the flag

`depends-on: TaskC2 [output]`.

**Files:** `frontend/src/reader/Reader.tsx` (PassageText at `:365`/`:419`, read-aloud inputs at
`:96`/`:151`), ending titles; a single `isPersonalizationEnabled()` helper reading
`VITE_FEATURE_PERSONALIZATION`. Admin surfaces (`ReviewDetailPage.tsx`, `ReviewCompare.tsx`)
are deliberately untouched: reviewers see markers (ADR-023 section 10).

- [ ] TDD: reader renders resolved text with a payload, generic without; flag off means no
  fetch and no resolver call; admin surfaces show raw markers. Commit.

### Task C4: ring-2 delivery

`depends-on: TaskC3 [completion]` for the client half; server half can start with Stage C.

**Files:** `api/deps.py` (new `authorize_via_connection`, never a loosened
`authorize_family`); `api/personalization.py` (the values route gains the ring-2 leg);
`tests/integration/test_personalization_ring2.py`.

The predicate is design-plan 8.4 verbatim, implemented as explicit per-row Python booleans (the
house convention at `recommendations.py:214-221`), in order: **(0)** viewer family's
`personalization_receive_enabled`; **(1)** caller in viewer family; **(2)** connection dual-
consented (`_is_dual_consented` shape); **(3)** subject in sharer family; **(4)** subject live:
`deactivated_at` AND `processing_restricted_at` both NULL; **(5)** per-slot ring-2 flag;
**(6)** consent row covers (profile, connection, slot); **(7)** taxonomy ceiling is ring 2
(belt-and-braces behind the DB CHECK); **(8)** sibling slot only: conditions 3-7 re-evaluated
against the **referenced** profile for `protagonist_first_name` on the same connection; that
slot alone is omitted on failure.

- [ ] TDD: the full design-plan 8.8 test list, verbatim, including the four A/B sibling
  combinations, the deactivated/restricted cases, the device-principal empty, and the
  unconnected-family indistinguishability property. ROUTE_TABLE row added. Commit.
  **Do not enable shipping surfaces until G2 passes.**

### Task C5: dedication overlay (**[Stage R re-scope]** mandatory, no longer droppable)

Originally "last; first thing dropped if the stage runs long". The re-insertion measurement
reversed that: 11/30 corpus stories never name the hero in prose (second-person narration),
so the dedication is the ONE surface guaranteed to carry the child's name in every
personalized story. It is now a required Stage C deliverable and the surface gate G1-R's
"dedication guaranteed" clause points at.

**Files:** one component in `frontend/src/reader/` beside `ReaderChrome.tsx`, template
`For {NAME}, love {KINSHIP}`, composed client-side from values the payload already carries;
one `dedication` slot row (ring 1, enforced by the B1 CHECK). Never enters `node.body`, never
reaches `PassageText`. TDD, commit.

---

## Stage D: surfaces, migration, compliance (blocked on Stage C; D1 gates the flag)

Branch: `feat/personalization-p9-p11-surfaces`.

### Task D1: Route A copy wiring (G3; merge before any flag enablement)

**Files:** `src/cyo_adventure/story_requests/interpretation.py` only, in exactly three edits
(design-plan section 12; the drafted strings are in ADR-023 coordination Ask 1b):

1. Catalog key gains a toggle axis: `(disposition, reason, band_group, personalized: bool)`;
   `_register` (`:709-721`) takes three optional `*_personalized` pairs defaulting to the
   standard ones, so only `IDENTITY_PROTECTION` supplies them.
2. `render_interpretation` (`:1249`) gains keyword-only
   `name_personalization_enabled: bool = False` (a bool, never the profile object; the
   module's purity discipline is load-bearing).
3. Five production call sites thread `profile.real_name_ring1_enabled`:
   `generation/worker.py:380, :433, :532` and `interpretation.py:1441, :1487` (re-verify
   these line anchors first). Also fix the stale "Section 5 Decision 4" citation at `:174`.

- [ ] TDD: existing `IDENTITY_PROTECTION` tests pass unchanged (Route A intact); new tests for
  the toggle-on variants per band group. Commit.

### Task D2: guardian settings UI and the ring-2 consent ceremony

**Files:** `frontend/src/guardian/` beside existing profile management; ceremony reuses the
shape of `GuardianConsentPage.tsx` but is a separate flow, separate copy. The ceremony copy
constraints are design-plan 10.1.1 items 1-3 verbatim (enumerated slot names, the companion-
appearance clause, the distinct sibling-authority attestation writing
`sibling_authority_attested`), plus the prospective-revocation and never-reaches-a-provider
sentences. Framing per ADR-023 section 8: fictional protagonist is the recommended default.
TDD, commit. **Ships only after G2.**

### Task D3: kid-facing control

Local-only per-profile per-device preference ("Use my name in stories"), multiplies with the
guardian envelope, never widens it; **not rendered at all for the 3-5 band**, and the guardian
settings screen says so in as many words. TDD, commit.

### Task D4: first personalizable contract and catalog migration (the power switch)

- [x] Declare `kind: "personalizable"` slots (with `role_safety` on real-person fields) in one
  pilot contract; run the full gate. **DONE 2026-07-31** (commits `84ef0574`, `d76a1bc7`): HERO
  declared personalizable in `skeletons/10-13/the-midnight-museum.contract.json`
  (`personalization_field: "protagonist_first_name"`, `role_safety: "protagonist"`,
  `default_binding.HERO = "Nadia"`). Gate evidence: `uv run python scripts/check_skeleton.py
  skeletons/10-13/the-midnight-museum.json --band 10-13` reports "ok: skeleton passes gate and
  brief checks"; `uv run python scripts/check_theme_contract.py
  skeletons/10-13/the-midnight-museum.json` passes all 7 WS-2 acceptance checks (gate,
  contract load/cross-check, forbid-bundle ids, default-binding validation, a synthesized
  lethal-value rejection on `A2_GATE`, `render_bound_skeleton` with zero residual tokens, no
  retired-theme proper noun). Also exercised directly against the real on-disk files (not a
  copy) by `load_skeleton`/`load_contract_for` in
  `tests/unit/test_d4_pilot_integrity.py::test_pilot_contract_declares_exactly_hero`.
- [x] Confirm Variant A/B checks fire on a deliberately mutated fixture, proven at unit level
  against the pilot's own declared slot (HERO) and default-binding value ("Nadia").
  **[Stage R re-scope]**: "fire" means the mutated blob no longer matches the version's DERIVED
  `sentinel_manifest` (Task R3 semantics), not the contract-prescribed multiset. **DONE
  2026-07-31** (commit `7e96e52c`, `tests/unit/test_d4_pilot_integrity.py`):
  `test_untouched_pilot_blob_passes_verify_manifest` proves the positive case;
  `test_mutated_pilot_blob_fails_verify_manifest` proves three independent at-rest mutations
  (stripped sentinel, partial strip, forged addition in an unrecorded node) each fail
  `verify_manifest`; `test_hero_coverage_warns_only_when_hero_is_uncovered` proves the zero-HERO
  soft-floor WARNING mechanism itself fires (calling `_warn_on_zero_coverage_slots` directly)
  for the pilot's real declared slot set, and stays silent once HERO is covered. All three are unit-level proofs against hand-built or
  directly-invoked fixtures carrying the pilot's real slot id and default value, not a live
  pilot-story generation.
- [x] Generate a pilot story through the live fill pipeline; confirm Variant A/B fire against
  that story's actual generated `sentinel_manifest` (not a hand-built fixture). **DONE
  2026-07-31**, owner-run, script path (not the worker path; see the scope note below). Run
  slug `20260731T173743Z`, provider openrouter with fallback leg
  `anthropic/claude-haiku-4.5`. The run's aggregate numbers are committed, verbatim and
  sanitized, at [d4-pilot-run-20260731.md](d4-pilot-run-20260731.md); the raw fill prose and
  the original `/tmp/d4-pilot-run/20260731T173743Z/` tmpdir are not part of the repo.
  `scripts/measure_sentinel_survival.py --count 1` against the pilot skeleton with its now-
  personalizable HERO slot: first-attempt survival 0/1 clean, consistent with the Stage R
  ~3.3% baseline that motivated the reinsertion design in the first place; **not a failure
  signal**, it is why the deterministic transform exists.
  `scripts/prototype_sentinel_reinsertion.py` on the saved fill: HERO reinsertable 23/23 nodes
  (100% coverage of the personalizable slot, so the zero-coverage soft floor correctly did not
  fire on this run); `verify_manifest` pass 1/1 (100%, the G1-R transform-correctness metric
  this task requires at 100%); overall 76/78 tokens reinsertable, with the only 2 `not_found`
  being the theme slots GUARD and THRESHOLD, which production never sentinel-wraps (they are
  not `kind: "personalizable"`). **Scope note: this proves the script-path generation and
  reinsertion evidence (real-provider fill plus offline deterministic reinsertion plus
  manifest self-consistency), not a full worker-path end-to-end.** DB stamping of
  `personalization_eligible`, the validator gate, moderation, and library visibility remain
  covered by the Task 2 and Task 4 unit suites and will get their first live coverage on the
  first staging deploy that runs the actual `generation/worker.py` path against this contract;
  do not read this checkbox as proof of that.
- [x] Replace-by-default migration of any test story worth keeping eligible; everything not
  migrated stays `personalization_eligible = false` with no deadline. **RATIFIED BY OWNER
  2026-07-31** (Task 6): keep `sk_midnight_museum` v1 exactly as is, a book without
  personalization; it stays `personalization_eligible = false` with no deadline. See the
  "Replace-by-default migration decision" block below for the full record.
- [x] Pronoun audit (per-skeleton, directives not prose; `pronoun_parameterized` flips only
  after a human read) and the R11 role-safety audit ride along. **DONE 2026-07-31** (Task 3,
  commit `a51df507`): see the "Pilot audit record" below.
- [x] Append lessons rows; this is squarely authoring/validator work. Commit. **DONE 2026-
  07-31**: `AL-071` (the `personalization_eligible` producer-docstring gap this branch closed),
  `AL-072` (the D6 migration-prefix collision, linked via `UW-C21`), and `AL-073` (the
  cwd-relative `.env` file-path setting breaking the owner's Task 5 run from a worktree,
  linked via `UW-C22`) are appended.

**Pilot audit record (2026-07-31, pre-generation): the-midnight-museum (10-13).**

- **HERO placement count.** `grep -c "{HERO}" skeletons/10-13/the-midnight-museum.json` returns
  23 occurrences, all inside `<<FILL ...>>` directive text, one each across 23 distinct nodes
  (the enumerated list below has 23 entries): `n_start`,
  `a_gems_vitrine`, `a_gems_hide`, `b_egypt_torch`, `n_key`, `k_study`, `v_reveal2`,
  `e_set_alarm`, `e_set_stuck_dark`, `e_set_broken_case`, `e_set_jammed_globe`, `e_set_caught`,
  `e_set_dawn`, `e_win_secret_workshop`, `e_win_mystery_solved`, `e_win_quiet_keeper`,
  `e_win_lost_wing`, `e_win_hero_curator`, `e_win_secret_kept`, `e_win_donate`,
  `e_neutral_call_home`, `e_neutral_evidence`, `e_neutral_wiser`.
- **R11 role-safety verdict, per questionable beat.** The contract declares HERO's
  `role_safety` as `"protagonist"`, so R11 requires every placement to avoid casting HERO as
  antagonist or as the target of a mishap. The skeleton has 12 endings whose `kind`/`valence`
  metadata marks them non-positive (9 `setback`/`negative`, 3 `discovery`/`neutral`); the nine
  of those that carry a `{HERO}` placement, the only ones R11 has anything to say about, were
  each read in full:
  - `e_set_alarm`, `e_set_stuck_dark`, `e_set_broken_case`, `e_set_jammed_globe`,
    `e_set_caught`, `e_set_dawn` (all `ending.kind == "setback"`,
    `ending.valence == "negative"`): HERO trips an alarm, gets briefly stuck, damages a case,
    jams a globe exhibit, gets caught, or has to leave at dawn empty-handed. In every one HERO
    remains the actor making the choice that led to the setback, not the object of harm
    inflicted by another character; no antagonist role, no injury, no malicious framing.
    **Verdict: PASS**, no antagonist/mishap framing.
  - `e_neutral_call_home`, `e_neutral_evidence`, `e_neutral_wiser` (all
    `ending.kind == "discovery"`, `ending.valence == "neutral"`): HERO chooses to call a
    guardian, hand over evidence, or leave having learned something. HERO is the deciding
    actor in each; no antagonist or mishap framing. **Verdict: PASS.**
  - The remaining 14 placements (7 opening/setup nodes and all 7 positive `e_win_*` endings)
    place HERO as the story's protagonist throughout, the framing R11 exists to protect.
    **Verdict: PASS.**
  - **Overall: no UNRESOLVED placements.** All 23 `{HERO}` occurrences keep HERO in the
    protagonist role; none is antagonist- or mishap-framed under R11.
- **Pronoun audit.** `grep -inc` for `she|her|he\b|him\b|they\b|them\b` across
  `skeletons/10-13/the-midnight-museum.json` matches 149 lines: the fill directives refer to
  HERO with a fixed pronoun (she/her) written directly into the directive prose, not through a
  sentinel or slot token. Per this bullet's own instruction, the audit is of the directives
  (what the skeleton instructs the fill LLM to write), not of any already-generated prose, and
  `pronoun_parameterized` (a per-`storybook_version` column, `db/models.py`) flips only after a
  human read confirms the fixed pronoun could be swapped without a skeleton rewrite; no such
  contract or skeleton change was made here. **the-midnight-museum D4 pilot:
  `pronoun_parameterized` remains false; pronouns not parameterized; flip requires a future
  per-skeleton audit plus contract change.**

**Replace-by-default migration decision (2026-07-31, RATIFIED by owner).**

- **Prod inventory.** Exactly one prod `storybook_version` row traces to the pilot skeleton
  (`skeleton_slug = 'the-midnight-museum'`): storybook `sk_midnight_museum`, version 1,
  approved and published 2026-07-28 15:14 UTC (created 2026-07-21), one of the 28 published
  catalog books. Full catalog spread: 27 distinct skeleton slugs with 1 version each, plus
  `the-cave-of-echoes` (3 versions, series) and 3 versions with a NULL `skeleton_slug`
  (pre-column imports, never backfilled by design, `models.py:998`).
- **Recommendation: keep `sk_midnight_museum` v1 exactly as is.** It stays
  `personalization_eligible = false` (see the prod-schema note below: the column does not exist
  in prod yet) with no deadline, per this task's own "everything not migrated stays false"
  clause. Regenerating a published prod book through the post-D4 pipeline is a content
  replacement requiring the full validator plus moderation plus human approve/publish
  ceremony, and would produce new prose for a book a child may already have read; the pilot's
  eligibility proof comes from a fresh local generation (Task 5) instead. Migrating the prod
  book, if ever wanted, is a separate owner-initiated regeneration run. **Ratified by the owner
  2026-07-31: keep `sk_midnight_museum` v1 exactly as is; no migration of the published prod
  book.**
  - **Tension with ADR-023 section 6, recorded not resolved.** That section grounds "replace by
    default" in there being no live child-linked production data; the inventory above establishes
    the opposite (one published book a child may already have read), and that is precisely the
    reason not to regenerate it. The outcome is permitted by this task's own "everything not
    migrated stays false" clause and is owner-ratified, so nothing here is blocked, but the ADR
    clause's stated premise no longer holds and should be amended the next time ADR-023 is
    revised. Flagged so the next reader does not treat the ADR premise as still-current fact.
- **Prod-schema note (deploy-relevant, not D4-blocking).** `storybook_version
  .personalization_eligible` does not exist in prod: the ADR-023 Stage B migrations that add it
  have not been applied there (the live column list ends at `skeleton_slug`, 15 columns).
  `sentinel_manifest` and `pronoun_parameterized` are likewise absent. The next prod deploy
  must apply the pending `supabase/migrations` chain before the new image boots, since that
  image's `api/library.py` reads these columns (D8). Pairs with the existing note that the next
  prod image also needs a real moderation reviewer or `CYO_ADVENTURE_ALLOW_MOCK_REVIEW=1`.
- **Staging.** Not queried (the Supabase MCP session is scoped to the prod project).
  `seed_staging.py` seeds only the tide-pools and clockwork-garden fixtures, so a
  midnight-museum story on staging is unlikely but unverified.

### Task D5: compliance artifacts and closeout

- [ ] Erasure response template sentence (design-plan 8.7) into the remediation plan's Phase 3
  erasure work; retention-table rows for slot values and consent evidence
  (`coppa-gdpr-remediation-plan.md:710-719`).
- [ ] ADR-018 P7-08: new processing purpose, notice, classification, nutrition labels.
- [ ] ADR-016 amendment: **one** edit recording both B6 attribution granularity and ring-2
  personalization granularity (the parked addendum block marks the spot); coordinate so it is
  written once.
- [ ] Capability register: flip **G18** and **K20** from ❌ with spec links and covering tests.
- [x] ADR-023 status: flipped Proposed to Accepted. The original condition read "when counsel
  closes OD-1/OD-5"; no external counsel exists at this scale, so owner review closed both
  instead (the gates table's G2 entry is the record). **DONE 2026-07-29: owner review closed
  both (OD-5 conditionally, R1 scope), satisfying G2 at R1 scope; status flipped the same day
  on the Stage C branch (PR #489).**

### Task D6: closed-vocabulary implementation (split `favorite`, seed the accepted lists)

Implements the 2026-07-29 vocabulary decisions from
`personalization-closed-vocabularies-proposal.md` (accepted lists recorded there):

- [x] Split `favorite` into `favorite_color` / `favorite_food` / `favorite_hobby` (Option B):
  new slot_type values in the DB CHECK constraint (Supabase migration), `PERSONALIZATION_FIELDS`
  (`theme_contract.py`), `_PersonalizationSlotType` (`api/schemas.py`), and any theme-contract
  slot declaration bound to `favorite` today; regenerate the frontend client (contract change).
- [x] Seed `CLOSED_VOCABULARIES` with the accepted lists: pet_species (16), kinship_label (21),
  dedication (same 21), home_type (12), and the three split favorite lists (12 each), citing
  the proposal doc per the dict's `#VERIFY` marker.
- [x] No case normalization anywhere (owner decision): values are stored and matched exactly
  as listed. No "none" sentinel members. Drift-guard test per AL-068/UW-C20 rides along.
- [x] TDD throughout; one membership test per vocabulary; commit.

**DONE 2026-07-31 (PR #507).** No theme-contract slot was bound to `favorite`: no contract on
disk declares a `kind="personalizable"` slot yet, so the split cost no catalog edit. Two
deviations found in review and fixed on the branch:

1. **The vocabulary has two stores, and the first draft swept only one.**
   `child_profile_personalization.slot_type` carries a DB CHECK, which made a `'favorite'` row
   unwritable, so the migration's `DELETE` is purely defensive. But
   `personalization_disclosure_consent.covered_slot_types` is an *unconstrained* JSONB array holding the
   same names, gated only in Python, where `'favorite'` genuinely was writable. The migration
   now sweeps it too, **removing** the element rather than expanding it into the three new keys:
   rewriting one grant into three would widen a ring-2 sharing scope to facts the guardian was
   never shown. Pinned by a new drift guard binding that column's admissible vocabulary to the
   same ceiling as `ck_cpp_ring2_ceiling`.
2. **Migration version collision.** The file first shipped as `20260730000000_`, which `#494`
   had already taken for `add_cover_object_salt.sql`; Supabase keys `schema_migrations` on that
   prefix, so both integration legs failed on `duplicate key value violates unique constraint
   "schema_migrations_pkey"`. Renamed to `20260730010000_`.

Also recorded: the longest vocabulary member is 3 words (`mac and cheese`), which becomes a
floor on `max_words` for the first catalog slot bound to a personalization field. Latent today
(no personalizable slot exists), pinned by a ceiling test so a longer member cannot be added
silently.

### Task D7: vocabulary-expansion request feature (owner-requested 2026-07-29)

- [ ] Spec first, citing the capability register IDs served (guardian requests an entry for a
  closed vocabulary; admin validates appropriateness and expands the list; the expansion is an
  audited event). Follows the existing request/review shape (story_requests, flags) rather
  than inventing a new one. Build after D6 lands the split schema.

### Task D8: expose `personalization_eligible` to the reader (owner-scheduled 2026-07-29)

- [ ] Add `personalization_eligible` to the library response (`LibraryItemView`), thread it
  from `LibraryPage` into the reader route state, and skip the values fetch when false.
  Closes Stage C open question 2; pure optimization, the fetch already fails safe.

---

## Self-review notes (recorded, not aspirational)

- Clause-level spec coverage was checked against design-plan sections 4 through 12; the one
  deliberate deviation: consent/toggle **event types** are built in Stage B (Task B4) beside
  their emitters rather than in P3 where the design plan lists them, because an allowlist entry
  with no emitter is dead config.
- Fixture-vs-gate: the slot vocabulary in Task B1's CHECKs is pinned to
  `PERSONALIZATION_FIELDS` by a drift-guard test, not copied by hand; the A2 excerpt fixture is
  validated against `_opening_excerpt` itself (the strictest consumer).
- Manual-variant env: every documented command that loads app settings carries
  `ENVIRONMENT=local`; the measurement command names its key prerequisites.
- Known drift risk: all `file:line` anchors are 2026-07-28 origin/main; each stage re-verifies
  before editing.
- Stage R revision (2026-07-29) pairwise sweep: the four places that assumed a PRESCRIBED
  token multiset were each resolved in place and tagged **[Stage R re-scope]** (B2's
  `sentinel_manifest` semantics, C5's droppable-to-mandatory promotion, D4's Variant A/B
  firing definition, and the G1 gate row's succession to G1-R). Stages B through D otherwise
  survive unchanged because they operate on "the blob carries well-formed tokens" and never
  depended on how tokens entered it. Task R4 deliberately claims representativeness (shared
  transform), not production-path execution, for the offline instrument.

## Related

- [ADR-023](./adr/adr-023-story-personalization-slots.md), the decision record.
- [Design plan](./story-personalization-implementation-plan.md), sections 4-12 are the
  authority wherever this plan compresses.
- [authoring-lessons-log.md](./authoring-lessons-log.md), the standing logging obligation.
- [capability-register.md](./capability-register.md), G18/K20.
