---
title: "CYO Adventure - Phased Build Execution Plan"
schema_type: planning
status: draft
owner: core-maintainer
component: Strategy
source: "docs/planning/PROJECT-PLAN.md, roadmap.md, tech-spec.md, project-vision.md, adr/001-006"
purpose: "Execution plan for building CYO Adventure across all phases, one PR per phase, starting with the Phase 0 foundations gate."
tags:
  - planning
  - roadmap
  - project
authors:
  - name: "Byron Williams"
---

> **For agentic workers:** REQUIRED SUB-SKILL per phase: use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement each phase's task list. Steps use checkbox (`- [ ]`) tracking. This file is the **master** plan; each phase gets its own detailed plan file written at its boundary.

## Context

The repo holds a complete set of planning documents (`PROJECT-PLAN.md`, `roadmap.md`, `tech-spec.md`, six ADRs) for **CYO Adventure (Ariadne)**, a family choose-your-own-adventure reader plus a safety-gated LLM story-generation pipeline. No application code exists yet: `src/cyo_adventure/` contains only cookiecutter template boilerplate (config, middleware, health, logging, exceptions, async database plumbing).

A **parallel stream** is bringing the repo up to org-standard templates on branch `chore/compliance-standards-alignment` (uncommitted edits to `pyproject.toml`, template modules, plus a new `database.py` and `.cruft.json`). That stream owns generic template/CI/standards alignment, which maps to plan item **P0-10**.

**Goal (user-confirmed):** build out the entire PROJECT-PLAN, **all phases, one PR per phase**. Items needing a human decision are drafted with explicit **OPEN blockers** (RAD `#CRITICAL` / `#VERIFY` markers), never silently assumed.

**Honest cadence note:** the plan's own estimate is 16-25 weeks for 1-2 developers across a Python backend *and* a React PWA. This is a long-horizon, multi-session effort. This plan delivers **Phase 0 in full as PR #1 now**, then proceeds phase by phase; each phase's PR is a natural review checkpoint. "All 5 phases" is the destination, driven phase-gated, not a single-session claim.

## Execution Model

1. **Isolation via worktree.** Work happens in a git worktree off `main` at `../cyo_adventure-worktrees/<phase-slug>` (project CLAUDE.md convention), so the parallel stream's uncommitted tree is never disturbed. Each phase = its own branch from the plan's branch map.
2. **Phase-gated, PR per phase.** Branch order: `chore/phase-0-foundations` → `feat/phase-1-schema-reader` → `feat/phase-2-generation-gate` → `feat/phase-3-safety-review` → `feat/phase-4a-library-profiles` → `feat/phase-4b-editor-ux` → `chore/phase-5-hardening`. Each merges to `main` via a signed, conventional-commit PR after its quality gates pass.
3. **Plan-then-execute each phase.** At each phase boundary, write a detailed bite-sized plan file (`docs/superpowers/plans/`), then execute task-by-task with TDD and frequent signed commits.
4. **Coordination with the compliance stream.** Phase branches start from `main`. When the compliance PR merges to `main`, rebase the next phase branch on updated `main`. Phase 0 (docs + schema) has near-zero file overlap with the compliance stream (which tightens existing template config), so they proceed independently.
5. **OPEN blockers.** Human-only items (Anthropic data-handling terms; Pangolin/homelab reachability; solo-dev "cross-sign" approvals) are written as complete documents with the decision point marked `#CRITICAL` + `#VERIFY` and an "OPEN - requires human action" callout. They do not block drafting; they block the *gate close*.

## Conventions to follow (from codebase discovery)

- **Python deps:** PEP 621 `[project.optional-dependencies]`; add with `uv add <pkg>` (prod) / `uv add --dev <pkg>` (dev). API libs live in the `api` extra. New runtime libs (networkx, textstat, rq, anthropic) → `uv add`; test libs (hypothesis) → `uv add --dev`.
- **Reuse existing modules:** extend `core/exceptions.py` (`ValidationError`, `AuthorizationError`, `ProjectBaseError.to_dict`), `core/database.py` (`Base`, `get_session`), `core/config.py` (Settings singleton), `utils/logging.py` (structlog `get_logger`).
- **Code style:** `from __future__ import annotations`; Google docstrings; Ruff 88-char strict + RAD codes; BasedPyright strict. Tests in `tests/unit/` and `tests/integration/` with `@pytest.mark.unit` / `integration`.
- **Docs gates:** new `docs/` pages outside `docs/planning/` need valid frontmatter (`schema_type`, `component`, `source`, `purpose` ending in punctuation, tags from `docs/_data/tags.yml`, owner from `docs/_data/owners.yml`). **Every** new `docs/` page must be added to `mkdocs.yml` nav (`strict: true`). Files at repo root (e.g. `TECHNICAL_BASELINE.md`) are exempt from both.
- **Commits:** `git commit -S`, conventional messages, no em-dashes, `pre-commit run --all-files` before each commit.

---

## Phase 0: Foundations (PR #1 - this session) - `chore/phase-0-foundations`

**Objective:** lock the decisions and artifacts expensive to change once code exists. The schema and the spec docs *are* the gate; this is not "app code."

