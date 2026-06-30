# Task 6 Report: LLM Moderation Stages 1-4

**Branch**: feat/phase-3-safety-review
**Date**: 2026-06-30

---

## Files Changed

- `src/cyo_adventure/moderation/stages.py` (created)
- `tests/unit/test_moderation_stages.py` (created)
- `pyproject.toml` (added `**/moderation/stages.py = ["PLR0913"]` per-file Ruff override)

---

## Implementation Per Stage

### Stage 1: `run_safety_stage` (per-node, hard gate)

Matches the brief exactly. Per-node loop over `(node_id, prose)` pairs, prompts with the
`_SAFETY_SYSTEM` prompt (block/flag/safe triage), parses via `_parse_verdict` with
`fail_safe=Verdict.FLAG`. RAD markers required by the brief are present:
`#CRITICAL: security` and `#VERIFY: _parse_verdict maps unknown/garbled output to FLAG`.
Source: `LLM_SAFETY`, category: `"safety"`, stage: 1.

### Stage 2: `run_readability_stage` (per-node, soft gate)

Per-node loop. System prompt instructs the model to judge vocabulary/sentence complexity
against the band's Flesch-Kincaid grade target and tolerance. `reading_target` and
`tolerance` are embedded in the user prompt so the model has the numeric target.
Maps `flag` -> `FLAG` (too hard/off-target), `pass` -> `PASS`.
`fail_safe=Verdict.PASS` (soft gate). Source: `LLM_READABILITY`, category:
`"reading_level"`, stage: 2.

### Stage 3: `run_coherence_stage` (whole-story, one call, soft gate)

Single provider call. All nodes are rendered as `[node_id] prose` lines in the user
prompt. The model is asked to identify severe cross-branch plot/character/state
inconsistencies. Returns at most one `Finding` with `node_id=None`.
`fail_safe=Verdict.PASS`. Source: `LLM_COHERENCE`, category: `"coherence"`, stage: 3.

### Stage 4: `run_engagement_stage` (whole-story, one call, advisory only)

Single provider call. Same whole-story rendering as Stage 3. The model judges choice
distinctness, pacing, and child-voice. Maps `advisory` -> `ADVISORY` (never gates),
`pass` -> `PASS`. Returns at most one `Finding` with `node_id=None`.
`fail_safe=Verdict.PASS`. Source: `LLM_ENGAGEMENT`, category: `"engagement"`, stage: 4.

### `_parse_verdict` helper

Shared by all four stages. Handles:
- `json.JSONDecodeError`: returns `fail_safe`
- Non-dict JSON: `isinstance` check raises `TypeError`, caught, returns `fail_safe`
- Unknown verdict string: returns `fail_safe`
- Known verdicts: maps `safe`/`pass` -> `PASS`, `flag` -> `FLAG`, `block` -> `BLOCK`,
  `advisory` -> `ADVISORY`

Type annotations: `parsed: object = json.loads(...)  # pyright: ignore[reportAny]` then
`cast("dict[str, object]", parsed)` after `isinstance` narrowing. This pattern matches
the existing codebase (`orchestrator.py` line 282).

---

## TDD Evidence

### RED phase

Running `uv run pytest tests/unit/test_moderation_stages.py -p no:randomly -v` before
creating `stages.py` produced:

```
ERROR collecting tests/unit/test_moderation_stages.py
ModuleNotFoundError: No module named 'cyo_adventure.moderation.stages'
1 error (0 tests collected)
```

### GREEN phase

After implementing `stages.py`:

```
9 passed in 0.26s
```

All 9 tests green: 3 safety (including source/category/node_id assertion), 2 readability,
2 coherence, 2 engagement.

---

## Quality Gates

| Check | Result |
|---|---|
| `uv run basedpyright src/cyo_adventure/moderation/stages.py` | 0 errors, 0 warnings, 0 notes |
| `uv run ruff check src/cyo_adventure/moderation/` | All checks passed |
| `uv run ruff format --check src/cyo_adventure/moderation/stages.py` | 1 file already formatted |
| `pre-commit run --all-files` | All hooks passed |

---

## Self-Review

**What went well:**
- The `_parse_verdict` helper is cleanly shared across all four stages with no duplication.
- BasedPyright strict 0/0 achieved using the established project pattern
  (`pyright: ignore[reportAny]` on the `json.loads` line, cast for the dict).
- Ruff required three fixes: `Sequence` moved under `TYPE_CHECKING` (TC003), error
  string extracted to variable (EM101), and `PLR0913` suppressed in `pyproject.toml`
  with a documented rationale comment (matching the existing orchestrator pattern).
- `run_readability_stage` has 5 keyword-only parameters, which is unavoidable given the
  brief mandates exact signatures. The pyproject.toml override is justified because all
  5 params are mandatory with no sensible defaults.

**Concerns / follow-up:**
- The `fail_safe=Verdict.PASS` on the safety `_parse_verdict` path is intentionally set
  to `FLAG` (not `PASS`) per the brief. The `#CRITICAL` marker documents this. Task 8's
  pipeline integration should validate that parse failures on Stage 1 surface for human
  review rather than silently passing through.
- Stage 3 and 4 render nodes as flat `[id] prose` lines. If a future node type includes
  choices or variable state, the whole-story prompt will not capture that; a richer
  rendering would be needed.
- No test covers the `_parse_verdict` fail-safe paths directly. The brief scoped tests
  to the stage functions; a future coverage pass could add a parse-failure test for Stage 1
  (confirming the hard gate defaults to FLAG, not PASS).
