"""Skeleton loading utilities for structurally-valid Storybook shells.

A skeleton is a Storybook shell whose node bodies (ending nodes included)
carry a ``<<FILL ...>>`` directive to be replaced by prose.

The shell is validated through the existing gate's blocking layers (structure,
references, reachability, termination, budget) at load time, so a skeleton can
never introduce a structural defect; the fill step only writes prose.
"""

from __future__ import annotations

import json
import logging
import math
import re
from typing import TYPE_CHECKING, cast

from cyo_adventure.core.exceptions import ValidationError

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping
    from pathlib import Path

    from cyo_adventure.validator.gate import GateResult

# Stdlib rather than `utils.logging.get_logger`, deliberately. That helper
# reaches `middleware.correlation` and pulls the sqlalchemy chain at import
# time, and this module is contractually free of it:
# `test_fill_output_cap.py::test_the_module_imports_without_a_database_driver`
# asserts that in a subprocess, for the light importers (`check_fill_integrity`,
# `compare_vendors`, the ADR-020 offline mutation core, which reads no
# database by design). Records emitted here still reach the configured
# structlog handlers, which wrap stdlib logging.
_logger = logging.getLogger(__name__)

FILL_MARKER = "<<FILL"

# The sidecar filename suffixes that live next to a ``<slug>.json`` skeleton in a
# band directory but are NOT themselves selectable skeletons: the WS-2 theme
# contract (``<slug>.contract.json``) and the WS-5 lineage record
# (``<slug>.lineage.json``, ADR-020 decision 2 / OQ-1). Every catalog scan that
# globs ``*.json`` must skip these, so the set is defined once here and a future
# sidecar type is a single edit. Ordered longest-suffix-first is unnecessary; a
# sidecar name ends in exactly one of these.
SIDECAR_SUFFIXES: tuple[str, ...] = (
    ".contract.json",
    ".lineage.json",
    # Narrative obligation contract (skeleton-narrative-redesign proposal,
    # 2026-08-09): per-node obligations for open-tier nodes. Registered ahead
    # of the SQ-12 pilot so catalog scans never load it as a skeleton, the
    # exact trap the SQ-11 brief flagged for variant sidecars.
    ".narrative.json",
)


def is_sidecar(path: Path) -> bool:
    """Return whether a catalog path is a sidecar rather than a skeleton.

    A sidecar (a theme contract or a lineage record) shares the ``*.json`` glob
    and the band directory with the skeleton it annotates, but carries no
    ``id``/``nodes`` and must never be treated as a selectable skeleton. This is
    the single predicate every catalog scanner uses in place of an inline
    ``endswith(".contract.json")`` check (design 8, ADR-020 decision 2).

    Args:
        path: The catalog file path to classify.

    Returns:
        bool: True when ``path`` is a known sidecar, False for a skeleton.
    """
    return any(path.name.endswith(suffix) for suffix in SIDECAR_SUFFIXES)


