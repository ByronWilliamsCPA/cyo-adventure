"""Unit tests for cyo_adventure.moderation.personalizable_slots.

Covers `personalizable_slot_fields_for_story` (ADR-023 Stage C, Task C0c):
the story-scoped slot-id-to-personalization-field resolver the
personalization-values route needs. It shares its provenance chain
(`GenerationJob` by `storybook_id`, then `resolve_skeleton_path` plus
`load_skeleton` plus `load_contract_for`, via the `_contract_for_job` helper
extracted for this task) with the existing `personalizable_slot_ids_for_story`.

SUBSTITUTION (ADR-023 Stage C, Task C0a step 3): this plan named
`tests/unit/test_personalizable_slots.py` as a guess for this module's
filename, and it did not exist. It also did not exist as an indirect home
for `personalizable_slot_ids_for_story` coverage: that function is exercised
only via tests/unit/test_moderation_pipeline.py (its `personalizable_slot_ids_for_job`
cases and the `run_moderation_pipeline`-layer resolver-spy cases) and
tests/unit/test_resume_manual_fill_personalizable_slots.py (the resume path).
Per the plan's own fallback instruction, this file is created fresh and
mirrors those two donor modules' patterns rather than seeding a real
skeleton-with-personalizable-contract through a live database: no `session`
fixture backed by a real `AsyncSession`/Postgres exists in this test tier
(org testing standard 4.2/4.3, restated in test_moderation_pipeline.py's own
module docstring: "the DB session (spec'd AsyncMock; no live database in
unit tests)"). The `GenerationJob` SELECT here is doubled with the shared
spec'd `mock_async_session` fixture (tests/unit/conftest.py); where a real
contract is needed, `resolve_skeleton_path`/`load_skeleton` are monkeypatched
onto this module while `load_contract_for` is left real, reading an actual
sidecar written to `tmp_path` -- this mirrors
test_moderation_pipeline.py's `_wire_personalizable_job` helper exactly.
"""

from __future__ import annotations

import copy
import pickle
import uuid
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest

from cyo_adventure.db.models import GenerationJob, StorybookVersion
from cyo_adventure.moderation import personalizable_slots as pslots_mod
from cyo_adventure.moderation.personalizable_slots import (
    PERSONALIZABLE_SLOTS_UNRECOVERABLE,
    PERSONALIZABLE_SLOTS_UNSET,
    PersonalizableSlots,
    PersonalizableSlotsUnrecoverable,
    PersonalizableSlotsUnset,
    personalizable_slot_fields_for_story,
    personalizable_slot_ids_for_job,
    personalizable_slot_ids_for_version,
)
from cyo_adventure.storybook.models import AgeBand
from cyo_adventure.storybook.theme_contract import SlotScope, SlotSpec, ThemeContract

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.asyncio

_PERSONALIZABLE_SLUG = "themed-slug"


def _personalizable_contract() -> ThemeContract:
    """A minimal contract declaring one ``kind="personalizable"`` HERO slot.

    Same fixture shape as
    tests/unit/test_moderation_pipeline.py::_personalizable_contract and
    tests/unit/test_resume_manual_fill_personalizable_slots.py::_personalizable_contract;
    duplicated rather than imported because neither module exports it as a
    public, cross-module fixture.
    """
    return ThemeContract(
        contract_version=1,
        skeleton_slug=_PERSONALIZABLE_SLUG,
        age_band=AgeBand.BAND_8_11,
        legacy_lexicon=[],
        default_binding={"HERO": "Ada"},
        slots=[
            SlotSpec(
                id="HERO",
                scope=SlotScope.GLOBAL,
                meaning="the reader's own child, personalized",
                kind="personalizable",
                personalization_field="protagonist_first_name",
                role_safety="protagonist",
            ),
        ],
    )


