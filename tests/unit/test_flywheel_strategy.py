"""Unit tests for the WS-8 flywheel candidate strategy (design section 6).

The real catalog corpus (``skeletons/``) is git-versioned data, not a live
service, so loading it here honors the ``tests/`` no-network/no-DB posture. Tests
that need a lineage chain the real catalog does not contain build a tiny
fixture catalog under ``tmp_path`` by copying a real skeleton file.
"""

from __future__ import annotations

import json
from pathlib import Path

from cyo_adventure.flywheel import strategy
from cyo_adventure.flywheel.strategy import (
    MAX_ATTEMPTS_PER_CELL,
    CandidateMetrics,
    Cell,
    compute_candidate_metrics,
    eligible_parents,
    load_catalog,
    plan_attempts,
    ranking_key,
)

_SKELETONS_ROOT = Path(__file__).resolve().parents[2] / "skeletons"


def _entry_cell(entry: strategy.CatalogEntry) -> Cell:
    """Return the cell an entry belongs to."""
    meta = entry.metadata
    return Cell(
        band=meta.age_band.value,
        length=meta.length.value if meta.length is not None else "n/a",
        style=meta.narrative_style.value,
    )


# --- catalog load ---


def test_load_catalog_finds_known_tier1_and_tier2_slugs() -> None:
    """The real catalog decodes known skeletons with the expected tiers."""
    catalog = load_catalog()
    star = catalog.by_slug("the-sleepy-little-star")
    comet = catalog.by_slug("the-glass-comet")
    assert star is not None
    assert comet is not None
    assert star.tier == 1
    assert comet.tier == 2


def test_cell_as_dict_is_enum_only() -> None:
    """A cell serializes to the enum coordinate the ledger records."""
    cell = Cell(band="8-11", length="short", style="prose")
    assert cell.as_dict() == {"band": "8-11", "length": "short", "style": "prose"}


# --- eligibility (design 6.1) ---


def test_eligible_parents_excludes_series_skeletons() -> None:
    """A series skeleton is never an eligible parent (WS-5 precondition, 6.1)."""
    catalog = load_catalog()
    series_entry = next(
        (e for e in catalog.entries if e.metadata.series is not None), None
    )
    assert series_entry is not None, "expected at least one series skeleton in catalog"
    cell = _entry_cell(series_entry)
    eligible_slugs = {e.slug for e in eligible_parents(cell, catalog)}
    assert series_entry.slug not in eligible_slugs


def test_eligible_parents_excludes_non_production_seeds() -> None:
    """An MVP seed (production_eligible False) is never in-cell, so never eligible."""
    catalog = load_catalog()
    seed = next(
        (e for e in catalog.entries if not e.metadata.production_eligible), None
    )
    if seed is None:
        return  # no MVP seed in the catalog; the in_cell filter is exercised elsewhere
    cell = _entry_cell(seed)
    eligible_slugs = {e.slug for e in eligible_parents(cell, catalog)}
    assert seed.slug not in eligible_slugs


def test_eligible_parents_honors_excluded_parent_slugs() -> None:
    """A slug passed as excluded (open-PR check, 6.1 rule 4) is dropped."""
    catalog = load_catalog()
    star = catalog.by_slug("the-sleepy-little-star")
    assert star is not None
    cell = _entry_cell(star)
    assert star.slug in {e.slug for e in eligible_parents(cell, catalog)}
    excluded = frozenset({star.slug})
    remaining = {
        e.slug for e in eligible_parents(cell, catalog, excluded_parent_slugs=excluded)
    }
    assert star.slug not in remaining


# --- lineage-depth walk (design 6.1 rule 3), built on a tiny fixture catalog ---


def _build_lineage_chain(tmp_path: Path) -> Path:
    """Copy a real skeleton into a 3-generation chain and return the repo root.

    Layout under ``tmp_path/skeletons/3-5/``: ``root`` (generation 0, no sidecar),
    ``child`` (sidecar parent=root), ``grandchild`` (sidecar parent=child).
    """
    source = _SKELETONS_ROOT / "3-5" / "the-sleepy-little-star.json"
    document = source.read_text(encoding="utf-8")
    band_dir = tmp_path / "skeletons" / "3-5"
    band_dir.mkdir(parents=True)
    for slug in ("fw-root", "fw-child", "fw-grandchild"):
        _ = (band_dir / f"{slug}.json").write_text(document, encoding="utf-8")
    _ = (band_dir / "fw-child.lineage.json").write_text(
        json.dumps({"parent_slug": "fw-root"}), encoding="utf-8"
    )
    _ = (band_dir / "fw-grandchild.lineage.json").write_text(
        json.dumps({"parent_slug": "fw-child"}), encoding="utf-8"
    )
    return tmp_path