def load_skeleton(
    path: Path,
    *,
    enforce_grammar: bool = False,
    report_sink: Callable[[GateResult], None] | None = None,
) -> dict[str, object]:
    """Load a skeleton JSON file and assert it is a structurally-valid shell.

    Args:
        path: Path to the skeleton JSON.
        enforce_grammar: Forwarded to :func:`run_gate` so an authoring caller
            (``scripts/check_skeleton.py --strict``) can opt a new skeleton
            into the CG-1..CG-4 choice-grammar checks. Defaults to ``False``
            so every existing caller is unaffected (UW-C24).
        report_sink: Optional callback that receives the full
            :class:`GateResult` before any block decision is taken. Without
            it this loader silently discarded every advisory finding (PL-19
            story mean, PL-20 arc ceiling, PL-23..PL-26, L1-7 below-min,
            L2-13, RL-13), so authoring tools printed ``ok`` for skeletons
            the gate had warned about; 40 of the 61 catalog skeletons
            carried such hidden advisories (2026-08-09 review, section 2.2).

    Returns:
        The decoded skeleton as a dict.

    Raises:
        ValidationError: If any ERROR-severity finding in the gate's merged
            report has a ``rule_id`` starting with ``"CH"`` (character
            envelope, ADR-028), ``"L1"`` (Layer 1 graph structure, schema,
            and logic), ``"L2"`` (Layer 2 state-space walk), or ``"PL"``
            (policy: age-safety and shape invariants); see
            :func:`cyo_adventure.validator.gate.run_gate`'s blocking
            semantics.
    """
    # Imported here rather than at module scope because `run_gate` is this
    # module's ONLY heavy dependency, and it pulls
    # validator.gate -> validator.choice_grammar -> diversity -> diversity.history
    # -> sqlalchemy. Everything else in this file is pure text and table
    # lookups, and most importers want only those: `scripts/check_fill_integrity.py`
    # takes `commissioned_words_by_node`, `scripts/compare_vendors.py` takes
    # `resolve_output_cap`, and `mutation/floors.py`, `mutation/sample_fill.py`
    # and `flywheel/strategy.py` take `is_sidecar` or `FILL_MARKER`. At module
    # scope this import made all of them fail to load without a database driver
    # installed, and made the offline mutation core, which ADR-020 says reads no
    # request, database or network, import the deterministic gate transitively.
    # A local import here is narrower than splitting the module, because
    # `load_skeleton` is the single gated function and the most widely imported
    # symbol, so a split would repoint far more call sites than it protects.
    # #VERIFY: test_the_module_imports_without_a_database_driver.
    from cyo_adventure.validator.gate import run_gate  # noqa: PLC0415

    data: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    result = run_gate(data, enforce_grammar=enforce_grammar)
    if report_sink is not None:
        report_sink(result)
    if result.blocked:
        messages = (
            "; ".join(f.message for f in result.report.errors)
            or "no error details available"
        )
        msg = f"skeleton {path} failed structural validation: {messages}"
        raise ValidationError(msg)
    return data


def is_production_eligible(story: dict[str, object]) -> bool:
    """Return whether a skeleton may be selected for a child-facing story.

    A skeleton is production-eligible unless its metadata explicitly sets
    ``production_eligible`` to ``False`` (the MVP/Test tier; see ADR-011).
    Production story selection must exclude non-eligible skeletons; the gate
    still accepts them (against the band-independent MVP node envelope) so they
    remain usable for prototyping and pipeline testing.

    Args:
        story: The decoded skeleton dict.

    Returns:
        ``True`` unless ``metadata.production_eligible`` is explicitly ``False``.
    """
    # #CRITICAL: security: this gate decides whether a skeleton is offered to a
    # child; malformed or absent metadata defaults to eligible (the permissive
    # direction), and the raw ``is not False`` test treats a JSON string "false" as
    # eligible. A production selector MUST call this on already-schema-validated
    # metadata (StoryMetadata.production_eligible: bool), not on arbitrary raw JSON.
    # #VERIFY: production story selection screens skeletons through the Pydantic
    # StoryMetadata model before calling this, so production_eligible is a real bool.
    meta = story.get("metadata")
    if not isinstance(meta, dict):
        return True
    return meta.get("production_eligible") is not False


