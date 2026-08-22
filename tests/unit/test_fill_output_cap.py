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
import subprocess
import sys
from pathlib import Path

import pytest

from cyo_adventure.core.config import Settings
from cyo_adventure.generation.skeleton import (
    _DATED_VARIANT_SUFFIX_RE,
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

    The candidate set is DERIVED from `Settings`, not listed here. A hardcoded
    tuple made the docstring's promise false: it named three fields, so the
    exemption below could never fire and a newly added default was checked only
    if someone also edited the tuple. Five of the eight `*_model` fields were
    outside it, including `review_openrouter_model`.

    Exemptions, each because no vendor fill ceiling exists to look up rather
    than for convenience: the two `ollama` fields are locally served, so the
    ceiling is the deployment's runtime configuration; `cover_model` is an image
    model, and this table governs fill output tokens. A `None` default is
    skipped, which covers `modal_model`.
    """
    exempt = {"ollama_model", "review_ollama_model", "cover_model"}
    fields = tuple(name for name in Settings.model_fields if name.endswith("_model"))
    assert set(exempt) <= set(fields), (
        f"exempt names no longer in Settings: {set(exempt) - set(fields)}"
    )
    assert len(fields) > len(exempt), "derivation found no checkable model field"
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
    """One directive, one grammar. Accounting is deliberately NOT shared.

    `generation/skeleton.py` and `mutation/identity.py` must recognise the same
    `words=` token, because a spelling one accepts and the other does not is how
    the `AL-429` fail-open got in.

    This pins the GRAMMAR only, which is the whole invariant. The two modules
    already differ on what they do with a match and are meant to:
    `_word_estimate` reads the first directive and falls back to the body's own
    length, while `commissioned_words_by_node` sums every directive and ignores
    bodies that carry none. Widening this assertion to compare per-node
    membership or totals would either fail on contact or freeze one caller's
    accounting into the other.
    """
    assert _FILL_WORDS_RE.pattern == _MUTATION_FILL_WORDS_RE.pattern


@pytest.mark.unit
def test_a_dated_variant_inherits_its_undated_row() -> None:
    """A dated or pinned variant must not take the permissive default.

    The comment above `MODEL_OUTPUT_CAPS` names this as the live route into the
    fallback: `deepseek/deepseek-chat-v3.1-0813` matched no row and resolved to
    131,072 against a real 32,768, four times what the backend emits. The
    over-ask truncates non-empty, which `AL-479` establishes is not leg-fatal,
    so it spends the entire repair budget instead of failing fast.
    """
    assert resolve_output_cap("deepseek/deepseek-chat-v3.1-0813") == 32_768, (
        "a dated variant still takes the permissive default, so the clamp is a "
        "no-op on exactly the ids most likely to be pinned in config"
    )
    # An exact row always wins over the fallback.
    assert resolve_output_cap("deepseek/deepseek-r1-0528") == 32_768


@pytest.mark.unit
def test_a_routing_variant_inherits_its_base_row() -> None:
    """An OpenRouter `:variant` suffix is the same miss as a date stamp.

    Closing only the dated form left the suffix form this repo actually
    configures wide open: `scripts/yield_harness.py` documents
    `--model google/gemma-4-31b-it:free`, ADR-003 names `:free` endpoints, and
    `test_worker.py` sets `openrouter_fallback_model` to a `:free` slug. So
    `anthropic/claude-haiku-4.5:free` matched no row and took the permissive
    131,072 against its own row's 64,000, which is exactly the over-ask the
    `#CRITICAL` note on `resolve_output_cap` describes.
    """
    assert resolve_output_cap("anthropic/claude-haiku-4.5:free") == 64_000, (
        "a routing variant still takes the permissive default, so the clamp is "
        "a no-op on the suffix form this repo configures"
    )
    assert resolve_output_cap("anthropic/claude-sonnet-4.6:nitro") == 128_000
    # Both suffix forms at once: strip the tier, then the date stamp.
    assert resolve_output_cap("deepseek/deepseek-chat-v3.1-0813:free") == 32_768
    # An unknown base still falls through to the default rather than inventing one.
    assert (
        resolve_output_cap("qwen/qwen-never-heard-of-it:free") == MAX_FILL_OUTPUT_TOKENS
    )


@pytest.mark.unit
def test_a_version_segment_is_not_read_as_a_date() -> None:
    """The suffix pattern must not eat a one-digit version segment.

    Asserted against the PATTERN, not through `resolve_output_cap`. Every id of
    this shape in the table today (`claude-sonnet-4-6`, `claude-haiku-4-5`) has
    its own exact row, so the fallback never runs for them and a resolver-level
    assertion here would pass under any bound at all: it could not fail. The
    bound is defensive against a future table that holds a base row like
    `claude-sonnet-4` while a caller asks for `claude-sonnet-4-6`, where a
    greedy `-\\d+$` would silently inherit the wrong ceiling.
    """
    assert _DATED_VARIANT_SUFFIX_RE.search("deepseek/deepseek-chat-v3.1-0813")
    assert _DATED_VARIANT_SUFFIX_RE.search("claude-sonnet-4-6") is None, (
        "a one-digit version segment is being read as a date stamp, so a model "
        "id would inherit its base model's ceiling instead of its own"
    )
    assert _DATED_VARIANT_SUFFIX_RE.search("claude-haiku-4-5") is None
    assert _DATED_VARIANT_SUFFIX_RE.search("anthropic/claude-haiku-4.5") is None


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
def test_the_per_node_keying_preserves_the_flat_word_total() -> None:
    """Duplicate and id-less keys must accumulate, not overwrite.

    ``expected_output_tokens`` folds this map, so an overwrite would make it
    UNDERstate a duplicate-id skeleton's demand and let ``is_fill_feasible``
    fail open on a book the backend cannot emit, which is the `AL-429` shape.
    ``scripts/check_fill_integrity.py`` joins its delivered words on the same
    keys, so an overwrite would also shrink that gate's denominator.
    """
    story: dict[str, object] = {
        "nodes": [
            {"id": "dup", "body": "<<FILL role=scene words=100>>"},
            {"id": "dup", "body": "<<FILL role=scene words=100>>"},
            {"body": "<<FILL role=scene words=50>>"},
            {"body": "<<FILL role=scene words=50>>"},
            {"id": "multi", "body": "<<FILL words=30>>\n<<FILL words=20>>"},
        ]
    }
    assert commissioned_words_by_node(story) == {
        "dup": 200,
        "#2": 50,
        "#3": 50,
        "multi": 50,
    }, (
        "a repeated node id must sum its targets and an id-less node must take "
        "a positional key; overwriting either loses commissioned words"
    )
    # 350 commissioned words at 2.0 tokens/word. Asserted alongside the map so
    # a keying change that happens to preserve the total is still caught, and a
    # keying change that silently loses words fails here too.
    assert expected_output_tokens(story) == 700


def test_commissioned_words_skip_malformed_shapes() -> None:
    """Malformed stories yield empty or partial targets, never an exception.

    ``expected_output_tokens`` runs at selection time over decoded JSON it did
    not author, so a story with no node list, a non-dict node member, or a
    non-string body must degrade to "no commissioned words there" rather than
    raise mid-selection.
    """
    assert commissioned_words_by_node({}) == {}
    assert commissioned_words_by_node({"nodes": "not-a-list"}) == {}

    story = {
        "nodes": [
            "not-a-node",
            {"id": "a", "body": None},
            {"id": "b", "body": "<<FILL role=rising words=50 beats='x'>>"},
        ]
    }

    assert commissioned_words_by_node(story) == {"b": 50}


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


@pytest.mark.unit
def test_the_module_imports_without_a_database_driver() -> None:
    """`generation.skeleton` must not pull the DB layer at import time.

    `load_skeleton` needs `validator.gate`, which reaches sqlalchemy through
    `validator.choice_grammar` -> `diversity` -> `diversity.history`. Every other
    symbol here is pure text and table lookups, and the light importers want only
    those: `scripts/check_fill_integrity.py`, `scripts/compare_vendors.py`, and
    the ADR-020 offline mutation core, which is specified to read no request,
    database or network.

    Run in a subprocess because the in-process test session has already imported
    sqlalchemy for other suites, so `sys.modules` here can never observe the
    regression. An in-process assertion would be a check that cannot fail.
    """
    probe = (
        "import sys;"
        "import cyo_adventure.generation.skeleton as s;"
        "assert callable(s.commissioned_words_by_node);"
        "assert callable(s.load_skeleton);"
        "print('sqlalchemy' in sys.modules)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    assert result.stdout.strip() == "False", (
        "importing generation.skeleton pulled the sqlalchemy chain, so the "
        "script and offline-mutation importers now need a database driver "
        f"installed to load a pure text helper. stdout={result.stdout!r}"
    )


def test_a_pinned_variant_inherits_its_base_context_window() -> None:
    """The window resolver normalizes suffixes exactly like the cap resolver.

    PR #737 review, I16: a pinned (`:variant`) or dated slug resolved a CAP
    through suffix normalization while the WINDOW came back None, and None
    constrains nothing, restoring the unbounded-ask overflow `UW-C320` filed.
    """
    from cyo_adventure.generation.skeleton import resolve_context_window

    base = resolve_context_window("deepseek/deepseek-v3.2")
    assert base == 163_840
    assert resolve_context_window("deepseek/deepseek-v3.2:free") == base
    assert resolve_context_window("deepseek/deepseek-v3.2-0821") == base
    assert resolve_context_window("vendor/unknown-model") is None
    assert resolve_context_window(None) is None


def test_duplicate_node_ids_do_not_pool_their_delivery() -> None:
    """Only the first occurrence of a node id is credited (PR #737, I15).

    Two filled nodes sharing one id previously summed their words against a
    single commissioned target, so a fill leaving one empty still cleared
    the floor; a duplicated id is the gate's rejection, not a passing rate.
    """
    from cyo_adventure.generation.skeleton import story_fill_rate

    skeleton = {
        "nodes": [
            {"id": "dup", "body": "<<FILL role=setup words=10 beats='open'>>"},
        ]
    }
    filled = {
        "nodes": [
            {"id": "dup", "body": "one two three four five"},
            {"id": "dup", "body": "six seven eight nine ten"},
        ]
    }
    rate = story_fill_rate(skeleton, filled)
    assert rate is not None
    assert rate == pytest.approx(0.5)
