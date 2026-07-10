---
schema_type: planning
title: "WS-G PR 1 Implementation Plan: Series Metadata and Validator Gate"
description: "Task-level implementation plan for WS-G PR 1: embed the document Series block at
  generation, relax SR-4 to allow open-ended chains, and wire validate_series into release
  approval with the grandfather rule. Backend only, no migration, no client regen."
tags:
  - planning
  - series
status: active
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Give an implementer with zero session context everything needed to build WS-G PR 1
  task-by-task: exact files, anchors, complete code, test commands, and commit points."
component: Generation
source: "docs/planning/ws-g-series-chaining-spec.md (ratified G1-G4); codebase discovery
  2026-07-09 against feat/ws-g-series-chaining a9b1b06 (= origin/main post WS-C PR2)."
---

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

## Goal

Every generated series book's stored blob carries a populated `metadata.series` block; the SR
validator accepts open-ended chains; release approval blocks on SR errors for fully WS-G chains
and grandfather-skips legacy ones.

## Architecture

Three seams, all existing: `generation/series_link.py` gains `embed_series_block` (called by the
worker after `link_series_position` AND after `run_moderation_pipeline` returns, same
transaction: moderation's soft-repair path can reassign the blob wholesale, and a repaired blob
predates the embedded block, so embedding first would let repair silently discard it; see the
`worker.py::_persist_and_moderate` RAD marker on the embed call for the full rationale);
`validator/series.py::_check_final_flags` is relaxed to error only on a non-top final book;
`publishing/service.py::approve` gains a chain-so-far `validate_series` gate with the grandfather
rule. No migration (Alembic head stays `228c68e8f1e7`), no OpenAPI change, no new event type.

## Tech Stack

Python 3.12, async SQLAlchemy 2.x, Pydantic v2, pytest (+ testcontainers Postgres for
integration), ruff, basedpyright strict. All commands run from the worktree root
`/home/byron/dev/CYO_Adventure/.worktrees/ws-g` with `uv run`.

## Key facts an implementer must not re-derive

- The worker persists first, then links: `generation/worker.py::_persist_and_moderate` calls
  `persist_storybook` (~line 500) then `link_series_position` (~line 519) then
  `run_moderation_pipeline`. `assign_book_index` (`generation/series_link.py:60`) requires the
  `Storybook` row to exist, so the embed step MUST come after linkage, not before persist.
- JSONB change tracking: `StorybookVersion.blob` must be REASSIGNED to a new dict; in-place
  mutation is invisible to the session and silently skips the UPDATE.
- The document model and the ORM share the name `Storybook`. The document lives at
  `cyo_adventure.storybook.models` (alias it `StorybookDoc` in publishing code); the ORM lives at
  `cyo_adventure.db.models`. Same for `Series` (embedded Pydantic block vs ORM row).
- Embedded `Series` Pydantic fields (`storybook/models.py:180`): `series_id: str`,
  `book_index: int (ge=1)`, `series_entry_node: str | None`, `is_final: bool`,
  `carries_state: bool = True`. `extra="forbid"`.
- `validate_series` (`validator/series.py:43`) takes `Sequence[Storybook]` (document models) and
  returns a `ValidationReport` with `.ok` and `.errors` (findings with `.rule_id`, `.message`).
- Blob byte budget: `generation/persistence.py::_check_byte_budget(payload, field=...)` guards
  JSONB size; Task 2 adds a public wrapper rather than importing the private name elsewhere
  (ruff SLF).
- `approve()` (`publishing/service.py:111`) already gates on `moderation_report is not None` and
  raises `BusinessLogicError(msg, rule=...)`; the series gate follows the same pattern. The
  `storybook` row arrives locked (SELECT ... FOR UPDATE) by both callers.
- Test conventions: unit tests in `tests/unit/`, integration (real Postgres via fixtures in
  `tests/conftest.py`) in `tests/integration/`. `tests/conftest.py::make_clean_moderation_report`
  builds a passing moderation report. `tests/unit/test_series.py::_book` (line 19) builds a
  minimal valid document with an optional series block; reuse its shape when building blobs.

