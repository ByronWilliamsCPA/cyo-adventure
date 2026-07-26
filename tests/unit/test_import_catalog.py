"""Unit tests for the catalog batch importer's pure logic.

No database, no network: exercises blob loading/normalization, id-suffix
handling, and error classification directly against real repo files (the
manifest entries and their skeletons) or small synthetic fixtures. DB-backed
end-to-end coverage (idempotency, per-story isolation, family/skeleton_slug
threading) lives in tests/integration/test_import_catalog.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

import cyo_adventure.generation.import_catalog as import_catalog_module
from cyo_adventure.core.exceptions import BusinessLogicError, ValidationError
from cyo_adventure.generation.import_catalog import (
    CATALOG_ENTRIES,
    CatalogEntry,
    ImportConfig,
    ImportOutcome,
    _index_skeleton_nodes_by_id,
    _load_blob,
    _load_reference_skeleton,
    _needs_legacy_normalization,
    _normalize_legacy_endings,
    _normalize_legacy_fill,
    _normalize_legacy_metadata,
    _persist_and_classify,
    _prepare_blob,
    _print_summary,
    build_arg_parser,
)
from cyo_adventure.validator.gate import run_gate

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The 3 manifest entries documented (draft-stories-manifest.md) as carrying
# the older metadata shape; used to prove the normalization recipe against
# the real files, not a synthetic stand-in.
_LEGACY_TITLES = (
    "The Lost Mitten",
    "The Clocktower Cipher",
    "The Sunken Signal",
)


def _entry(title: str) -> CatalogEntry:
    """Return the CATALOG_ENTRIES row with the given title, or raise.

    Args:
        title: The entry's ``title`` field.

    Returns:
        The matching CatalogEntry.

    Raises:
        AssertionError: If no entry has this title (a manifest/test drift).
    """
    for entry in CATALOG_ENTRIES:
        if entry.title == title:
            return entry
    msg = f"no CATALOG_ENTRIES row titled {title!r}"
    raise AssertionError(msg)


def _minimal_current_blob() -> dict[str, object]:
    """A tiny, already-current-shape (schema_version "2.0") filled story."""
    return {
        "schema_version": "2.0",
        "id": "sk_unit_test_current",
        "version": 1,
        "title": "Current Shape",
        "metadata": {
            "age_band": "8-11",
            "topology": "linear",
            "production_eligible": False,
        },
        "start_node": "start",
        "nodes": [
            {
                "id": "start",
                "body": "A short beginning.",
                "is_ending": True,
                "ending": {
                    "id": "e_end",
                    "valence": "positive",
                    "kind": "completion",
                    "title": "The End",
                },
            }
        ],
    }


def _minimal_legacy_blob() -> dict[str, object]:
    """A tiny, stale-shape (schema_version "1.0", no topology) filled story."""
    return {
        "schema_version": "1.0",
        "id": "sk_unit_test_legacy",
        "version": 1,
        "title": "Legacy Shape",
        "metadata": {
            "age_band": "8-11",
        },
        "start_node": "start",
        "nodes": [
            {
                "id": "start",
                "body": "A short beginning.",
                "is_ending": True,
                "ending": {
                    "id": "e_end",
                    "type": "positive",
                    "title": "The End",
                },
            }
        ],
    }


def _minimal_legacy_skeleton() -> dict[str, object]:
    """The skeleton counterpart of :func:`_minimal_legacy_blob`."""
    return {
        "metadata": {
            "age_band": "8-11",
            "topology": "linear",
            "production_eligible": False,
        },
        "nodes": [
            {
                "id": "start",
                "is_ending": True,
                "ending": {
                    "id": "e_end",
                    "valence": "positive",
                    "kind": "completion",
                    "title": "The End",
                },
            }
        ],
    }


@pytest.mark.unit
class TestLoadBlob:
    def test_reads_valid_json_object(self, tmp_path: Path) -> None:
        (tmp_path / "story.json").write_text(json.dumps({"id": "s1"}), encoding="utf-8")
        blob = _load_blob(tmp_path, "story.json")
        assert blob == {"id": "s1"}

    def test_rejects_non_dict_json(self, tmp_path: Path) -> None:
        (tmp_path / "story.json").write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        with pytest.raises(ValidationError, match="expected a JSON object"):
            _load_blob(tmp_path, "story.json")

    def test_rejects_invalid_json(self, tmp_path: Path) -> None:
        (tmp_path / "story.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(ValidationError, match="invalid JSON"):
            _load_blob(tmp_path, "story.json")

    def test_raises_oserror_for_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(OSError, match="No such file"):
            _load_blob(tmp_path, "nope.json")


@pytest.mark.unit
class TestNeedsLegacyNormalization:
    def test_true_for_stale_schema_version(self) -> None:
        assert _needs_legacy_normalization(_minimal_legacy_blob()) is True

    def test_true_for_missing_topology(self) -> None:
        blob = _minimal_current_blob()
        blob["schema_version"] = "2.0"
        meta = blob["metadata"]
        assert isinstance(meta, dict)
        del meta["topology"]
        assert _needs_legacy_normalization(blob) is True

    def test_false_for_current_shape(self) -> None:
        assert _needs_legacy_normalization(_minimal_current_blob()) is False

    def test_true_when_metadata_is_not_a_dict(self) -> None:
        blob = _minimal_current_blob()
        blob["metadata"] = "not-a-dict"
        assert _needs_legacy_normalization(blob) is True


@pytest.mark.unit
class TestNormalizeLegacyFill:
    def test_backfills_metadata_and_ending_shape(self) -> None:
        blob = _minimal_legacy_blob()
        skeleton = _minimal_legacy_skeleton()

        normalized = _normalize_legacy_fill(blob, skeleton)

        assert normalized["schema_version"] == "2.0"
        meta = normalized["metadata"]
        assert isinstance(meta, dict)
        assert meta["topology"] == "linear"
        assert meta["production_eligible"] is False

        nodes = normalized["nodes"]
        assert isinstance(nodes, list)
        ending = nodes[0]["ending"]
        assert isinstance(ending, dict)
        assert ending == {
            "id": "e_end",
            "valence": "positive",
            "kind": "completion",
            "title": "The End",
        }

    def test_does_not_overwrite_present_metadata_fields(self) -> None:
        blob = _minimal_legacy_blob()
        meta = blob["metadata"]
        assert isinstance(meta, dict)
        meta["topology"] = "already-set"
        skeleton = _minimal_legacy_skeleton()

        normalized = _normalize_legacy_fill(blob, skeleton)

        assert normalized["metadata"]["topology"] == "already-set"  # type: ignore[index]

    def test_raises_when_no_id_matching_skeleton_ending(self) -> None:
        blob = _minimal_legacy_blob()
        skeleton = _minimal_legacy_skeleton()
        skel_nodes = skeleton["nodes"]
        assert isinstance(skel_nodes, list)
        skel_nodes[0]["id"] = "different-node-id"  # type: ignore[index]

        with pytest.raises(ValidationError, match="no matching skeleton ending"):
            _normalize_legacy_fill(blob, skeleton)

    def test_skips_nodes_already_in_current_shape(self) -> None:
        blob = _minimal_legacy_blob()
        nodes = blob["nodes"]
        assert isinstance(nodes, list)
        # Already current shape (has "kind"): must be left untouched even
        # though no matching skeleton node exists.
        nodes[0]["ending"] = {  # type: ignore[index]
            "id": "e_end",
            "valence": "neutral",
            "kind": "discovery",
            "title": "Untouched",
        }
        skeleton: dict[str, object] = {"nodes": []}

        normalized = _normalize_legacy_fill(blob, skeleton)

        result_nodes = normalized["nodes"]
        assert isinstance(result_nodes, list)
        assert result_nodes[0]["ending"]["title"] == "Untouched"  # type: ignore[index]


@pytest.mark.unit
class TestIndexSkeletonNodesById:
    def test_indexes_by_string_id(self) -> None:
        skeleton = _minimal_legacy_skeleton()
        indexed = _index_skeleton_nodes_by_id(skeleton)
        assert set(indexed) == {"start"}

    def test_skips_nodes_with_non_string_or_missing_id(self) -> None:
        skeleton: dict[str, object] = {
            "nodes": [
                {"id": 42, "body": "bad id type"},
                {"body": "no id at all"},
                "not-a-dict-node",
                {"id": "good", "body": "fine"},
            ]
        }
        indexed = _index_skeleton_nodes_by_id(skeleton)
        assert set(indexed) == {"good"}

    def test_returns_empty_for_non_list_nodes(self) -> None:
        assert _index_skeleton_nodes_by_id({"nodes": "not-a-list"}) == {}


@pytest.mark.unit
class TestNormalizeLegacyEndings:
    def test_noop_when_nodes_is_not_a_list(self) -> None:
        blob: dict[str, object] = {"nodes": "not-a-list"}
        _normalize_legacy_endings(blob, _minimal_legacy_skeleton())
        assert blob["nodes"] == "not-a-list"

    def test_skips_nodes_without_a_dict_ending(self) -> None:
        blob: dict[str, object] = {
            "nodes": [{"id": "n1", "ending": None}, "not-a-dict"]
        }
        _normalize_legacy_endings(blob, {"nodes": []})
        nodes = blob["nodes"]
        assert isinstance(nodes, list)
        assert nodes[0]["ending"] is None  # type: ignore[index]


@pytest.mark.unit
class TestNormalizeLegacyMetadata:
    def test_noop_when_blob_metadata_is_not_a_dict(self) -> None:
        blob: dict[str, object] = {"metadata": "not-a-dict"}
        _normalize_legacy_metadata(blob, _minimal_legacy_skeleton())
        assert blob["metadata"] == "not-a-dict"

    def test_noop_when_skeleton_metadata_is_not_a_dict(self) -> None:
        blob = _minimal_legacy_blob()
        _normalize_legacy_metadata(blob, {"metadata": "not-a-dict"})
        meta = blob["metadata"]
        assert isinstance(meta, dict)
        assert "topology" not in meta


@pytest.mark.unit
class TestRealLegacyFilesNormalizeCleanly:
    """Regression: the 3 documented legacy files pass run_gate once normalized.

    Empirically verifies the normalization recipe against the actual repo
    files rather than a synthetic stand-in, matching how these 3 files were
    originally investigated. Files are small (11-32 nodes), so running the
    real validator gate here stays fast.
    """

    @pytest.mark.parametrize("title", _LEGACY_TITLES)
    def test_normalized_blob_passes_the_validation_gate(
        self, title: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.chdir(_REPO_ROOT)
        entry = _entry(title)
        blob = _load_blob(_REPO_ROOT, entry.path)
        assert _needs_legacy_normalization(blob) is True

        skeleton = _load_reference_skeleton(entry.skeleton_band, entry.skeleton_slug)
        normalized = _normalize_legacy_fill(blob, skeleton)

        result = run_gate(normalized)
        assert result.blocked is False, [f.message for f in result.report.errors]


@pytest.mark.unit
class TestLoadReferenceSkeleton:
    def test_raises_when_skeleton_file_is_missing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.chdir(tmp_path)
        with pytest.raises(ValidationError, match="skeleton not found"):
            _load_reference_skeleton("8-11", "does-not-exist")

    def test_raises_when_skeleton_is_invalid_json(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.chdir(tmp_path)
        skel_dir = tmp_path / "skeletons" / "8-11"
        skel_dir.mkdir(parents=True)
        (skel_dir / "broken.json").write_text("{not json", encoding="utf-8")
        with pytest.raises(ValidationError, match="not valid JSON"):
            _load_reference_skeleton("8-11", "broken")


@pytest.mark.unit
class TestPrepareBlob:
    def test_success_without_id_suffix_or_normalization(self, tmp_path: Path) -> None:
        (tmp_path / "story.json").write_text(
            json.dumps(_minimal_current_blob()), encoding="utf-8"
        )
        entry = CatalogEntry("Title", "story.json", "8-11", "irrelevant-slug")

        result = _prepare_blob(tmp_path, entry)

        assert not isinstance(result, ImportOutcome)
        story_id, blob = result
        assert story_id == "sk_unit_test_current"
        assert blob["id"] == "sk_unit_test_current"

    def test_applies_id_suffix_before_computing_story_id(self, tmp_path: Path) -> None:
        (tmp_path / "story.json").write_text(
            json.dumps(_minimal_current_blob()), encoding="utf-8"
        )
        entry = CatalogEntry(
            "Title", "story.json", "8-11", "irrelevant-slug", id_suffix="variant-a"
        )

        result = _prepare_blob(tmp_path, entry)

        assert not isinstance(result, ImportOutcome)
        story_id, blob = result
        assert story_id == "sk_unit_test_current__variant-a"
        assert blob["id"] == "sk_unit_test_current__variant-a"

    def test_returns_error_outcome_on_missing_file(self, tmp_path: Path) -> None:
        entry = CatalogEntry("Title", "missing.json", "8-11", "slug")

        result = _prepare_blob(tmp_path, entry)

        assert isinstance(result, ImportOutcome)
        assert result.outcome == "error"
        assert result.story_id is None
        assert "load failed" in result.detail

    def test_returns_error_outcome_on_invalid_json(self, tmp_path: Path) -> None:
        (tmp_path / "story.json").write_text("{not json", encoding="utf-8")
        entry = CatalogEntry("Title", "story.json", "8-11", "slug")

        result = _prepare_blob(tmp_path, entry)

        assert isinstance(result, ImportOutcome)
        assert result.outcome == "error"

    def test_returns_error_outcome_when_blob_has_no_string_id(
        self, tmp_path: Path
    ) -> None:
        blob = _minimal_current_blob()
        del blob["id"]
        (tmp_path / "story.json").write_text(json.dumps(blob), encoding="utf-8")
        entry = CatalogEntry("Title", "story.json", "8-11", "slug")

        result = _prepare_blob(tmp_path, entry)

        assert isinstance(result, ImportOutcome)
        assert result.outcome == "error"
        assert "no string id" in result.detail

    def test_returns_error_outcome_when_id_suffix_requested_but_no_base_id(
        self, tmp_path: Path
    ) -> None:
        blob = _minimal_current_blob()
        del blob["id"]
        (tmp_path / "story.json").write_text(json.dumps(blob), encoding="utf-8")
        entry = CatalogEntry(
            "Title", "story.json", "8-11", "slug", id_suffix="variant-a"
        )

        result = _prepare_blob(tmp_path, entry)

        assert isinstance(result, ImportOutcome)
        assert result.outcome == "error"
        assert "no string id to suffix" in result.detail

    def test_returns_error_outcome_when_normalization_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        blob = _minimal_legacy_blob()
        (tmp_path / "story.json").write_text(json.dumps(blob), encoding="utf-8")
        entry = CatalogEntry("Title", "story.json", "8-11", "slug")

        def _mismatched_skeleton(_band: str, _slug: str) -> dict[str, object]:
            skeleton = _minimal_legacy_skeleton()
            nodes = skeleton["nodes"]
            assert isinstance(nodes, list)
            nodes[0]["id"] = "no-such-match"  # type: ignore[index]
            return skeleton

        monkeypatch.setattr(
            "cyo_adventure.generation.import_catalog._load_reference_skeleton",
            _mismatched_skeleton,
        )

        result = _prepare_blob(tmp_path, entry)

        assert isinstance(result, ImportOutcome)
        assert result.outcome == "error"
        assert "normalization failed" in result.detail

    def test_applies_normalization_when_blob_is_legacy_shaped(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        blob = _minimal_legacy_blob()
        (tmp_path / "story.json").write_text(json.dumps(blob), encoding="utf-8")
        entry = CatalogEntry("Title", "story.json", "8-11", "slug")

        monkeypatch.setattr(
            "cyo_adventure.generation.import_catalog._load_reference_skeleton",
            lambda _band, _slug: _minimal_legacy_skeleton(),
        )

        result = _prepare_blob(tmp_path, entry)

        assert not isinstance(result, ImportOutcome)
        _story_id, normalized_blob = result
        assert normalized_blob["schema_version"] == "2.0"


@pytest.mark.unit
class TestCatalogEntriesManifestIntegrity:
    """Structural sanity checks against the real 25-entry manifest on disk."""

    def test_all_entry_files_exist_and_parse(self) -> None:
        for entry in CATALOG_ENTRIES:
            blob = _load_blob(_REPO_ROOT, entry.path)
            story_id = blob.get("id")
            assert isinstance(story_id, str), entry.title
            assert story_id, entry.title

    def test_effective_story_ids_are_unique_after_suffixing(self) -> None:
        ids: list[str] = []
        for entry in CATALOG_ENTRIES:
            blob = _load_blob(_REPO_ROOT, entry.path)
            base_id = blob["id"]
            assert isinstance(base_id, str)
            effective_id = (
                f"{base_id}__{entry.id_suffix}"
                if entry.id_suffix is not None
                else base_id
            )
            ids.append(effective_id)
        assert len(ids) == len(set(ids)), "duplicate effective story ids"

    def test_has_exactly_twenty_five_entries(self) -> None:
        assert len(CATALOG_ENTRIES) == 25

    def test_pilot_entries_share_the_cave_of_echoes_skeleton(self) -> None:
        pilot_entries = [e for e in CATALOG_ENTRIES if e.id_suffix is not None]
        assert len(pilot_entries) == 2
        assert {e.skeleton_slug for e in pilot_entries} == {"the-cave-of-echoes"}
        assert {e.id_suffix for e in pilot_entries} == {"dino-dig", "space-station"}


@pytest.mark.unit
class TestPrintSummary:
    def test_returns_zero_when_only_imported_and_skipped(self) -> None:
        entry = CatalogEntry("Title", "path.json", "8-11", "slug")
        outcomes = [
            ImportOutcome(entry, "s1", "imported", "status=in_review"),
            ImportOutcome(entry, "s2", "skipped_existing"),
        ]
        assert _print_summary(outcomes) == 0

    def test_returns_one_when_any_gate_blocked(self) -> None:
        entry = CatalogEntry("Title", "path.json", "8-11", "slug")
        outcomes = [ImportOutcome(entry, "s1", "gate_blocked", "blocked reason")]
        assert _print_summary(outcomes) == 1

    def test_returns_one_when_any_error(self) -> None:
        entry = CatalogEntry("Title", "path.json", "8-11", "slug")
        outcomes = [ImportOutcome(entry, None, "error", "load failed")]
        assert _print_summary(outcomes) == 1

    def test_returns_zero_for_empty_outcomes(self) -> None:
        assert _print_summary([]) == 0


@pytest.mark.unit
class TestBuildArgParser:
    def test_defaults(self) -> None:
        args = build_arg_parser().parse_args([])
        assert args.model == "catalog-import"
        assert args.prompt_version == "catalog-import-v1"

    def test_overrides(self) -> None:
        args = build_arg_parser().parse_args(
            ["--model", "custom-model", "--prompt-version", "v2"]
        )
        assert args.model == "custom-model"
        assert args.prompt_version == "v2"


def _persist_entry() -> CatalogEntry:
    """A minimal CatalogEntry for _persist_and_classify tests (path unused)."""
    return CatalogEntry("Title", "out/does-not-matter.json", "8-11", "slug")


def _persist_blob() -> dict[str, object]:
    """A minimal blob carrying only the ``id`` _persist_and_classify reads."""
    return {"id": "sk_unit_persist_test"}


@pytest.mark.unit
class TestPersistAndClassify:
    """Unit coverage for _persist_and_classify's outcome classification.

    Patches ``import_filled_story`` on the ``import_catalog`` module (the
    same monkeypatch target the integration suite's own flaky-import test
    uses) against a bare ``AsyncMock`` session, so every classification
    branch (gate_blocked, error via ProjectBaseError, error via a bare
    SQLAlchemyError, and the "status=unknown" re-read miss) is exercised
    without a real Postgres connection. DB-backed, end-to-end coverage of
    the same function (through ``import_catalog()``) lives in
    tests/integration/test_import_catalog.py.
    """

    @pytest.mark.asyncio
    async def test_gate_blocked_on_validation_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A ValidationError from import_filled_story classifies as gate_blocked."""

        async def _raise_validation(session: object, request: object) -> str:
            _ = (session, request)
            msg = "topology violates the band's node budget"
            raise ValidationError(msg, field="nodes", value="n1")

        monkeypatch.setattr(
            import_catalog_module, "import_filled_story", _raise_validation
        )
        session = AsyncMock(spec=AsyncSession)

        outcome = await _persist_and_classify(
            session, _persist_entry(), _persist_blob(), ImportConfig()
        )

        assert outcome.outcome == "gate_blocked"
        assert "topology violates the band's node budget" in outcome.detail
        session.commit.assert_not_awaited()
        session.rollback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_error_on_project_base_error_rolls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A ProjectBaseError from import_filled_story classifies as error and rolls back."""

        async def _raise_domain_error(session: object, request: object) -> str:
            _ = (session, request)
            msg = "moderation pipeline failed"
            raise BusinessLogicError(msg, rule="moderation_pipeline_failure")

        monkeypatch.setattr(
            import_catalog_module, "import_filled_story", _raise_domain_error
        )
        session = AsyncMock(spec=AsyncSession)

        outcome = await _persist_and_classify(
            session, _persist_entry(), _persist_blob(), ImportConfig()
        )

        assert outcome.outcome == "error"
        assert "moderation pipeline failed" in outcome.detail
        session.rollback.assert_awaited_once()
        session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_error_on_bare_sqlalchemy_error_rolls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bare SQLAlchemyError (not a ProjectBaseError) also classifies as error.

        Regression for the broadened exception boundary (#CRITICAL note on
        _persist_and_classify): must NOT be narrowed to ProjectBaseError
        only, since a DB-layer failure like this one is not a domain error.
        """

        async def _raise_db_error(session: object, request: object) -> str:
            _ = (session, request)
            msg = "connection reset by peer"
            raise SQLAlchemyError(msg)

        monkeypatch.setattr(
            import_catalog_module, "import_filled_story", _raise_db_error
        )
        session = AsyncMock(spec=AsyncSession)

        outcome = await _persist_and_classify(
            session, _persist_entry(), _persist_blob(), ImportConfig()
        )

        assert outcome.outcome == "error"
        assert "connection reset by peer" in outcome.detail
        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_imported_with_unknown_status_when_row_not_found(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the freshly-imported Storybook row can't be re-read, status='unknown'."""

        async def _succeed(session: object, request: object) -> str:
            _ = (session, request)
            return "sk_unit_persist_test"

        monkeypatch.setattr(import_catalog_module, "import_filled_story", _succeed)
        session = AsyncMock(spec=AsyncSession)
        session.get = AsyncMock(return_value=None)

        outcome = await _persist_and_classify(
            session, _persist_entry(), _persist_blob(), ImportConfig()
        )

        assert outcome.outcome == "imported"
        assert outcome.detail == "status=unknown"
        session.commit.assert_awaited_once()


@pytest.mark.unit
class TestImportOneTransientErrorHandling:
    """Regression for Fix 3: the try-boundary move in ``_import_one``.

    Before the fix, the session acquire (``session_factory()``) and the
    pre-insert existence check (``session.get``) sat OUTSIDE the per-entry
    try/except, so a transient ``OperationalError`` at either point escaped
    ``_import_one`` uncaught and aborted the whole 25-story batch. Both are
    now inside the same ``except (ProjectBaseError, SQLAlchemyError))``
    boundary that already protects ``_persist_and_classify``'s own call to
    ``import_filled_story``. This class forces an ``OperationalError`` at
    each of the two newly-covered points and asserts only that one entry is
    classified "error", never a propagated exception.
    """

    class _FailingAcquireSessionCM:
        """An async context manager whose __aenter__ simulates a connect failure."""

        async def __aenter__(self) -> AsyncSession:
            msg = "connection refused"
            raise OperationalError("SELECT 1", {}, Exception(msg))

        async def __aexit__(self, *exc_info: object) -> bool:
            return False

    class _SessionCM:
        """An async context manager that just yields a pre-built session double."""

        def __init__(self, session: AsyncSession) -> None:
            self._session = session

        async def __aenter__(self) -> AsyncSession:
            return self._session

        async def __aexit__(self, *exc_info: object) -> bool:
            return False

    @pytest.mark.asyncio
    async def test_survives_a_transient_error_on_session_acquire(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entry = _persist_entry()
        monkeypatch.setattr(
            import_catalog_module,
            "_prepare_blob",
            lambda _root, _entry: ("sk_unit_test", _persist_blob()),
        )

        outcome = await import_catalog_module._import_one(
            self._FailingAcquireSessionCM,  # type: ignore[arg-type]
            entry,
            ImportConfig(),
        )

        assert outcome.outcome == "error"
        assert outcome.story_id == "sk_unit_test"
        assert "connection refused" in outcome.detail

    @pytest.mark.asyncio
    async def test_survives_a_transient_error_on_existence_check(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        entry = _persist_entry()
        monkeypatch.setattr(
            import_catalog_module,
            "_prepare_blob",
            lambda _root, _entry: ("sk_unit_test", _persist_blob()),
        )
        session = AsyncMock(spec=AsyncSession)
        session.get = AsyncMock(
            side_effect=OperationalError("SELECT 1", {}, Exception("pool exhausted"))
        )

        outcome = await import_catalog_module._import_one(
            lambda: self._SessionCM(session),  # type: ignore[arg-type]
            entry,
            ImportConfig(),
        )

        assert outcome.outcome == "error"
        assert outcome.story_id == "sk_unit_test"
        assert "pool exhausted" in outcome.detail