# Output tokens the fill of one skeleton is expected to cost, per word of
# declared `words=` fill target. The completion is the whole filled JSON
# document, not just prose, so the ratio carries node ids, choice labels and
# structural scaffolding as well.
#
# Measured 2026-08-16 over all 31 committed filled books, using a chars/4 proxy
# against each book's own skeleton fill-word total: median 2.00, range 1.43 to
# 3.02. The ratio is highest on the smallest books (3.02 on the 682-word
# sleepy-little-star) because fixed JSON scaffolding is a larger share of a
# short document, and settles to 1.43-1.59 on the large books, which are the
# only ones that come near the cap. Cross-checked against AL-328's direct
# measurement of 6,054 completion tokens on a 5-8 skeleton, which implies 1.40
# to 2.33 for that band; the two methods agree.
# The default output cap a one-shot fill runs under. Owned here rather than in
# the orchestrator so the feasibility screen and the call it screens for read
# one constant and cannot drift.
#
# Raised from 32,000 to 131,072 on 2026-08-16. The old value dated from initial
# testing and made 36 of the 59 production skeletons unfillable, with the 13-16
# and 16+ bands unfillable in their entirety. Measured against the catalog then:
# the largest skeleton needed 87,200 output tokens, so 131,072 cleared every cell
# with 20 percent headroom, and the next step down (65,536) still left 12 short.
# Cost is not the constraint at this size: one full 59-book catalog fill is
# about $6.42 on deepseek-v4-pro and $0.33 on deepseek-v4-flash.
#
# **The headroom claim is no longer true and the tense above is deliberate.**
# Re-measured 2026-08-19 across 73 production skeletons: the largest
# (`the-last-cartage`) needs 99,906 output tokens against the 104,857 this cap
# actually permits once `_FEASIBILITY_MARGIN` is applied, which is 4.7 percent
# of headroom rather than 20. The catalog grew into the cap; the cap did not
# move. Two consequences worth stating rather than rediscovering. A skeleton
# authored much past the current largest becomes unselectable with a green gate,
# which is why `check_skeleton.py --headroom` now prints this budget
# (`UW-C302`). And the margin's own justification (`AL-328`: a leg with under
# ~20 percent headroom is a coin toss) no longer holds for the top of the
# catalog even at the default cap, so raising this constant is a live question
# and not a settled one.
MAX_FILL_OUTPUT_TOKENS = 131_072

# Per-model output ceilings, used to CLAMP the default DOWN for a backend that
# cannot emit it. Only ever lowers the cap, never raises it.
#
# #CRITICAL: external-resources: AL-328's finding was that one fixed cap across
# models silently converts a verbose model into a failing one, so raising the
# default without this table would repeat that defect in the other direction: a
# model with a 32,000-token ceiling asked for 131,072 truncates, and a truncated
# completion parses as nothing. Values are transcribed from the OpenRouter
# models endpoint on 2026-08-16, not estimated. A model absent from this table
# gets the default, which is the permissive direction.
#
# That fallback used to be justified here on the grounds that a completion
# stopped on `length` is leg-fatal rather than retried (`AL-329`), so an unknown
# small-output model would fail fast and loudly. **That justification is wrong
# and the correction is `AL-479`.** `providers/openrouter.py` sets
# `leg_fatal=finish_reason == "length"` INSIDE `if not content:`, so it covers an
# EMPTY body at the length stop. An over-ask against a small ceiling produces a
# truncated NON-empty completion, which is an ordinary completion: it parses as
# nothing and spends the repair budget, which is the loud-failure case this
# comment claimed could not happen. So the fallback is permissive without the
# backstop it was written to rely on, and the rule below is the whole of the
# protection rather than a belt beside a brace.
#
# A dated or pinned model id is the live way to land in that state, because it
# does not match its own undated row: `deepseek/deepseek-chat-v3.1` resolves to
# 32,768 and `deepseek/deepseek-chat-v3.1-0813` resolves to the 131,072 default,
# four times what the backend can emit. Pin a variant in `core/config.py` only
# together with its own row here.
#
# This table is PARTIAL by construction: it lists only the models whose ceiling
# is known, and every entry must be looked up rather than inferred. The set that
# matters most is whatever `core/config.py` actually defaults to, because the
# permissive fallback above is only survivable for a model nobody is configured
# to use. Every model this app ships pointing at MUST have a row here; a missing
# row on a configured model means the clamp silently does nothing (`AL-428`).
# #VERIFY: test_fill_output_cap.py::
# test_every_configured_default_model_has_a_cap asserts exactly that, so adding a
# new default to `core/config.py` without a row here fails the suite.
# #VERIFY: test_fill_output_cap.py::test_a_small_output_model_clamps_the_cap_down
# covers the clamp and ::test_an_unknown_model_gets_the_default the passthrough.
# A trailing date or build stamp on a model id, as in
# `deepseek/deepseek-chat-v3.1-0813`. Four to eight digits so a version segment
# like `claude-sonnet-4-6` or `claude-haiku-4-5` is NOT mistaken for one.
_DATED_VARIANT_SUFFIX_RE = re.compile(r"-\d{4,8}$")