---

### Task 0: Verify base state and gates

- [ ] **Step 1: Confirm branch and head**

Run: `git -C /home/byron/dev/CYO_Adventure/.worktrees/ws-g log --oneline -1 && git branch --show-current`
Expected: head `a9b1b06` (or a descendant containing spec commits) on `feat/ws-g-series-chaining`
Abort if: on `main` or the worktree has unrelated uncommitted changes (`git status --short`).

- [ ] **Step 2: Confirm the suite is green before touching anything**

Run: `uv run pytest -q 2>&1 | tail -3`
Expected: all tests pass (WS-C PR2 baseline was ~2084 passing).
Abort if: pre-existing failures; report them instead of building on a red base.

---

### Task 1: Relax SR-4 to allow open-ended chains

**Files:**

- Modify: `src/cyo_adventure/validator/series.py:173-190` (`_check_final_flags`)
- Test: `tests/unit/test_series.py`

- [ ] **Step 1: Survey existing SR-4 expectations**

Run: `grep -n "SR-4\|is_final" tests/unit/test_series.py`
Expected: `test_wrong_final_flag_is_sr4` (non-top book marked final; stays valid under the new
semantics because book 1 of 2 is non-top) plus possibly a test asserting an all-`False` chain
errors. Note every hit; any test that asserts SR-4 fires for a chain whose only "defect" is the
top book not being final encodes the OLD semantics and will be rewritten in Step 4.

- [ ] **Step 2: Write the new failing test**

Add to `tests/unit/test_series.py` (next to the other SR-4 tests):

```python
def test_open_chain_all_not_final_is_valid():
    # WS-G G4: an open-ended chain (no book marked final) is a first-class
    # state; only a NON-top book marked final is an SR-4 error.
    books = [
        _book(book_index=1),
        _book(book_index=2, entry="n0"),
    ]
    report = validate_series(books)
    assert not any(f.rule_id == "SR-4" for f in report.errors)


def test_closed_chain_top_final_is_valid():
    books = [
        _book(book_index=1),
        _book(book_index=2, entry="n0", is_final=True),
    ]
    report = validate_series(books)
    assert not any(f.rule_id == "SR-4" for f in report.errors)
```

- [ ] **Step 3: Run to verify the open-chain test fails**

Run: `uv run pytest tests/unit/test_series.py -q -k "final"`
Expected: `test_open_chain_all_not_final_is_valid` FAILS (current code demands the top book be
final); `test_closed_chain_top_final_is_valid` passes.

- [ ] **Step 4: Implement the relaxation**

Replace `_check_final_flags` in `src/cyo_adventure/validator/series.py` with:

```python
def _check_final_flags(series_books: list[_Book], report: ValidationReport) -> None:
    """SR-4: a book below the highest index must not be ``is_final``.

    The top-index book MAY be final (closed series) or not (open-ended chain
    a future continuation extends). ADR-011 section 8 and the WS-G spec (G4)
    make open chains first-class; v1 generation always writes is_final=False.
    """
    last = len(series_books)
    for book, series in series_books:
        if series.is_final and series.book_index != last:
            report.add(
                ValidationFinding(
                    rule_id="SR-4",
                    severity=Severity.ERROR,
                    story_id=book.id,
                    message=(
                        f"SR-4 series: book {series.book_index} '{book.id}' is "
                        f"marked is_final but is not the last of {last} books"
                    ),
                )
            )
```

If Step 1 found tests encoding the old strictness (top book must be final), rewrite each to
assert the new behavior (no SR-4 for all-`False`), keeping the non-top-final error case intact.

- [ ] **Step 5: Run the module's tests**

Run: `uv run pytest tests/unit/test_series.py -q`
Expected: PASS, zero failures.

- [ ] **Step 6: Commit**

