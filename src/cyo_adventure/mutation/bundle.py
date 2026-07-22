"""The WS-5 promotion bundle: lineage schema and the bundle writer (design 9.2).

D8. A promotion bundle is the machine-readable hand-off WS-8 promotes behind a
human structure-approval PR (design section 9). It lives under
``out/mutations/<mutant-slug>/`` (gitignored scratch; promotion into
``skeletons/`` is always a reviewed PR, never a script side effect) and contains:

- ``<slug>.json`` -- the gate-passing mutant shell (FILL intact).
- ``<slug>.contract.json`` -- the mutated theme contract (parameterized parents
  only; a contract-less parent's mutant lands contract-less at parity).
- ``<slug>.lineage.json`` -- the versioned provenance record (:class:`Lineage`,
  ADR-020 decision 2 / OQ-1: lineage is a sidecar that versions atomically with
  the tree it explains).
- ``acceptance.json`` -- the full section-6 per-stage transcript.
- ``reguide.json`` -- the emitted re-guidance items and their author resolutions.
- ``sample-fill/`` -- the stage-5 sample-fill evidence (filled JSON + its own
  gate report), or a skip note when no provider was available.
- ``diagram.svg`` (or ``diagram.puml`` under graceful degrade) -- the mutant's
  structure diagram, rendered by ``scripts/render_skeleton_diagrams.py``.

Pure module: standard library plus Pydantic and the ``storybook`` /
``mutation.ops`` value types. It performs filesystem writes only inside
:func:`write_bundle` and reads only inside :func:`verify_bundle`; every timestamp
is supplied by the caller (design principle 5, determinism: no ``datetime.now``
inside a pure function).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.mutation.ops import ParamValue
from cyo_adventure.storybook.theme_contract import (
    SLOT_TOKEN_RE,
    SlotConstraints,
    SlotSpec,
    ThemeContract,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

# The FILL directive parse (matches generation.binding._FILL_RE) so the beats
# surface is scanned identically to the render/contract paths.
_FILL_RE = re.compile(r"^<<FILL role=(\w+) words=(\d+) beats='(.*)'>>$", re.DOTALL)

# A grafted, renamed slot token: ``M<k>_<ORIGINAL_SLOT>`` (design 4.4). Used to
# recover the donor slot id when deriving a mutant contract from a graft chain.
_GRAFT_SLOT_RE = re.compile(r"^M(\d+)_(.+)$")

# The lineage schema version. Bump on any breaking change to the lineage record; a
# reader keys behavior off it so an old bundle stays interpretable. Version 2
# (D5, design 7.2) adds the feed-agnostic ``origin`` discriminator so a WS-6
# ``fresh`` tree or a future ``composed`` tree ships the same bundle contract; the
# v1 :class:`Lineage` schema stays readable and is upgraded to :class:`LineageV2`
# on read.
LINEAGE_VERSION = 2


def content_sha256(document: Mapping[str, object]) -> str:
    """Return the SHA-256 hex digest of a document's canonical JSON form.

    Canonical means sorted keys and no ASCII escaping, so two documents that
    differ only in key order or formatting hash identically while any content
    change is detected. This matches ``acceptance._content_hash`` byte-for-byte,
    so the ``parent_sha256`` recorded here equals the value the acceptance discard
    log emits for the same parent.

    Args:
        document: The document to hash.

    Returns:
        str: The hex digest.
    """
    # #CRITICAL: data-integrity: this digest is what ``verify_bundle`` compares to
    # detect a bundle derived from a since-changed parent (design 9.2 #EDGE). It
    # must be a pure function of content only. SHA-256 is FIPS-approved, so this is
    # safe on FIPS-enabled deployments.
    # #VERIFY: tests/unit/test_mutation_bundle.py asserts identical documents hash
    # identically and any content edit changes the digest, and that verify_bundle
    # hard-fails on a parent hash mismatch.
    canonical = json.dumps(document, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def acceptance_digest(acceptance: Mapping[str, object]) -> str:
    """Return the SHA-256 digest of a serialized acceptance transcript.

    Args:
        acceptance: The ``acceptance_to_dict`` output for this mutant.

    Returns:
        str: The hex digest recorded in the lineage as ``acceptance_digest``.
    """
    return content_sha256(acceptance)


class OpChainEntry(BaseModel):
    """One operator application in a mutant's derivation chain (design 9.2).

    A single-operator mutant has a one-entry chain; a bounded composed chain
    (OQ-7, ``<= 3`` ops) records one entry per applied operator, in application
    order, so any promoted mutant re-derives byte-for-byte from its parent.

    Attributes:
        op_id: The operator's stable id (``M1`` .. ``M5``).
        params: The operator parameters, recorded verbatim (JSON scalars only).
        seed: The rng seed used for this operator's application.
    """

    model_config = ConfigDict(extra="forbid")

    op_id: str = Field(min_length=1)
    params: dict[str, ParamValue] = Field(default_factory=dict)
    seed: int = 0


class Lineage(BaseModel):
    """The v1 provenance record for a promoted mutant (design 9.2).

    This is the ``lineage_version == 1`` schema. It is retained for read
    compatibility: :func:`load_lineage` parses a v1 payload with this model and
    upgrades it to :class:`LineageV2` (``origin="mutation"``) so every in-memory
    consumer sees one canonical shape. New bundles are written at v2 by
    :func:`build_lineage`; nothing produces a v1 record anymore.

    Attributes:
        lineage_version: The schema version (``1`` for this model).
        mutant_slug: The mutant's slug (the bundle directory name).
        parent_slug: The parent skeleton's catalog slug.
        parent_sha256: The parent's canonical content hash at derivation time, so
            a later parent edit cannot silently invalidate the record.
        donor_slugs: The slugs of any M3 graft donors (empty for non-graft
            chains).
        op_chain: The operator chain, in application order.
        created_at: The derivation timestamp (ISO-8601), supplied by the caller.
        tool_version: The package version that produced the bundle.
        acceptance_digest: The digest of the acceptance transcript this mutant
            passed, tying the lineage to the exact acceptance evidence.
    """

    model_config = ConfigDict(extra="forbid")

    lineage_version: int = Field(ge=1)
    mutant_slug: str = Field(min_length=1)
    parent_slug: str = Field(min_length=1)
    parent_sha256: str = Field(min_length=1)
    donor_slugs: list[str] = Field(default_factory=list)
    op_chain: list[OpChainEntry] = Field(min_length=1)
    created_at: str = Field(min_length=1)
    tool_version: str = Field(min_length=1)
    acceptance_digest: str = Field(min_length=1)


class LineageV2(BaseModel):
    """The feed-agnostic v2 provenance record (design 7.2, WS-8 D5).

    Version 2 adds an ``origin`` discriminator so the promotion path is agnostic
    to which workstream produced the tree: a WS-5 ``mutation``, a WS-6 ``fresh``
    tree, or a future ``composed`` tree all ship this one contract. Cross-field
    validators enforce the origin-specific requirements, so the record cannot be
    self-inconsistent (a ``mutation`` without a parent, a ``fresh`` with one):

    - ``origin == "mutation"``: exactly the v1 fields. ``parent_slug``,
      ``parent_sha256``, and a non-empty ``op_chain`` are mandatory; the
      generator fields must be absent. This arm is byte-compatible with v1
      semantics, and :func:`verify_bundle` treats it identically to a v1 record.
    - ``origin == "fresh"`` (WS-6): the generation provenance instead. ``generator``
      and ``generation_params_sha256`` are mandatory; there is no parent
      (``parent_slug`` / ``parent_sha256`` None, ``op_chain`` empty).
    - ``origin == "composed"``: reserved for a future composer and not yet
      produced. Validated minimally (``mutant_slug`` and ``acceptance_digest``
      are required by the field definitions); parent / op_chain stay optional.

    The ``origin`` value is provenance metadata only. It never keys an acceptance
    stage, a floor, or an in-cell clone decision (design 7.2 safety property, and
    the safety-pin test in ``tests/unit/test_mutation_bundle.py``): every
    acceptance stage that applies to a tree applies regardless of its origin.

    Attributes:
        lineage_version: The schema version (``2``).
        origin: The producer discriminator (``mutation`` / ``fresh`` / ``composed``).
        mutant_slug: The tree's slug (the bundle directory name).
        parent_slug: The parent's catalog slug (mutation only; None otherwise).
        parent_sha256: The parent's canonical content hash (mutation only).
        donor_slugs: Any M3 graft donor slugs (empty for non-graft chains).
        op_chain: The operator chain in application order (empty permitted only
            for a non-mutation origin).
        generator: The fresh-generation pipeline id, e.g. ``ws6:<version>`` (fresh
            only; None otherwise).
        generation_params_sha256: The hash of the fresh-generation parameters
            (fresh only).
        created_at: The derivation timestamp (ISO-8601), supplied by the caller.
        tool_version: The package version that produced the bundle.
        acceptance_digest: The digest of the acceptance transcript this tree
            passed, tying the lineage to the exact acceptance evidence.
    """

    model_config = ConfigDict(extra="forbid")

    lineage_version: int = Field(default=LINEAGE_VERSION, ge=2)
    origin: Literal["mutation", "fresh", "composed"]
    mutant_slug: str = Field(min_length=1)
    parent_slug: str | None = None
    parent_sha256: str | None = None
    donor_slugs: list[str] = Field(default_factory=list)
    op_chain: list[OpChainEntry] = Field(default_factory=list)
    generator: str | None = None
    generation_params_sha256: str | None = None
    created_at: str = Field(min_length=1)
    tool_version: str = Field(min_length=1)
    acceptance_digest: str = Field(min_length=1)

    @model_validator(mode="after")
    def _validate_origin_fields(self) -> LineageV2:
        """Enforce the origin-specific field contract (design 7.2)."""
        if self.origin == "mutation":
            if not self.parent_slug or not self.parent_sha256:
                msg = "a 'mutation' lineage must carry parent_slug and parent_sha256"
                raise ValueError(msg)
            if not self.op_chain:
                msg = "a 'mutation' lineage must carry a non-empty op_chain"
                raise ValueError(msg)
            if self.generator is not None or self.generation_params_sha256 is not None:
                msg = "a 'mutation' lineage must not carry generator provenance"
                raise ValueError(msg)
        elif self.origin == "fresh":
            if not self.generator or not self.generation_params_sha256:
                msg = (
                    "a 'fresh' lineage must carry generator and "
                    "generation_params_sha256"
                )
                raise ValueError(msg)
            if self.parent_slug is not None or self.parent_sha256 is not None:
                msg = "a 'fresh' lineage must not carry a parent"
                raise ValueError(msg)
            if self.op_chain:
                msg = "a 'fresh' lineage must carry an empty op_chain"
                raise ValueError(msg)
        # origin == "composed": reserved for a future composer; validated only by
        # the required field definitions. No composer produces it yet.
        return self


def _upgrade_v1_lineage(v1: Lineage) -> LineageV2:
    """Upgrade a parsed v1 :class:`Lineage` to a :class:`LineageV2` mutation record.

    A v1 record is, by definition, a WS-5 mutation with a parent and a non-empty
    op chain, so it maps onto the v2 ``mutation`` arm without loss.

    Args:
        v1: The parsed v1 lineage record.

    Returns:
        LineageV2: The equivalent v2 mutation-origin record.
    """
    return LineageV2(
        lineage_version=LINEAGE_VERSION,
        origin="mutation",
        mutant_slug=v1.mutant_slug,
        parent_slug=v1.parent_slug,
        parent_sha256=v1.parent_sha256,
        donor_slugs=list(v1.donor_slugs),
        op_chain=list(v1.op_chain),
        created_at=v1.created_at,
        tool_version=v1.tool_version,
        acceptance_digest=v1.acceptance_digest,
    )


def load_lineage(raw: str) -> LineageV2:
    """Parse a lineage sidecar's JSON text into a canonical :class:`LineageV2`.

    Keys on ``lineage_version`` (the module's read-compat contract): a v1 payload
    is parsed with :class:`Lineage` and upgraded, and a v2 payload is parsed
    directly. Every consumer therefore handles one shape regardless of the bundle's
    on-disk schema version.

    Args:
        raw: The ``*.lineage.json`` file contents.

    Returns:
        LineageV2: The canonical v2 record.

    Raises:
        pydantic.ValidationError: If the payload does not satisfy the schema (for a
            v2 payload, including the origin-specific cross-field rules), or is not
            a JSON object.
    """
    data = cast("object", json.loads(raw))
    if (
        isinstance(data, dict)
        and cast("dict[str, object]", data).get("lineage_version") == 1
    ):
        return _upgrade_v1_lineage(Lineage.model_validate(data))
    # A v2 payload (or a non-object payload, which pydantic rejects with a
    # ValidationError) is validated directly against the v2 schema.
    return LineageV2.model_validate_json(raw)


def build_lineage(  # noqa: PLR0913 -- one cohesive lineage-record constructor
    *,
    mutant_slug: str,
    parent: Mapping[str, object],
    parent_slug: str,
    op_chain: Sequence[OpChainEntry],
    donor_slugs: Sequence[str],
    created_at: str,
    tool_version: str,
    acceptance: Mapping[str, object],
) -> LineageV2:
    """Build a :class:`LineageV2` mutation record for a mutant (design 9.2 / 7.2).

    Computes the parent content hash and the acceptance digest; the timestamp and
    tool version are supplied by the caller (the CLI boundary), so this stays a
    pure function. The output is a v2 record with ``origin="mutation"``: the
    mutation arm is byte-compatible with v1 semantics, so a promoted mutant
    verifies exactly as it did under v1 (parent-hash gate).

    Args:
        mutant_slug: The mutant's slug.
        parent: The raw parent story document (hashed for ``parent_sha256``).
        parent_slug: The parent's catalog slug.
        op_chain: The operator chain, in application order.
        donor_slugs: Any M3 graft donor slugs.
        created_at: The derivation timestamp (ISO-8601).
        tool_version: The package version producing the bundle.
        acceptance: The serialized acceptance transcript.

    Returns:
        LineageV2: The provenance record (``origin="mutation"``).
    """
    return LineageV2(
        lineage_version=LINEAGE_VERSION,
        origin="mutation",
        mutant_slug=mutant_slug,
        parent_slug=parent_slug,
        parent_sha256=content_sha256(parent),
        donor_slugs=sorted(set(donor_slugs)),
        op_chain=list(op_chain),
        created_at=created_at,
        tool_version=tool_version,
        acceptance_digest=acceptance_digest(acceptance),
    )


def _candidate_slot_tokens(candidate: Mapping[str, object]) -> frozenset[str]:  # noqa: C901 -- one cohesive three-surface token scan
    """Return every ``{SLOT}`` token in a candidate's three slotted surfaces.

    The three ADR-019 slotted surfaces are the ``beats='...'`` segment of a
    ``<<FILL ...>>`` body, an ending title, and a choice label. Reimplemented here
    (as elsewhere in the codebase) so the bundle layer holds no cross-module
    private import.

    Args:
        candidate: The mutant shell to scan.

    Returns:
        frozenset[str]: The slot ids the candidate references.
    """
    tokens: set[str] = set()
    raw_nodes = candidate.get("nodes")
    if not isinstance(raw_nodes, list):
        return frozenset()
    for raw_node in cast("list[object]", raw_nodes):
        if not isinstance(raw_node, dict):
            continue
        node = cast("dict[str, object]", raw_node)
        body = node.get("body")
        if isinstance(body, str):
            match = _FILL_RE.match(body)
            if match is not None:
                tokens.update(cast("list[str]", SLOT_TOKEN_RE.findall(match.group(3))))
        ending = node.get("ending")
        if isinstance(ending, dict):
            title = cast("dict[str, object]", ending).get("title")
            if isinstance(title, str):
                tokens.update(cast("list[str]", SLOT_TOKEN_RE.findall(title)))
        choices = node.get("choices")
        if isinstance(choices, list):
            for raw_choice in cast("list[object]", choices):
                if isinstance(raw_choice, dict):
                    label = cast("dict[str, object]", raw_choice).get("label")
                    if isinstance(label, str):
                        tokens.update(cast("list[str]", SLOT_TOKEN_RE.findall(label)))
    return frozenset(tokens)


def _find_donor_spec(
    original_id: str, donor_contracts: Mapping[str, ThemeContract]
) -> tuple[ThemeContract, SlotSpec] | None:
    """Return the ``(contract, spec)`` declaring ``original_id`` among donors."""
    for contract in donor_contracts.values():
        for spec in contract.slots:
            if spec.id == original_id:
                return contract, spec
    return None


def _kept_host_spec(spec: SlotSpec, present: frozenset[str]) -> SlotSpec:
    """Return a host slot spec with ``distinct_from`` filtered to present slots."""
    return SlotSpec(
        id=spec.id,
        scope=spec.scope,
        meaning=spec.meaning,
        guidance=spec.guidance,
        constraints=SlotConstraints(
            max_words=spec.constraints.max_words,
            forbid=list(spec.constraints.forbid),
            distinct_from=[
                ref for ref in spec.constraints.distinct_from if ref in present
            ],
            pattern=spec.constraints.pattern,
        ),
    )


def _imported_donor_spec(
    token: str, k: int, spec: SlotSpec, present: frozenset[str]
) -> SlotSpec:
    """Return a renamed donor slot spec for a grafted ``M<k>_<slot>`` token."""
    return SlotSpec(
        id=token,
        scope=spec.scope,
        meaning=spec.meaning,
        guidance=spec.guidance,
        constraints=SlotConstraints(
            max_words=spec.constraints.max_words,
            forbid=list(spec.constraints.forbid),
            distinct_from=[
                f"M{k}_{ref}"
                for ref in spec.constraints.distinct_from
                if f"M{k}_{ref}" in present
            ],
            pattern=spec.constraints.pattern,
        ),
    )


def derive_mutant_contract(
    candidate: Mapping[str, object],
    *,
    mutant_slug: str,
    host_contract: ThemeContract,
    donor_contracts: Mapping[str, ThemeContract] | None = None,
) -> ThemeContract | None:
    """Derive a mutant's theme contract from its final tokens (design 4.7 / 4.4).

    Reconciles the contract to the mutant's ACTUAL slot tokens, so it composes
    cleanly across a chain: surviving host slots are kept (with ``distinct_from``
    pruned to present siblings), grafted ``M<k>_<slot>`` tokens are imported from
    the donor contract under their renamed id, and slots no surface references are
    dropped. The result is a fresh contract (version 1) whose slot id set equals
    the mutant's tokens, which is exactly what ``load_contract_for`` and stage-4
    acceptance require.

    Args:
        candidate: The final mutant shell.
        mutant_slug: The mutant's slug (the new ``skeleton_slug``).
        host_contract: The parent (host) skeleton's contract.
        donor_contracts: The graft donors' contracts, keyed by donor slug (include
            the host's own contract for a same-skeleton graft). Defaults to none.

    Returns:
        ThemeContract | None: The mutant contract, or None when the mutant carries
            no slot tokens (it ships contract-less).

    Raises:
        ValidationError: If a token cannot be resolved to a host or donor slot
            (the caller passed an incomplete donor-contract set).
    """
    tokens = _candidate_slot_tokens(candidate)
    if not tokens:
        return None
    donors = dict(donor_contracts) if donor_contracts is not None else {}
    host_by_id = {spec.id: spec for spec in host_contract.slots}
    slots: list[SlotSpec] = []
    binding: dict[str, str] = {}
    legacy: set[str] = set(host_contract.legacy_lexicon)
    for token in sorted(tokens):
        if token in host_by_id:
            slots.append(_kept_host_spec(host_by_id[token], tokens))
            binding[token] = host_contract.default_binding[token]
            continue
        match = _GRAFT_SLOT_RE.match(token)
        found = _find_donor_spec(match.group(2), donors) if match is not None else None
        if match is None or found is None:
            msg = (
                f"cannot derive mutant contract: slot token '{token}' matches no "
                f"host slot and no donor slot (donors: {sorted(donors)})"
            )
            raise ValidationError(msg, field="slots", value=token)
        donor_contract, donor_spec = found
        slots.append(
            _imported_donor_spec(token, int(match.group(1)), donor_spec, tokens)
        )
        binding[token] = donor_contract.default_binding[donor_spec.id]
        legacy |= set(donor_contract.legacy_lexicon)
    return ThemeContract(
        contract_version=1,
        skeleton_slug=mutant_slug,
        age_band=host_contract.age_band,
        legacy_lexicon=sorted(legacy),
        default_binding=binding,
        slots=slots,
    )


def _write_json(path: Path, payload: object) -> None:
    """Write ``payload`` as indented JSON with a trailing newline."""
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def write_bundle(  # noqa: PLR0913 -- one cohesive bundle-directory writer
    out_root: Path,
    *,
    slug: str,
    candidate: Mapping[str, object],
    lineage: Lineage | LineageV2,
    acceptance: Mapping[str, object],
    reguide: Mapping[str, object],
    contract: ThemeContract | None = None,
    sample_fill: Mapping[str, object] | None = None,
    diagram_svg: str | None = None,
    diagram_puml: str | None = None,
) -> Path:
    """Write the full promotion bundle and return its directory (design 9.2).

    Args:
        out_root: The resolved output root (``out/mutations``); the bundle is
            written under ``out_root/<slug>/``.
        slug: The mutant slug (the bundle directory name).
        candidate: The gate-passing mutant shell.
        lineage: The provenance record.
        acceptance: The serialized acceptance transcript.
        reguide: The serialized re-guidance items and resolutions.
        contract: The mutated theme contract, or None for a contract-less mutant.
        sample_fill: The stage-5 sample-fill result (filled doc + gate report or a
            skip note), or None to omit the ``sample-fill/`` directory.
        diagram_svg: The rendered SVG source, when a PlantUML jar was available.
        diagram_puml: The PlantUML source (always available; written as
            ``diagram.puml`` so the diagram survives the no-jar degrade path).

    Returns:
        Path: The bundle directory that was written.
    """
    bundle_dir = out_root / slug
    bundle_dir.mkdir(parents=True, exist_ok=True)

    _write_json(bundle_dir / f"{slug}.json", candidate)
    (bundle_dir / f"{slug}.lineage.json").write_text(
        lineage.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    _write_json(bundle_dir / "acceptance.json", acceptance)
    _write_json(bundle_dir / "reguide.json", reguide)

    if contract is not None:
        (bundle_dir / f"{slug}.contract.json").write_text(
            contract.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )

    if sample_fill is not None:
        fill_dir = bundle_dir / "sample-fill"
        fill_dir.mkdir(parents=True, exist_ok=True)
        _write_json(fill_dir / "result.json", sample_fill)
        filled = sample_fill.get("filled")
        if isinstance(filled, dict):
            _write_json(fill_dir / "filled.json", cast("dict[str, object]", filled))
        gate = sample_fill.get("gate")
        if isinstance(gate, dict):
            _write_json(fill_dir / "gate.json", cast("dict[str, object]", gate))

    if diagram_puml is not None:
        (bundle_dir / "diagram.puml").write_text(diagram_puml, encoding="utf-8")
    if diagram_svg is not None:
        (bundle_dir / "diagram.svg").write_text(diagram_svg, encoding="utf-8")

    return bundle_dir


@dataclass(frozen=True, slots=True)
class VerifyResult:
    """The outcome of a bundle verification (design 9.2 / 7.2).

    The verified quantity depends on the lineage ``origin`` (see
    :func:`verify_bundle`): a ``mutation`` bundle verifies its parent hash against
    the live catalog, while a ``fresh`` bundle (no parent to go stale) verifies its
    acceptance digest against the recomputed ``acceptance.json`` digest. The
    ``expected_sha256`` / ``actual_sha256`` fields carry whichever digest applies.

    Attributes:
        ok: True only when the applicable digest was recomputed and matched.
        message: A human-readable explanation (the mismatch detail when not ok).
        expected_sha256: The digest recorded in the lineage (parent hash for a
            mutation, acceptance digest for a fresh bundle).
        actual_sha256: The recomputed digest, or None when it could not be computed
            (parent file absent, acceptance file absent, or a reserved origin).
    """

    ok: bool
    message: str
    expected_sha256: str
    actual_sha256: str | None


def _load_lineage(bundle_dir: Path) -> LineageV2:
    """Load and validate the ``<slug>.lineage.json`` in a bundle directory.

    Keys on ``lineage_version`` via :func:`load_lineage`: a v1 sidecar is parsed
    and upgraded to a :class:`LineageV2` mutation record, and a v2 sidecar is
    parsed directly, so the caller always receives the canonical v2 shape.

    Args:
        bundle_dir: The bundle directory.

    Returns:
        LineageV2: The validated, canonical lineage record.

    Raises:
        FileNotFoundError: If no ``*.lineage.json`` sidecar exists in the bundle.
    """
    matches = sorted(bundle_dir.glob("*.lineage.json"))
    if not matches:
        msg = f"no *.lineage.json found in bundle directory {bundle_dir}"
        raise FileNotFoundError(msg)
    return load_lineage(matches[0].read_text(encoding="utf-8"))


def _find_parent_file(skeletons_root: Path, parent_slug: str) -> Path | None:
    """Return the parent skeleton file under the catalog, or None when absent."""
    matches = sorted(skeletons_root.glob(f"*/{parent_slug}.json"))
    return matches[0] if matches else None


def verify_bundle(bundle_dir: Path, *, skeletons_root: Path) -> VerifyResult:
    """Verify a bundle against the live catalog, branching on lineage origin.

    The verification is feed-agnostic (design 7.2): it keys on the lineage
    ``origin``, not on which workstream produced the tree.

    - ``mutation``: the byte-identical WS-5 parent-hash gate. Recomputes the live
      parent's canonical content hash and compares it to the recorded
      ``parent_sha256``; a mismatch (or a missing parent) is a HARD failure,
      because the acceptance evidence no longer describes the tree on disk.
    - ``fresh``: there is no parent to go stale, so the staleness gate becomes an
      acceptance-digest match (recompute the digest from the bundle's
      ``acceptance.json`` and compare to the recorded ``acceptance_digest``).
    - ``composed``: reserved and not yet produced; reported as unverifiable.

    The origin selects only WHICH recorded evidence is re-attested; it relaxes no
    acceptance stage (design 7.2 safety property).

    Args:
        bundle_dir: The promotion bundle directory (contains ``*.lineage.json``).
        skeletons_root: The catalog root the parent slug is resolved under
            (used by the ``mutation`` branch only).

    Returns:
        VerifyResult: ``ok`` true only when the origin's applicable digest matches;
            otherwise a failing result with the reason.
    """
    lineage = _load_lineage(bundle_dir)
    if lineage.origin == "fresh":
        return _verify_fresh_bundle(bundle_dir, lineage)
    if lineage.origin == "composed":
        return VerifyResult(
            ok=False,
            message=(
                "lineage origin 'composed' is reserved and not yet produced; "
                "this bundle cannot be verified"
            ),
            expected_sha256=lineage.acceptance_digest,
            actual_sha256=None,
        )
    return _verify_mutation_bundle(skeletons_root, lineage)


def _verify_mutation_bundle(skeletons_root: Path, lineage: LineageV2) -> VerifyResult:
    """Verify a mutation bundle's parent hash against the live catalog (design 9.2).

    Byte-identical to the pre-D5 ``verify_bundle`` behavior for a mutation record.
    """
    # #EDGE: data-integrity: a promotion PR could be opened from a stale bundle
    # after the parent skeleton changed on main; this parent_sha256 mismatch is the
    # hard gate the design's D8 promotion runbook step 1 relies on (design 9.2).
    # A missing parent file is also a failure: an unverifiable bundle must not
    # promote.
    # #VERIFY: tests/unit/test_mutation_bundle.py asserts a matching parent
    # verifies ok and an edited parent hard-fails with a mismatch message.
    parent_slug = lineage.parent_slug
    expected = lineage.parent_sha256
    if parent_slug is None or expected is None:
        # Unreachable for a validated mutation record (the cross-field validator
        # requires both); defensive so a hand-built record cannot bypass the gate.
        return VerifyResult(
            ok=False,
            message="mutation lineage is missing its parent reference; cannot verify",
            expected_sha256=expected or "",
            actual_sha256=None,
        )
    parent_path = _find_parent_file(skeletons_root, parent_slug)
    if parent_path is None:
        return VerifyResult(
            ok=False,
            message=(
                f"parent '{parent_slug}' not found under {skeletons_root}; "
                f"cannot verify the bundle"
            ),
            expected_sha256=expected,
            actual_sha256=None,
        )
    parent_document = cast(
        "dict[str, object]",
        json.loads(parent_path.read_text(encoding="utf-8")),
    )
    actual = content_sha256(parent_document)
    if actual != expected:
        return VerifyResult(
            ok=False,
            message=(
                f"parent hash mismatch for '{parent_slug}': the parent "
                f"changed since derivation (expected {expected}, "
                f"recomputed {actual}); this bundle must not promote"
            ),
            expected_sha256=expected,
            actual_sha256=actual,
        )
    return VerifyResult(
        ok=True,
        message=(
            f"parent hash verified for '{parent_slug}' ({actual}); the "
            f"bundle matches the live catalog parent"
        ),
        expected_sha256=expected,
        actual_sha256=actual,
    )


def _verify_fresh_bundle(bundle_dir: Path, lineage: LineageV2) -> VerifyResult:
    """Verify a fresh bundle's acceptance digest against its ``acceptance.json``.

    A fresh (WS-6) tree has no parent, so verification re-attests the acceptance
    evidence: recompute the digest of the bundle's ``acceptance.json`` and compare
    it to the ``acceptance_digest`` the lineage recorded (design 7.2).
    """
    # #EDGE: data-integrity: a fresh bundle has no parent-hash staleness gate, so a
    # tampered acceptance.json is the analogous hazard; recomputing the digest and
    # comparing catches it. This chooses the evidence to re-attest, not whether any
    # acceptance stage ran: a fresh candidate still passes the full gate at
    # acceptance time (design 7.2 safety property).
    acceptance_path = bundle_dir / "acceptance.json"
    if not acceptance_path.is_file():
        return VerifyResult(
            ok=False,
            message=(
                f"no acceptance.json in {bundle_dir}; cannot verify a fresh "
                f"bundle's acceptance digest"
            ),
            expected_sha256=lineage.acceptance_digest,
            actual_sha256=None,
        )
    acceptance_document = cast(
        "dict[str, object]",
        json.loads(acceptance_path.read_text(encoding="utf-8")),
    )
    actual = acceptance_digest(acceptance_document)
    if actual != lineage.acceptance_digest:
        return VerifyResult(
            ok=False,
            message=(
                f"acceptance digest mismatch for fresh tree '{lineage.mutant_slug}': "
                f"acceptance.json changed since bundling (expected "
                f"{lineage.acceptance_digest}, recomputed {actual}); this bundle "
                f"must not promote"
            ),
            expected_sha256=lineage.acceptance_digest,
            actual_sha256=actual,
        )
    return VerifyResult(
        ok=True,
        message=(
            f"acceptance digest verified for fresh tree '{lineage.mutant_slug}' "
            f"({actual}); the bundle matches its recorded acceptance evidence"
        ),
        expected_sha256=lineage.acceptance_digest,
        actual_sha256=actual,
    )
