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

**Not started (this plan):** every P3 title/prompt strip, all persistence, all API routes, all
frontend work, all UI, the Route A copy wiring, the catalog migration, and the compliance
artifacts. No `.contract.json` on disk declares a personalizable slot, so every merged check is
currently a structural no-op: the first contract that declares one is the feature's power
switch and is deliberately sequenced late (Task D4).

**PR #416 has merged**, so the authoring-lessons directive is live: any task below that touches
validator or authoring behaviour appends its lessons to
[authoring-lessons-log.md](./authoring-lessons-log.md) and validates with
`uv run python scripts/check_lessons_log.py`.

## Gates and owner decisions

| Gate | What it blocks | Condition to pass |
|---|---|---|
| **G1: survival GO/NO-GO** | Stage B onward (everything after leak guards) | Task A1's measured clean-pass rate at or above ~95% is GO; 80-95% means iterate the prompt/delimiter and re-measure before proceeding, with the retry cost line made explicit; below ~80% is STOP: prototype deterministic post-fill re-insertion instead and re-plan Stage B+ |
| **G2: counsel on OD-1/OD-5** | **Shipping** P7 (ring-2) and P9 (consent UI); building them is not blocked | Counsel confirms the ring-2 separate disclosure consent design and the sibling/pet-name raise |
| **G3: Route A copy precedes the flag** | Enabling `VITE_FEATURE_PERSONALIZATION` anywhere a real family can reach | Task D1 (toggle-aware Route A copy) merged |

Owner decisions recorded 2026-07-28 (this plan is their record; Task A6 propagates them into
the design plan):

- **Section 3.4 measurement runs as Stage A work, and Stage B+ stays gated on its result** (the
  design plan's own P4-waits-on-P2 rule, confirmed).
- **R20 (shared-device IndexedDB isolation of values payloads): accepted for v1.** A shared
  family device is a shared trust boundary; no per-profile encryption, no in-memory-only mode.
  The acceptance must be recorded in the DPIA/privacy-model entry (Tasks A6, B9), not silently
  inherited.

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
  injects `.env`, and non-local guard families trip otherwise).

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

Run: `ENVIRONMENT=local uv run pytest tests/unit -q -x --timeout=120 -k "sentinel or covers or recommendations"`
Expected: PASS (pins the pre-change behaviour of the files this stage edits).

- [ ] **Step 3: copy this plan into the worktree and commit it**

```bash
cp ../../docs/planning/story-personalization-execution-plan.md docs/planning/
git add docs/planning/story-personalization-execution-plan.md
git commit -S -m "docs(planning): staged execution plan for ADR-023 P3-P11"
```

### Task A1: run the section-3.4 sentinel-survival measurement (GO/NO-GO input)

The instrument is standalone: no DB, no backend, reads `skeletons/` from disk, writes
`report.json` and `report.md` under `results/sentinel-survival/<run-slug>/`. Provider
credentials come from `core.config.settings` (`.env`), not from CLI flags; a missing key
surfaces as `ConfigurationError`.

- [ ] **Step 1: mock smoke run (free, proves the harness)**

Run: `ENVIRONMENT=local uv run python scripts/measure_sentinel_survival.py --providers mock --count 5`
Expected: a run directory with `report.json` and `report.md`; clean-pass rate 100% on mock.
Abort if: the script errors before producing a report (fix the harness before spending money).

- [ ] **Step 2: real measurement across two providers**

Confirm `ANTHROPIC_API_KEY` and `OPENROUTER_API_KEY` (as named by `core/config.py`) are set in
`.env` first. Then:

Run: `ENVIRONMENT=local uv run python scripts/measure_sentinel_survival.py --providers anthropic openrouter --count 30 --slots-per-story 4`
Expected: per-provider clean-pass rate plus the failure taxonomy (dropped, duplicated,
relocated, mutated wrapper, mutated inner text) in `report.md`.
Abort if: `ConfigurationError` (missing key), or provider spend is not authorized. Cost is
roughly 60 frontier fill calls; approve the spend before this step, not after.

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

Run: `ENVIRONMENT=local uv run pytest tests/unit -q -k covers`
Expected: PASS, no regressions.

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

- [ ] **Step 1: the R2 registry test.** Every response model in `api/schemas.py` with a field
  named `title` must have an explicit strip decision, so the 29th router cannot forget:

```python
from pydantic import BaseModel
import cyo_adventure.api.schemas as schemas

# Explicit decisions; adding a title-bearing model without a row here fails the test.
DECIDED: dict[str, str] = {
    "LibraryItem": "strip",          # library.py::_library_item
    # ... enumerate what the scan below finds, with "strip" or "raw" + a comment
}

def test_every_title_field_has_a_strip_decision() -> None:
    found = {
        name
        for name, obj in vars(schemas).items()
        if isinstance(obj, type)
        and issubclass(obj, BaseModel)
        and "title" in getattr(obj, "model_fields", {})
    }
    assert found == set(DECIDED), (
        "New title-bearing response model: add a strip/raw decision and, if strip, a test."
    )
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
not start on a NO-GO.

---

## Stage B: data model and API (blocked on G1 GO)

Branch: `feat/personalization-p4-p5-data-api` off origin/main, after the Stage A PR merges.
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
- [ ] **Step 4: commit** (`feat(db): child_profile_personalization store and ring toggles (ADR-023 P4)`).

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
  `pronoun_parameterized BOOLEAN NOT NULL DEFAULT FALSE`, `sentinel_manifest JSONB` (per-node
  expected token sets, written at fill time so rescreen never re-reads the contract from disk).
  Verify the exact version-table model name in `db/models.py` before writing the DDL.

- [ ] Steps: same TDD rhythm as B1 (parity test + tombstone-behaviour unit test first, then
  migration + ORM, then PASS, then commit
  `feat(db): ring-2 consent evidence, viewer switch, subject link (ADR-023 P4)`).

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
- [ ] **Step 3:** commit (`feat(api): export and deletion coverage for personalization data (ADR-023 P4)`).

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

- [ ] TDD steps as above, plus one test asserting a value-bearing key (e.g. `pet_name`) is
  rejected by the allowlist. Commit
  (`feat(events): personalization consent/toggle event types (ADR-023 P3/P4)`).

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

- [ ] TDD steps; include one test per rejection class and one asserting the render-time
  fallback contract (invalid value at build time means the slot is omitted from the payload,
  never an error). Commit (`feat(storybook): personalization value validation (ADR-023 5.2)`).

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

- [ ] TDD steps; RouteSpec rows follow the dataclass at `test_authz_matrix.py:377-398` (copy
  the `PATCH /admin/profiles/{id}` row shape at `:445-451`). Empty payload, never 403, on any
  gate miss. Commit, then **regenerate the OpenAPI client in the same commit** (standing
  constraint). (`feat(api): personalization settings, consent, and ring-1 values routes (ADR-023 P5)`).

### Task B7: privacy-model classification entries

`depends-on: TaskB2 [completion]`. Docs only: the four entries from design-plan 5.6 into
`docs/planning/privacy-model.md` ("Data Classification" and "If Shared Beyond Family"),
including the R20 acceptance sentence for the client-held values payload. Commit
(`docs(privacy): classify personalization data categories (ADR-023 5.6)`).

**Stage B exit:** full gate green, contract job green, deletion drill green, PR merged.

---

## Stage C: client resolution and ring 2 (blocked on Stage B; shipping blocked on G2/G3)

Branch: `feat/personalization-p6-p7-client`.

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

### Task C5: dedication overlay (last; first thing dropped if the stage runs long)

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

- [ ] Declare `kind: "personalizable"` slots (with `role_safety` on real-person fields) in one
  pilot contract; run the full gate; generate a pilot story; confirm Variant A/B checks fire on
  a deliberately mutated fixture.
- [ ] Replace-by-default migration of any test story worth keeping eligible; everything not
  migrated stays `personalization_eligible = false` with no deadline.
- [ ] Pronoun audit (per-skeleton, directives not prose; `pronoun_parameterized` flips only
  after a human read) and the R11 role-safety audit ride along.
- [ ] Append lessons rows; this is squarely authoring/validator work. Commit.

### Task D5: compliance artifacts and closeout

- [ ] Erasure response template sentence (design-plan 8.7) into the remediation plan's Phase 3
  erasure work; retention-table rows for slot values and consent evidence
  (`coppa-gdpr-remediation-plan.md:710-719`).
- [ ] ADR-018 P7-08: new processing purpose, notice, classification, nutrition labels.
- [ ] ADR-016 amendment: **one** edit recording both B6 attribution granularity and ring-2
  personalization granularity (the parked addendum block marks the spot); coordinate so it is
  written once.
- [ ] Capability register: flip **G18** and **K20** from ❌ with spec links and covering tests.
- [ ] ADR-023 status: flip Proposed to Accepted when counsel closes OD-1/OD-5; until then G2
  keeps P7/P9 unshipped.

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

## Related

- [ADR-023](./adr/adr-023-story-personalization-slots.md), the decision record.
- [Design plan](./story-personalization-implementation-plan.md), sections 4-12 are the
  authority wherever this plan compresses.
- [authoring-lessons-log.md](./authoring-lessons-log.md), the standing logging obligation.
- [capability-register.md](./capability-register.md), G18/K20.