```bash
git add src/cyo_adventure/validator/series.py tests/unit/test_series.py
git commit -S -m "feat(validator): relax SR-4 so open-ended series chains validate (WS-G G4)"
```

---

### Task 2: Embed the series block at generation

`depends-on: Task 1 [completion]` (independent code paths; ordered only for a clean history).

**Files:**

- Modify: `src/cyo_adventure/generation/persistence.py` (public byte-budget wrapper)
- Modify: `src/cyo_adventure/generation/series_link.py` (new `embed_series_block`)
- Modify: `src/cyo_adventure/generation/worker.py:519` area (wire the call)
- Test: `tests/integration/test_series_link.py`

- [ ] **Step 1: Survey the integration test file's helpers**

Run: `grep -n "^def \|^async def \|fixture\|_seed\|_make" tests/integration/test_series_link.py | head -20`
Expected: the file's existing seeding helpers for Family/Series/StoryRequest/Concept/Storybook.
Reuse them in Step 3's tests; only fall back to the inline seeding shown there if no helper
covers the shape.

- [ ] **Step 2: Add the public byte-budget wrapper**

In `src/cyo_adventure/generation/persistence.py`, below `_check_byte_budget`:

```python
def ensure_blob_within_budget(blob: dict[str, object]) -> None:
    """Guard a post-persist blob update against the JSONB byte budget.

    Public wrapper so callers outside this module (WS-G series embed) do not
    reach into the private ``_check_byte_budget``.

    Raises:
        ValidationError: If the blob serializes past the budget.
    """
    _check_byte_budget(blob, field="blob")
```

- [ ] **Step 3: Write the failing integration tests**

Add to `tests/integration/test_series_link.py` (adapting seeding to the helpers found in
Step 1; the flow and assertions below are the contract). The document blob must be
schema-shaped enough to carry `start_node` and a `metadata` dict; mirror the minimal blob the
file already persists, adding `"start_node": "n0"` and a `"metadata": {}` key if absent.

```python
async def test_embed_series_block_writes_metadata(session: AsyncSession) -> None:
    # Seed: family, series (carries_state=False to prove copy-through),
    # request with series_id, concept, then persist + link as the worker does.
    ...  # seed via the file's existing helpers; capture story_id, version=1
    await link_series_position(session, story_id=story_id, concept_id=concept_id)
    await embed_series_block(session, story_id=story_id, version=1)
    await session.commit()

    row = await session.get(StorybookVersion, (story_id, 1))
    assert row is not None
    meta = row.blob["metadata"]
    assert isinstance(meta, dict)
    block = meta["series"]
    assert isinstance(block, dict)
    storybook = await session.get(Storybook, story_id)
    assert storybook is not None
    assert block["series_id"] == str(storybook.series_id)
    assert block["book_index"] == storybook.book_index
    assert block["series_entry_node"] == row.blob["start_node"]
    assert block["is_final"] is False
    assert block["carries_state"] is False  # copied from the series row


async def test_embed_series_block_noop_for_non_series(session: AsyncSession) -> None:
    ...  # seed a storybook persisted with no series linkage (existing helper)
    await embed_series_block(session, story_id=story_id, version=1)
    row = await session.get(StorybookVersion, (story_id, 1))
    assert row is not None
    assert "series" not in row.blob.get("metadata", {})
```

The `...` seeding lines are the ONLY part left to the implementer, precisely because the file's
existing helpers must be reused rather than duplicated (Step 1); every assertion is complete.
The file already contains at least one test that drives `link_series_position` end-to-end
(seeding family, series, request, concept, and a persisted storybook); copy that test's seed
flow verbatim as the `...` body, changing only the series row's `carries_state` to `False` for
the first test.

- [ ] **Step 4: Run to verify they fail**

Run: `uv run pytest tests/integration/test_series_link.py -q -k "embed"`
Expected: FAIL with `ImportError`/`NameError` (no `embed_series_block` yet).

