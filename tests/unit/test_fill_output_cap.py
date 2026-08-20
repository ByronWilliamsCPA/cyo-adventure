"""The fill output cap: raised default, per-model clamp, feasibility screen.

The cap was 32,000 from initial testing until 2026-08-16, which made 36 of the
59 production skeletons unfillable and the 13-16 and 16+ bands unfillable
entirely. Raising it is only safe alongside the clamp: AL-328's finding was
that ONE fixed cap across models silently converts a verbose model into a
failing one, and a raised default repeats that defect in the other direction
unless a small-output backend is clamped back down.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.generation.skeleton import (
    _FILL_WORDS_RE,
    MAX_FILL_OUTPUT_TOKENS,
    MODEL_OUTPUT_CAPS,
    active_fill_model,
    commissioned_words_by_node,
    expected_output_tokens,
    is_fill_feasible,
    resolve_output_cap,
)
from cyo_adventure.mutation.identity import (
    _FILL_WORDS_RE as _MUTATION_FILL_WORDS_RE,
)

_SKELETONS_DIR = Path(__file__).resolve().parents[2] / "skeletons"
_SIDECAR_SUFFIXES = (".contract.json", ".lineage.json", ".narrative.json")


def _production_skeletons() -> list[Path]:
    """Return every committed production-eligible, non-deprecated skeleton shell.

    Returns:
        list[Path]: Skeleton shell paths, sidecars and retired shells excluded.
    """
    shells: list[Path] = []
    for path in sorted(_SKELETONS_DIR.glob("*/*.json")):
        if path.name.endswith(_SIDECAR_SUFFIXES):
            continue
        metadata = json.loads(path.read_text(encoding="utf-8")).get("metadata") or {}
        if metadata.get("production_eligible") is False or metadata.get("deprecated"):
            continue
        shells.append(path)
    return shells


class _Settings:
    """Minimal stand-in carrying only the fields the resolver reads."""

    def __init__(self, provider: str, **models: str) -> None:
        self.generation_provider = provider
        for name, value in models.items():
            setattr(self, name, value)


@pytest.mark.unit
def test_the_default_cap_clears_the_whole_production_catalog() -> None:
    """131,072 is chosen against the catalog, not picked round.

    Reads the committed catalog rather than comparing two literals: the earlier
    form asserted `int(87_200 / 0.8) <= MAX_FILL_OUTPUT_TOKENS`, which is true
    of two constants regardless of what the skeletons actually need, so it
    would have stayed green if a larger skeleton landed.
    """
    largest = max(
        (
            expected_output_tokens(json.loads(p.read_text(encoding="utf-8")))
            for p in _production_skeletons()
        ),
        default=0,
    )

    assert largest > 0, "no production skeletons scanned; the glob is wrong"
    assert is_fill_feasible(
        {"nodes": [{"body": f"<<FILL words={largest // 2}>>"}]},
        max_tokens=MAX_FILL_OUTPUT_TOKENS,
    )


@pytest.mark.unit
def test_every_configured_default_model_has_a_cap() -> None:
    """A configured model with no row makes the clamp a silent no-op.

    The permissive fallback in `resolve_output_cap` is only survivable for a
    model nobody is pointed at. When the table shipped with DeepSeek rows only,
    every Anthropic default resolved to the 131,072 default against real
    ceilings of 64,000 and 128,000, so `fill_skeleton` over-asked and
    `is_fill_feasible` never refused anything (`AL-428`).

    `ollama_model` is exempt on purpose: a locally-served model's output ceiling
    is set by the deployment's runtime configuration, not by a vendor, so there
    is no value to look up. Adding any new default to `core/config.py` fails
    this test until it is either given a row or added here deliberately.
    """
    exempt = {"ollama_model"}
    fields = ("openrouter_model", "openrouter_fallback_model", "anthropic_model")
    missing = [
        (name, default)
        for name in fields
        if name not in exempt
        and isinstance(default := Settings.model_fields[name].default, str)
        and default not in MODEL_OUTPUT_CAPS
    ]

    assert not missing, (
        f"configured default models with no MODEL_OUTPUT_CAPS row: {missing}"
    )


@pytest.mark.unit
def test_a_configured_default_below_the_cap_actually_clamps() -> None:
    """The rows must be load-bearing, not merely present.

    A row equal to the default would satisfy the presence test above while
    leaving the over-ask in place, so assert the resolved cap for the shipped
    OpenRouter default is genuinely lower than what a one-shot fill would
    otherwise request.
    """
    default_model = Settings.model_fields["openrouter_model"].default

    assert resolve_output_cap(default_model) < MAX_FILL_OUTPUT_TOKENS


@pytest.mark.unit
def test_a_spaced_words_directive_is_counted_like_the_strict_form() -> None:
    """`words = 30` must not score zero.

    The strict `\\bwords=(\\d+)` pattern returned 0 expected tokens for a spaced
    directive, so `is_fill_feasible` returned True under any cap: a fail-open in
    the guard that exists to refuse what the backend cannot emit (`AL-429`).
    """
    strict = {"nodes": [{"body": "<<FILL role=rising words=4000>>"}]}
    spaced = {"nodes": [{"body": "<<FILL role=rising words = 4000>>"}]}

    assert expected_output_tokens(spaced) == expected_output_tokens(strict) == 8000
    assert not is_fill_feasible(spaced, max_tokens=1000)


@pytest.mark.unit
def test_the_fill_word_pattern_matches_the_mutation_core() -> None:
    """One directive, one grammar.

    `generation/skeleton.py` and `mutation/identity.py` both parse the same
    `words=` directive. Divergence means the two disagree about a skeleton's
    size, which is how the fail-open above got in.
    """
    assert _FILL_WORDS_RE.pattern == _MUTATION_FILL_WORDS_RE.pattern


@pytest.mark.unit
def test_a_small_output_model_clamps_the_cap_down() -> None:
    """A backend that cannot emit the default must not be asked to.

    Asking for more than a model will emit truncates the completion, and a
    truncated document parses as nothing at all rather than as a partial book.
    """
    small = "deepseek/deepseek-chat-v3.1"

    assert MODEL_OUTPUT_CAPS[small] < MAX_FILL_OUTPUT_TOKENS
    assert resolve_output_cap(small) == MODEL_OUTPUT_CAPS[small]


@pytest.mark.unit
def test_a_large_output_model_does_not_raise_the_cap() -> None:
    """The clamp only ever lowers. deepseek-v4-pro emits far more than we ask."""
    assert MODEL_OUTPUT_CAPS["deepseek/deepseek-v4-pro"] > MAX_FILL_OUTPUT_TOKENS
    assert resolve_output_cap("deepseek/deepseek-v4-pro") == MAX_FILL_OUTPUT_TOKENS


@pytest.mark.unit
def test_an_unknown_model_gets_the_default() -> None:
    """Absent evidence the cap is not lowered; `length` is leg-fatal anyway."""
    assert resolve_output_cap("some/unlisted-model") == MAX_FILL_OUTPUT_TOKENS
    assert resolve_output_cap(None) == MAX_FILL_OUTPUT_TOKENS


@pytest.mark.unit
@pytest.mark.parametrize(
    ("provider", "field", "model"),
    [
        ("openrouter", "openrouter_model", "deepseek/deepseek-v4-pro"),
        ("ollama", "ollama_model", "qwen2.5:14b"),
        ("anthropic", "anthropic_model", "claude-sonnet-4-6"),
    ],
)
def test_the_active_model_follows_the_configured_backend(
    provider: str, field: str, model: str
) -> None:
    """The cap must resolve against the model the call will actually use."""
    assert active_fill_model(_Settings(provider, **{field: model})) == model


@pytest.mark.unit
def test_a_backend_with_no_model_concept_resolves_to_none() -> None:
    """mock has no model, and None must mean 'use the default', not crash."""
    assert active_fill_model(_Settings("mock")) is None


@pytest.mark.unit
def test_feasibility_is_measured_against_the_declared_fill_targets() -> None:
    """Expected size is computable before anything has been paid for."""
    story = {
        "nodes": [
            {"body": "<<FILL role=rising words=100 beats='a'>>"},
            {"body": "<<FILL role=rising words=150 beats='b'>>"},
        ]
    }

    assert expected_output_tokens(story) == 500
    assert is_fill_feasible(story, max_tokens=1000)
    assert not is_fill_feasible(story, max_tokens=100)


@pytest.mark.unit
def test_commissioned_words_are_reported_per_node() -> None:
    """The per-node breakdown keys on id and skips directive-less nodes.

    The fill-rate check (AL-490/UW-C307) joins these targets against the
    filled book's node ids, so a node without a ``words=`` directive must be
    absent (pre-authored prose never dilutes the ratio) and an id-less node
    must not collapse onto another's key (that overwrite once undercounted
    ``expected_output_tokens``).
    """
    story = {
        "nodes": [
            {"id": "a", "body": "<<FILL role=rising words=100 beats='x'>>"},
            {"id": "b", "body": "already-authored prose, no directive"},
            {"body": "<<FILL role=rising words=25 beats='y'>>"},
            {"body": "<<FILL role=rising words=75 beats='z'>>"},
        ]
    }

    targets = commissioned_words_by_node(story)

    assert targets == {"a": 100, "#2": 25, "#3": 75}
    assert sum(targets.values()) == 200


@pytest.mark.unit
def test_the_provider_model_outranks_the_configured_default() -> None:
    """A per-job model override is only visible on the provider.

    `worker.py` builds the provider with `model_override=` but hands
    `fill_skeleton` the module-level `_default_settings`, so resolving the cap
    from Settings alone returns the process default and misses the override
    (`AL-432`). `PiiGuardedProvider.model` forwards the inner declaration so the
    cap can follow the model that will actually serve the call.
    """
    from cyo_adventure.generation.guarded import PiiGuardedProvider
    from cyo_adventure.generation.pii import PiiContext

    class _Inner:
        model = "deepseek/deepseek-chat-v3.1"

        async def complete(
            self, *, system: str, prompt: str, max_tokens: int
        ) -> object:
            raise AssertionError("not called")

    guarded = PiiGuardedProvider(
        _Inner(),  # pyright: ignore[reportArgumentType] - stub declares only what is read
        forbidden=PiiContext(child_names=frozenset()),
    )

    assert guarded.model == "deepseek/deepseek-chat-v3.1"
    assert resolve_output_cap(guarded.model) == 32_768
    # ...and a provider that declares nothing leaves the caller on the default.
    assert (
        PiiGuardedProvider(
            object(),  # pyright: ignore[reportArgumentType] - deliberately model-less
            forbidden=PiiContext(child_names=frozenset()),
        ).model
        is None
    )
