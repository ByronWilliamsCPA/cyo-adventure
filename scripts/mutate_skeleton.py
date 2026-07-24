"""Mutate one catalog skeleton, run acceptance, and write a promotion bundle (D8).

Three modes:

- **Single operator** (``--op M3 --params mode=graft ...``): apply one operator.
- **Chain** (``--chain chain.json``): apply a bounded chain (``<= 3`` ops, OQ-7)
  read from a JSON step file (a list of ``{"op", "params", "seed"}`` objects),
  each op fed the previous op's candidate. The highest-value mutants pair a
  structural op with an outcome re-map (design OQ-7), which single ops (usually
  below ``TAU_STRUCT``) cannot reach.
- **Verify** (``--verify-bundle <dir>``): recompute the parent hash of an
  existing bundle and hard-fail on a mismatch (design 9.2 #EDGE: a bundle derived
  from a since-changed parent must not promote).

On acceptance the writer emits the full section-9.2 promotion bundle under
``<out-dir>/<mutant-slug>/``: the mutant shell, its lineage sidecar, the mutated
theme contract (parameterized parents), the acceptance transcript, the reguide
resolutions, the stage-5 sample-fill evidence, and the structure diagram. On any
stage discard it exits non-zero and writes nothing.

Re-guidance: D2-D7 leave an accepted mutant *held* (re-guidance outstanding).
Supply ``--resolve resolutions.json`` (an author resolution file) to record the
new beats/labels and let a fully-resolved mutant become promotable (then it faces
the D7 anti-clone floor). Sample-fill uses a deterministic mock provider with
``--sample-fill-mock`` (no live LLM); otherwise it is recorded as skipped.

Promotion into ``skeletons/`` is always a reviewed human PR, never a script side
effect (design CR-1), which is why the CLI refuses to write anywhere under
``skeletons/``.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

from pydantic import ValidationError as PydanticValidationError

from cyo_adventure import __version__
from cyo_adventure.core.exceptions import ValidationError

# Importing the mutation package runs its __init__, registering every operator
# (M1..M5) in the default REGISTRY and exposing the D8 bundle/chain/reguide API.
from cyo_adventure.generation.diagram import skeleton_to_plantuml
from cyo_adventure.mutation.acceptance import acceptance_to_dict
from cyo_adventure.mutation.bundle import (
    build_lineage,
    derive_mutant_contract,
    verify_bundle,
    write_bundle,
)
from cyo_adventure.mutation.compose import ChainStep, apply_chain, run_chain_acceptance
from cyo_adventure.mutation.ops import OpParams, ParamValue
from cyo_adventure.mutation.reguide import (
    ReguideResolutions,
    load_resolutions,
    reconcile,
    resolved_ids,
)
from cyo_adventure.mutation.sample_fill import run_mock_sample_fill, skipped_result
from cyo_adventure.storybook.theme_contract import ThemeContract

if TYPE_CHECKING:
    from cyo_adventure.mutation.compose import ChainResult

_INT_RE = re.compile(r"^-?\d+$")
_REPO_ROOT = Path(__file__).resolve().parent.parent
_SKELETONS_ROOT = _REPO_ROOT / "skeletons"


def _coerce(raw: str) -> ParamValue:
    """Coerce a ``k=v`` value string to a JSON scalar."""
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if _INT_RE.match(raw):
        return int(raw)
    return raw


def _params_from_tokens(tokens: list[str]) -> OpParams:
    """Parse ``--params`` ``k=v`` tokens into operator parameters."""
    values: dict[str, ParamValue] = {}
    for token in tokens:
        if "=" not in token:
            msg = f"--params entry '{token}' is not of the form key=value"
            raise ValueError(msg)
        key, raw = token.split("=", 1)
        if not key:
            msg = f"--params entry '{token}' has an empty key"
            raise ValueError(msg)
        values[key] = _coerce(raw)
    return OpParams.of(**values)


def _params_from_obj(obj: object) -> OpParams:
    """Build OpParams from a JSON object of scalar values (a chain step)."""
    if not isinstance(obj, dict):
        msg = "chain step 'params' must be a JSON object"
        raise ValueError(msg)
    values: dict[str, ParamValue] = {}
    for key, value in cast("dict[str, object]", obj).items():
        if not isinstance(value, str | int | float | bool) and value is not None:
            msg = f"chain step param '{key}' must be a JSON scalar"
            raise ValueError(msg)
        values[key] = value
    return OpParams.of(**values)


def _parse_chain_file(path: Path) -> list[ChainStep]:
    """Parse a chain step file into ChainStep objects (a JSON list of steps)."""
    raw: object = json.loads(path.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
    if not isinstance(raw, list):
        msg = f"chain file {path} must contain a JSON list of steps"
        raise ValueError(msg)
    steps: list[ChainStep] = []
    for entry in cast("list[object]", raw):
        if not isinstance(entry, dict):
            msg = "each chain step must be a JSON object with 'op'"
            raise ValueError(msg)
        step = cast("dict[str, object]", entry)
        op = step.get("op")
        if not isinstance(op, str):
            msg = "chain step 'op' must be a string operator id"
            raise ValueError(msg)
        seed_raw = step.get("seed", 0)
        seed = seed_raw if isinstance(seed_raw, int) else 0
        steps.append(
            ChainStep(
                op_id=op, params=_params_from_obj(step.get("params", {})), seed=seed
            )
        )
    return steps


def _step_sig(step: ChainStep) -> str:
    """Return a compact, collision-safe slug fragment for one chain step.

    Includes the mode/variant so, per the D4/D5 note, a prune and a graft at the
    same seed no longer collide on ``<parent>-<op>-s<seed>``.
    """
    parts = [step.op_id.lower()]
    for key in ("mode", "variant"):
        value = step.params.get(key)
        if isinstance(value, str):
            parts.append(value.replace("-", "").replace("_", ""))
    return "".join(parts) + f"-s{step.seed}"


def _derive_slug(parent_slug: str, steps: list[ChainStep]) -> str:
    """Return the mutant slug, including each step's op/mode/seed (collision-safe)."""
    if len(steps) == 1:
        return f"{parent_slug}-{_step_sig(steps[0])}"
    return f"{parent_slug}-chain-" + "-".join(_step_sig(s) for s in steps)


