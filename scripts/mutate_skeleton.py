"""Mutate one catalog skeleton and run the WS-5 acceptance harness (D2).

Usage::

    uv run python scripts/mutate_skeleton.py <parent.json> --op <id> \\
        [--params k=v ...] [--seed N] --out-dir out/mutations/

Runs the design section 6 stage table (D2 subset) end to end: operator
preconditions, apply, then the full unchanged gate and the cell assertion. On
any stage discard it exits non-zero and writes nothing. On acceptance it writes
a minimal bundle under ``<out-dir>/<mutant-slug>/``: the candidate shell and an
``acceptance.json`` transcript. The full promotion bundle (lineage.json,
sample-fill, diagram) is D8, so this writer is deliberately minimal.

An accepted M1 mutant is *held*, not promotable, in D2: its four re-guidance
items are unresolved (the reguide.json resolution flow is D8), so the shell is
written for review but is never a promotable artifact. Promotion is always a
human skeletons/ PR, never a script side effect (design CR-1), which is why the
CLI refuses to write anywhere under ``skeletons/``.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import cast

# Importing the mutation package runs its __init__, which imports the operators
# module and so registers every operator (M1, ...) in the default REGISTRY. The
# CLI resolves ``--op`` against that registry.
from cyo_adventure.mutation.acceptance import acceptance_to_dict, run_acceptance
from cyo_adventure.mutation.ops import REGISTRY, OpParams, ParamValue

_INT_RE = re.compile(r"^-?\d+$")


def _coerce(raw: str) -> ParamValue:
    """Coerce a ``k=v`` value string to a JSON scalar.

    ``true``/``false`` become booleans, an all-digit token (optional sign)
    becomes an int, and everything else stays a string (choice ids, slugs).

    Args:
        raw: The raw value text.

    Returns:
        ParamValue: The coerced scalar.
    """
    lowered = raw.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if _INT_RE.match(raw):
        return int(raw)
    return raw


def _parse_params(tokens: list[str]) -> OpParams:
    """Parse ``--params`` ``k=v`` tokens into operator parameters.

    Args:
        tokens: The raw ``k=v`` strings.

    Returns:
        OpParams: The parsed, canonically ordered parameters.

    Raises:
        ValueError: If a token is not of the form ``key=value``.
    """
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


def _refuses_under_skeletons(out_dir: Path) -> bool:
    """Return whether ``out_dir`` resolves to a path under a ``skeletons`` dir.

    Args:
        out_dir: The requested output directory.

    Returns:
        bool: True when the resolved path has a ``skeletons`` component.
    """
    # #CRITICAL: security: promotion into the catalog is a reviewed human PR,
    # never a script side effect (design CR-1). The out-dir is resolved to an
    # absolute path and refused whenever any component is ``skeletons``, the safe
    # (over-refusing) direction: a mutant must never be writable straight into
    # the child-facing catalog, even via a symlink or ``..`` traversal.
    # #VERIFY: test_mutate_skeleton_cli.py asserts an --out-dir under skeletons/
    # exits non-zero and writes nothing.
    return "skeletons" in out_dir.resolve().parts


def _load_parent(path: Path) -> dict[str, object]:
    """Load the parent skeleton JSON document.

    Args:
        path: The parent skeleton path.

    Returns:
        dict[str, object]: The decoded document.

    Raises:
        OSError: If the file cannot be read.
        json.JSONDecodeError: If the file is not valid JSON.
        ValueError: If the top-level JSON value is not an object.
    """
    data: object = json.loads(path.read_text(encoding="utf-8"))  # pyright: ignore[reportAny]
    if not isinstance(data, dict):
        msg = f"expected a JSON object in {path}"
        raise ValueError(msg)
    return cast("dict[str, object]", data)


def _write_bundle(
    out_root: Path,
    slug: str,
    candidate: dict[str, object],
    acceptance: dict[str, object],
) -> Path:
    """Write the minimal D2 bundle and return its directory.

    Args:
        out_root: The resolved output root directory.
        slug: The mutant slug (bundle directory name).
        candidate: The candidate shell to write.
        acceptance: The serialized acceptance transcript.

    Returns:
        Path: The bundle directory that was written.
    """
    bundle_dir = out_root / slug
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / f"{slug}.json").write_text(
        json.dumps(candidate, indent=2) + "\n", encoding="utf-8"
    )
    (bundle_dir / "acceptance.json").write_text(
        json.dumps(acceptance, indent=2) + "\n", encoding="utf-8"
    )
    return bundle_dir


def main(argv: list[str] | None = None) -> int:
    """Mutate one skeleton, run acceptance, and write a minimal bundle.

    Args:
        argv: Optional argument list (defaults to ``sys.argv``).

    Returns:
        Exit code: 0 when the candidate is accepted (promotable or held) and its
        bundle written, 1 on any load error, unknown operator, out-dir refusal,
        or stage discard (nothing promotable is written on failure).
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("parent", help="Path to the parent skeleton JSON.")
    parser.add_argument("--op", required=True, help="Operator id (for example 'M1').")
    parser.add_argument(
        "--params",
        nargs="*",
        default=[],
        metavar="KEY=VALUE",
        help="Operator parameters, for example choice1=c_x choice2=c_y.",
    )
    parser.add_argument("--seed", type=int, default=0, help="Rng seed (default 0).")
    parser.add_argument(
        "--out-dir", required=True, help="Directory to write the mutant bundle under."
    )
    args = parser.parse_args(argv)

    # argparse.Namespace attribute access is untyped (Any) in the stdlib stubs;
    # this is the standard boundary, mirrored from scripts/parameterize_skeleton.py.
    parent_path = Path(args.parent)  # pyright: ignore[reportAny]
    op_id: str = args.op  # pyright: ignore[reportAny]
    param_tokens: list[str] = list(args.params)  # pyright: ignore[reportAny]
    seed: int = args.seed  # pyright: ignore[reportAny]
    out_dir = Path(args.out_dir)  # pyright: ignore[reportAny]

    if _refuses_under_skeletons(out_dir):
        why = "promotion into the catalog is a reviewed PR, never a script write"
        message = (
            f"refusing: --out-dir {out_dir} resolves under a skeletons/ directory; "
            f"{why}\n"
        )
        sys.stderr.write(message)
        return 1

    if op_id not in REGISTRY:
        sys.stderr.write(
            f"error: unknown operator '{op_id}'; registered: {list(REGISTRY.ids())}\n"
        )
        return 1
    op = REGISTRY.get(op_id)

    try:
        parent = _load_parent(parent_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        sys.stderr.write(f"error: cannot load parent {parent_path}: {exc}\n")
        return 1

    try:
        params = _parse_params(param_tokens)
    except ValueError as exc:
        sys.stderr.write(f"error: {exc}\n")
        return 1

    parent_slug = parent_path.stem
    result = run_acceptance(op, parent, params, seed=seed, parent_slug=parent_slug)

    if result.discarded_at_stage is not None:
        sys.stderr.write(
            f"discarded at stage {result.discarded_at_stage}: {result.discard_reason}\n"
        )
        return 1

    candidate = result.candidate
    if candidate is None:
        # Not reachable when no discard occurred, but guards the writer.
        sys.stderr.write("error: acceptance produced no candidate to write\n")
        return 1

    out_root = out_dir.resolve()
    slug = f"{parent_slug}-{op_id.lower()}-s{seed}"
    try:
        bundle_dir = _write_bundle(
            out_root, slug, candidate, acceptance_to_dict(result)
        )
    except OSError as exc:
        sys.stderr.write(f"error: cannot write bundle for {slug}: {exc}\n")
        return 1

    status = "promotable" if result.promotable else "held (re-guidance outstanding)"
    summary = (
        f"accepted [{status}]: wrote {bundle_dir}/ "
        f"({slug}.json + acceptance.json), reguide_outstanding="
        f"{result.reguide_outstanding}\n"
    )
    sys.stdout.write(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