def test_generation_of_walks_the_sidecar_chain(tmp_path: Path) -> None:
    """Generation is 0 for a root, 1 for a child, 2 for a grandchild (6.1)."""
    catalog = load_catalog(_build_lineage_chain(tmp_path))
    assert catalog.generation_of("fw-root") == 0
    assert catalog.generation_of("fw-child") == 1
    assert catalog.generation_of("fw-grandchild") == 2


def test_eligible_parents_excludes_generation_two(tmp_path: Path) -> None:
    """A generation-2 skeleton is over the depth ceiling and excluded (6.1)."""
    catalog = load_catalog(_build_lineage_chain(tmp_path))
    star = catalog.by_slug("fw-root")
    assert star is not None
    cell = _entry_cell(star)
    eligible_slugs = {e.slug for e in eligible_parents(cell, catalog)}
    assert "fw-root" in eligible_slugs
    assert "fw-child" in eligible_slugs
    assert "fw-grandchild" not in eligible_slugs


# --- template instantiation (design 6.2) over small real parents ---


def test_t1_and_t2_instantiate_over_a_small_tier1_cell() -> None:
    """A Tier-1 cell yields graft (T1) and swap (T2) chains that construct."""
    catalog = load_catalog()
    cell = Cell(band="3-5", length="short", style="prose")
    plans = plan_attempts(cell, catalog, {})
    assert plans, "expected at least one plan for a populated Tier-1 cell"
    ops = {tuple(step.op_id for step in plan.steps) for plan in plans}
    assert ("M3", "M2") in ops  # T1 graft -> re-map


def test_t3_three_op_chain_constructs_on_a_small_parent() -> None:
    """T3 (M4 insert-decision -> M1 -> M2) instantiates on a small Tier-1 parent."""
    catalog = load_catalog()
    parent = catalog.by_slug("the-clover-and-the-butterfly")
    assert parent is not None
    plans = strategy._instantiate_t3(  # pyright: ignore[reportPrivateUsage]
        parent, _entry_cell(parent)
    )
    assert plans
    assert [s.op_id for s in plans[0].steps] == ["M4", "M1", "M2"]


def test_t4_state_chain_constructs_on_a_small_tier2_parent() -> None:
    """T4 (M5a retune -> M5b gate-choice) instantiates on the smallest Tier-2 tree."""
    catalog = load_catalog()
    parent = catalog.by_slug("the-glass-comet")
    assert parent is not None
    plans = strategy._instantiate_t4(  # pyright: ignore[reportPrivateUsage]
        parent, _entry_cell(parent)
    )
    assert plans
    assert [s.op_id for s in plans[0].steps] == ["M5", "M5"]


# --- plan_attempts (design 6.2/6.3) ---


def test_plan_attempts_respects_the_budget_and_value_order() -> None:
    """Attempts are capped and filled in value order (T1 before T2)."""
    catalog = load_catalog()
    cell = Cell(band="3-5", length="short", style="prose")
    plans = plan_attempts(catalog=catalog, cell=cell, ledger={})
    assert len(plans) <= MAX_ATTEMPTS_PER_CELL
    templates = [plan.template_id for plan in plans]
    # Value order: no lower-value template appears before a higher-value one runs
    # out. With T1 filling the budget here, every plan is T1.
    assert templates == sorted(templates, key=strategy.TEMPLATE_ORDER.index)


def test_plan_attempts_is_deterministic() -> None:
    """Two plans of the same cell produce the same attempt signatures."""
    catalog = load_catalog()
    cell = Cell(band="3-5", length="short", style="prose")
    first = [p.attempt_sig for p in plan_attempts(cell, catalog, {})]
    second = [p.attempt_sig for p in plan_attempts(cell, catalog, {})]
    assert first == second


