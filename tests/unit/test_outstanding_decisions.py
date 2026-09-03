"""Unit tests for the `RS-C2`/`RS-C3` outstanding-decisions surface.

Docker-independent: these call ``approval.get_outstanding_decisions`` and the
``review_surface`` projection helpers directly, with a session double in place
of a real session. The SQL itself (the correlated latest-version subquery and
the published/latest CASE) is exercised in
``tests/integration/test_outstanding_decisions_api.py``; nothing here can
validate a query, so nothing here pretends to.

The invariant the whole surface exists to protect: an outstanding decision on a
book the review queue does not list is INVISIBLE, and under ADR-005 (the human
approver is the final gate) an invisible decision is a safety defect rather
than a missing convenience.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from cyo_adventure.api import approval
from cyo_adventure.api.deps import Principal, RequestContext
from cyo_adventure.api.review_surface import (
    build_decision_counts,
    build_moderation_decision_detail,
    build_review_queue_item,
    build_review_surface,
)
from cyo_adventure.api.schemas import OutstandingDecisionsView
from cyo_adventure.core.exceptions import AuthorizationError
from cyo_adventure.publishing.state_machine import (
    LEGAL_TRANSITIONS,
    Action,
    Status,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

_NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


def _principal(role: str, *, is_admin: bool | None = None) -> Principal:
    """Return a minimal Principal; ``is_admin`` defaults to role == "admin"."""
    admin = role == "admin" if is_admin is None else is_admin
    return Principal(
        subject=f"{role}-x",
        user_id=uuid.uuid4(),
        role="admin" if admin else role,
        family_id=uuid.uuid4(),
        profile_ids=frozenset(),
    )


class _Rows:
    """Minimal stand-in for a SQLAlchemy Result/ScalarResult.

    Both accessors are needed: the handler calls ``.all()`` on its candidate
    query, while ``load_threshold_policy`` iterates its ScalarResult directly.
    """

    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        """Return the seeded rows."""
        return self._rows

    def __iter__(self) -> Iterator[object]:
        """Iterate the seeded rows, as a ScalarResult does."""
        return iter(self._rows)


class _DecisionSession:
    """Session double for get_outstanding_decisions that counts round trips.

    The handler makes exactly one execute() (the candidate-row query), one get()
    (the admin noise floor), and one scalars() (the `RS-B3` threshold policy),
    regardless of how many books come back. Counting all three is the only way
    a test can prove the surface stayed O(1) queries: a future edit that reaches
    for a blob or a per-row policy read would still return correct data and
    would still pass every assertion about content.
    """

    def __init__(self, rows: list[object]) -> None:
        self._rows = rows
        self.execute_calls = 0
        self.scalars_calls = 0
        self.get_calls = 0

    async def execute(self, _stmt: object) -> _Rows:
        """Return the seeded candidate rows."""
        self.execute_calls += 1
        return _Rows(self._rows)

    async def scalars(self, _stmt: object) -> _Rows:
        """Return no threshold-override rows (the code defaults apply)."""
        self.scalars_calls += 1
        return _Rows([])

    async def get(self, _entity: object, _key: object) -> None:
        """Return None (no moderation_setting row; the code default floor applies)."""
        self.get_calls += 1


def _row(
    *,
    storybook_id: str = "s1",
    status: str = "published",
    current_published_version: int | None = 1,
    version: int = 1,
    title: str | None = "A Title",
    age_band: str | None = "6-8",
    moderation_report: dict[str, object] | None = None,
    cover_status: str = "ready",
    created_at: datetime = _NOW,
) -> approval._OutstandingRow:
    """Build one candidate row as the bulk query would return it.

    Returns the module's own ``_OutstandingRow`` for readable keyword
    construction; the handler re-builds it POSITIONALLY, so this double does
    exercise the field order. What it cannot exercise is the bridge itself: a
    real SQLAlchemy Row is labelled by COLUMN name (``id``, and ``anon_1`` for a
    JSONB extraction), so attribute access on the raw Row raises. Only
    ``tests/integration/test_outstanding_decisions_api.py`` can catch that.
    """
    return approval._OutstandingRow(
        storybook_id=storybook_id,
        status=status,
        family_id=uuid.uuid4(),
        current_published_version=current_published_version,
        version=version,
        title=title,
        age_band=age_band,
        moderation_report=moderation_report,
        cover_status=cover_status,
        version_created_at=created_at,
    )


def _blob() -> dict[str, object]:
    """A two-node blob, for the queue-row comparison only."""
    return {
        "title": "A Title",
        "metadata": {"age_band": "6-8"},
        "nodes": [
            {"id": "n_start", "body": "Start prose."},
            {"id": "n_end", "body": "End prose."},
        ],
    }


def _report(
    *findings: dict[str, object], hard_block: bool = False
) -> dict[str, object]:
    """Wrap findings in the report envelope build_review_surface expects."""
    return {
        "findings": list(findings),
        "summary": {
            "count": len(findings),
            "hard_block": hard_block,
            "soft_flag": any(f.get("verdict") == "flag" for f in findings),
            "repaired": False,
            "reviewer_independent": True,
        },
    }


def _finding(
    verdict: str, *, node_id: str | None = "n_start", category: str = "safety"
) -> dict[str, object]:
    """One genuine content finding at the given verdict."""
    return {
        "stage": 1,
        "source": "llm_safety",
        "category": category,
        "node_id": node_id,
        "verdict": verdict,
        "score": None,
        "message": f"{verdict} on {category}",
    }


def _unusable_report() -> dict[str, object]:
    """A whole report with no genuine content judgment in it.

    Shaped as ``stages.py::run_safety_stage`` emits when the review model is
    unreachable: one collapsed fail-safe finding naming every node. This is the
    case ``moderation_report_unusable`` was added for.
    """
    return _report(
        {
            "stage": 1,
            "source": "pipeline",
            "category": "pipeline",
            "node_id": "n_start",
            "verdict": "flag",
            "score": None,
            "message": (
                "reviewer unavailable or unparseable on 2 node(s); "
                "defaulted to fail-safe"
            ),
            "severity": "high",
            "structural": True,
            "concern": "reviewer_unavailable",
            "node_ids": ["n_start", "n_end"],
        }
    )


# ---------------------------------------------------------------------------
# _is_recallable
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.parametrize("status", [s.value for s in Status])
def test_recallable_is_derived_from_the_transition_table(status: str) -> None:
    """Recallability agrees with LEGAL_TRANSITIONS for every status, by construction.

    This is the assertion the schema's RAD marker cites. A client that decided
    for itself (``status == "published"``) would offer a button the API answers
    409 to the moment the table changes; deriving it means widening RECALL's
    legal sources widens this flag in the same commit.
    """
    expected = (Status(status), Action.RECALL) in LEGAL_TRANSITIONS
    assert approval._is_recallable(status) is expected


@pytest.mark.unit
def test_recallable_discriminates_between_statuses() -> None:
    """The table-derived predicate is not vacuously true or false.

    Without this, ``test_recallable_is_derived_from_the_transition_table`` would
    still pass if ``_is_recallable`` were ``return False`` and RECALL had been
    deleted from the table: both sides would agree on nothing. Pin the two ends
    against `RS-C1`'s actual ruling instead: published is the one recoverable
    exit from the shelf, and archived is absorbing.
    """
    assert approval._is_recallable("published") is True
    assert approval._is_recallable("archived") is False
    assert approval._is_recallable("draft") is False


@pytest.mark.unit
def test_an_unknown_status_is_not_recallable() -> None:
    """A status outside the enum degrades to "not recallable", not a 500.

    Only reachable if ck_storybook_status was dropped or bypassed. The listing
    is the operator's only view of these decisions, so one corrupt row must not
    deny the others; offering no recall button is the safe direction to fail.
    """
    assert approval._is_recallable("not_a_status") is False


# ---------------------------------------------------------------------------
# build_moderation_decision_detail
# ---------------------------------------------------------------------------


def _detail(report: dict[str, object] | None, *, status: str = "published") -> object:
    """Project a report into a decision detail with default floor and policy."""
    return build_moderation_decision_detail(
        storybook_id="s1",
        status=status,
        version=1,
        moderation_report=report,
        admin_noise_floor=None,
        age_band="6-8",
        policy=None,
    )


@pytest.mark.unit
def test_an_unusable_report_on_a_published_book_is_an_outstanding_decision() -> None:
    """A report too damaged to judge is a decision, not a clean bill of health.

    This is the assertion review_surface.py's ``#CRITICAL`` marker cites. The
    counts are all zero here precisely because no verdict could be drawn, so a
    "no blocks and no flags, therefore nothing to do" test would drop exactly
    the book whose safety is least established.
    """
    detail = _detail(_unusable_report())
    assert detail is not None
    assert detail.report_unusable is True
    assert (detail.block_findings, detail.flag_findings) == (0, 0)


@pytest.mark.unit
def test_a_clean_usable_report_is_not_an_outstanding_decision() -> None:
    """A published book whose report is clean and usable stays off the list."""
    assert _detail(_report(_finding("pass"))) is None


@pytest.mark.unit
def test_an_advisory_only_report_is_not_an_outstanding_decision() -> None:
    """Advisories alone do not put a published book on the list.

    Owner ruling 3: advisories are counted and available to dig into, never a
    gate. A surface that listed every advisory-carrying published book would be
    the whole catalog, which is the same as listing nothing.
    """
    assert _detail(_report(_finding("advisory"))) is None


@pytest.mark.unit
@pytest.mark.parametrize("verdict", ["block", "flag"])
def test_a_gating_verdict_on_a_published_book_is_an_outstanding_decision(
    verdict: str,
) -> None:
    """Both gating verdicts land on the list, with a headline finding attached."""
    detail = _detail(_report(_finding(verdict), hard_block=verdict == "block"))
    assert detail is not None
    assert detail.report_unusable is False
    counted = detail.block_findings if verdict == "block" else detail.flag_findings
    assert counted == 1
    # The headline is what the row shows without the admin opening the book, so
    # a row with a verdict and no top_finding would be a dead end.
    assert detail.top_finding is not None


@pytest.mark.unit
def test_decision_detail_counts_equal_the_queue_rows_counts() -> None:
    """The same report yields the same four numbers here and in the review queue.

    The point of extracting ``build_decision_counts``: a book that reads "1
    block" in one admin list must read "1 block" in the other and on the detail
    page. Two independent count implementations would drift, and the drift would
    show up as an operator disbelieving whichever number is smaller.
    """
    report = _report(
        _finding("block"),
        _finding("flag", node_id="n_end"),
        _finding("advisory", node_id=None, category="coherence"),
        hard_block=True,
    )
    queue_item = build_review_queue_item(
        storybook_id="s1",
        status="published",
        version=1,
        blob=_blob(),
        moderation_report=report,
        admin_noise_floor=None,
        created_at=_NOW,
        age_band="6-8",
        policy=None,
    )
    detail = _detail(report)
    assert detail is not None
    assert (
        detail.block_findings,
        detail.flag_findings,
        detail.advisory_findings,
    ) == (
        queue_item.block_findings,
        queue_item.flag_findings,
        queue_item.advisory_findings,
    )
    assert (detail.block_findings, detail.flag_findings) == (1, 1)


@pytest.mark.unit
def test_decision_detail_needs_no_blob_to_count_findings() -> None:
    """An empty blob changes none of the four numbers.

    This is what makes the bulk query blob-free, and therefore what makes the
    surface affordable at catalog scale: every number is report-derived, and the
    blob feeds only the prose join the decision row does not carry.
    """
    report = _report(_finding("block"), hard_block=True)
    with_blob = build_decision_counts(
        build_review_surface(
            status="published",
            storybook_id="s1",
            version=1,
            blob=_blob(),
            moderation_report=report,
        )
    )
    without_blob = build_decision_counts(
        build_review_surface(
            status="published",
            storybook_id="s1",
            version=1,
            blob={},
            moderation_report=report,
        )
    )
    assert with_blob.block_findings == without_blob.block_findings == 1
    assert with_blob.flag_findings == without_blob.flag_findings
    assert with_blob.advisory_findings == without_blob.advisory_findings


# ---------------------------------------------------------------------------
# get_outstanding_decisions
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.asyncio
async def test_outstanding_decisions_blocks_non_admin() -> None:
    """A non-admin raises AuthorizationError before any row is read.

    The order matters, not just the 403: a guardian must not learn WHICH books
    carry an unresolved safety verdict, so the counters have to stay at zero.
    """
    session = _DecisionSession([])
    ctx = RequestContext(principal=_principal("guardian"), session=session)  # type: ignore[arg-type]

    with pytest.raises(AuthorizationError, match="admin role required"):
        await approval.get_outstanding_decisions(ctx)

    assert (session.execute_calls, session.scalars_calls, session.get_calls) == (
        0,
        0,
        0,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_outstanding_decisions_empty_short_circuits_config_loads() -> None:
    """No candidate rows means no floor or policy read at all."""
    session = _DecisionSession([])
    ctx = RequestContext(principal=_principal("admin"), session=session)  # type: ignore[arg-type]

    view = await approval.get_outstanding_decisions(ctx)

    assert isinstance(view, OutstandingDecisionsView)
    assert view.items == []
    assert session.execute_calls == 1
    assert (session.scalars_calls, session.get_calls) == (0, 0)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_outstanding_decisions_is_bulk_not_n_plus_one() -> None:
    """Three books cost the same fixed round trips as one."""
    rows = [
        _row(
            storybook_id=f"s{i}",
            moderation_report=_report(_finding("block"), hard_block=True),
        )
        for i in range(3)
    ]
    session = _DecisionSession(list(rows))
    ctx = RequestContext(principal=_principal("admin"), session=session)  # type: ignore[arg-type]

    view = await approval.get_outstanding_decisions(ctx)

    assert {item.storybook_id for item in view.items} == {"s0", "s1", "s2"}
    # One candidate query, one noise-floor get, one threshold-policy read:
    # three for three books, and the same three for three hundred.
    assert (session.execute_calls, session.get_calls, session.scalars_calls) == (
        1,
        1,
        1,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_published_book_with_a_clean_report_is_omitted() -> None:
    """A candidate row with nothing outstanding produces no item.

    The query deliberately admits every published book (filtering on a JSONB
    verdict in SQL would be a second routing implementation), so the Python side
    is what keeps the list short. If this ever regresses, the surface degrades
    into "every published book", which is the failure mode `RS-C2` exists to
    avoid.
    """
    session = _DecisionSession([_row(moderation_report=_report(_finding("pass")))])
    ctx = RequestContext(principal=_principal("admin"), session=session)  # type: ignore[arg-type]

    view = await approval.get_outstanding_decisions(ctx)

    assert view.items == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_book_with_both_kinds_yields_two_rows() -> None:
    """A blocked published book awaiting a cover decision produces both rows.

    One row per DECISION, not per book: the two resolve through different
    actions on different pages, so collapsing them would hide whichever one the
    single row did not name.
    """
    session = _DecisionSession(
        [
            _row(
                moderation_report=_report(_finding("block"), hard_block=True),
                cover_status="pending_review",
            )
        ]
    )
    ctx = RequestContext(principal=_principal("admin"), session=session)  # type: ignore[arg-type]

    view = await approval.get_outstanding_decisions(ctx)

    assert [item.kind for item in view.items] == ["moderation", "cover"]
    # Both rows describe the same book at the same version, and both agree the
    # book can be recalled: _build_decision_item is what guarantees that.
    assert {item.storybook_id for item in view.items} == {"s1"}
    assert {item.version for item in view.items} == {1}
    assert all(item.recallable for item in view.items)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_pending_cover_is_child_facing_only_on_the_read_version() -> None:
    """child_facing is true only for the version api/library.py serves.

    A published book whose pending cover sits on a LATER version than
    ``current_published_version`` shows children the older art (or none), so
    approving that cover changes nothing a child sees today. Conflating the two
    would rank a cosmetic backlog item alongside a book on the shelf with no art.
    """
    session = _DecisionSession(
        [
            _row(
                storybook_id="on_shelf",
                current_published_version=2,
                version=2,
                cover_status="pending_review",
            ),
            _row(
                storybook_id="ahead_of_shelf",
                current_published_version=1,
                version=2,
                cover_status="pending_review",
            ),
            _row(
                storybook_id="draft_book",
                status="draft",
                current_published_version=None,
                version=1,
                cover_status="pending_review",
            ),
        ]
    )
    ctx = RequestContext(principal=_principal("admin"), session=session)  # type: ignore[arg-type]

    view = await approval.get_outstanding_decisions(ctx)

    facing = {item.storybook_id: item.cover for item in view.items}
    assert facing["on_shelf"] is not None
    assert facing["on_shelf"].child_facing is True
    assert facing["ahead_of_shelf"] is not None
    assert facing["ahead_of_shelf"].child_facing is False
    # A draft's pending cover is still an unmade decision and is still listed,
    # just never child-facing: no child can reach a draft.
    assert facing["draft_book"] is not None
    assert facing["draft_book"].child_facing is False
    assert facing["draft_book"].cover_status == "pending_review"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_non_published_book_contributes_no_moderation_row() -> None:
    """A draft's moderation verdict is not an outstanding decision here.

    Its home is the review queue (once submitted) or nowhere (a draft nobody
    submitted). Listing it would double-count the queue's own work and lengthen
    the one list that has to stay readable.
    """
    session = _DecisionSession(
        [
            _row(
                status="draft",
                current_published_version=None,
                moderation_report=_report(_finding("block"), hard_block=True),
                cover_status="pending_review",
            )
        ]
    )
    ctx = RequestContext(principal=_principal("admin"), session=session)  # type: ignore[arg-type]

    view = await approval.get_outstanding_decisions(ctx)

    assert [item.kind for item in view.items] == ["cover"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_rows_are_ordered_worst_first_not_newest_first() -> None:
    """Blocks, then other moderation decisions, then covers; oldest first within.

    This list exists because these decisions were already missed, so recency is
    the wrong axis: "newest first" buries exactly the rows that have been
    invisible longest. The fixture makes the newest row the least urgent one, so
    a plain reverse-chronological sort fails.
    """
    older = _NOW - timedelta(days=30)
    rows = [
        # This row carries NO moderation report at all, which
        # moderation_report_unusable treats exactly like a damaged one, so a
        # published book in this state yields a moderation row of its own on top
        # of its cover row. That is the intended reading: a published book whose
        # safety was never recorded is the strongest possible case of a decision
        # nobody was shown.
        _row(
            storybook_id="no_report",
            created_at=_NOW,
            cover_status="pending_review",
        ),
        _row(
            storybook_id="flagged",
            created_at=_NOW - timedelta(days=1),
            moderation_report=_report(_finding("flag")),
        ),
        _row(
            storybook_id="blocked_new",
            created_at=_NOW,
            moderation_report=_report(_finding("block"), hard_block=True),
        ),
        _row(
            storybook_id="blocked_old",
            created_at=older,
            moderation_report=_report(_finding("block"), hard_block=True),
        ),
        _row(
            storybook_id="unusable",
            created_at=_NOW - timedelta(days=2),
            moderation_report=_unusable_report(),
        ),
    ]
    session = _DecisionSession(list(rows))
    ctx = RequestContext(principal=_principal("admin"), session=session)  # type: ignore[arg-type]

    view = await approval.get_outstanding_decisions(ctx)

    assert [(item.storybook_id, item.kind) for item in view.items] == [
        ("blocked_old", "moderation"),
        ("blocked_new", "moderation"),
        ("unusable", "moderation"),
        ("flagged", "moderation"),
        ("no_report", "moderation"),
        ("no_report", "cover"),
    ]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_missing_title_falls_back_to_the_storybook_id() -> None:
    """A blob with no title still yields a row an admin can identify.

    The title is extracted in Postgres, so a blob missing the key returns NULL
    rather than raising; an empty title would render as an unclickable blank row
    on the one surface these books appear on.
    """
    session = _DecisionSession(
        [
            _row(
                title=None,
                age_band=None,
                moderation_report=_report(_finding("block"), hard_block=True),
            )
        ]
    )
    ctx = RequestContext(principal=_principal("admin"), session=session)  # type: ignore[arg-type]

    view = await approval.get_outstanding_decisions(ctx)

    assert [item.title for item in view.items] == ["s1"]
    assert view.items[0].age_band is None