### 0.A Schema module (the keystone)

**Files:**
- Create `src/cyo_adventure/storybook/__init__.py`
- Create `src/cyo_adventure/storybook/models.py` - Pydantic v2 models: `Storybook`, `StoryMetadata`, `Variable`, `Node`, `Choice`, `Effect`, `Ending`, plus enums (`AgeBand`, `VariableType`, `EffectOp`, `ContentFlagLevel`). Encodes unique node/choice/ending ids (model validators), int `min`/`max`, optional `once`, `schema_version`.
- Create `src/cyo_adventure/storybook/condition.py` - typed model for the JSONLogic condition shape (whitelisted operators only: `var`, `== != < <= > >=`, `and or !`).
- Create `src/cyo_adventure/storybook/schema_export.py` - dumps `Storybook.model_json_schema()` to `schema/storybook.schema.json`.
- Create `schema/storybook.schema.json` (generated artifact, committed).
- Test `tests/unit/test_storybook_schema.py` - round-trip (model → JSON Schema → validate fixtures), unique-id validators, bound checks.

**Task steps (TDD, per model group):** write failing test for the model + its validator → implement model → run → green → commit. Repeat for `Effect`/`Variable`, `Choice`/`condition`, `Node`/`Ending`, `Storybook` aggregate + cross-id uniqueness, then the JSON Schema export round-trip.

### 0.B Fixture corpus

**Files:**
- `tests/fixtures/storybook/valid/*.json` - ≥5 valid stories (Tier-1 simple branch; Tier-2 with vars; minimal hello-world; multi-ending; conditional-gated choice).
- `tests/fixtures/storybook/invalid/*.json` - ≥10 invalid: dangling target, orphan node, unreachable ending, non-terminating node, trap loop, undeclared variable, non-whitelisted operator, type-mismatched comparison, bound-overflow effect, duplicate node id, missing ending block.
- Test `tests/unit/test_fixtures_validate.py` - every valid fixture passes schema validation; every invalid fixture fails (asserting the offending rule once the validator exists in Phase 1; here, schema-level failures only).

> Note: graph/state-space rejections land in Phase 1/2 validators. Phase 0 asserts schema-level validity/invalidity and pins the corpus so the validators have a target.

### 0.C Specification documents (under `docs/planning/`, frontmatter-exempt; wire into `mkdocs.yml` nav)

- `docs/planning/runtime-semantics.md` - Story Runtime Semantics v1 (transition order, `once`, bounds-reject, hidden-vs-shown, snapshots, no-backtrack, version pinning). Marked for owner cross-sign.
- `docs/planning/validator-rules.md` - Layer-1 (rules L1-1..L1-7) and Layer-2 (L2-8..L2-12) catalog: rule id, description, failure message template, node attribution; reading-level (advisory) and safety rules.
- `docs/planning/condition-evaluator-spec.md` - evaluator contract (totality, no raising, boolean result), whitelisted-operator table, exclusions, and the shared conformance-fixture format.
- `docs/planning/authorization-matrix.md` - endpoint × role table; the four IDOR negative tests enumerated.
- `docs/planning/privacy-model.md` - data classification, retention, deletion-readiness, prompt-injection defense. **OPEN:** Anthropic data-handling terms (`#CRITICAL` + `#VERIFY`).
- `docs/planning/configuration-cap.md` - worked example: reachable-config count for 2 bools + one `int(0-5)` across ~50 nodes vs the 100,000 ceiling.
- `docs/planning/drafting-guide.md` + `docs/planning/stage-prompts/{structure,prose,repair}.md` - drafting guide and the three staged-generation prompt templates.

### 0.D Decision + scope + baseline docs

- `docs/mvp-cut.md` - one-page in/out scope (needs frontmatter + nav entry).
- `docs/phase0-decisions.md` - the seven ratified Part V decisions (needs frontmatter + nav entry).
- `TECHNICAL_BASELINE.md` (repo root) - exact pinned versions (backend + frontend + container tags), RQ + in-house evaluator confirmed, **no `latest` tags** (note: `docker-compose.yml` currently uses `${VERSION:-latest}` - flag for the compliance stream / fix here), Alembic migration convention (naming, down-revision policy, CI migration check).

### 0.E Wire-up + template feedback

- Update `mkdocs.yml` nav to include every new `docs/` page (or `mkdocs build --strict` fails).
- Append any template gaps found (e.g. `latest` fallback in compose, missing PWA/XState/idb deps) to `docs/template_feedback.md` per the project's mandatory template-feedback rule.

### Phase 0 OPEN blockers (carry forward, do not close the gate without them)