# An OpenRouter routing or tier variant, as in `anthropic/claude-haiku-4.5:free`
# or `...:nitro`. The same exact-lookup miss as a date stamp, in the suffix form
# this repo actually configures: `scripts/yield_harness.py` documents
# `--model google/gemma-4-31b-it:free`, ADR-003 names `:free` endpoints, and
# `core/config.py` ships `ollama_model = "qwen2.5:14b"`.
_VARIANT_SUFFIX_RE = re.compile(r":[^:]+$")


def _lookup_slug(table: Mapping[str, int], model: str) -> int | None:
    """Look ``model`` up in ``table``, falling back to its base slug.

    The ONE normalizer both per-model tables share. It existed inlined inside
    :func:`resolve_output_cap` until 2026-08-22, and the cost of that was
    `UW-C320` reopening: :func:`resolve_context_window` was a bare ``dict.get``,
    so a pinned or dated slug resolved an output cap and no window at all, and a
    None window constrains nothing. Two normalizers drift; one cannot.

    Exact match wins. Otherwise suffixes are stripped most-specific first, so a
    dated variant of a tiered slug (``vendor/model:free-0813``) still reaches
    its base row.

    Args:
        table: The per-model table to look up (caps or context windows). Both
            are PARTIAL by construction, so a miss means "unknown", never zero.
        model: The backend model id as configured, variants included.

    Returns:
        int | None: The table's value for the slug or its base form, or None
        when neither is recorded.
    """
    value = table.get(model)
    if value is not None:
        return value
    candidate = model
    for pattern in (_VARIANT_SUFFIX_RE, _DATED_VARIANT_SUFFIX_RE):
        candidate = pattern.sub("", candidate)
        value = table.get(candidate)
        if value is not None:
            return value
    return None


MODEL_OUTPUT_CAPS: dict[str, int] = {
    "deepseek/deepseek-v4-pro": 393_216,
    "deepseek/deepseek-v4-flash": 384_000,
    "deepseek/deepseek-v3.2": 65_536,
    "deepseek/deepseek-chat-v3.1": 32_768,
    "deepseek/deepseek-r1-0528": 32_768,
    # The Anthropic models `core/config.py` defaults to. Both ceilings sit BELOW
    # the 131,072 default, so omitting them made the clamp a no-op on the
    # shipped configuration: `fill_skeleton` asked claude-haiku-4.5 for 131,072
    # against a real ceiling of 64,000, and because the resolved cap stayed at
    # the default `is_fill_feasible` returned True for every skeleton, so the
    # chunked path could never engage on the one backend that needs it.
    "anthropic/claude-haiku-4.5": 64_000,
    "anthropic/claude-sonnet-4.6": 128_000,
    # The `generation_provider="anthropic"` spelling of the same model, which
    # `active_fill_model` reads from `anthropic_model` rather than
    # `openrouter_model`.
    "claude-sonnet-4-6": 128_000,
    "claude-haiku-4-5": 64_000,
}


