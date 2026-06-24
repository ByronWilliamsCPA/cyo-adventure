---
title: "Skeleton-Fill Authoring Concept Test (Phase 1) Implementation Plan"
schema_type: planning
status: draft
owner: core-maintainer
component: Strategy
source: "docs/superpowers/specs/2026-06-23-modal-generation-tiers-design.md (Phase 1)"
purpose: "Phase 1 implementation plan for the skeleton-library generation design: a tested skeleton-fill code and skill foundation, proven end-to-end on three bands (3-5, 10-13, and the stateful 16+)."
tags:
  - planning
  - architecture
  - development
---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Each
> code task is test-first (TDD): write the failing test, run it red, implement minimally,
> run it green, commit. Steps use checkbox (`- [ ]`) syntax.

## Goal

Prove the core bet of the skeleton-library design: that a pre-authored story *skeleton*
(a structurally-valid graph with empty prose) can be filled with prose by a model and
imported into the existing story store as a schema-valid `Storybook`, end-to-end on one
reading band, with the code and skill foundation to extend to all six.

## Architecture

A skeleton is a single JSON file that is already a valid `Storybook` (the schema permits
empty/placeholder node bodies) whose non-ending node bodies hold a `<<FILL ...>>` directive.
A Claude Code authoring skill (running on the user's Opus subscription) replaces each
directive with prose, then the filled story is validated through the existing
`run_gate` and persisted through a new reusable `persist_storybook` helper. No new runtime
provider, no orchestrator change.

## Tech Stack

Python 3.12, Pydantic v2, async SQLAlchemy 2.x, pytest (`@pytest.mark.unit`), the existing
validator (`cyo_adventure.validator.gate.run_gate`) and ORM (`cyo_adventure.db.models`).

## Scope

In scope: skeleton format + loader, a reusable `persist_storybook` helper, a worker refactor
to use it, an `import_filled_story` validate-and-persist function, the `cyo-author` skill,
the three new age bands, and **three** hand-authored skeletons spanning the complexity range,
proven to load and (operationally) fill: **3-5** (lowest: Tier-1 no-death tree), **10-13**
(middle: Tier-1 branch-and-bottleneck with reconvergence), and **16+** (highest: Tier-2
stateful gamebook with variables/effects/conditions and Layer-2 validation). The 16+ band is
the architecture's real stress test and is mandatory for Phase 1.

Out of scope (later phases): Modal/OpenRouter runtime adapters; validator ending/decision
floors; the config-driven band table (this plan extends the hardcoded enum minimally);
series manifest/generation; the full six-band content. `lineage_id` (ratings spec) is NOT
added here but the persist helper is structured to accept it additively later.

## Forward-compatibility note

`persist_storybook` creates a `Storybook` row under a `family_id`. A future `lineage_id`
column (ratings/family-sharing spec) is purely additive: it becomes one more keyword
argument defaulting to `None`. Do not add it now.

---

### Task 1: Add three new age bands (3-5, 5-8, 16+)

The spec needs six bands; the schema's `AgeBand` enum has three. Add the new members and
their L1-7 budgets. `_check_budget` already skips bands absent from `_BUDGETS` (no crash),
but we add budgets so node-count is enforced.

**Files:**
- Modify: `src/cyo_adventure/storybook/models.py` (the `AgeBand` enum, lines 27-33)
- Modify: `src/cyo_adventure/validator/layer1.py` (`_BUDGETS`, lines 42-46)
- Test: `tests/unit/test_storybook_schema.py`, `tests/unit/test_layer1_validator.py`

- [ ] **Step 1: Verify whether the JSON Schema is generated or static**

The L1-1 check (`_check_schema`) validates against a JSON Schema. Confirm it is derived from
the Pydantic model (so extending `AgeBand` updates it automatically) rather than a static
file with a frozen `age_band` enum.

Run: `grep -rniE "model_json_schema|age_band.*enum|\"enum\".*8-11|schema.*\.json" src/cyo_adventure/storybook/ src/cyo_adventure/validator/`
Expected: the schema comes from `Storybook.model_json_schema()` (generated). If instead a
static `.json` schema file lists `"enum": ["8-11", "10-13", "13-16"]`, also add the three new
values to that file in this task.

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_storybook_schema.py
@pytest.mark.unit
@pytest.mark.parametrize("band", ["3-5", "5-8", "16+"])
def test_new_age_bands_are_valid(band: str) -> None:
    """The three added bands parse on a minimal Tier 1 story."""
    story = _minimal_tier1()
    story["metadata"]["age_band"] = band
    book = Storybook.model_validate(story)
    assert book.metadata.age_band == band
```

```python
# tests/unit/test_layer1_validator.py
@pytest.mark.unit
@pytest.mark.parametrize(
    ("band", "expected"),
    [("3-5", (8, 20, 4)), ("5-8", (12, 30, 6)), ("16+", (30, 60, 12))],
)
def test_new_bands_have_budgets(band: str, expected: tuple[int, int, int]) -> None:
    """band_budget returns the configured tuple for each new band."""
    from cyo_adventure.validator.layer1 import band_budget

    assert band_budget(band) == expected
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_storybook_schema.py::test_new_age_bands_are_valid tests/unit/test_layer1_validator.py::test_new_bands_have_budgets -v`
Expected: FAIL (`5-8` not a valid `AgeBand`; `band_budget("3-5")` is `None`).

- [ ] **Step 4: Implement**

```python
# src/cyo_adventure/storybook/models.py
class AgeBand(StrEnum):
    """The reading age band a story targets."""

    BAND_3_5 = "3-5"
    BAND_5_8 = "5-8"
    BAND_8_11 = "8-11"
    BAND_10_13 = "10-13"
    BAND_13_16 = "13-16"
    BAND_16_PLUS = "16+"
```

```python
# src/cyo_adventure/validator/layer1.py
_BUDGETS: dict[str, tuple[int, int, int]] = {
    "3-5": (8, 20, 4),
    "5-8": (12, 30, 6),
    "8-11": (15, 30, 6),
    "10-13": (25, 50, 8),
    "13-16": (30, 60, 10),
    "16+": (30, 60, 12),
}
```

- [ ] **Step 5: Run the new tests and the existing band-sensitive tests**

Run: `uv run pytest tests/unit/test_storybook_schema.py tests/unit/test_layer1_validator.py tests/unit/test_prompts.py -v`
Expected: PASS. `test_prompts` iterates `AgeBand` members against `band_budget`; the new
members now have budgets so it stays green.

- [ ] **Step 6: Commit**

```bash
git add src/cyo_adventure/storybook/models.py src/cyo_adventure/validator/layer1.py tests/unit/test_storybook_schema.py tests/unit/test_layer1_validator.py
git commit -S -m "feat(storybook): add 3-5, 5-8, and 16+ age bands with L1-7 budgets"
```

---

### Task 2: Reusable `persist_storybook` helper

Persistence is currently inline in `worker.py:271-318`. Extract a reusable helper so the
import path (Task 5) and the worker (Task 3) share one implementation.

**Files:**
- Create: `src/cyo_adventure/generation/persistence.py`
- Test: `tests/unit/test_persistence.py`

depends-on: Task 1 [completion]

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_persistence.py
import uuid

import pytest

from cyo_adventure.db.models import Storybook, StorybookVersion
from cyo_adventure.generation.persistence import persist_storybook


class _FakeSession:
    """Captures rows added; flush/commit are no-ops (mirrors test_worker_persistence)."""

    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, row: object) -> None:
        self.added.append(row)

    async def flush(self) -> None:  # noqa: D401
        return None


def _added(session: _FakeSession, kind: type) -> list[object]:
    return [r for r in session.added if isinstance(r, kind)]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_persist_creates_storybook_and_version() -> None:
    session = _FakeSession()
    family_id = uuid.uuid4()
    blob = {"id": "ignored", "title": "T", "nodes": []}

    story_id = await persist_storybook(
        session,
        story_id="s_demo",
        blob=blob,
        family_id=family_id,
        model="opus-4.8",
        prompt_version="skeleton-fill-v1",
    )

    assert story_id == "s_demo"
    books = _added(session, Storybook)
    versions = _added(session, StorybookVersion)
    assert len(books) == 1 and books[0].id == "s_demo"
    assert books[0].family_id == family_id
    assert len(versions) == 1
    assert versions[0].storybook_id == "s_demo"
    assert versions[0].version == 1
    # The blob id is stamped to match the row id.
    assert versions[0].blob["id"] == "s_demo"
    assert versions[0].model == "opus-4.8"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_persistence.py -v`
Expected: FAIL (`cyo_adventure.generation.persistence` does not exist).

- [ ] **Step 3: Implement**

```python
# src/cyo_adventure/generation/persistence.py
"""Reusable persistence for a validated Storybook blob.

Extracted from the generation worker so both the worker and the offline
authoring-import path create ``storybook`` and ``storybook_version`` rows
identically. The caller owns the transaction (this helper flushes but does not
commit), matching the worker's unit-of-work contract.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from cyo_adventure.db.models import Storybook, StorybookVersion

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_FIRST_VERSION = 1


async def persist_storybook(
    session: AsyncSession,
    *,
    story_id: str,
    blob: dict[str, object],
    family_id: uuid.UUID,
    created_by: uuid.UUID | None = None,
    model: str | None = None,
    prompt_version: str | None = None,
    validation_report: dict[str, object] | None = None,
    status: str = "draft",
    version: int = _FIRST_VERSION,
) -> str:
    """Create a ``Storybook`` row and its first ``StorybookVersion``.

    The blob's ``id`` is stamped to ``story_id`` so the stored content's id always
    matches its DB primary key. Flushes after each insert so the FK ordering holds;
    the caller commits.

    Args:
        session: An open async session; the caller owns the transaction.
        story_id: Primary key for the storybook row and stamped onto the blob.
        blob: The validated Storybook JSON as a dict.
        family_id: Owning family (the ownership boundary).
        created_by: Optional authoring user id.
        model: Optional model identifier recorded on the version.
        prompt_version: Optional prompt/skill version recorded on the version.
        validation_report: Optional gate report stored on the version.
        status: Storybook lifecycle status (default ``"draft"``).
        version: Version number (default 1).

    Returns:
        The ``story_id`` that was persisted.
    """
    # #CRITICAL: data-integrity: the stored blob's id must equal its DB row id, or
    # the reader resolves a story by a key absent from the blob.
    # #VERIFY: test_persist_creates_storybook_and_version asserts blob["id"] == story_id.
    stamped = {**blob, "id": story_id}

    storybook_row = Storybook(
        id=story_id,
        family_id=family_id,
        status=status,
        created_by=created_by,
    )
    session.add(storybook_row)
    await session.flush()  # ensure PK exists before the version FK

    version_row = StorybookVersion(
        storybook_id=story_id,
        version=version,
        blob=stamped,
        validation_report=validation_report,
        model=model,
        prompt_version=prompt_version,
    )
    session.add(version_row)
    await session.flush()

    return story_id
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_persistence.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cyo_adventure/generation/persistence.py tests/unit/test_persistence.py
git commit -S -m "feat(generation): add reusable persist_storybook helper"
```

---

### Task 3: Refactor the worker to use `persist_storybook`

Remove the duplicated inline persistence. The existing worker persistence tests are the
safety net: they must stay green unchanged.

**Files:**
- Modify: `src/cyo_adventure/generation/worker.py:271-318`
- Test (existing, must pass unchanged): `tests/unit/test_worker_persistence.py`

depends-on: Task 2 [output]

- [ ] **Step 1: Run the existing worker persistence tests to confirm the green baseline**

Run: `uv run pytest tests/unit/test_worker_persistence.py -v`
Expected: PASS (baseline before refactor).

- [ ] **Step 2: Replace the inline insert block with a call to the helper**

In `worker.py`, replace the `Storybook(...)` / `StorybookVersion(...)` creation block
(lines ~283-309, between `story_blob = {...}` and `job_row.storybook_id = story_id`) with:

```python
        await persist_storybook(
            session,
            story_id=story_id,
            blob=outcome.storybook,
            family_id=concept_row.family_id,
            created_by=concept_row.created_by,
            model=job_row.model,
            prompt_version=_PROMPT_VERSION,
            validation_report=dict(outcome.report),
        )

        job_row.storybook_id = story_id
        job_row.version = _FIRST_VERSION
```

Add the import at the top of `worker.py`:

```python
from cyo_adventure.generation.persistence import persist_storybook
```

Keep the existing `story_id = f"s_{job_id}"` line (id minting stays worker-specific). Remove
the now-unused local `story_blob` assignment if `persist_storybook` is given `outcome.storybook`
directly (the helper stamps the id).

- [ ] **Step 3: Run the existing tests to verify behavior is unchanged**

Run: `uv run pytest tests/unit/test_worker_persistence.py tests/unit/test_worker.py -v`
Expected: PASS, unchanged. The tests assert `blob["id"] == f"s_{job_id}"`, which the helper
preserves by stamping.

- [ ] **Step 4: Commit**

```bash
git add src/cyo_adventure/generation/worker.py
git commit -S -m "refactor(generation): worker persists via persist_storybook"
```

---

### Task 4: Skeleton format and `load_skeleton`

Define the `<<FILL ...>>` directive convention and a loader that asserts a skeleton is a
structurally-valid shell (passes the gate's blocking layers).

**Files:**
- Create: `src/cyo_adventure/generation/skeleton.py`
- Test: `tests/unit/test_skeleton.py`
- Create (test asset): `tests/fixtures/skeletons/demo_shell.json`

depends-on: Task 1 [completion]

- [ ] **Step 1: Add a minimal valid skeleton shell fixture**

Create `tests/fixtures/skeletons/demo_shell.json` (a structurally valid Tier 1 story whose
non-ending body holds a fill directive):

```json
{
  "schema_version": "1.0",
  "id": "sk_demo",
  "version": 1,
  "title": "Demo Skeleton",
  "metadata": {
    "age_band": "8-11",
    "reading_level": {"target": 3.0},
    "tier": 1,
    "estimated_minutes": 5,
    "ending_count": 1
  },
  "variables": [],
  "start_node": "start",
  "nodes": [
    {
      "id": "start",
      "body": "<<FILL role=setup words=120 beats='introduce the hero at the forest edge'>>",
      "is_ending": false,
      "choices": [{"id": "c1", "label": "Enter the forest", "target": "end"}]
    },
    {
      "id": "end",
      "body": "<<FILL role=ending words=80 beats='a warm, safe resolution'>>",
      "is_ending": true,
      "ending": {"id": "e_home", "type": "completion", "title": "Safely Home"}
    }
  ]
}
```

- [ ] **Step 2: Write the failing test**

```python
# tests/unit/test_skeleton.py
from pathlib import Path

import pytest

from cyo_adventure.generation.skeleton import has_unfilled_directives, load_skeleton

_SKELETON = Path("tests/fixtures/skeletons/demo_shell.json")


@pytest.mark.unit
def test_load_skeleton_accepts_valid_shell() -> None:
    """A structurally valid shell loads and is reported as unfilled."""
    data = load_skeleton(_SKELETON)
    assert data["id"] == "sk_demo"
    assert has_unfilled_directives(data) is True


@pytest.mark.unit
def test_load_skeleton_rejects_structurally_broken_shell(tmp_path: Path) -> None:
    """A shell whose choice targets a missing node is rejected (L1-2)."""
    import json

    broken = json.loads(_SKELETON.read_text())
    broken["nodes"][0]["choices"][0]["target"] = "does_not_exist"
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(broken))
    with pytest.raises(ValueError, match="structural"):
        load_skeleton(path)
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_skeleton.py -v`
Expected: FAIL (`cyo_adventure.generation.skeleton` does not exist).

- [ ] **Step 4: Implement**

```python
# src/cyo_adventure/generation/skeleton.py
"""Skeleton loading: a skeleton is a structurally-valid Storybook shell whose
non-ending node bodies carry a ``<<FILL ...>>`` directive to be replaced by prose.

The shell is validated through the existing gate's blocking layers (structure,
references, reachability, termination, budget) at load time, so a skeleton can
never introduce a structural defect; the fill step only writes prose.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from cyo_adventure.validator.gate import run_gate

if TYPE_CHECKING:
    from pathlib import Path

FILL_MARKER = "<<FILL"


def load_skeleton(path: Path) -> dict[str, object]:
    """Load a skeleton JSON file and assert it is a structurally-valid shell.

    Args:
        path: Path to the skeleton JSON.

    Returns:
        The decoded skeleton as a dict.

    Raises:
        ValueError: If the skeleton fails the gate's blocking (L1/L2) layers.
    """
    data: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    result = run_gate(data)
    if result.blocked:
        messages = "; ".join(f.message for f in result.report.errors)
        msg = f"skeleton {path} failed structural validation: {messages}"
        raise ValueError(msg)
    return data


def has_unfilled_directives(story: dict[str, object]) -> bool:
    """Return True if any node body still contains a ``<<FILL>>`` directive."""
    nodes = story.get("nodes")
    if not isinstance(nodes, list):
        return False
    return any(
        isinstance(n, dict)
        and isinstance(n.get("body"), str)
        and FILL_MARKER in n["body"]
        for n in nodes
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_skeleton.py -v`
Expected: PASS. (If the valid shell is unexpectedly blocked, inspect the printed errors:
an `ending.type` of `"completion"` is a free string and must pass; if a safety rule blocks
the directive text, simplify the `beats=` wording.)

- [ ] **Step 6: Commit**

```bash
git add src/cyo_adventure/generation/skeleton.py tests/unit/test_skeleton.py tests/fixtures/skeletons/demo_shell.json
git commit -S -m "feat(generation): add skeleton shell format and load_skeleton"
```

---

### Task 5: `import_filled_story` (validate then persist)

The bridge the authoring skill calls: take a filled story dict, run the gate, and persist if
it is not blocked.

**Files:**
- Create: `src/cyo_adventure/generation/import_story.py`
- Test: `tests/unit/test_import_story.py`

depends-on: Task 2 [output], Task 4 [completion]

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_import_story.py
import uuid

import pytest

from cyo_adventure.db.models import StorybookVersion
from cyo_adventure.generation.import_story import import_filled_story


class _FakeSession:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, row: object) -> None:
        self.added.append(row)

    async def flush(self) -> None:
        return None


def _filled_story() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "id": "s_filled",
        "version": 1,
        "title": "Filled",
        "metadata": {
            "age_band": "8-11",
            "reading_level": {"target": 3.0},
            "tier": 1,
            "estimated_minutes": 5,
            "ending_count": 1,
        },
        "variables": [],
        "start_node": "start",
        "nodes": [
            {
                "id": "start",
                "body": "You step onto the mossy path as a rabbit darts past.",
                "is_ending": False,
                "choices": [{"id": "c1", "label": "Follow it", "target": "end"}],
            },
            {
                "id": "end",
                "body": "The rabbit leads you to a sunny clearing. You feel happy.",
                "is_ending": True,
                "ending": {"id": "e_home", "type": "completion", "title": "Home"},
            },
        ],
    }


