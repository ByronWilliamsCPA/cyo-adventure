"""WS-8 catalog-flywheel candidate strategy (design section 6, stage S2).

Given a saturated cell (an enum ``(band, length, style)`` coordinate and nothing
else), this module plans the bounded set of mutation attempts the flywheel will
run against that cell's catalog: which parents are eligible (section 6.1), which
fixed chain templates to instantiate over them (section 6.2, T1 > T2 > T3 > T4),
a per-cell attempt budget with discard-ledger memory (section 6.3), and the
distance-based ranking that picks the single candidate to bundle (section 6.4).

**The whole surface is pure over catalog files and cell enums (design principle
5, OWASP LLM01).** No function accepts a brief, theme, premise, or story request;
the inputs are a :class:`Cell` of validated enum values, catalog skeleton
documents read from ``skeletons/`` on disk, and the ledger. It imports nothing
from ``story_requests`` (the D2 grep test pins this), performs no database or
network I/O, and wraps the delivered WS-5 engine
(:func:`~cyo_adventure.mutation.compose.apply_chain`) without modifying it: a
plan is validated by dry-running ``apply_chain`` (preconditions only, no gate),
and the caller (``scripts/flywheel_candidates.py``) runs the unchanged
acceptance harness.

Module constants (the attempt budget, the seed count, the template set version,
the lineage-depth ceiling) are tunable only by a reviewed PR: there is no
runtime override path (design 8.2).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from math import inf
from pathlib import Path
from typing import TYPE_CHECKING, cast

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.diversity.structure import structural_distance
from cyo_adventure.flywheel.ledger import attempt_sig
from cyo_adventure.generation.skeleton import is_sidecar
from cyo_adventure.mutation.bundle import content_sha256
from cyo_adventure.mutation.compose import ChainStep, apply_chain

# Importing the operator modules registers M1..M5 in the default REGISTRY, which
# ``apply_chain`` resolves against. The op-id constants are the stable ids the
# templates reference (never a spelled string literal).
from cyo_adventure.mutation.identity import recompute_tier
from cyo_adventure.mutation.operators import M1_OP_ID, M2_OP_ID, M3_OP_ID, M4_OP_ID
from cyo_adventure.mutation.ops import OpParams, ParamValue
from cyo_adventure.mutation.state_ops import M5_OP_ID
from cyo_adventure.mutation.subtree import extract_subtree, node_ids
from cyo_adventure.storybook.models import StoryMetadata

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

# The repository root, resolved from this file so the catalog scan is
# cwd-independent (mirrors ``mutation.floors._REPO_ROOT``).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_SKELETON_ROOT = _REPO_ROOT / "skeletons"

# The two bands where narrative style is a cell axis (ADR-011), mirroring
# ``mutation.floors._STYLE_AWARE_BANDS`` by value; below these, style is prose.
_STYLE_AWARE_BANDS = frozenset({"13-16", "16+"})

# --- Tunable-only-by-PR constants (design 8.2; no runtime override path) ---

# The per-cell-per-cycle acceptance-run cap (design 6.3). A pathological cell
# cannot burn a cycle no matter how many parents/templates apply.
MAX_ATTEMPTS_PER_CELL = 12

# The remaining four of the six design-8.2 hard bounds (the trigger threshold
# lives in ``flywheel/trigger.py`` as ``DEFAULT_MIN_CATALOG_EVENTS`` /
# ``DEFAULT_MIN_DISTINCT_REQUESTS`` and ``MAX_ATTEMPTS_PER_CELL`` is above; all
# six are constants changed ONLY by a reviewed PR, with no runtime override
# path). The scheduled cadence runner (D8) enforces every one of these in a
# single pure gate (:func:`cyo_adventure.flywheel.cadence.select_growable_cells`)
# so a triggered-but-capped cell is always REPORTED, never silently dropped
# (design 8.2 safety property).

# At most one open ``skeleton-promotion`` PR per cell: the reviewer compares one
# candidate against one cell at a time; a second candidate for the same cell
# waits (design 8.2).
OPEN_PR_PER_CELL = 1

# At most this many open ``skeleton-promotion`` PRs across the whole catalog:
# review-queue protection so the flywheel can never flood the one human it
# depends on (design 8.2).
OPEN_PR_GLOBAL = 3

# Per-cell cool-down after a merge, in days: let the WS-0 metrics and real
# selection absorb the new tree before growing the same cell again (design 8.2).
COOLDOWN_DAYS = 30

# The monthly promotion budget, in merged trees: matches the headline metric's
# unit (net new trees per month) and keeps the accepted contract-maintenance
# growth deliberate (design 8.2).
MONTHLY_MERGE_BUDGET = 4

# Seeds tried per (parent, template). For a template with an rng-selected step
# (M1/M2/M4), each seed explores a different selection; for a fully
# parameter-driven template (T1's graft, T4's M5 chain) the seed is recorded but
# the selection is fixed, so distinct attempts come from distinct targets.
SEEDS_PER_TEMPLATE = 4

# The chain-template set version (design 6.2). Bump on any change to a template's
# operator sequence so the ledger and lineage stay interpretable across versions.
TEMPLATE_SET_VERSION = 1

# Lineage-depth ceiling (design 6.1 rule 3, OQ-5): the parent we mutate must be
# at most this generation, so no promoted tree is more than two derivations from
# a hand-authored (generation 0) root.
MAX_PARENT_GENERATION = 1

# The four fixed chain templates, in descending value order (design 6.2).
TEMPLATE_T1 = "T1"
TEMPLATE_T2 = "T2"
TEMPLATE_T3 = "T3"
TEMPLATE_T4 = "T4"
# Value order the cell attempt budget is filled in (T1 first).
TEMPLATE_ORDER: tuple[str, ...] = (TEMPLATE_T1, TEMPLATE_T2, TEMPLATE_T3, TEMPLATE_T4)

# The empty slug set, as a module constant. Used as the default for the
# open-PR exclusion set and the lineage-walk cycle guard so no ``frozenset()``
# call appears in a parameter default (matches ``compose._NO_RESOLVED_REGUIDE``).
_EMPTY_SLUGS: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class Cell:
    """A saturated cell coordinate: enum values only (design 4.1, LLM01).

    Attributes:
        band: The age band (an :class:`~cyo_adventure.storybook.models.AgeBand`
            value).
        length: The length tier (a :class:`~cyo_adventure.storybook.models.Length`
            value).
        style: The narrative style (a
            :class:`~cyo_adventure.storybook.models.NarrativeStyle` value).
    """

    band: str
    length: str
    style: str

    def as_dict(self) -> dict[str, str]:
        """Return the cell as a ``{band, length, style}`` dict for the ledger."""
        return {"band": self.band, "length": self.length, "style": self.style}


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    """One catalog skeleton, decoded with the facts the strategy needs.

    Attributes:
        slug: The skeleton's slug (its filename stem).
        band: The skeleton's age band.
        path: The on-disk path (audit only; never written to).
        document: The decoded skeleton document.
        metadata: The typed skeleton metadata.
        tier: The recomputed structural tier (1 or 2).
        has_lineage_sidecar: Whether a ``<slug>.lineage.json`` sits beside it
            (True means generation >= 1; see :func:`Catalog.generation_of`).
    """

    slug: str
    band: str
    path: Path
    document: dict[str, object] = field(compare=False)
    metadata: StoryMetadata = field(compare=False)
    tier: int
    has_lineage_sidecar: bool


@dataclass(frozen=True, slots=True)
class Catalog:
    """The in-memory catalog scan the strategy plans over (design 6.1).

    Attributes:
        entries: Every decoded, production-or-MVP skeleton found on disk.
    """

    entries: tuple[CatalogEntry, ...]

    def by_slug(self, slug: str) -> CatalogEntry | None:
        """Return the entry with ``slug``, or None when absent."""
        for entry in self.entries:
            if entry.slug == slug:
                return entry
        return None

    def in_cell(self, cell: Cell) -> list[CatalogEntry]:
        """Return the production-eligible entries in ``cell``, sorted by slug.

        A length-less skeleton is a wildcard and narrative style is matched only
        for the two style-aware bands, mirroring the selector and floor cell
        semantics (``mutation.floors._matches_cell``).

        Args:
            cell: The cell to filter on.

        Returns:
            list[CatalogEntry]: The in-cell production-eligible entries.
        """
        matched = [
            entry
            for entry in self.entries
            if entry.metadata.production_eligible
            and _metadata_matches_cell(entry.metadata, cell)
        ]
        return sorted(matched, key=lambda entry: entry.slug)

    def same_band_donors(self, band: str, *, exclude_slug: str) -> list[CatalogEntry]:
        """Return eligible M3 graft donors in ``band`` (design 6.2).

        Donors are same-band, production-eligible, non-series skeletons, excluding
        the host itself. The caller ranks them by structural distance from the
        host.

        Args:
            band: The host's age band.
            exclude_slug: The host slug to omit from the donor set.

        Returns:
            list[CatalogEntry]: The eligible donor entries, sorted by slug.
        """
        donors = [
            entry
            for entry in self.entries
            if entry.band == band
            and entry.slug != exclude_slug
            and entry.metadata.production_eligible
            and entry.metadata.series is None
        ]
        return sorted(donors, key=lambda entry: entry.slug)

    def generation_of(self, slug: str, *, _seen: frozenset[str] = _EMPTY_SLUGS) -> int:
        """Return a skeleton's lineage generation by walking sidecars (design 6.1).

        A hand-authored skeleton has no ``*.lineage.json`` sidecar and is
        generation 0; a skeleton with one is ``1 + generation(parent_slug)``,
        recursing over the sidecar chain on disk (no new metadata). A missing or
        cyclic parent link terminates the walk defensively.

        Args:
            slug: The skeleton slug to compute the generation of.
            _seen: The slugs already visited on this walk (cycle guard).

        Returns:
            int: The lineage generation (0 for a hand-authored root).
        """
        entry = self.by_slug(slug)
        if entry is None or not entry.has_lineage_sidecar or slug in _seen:
            return 0
        parent_slug = _lineage_parent_slug(entry)
        if parent_slug is None:
            return 1
        return 1 + self.generation_of(parent_slug, _seen=_seen | {slug})


def _raw_nodes(document: Mapping[str, object]) -> list[dict[str, object]]:
    """Return a document's node dicts, skipping any malformed entry."""
    raw = document.get("nodes")
    if not isinstance(raw, list):
        return []
    return [
        cast("dict[str, object]", node)
        for node in cast("list[object]", raw)
        if isinstance(node, dict)
    ]