1. **Anthropic data-handling terms** (P0-09) - confirm standard retention vs ZDR. Human action.
2. **Homelab hosting reachable through Pangolin** (P0-10) - infra. Human action.
3. **Owner cross-sign** of runtime semantics + validator rules + schema (solo-dev: Byron's approval).

### Phase 0 quality gates

- [ ] `uv run pytest --cov=src --cov-fail-under=80` green (schema + fixtures ≥80%, ≥90% on schema validators)
- [ ] `uv run ruff check .` + `ruff format --check .` clean; `uv run basedpyright src/` strict clean
- [ ] `uv run bandit -r src` + `pip-audit` no high/critical
- [ ] `mkdocs build --strict` succeeds (all new docs in nav, frontmatter valid)
- [ ] `pre-commit run --all-files` green; commits signed + conventional
- [ ] A "hello world" Storybook validates against `schema/storybook.schema.json`

### Phase 0 verification (end-to-end)

```bash
cd ../cyo_adventure-worktrees/phase-0-foundations
uv sync --all-extras
uv run python -m cyo_adventure.storybook.schema_export   # regenerates schema/storybook.schema.json
uv run pytest tests/unit/test_storybook_schema.py tests/unit/test_fixtures_validate.py -v
uv run mkdocs build --strict
pre-commit run --all-files
```

Then open the PR for `chore/phase-0-foundations` → `main`.

---

## Phases 1-5 (sequenced; each planned in detail at its boundary)

Each phase below lists branch, headline deliverables, and the key reuse/new-dependency notes. A full bite-sized plan file is written when the phase starts.

### Phase 1 - Schema, Runtime, Reader MVP - `feat/phase-1-schema-reader`
- **Backend:** deterministic player library (Python) + Layer-1 graph validator (networkx) over the Phase-0 fixture corpus; in-house condition evaluator (Python) with Hypothesis totality tests.
- **Frontend:** PWA reader (add `vite-plugin-pwa`, `XState`, `idb`); state-gated choices (hidden when false); offline service-worker + IndexedDB cache; save/resume; revision-based multi-device sync with 409 reconciliation UX; TS condition evaluator + shared conformance fixtures (fast-check).
- **Tests:** cross-impl conformance corpus (Python ≡ TS); runtime-semantics fixtures; Playwright offline/save-resume/409 (wire Playwright into CI).
- **Reuse:** `ValidationError`, `database.py`, OpenAPI client generation (`scripts/generate-client.sh`).

### Phase 2 - Validation Gate + Authoring Pipeline - `feat/phase-2-generation-gate`
- Layer-2 state-space validator (config walk, stateful dead-end/termination/loop-escape, conditional usefulness, 100k cap); generation orchestrator (Stage A/B/C with repair cap=3 + no-progress abort); `GenerationProvider` interface (Claude primary; Ollama/OpenRouter fallback; `uv add anthropic`); RQ worker (`uv add rq`); concept intake; known-bad + Tier-2 corpora.
- **Precondition:** Phase-0 OPEN blocker #1 (provider data-handling) must be closed before the first real LLM call. Mocked-provider integration tests need no external egress.

### Phase 3 - Safety + Review Workflow - `feat/phase-3-safety-review`
- Moderation pass (provider API + independent LLM-reviewer, per-age-band); publish state machine (`draft→…→published→archived`, guardian-only `approve`); parent review surface; provenance/audit on `storybook_version`; authz enforcement + all IDOR negative tests green.

### Phase 4a - Library + Profiles (FIRST RELEASE) - `feat/phase-4a-library-profiles`
- `GET /api/v1/library?profile_id=` filtered by published status + age band + reading cap; `child_profile` records server-enforced; guardian view→approve→publish→assign flow; profile management screens.

### Phase 4b - Editor, Engagement, UX (post-release) - `feat/phase-4b-editor-ux`
- Lightweight node editor (`PATCH …/nodes/{id}` → repair pass → revalidate); ending tracker (`completion` table, stable `ending.id`); bookmarks; read-aloud (Web Speech API).

### Phase 5 - Hardening + Deploy - `chore/phase-5-hardening`
- Performance pass to targets (node <50ms, library <300ms, validation <2s/200-node); iOS PWA eviction hardening; WCAG AA basics; Sentry client+server; nightly Postgres+MinIO backup and a **restore drill**; operator runbook + authoring guide.
- **Precondition:** Phase-0 OPEN blocker #2 (Pangolin/homelab) for the live deploy.

---

## Master risks / coordination

| Risk | Mitigation |
|------|------------|
| Merge conflict with compliance stream on shared config (`pyproject.toml`) | Phase 0 only *adds* deps via `uv add`; rebase each phase branch on `main` after the compliance PR merges |
| Over-long single session | Phase-gated; each PR is a stop/checkpoint; subsequent phases resume from this master plan + per-phase plan files (survives compaction) |
| Worktree venv drift | `uv sync --all-extras` in each worktree after creation |
| Human-blocked items stall a phase gate | Drafted now with `#CRITICAL`/`#VERIFY` OPEN markers; surfaced in each PR description so the human action is visible |
| Scope creep beyond source docs | This plan adds no scope absent from PROJECT-PLAN/roadmap/tech-spec |

## Immediate next actions on approval

1. Create worktree `../cyo_adventure-worktrees/phase-0-foundations` on `chore/phase-0-foundations` from `main`; `uv sync --all-extras`.
2. Create the Phase 0 task list (TaskCreate) covering 0.A-0.E.
3. Execute 0.A → 0.E TDD-style with signed commits; run the verification block; open PR #1.
4. On PR #1 review, write the Phase 1 detailed plan file and continue.
