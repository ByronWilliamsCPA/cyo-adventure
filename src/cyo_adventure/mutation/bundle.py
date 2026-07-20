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
from typing import TYPE_CHECKING, cast

from pydantic import BaseModel, ConfigDict, Field

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

# The lineage schema version. Bump on any breaking change to :class:`Lineage`; a
# reader keys behavior off it so an old bundle stays interpretable.
LINEAGE_VERSION = 1


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
    """The versioned provenance record for a promoted mutant (design 9.2).

    Attributes:
        lineage_version: The :data:`LINEAGE_VERSION` this record was written at.
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
) -> Lineage:
    """Build a :class:`Lineage` record for a mutant (design 9.2).

    Computes the parent content hash and the acceptance digest; the timestamp and
    tool version are supplied by the caller (the CLI boundary), so this stays a
    pure function.

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
        Lineage: The provenance record.
    """
    return Lineage(
        lineage_version=LINEAGE_VERSION,
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
    lineage: Lineage,
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
    """The outcome of a bundle parent-hash verification.

    Attributes:
        ok: True only when the parent was found and its hash matches the lineage.
        message: A human-readable explanation (the mismatch detail when not ok).
        expected_sha256: The parent hash recorded in the lineage.
        actual_sha256: The recomputed parent hash, or None when the parent file
            could not be located.
    """

    ok: bool
    message: str
    expected_sha256: str
    actual_sha256: str | None


def _load_lineage(bundle_dir: Path) -> Lineage:
    """Load and validate the ``<slug>.lineage.json`` in a bundle directory.

    Args:
        bundle_dir: The bundle directory.

    Returns:
        Lineage: The validated lineage record.

    Raises:
        FileNotFoundError: If no ``*.lineage.json`` sidecar exists in the bundle.
    """
    matches = sorted(bundle_dir.glob("*.lineage.json"))
    if not matches:
        msg = f"no *.lineage.json found in bundle directory {bundle_dir}"
        raise FileNotFoundError(msg)
    return Lineage.model_validate_json(matches[0].read_text(encoding="utf-8"))


def _find_parent_file(skeletons_root: Path, parent_slug: str) -> Path | None:
    """Return the parent skeleton file under the catalog, or None when absent."""
    matches = sorted(skeletons_root.glob(f"*/{parent_slug}.json"))
    return matches[0] if matches else None


def verify_bundle(bundle_dir: Path, *, skeletons_root: Path) -> VerifyResult:
    """Verify a bundle's parent hash against the live catalog (design 9.2 #EDGE).

    Recomputes the current parent's canonical content hash and compares it to the
    ``parent_sha256`` the lineage recorded at derivation time. A mismatch is a
    HARD failure: a bundle derived from a since-changed parent must not promote,
    because its acceptance evidence no longer describes the tree on disk.

    Args:
        bundle_dir: The promotion bundle directory (contains ``*.lineage.json``).
        skeletons_root: The catalog root the parent slug is resolved under.

    Returns:
        VerifyResult: ``ok`` true only when the parent is found and its hash
            matches; otherwise a failing result with the reason.
    """
    # #EDGE: data-integrity: a promotion PR could be opened from a stale bundle
    # after the parent skeleton changed on main; this parent_sha256 mismatch is the
    # hard gate the design's D8 promotion runbook step 1 relies on (design 9.2).
    # A missing parent file is also a failure: an unverifiable bundle must not
    # promote.
    # #VERIFY: tests/unit/test_mutation_bundle.py asserts a matching parent
    # verifies ok and an edited parent hard-fails with a mismatch message.
    lineage = _load_lineage(bundle_dir)
    parent_path = _find_parent_file(skeletons_root, lineage.parent_slug)
    if parent_path is None:
        return VerifyResult(
            ok=False,
            message=(
                f"parent '{lineage.parent_slug}' not found under {skeletons_root}; "
                f"cannot verify the bundle"
            ),
            expected_sha256=lineage.parent_sha256,
            actual_sha256=None,
        )
    parent_document = cast(
        "dict[str, object]",
        json.loads(parent_path.read_text(encoding="utf-8")),
    )
    actual = content_sha256(parent_document)
    if actual != lineage.parent_sha256:
        return VerifyResult(
            ok=False,
            message=(
                f"parent hash mismatch for '{lineage.parent_slug}': the parent "
                f"changed since derivation (expected {lineage.parent_sha256}, "
                f"recomputed {actual}); this bundle must not promote"
            ),
            expected_sha256=lineage.parent_sha256,
            actual_sha256=actual,
        )
    return VerifyResult(
        ok=True,
        message=(
            f"parent hash verified for '{lineage.parent_slug}' ({actual}); the "
            f"bundle matches the live catalog parent"
        ),
        expected_sha256=lineage.parent_sha256,
        actual_sha256=actual,
    )