def _node_choices(node: Mapping[str, object]) -> list[dict[str, object]]:
    """Return a node's choice dicts, skipping any malformed entry."""
    raw = node.get("choices")
    if not isinstance(raw, list):
        return []
    return [
        cast("dict[str, object]", choice)
        for choice in cast("list[object]", raw)
        if isinstance(choice, dict)
    ]


def _node_id(node: Mapping[str, object]) -> str | None:
    """Return a node's id, or None when it is missing or non-string."""
    node_id = node.get("id")
    return node_id if isinstance(node_id, str) else None


def _is_ending(node: Mapping[str, object]) -> bool:
    """Return whether a node is an ending node."""
    return node.get("is_ending") is True


def _start_node(document: Mapping[str, object]) -> str | None:
    """Return a document's start node id, or None when absent."""
    start = document.get("start_node")
    return start if isinstance(start, str) else None


def _metadata_matches_cell(metadata: StoryMetadata, cell: Cell) -> bool:
    """Return whether a skeleton's metadata places it in ``cell``.

    Mirrors ``mutation.floors._matches_cell``: a length-less skeleton is a
    wildcard on length, and narrative style is matched only for the two
    style-aware bands.

    Args:
        metadata: The skeleton metadata.
        cell: The target cell.

    Returns:
        bool: True when the skeleton belongs to the cell.
    """
    if metadata.age_band.value != cell.band:
        return False
    if metadata.length is not None and metadata.length.value != cell.length:
        return False
    return (
        cell.band not in _STYLE_AWARE_BANDS
        or metadata.narrative_style.value == cell.style
    )