def story_fill_rate(
    skeleton: dict[str, object], filled: dict[str, object]
) -> float | None:
    """Return delivered over commissioned words, per-node surplus discounted.

    The story-level fill-rate quantity ruled into the fill pipeline on
    2026-08-21 (`UW-C307`, ruling 9.3 in
    ``docs/planning/live-structural-round-2026-08-21.md``): each node is
    credited at most what it was commissioned, so surplus on one node cannot
    pay for an empty body on another, matching
    ``scripts/check_fill_integrity.py``'s blocking check. Word counts use
    whitespace splitting on both sides, as that script does.

    Args:
        skeleton: The pristine skeleton carrying ``words=`` directives.
        filled: The filled story whose delivery is being measured.

    Returns:
        float | None: The capped ratio in [0, 1], or None when the skeleton
        commissions nothing (no ``words=`` directives).
    """
    commissioned = commissioned_words_by_node(skeleton)
    total = sum(commissioned.values())
    if total <= 0:
        # #ASSUME: data-integrity: None here is "the ratio is undefined", not
        # "the ratio is zero", and the difference matters because the caller
        # (`orchestrator._with_fill_rate`) returns the outcome UNCHANGED on
        # None: no `fill_rate` stamped and no downgrade, so ruling 9.3's floor
        # does not apply to this book at all. That is the correct answer for a
        # zero denominator, since 0.0 would report a total delivery failure and
        # 1.0 a full delivery, and both are inventions. It is NOT correct to
        # leave silent: every production skeleton commissions words, so a zero
        # total means the caller passed a filled document, a non-skeleton, or a
        # skeleton whose `words=` directives were stripped, and each of those
        # disables a gate. Hence the warning: the floor may vanish, but never
        # without a trace.
        # #VERIFY: tests/unit/test_skeleton.py::
        # test_a_skeleton_commissioning_nothing_has_an_undefined_fill_rate and
        # ::test_an_undefined_fill_rate_is_logged_rather_than_silent.
        _logger.warning(
            "story_fill_rate_no_commission: 0 words across %d nodes, no floor",
            len(commissioned),
        )
        return None
    delivered: dict[str, int] = {}
    nodes = filled.get("nodes")
    for index, entry in enumerate(nodes if isinstance(nodes, list) else []):
        if not isinstance(entry, dict):
            continue
        node = cast("dict[str, object]", entry)
        body = node.get("body")
        if not isinstance(body, str) or FILL_MARKER in body:
            continue
        node_id = node.get("id")
        key = str(node_id) if node_id is not None else f"#{index}"
        # #ASSUME: data-integrity: only the FIRST occurrence of a node id is
        # credited. Accumulating duplicates let two nodes sharing one id pool
        # their words against a single commissioned target, so a fill leaving
        # one of them empty still cleared the floor (PR #737 review, I15; the
        # duplicate-id laundering first flagged on #731). A duplicated id is
        # structural garbage the gate rejects; this measure must not launder
        # it into a passing rate first.
        # #VERIFY: test_fill_output_cap.py::
        # test_duplicate_node_ids_do_not_pool_their_delivery.
        if key in delivered:
            continue
        delivered[key] = len(body.split())
    effective = sum(
        min(delivered.get(key, 0), target) for key, target in commissioned.items()
    )
    return effective / total


# Known CONTEXT windows (input plus output) per model id, the companion to
# ``MODEL_OUTPUT_CAPS``. PARTIAL by construction, exactly like that table:
# a missing row means "unknown", and :func:`resolve_context_window` returns
# None rather than guessing, so only VERIFIED rows constrain anything. Missing
# is judged AFTER `_lookup_slug` normalization, the same as MODEL_OUTPUT_CAPS:
# a row here covers its own pinned and dated variants, so a `:free` or dated
# form of a listed slug is bounded by the base row rather than left unbounded.
#
# Why it exists: the chunked fill path bounds each batch's OUTPUT under the
# resolved cap while the batch prompt carries the whole document, so input
# grows with skeleton size and nothing checked input plus ask against the
# endpoint's window. Measured 2026-08-21: a batch call requested 58,983
# output tokens with a 104,858-token prompt against deepseek-v3.2's
# 163,840-token window, one token over, HTTP 400 (`AL-514`/`UW-C320`).
# #ASSUME: external resources: values transcribed from the OpenRouter
# endpoints API for the pinned endpoints; per-endpoint variation exists for
# some slugs, so record the MINIMUM across the endpoints a pin can reach.
# #VERIFY: tests/unit/test_chunked_fill.py::
# test_a_known_window_clamps_the_batch_ask_below_the_cap (reads this table
# through resolve_context_window on the chunked path).
MODEL_CONTEXT_WINDOWS: dict[str, int] = {
    # Uniform 163,840 across every serving endpoint, read 2026-08-21.
    "deepseek/deepseek-v3.2": 163_840,
}