def test_plan_attempts_skips_ledger_known_signatures() -> None:
    """A recorded attempt_sig is skipped; the next-value template fills instead."""
    catalog = load_catalog()
    cell = Cell(band="3-5", length="short", style="prose")
    first = plan_attempts(cell, catalog, {})
    known = {p.attempt_sig: "held" for p in first}
    second = plan_attempts(cell, catalog, known)
    first_sigs = {p.attempt_sig for p in first}
    second_sigs = {p.attempt_sig for p in second}
    assert first_sigs.isdisjoint(second_sigs)


# --- ranking (design 6.4) ---


def _metrics(
    *, min_in_cell: float, parent: float, reguide: int, seed: int
) -> CandidateMetrics:
    """Build a CandidateMetrics for a ranking fixture."""
    return CandidateMetrics(
        min_in_cell_distance=min_in_cell,
        parent_distance=parent,
        reguide_count=reguide,
        seed=seed,
    )


def test_ranking_prefers_larger_in_cell_headroom() -> None:
    """Rule 1: a candidate more distinct from in-cell siblings ranks first."""
    far = _metrics(min_in_cell=0.4, parent=0.1, reguide=5, seed=0)
    near = _metrics(min_in_cell=0.2, parent=0.9, reguide=0, seed=0)
    assert ranking_key(far) < ranking_key(near)


def test_ranking_breaks_ties_on_parent_distance_then_reguide_then_seed() -> None:
    """Rules 2-4: parent distance, then fewer re-guidance items, then lower seed."""
    a = _metrics(min_in_cell=0.3, parent=0.5, reguide=2, seed=1)
    b = _metrics(min_in_cell=0.3, parent=0.4, reguide=0, seed=0)
    # Rule 2 (parent distance) decides before rule 3/4 even look:
    assert ranking_key(a) < ranking_key(b)
    c = _metrics(min_in_cell=0.3, parent=0.5, reguide=3, seed=0)
    d = _metrics(min_in_cell=0.3, parent=0.5, reguide=1, seed=9)
    # Same rules 1-2; rule 3 (fewer reguide) decides:
    assert ranking_key(d) < ranking_key(c)
    e = _metrics(min_in_cell=0.3, parent=0.5, reguide=1, seed=2)
    f = _metrics(min_in_cell=0.3, parent=0.5, reguide=1, seed=7)
    # Same rules 1-3; rule 4 (lower seed) decides:
    assert ranking_key(e) < ranking_key(f)


def test_compute_candidate_metrics_empty_cohort_is_maximally_distinct() -> None:
    """An empty in-cell cohort makes the minimum in-cell distance infinite."""
    catalog = load_catalog()
    star = catalog.by_slug("the-sleepy-little-star")
    assert star is not None
    metrics = compute_candidate_metrics(
        star.document, star.document, [], reguide_count=0, seed=0
    )
    assert metrics.min_in_cell_distance == float("inf")
    assert metrics.parent_distance == 0.0  # identical doc against itself


# --- LLM01 safety property (design principle 5): no request-side inputs ---


def test_flywheel_package_imports_nothing_from_story_requests() -> None:
    """No flywheel module imports from story_requests (the D2 grep pin).

    Inspects real ``import``/``from`` statements via the AST, so a docstring
    that merely mentions the module (as ``strategy``'s does) does not trip it.
    """
    import ast

    package_dir = Path(strategy.__file__).parent
    for module in package_dir.glob("*.py"):
        tree = ast.parse(module.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert node.module is None or "story_requests" not in node.module, (
                    f"{module.name} imports from {node.module}"
                )
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert "story_requests" not in alias.name, (
                        f"{module.name} imports {alias.name}"
                    )


def test_strategy_public_functions_accept_no_brief_or_theme() -> None:
    """No public strategy function takes a brief/theme/premise/request parameter."""
    import inspect
    from typing import cast

    banned = {"brief", "theme", "premise", "request", "prompt", "concept"}
    for name in dir(strategy):
        if name.startswith("_"):
            continue
        obj = cast("object", getattr(strategy, name))
        if not inspect.isfunction(obj):
            continue
        params = set(inspect.signature(obj).parameters)
        assert params.isdisjoint(banned), f"{name} accepts a request-side param"