- [ ] **Step 5: Implement `embed_series_block`**

In `src/cyo_adventure/generation/series_link.py`, extend the imports and add:

```python
from cyo_adventure.db.models import Series as SeriesRow
from cyo_adventure.db.models import StorybookVersion
from cyo_adventure.generation.persistence import ensure_blob_within_budget
from cyo_adventure.storybook.models import Series as SeriesBlock
```

(keep the existing `Storybook`/`StoryRequest` imports as they are), then:

```python
async def embed_series_block(
    session: AsyncSession, *, story_id: str, version: int
) -> None:
    """Write the embedded document ``Series`` block for a linked series book.

    WS-G G2: ``series_entry_node`` is the document's own ``start_node``;
    ``is_final`` is always False in v1 (open chains are valid post-SR-4
    relaxation); ``carries_state`` copies the series row. No-op for a book
    with no series linkage. Same transaction as linkage; the caller commits.

    Raises:
        ValueError: If the series row or version row is missing (FK-guaranteed
            in the worker flow; defensive for direct callers).
    """
    storybook = await session.get(Storybook, story_id)
    if (
        storybook is None
        or storybook.series_id is None
        or storybook.book_index is None
    ):
        return
    series_row = await session.get(SeriesRow, storybook.series_id)
    if series_row is None:
        msg = f"series '{storybook.series_id}' not found for '{story_id}'"
        raise ValueError(msg)
    version_row = await session.get(StorybookVersion, (story_id, version))
    if version_row is None:
        msg = f"version {version} of storybook '{story_id}' not found"
        raise ValueError(msg)
    blob = dict(version_row.blob)
    block = SeriesBlock(
        series_id=str(storybook.series_id),
        book_index=storybook.book_index,
        series_entry_node=str(blob["start_node"]),
        is_final=False,
        carries_state=series_row.carries_state,
    )
    raw_meta = blob.get("metadata")
    metadata = dict(raw_meta) if isinstance(raw_meta, dict) else {}
    metadata["series"] = block.model_dump()
    blob["metadata"] = metadata
    ensure_blob_within_budget(blob)
    # #ASSUME: data-integrity: JSONB change detection requires reassigning
    # version_row.blob to a new dict; in-place mutation is invisible to the
    # session and would silently skip the UPDATE.
    # #VERIFY: test_embed_series_block_writes_metadata re-reads after commit.
    version_row.blob = blob
    await session.flush()
```

- [ ] **Step 6: Run the embed tests**

Run: `uv run pytest tests/integration/test_series_link.py -q`
Expected: PASS (new tests plus the file's pre-existing linkage/concurrency tests).

- [ ] **Step 7: Wire the worker**

In `src/cyo_adventure/generation/worker.py`, extend the `series_link` import to include
`embed_series_block`, and add the call *after* the existing
`await run_moderation_pipeline(...)` call inside `_persist_and_moderate`'s try block (not after
`link_series_position`):

```python
    try:
        await run_moderation_pipeline(...)
        await embed_series_block(session, story_id=story_id, version=_FIRST_VERSION)
    except Exception as exc:
        ...
```