@pytest.mark.unit
@pytest.mark.asyncio
async def test_import_persists_a_valid_filled_story() -> None:
    session = _FakeSession()
    story_id = await import_filled_story(
        session, blob=_filled_story(), family_id=uuid.uuid4(), model="opus-4.8"
    )
    assert story_id == "s_filled"
    versions = [r for r in session.added if isinstance(r, StorybookVersion)]
    assert len(versions) == 1
    assert versions[0].blob["id"] == "s_filled"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_import_rejects_a_blocked_story() -> None:
    session = _FakeSession()
    broken = _filled_story()
    broken["nodes"][0]["choices"][0]["target"] = "missing"
    with pytest.raises(ValueError, match="blocked"):
        await import_filled_story(session, blob=broken, family_id=uuid.uuid4())
    assert session.added == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_import_story.py -v`
Expected: FAIL (module does not exist).

- [ ] **Step 3: Implement**

```python
# src/cyo_adventure/generation/import_story.py
"""Import an externally-authored (e.g. Claude Code authoring skill) filled story
into the story store, gated by the same validator used by the generation worker.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from cyo_adventure.generation.persistence import persist_storybook
from cyo_adventure.validator.gate import run_gate

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def import_filled_story(
    session: AsyncSession,
    *,
    blob: dict[str, object],
    family_id: uuid.UUID,
    created_by: uuid.UUID | None = None,
    model: str | None = None,
    prompt_version: str = "skeleton-fill-v1",
) -> str:
    """Validate a filled story and persist it if the gate does not block.

    Args:
        session: Open async session; caller owns the transaction.
        blob: The filled Storybook JSON as a dict.
        family_id: Owning family.
        created_by: Optional authoring user id.
        model: Optional model identifier (e.g. the fill model).
        prompt_version: Skill/prompt version recorded on the version.

    Returns:
        The persisted story id (the blob's ``id``).

    Raises:
        ValueError: If the validation gate blocks the story.
    """
    result = run_gate(blob)
    if result.blocked:
        messages = "; ".join(f.message for f in result.report.errors)
        msg = f"filled story blocked by validation gate: {messages}"
        raise ValueError(msg)

    story_id = blob.get("id")
    if not isinstance(story_id, str) or not story_id:
        msg = "filled story has no string id"
        raise ValueError(msg)

    return await persist_storybook(
        session,
        story_id=story_id,
        blob=blob,
        family_id=family_id,
        created_by=created_by,
        model=model,
        prompt_version=prompt_version,
        validation_report=dict(result.report.to_dict()),
    )
```

Note: confirm `result.report.to_dict()` is the report serializer used by the worker (the
worker stores `dict(outcome.report)`); match whichever form the worker uses so the stored
`validation_report` shape is consistent. If the worker uses `dict(outcome.report)` directly,
use the same here.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_import_story.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cyo_adventure/generation/import_story.py tests/unit/test_import_story.py
git commit -S -m "feat(generation): add import_filled_story validate-and-persist bridge"
```

---

### Task 6: The `cyo-author` Claude Code skill

A skill so a Claude Code session (on the user's Opus subscription) fills a skeleton's prose
and imports it. This is the offline authoring path; it produces a filled Storybook JSON.

**Files:**
- Create: `.claude/skills/cyo-author/SKILL.md`
- Create: `.claude/skills/cyo-author/reference/skeleton-format.md`

depends-on: Task 4 [completion], Task 5 [completion]

- [ ] **Step 1: Write the skill definition**

Create `.claude/skills/cyo-author/SKILL.md` with this content:

````markdown
---
name: cyo-author
description: Fill a CYO Adventure story skeleton with prose using the active model, then validate and import it. Use when authoring a story from a pre-authored skeleton (a structurally-valid Storybook shell whose node bodies hold <<FILL ...>> directives).
---

# CYO Author (skeleton fill)

## When to use
Invoke when given a skeleton file under `skeletons/<band>/<slug>.json` (or any
`<<FILL>>`-bearing Storybook shell) and asked to author the story.

## Procedure

1. **Load the skeleton.** Read the JSON. It is already a valid story graph; you only write
   prose. Never change `id`, `choices[].target`, `start_node`, node ids, `is_ending`,
   `ending`, `variables`, or `metadata`. Changing structure is a bug.

2. **Read the band rules.** From `metadata.age_band`, apply the per-band words/node target
   and fail-state policy (see `reference/skeleton-format.md`). Word targets: 3-5 ~75-100,
   5-8 ~100, 8-11 ~125-150, 10-13 ~175, 13-16 ~225, 16+ ~250 words per node.

3. **Fill each `<<FILL role=... words=... beats='...'>>` body** with prose that:
   - matches the band's word target and reading level (keep vocabulary/sentence length
     age-appropriate);
   - honors the `beats=` intent and the node's `role`;
   - sets up exactly the choices on that node (each `choice.label` is the action the prose
     should make available);
   - obeys the band fail-state policy (no death endings for 3-5 / 5-8).
   Replace the entire `<<FILL ...>>` string with the prose. Leave no `<<FILL` markers.

3b. **For Tier-2 (stateful) skeletons** (`metadata.tier` is 2): read the `variables`, each
   node's `on_enter` effects, and each choice's `effects`/`conditions`. The `beats=` directive
   names the relevant state; write prose consistent with the state reachable at that node (e.g.
   if `health` is low on the paths that reach a node, the diver feels the strain there). Never
   add, remove, or change a variable, effect, or condition; only write prose that fits the state
   the structure already defines.

4. **Keep the shared context stable for caching.** Fill nodes in one pass with the skeleton,
   band rules, and any world/character notes as a stable preamble; vary only the node being
   written. This maximizes prompt-cache reuse on the subscription.

5. **Write the filled story** to `out/<skeleton-slug>.filled.json`.

6. **Validate and import.** Run the import bridge:

   ```bash
   uv run python -m cyo_adventure.generation.import_cli out/<slug>.filled.json --family <family-uuid>
   ```

   If it reports a blocked gate, read the messages, fix the offending prose (never the
   structure), and re-run. If it reports an RL-13 reading-level warning, adjust vocabulary
   toward the band target; warnings do not block but should be addressed.

## Hard rules
- Structure is immutable; you only write prose.
- No `<<FILL` markers may remain.
- Respect the band fail-state policy (no death at 3-5 / 5-8).
````

- [ ] **Step 2: Write the format reference**

Create `.claude/skills/cyo-author/reference/skeleton-format.md` documenting: the `<<FILL>>`
directive grammar (`role`, `words`, `beats`); the six bands with words/node targets, reading
level (Lexile anchors), topology family, and fail-state policy from the design spec Section 3;
and the rule that `ending.type` of `completion` marks a series-advancing success ending.

- [ ] **Step 3: Verify the skill is discoverable**

Run: `ls .claude/skills/cyo-author/`
Expected: `SKILL.md` and `reference/skeleton-format.md` present, matching the repo's
`SKILL.md`-per-directory convention.

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/cyo-author/
git commit -S -m "feat(skills): add cyo-author skeleton-fill authoring skill"
```

---

### Task 7: Import CLI entry point

The skill calls a module entry point; provide it.

**Files:**
- Create: `src/cyo_adventure/generation/import_cli.py`
- Test: `tests/unit/test_import_cli.py`

depends-on: Task 5 [output]

- [ ] **Step 1: Write the failing test (argument parsing only; no DB)**

```python
# tests/unit/test_import_cli.py
import pytest

from cyo_adventure.generation.import_cli import build_arg_parser


@pytest.mark.unit
def test_arg_parser_requires_path_and_family() -> None:
    parser = build_arg_parser()
    args = parser.parse_args(["out/demo.filled.json", "--family", "abc"])
    assert args.path == "out/demo.filled.json"
    assert args.family == "abc"


@pytest.mark.unit
def test_arg_parser_errors_without_family() -> None:
    parser = build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["out/demo.filled.json"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_import_cli.py -v`
Expected: FAIL (module does not exist).

- [ ] **Step 3: Implement**

```python
# src/cyo_adventure/generation/import_cli.py
"""CLI: validate and import a filled story JSON into the store.

Usage:
    uv run python -m cyo_adventure.generation.import_cli <path> --family <family-uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from pathlib import Path

from cyo_adventure.core.database import get_session
from cyo_adventure.generation.import_story import import_filled_story


def build_arg_parser() -> argparse.ArgumentParser:
    """Build the import CLI argument parser."""
    parser = argparse.ArgumentParser(description="Import a filled story into the store.")
    parser.add_argument("path", help="Path to the filled story JSON.")
    parser.add_argument(
        "--family", required=True, help="Owning family UUID."
    )
    parser.add_argument("--model", default=None, help="Model id to record.")
    return parser


async def _run(path: str, family: str, model: str | None) -> str:
    blob: dict[str, object] = json.loads(Path(path).read_text(encoding="utf-8"))
    async with get_session() as session:
        story_id = await import_filled_story(
            session, blob=blob, family_id=uuid.UUID(family), model=model
        )
        await session.commit()
    return story_id


def main(argv: list[str] | None = None) -> int:
    """Entry point: parse args, import, print the resulting story id."""
    args = build_arg_parser().parse_args(argv)
    try:
        story_id = asyncio.run(_run(args.path, args.family, args.model))
    except ValueError as exc:
        print(f"import failed: {exc}", file=sys.stderr)  # noqa: T201
        return 1
    print(f"imported {story_id}")  # noqa: T201
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Note: confirm `get_session` is the async context manager exported by
`cyo_adventure.core.database` (the discovery and CLAUDE.md reference
`get_session()` as the query entry point). If its import path differs, adjust the import.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_import_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/cyo_adventure/generation/import_cli.py tests/unit/test_import_cli.py
git commit -S -m "feat(generation): add import_cli entry point for filled stories"
```

---

### Task 8: Author and prove three skeletons across the complexity range (operational)

Prove the loop on the extremes plus a midpoint: **3-5** (Tier-1 no-death tree), **10-13**
(Tier-1 branch-and-bottleneck), and **16+** (Tier-2 stateful gamebook). The 16+ skeleton is
the mandatory stress test: it exercises variables/effects/conditions and the Layer-2
state-space walk.

**Files:**
- Create: `skeletons/3-5/the-lost-mitten.json` (Tier 1)
- Create: `skeletons/10-13/the-clocktower-cipher.json` (Tier 1)
- Create: `skeletons/16+/the-sunken-signal.json` (Tier 2)

depends-on: Task 1 [completion], Task 4 [completion], Task 6 [completion], Task 7 [completion]

- [ ] **Step 1: Author the 3-5 skeleton (Tier 1, no-death tree)**

Create `skeletons/3-5/the-lost-mitten.json`: a valid Tier-1 shell, `age_band` `"3-5"`,
8-20 nodes, depth <= 4, a near-pure tree (Loop-and-Grow: wrong turns loop back, never end
the story). Every ending `type` is `completion` or a gentle `good`; **no `death` or scary
failure endings** (the 3-5 fail-state rule). Each non-ending body a `<<FILL role=... words=80
beats='...'>>` directive. `metadata.ending_count` equals the number of ending nodes.

- [ ] **Step 2: Author the 10-13 skeleton (Tier 1, branch-and-bottleneck)**

Create `skeletons/10-13/the-clocktower-cipher.json`: a valid Tier-1 shell, `age_band`
`"10-13"`, 25-50 nodes, depth <= 8, a **branch-and-bottleneck** shape (branches RECONVERGE
onto shared later nodes; aim for a few nodes with indegree 2). A mix of `completion` and
non-death `failure` endings is allowed at this band. `<<FILL>>` directives throughout;
`metadata.ending_count` accurate.

- [ ] **Step 3: Author the 16+ skeleton (Tier 2, stateful)**

Create `skeletons/16+/the-sunken-signal.json`: a valid **Tier 2** shell (`metadata.tier` 2),
`age_band` `"16+"`, 30-60 nodes, depth <= 12. It MUST declare `variables` and use node
`on_enter`/choice `effects` and `conditions` so the Layer-2 walk is meaningful. Model the
variable/effect/condition shape on an existing valid Tier-2 fixture:

Run: `grep -rl '"variables": \[\s*{' tests/fixtures/storybook/valid/`
Expected: at least one valid Tier-2 fixture; open it and copy the `variables` / `on_enter` /
`conditions` / `effects` shapes.

Requirements specific to Tier 2:
- Declare 1-2 variables (e.g. a bool `has_key`, an int `health` with `min`/`max`).
- Some choices set/inc/dec a variable (`effects`); some choices or nodes are gated by a
  `condition` on a variable.
- No **stateful dead-end** (L2-9): every reachable configuration can still reach an ending.
  This is the part most likely to fail; trace it before committing.
- Lethal/resource endings are allowed at 16+ (e.g. `health` reaching 0 -> a `death` ending).
- `<<FILL>>` directives include the relevant state in `beats`, e.g.
  `<<FILL role=climax words=240 beats='the diver is out of air (health low); the signal
  finally answers'>>`.

- [ ] **Step 4: Verify all three load as structurally-valid shells**

Run:
```bash
for f in skeletons/3-5/the-lost-mitten.json skeletons/10-13/the-clocktower-cipher.json skeletons/16+/the-sunken-signal.json; do
  uv run python -c "import sys; from pathlib import Path; from cyo_adventure.generation.skeleton import load_skeleton, has_unfilled_directives; d=load_skeleton(Path(sys.argv[1])); print(sys.argv[1], 'nodes', len(d['nodes']), 'tier', d['metadata']['tier'], 'unfilled', has_unfilled_directives(d))" "$f";
done
```
Expected: three lines, each with no exception and `unfilled True`. The 16+ line shows
`tier 2`.
Abort if: any raises `ValueError`. For the 16+ skeleton a Layer-2 finding (L2-9 stateful
dead-end, L2-10 loop escape) means a reachable state cannot reach an ending; fix the state
logic or add an escape edge before proceeding.

- [ ] **Step 5: Commit the three skeletons**

```bash
git add skeletons/3-5/ skeletons/10-13/ skeletons/16+/
git commit -S -m "feat(skeletons): add 3-5, 10-13, and 16+ stateful demo skeletons"
```

- [ ] **Step 6: Fill each via the authoring skill (operational; Opus in Claude Code)**

Invoke the `cyo-author` skill on each of the three skeletons in turn. For the 16+ Tier-2
skeleton, the skill must write prose consistent with the reachable state at each node (it is
told the state in the `beats` and can read the variables/effects). Each run writes
`out/<slug>.filled.json`.
Expected: every `<<FILL>>` replaced; no markers remain in any of the three.

- [ ] **Step 7: Validate each filled story passes the gate (no DB required)**

Run (per filled file):
```bash
uv run python -c "import json,sys; from cyo_adventure.validator.gate import run_gate; r=run_gate(json.load(open(sys.argv[1]))); print(sys.argv[1], 'blocked', r.blocked); [print(' ', f.rule_id, f.message) for f in r.report.findings]" out/the-sunken-signal.filled.json
```
Expected: `blocked False` for all three. RL-13 reading-level findings are warnings; if a
band's Flesch-Kincaid grade is far from target (3-5 lowest, 16+ highest), revise prose and
re-run.
Abort if: `blocked True` (fix prose only, never structure). For the 16+ story, a Layer-2
block means the prose changed structure (it must not); re-fill, do not edit the graph.

- [ ] **Step 8: (Optional, requires a running DB and a seed family) Import each to the store**

Seed a family/user in the dev database (or reuse one), then run the import CLI for each
filled file:
```bash
uv run python -m cyo_adventure.generation.import_cli out/the-sunken-signal.filled.json --family <family-uuid> --model opus-4.8
```
Expected: prints `imported s_...` for each. Confirms the end-to-end save path across Tier 1
and Tier 2.

---

### Task 9: Repeat-procedure note for the remaining three bands (operational)

Phase 1's acceptance is "at least one sample per band." Tasks 1-8 deliver the machinery and
three bands end-to-end (3-5, 10-13, 16+, the extremes plus a midpoint). For each remaining
band (5-8, 8-11, 13-16):

- [ ] Author `skeletons/<band>/<slug>.json` to the band's topology, budget, and fail-state
      policy (Section 3 of the spec), verify it loads (Task 8 Step 4), commit.
- [ ] Fill via the `cyo-author` skill, validate (Task 8 Step 7), and (optionally) import.
- [ ] Record, per band, whether the filled story cleared the gate and how close the
      Flesch-Kincaid grade landed to the band target. This per-band record is the input to the
      later model-alignment calibration.

This task is intentionally a procedure, not enumerated code: the skeletons are content and
the fills are operational. Do not block Phase 1 completion on automating it.

---

## Self-Review

Run after the tasks are drafted; this is the author's checklist.

**Spec coverage (clause-level):**
- "Authoring skill" -> Task 6. "Skeleton + filled sample per band (all six)" -> Tasks 8
  (three bands proven: lowest 3-5, middle 10-13, highest Tier-2 16+) + 9 (procedure for the
  remaining three) + Task 1 (the six bands exist). "Stateful approach proven" -> Task 8's 16+
  Tier-2 skeleton exercises variables/effects/conditions and Layer-2. "Import into the
  Storybook/StorybookVersion store" -> Tasks 2, 5, 7, 8 Step 8. "Near-zero app code" -> only
  small new modules + a worker refactor; no runtime provider.
- Gap acknowledged and intentional: the remaining three fills are operational (Task 9), not
  code.

**Placeholder scan:** no TBD/TODO; every code step shows complete code. The two "Note:"
verifications (report serializer form in Task 5; `get_session` import in Task 7) are explicit
confirmations against existing code, not placeholders.

**Type consistency:** `persist_storybook(session, *, story_id, blob, family_id, ...)` is
defined in Task 2 and called identically in Task 3 (worker) and Task 5 (import). `run_gate`
returns a result with `.blocked` and `.report` (`.report.errors`, `.report.findings`,
`.report.to_dict()`), matching the discovery report.

**Shell command environment:** all `uv run` commands run from the worktree root; the inline
`python -c` snippets import installed package modules (no `PYTHONPATH` needed under `uv run`).

**Test-helper consistency:** the new tests define a local minimal `_FakeSession` mirroring the
pattern in `tests/unit/test_worker_persistence.py`; this is intentional (the helper only needs
`add` + async `flush`). If a shared async-session fixture exists in `tests/unit/conftest.py`,
prefer it.

**pytest marks:** every test uses `@pytest.mark.unit`; async tests add `@pytest.mark.asyncio`,
matching `tests/unit/test_worker_persistence.py`.

## Execution Handoff

This plan covers Phase 1 only. Phases 2-7 (skeleton store, validator floors, ModalProvider,
endpoint deploys, procedural generator, series) get their own plans from the spec.