def _wire_job_lookup(session: AsyncMock, job: GenerationJob | None) -> None:
    """Wire ``session.execute(...).scalar_one_or_none()`` to answer ``job``.

    `personalizable_slot_fields_for_story` (like `personalizable_slot_ids_for_story`)
    issues exactly one SELECT, the `GenerationJob` lookup by `storybook_id`;
    unlike test_moderation_pipeline.py's `_load`, which distinguishes two
    concurrent SELECT targets on the shared pipeline session, a single
    unconditional return is correct for this narrower resolver.
    """
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    session.execute = AsyncMock(return_value=result)


def _seed_story_with_job(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, session: AsyncMock
) -> str:
    """Wire ``session`` to a ``GenerationJob`` whose contract declares HERO.

    Writes a real contract sidecar to ``tmp_path`` and monkeypatches
    ``resolve_skeleton_path``/``load_skeleton`` onto this module so no real
    skeleton catalog entry is needed; ``load_contract_for`` is left real,
    genuinely reading the sidecar (mirrors
    test_moderation_pipeline.py::_wire_personalizable_job).

    Returns:
        str: the storybook id the wired job resolves to.
    """
    band_dir = tmp_path / "8-11"
    band_dir.mkdir()
    skeleton_path = band_dir / f"{_PERSONALIZABLE_SLUG}.json"
    contract_path = skeleton_path.with_name(f"{_PERSONALIZABLE_SLUG}.contract.json")
    contract_path.write_bytes(
        _personalizable_contract().model_dump_json().encode("utf-8")
    )
    monkeypatch.setattr(
        pslots_mod, "resolve_skeleton_path", lambda _band, _slug: skeleton_path
    )
    monkeypatch.setattr(
        pslots_mod,
        "load_skeleton",
        lambda _path: {
            "nodes": [
                {
                    "id": "n_start",
                    "body": (
                        "<<FILL role=setup words=40 beats='The hero, {HERO}, "
                        "arrives and must choose a path.'>>"
                    ),
                    "choices": [],
                },
            ],
        },
    )
    story_id = "s1"
    job = GenerationJob(
        concept_id=uuid.uuid4(),
        storybook_id=story_id,
        authoring_metadata={
            "skeleton_slug": _PERSONALIZABLE_SLUG,
            "skeleton_band": "8-11",
        },
    )
    _wire_job_lookup(session, job)
    return story_id


def _seed_story_without_job(session: AsyncMock) -> str:
    """Wire ``session`` so the ``GenerationJob`` SELECT finds no row."""
    _wire_job_lookup(session, None)
    return "s_no_job"