def resolve_context_window(model: str | None) -> int | None:
    """Return the model's known context window, or None when unknown.

    Args:
        model: The backend model id, or None when it is not known.

    Returns:
        int | None: The verified window, or None (no constraint) for a model
        without a row; unlike :func:`resolve_output_cap` there is no safe
        permissive default to fall back to, because the window bounds input
        PLUS output and a wrong guess fails or truncates real requests.
    """
    if model is None:
        return None
    # #CRITICAL: external-resources: this governs whether a paid third-party
    # call is bounded AT ALL, so a lookup miss is not a degraded bound, it is
    # no bound. Until 2026-08-22 this was a bare `MODEL_CONTEXT_WINDOWS.get`
    # while its declared companion `resolve_output_cap` already normalized
    # `:variant` and dated suffixes (`49d17a64`, `AL-500`). A pinned slug
    # (`vendor/model:free`) or a dated one (`vendor/model-20260101`) therefore
    # resolved a cap and returned None here; None constrains nothing, the
    # chunked path's context bound went inert, and the exact unbounded ask
    # `UW-C320` was filed for came back with no warning and no refusal.
    # Sharing `_lookup_slug` with the cap is the whole fix: a second normalizer
    # is how this recurs. Inheriting the base row is the safe direction here
    # too. A variant whose real window is LARGER only makes the batch ask
    # smaller than it had to be, while a variant whose window is SMALLER is no
    # worse off than the unbounded status quo, and both beat no bound at all.
    # #VERIFY: tests/unit/test_skeleton.py::
    # test_a_variant_slug_resolves_the_same_context_window_as_its_base_form
    # (pinned and dated forms) and ::
    # test_context_window_and_output_cap_normalize_variants_identically
    # (parity across both tables, which catches the NEXT divergence).
    return _lookup_slug(MODEL_CONTEXT_WINDOWS, model)


# Conservative characters-per-token divisor for estimating a prompt's input
# tokens. Measured on the 2026-08-21 chunked batch prompt: 369,399 chars
# tokenized to 104,858 tokens (3.52 chars/token); 3.0 deliberately
# OVER-estimates the token count so the context bound errs toward asking for
# less output, never toward another one-token overflow.
_CHARS_PER_INPUT_TOKEN = 3.0


def estimate_input_tokens(*texts: str) -> int:
    """Conservatively estimate the input tokens of the given prompt parts.

    Args:
        *texts: The prompt strings that will be sent (system and user blocks).

    Returns:
        int: The estimated token count, rounded up.
    """
    total_chars = sum(len(text) for text in texts)
    return math.ceil(total_chars / _CHARS_PER_INPUT_TOKEN)


def active_fill_model(settings: object) -> str | None:
    """Return the model id the configured provider will fill with, if knowable.

    Mirrors ``provider.build_provider``'s selection so the cap resolves against
    the model the call will actually use. Returns None for backends with no
    model concept (mock) or an unrecognised provider, which resolves to the
    default cap.

    Args:
        settings: The application settings object.

    Returns:
        str | None: The model id, or None when it cannot be determined.
    """
    backend = getattr(settings, "generation_provider", None)
    field = {
        "openrouter": "openrouter_model",
        "ollama": "ollama_model",
        "anthropic": "anthropic_model",
    }.get(str(backend))
    if field is None:
        return None
    model = getattr(settings, field, None)
    return model if isinstance(model, str) else None


def resolve_output_cap(
    model: str | None, *, default: int = MAX_FILL_OUTPUT_TOKENS
) -> int:
    """Return the output cap to use for *model*, never above *default*.

    Args:
        model: The backend model id, or None when it is not known.
        default: The configured cap to use when the model imposes none lower.

    Returns:
        int: The effective cap.
    """
    if model is None:
        return default
    # #CRITICAL: data-integrity: a dated or pinned variant does not match
    # its own undated row, and the comment above MODEL_OUTPUT_CAPS names
    # that as the live way into the permissive fallback:
    # `deepseek/deepseek-chat-v3.1-0813` took 131,072 against a real 32,768,
    # four times what the backend can emit, and the over-ask truncates
    # NON-EMPTY, which `AL-479` establishes is not leg-fatal and therefore
    # spends the whole repair budget. Falling back to the undated row is
    # strictly safer than the default: it can only lower the cap, so the
    # error direction is engaging the chunked path too early rather than
    # asking for prose the endpoint will not emit. A variant whose real
    # ceiling is HIGHER than its base still needs its own row, because this
    # table is looked up and never inferred.
    # A trailing `:variant` is the SAME miss in the other suffix form, and
    # it is the one this repo configures: closing only the dated form left
    # `anthropic/claude-haiku-4.5:free` resolving to 131,072 against its
    # row's 64,000. Both are stripped by `_lookup_slug`, most-specific
    # candidate first, so a dated variant of a tiered slug still finds its
    # base row. That normalization is SHARED with
    # :func:`resolve_context_window` rather than repeated here; see
    # `_lookup_slug` for why a second copy is the defect and not the fix.
    # #VERIFY: test_a_dated_variant_inherits_its_undated_row and
    # test_a_routing_variant_inherits_its_base_row.
    cap = _lookup_slug(MODEL_OUTPUT_CAPS, model)
    return min(default, cap if cap is not None else default)


