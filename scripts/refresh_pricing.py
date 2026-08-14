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
import urllib.error
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
    # Open-weight judge candidates evaluated as distillation parents against
    # W7's arms. Priced here for the same reason as every other entry: an
    # unpriced model reports its runs as costing nothing.
    "deepseek/deepseek-v4-flash",
    "deepseek/deepseek-v4-flash-0731",
    "~deepseek/deepseek-v4-flash-latest",
    "qwen/qwen3-32b",
    "qwen/qwen3.5-27b",
    "qwen/qwen3.6-27b",
    "meta-llama/llama-3.3-70b-instruct",
    "z-ai/glm-5",
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


def endpoint_count(api_key: str, model: str) -> int | None:
    """Return how many providers currently serve *model*.

    The distinction this exists for cost a wrong answer on 2026-08-14. The
    ``/models`` list returns only models with at least one live endpoint, so a
    real model nobody is serving is absent from it, and reporting that absence
    as "NOT LISTED" reads as "does not exist". OpenRouter itself distinguishes
    the two clearly and we were not listening: a completion against an unknown
    slug returns ``400 not a valid model ID``, while a real model with no
    endpoints returns ``404 No endpoints found``. ``qwen/qwen3.8-27b`` is the
    second case, a catalogue entry named "Qwen: Qwen3.8 27B" with zero
    endpoints, and it was written off as nonexistent.

    Args:
        api_key: An OpenRouter credential.
        model: The model slug.

    Returns:
        The endpoint count, or ``None`` when the slug is unknown to OpenRouter,
        which is the genuinely-does-not-exist case.
    """
    url = f"https://openrouter.ai/api/v1/models/{model}/endpoints"
    request = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {api_key}"}
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as response:  # noqa: S310
            payload = json.load(response)
    except urllib.error.HTTPError:
        return None
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    endpoints = data.get("endpoints")
    return len(endpoints) if isinstance(endpoints, list) else 0


def probe_callable(api_key: str, model: str) -> str:
    """Return whether *model* can actually be called by THIS account.

    The authoritative availability test, because the cheaper checks each miss a
    real case. ``GET /models`` omits models with no endpoints. The endpoints
    route counts endpoints that exist globally, not endpoints this account may
    route to. On 2026-08-14 the whole ``qwen/qwen3.7`` line (flash, plus, max)
    listed fine, had endpoints, and refused every call with "No endpoints
    available matching your guardrail restrictions and data policy": this
    account's policy excludes their serving stacks, which is a correct setting
    for a children's product and still leaves the model uncallable.

    Four outcomes, each needing a different response, which is why they are
    reported separately rather than collapsed into "unavailable":

    * ``ok``: callable now.
    * ``data-policy``: real, served, blocked by our own routing policy. Change
      the policy or pick another model; waiting will not help.
    * ``no-endpoints``: real, nobody serving it. Waiting may help.
    * ``unknown-slug``: not a model id OpenRouter recognises.

    Args:
        api_key: An OpenRouter credential.
        model: The model slug.

    Returns:
        One of the four states above.
    """
    body = json.dumps(
        {
            "model": model,
            "max_tokens": 8,
            "messages": [{"role": "user", "content": "say ok"}],
        }
    ).encode()
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS):  # noqa: S310
            return "ok"
    except urllib.error.HTTPError as exc:
        try:
            message = json.loads(exc.read())["error"]["message"]
        except (ValueError, KeyError):
            return f"http-{exc.code}"
    if "data policy" in message or "guardrail" in message:
        return "data-policy"
    if "No endpoints" in message:
        return "no-endpoints"
    if "not a valid model" in message:
        return "unknown-slug"
    return "other"


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


def render(
    models: dict[str, dict[str, Any]], wanted: Sequence[str], api_key: str = ""
) -> str:
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
            # Absent from the list is two different facts and they need
            # different answers, so ask which one this is rather than guessing.
            count = endpoint_count(api_key, model) if api_key else None
            if count == 0:
                lines.append(
                    f"    # NO ENDPOINTS on {today}: {model!r} is a real "
                    "OpenRouter model that no provider is currently serving. "
                    "Re-check later; it is not unavailable permanently."
                )
            elif count is None:
                lines.append(
                    f"    # UNKNOWN SLUG on {today}: {model!r} is not a model "
                    "id OpenRouter recognises."
                )
            else:
                lines.append(
                    f"    # UNPRICED on {today}: {model!r} has {count} "
                    "endpoint(s) but no entry in the model list."
                )
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
    print(render(models, args.models or _WANTED, api_key))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