This runs AFTER `run_moderation_pipeline` returns, not before: moderation's soft-repair path
(`moderation/pipeline.py`'s `attempt_repair`) can reassign `version_row.blob` to an LLM-revised
blob whose prompt preserves node ids/structure but says nothing about `metadata.series`, and
`StoryMetadata.series` is optional, so a repaired blob is schema-valid with the series block
silently dropped. Embedding after moderation reads the post-repair blob (when a repair happened)
and stamps the authoritative linkage-derived block last, inside the worker's single unit of work.
Placing the call inside the same `try` as `run_moderation_pipeline`, right after it, means a
moderation failure still takes the existing rollback path unchanged (the embed call is simply
never reached), and an embed failure (for example a malformed blob missing `start_node`) is
caught by the same except and rolled back identically.

- [ ] **Step 8: Assert the wiring in the worker's own test**

Run: `grep -rln "link_series_position\|series_position_assigned" tests/ --include="*.py"`
Expected: the worker-flow test file(s) that already drive a series-linked generation job. In the
test that asserts `book_index` was assigned via the worker path, add:

```python
    version_row = await session.get(StorybookVersion, (story_id, 1))
    assert version_row is not None
    meta = version_row.blob["metadata"]
    assert isinstance(meta, dict)
    assert isinstance(meta.get("series"), dict)
```

If no worker-path series test exists (only direct `link_series_position` calls), state that in
the task report; the direct-call integration tests from Step 3 plus this wiring line are then
the coverage, and PR 2's e2e closes the gap. Note the spec's "both skeleton-fill and fresh
paths" testing clause is satisfied structurally: both branches converge on the single
`_persist_and_moderate` before the embed call, so one wiring assertion covers both.

- [ ] **Step 9: Run the affected suites**

Run: `uv run pytest tests/integration/test_series_link.py tests/unit/test_series.py -q && uv run pytest tests/ -q -k "worker" 2>&1 | tail -3`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add src/cyo_adventure/generation/persistence.py src/cyo_adventure/generation/series_link.py src/cyo_adventure/generation/worker.py tests/integration/test_series_link.py
git commit -S -m "feat(generation): embed document Series block at persist for series books (WS-G G2)"
```

(Include the worker-test file in `git add` if Step 8 modified one.)

---

### Task 3: Chain-so-far validator gate at approval

`depends-on: Task 1 [output]` (gate tests build open chains that only validate post-relaxation).
`depends-on: Task 2 [completion]` (tests construct blocks directly; no code dependency).

**Files:**

- Modify: `src/cyo_adventure/publishing/service.py` (gate + helper in `approve`, line 111 area)
- Create: `tests/integration/test_series_approval_gate.py`

- [ ] **Step 1: Survey shared builders before writing new ones**

Run: `ls tests/_series_utils.py tests/integration/_series_utils.py 2>/dev/null; grep -rn "def _book\|def make_series\|def _series" tests/ --include="*.py" | head`
Expected: locations of any shared series/document builders. If a shared builder producing a
schema-valid document exists, import it; otherwise define the local `_doc` helper below (a
trimmed copy of `tests/unit/test_series.py::_book`, which is test-module-local and must not be
imported across test modules).

- [ ] **Step 2: Write the failing integration tests**

Create `tests/integration/test_series_approval_gate.py`:

```python
"""WS-G G4: chain-so-far series validation at release approval."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from cyo_adventure.core.exceptions import BusinessLogicError
from cyo_adventure.db.models import Family, Series, Storybook, StorybookVersion, User
from cyo_adventure.publishing.service import approve
from cyo_adventure.storybook.models import (
    AgeBand,
    Choice,
    Ending,
    EndingKind,
    Node,
    ReadingLevel,
    Series as SeriesBlock,
    StoryMetadata,
    Storybook as StorybookDoc,
    Topology,
    Valence,
)
# make_clean_moderation_report: grep how existing integration tests reference
# it (fixture vs direct import) and copy that idiom verbatim; the direct-import
# form is `from tests.conftest import make_clean_moderation_report` ONLY if
# other tests already do that.


def _doc(
    story_id: str,
    *,
    series_id: str,
    book_index: int,
    entry: str | None = None,
    win: bool = True,
    with_series: bool = True,
) -> dict[str, object]:
    """A minimal schema-valid document blob, optionally series-tagged."""
    kind = EndingKind.SUCCESS if win else EndingKind.SETBACK
    valence = Valence.POSITIVE if win else Valence.NEGATIVE
    doc = StorybookDoc(
        id=story_id,
        version=1,
        title="T",
        start_node="n0",
        nodes=[
            Node(id="n0", body="go", choices=[Choice(id="c1", label="x", target="n_end")]),
            Node(
                id="n_end",
                body="done",
                is_ending=True,
                ending=Ending(id="e1", valence=valence, kind=kind, title="End"),
            ),
        ],
        metadata=StoryMetadata(
            age_band=AgeBand.BAND_10_13,
            reading_level=ReadingLevel(target=2.0),
            tier=2,
            estimated_minutes=5,
            ending_count=1,
            topology=Topology.GAUNTLET,
            series=SeriesBlock(
                series_id=series_id,
                book_index=book_index,
                series_entry_node=entry,
                is_final=False,
                carries_state=True,
            )
            if with_series
            else None,
        ),
    )
    return doc.model_dump(mode="json")


async def _seed_series(session: AsyncSession) -> tuple[Series, uuid.UUID]:
    fam = Family(name="Fam")
    session.add(fam)
    await session.flush()
    admin = User(family_id=fam.id, role="guardian", authn_subject="g")
    session.add(admin)
    await session.flush()
    series = Series(
        family_id=fam.id,
        title="Camp",
        age_band="10-13",
        carries_state=True,
    )
    session.add(series)
    await session.flush()
    return series, admin.id


async def _seed_book(
    session: AsyncSession,
    series: Series,
    *,
    story_id: str,
    book_index: int,
    status: str,
    blob: dict[str, object],
) -> Storybook:
    book = Storybook(
        id=story_id,
        family_id=series.family_id,
        status=status,
        current_published_version=1 if status == "published" else None,
        series_id=series.id,
        book_index=book_index,
    )
    session.add(book)
    await session.flush()
    session.add(
        StorybookVersion(
            storybook_id=story_id,
            version=1,
            blob=blob,
            moderation_report=make_clean_moderation_report(),
        )
    )
    await session.flush()
    return book


@pytest.mark.anyio
async def test_valid_chain_approves(session: AsyncSession, principal_admin) -> None:
    series, _ = await _seed_series(session)
    sid = str(series.id)
    await _seed_book(
        session, series, story_id="b1", book_index=1, status="published",
        blob=_doc("b1", series_id=sid, book_index=1),
    )
    book2 = await _seed_book(
        session, series, story_id="b2", book_index=2, status="in_review",
        blob=_doc("b2", series_id=sid, book_index=2, entry="n0"),
    )
    row = await approve(session, principal_admin, book2, 1)
    assert row.approved_by is not None
    assert book2.status == "published"


@pytest.mark.anyio
async def test_sr_violation_blocks_approval(session: AsyncSession, principal_admin) -> None:
    # Book 1 published with NO satisfying ending: SR-5 fires for the chain.
    series, _ = await _seed_series(session)
    sid = str(series.id)
    await _seed_book(
        session, series, story_id="b1", book_index=1, status="published",
        blob=_doc("b1", series_id=sid, book_index=1, win=False),
    )
    book2 = await _seed_book(
        session, series, story_id="b2", book_index=2, status="in_review",
        blob=_doc("b2", series_id=sid, book_index=2, entry="n0"),
    )
    with pytest.raises(BusinessLogicError, match="SR-5"):
        await approve(session, principal_admin, book2, 1)
    assert book2.status == "in_review"  # transition never happened


@pytest.mark.anyio
async def test_out_of_order_approval_blocked_sr2(
    session: AsyncSession, principal_admin
) -> None:
    # Book 1 exists but is not yet published; approving book 2 sees a chain
    # of {2} which is not contiguous from 1.
    series, _ = await _seed_series(session)
    sid = str(series.id)
    await _seed_book(
        session, series, story_id="b1", book_index=1, status="in_review",
        blob=_doc("b1", series_id=sid, book_index=1),
    )
    book2 = await _seed_book(
        session, series, story_id="b2", book_index=2, status="in_review",
        blob=_doc("b2", series_id=sid, book_index=2, entry="n0"),
    )
    with pytest.raises(BusinessLogicError, match="SR-2"):
        await approve(session, principal_admin, book2, 1)


@pytest.mark.anyio
async def test_legacy_chain_is_grandfathered(
    session: AsyncSession, principal_admin
) -> None:
    # Book 1 predates WS-G: schema-valid blob, no series block. The gate is
    # skipped for the whole chain and approval proceeds.
    series, _ = await _seed_series(session)
    sid = str(series.id)
    await _seed_book(
        session, series, story_id="b1", book_index=1, status="published",
        blob=_doc("b1", series_id=sid, book_index=1, with_series=False),
    )
    book2 = await _seed_book(
        session, series, story_id="b2", book_index=2, status="in_review",
        blob=_doc("b2", series_id=sid, book_index=2, entry="n0"),
    )
    row = await approve(session, principal_admin, book2, 1)
    assert row.approved_by is not None


@pytest.mark.anyio
async def test_self_legacy_book_is_grandfathered(
    session: AsyncSession, principal_admin
) -> None:
    # The book under approval itself lacks the block (generated pre-deploy).
    series, _ = await _seed_series(session)
    sid = str(series.id)
    book1 = await _seed_book(
        session, series, story_id="b1", book_index=1, status="in_review",
        blob=_doc("b1", series_id=sid, book_index=1, with_series=False),
    )
    row = await approve(session, principal_admin, book1, 1)
    assert row.approved_by is not None
```

Fixture note: `principal_admin` stands for the file-appropriate way to obtain an approving
`Principal`. Check `tests/integration/test_publishing_service.py` (its tests call
`approve(session, principal, ...)`) and reuse EXACTLY its principal construction and its
session/anyio fixture idioms, including whether `@pytest.mark.anyio` is needed; adjust the
signatures above to match that file's conventions verbatim.

- [ ] **Step 3: Run to verify the new gate tests fail**

Run: `uv run pytest tests/integration/test_series_approval_gate.py -q`
Expected: `test_valid_chain_approves` and the two grandfather tests PASS already (no gate means
approval succeeds); `test_sr_violation_blocks_approval` and
`test_out_of_order_approval_blocked_sr2` FAIL (no `BusinessLogicError` raised). That split is
the point: the gate must add blocking without breaking the allow paths.

- [ ] **Step 4: Implement the gate**

In `src/cyo_adventure/publishing/service.py`, add imports:

```python
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select

from cyo_adventure.storybook.models import Storybook as StorybookDoc
from cyo_adventure.validator.series import validate_series
```

(merge into the existing import block; `select` may already be imported). Add the helper above
`approve`:

```python
async def _series_chain_docs(
    session: AsyncSession,
    storybook: Storybook,
    version_row: StorybookVersion,
) -> list[StorybookDoc] | None:
    """Load the parsed chain-so-far for a series approval, or None to skip.

    The chain is every published sibling's current published version plus the
    version under approval. Grandfather rule (WS-G G4): if ANY chain member
    predates WS-G (no embedded series block) or no longer parses against the
    current schema, return None so the gate is skipped with a warning;
    approved blobs are immutable, so a legacy chain can never be made to
    pass and must not block new approvals.
    """
    siblings = (
        (
            await session.execute(
                select(StorybookVersion).join(
                    Storybook,
                    (StorybookVersion.storybook_id == Storybook.id)
                    & (StorybookVersion.version == Storybook.current_published_version),
                ).where(
                    Storybook.series_id == storybook.series_id,
                    Storybook.id != storybook.id,
                    Storybook.status == "published",
                )
            )
        )
        .scalars()
        .all()
    )
    docs: list[StorybookDoc] = []
    for row in [*siblings, version_row]:
        try:
            doc = StorybookDoc.model_validate(row.blob)
        except PydanticValidationError:
            _logger.warning(
                "series_gate.skipped_unparseable_blob",
                storybook_id=row.storybook_id,
                version=row.version,
                series_id=str(storybook.series_id),
            )
            return None
        if doc.metadata.series is None:
            _logger.warning(
                "series_gate.skipped_legacy_chain",
                storybook_id=row.storybook_id,
                series_id=str(storybook.series_id),
            )
            return None
        docs.append(doc)
    return docs
```

Then in `approve()`, immediately AFTER the `moderation_report is None` gate and BEFORE
`storybook.status = target.value`, insert:

```python
    # #ASSUME: data-integrity: the chain read and the approval write share the
    # session's transaction; siblings are selected by status="published", so a
    # chain member mid-approval in another transaction is simply not yet part
    # of the chain-so-far.
    # #EDGE: concurrency: two same-series approvals racing can make the later
    # gate read a stale chain and fail SR-2 spuriously; the admin retries
    # after the first commit. No cross-series lock is taken for this.
    # #VERIFY: test_out_of_order_approval_blocked_sr2 covers the sequential
    # equivalent of that ordering rule.
    if storybook.series_id is not None:
        chain = await _series_chain_docs(session, storybook, version_row)
        if chain is not None:
            series_report = validate_series(chain)
            if not series_report.ok:
                detail = "; ".join(f.message for f in series_report.errors)
                msg = f"series chain validation failed: {detail}"
                raise BusinessLogicError(msg, rule="series_validation")
```

- [ ] **Step 5: Run the gate tests**

Run: `uv run pytest tests/integration/test_series_approval_gate.py -q`
Expected: all PASS.

- [ ] **Step 6: Run the neighboring suites (no regression in approval or events)**

Run: `uv run pytest tests/integration/test_publishing_service.py tests/integration/test_approval_api.py tests/integration/test_pipeline_event_instrumentation.py -q`
Expected: PASS; non-series approvals are untouched (`series_id is None` short-circuits).

- [ ] **Step 7: Commit**

```bash
git add src/cyo_adventure/publishing/service.py tests/integration/test_series_approval_gate.py
git commit -S -m "feat(publishing): gate series-book approval on chain-so-far SR validation (WS-G G4)"
```

---

### Task 4: Full gates and CHANGELOG

`depends-on: Task 2 [completion]`, `depends-on: Task 3 [completion]`.

- [ ] **Step 1: CHANGELOG entry**

Add under the `## [Unreleased]` / `### Added` section of `CHANGELOG.md` (create the subsection
if absent, matching the file's existing style):

```markdown
- Series chaining (WS-G PR 1): generated series books embed their document
  `Series` metadata block; SR-4 accepts open-ended chains; release approval
  validates the chain-so-far and blocks on SR errors (legacy pre-WS-G chains
  are grandfathered).
```

- [ ] **Step 2: Lint, format, types**

Run: `uv run ruff format . && uv run ruff check . && uv run basedpyright src/`
Expected: no errors. Fix any strict-mode findings in the new code (the `blob` dict handling in
`embed_series_block` and the join condition in `_series_chain_docs` are the likely candidates);
never suppress with ignores.

- [ ] **Step 3: Security scan**

Run: `uv run bandit -r src -q`
Expected: no new findings.

- [ ] **Step 4: Full suite with coverage**

Run: `uv run pytest --cov=src --cov-fail-under=80 -q 2>&1 | tail -5`
Expected: PASS, coverage >= 80 percent (baseline was ~95).

- [ ] **Step 5: Pre-commit over everything**

Run: `pre-commit run --all-files`
Expected: all hooks pass.

- [ ] **Step 6: Commit**

```bash
git add CHANGELOG.md
git commit -S -m "docs(changelog): WS-G PR 1 series metadata + validator gate"
```

(Fold any Step 2-5 fixes into this commit with their files listed explicitly; never `git add .`)

---

## Out of scope for PR 1 (later PRs, do not build here)

- `GET /api/v1/reading/series-next`, reader Continue, entry-node jump, var-state seeding, client
  regen, e2e (PR 2).
- `AnchorContext` variable names and continuation prompt changes (PR 3).
- Any migration, any new `pipeline_event` type, series closing (`is_final=True`).