async def test_slot_fields_for_story_returns_the_contract_map(
    mock_async_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A story whose job resolves a contract yields that contract's field map."""
    story_id = _seed_story_with_job(monkeypatch, tmp_path, mock_async_session)

    fields = await personalizable_slot_fields_for_story(mock_async_session, story_id)

    assert fields == {"HERO": "protagonist_first_name"}


async def test_slot_fields_for_story_is_empty_without_a_job(
    mock_async_session: AsyncMock,
) -> None:
    """No GenerationJob means no reachable contract: empty, not fail-closed.

    Same reasoning as `personalizable_slot_ids_for_story`: seeded and
    directly-imported stories legitimately have no job row, and returning
    `PERSONALIZABLE_SLOTS_UNRECOVERABLE` would make every such story look
    uncomputable to a caller that treats that marker as "refuse".
    """
    story_id = _seed_story_without_job(mock_async_session)

    result = await personalizable_slot_fields_for_story(mock_async_session, story_id)

    assert result == {}


async def test_slot_fields_for_story_degrades_to_empty_when_the_skeleton_is_missing(
    mock_async_session: AsyncMock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A slug pointing at a vanished skeleton yields {} with a traceable warning.

    The documented contract (this function's Returns section) is that an
    unrecoverable contract is a DEGRADE case, not a fail-closed one: the map
    only feeds sentinel-value lookups, so empty is already the fail-safe
    outcome. What must not degrade silently is the log line: it has to carry
    the slug and band (structured attributes on `_ContractForJobError`, not a
    substring of the loader's message) or the operator cannot tell WHICH
    skeleton went missing. `load_skeleton` is left real here so the raw
    ``FileNotFoundError`` genuinely fires and is wrapped by
    `_contract_for_job` (mirrors test_moderation_pipeline.py::
    test_repair_contract_file_missing_is_discarded_and_routes_to_human_review).
    """
    missing_path = tmp_path / f"{_PERSONALIZABLE_SLUG}.json"
    monkeypatch.setattr(
        pslots_mod, "resolve_skeleton_path", lambda _band, _slug: missing_path
    )
    story_id = "s_missing_skeleton"
    job = GenerationJob(
        concept_id=uuid.uuid4(),
        storybook_id=story_id,
        authoring_metadata={
            "skeleton_slug": _PERSONALIZABLE_SLUG,
            "skeleton_band": "8-11",
        },
    )
    _wire_job_lookup(mock_async_session, job)

    with caplog.at_level("WARNING"):
        result = await personalizable_slot_fields_for_story(
            mock_async_session, story_id
        )

    assert result == {}
    # structlog renders through stdlib logging here (same capture route as
    # test_cover_optimize.py), so the structured kv pairs land in the rendered
    # record text; ANSI color codes sit between key and value, so each token
    # is asserted on its own rather than as a "key=value" substring.
    assert "personalization.slot_fields_contract_unresolved" in caplog.text
    assert _PERSONALIZABLE_SLUG in caplog.text
    assert "8-11" in caplog.text
    assert story_id in caplog.text


# ---------------------------------------------------------------------------
# personalizable_slot_ids_for_version: the imported-book path, which has no job
# ---------------------------------------------------------------------------

# A real catalog skeleton whose contract declares a NON-EMPTY personalizable
# slot set, so the assertion below can tell "the contract loaded" apart from
# "no sidecar, empty set by default". Most catalog contracts declare no
# personalizable slot at all, and against one of those the test would pass with
# the contract chain entirely broken.
# Re-derive with: grep -l personalizable skeletons/*/*.contract.json
_REAL_SLUG = "the-midnight-museum"
_REAL_SLUG_SLOTS = frozenset({"HERO"})


async def test_version_resolution_needs_no_generation_job() -> None:
    """An imported book resolves a real slot set with no job row in sight.

    This is the production shape of all seventeen in_review books: provider
    'import', skeleton_slug set, zero generation_job rows. Routed through
    :func:`personalizable_slot_ids_for_story` they resolve the fail-closed
    :data:`PERSONALIZABLE_SLOTS_UNRECOVERABLE`, moderation/pipeline.py turns
    that into a
    sentinel_integrity_violation BLOCK, and a report describing absent
    provenance overwrites one that described the prose.
    """
    version_row = StorybookVersion(
        storybook_id="s1", version=1, blob={}, skeleton_slug=_REAL_SLUG
    )

    # Asserting the exact set, not merely "not the fail-closed marker": an
    # unresolvable contract returns the EMPTY set on the no-sidecar arm, so a
    # marker-identity check alone would pass with the whole chain broken.
    assert personalizable_slot_ids_for_version(version_row) == _REAL_SLUG_SLOTS


async def test_version_without_a_slug_returns_the_empty_set() -> None:
    """No slug means no personalizable slot could exist: an empty set.

    Distinct from the fail-closed :data:`PERSONALIZABLE_SLOTS_UNRECOVERABLE`
    below, and the distinction is the whole tri-state. A fresh-generation
    version has no skeleton, so there is nothing a contract could declare;
    returning the marker here would manufacture a block for a book that is
    simply not skeleton-backed.
    """
    version_row = StorybookVersion(
        storybook_id="s1", version=1, blob={}, skeleton_slug=None
    )

    assert personalizable_slot_ids_for_version(version_row) == frozenset()


async def test_version_with_an_unlocatable_slug_fails_closed() -> None:
    """A slug naming no skeleton returns the marker, preserving the tri-state.

    The version claims skeleton provenance, so a contract may genuinely declare
    personalizable slots. Not finding it means the contract could not be
    recovered, which must still fail closed rather than guess an empty set and
    risk treating a real sentinel as forged.
    """
    version_row = StorybookVersion(
        storybook_id="s1", version=1, blob={}, skeleton_slug="no-such-skeleton-anywhere"
    )

    assert (
        personalizable_slot_ids_for_version(version_row)
        is PERSONALIZABLE_SLOTS_UNRECOVERABLE
    )


async def test_version_resolution_fails_closed_when_the_catalog_is_unreadable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unreadable skeleton catalog fails closed, it does not crash the caller.

    find_skeleton_band SCANS the catalog directory, so a permission fault or a
    hung mount raises a raw OSError rather than a ValidationError. Uncaught it
    escapes this function and takes down the whole re-moderation request, even
    though the contract load a few lines later already treats the identical
    fault on the identical catalog as fail-closed.
    """

    def _unreadable(_slug: str) -> str | None:
        msg = "skeleton catalog is unreadable"
        raise PermissionError(msg)

    monkeypatch.setattr(pslots_mod, "find_skeleton_band", _unreadable)
    version_row = StorybookVersion(
        storybook_id="s1", version=1, blob={}, skeleton_slug="any-slug"
    )

    assert (
        personalizable_slot_ids_for_version(version_row)
        is PERSONALIZABLE_SLOTS_UNRECOVERABLE
    )


# A real catalog skeleton with NO ".contract.json" sidecar, so load_contract_for
# takes its legacy arm and returns None. Asserting against a slug that has a
# sidecar could not tell "no contract to read" apart from "a contract that
# declares nothing", and those are different states of the catalog.
# Re-derive with:
#   for f in skeletons/*/*.json; do [ -f "${f%.json}.contract.json" ] ||
#       echo "$f"; done
_LEGACY_SLUG = "the-blackout-week"


async def test_version_with_a_traversing_slug_fails_closed() -> None:
    """A traversing slug fails closed; it does not read a file.

    find_skeleton_band raises ValidationError rather than returning None for a
    traversing slug, so this lands on a DIFFERENT arm than
    ::test_version_with_an_unlocatable_slug_fails_closed above, which resolves
    through the band-is-None path. Both fail closed, and the separation matters:
    a merely-absent slug is a catalog gap, while a traversing one is a hostile
    or corrupt ``skeleton_slug`` on a row that is about to be re-moderated.
    :data:`PERSONALIZABLE_SLOTS_UNRECOVERABLE` keeps it from being read as an
    empty contract, which would let a forged sentinel pass as personalization.
    """
    version_row = StorybookVersion(
        storybook_id="s1", version=1, blob={}, skeleton_slug="../../etc/passwd"
    )

    assert (
        personalizable_slot_ids_for_version(version_row)
        is PERSONALIZABLE_SLOTS_UNRECOVERABLE
    )


async def test_version_with_an_unreadable_contract_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A contract that cannot be loaded fails closed, not to an empty set.

    Distinct from the band scan above: the band resolved, the path resolved, and
    the read itself failed. That is the arm a moved or corrupted catalog file
    lands on, and it must not be confused with the legacy no-sidecar arm below,
    which returns the empty set. One means "this book declares no personalizable
    slot", the other means "we do not know what it declares".
    """

    def _unreadable(_path: object) -> dict[str, object]:
        msg = "skeleton file vanished mid-read"
        raise OSError(msg)

    monkeypatch.setattr(pslots_mod, "load_skeleton", _unreadable)
    version_row = StorybookVersion(
        storybook_id="s1", version=1, blob={}, skeleton_slug=_REAL_SLUG
    )

    assert (
        personalizable_slot_ids_for_version(version_row)
        is PERSONALIZABLE_SLOTS_UNRECOVERABLE
    )


async def test_version_on_a_legacy_skeleton_returns_the_empty_set() -> None:
    """A skeleton with no contract sidecar declares no slots: empty, not the marker.

    The third leg of the tri-state, and the one that carries the real risk of
    being collapsed into the fail-closed arm by a future edit. A legacy
    skeleton genuinely declares nothing, so blocking it would manufacture a
    safety verdict for a book whose only fault is predating theme contracts.
    """
    version_row = StorybookVersion(
        storybook_id="s1", version=1, blob={}, skeleton_slug=_LEGACY_SLUG
    )

    assert personalizable_slot_ids_for_version(version_row) == frozenset()


# ---------------------------------------------------------------------------
# The fail-closed marker type itself.
#
# The tests above assert WHICH arm each provenance failure lands on. These
# assert that the fail-closed arm cannot be quietly turned into the benign
# one, which is the property the marker type exists to hold and the one the
# previous `None` spelling did not.
# ---------------------------------------------------------------------------


async def test_unrecoverable_marker_refuses_a_truth_value() -> None:
    """`bool()` on the fail-closed marker raises instead of answering.

    This is the whole point of the type. Strict-mode typing already caught a
    caller who forgot to handle the fail-closed arm: passing it where a plain
    `frozenset[str]` is wanted has always been an error. A truthiness test is
    the one shape that type-checks perfectly and still routes a security
    control the wrong way, because the previous `None` spelling and the
    benign empty `frozenset` are both falsy while meaning opposite things.
    """
    with pytest.raises(TypeError) as excinfo:
        bool(PERSONALIZABLE_SLOTS_UNRECOVERABLE)

    message = str(excinfo.value)
    assert "isinstance" in message, (
        "the error must name the check that fails closed, not merely refuse"
    )
    assert "frozenset" in message, (
        "the error must also name the other reading, since an author who "
        "meant 'no slots are declared' has a different fix"
    )


def _declares_no_slots(slots: object) -> bool:
    """The hazard shape, written out as a consumer would have written it.

    A plausible reading of "this book declares no personalizable slot".
    Correct for the empty `frozenset`; catastrophic for the fail-closed arm,
    which means the opposite and, under the previous `None` spelling, was
    falsy too.

    The parameter is typed `object`, NOT `PersonalizableSlots`, and that is
    the point rather than a shortcut: annotated with the real union this body
    is a BasedPyright error ("Invalid conditional operand of type
    PersonalizableSlots"), because `__bool__` returns `NoReturn`. So the
    static gate already refuses this shape wherever the type is known.
    Widening to `object` is what lets the test still reach the RUNTIME guard,
    which is the layer that covers a value arriving through `Any`, a mock, or
    deserialized data, where no annotation was ever checked.

    Args:
        slots: A resolved personalizable-slot tri-state, deliberately
            un-narrowed.

    Returns:
        bool: True when the set is empty.

    Raises:
        TypeError: When `slots` is the fail-closed marker, which is the
            behavior under test.
    """
    return not slots


async def test_a_falsy_test_over_the_resolver_cannot_reach_the_benign_branch() -> None:
    """The hazard shape refuses over a REAL resolution, not just the constant.

    Exercised through `personalizable_slot_ids_for_version` so this fails if a
    future edit reinstates a falsy value on any fail-closed arm, not only if
    `__bool__` is deleted. The traversing slug is used because it fails closed
    via ValidationError, the arm furthest from the benign empty set.
    """
    version_row = StorybookVersion(
        storybook_id="s1", version=1, blob={}, skeleton_slug="../../etc/passwd"
    )
    slots = personalizable_slot_ids_for_version(version_row)

    with pytest.raises(TypeError):
        _declares_no_slots(slots)

    # The same predicate over the benign arm must still answer, or the marker
    # would have bought safety by breaking the legitimate reading.
    assert _declares_no_slots(frozenset[str]())
    assert not _declares_no_slots(frozenset({"HERO"}))


async def test_unrecoverable_marker_reprs_as_its_constant_name() -> None:
    """A log line or failed assertion names the state, not an object id.

    A default `<...object at 0x...>` repr in a moderation log is unreadable
    and, worse, is not greppable against the name used in code and runbooks.
    """
    assert repr(PERSONALIZABLE_SLOTS_UNRECOVERABLE) == (
        "PERSONALIZABLE_SLOTS_UNRECOVERABLE"
    )


async def test_the_two_markers_are_distinct_types() -> None:
    """ "Unset" and "unrecoverable" must not narrow to each other.

    They are adjacent and easy to conflate: one means "the caller supplied
    nothing, resolve it yourself", the other "the caller resolved it and the
    answer was 'cannot be recovered'". Collapsing them would silently turn a
    caller's deliberate fail-closed value back into a re-resolution.
    """
    assert not isinstance(PERSONALIZABLE_SLOTS_UNSET, PersonalizableSlotsUnrecoverable)
    assert not isinstance(PERSONALIZABLE_SLOTS_UNRECOVERABLE, PersonalizableSlotsUnset)


async def test_the_marker_is_not_a_frozenset() -> None:
    """`isinstance(x, frozenset)` is a sound narrowing of the tri-state.

    Several consumers narrow the union that way rather than by testing for
    the marker (api/node_edit.py, generation/import_story.py). That is only
    correct while the marker is not itself a frozenset subclass.
    """
    slots: PersonalizableSlots = PERSONALIZABLE_SLOTS_UNRECOVERABLE

    assert not isinstance(slots, frozenset)


async def test_unset_marker_refuses_a_truth_value() -> None:
    """`bool()` on the no-override marker raises instead of answering.

    The sibling of ::test_unrecoverable_marker_refuses_a_truth_value, and the
    reason it is needed is that narrowing away the fail-closed arm leaves the
    residual union `frozenset[str] | PersonalizableSlotsUnset`, which IS
    truthiness-testable with no diagnostic. Truthy-by-default put this marker
    in the "slots are declared" branch; falsy would put it in the "no slot is
    declared" branch. It means neither, so it must answer neither.
    """
    with pytest.raises(TypeError) as excinfo:
        bool(PERSONALIZABLE_SLOTS_UNSET)

    message = str(excinfo.value)
    assert "isinstance" in message, (
        "the error must name the check that resolves the contract, not merely refuse"
    )
    assert "no slot is declared" in message, (
        "the error must name the reading it is NOT, since this marker is "
        "adjacent to the benign empty frozenset and easily confused with it"
    )
    assert "slots are declared" in message, (
        "and the opposite reading too, which is the one a truthy-by-default "
        "marker silently supplied"
    )


async def test_unset_marker_reprs_as_its_constant_name() -> None:
    """A log line or failed assertion names the state, not an object id.

    Mirrors ::test_unrecoverable_marker_reprs_as_its_constant_name. The two
    markers travel through the same parameters and appear in the same
    tracebacks, so one of them rendering as `<...object at 0x...>` is exactly
    the case where telling them apart matters most.
    """
    assert repr(PERSONALIZABLE_SLOTS_UNSET) == "PERSONALIZABLE_SLOTS_UNSET"


@pytest.mark.parametrize(
    ("marker", "name"),
    [
        (PERSONALIZABLE_SLOTS_UNSET, "PERSONALIZABLE_SLOTS_UNSET"),
        (PERSONALIZABLE_SLOTS_UNRECOVERABLE, "PERSONALIZABLE_SLOTS_UNRECOVERABLE"),
    ],
    ids=["unset", "unrecoverable"],
)
async def test_the_markers_survive_copy_deepcopy_and_a_serialization_round_trip(
    marker: object, name: str
) -> None:
    """Copying or serializing a marker must yield the marker, not a twin.

    Before `__copy__`/`__deepcopy__`/`__reduce__` existed, all three of these
    produced a DISTINCT instance that still satisfied `isinstance`, so `is`
    and `isinstance` disagreed about the same value. That is not academic:
    these markers ride a frozen dataclass field and cross a `run_sync`
    boundary, and this module's own tests assert arm membership with `is`. A
    marker that fails an `is` check while passing `isinstance` is a
    fail-closed arm that a caller can accidentally read as recovered.
    """
    assert copy.copy(marker) is marker
    assert copy.deepcopy(marker) is marker
    # pickle.loads over bytes this very expression produced; there is no
    # untrusted input anywhere in this round trip, which is what S301 guards.
    revived = pickle.loads(pickle.dumps(marker))  # noqa: S301
    assert revived is marker
    # `revived is marker` proves the round trip resolved the singleton, but not
    # by what mechanism, so pin the mechanism itself. A BARE STRING return from
    # `__reduce__` is the stdlib singleton protocol ("on unpickle, look this
    # name up as a module global"); a tuple return would rebuild instead, and
    # nothing but the identity assert above would stand between that and a
    # silent `is`/`isinstance` split.
    assert marker.__reduce__() == name
    # That assert is only as good as `name`, which the reduction promises is
    # resolvable on this module. Check that promise rather than assume it.
    assert getattr(pslots_mod, name) is marker


# ---------------------------------------------------------------------------
# The job and version resolvers must agree on absent provenance.
# ---------------------------------------------------------------------------

_BLANK_SLUGS = ["", "   "]


@pytest.mark.parametrize("blank", _BLANK_SLUGS, ids=["empty", "whitespace"])
async def test_a_blank_slug_resolves_the_benign_arm_from_a_job(blank: str) -> None:
    """A job whose stored slug is blank declares nothing; it is not unrecoverable.

    BEHAVIOR CHANGE. This used to reach the fail-closed marker, because the
    guard was `not isinstance(slug, str)` and `""` IS a str: resolution
    proceeded to `resolve_skeleton_path(band, "")`, which produced a path
    ending in `/.json`, which failed to load. The version resolver, given the
    identical corrupt provenance, returned the benign empty frozenset. Same
    input, opposite verdicts, chosen by nothing but whether the caller held a
    job or a version.

    Both functions' documented contracts already called "no skeleton_slug"
    the benign arm, so that is the arm both now take: a blank slug names no
    file, so no contract could have declared a personalizable slot.
    """
    job = GenerationJob(
        concept_id=uuid.uuid4(),
        storybook_id="s_blank_slug",
        authoring_metadata={"skeleton_slug": blank, "skeleton_band": "8-11"},
    )

    assert personalizable_slot_ids_for_job(job) == frozenset()


@pytest.mark.parametrize("blank", _BLANK_SLUGS, ids=["empty", "whitespace"])
async def test_a_blank_slug_resolves_the_same_arm_from_a_job_and_a_version(
    blank: str,
) -> None:
    """The two resolvers return the SAME verdict for the same blank slug.

    Asserting the two against each other, not merely each against a constant:
    the defect was disagreement, so the test that pins it has to compare them.
    """
    job = GenerationJob(
        concept_id=uuid.uuid4(),
        storybook_id="s_blank_slug",
        authoring_metadata={"skeleton_slug": blank, "skeleton_band": "8-11"},
    )
    version_row = StorybookVersion(
        storybook_id="s_blank_slug", version=1, blob={}, skeleton_slug=blank
    )

    from_job = personalizable_slot_ids_for_job(job)
    from_version = personalizable_slot_ids_for_version(version_row)

    assert from_job == from_version == frozenset()