_TOKENS_PER_FILL_WORD = 2.0

# Share of the output cap a fill may be expected to need before the skeleton is
# treated as infeasible. Not arbitrary: AL-328 measured claude-sonnet-5 at 91%
# of the 32,000-token cap across four briefs and it truncated on one of them, so
# a leg with under ~20% headroom is a coin toss rather than a working leg.
# Reasoning tokens make this worse and are invisible here, because they bill
# against the same budget and produce no prose (moonshotai/kimi-k3 spent 28,247
# of 32,000 thinking and returned nothing).
_FEASIBILITY_MARGIN = 0.8

# Whitespace-tolerant on purpose, and deliberately identical to
# `mutation/identity.py`'s pattern. The strict `\bwords=(\d+)` spelling scored a
# directive written `words = 30` as ZERO expected tokens, which made
# `is_fill_feasible` return True under any cap at all: a fail-open in the guard
# whose whole job is refusing a skeleton the backend cannot emit. No committed
# skeleton uses the spaced form today, so this was latent rather than live, but
# the two modules must recognise the same DIRECTIVE TOKEN (`AL-429`).
#
# The shared invariant is the token grammar and nothing more. The two modules
# deliberately disagree about what they then DO with a match, and always have:
# `identity.py::_word_estimate` takes `.search()`, so the FIRST directive in a
# body, and falls back to `len(body.split())` for a body carrying no directive
# at all; `commissioned_words_by_node` below takes `.findall()` and SUMS, skips
# a body with no directive, skips a `words=0` node, and keys an id-less node
# positionally where `identity.py::_fastest_finish_words` drops it. Those are
# four different questions ("what does this one node budget" against "what did
# this story commission"), so a convergence project would be chasing a property
# that never held. Read the invariant as "same token, independent accounting",
# and do not widen the pinning test into a membership or magnitude comparison:
# it would fail immediately, or enshrine one caller's accounting as the other's.
# #VERIFY: test_fill_output_cap.py::
# test_a_spaced_words_directive_is_counted_like_the_strict_form pins the
# tolerance, and ::test_the_fill_word_pattern_matches_the_mutation_core pins the
# two patterns together so a future edit to one fails the suite.
_FILL_WORDS_RE = re.compile(r"words\s*=\s*(\d+)")


def commissioned_words_by_node(story: dict[str, object]) -> dict[str, int]:
    """Return each node's declared ``words=`` fill target, keyed by node id.

    The per-node breakdown exists so a checker holding both the skeleton and
    the filled story can measure the story-level fill rate (delivered words
    over commissioned words, `AL-490`/`UW-C307`): the live DeepSeek run showed
    a fill can deliver 40 percent of its commissioned prose while no per-node
    rule fires, because the only hard word rule is a ceiling. Nodes without a
    ``words=`` directive do not appear, so pre-authored prose never dilutes
    the ratio.

    #ASSUME: data-integrity: the key scheme is a cross-module contract, not an
    internal detail. ``scripts/check_fill_integrity.py`` reproduces it exactly
    to join delivered words against commissioned words, so changing how an
    id-less or duplicate-id node is keyed silently changes that gate's
    denominator. Duplicate keys ACCUMULATE rather than overwrite so the summed
    total always equals a plain scan of the bodies, which is what
    ``expected_output_tokens`` depends on (`AL-429`).
    #VERIFY: test_commissioned_words_are_reported_per_node,
    test_the_per_node_keying_preserves_the_flat_word_total, and
    test_commissioned_words_skip_malformed_shapes.

    Args:
        story: The decoded skeleton dict.

    Returns:
        dict[str, int]: Summed ``words=`` targets per node, for nodes whose
            body declares at least one. Keyed by ``str(node["id"])``, or by
            ``#<index>`` for a node carrying no id; a key reached more than
            once accumulates rather than being overwritten.
    """
    targets: dict[str, int] = {}
    nodes = story.get("nodes")
    if not isinstance(nodes, list):
        return targets
    for index, node in enumerate(nodes):  # pyright: ignore[reportUnknownVariableType]
        if not isinstance(node, dict):
            continue
        body = node.get("body")
        if not isinstance(body, str):
            continue
        words = sum(int(m) for m in _FILL_WORDS_RE.findall(body))
        if not words:
            continue
        # An id-less node (a malformed or test skeleton) falls back to a
        # positional key, and duplicate keys accumulate rather than overwrite:
        # either way the summed total stays equal to what a plain scan of the
        # bodies would count, which `expected_output_tokens` depends on.
        raw_id = node.get("id")
        key = str(raw_id) if raw_id is not None else f"#{index}"
        targets[key] = targets.get(key, 0) + words
    return targets