def _refuses_under_skeletons(out_dir: Path) -> bool:
    """Return whether ``out_dir`` resolves to a path under a ``skeletons`` dir."""
    # #CRITICAL: security: promotion into the catalog is a reviewed human PR, never
    # a script side effect (design CR-1). The out-dir is resolved and refused
    # whenever any component is ``skeletons``, the over-refusing direction: a
    # mutant must never be writable straight into the child-facing catalog.
    # #VERIFY: test_mutate_skeleton_cli.py asserts an --out-dir under skeletons/
    # exits non-zero and writes nothing.
    return "skeletons" in out_dir.resolve().parts


def _load_json_doc(path: Path) -> dict[str, object]:
    """Load a JSON object document from disk."""
    data: object = json.loads(path.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
    if not isinstance(data, dict):
        msg = f"expected a JSON object in {path}"
        raise ValueError(msg)
    return cast("dict[str, object]", data)


def _load_contract(slug: str) -> ThemeContract | None:
    """Load a skeleton's theme contract by slug, or None when it is contract-less."""
    matches = sorted(_SKELETONS_ROOT.glob(f"*/{slug}.contract.json"))
    if not matches:
        return None
    return ThemeContract.model_validate_json(matches[0].read_text(encoding="utf-8"))


def _mutant_contract(
    chain: ChainResult, parent_slug: str, mutant_slug: str
) -> ThemeContract | None:
    """Derive the mutant's theme contract (parameterized parents), or None.

    The host contract is the parent's; donor contracts are loaded for any M3 graft
    donor slug recorded in the chain. A contract-less parent whose mutant carries
    no slot tokens returns None (contract parity, design 4.7 / OQ-2).
    """
    host_contract = _load_contract(parent_slug)
    if host_contract is None:
        return None
    donor_contracts: dict[str, ThemeContract] = {parent_slug: host_contract}
    for donor_slug in chain.donor_slugs:
        donor_contract = _load_contract(donor_slug)
        if donor_contract is not None:
            donor_contracts[donor_slug] = donor_contract
    return derive_mutant_contract(
        chain.candidate,
        mutant_slug=mutant_slug,
        host_contract=host_contract,
        donor_contracts=donor_contracts,
    )


def _render_svg(puml_path: Path) -> Path | None:
    """Render a diagram ``.puml`` to ``.svg`` beside it, or None (graceful degrade).

    Reuses the SHA-verified PlantUML jar resolution and renderer from
    ``scripts/render_skeleton_diagrams.py`` (never re-implemented). Returns None
    when no verified jar is available, matching that script's degrade posture (the
    ``.puml`` is always written regardless).
    """
    # Ensure the repository root is importable so the sibling script resolves when
    # this file is run directly (sys.path[0] is scripts/, not the repo root).
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from scripts.render_skeleton_diagrams import (  # noqa: PLC0415
        render_svgs,
        resolve_jar,
    )

    jar = resolve_jar()
    if jar is None:
        return None
    rendered = render_svgs([puml_path], jar=jar)
    return rendered[0] if rendered else None


def _run_verify(bundle_dir: Path) -> int:
    """Run the ``--verify-bundle`` mode and return a process exit code."""
    result = verify_bundle(bundle_dir, skeletons_root=_SKELETONS_ROOT)
    if result.ok:
        sys.stdout.write(f"OK: {result.message}\n")
        return 0
    sys.stderr.write(f"VERIFY FAILED: {result.message}\n")
    return 1


def _build_steps(args: argparse.Namespace) -> list[ChainStep]:
    """Build the chain steps from either --chain or the single --op form."""
    chain_path: str | None = args.chain  # pyright: ignore[reportAny]
    if chain_path is not None:
        # #ASSUME: security: canonicalized with .resolve() (CWE-23 hardening,
        # Snyk python/PT), but deliberately NOT contained to a fixed base:
        # tests/unit/test_mutation_compose.py::test_cli_chain_writes_bundle
        # exercises --chain against a pytest tmp_path fixture well outside
        # the repo tree with no chdir, proving arbitrary-location paths are
        # legitimate, exercised behavior that containment would reject. No
        # privilege boundary is crossed either way: the operator invoking
        # this dev-only mutation CLI already has full filesystem access.
        # #VERIFY: any future change adding a fixed base must re-run
        # test_mutation_compose.py first; a rejection there means real
        # behavior broke.
        return _parse_chain_file(Path(chain_path).resolve())
    op_id: str = args.op  # pyright: ignore[reportAny]
    param_tokens: list[str] = list(args.params)  # pyright: ignore[reportAny]
    seed: int = args.seed  # pyright: ignore[reportAny]
    return [ChainStep(op_id=op_id, params=_params_from_tokens(param_tokens), seed=seed)]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parent", nargs="?", help="Path to the parent skeleton JSON.")
    parser.add_argument(
        "--op", help="Operator id for a single-op mutation (e.g. 'M3')."
    )
    parser.add_argument(
        "--params",
        nargs="*",
        default=[],
        metavar="KEY=VALUE",
        help="Single-op parameters, for example mode=graft donor=some-slug.",
    )
    parser.add_argument("--seed", type=int, default=0, help="Rng seed (default 0).")
    parser.add_argument(
        "--chain",
        metavar="FILE",
        help="A JSON file of chain steps (<=3), each {op, params, seed}.",
    )
    parser.add_argument(
        "--resolve",
        metavar="FILE",
        help="An author re-guidance resolution file (JSON) to record and apply.",
    )
    parser.add_argument(
        "--sample-fill-mock",
        action="store_true",
        help="Run the stage-5 sample fill with a deterministic mock provider.",
    )
    parser.add_argument(
        "--no-svg", action="store_true", help="Skip SVG rendering of the diagram."
    )
    parser.add_argument("--out-dir", help="Directory to write the mutant bundle under.")
    parser.add_argument(
        "--verify-bundle",
        metavar="DIR",
        help="Verify an existing bundle's parent hash and exit (no mutation).",
    )
    return parser


def _write_and_report(
    args: argparse.Namespace,
    *,
    parent: dict[str, object],
    parent_slug: str,
    slug: str,
    chain: ChainResult,
    resolutions: ReguideResolutions,
) -> int:
    """Run acceptance, write the bundle, and report; return the exit code."""
    mutated_contract = _mutant_contract(chain, parent_slug, slug)
    result = run_chain_acceptance(
        parent,
        chain,
        parent_slug=parent_slug,
        resolved_reguide_ids=resolved_ids(resolutions),
        mutated_contract=mutated_contract,
    )
    if result.discarded_at_stage is not None:
        sys.stderr.write(
            f"discarded at stage {result.discarded_at_stage}: {result.discard_reason}\n"
        )
        return 1
    candidate = result.candidate
    if candidate is None:
        sys.stderr.write("error: acceptance produced no candidate to write\n")
        return 1

    acceptance = acceptance_to_dict(result)
    lineage = build_lineage(
        mutant_slug=slug,
        parent=parent,
        parent_slug=parent_slug,
        op_chain=list(chain.op_chain),
        donor_slugs=chain.donor_slugs,
        created_at=datetime.datetime.now(datetime.UTC).isoformat(),
        tool_version=__version__,
        acceptance=acceptance,
    )
    use_mock: bool = args.sample_fill_mock  # pyright: ignore[reportAny]
    sample = (
        run_mock_sample_fill(candidate, contract=mutated_contract)
        if use_mock
        else skipped_result("no provider; pass --sample-fill-mock for mock evidence")
    )
    out_root = Path(cast("str", args.out_dir)).resolve()
    diagram_puml = skeleton_to_plantuml(candidate, name=slug)
    bundle_dir = write_bundle(
        out_root,
        slug=slug,
        candidate=candidate,
        lineage=lineage,
        acceptance=acceptance,
        reguide=reconcile(chain.reguide, resolutions),
        contract=mutated_contract,
        sample_fill=sample.to_dict(),
        diagram_puml=diagram_puml,
    )
    svg_note = "diagram.puml"
    no_svg: bool = args.no_svg  # pyright: ignore[reportAny]
    if not no_svg and _render_svg(bundle_dir / "diagram.puml") is not None:
        svg_note = "diagram.puml + diagram.svg"

    status = "promotable" if result.promotable else "held (re-guidance outstanding)"
    contract_note = "contract, " if mutated_contract is not None else ""
    head = f"accepted [{status}]: wrote {bundle_dir}/ "
    body = f"(shell, lineage, {contract_note}acceptance, reguide, sample-fill, {svg_note}); "
    tail = f"reguide_outstanding={result.reguide_outstanding}\n"
    sys.stdout.write(head + body + tail)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Mutate one skeleton (single op or chain), run acceptance, write a bundle."""
    args = _build_parser().parse_args(argv)

    # #ASSUME: security: --verify-bundle/parent/--resolve are canonicalized
    # with .resolve() below (CWE-23 hardening, Snyk python/PT), but
    # deliberately NOT contained to a fixed base (the containment approach of
    # generation/import_cli.py::_load_blob). --out-dir is NOT .resolve()'d in
    # this flow; it is guarded separately by the pre-existing, more targeted
    # ``_refuses_under_skeletons`` denylist (design CR-1). Every one of these
    # is exercised in tests/unit/test_mutation_acceptance.py and
    # tests/unit/test_mutation_compose.py against pytest tmp_path fixtures
    # well outside the repo tree with no chdir, proving arbitrary-location
    # paths are legitimate, exercised behavior that containment would
    # reject. No privilege boundary is crossed either way: the operator
    # invoking this dev-only mutation CLI already has full filesystem
    # access.
    # #VERIFY: any future change adding a fixed base must re-run both test
    # files first; a rejection there means real behavior broke.
    verify_dir: str | None = args.verify_bundle  # pyright: ignore[reportAny]
    if verify_dir is not None:
        return _run_verify(Path(verify_dir).resolve())

    parent_arg: str | None = args.parent  # pyright: ignore[reportAny]
    out_dir_arg: str | None = args.out_dir  # pyright: ignore[reportAny]
    op_arg: str | None = args.op  # pyright: ignore[reportAny]
    chain_arg: str | None = args.chain  # pyright: ignore[reportAny]
    if parent_arg is None or out_dir_arg is None:
        sys.stderr.write("error: parent and --out-dir are required for a mutation\n")
        return 1
    if (op_arg is None) == (chain_arg is None):
        sys.stderr.write("error: pass exactly one of --op or --chain\n")
        return 1

    out_dir = Path(out_dir_arg)
    if _refuses_under_skeletons(out_dir):
        head = f"refusing: --out-dir {out_dir} resolves under a skeletons/ directory; "
        tail = "promotion into the catalog is a reviewed PR, never a script write\n"
        sys.stderr.write(head + tail)
        return 1

    parent_path = Path(parent_arg).resolve()
    try:
        parent = _load_json_doc(parent_path)
        steps = _build_steps(args)
    except (OSError, json.JSONDecodeError, ValueError, PydanticValidationError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    parent_slug = parent_path.stem
    slug = _derive_slug(parent_slug, steps)

    resolve_path: str | None = args.resolve  # pyright: ignore[reportAny]
    try:
        resolutions = (
            load_resolutions(Path(resolve_path).resolve())
            if resolve_path is not None
            else ReguideResolutions(resolutions=[])
        )
        chain = apply_chain(parent, steps)
    except (OSError, ValueError, ValidationError, PydanticValidationError) as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    return _write_and_report(
        args,
        parent=parent,
        parent_slug=parent_slug,
        slug=slug,
        chain=chain,
        resolutions=resolutions,
    )


if __name__ == "__main__":
    raise SystemExit(main())