def _lineage_parent_slug(entry: CatalogEntry) -> str | None:
    """Return the ``parent_slug`` from a skeleton's lineage sidecar, or None.

    Args:
        entry: The catalog entry (its sidecar is read beside ``entry.path``).

    Returns:
        str | None: The recorded parent slug, or None when the sidecar is absent
            or unreadable (the walk then treats the entry as a root of depth 1).
    """
    # #ASSUME: external-resources: the lineage sidecar sits at
    # ``<band>/<slug>.lineage.json`` beside the skeleton (bundle.write_bundle
    # layout). A missing or malformed sidecar is treated as no parent link, so a
    # corrupt sidecar can only under-count depth (fail-open toward exclusion is
    # handled by MAX_PARENT_GENERATION being an inclusive ceiling).
    # #VERIFY: tests build a generation-2 fixture (a sidecar whose parent also
    # has a sidecar) and assert the walk excludes it.
    sidecar = entry.path.with_name(f"{entry.slug}.lineage.json")
    if not sidecar.is_file():
        return None
    try:
        data = cast("object", json.loads(sidecar.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    parent_slug = cast("dict[str, object]", data).get("parent_slug")
    return parent_slug if isinstance(parent_slug, str) else None


def load_catalog(repo_root: Path | None = None) -> Catalog:
    """Scan ``skeletons/`` into a :class:`Catalog` (design 6.1).

    Reads every ``skeletons/<band>/<slug>.json`` that is not a sidecar, decodes
    it, validates its metadata, recomputes its tier, and notes whether a lineage
    sidecar sits beside it. Malformed files are skipped, never fatal.

    Args:
        repo_root: The repository root to scan under; defaults to this file's
            resolved repository root.

    Returns:
        Catalog: The decoded catalog.
    """
    # #ASSUME: external-resources: the catalog is read from ``skeletons/<band>/``
    # under the repository-root convention the selector and floors use. This is
    # a read of git-versioned catalog files, never a live service.
    # #VERIFY: tests load the real catalog and assert known slugs and tiers.
    root = (repo_root / "skeletons") if repo_root is not None else _SKELETON_ROOT
    entries: list[CatalogEntry] = []
    if not root.is_dir():
        return Catalog(entries=())
    for band_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for path in sorted(band_dir.glob("*.json")):
            if is_sidecar(path):
                continue
            entry = _decode_entry(path, band_dir.name)
            if entry is not None:
                entries.append(entry)
    return Catalog(entries=tuple(entries))


def _decode_entry(path: Path, band: str) -> CatalogEntry | None:
    """Decode one skeleton file into a :class:`CatalogEntry`, or None on failure.

    Args:
        path: The skeleton file path.
        band: The band directory name the file was found under.

    Returns:
        CatalogEntry | None: The decoded entry, or None when the file or its
            metadata is malformed.
    """
    try:
        document = cast(
            "dict[str, object]", json.loads(path.read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError):
        return None
    meta_raw = document.get("metadata")
    if not isinstance(meta_raw, dict):
        return None
    try:
        metadata = StoryMetadata.model_validate(meta_raw)
    except ValueError:
        return None
    sidecar = path.with_name(f"{path.stem}.lineage.json")
    return CatalogEntry(
        slug=path.stem,
        band=band,
        path=path,
        document=document,
        metadata=metadata,
        tier=recompute_tier(document),
        has_lineage_sidecar=sidecar.is_file(),
    )


def eligible_parents(
    cell: Cell,
    catalog: Catalog,
    *,
    excluded_parent_slugs: frozenset[str] = _EMPTY_SLUGS,
) -> list[CatalogEntry]:
    """Return the parents eligible to mutate for ``cell`` (design 6.1).

    The precedence-ordered filter keeps in-cell entries that are
    production-eligible (never the MVP seeds), standalone (``series is None``),
    within the lineage-depth ceiling (parent generation <=
    :data:`MAX_PARENT_GENERATION`), and not in ``excluded_parent_slugs``.

    ``excluded_parent_slugs`` is the injection point for the design's
    "parent already has an open ``skeleton-promotion`` PR" check (design 6.1 rule
    4). D2 has no GitHub access, so it is a passed-in set defaulting to empty; the
    scheduler/D4 supplies the real set at run time.

    Args:
        cell: The saturated cell.
        catalog: The catalog scan.
        excluded_parent_slugs: Slugs to exclude (open-PR parents, supplied by
            the caller; empty by default).

    Returns:
        list[CatalogEntry]: The eligible parents, sorted by slug.
    """
    eligible: list[CatalogEntry] = []
    for entry in catalog.in_cell(cell):
        if entry.metadata.series is not None:
            continue
        if entry.slug in excluded_parent_slugs:
            continue
        if catalog.generation_of(entry.slug) > MAX_PARENT_GENERATION:
            continue
        eligible.append(entry)
    return eligible


@dataclass(frozen=True, slots=True)
class AttemptPlan:
    """One planned flywheel attempt: a parent plus a bounded chain (design 6.2).

    Attributes:
        parent_slug: The parent skeleton's slug.
        parent_sha256: The parent's canonical content hash at plan time.
        cell: The saturated cell this attempt serves.
        template_id: The chain template (``T1``..``T4``).
        steps: The bounded operator chain (1..3 steps), precondition-validated by
            a dry-run ``apply_chain``.
        seed: The plan's rng seed (the ranking tiebreak; applied to every
            rng-selected step in the chain).
        attempt_sig: The deterministic ledger signature for this attempt.
        donor_slug: The M3 graft donor slug for a T1 plan, else None.
    """

    parent_slug: str
    parent_sha256: str
    cell: Cell
    template_id: str
    steps: tuple[ChainStep, ...]
    seed: int
    attempt_sig: str
    donor_slug: str | None = None


def _make_plan(  # noqa: PLR0913 -- one cohesive AttemptPlan constructor
    *,
    parent: CatalogEntry,
    parent_sha256: str,
    cell: Cell,
    template_id: str,
    steps: Sequence[ChainStep],
    seed: int,
    donor_slug: str | None,
) -> AttemptPlan:
    """Build an :class:`AttemptPlan`, computing its ledger signature."""
    step_tuple = tuple(steps)
    return AttemptPlan(
        parent_slug=parent.slug,
        parent_sha256=parent_sha256,
        cell=cell,
        template_id=template_id,
        steps=step_tuple,
        seed=seed,
        attempt_sig=attempt_sig(parent_sha256, step_tuple),
        donor_slug=donor_slug,
    )


def _chain_is_constructible(
    parent: Mapping[str, object], steps: Sequence[ChainStep]
) -> bool:
    """Return whether a chain's preconditions all hold on ``parent``.

    Dry-runs :func:`~cyo_adventure.mutation.compose.apply_chain`, which checks
    each step's preconditions against the running candidate (no gate, cheap). A
    :class:`ValidationError` means at least one step is ineligible, so the plan
    is dropped: the flywheel never emits a plan whose chain cannot even be built
    (design "an instantiation that can't satisfy preconditions yields no
    attempt").

    Args:
        parent: The raw parent document.
        steps: The candidate chain steps.

    Returns:
        bool: True when ``apply_chain`` succeeds, False when it raises.
    """
    try:
        _ = apply_chain(parent, steps)
    except ValidationError:
        return False
    return True


def _params(**values: ParamValue) -> OpParams:
    """Build :class:`OpParams` from keyword scalars (a thin ergonomic wrapper)."""
    return OpParams.of(**values)


def _first_valid_single_step(
    parent: Mapping[str, object], op_id: str, candidate_params: Iterable[OpParams]
) -> OpParams | None:
    """Return the first params whose single-op chain is constructible, or None.

    Used to search explicit-target operator params (M3 graft targets, M5 retune
    and gate-choice targets) that do not auto-select from a seed.

    Args:
        parent: The raw document the single step runs against (the original
            parent, or a prior step's candidate).
        op_id: The operator id.
        candidate_params: The candidate parameter sets to try, in order.

    Returns:
        OpParams | None: The first constructible params, or None if none work.
    """
    for params in candidate_params:
        if _chain_is_constructible(parent, [ChainStep(op_id=op_id, params=params)]):
            return params
    return None


# --- T1: M3 graft (same-band donor) -> M2 re-map (Tier-1) ---


def _pick_donor(parent: CatalogEntry, catalog: Catalog) -> CatalogEntry | None:
    """Return the max-distance eligible graft donor for a host (design 6.2).

    Among same-band, production-eligible, non-series donors, pick the one at
    maximum ``structural_distance`` from the host (a distant donor imports
    genuinely different material). Ties break on the lowest slug for determinism.

    Args:
        parent: The host (parent) entry.
        catalog: The catalog scan.

    Returns:
        CatalogEntry | None: The chosen donor, or None when the band has none.
    """
    donors = catalog.same_band_donors(parent.band, exclude_slug=parent.slug)
    if not donors:
        return None
    # Sort by descending distance, then ascending slug: max-distance donor first.
    ranked = sorted(
        donors,
        key=lambda donor: (
            -structural_distance(parent.document, donor.document),
            donor.slug,
        ),
    )
    return ranked[0]


def _graft_params(parent: CatalogEntry, donor: CatalogEntry) -> OpParams | None:
    """Return a precondition-satisfying M3 graft params for a host/donor, or None.

    Enumerates candidate ``(subtree_root, host_decision)`` pairs and returns the
    first constructible one, with donor subtrees tried LARGEST-FIRST. Grafting the
    biggest self-contained donor subtree that still fits the cell node envelope is
    what pushes the composed result's structural distance from the parent up toward
    the ``TAU_STRUCT`` anti-clone floor: a first-eligible (often tiny) graft barely
    moves the tree, so this maximization is not cosmetic but the difference between
    a floor-clearing candidate and a discard (measured: largest-first lifts a
    reference graft from ~0.02 to ~0.32 parent distance). Ties on size break on the
    root id for determinism.

    Args:
        parent: The host (parent) entry.
        donor: The chosen donor entry.

    Returns:
        OpParams | None: The graft params (``mode=graft`` plus ids), or None when
            no eligible graft exists.
    """
    donor_start = _start_node(donor.document)
    sized_roots = [
        (root, len(extract_subtree(donor.document, root).node_ids))
        for root in node_ids(donor.document)
        if root != donor_start and extract_subtree(donor.document, root).self_contained
    ]
    # Largest subtree first (then id): the biggest in-envelope graft is the most
    # structure-shifting one the anti-clone floor cares about.
    subtree_roots = [
        root for root, _ in sorted(sized_roots, key=lambda pair: (-pair[1], pair[0]))
    ]
    host_decisions = [
        node_id
        for node in _raw_nodes(parent.document)
        if not _is_ending(node)
        and 1 <= len(_node_choices(node)) <= 2
        and (node_id := _node_id(node)) is not None
    ]
    candidate_params = (
        _params(mode="graft", donor=donor.slug, subtree_root=root, host_decision=host)
        for root in subtree_roots
        for host in host_decisions
    )
    return _first_valid_single_step(parent.document, M3_OP_ID, candidate_params)


def _instantiate_t1(
    parent: CatalogEntry, catalog: Catalog, cell: Cell
) -> list[AttemptPlan]:
    """Instantiate T1 (M3 graft -> M2 re-map) for a Tier-1 parent (design 6.2)."""
    if parent.tier != 1:
        return []
    donor = _pick_donor(parent, catalog)
    if donor is None:
        return []
    graft = _graft_params(parent, donor)
    if graft is None:
        return []
    parent_sha256 = content_sha256(parent.document)
    plans: list[AttemptPlan] = []
    for seed in range(SEEDS_PER_TEMPLATE):
        steps = [
            ChainStep(op_id=M3_OP_ID, params=graft, seed=seed),
            ChainStep(op_id=M2_OP_ID, params=_params(), seed=seed),
        ]
        if _chain_is_constructible(parent.document, steps):
            plans.append(
                _make_plan(
                    parent=parent,
                    parent_sha256=parent_sha256,
                    cell=cell,
                    template_id=TEMPLATE_T1,
                    steps=steps,
                    seed=seed,
                    donor_slug=donor.slug,
                )
            )
    return plans


# --- T2: M1 swap -> M2 re-map (Tier-1) ---


def _instantiate_t2(parent: CatalogEntry, cell: Cell) -> list[AttemptPlan]:
    """Instantiate T2 (M1 swap -> M2 re-map) for a Tier-1 parent (design 6.2)."""
    if parent.tier != 1:
        return []
    return _rng_selected_plans(
        parent,
        cell,
        TEMPLATE_T2,
        [(M1_OP_ID, _params()), (M2_OP_ID, _params())],
    )


# --- T3: M4 insert-decision -> M1 swap -> M2 re-map (Tier-1) ---


def _instantiate_t3(parent: CatalogEntry, cell: Cell) -> list[AttemptPlan]:
    """Instantiate T3 (M4 insert-decision -> M1 -> M2) for a Tier-1 parent (6.2)."""
    if parent.tier != 1:
        return []
    return _rng_selected_plans(
        parent,
        cell,
        TEMPLATE_T3,
        [
            (M4_OP_ID, _params(mode="insert-decision")),
            (M1_OP_ID, _params()),
            (M2_OP_ID, _params()),
        ],
    )


def _rng_selected_plans(
    parent: CatalogEntry,
    cell: Cell,
    template_id: str,
    op_params: Sequence[tuple[str, OpParams]],
) -> list[AttemptPlan]:
    """Instantiate a template whose steps auto-select from the seed (T2/T3).

    Each ``(op_id, params)`` step omits the target ids, so the operator selects
    reproducibly from the seeded rng; distinct seeds explore distinct selections.

    Args:
        parent: The parent entry.
        cell: The saturated cell.
        template_id: The template id to record.
        op_params: The ordered ``(op_id, base params)`` steps.

    Returns:
        list[AttemptPlan]: One plan per seed whose chain is constructible.
    """
    parent_sha256 = content_sha256(parent.document)
    plans: list[AttemptPlan] = []
    for seed in range(SEEDS_PER_TEMPLATE):
        steps = [
            ChainStep(op_id=op_id, params=params, seed=seed)
            for op_id, params in op_params
        ]
        if _chain_is_constructible(parent.document, steps):
            plans.append(
                _make_plan(
                    parent=parent,
                    parent_sha256=parent_sha256,
                    cell=cell,
                    template_id=template_id,
                    steps=steps,
                    seed=seed,
                    donor_slug=None,
                )
            )
    return plans


# --- T4: M5a retune + M5b gate-choice (Tier-2) ---


def _retune_candidates(document: Mapping[str, object]) -> list[OpParams]:
    """Return candidate M5a retune params over a Tier-2 tree's variables.

    For each declared variable, a widen-max, a widen-min (int only), and a
    description-only retune are offered, in that order; the description retune is
    always schema-valid, so a variable always yields at least one constructible
    candidate. The caller keeps the first constructible one.

    Args:
        document: The parent document.

    Returns:
        list[OpParams]: The candidate retune parameter sets, in try order.
    """
    raw_vars = document.get("variables")
    if not isinstance(raw_vars, list):
        return []
    candidates: list[OpParams] = []
    for raw_var in cast("list[object]", raw_vars):
        if not isinstance(raw_var, dict):
            continue
        var = cast("dict[str, object]", raw_var)
        name = var.get("name")
        if not isinstance(name, str):
            continue
        maximum = var.get("max")
        minimum = var.get("min")
        if isinstance(maximum, int) and not isinstance(maximum, bool):
            candidates.append(_params(variable=name, max=maximum + 1))
        if isinstance(minimum, int) and not isinstance(minimum, bool):
            candidates.append(_params(variable=name, min=minimum - 1))
        description = var.get("description")
        base = description if isinstance(description, str) else f"state variable {name}"
        candidates.append(
            _params(variable=name, description=f"{base} (state variation)")
        )
    return candidates


def _gate_choice_candidates(document: Mapping[str, object]) -> list[OpParams]:
    """Return candidate M5b gate-choice params over a Tier-2 tree.

    For every unconditioned choice that keeps an unconditioned sibling (the cheap
    non-stranding precondition), a gate against each declared variable is offered
    (``>= min`` for an int variable, ``== True`` for a bool one). The caller keeps
    the first constructible one; the gate's L2 walk is the real stranding
    authority.

    Args:
        document: The document the gate-choice runs against (a retuned candidate).

    Returns:
        list[OpParams]: The candidate gate-choice parameter sets, in try order.
    """
    variables = _variable_gate_values(document)
    if not variables:
        return []
    candidates: list[OpParams] = []
    for node in _raw_nodes(document):
        choices = _node_choices(node)
        unconditioned = [
            choice_id
            for choice in choices
            if choice.get("condition") is None
            and (choice_id := _node_id(choice)) is not None
        ]
        if len(unconditioned) < 2:
            continue
        for choice_id in unconditioned:
            for gate_var, gate_op, gate_value in variables:
                candidates.append(
                    _params(
                        choice=choice_id,
                        gate_var=gate_var,
                        gate_op=gate_op,
                        gate_value=gate_value,
                    )
                )
    return candidates


def _variable_gate_values(
    document: Mapping[str, object],
) -> list[tuple[str, str, ParamValue]]:
    """Return ``(name, op, value)`` gate triples for each declared variable."""
    raw_vars = document.get("variables")
    if not isinstance(raw_vars, list):
        return []
    triples: list[tuple[str, str, ParamValue]] = []
    for raw_var in cast("list[object]", raw_vars):
        if not isinstance(raw_var, dict):
            continue
        var = cast("dict[str, object]", raw_var)
        name = var.get("name")
        if not isinstance(name, str):
            continue
        minimum = var.get("min")
        if isinstance(minimum, int) and not isinstance(minimum, bool):
            triples.append((name, ">=", minimum))
        elif var.get("type") == "bool":
            triples.append((name, "==", True))
    return triples


def _instantiate_t4(parent: CatalogEntry, cell: Cell) -> list[AttemptPlan]:
    """Instantiate T4 (M5a retune + M5b gate-choice) for a Tier-2 parent (6.2).

    A retune and a gate-choice must each carry explicit targets (M5 does not
    auto-select from a seed), so the retune is chosen first, its candidate is fed
    to the gate-choice search, and the two form a length-2 chain. Distinct plans
    come from distinct retune targets (bounded by :data:`SEEDS_PER_TEMPLATE`),
    since M5 ignores the seed.
    """
    if parent.tier != 2:
        return []
    parent_sha256 = content_sha256(parent.document)
    plans: list[AttemptPlan] = []
    seen_sigs: set[str] = set()
    for retune_base in _retune_candidates(parent.document):
        if len(plans) >= SEEDS_PER_TEMPLATE:
            break
        retune_step = ChainStep(
            op_id=M5_OP_ID, params=_retune_with_mode(retune_base), seed=0
        )
        if not _chain_is_constructible(parent.document, [retune_step]):
            continue
        retuned = apply_chain(parent.document, [retune_step]).candidate
        gate_params = _first_valid_single_step(
            retuned, M5_OP_ID, _gate_with_mode(_gate_choice_candidates(retuned))
        )
        if gate_params is None:
            continue
        steps = [retune_step, ChainStep(op_id=M5_OP_ID, params=gate_params, seed=0)]
        if not _chain_is_constructible(parent.document, steps):
            continue
        plan = _make_plan(
            parent=parent,
            parent_sha256=parent_sha256,
            cell=cell,
            template_id=TEMPLATE_T4,
            steps=steps,
            seed=0,
            donor_slug=None,
        )
        if plan.attempt_sig not in seen_sigs:
            seen_sigs.add(plan.attempt_sig)
            plans.append(plan)
    return plans


def _gate_with_mode(candidates: Sequence[OpParams]) -> list[OpParams]:
    """Return gate-choice candidates with ``mode=gate-choice`` merged in."""
    return [_params(mode="gate-choice", **params.mapping) for params in candidates]


def _retune_with_mode(retune: OpParams) -> OpParams:
    """Return a retune params with ``mode=retune`` merged in."""
    return _params(mode="retune", **retune.mapping)


def _instantiate_template(
    template_id: str, parent: CatalogEntry, catalog: Catalog, cell: Cell
) -> list[AttemptPlan]:
    """Instantiate one template over one parent (dispatch by template id)."""
    if template_id == TEMPLATE_T1:
        return _instantiate_t1(parent, catalog, cell)
    if template_id == TEMPLATE_T2:
        return _instantiate_t2(parent, cell)
    if template_id == TEMPLATE_T3:
        return _instantiate_t3(parent, cell)
    if template_id == TEMPLATE_T4:
        return _instantiate_t4(parent, cell)
    return []


def plan_attempts(
    cell: Cell,
    catalog: Catalog,
    ledger: Mapping[str, str],
    *,
    excluded_parent_slugs: frozenset[str] = _EMPTY_SLUGS,
) -> list[AttemptPlan]:
    """Plan the bounded attempts for a saturated cell (design section 6, S2).

    Enumerates eligible parents (6.1), instantiates the chain templates over them
    in value order (T1 > T2 > T3 > T4, 6.2), skips any attempt whose
    ``attempt_sig`` already has a recorded outcome in ``ledger`` (6.3 replay
    memory), and caps the result at :data:`MAX_ATTEMPTS_PER_CELL` (6.3 budget).

    Every returned plan is precondition-satisfying: its chain was validated by a
    dry-run ``apply_chain`` before it was emitted.

    Args:
        cell: The saturated cell (enum coordinate only).
        catalog: The catalog scan (:func:`load_catalog`).
        ledger: The known ``attempt_sig -> outcome`` map
            (:func:`~cyo_adventure.flywheel.ledger.load_outcomes`); any plan whose
            signature is a key here is skipped.
        excluded_parent_slugs: Parents with an open promotion PR, supplied by the
            caller (design 6.1 rule 4); empty by default.

    Returns:
        list[AttemptPlan]: The planned attempts, in value order, at most
            :data:`MAX_ATTEMPTS_PER_CELL`.
    """
    parents = eligible_parents(
        cell, catalog, excluded_parent_slugs=excluded_parent_slugs
    )
    planned: list[AttemptPlan] = []
    seen_sigs: set[str] = set()
    for template_id in TEMPLATE_ORDER:
        for parent in parents:
            for plan in _instantiate_template(template_id, parent, catalog, cell):
                if plan.attempt_sig in ledger or plan.attempt_sig in seen_sigs:
                    continue
                seen_sigs.add(plan.attempt_sig)
                planned.append(plan)
                if len(planned) >= MAX_ATTEMPTS_PER_CELL:
                    return planned
    return planned


# --- 6.4 ranking and selection ---


@dataclass(frozen=True, slots=True)
class CandidateMetrics:
    """The four ranking metrics for a surviving candidate (design 6.4).

    Attributes:
        min_in_cell_distance: The minimum ``structural_distance`` to any in-cell
            sibling (headroom above ``TAU_CELL``); larger is preferred.
        parent_distance: The ``structural_distance`` from the parent; larger is
            preferred.
        reguide_count: The number of outstanding re-guidance items; fewer is
            preferred (cheaper review).
        seed: The plan's rng seed; lower is the deterministic tiebreak.
    """

    min_in_cell_distance: float
    parent_distance: float
    reguide_count: int
    seed: int


def ranking_key(metrics: CandidateMetrics) -> tuple[float, float, int, int]:
    """Return the sort key that ranks candidates best-first (design 6.4).

    Precedence (each a tiebreak for the previous): (1) larger minimum in-cell
    distance, (2) larger parent distance, (3) fewer re-guidance items, (4) lower
    seed. The first two are negated so a plain ascending ``sorted`` puts the best
    candidate first.

    Args:
        metrics: The candidate's metrics.

    Returns:
        tuple[float, float, int, int]: The ascending sort key.
    """
    return (
        -metrics.min_in_cell_distance,
        -metrics.parent_distance,
        metrics.reguide_count,
        metrics.seed,
    )


def compute_candidate_metrics(  # noqa: PLR0913 -- one cohesive 6.4 metrics computation
    candidate: Mapping[str, object],
    parent: Mapping[str, object],
    in_cell_siblings: Sequence[Mapping[str, object]],
    *,
    reguide_count: int,
    seed: int,
) -> CandidateMetrics:
    """Compute a surviving candidate's ranking metrics (design 6.4).

    Args:
        candidate: The accepted mutant shell.
        parent: The parent document.
        in_cell_siblings: The in-cell sibling documents
            (``mutation.floors.load_in_cell_catalog``); an empty cohort makes the
            minimum in-cell distance infinite (maximally distinct).
        reguide_count: The outstanding re-guidance item count.
        seed: The plan seed.

    Returns:
        CandidateMetrics: The computed metrics.
    """
    min_in_cell = (
        min(structural_distance(sibling, candidate) for sibling in in_cell_siblings)
        if in_cell_siblings
        else inf
    )
    return CandidateMetrics(
        min_in_cell_distance=min_in_cell,
        parent_distance=structural_distance(parent, candidate),
        reguide_count=reguide_count,
        seed=seed,
    )