def expected_output_tokens(story: dict[str, object]) -> int:
    """Return the output tokens a one-shot fill of *story* is expected to cost.

    Derived from the declared ``words=`` targets rather than from prose, so it
    is computable at selection time, before anything has been generated or paid
    for.

    Args:
        story: The decoded skeleton dict.

    Returns:
        int: Expected completion tokens for the whole filled document.
    """
    words = sum(commissioned_words_by_node(story).values())
    return math.ceil(words * _TOKENS_PER_FILL_WORD)


def is_fill_feasible(story: dict[str, object], *, max_tokens: int) -> bool:
    """Return whether a one-shot fill of *story* can fit under *max_tokens*.

    #CRITICAL: payment: without this predicate selection could pick a skeleton
    the fill pipeline provably cannot emit. An over-cap one-shot fill does not
    degrade, it fails: the completion truncates, no document parses, and the
    orchestrator burns its whole repair budget (roughly four rounds of ~100k
    input tokens) before failing deterministically, forever, on every retry.
    Measured 2026-08-16: 26 of the 62 production skeletons exceed the then-current
    32,000-token cap, the largest needing about 76,000. This is `UW-C07` and
    `AL-046`.

    This predicate now serves two callers at two different caps, and conflating
    them is the trap. ``fill_skeleton`` is no longer one-shot-only: asked at the
    *resolved* (per-model) cap it decides whether to chunk, so False there means
    "batch this", not "refuse this". ``skeleton_match`` asks at the
    model-independent DEFAULT cap instead, where False means the skeleton is too
    large for ANY backend and is dropped from selection. Do not "simplify" the
    two call sites onto one cap: matching at the resolved cap would delete a
    skeleton from the catalog because of today's configured model, and chunking
    at the default cap would never fire at all (`AL-437`).
    #VERIFY: test_fill_output_cap.py::
    test_feasibility_is_measured_against_the_declared_fill_targets asserts the
    predicate itself, and test_skeleton_match.py::
    test_an_over_cap_skeleton_is_not_a_candidate that `skeleton_match` drops it.

    Note this bounds the *document*, not the call: reasoning tokens share the
    same budget and are not visible here, so a model that reasons heavily can
    still exhaust a cap this predicate called feasible. Choosing ``max_tokens``
    is the caller's job; this only refuses what cannot fit under any reasoning
    behaviour at all.

    Args:
        story: The decoded skeleton dict.
        max_tokens: The output cap the fill will run under.

    Returns:
        bool: True when the expected output leaves the required headroom.
    """
    return expected_output_tokens(story) <= max_tokens * _FEASIBILITY_MARGIN


def has_unfilled_directives(story: dict[str, object]) -> bool:
    """Return True if any node body still contains a ``<<FILL``-prefixed directive."""
    nodes = story.get("nodes")
    if not isinstance(nodes, list):
        return False
    return any(
        isinstance(n, dict)
        and isinstance(n.get("body"), str)
        and FILL_MARKER in n["body"]
        for n in nodes
    )
