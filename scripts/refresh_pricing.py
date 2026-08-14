"""Emit dated `core/pricing.py` entries from OpenRouter's live price list.

`UW-C239` has been open since the vendor comparison: every cloud entry in
``core/pricing.py`` carries ``input_usd_per_mtok=None``, because the project's
only recorded price source (the phase-2b analysis) noted output prices and no
input prices. The consequence is not a slightly-low estimate. ``estimate_cost``
marks every such estimate ``complete=False``, the per-job accounting merged with
#701 writes ``cost_complete = false`` on every row, and the migration's own
advice to filter on that column then selects nothing. Two measurement runs on
2026-08-14 printed ``$0.0000`` for work that cost $0.85 and $6.29.

Transcribing from a document was the original mistake, so this does not
transcribe: it reads the vendor's live list and prints entries ready to paste,
each stamped with the date it was read and sourced to the endpoint. That keeps
``pricing.py``'s discipline intact (a price is a dated fact citing its source)
while making a refresh a command rather than an act of archaeology.

What this cannot do is verify the vendor is telling the truth, or notice a price
that changes tomorrow. The ``#CRITICAL`` note in ``pricing.py`` stands.

Usage::

    uv run python scripts/refresh_pricing.py
    uv run python scripts/refresh_pricing.py --model x-ai/grok-4.6
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

_ENDPOINT: Final[str] = "https://openrouter.ai/api/v1/models"
_TIMEOUT_SECONDS: Final[int] = 60

# Every OpenRouter model the service or its measurement harnesses can issue a
# call against today: the generation default and the review model from
# `core/config.py`, the three judges in `scripts/judge_books.py`, and the
# fixture rewriter in `scripts/w7_battery.py`. A model promoted out of a vendor
# comparison must be added here at the same time it is added to the allowlist,
# or its calls price as unknown and every job it touches reports incomplete.
_WANTED: Final[tuple[str, ...]] = (
    "anthropic/claude-haiku-4.5",
    "anthropic/claude-sonnet-4.6",
    "anthropic/claude-sonnet-5",
    "google/gemini-2.5-flash",
    "google/gemini-3-flash-preview",
    "google/gemini-3.1-pro-preview",
    "openai/gpt-5.6-sol",
    "x-ai/grok-4.6",
)


def fetch(api_key: str) -> dict[str, dict[str, Any]]:
    """Return OpenRouter's model list, keyed by model id.

    Args:
        api_key: An OpenRouter credential. Sent as a bearer token and never
            logged; only model ids and prices are printed by this script.

    Returns:
        Every model the endpoint lists.

    Raises:
        RuntimeError: If the response carries no ``data`` array.
    """
    request = urllib.request.Request(
        _ENDPOINT, headers={"Authorization": f"Bearer {api_key}"}
    )
    with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310
        payload = json.load(response)
    rows = payload.get("data")
    if not isinstance(rows, list):
        msg = "OpenRouter returned no 'data' array"
        raise RuntimeError(msg)
    return {str(row["id"]): row for row in rows if isinstance(row, dict)}


def _rate(pricing: dict[str, Any], key: str) -> Decimal | None:
    """Return a per-million-token rate, or ``None`` when the vendor omits it.

    Args:
        pricing: One model's ``pricing`` object.
        key: ``"prompt"`` or ``"completion"``.

    Returns:
        The rate as a ``Decimal``, never a float: this value is summed across
        thousands of calls and binary floating point has no business in it.
        ``None`` when absent or unparseable, which must stay distinct from a
        zero rate.
    """
    raw = pricing.get(key)
    if raw in (None, ""):
        return None
    try:
        return Decimal(str(raw)) * Decimal(1_000_000)
    except (ArithmeticError, ValueError):
        return None


def render(models: dict[str, dict[str, Any]], wanted: Sequence[str]) -> str:
    """Render paste-ready ``_PRICES`` entries for *wanted*.

    Args:
        models: The fetched model list.
        wanted: Model ids to emit.

    Returns:
        Python source for the entries, and a comment for any id the vendor did
        not list, because a silently omitted model is how this gap reopens.
    """
    today = datetime.now(tz=UTC).date().isoformat()
    lines: list[str] = []
    for model in wanted:
        row = models.get(model)
        if row is None:
            lines.append(f"    # NOT LISTED by OpenRouter on {today}: {model!r}")
            continue
        pricing = row.get("pricing")
        if not isinstance(pricing, dict):
            lines.append(f"    # NO PRICING BLOCK on {today}: {model!r}")
            continue
        prompt = _rate(pricing, "prompt")
        completion = _rate(pricing, "completion")
        lines.append(f'    ("openrouter", "{model}"): ModelPrice(')
        lines.append(
            f"        input_usd_per_mtok={_decimal_literal(prompt)},"
            if prompt is not None
            else "        input_usd_per_mtok=None,  # vendor omitted a prompt rate"
        )
        lines.append(
            f"        output_usd_per_mtok={_decimal_literal(completion)},"
            if completion is not None
            else "        output_usd_per_mtok=None,  # vendor omitted a rate"
        )
        year, month, day = today.split("-")
        lines.append(f"        as_of=date({int(year)}, {int(month)}, {int(day)}),")
        lines.append("        source=_OPENROUTER_API,")
        lines.append(f'        note="read live from {_ENDPOINT}",')
        lines.append("    ),")
    return "\n".join(lines)


def _decimal_literal(value: Decimal) -> str:
    """Return a ``Decimal`` literal for *value*, in this project's lint style.

    Whole numbers are emitted unquoted (``Decimal(5)``) and fractional ones
    quoted (``Decimal("0.5")``). Ruff's FURB157 rejects the quoted form for an
    integer, and the quoted form is what matters for the fractional case: a
    bare ``Decimal(0.5)`` would construct from a binary float and reintroduce
    exactly the representation error this module exists to avoid.

    Args:
        value: The per-million-token rate.

    Returns:
        Python source for the literal.
    """
    text = format(value.normalize(), "f")
    return (
        f"Decimal({text})"
        if value == value.to_integral_value()
        else f'Decimal("{text}")'
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Fetch and print entries.

    Args:
        argv: Argument vector, or ``None`` for ``sys.argv``.

    Returns:
        ``0`` on success, ``2`` when no credential is configured.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--model",
        action="append",
        dest="models",
        help="Emit this model instead of the built-in list. Repeatable.",
    )
    args = parser.parse_args(argv)

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("OPENROUTER_API_KEY is not set.", file=sys.stderr)
        return 2

    models = fetch(api_key)
    print(render(models, args.models or _WANTED))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
