import logging
from pathlib import Path

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.skeleton import (
    MODEL_CONTEXT_WINDOWS,
    MODEL_OUTPUT_CAPS,
    has_unfilled_directives,
    is_production_eligible,
    is_sidecar,
    load_skeleton,
    resolve_context_window,
    resolve_output_cap,
    story_fill_rate,
)

_SKELETON = Path("tests/fixtures/skeletons/demo_shell.json")


@pytest.mark.unit
def test_load_skeleton_accepts_valid_shell() -> None:
    """A structurally valid shell loads and is reported as unfilled."""
    data = load_skeleton(_SKELETON)
    assert data["id"] == "sk_demo"
    assert has_unfilled_directives(data) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "story",
    [
        pytest.param({}, id="no_nodes_key"),
        pytest.param({"nodes": "not-a-list"}, id="nodes_not_a_list"),
    ],
)
def test_has_unfilled_directives_returns_false_when_nodes_missing_or_not_a_list(
    story: dict[str, object],
) -> None:
    """A story with no 'nodes' key, or a non-list 'nodes', reports no directives."""
    assert has_unfilled_directives(story) is False


@pytest.mark.unit
def test_load_skeleton_rejects_structurally_broken_shell(tmp_path: Path) -> None:
    """A shell whose choice targets a missing node is rejected."""
    import json

    broken = json.loads(_SKELETON.read_text())
    broken["nodes"][0]["choices"][0]["target"] = "does_not_exist"
    path = tmp_path / "broken.json"
    path.write_text(json.dumps(broken))
    with pytest.raises(ValidationError, match="structural"):
        load_skeleton(path)


_DEMO_SKELETONS = [
    "skeletons/3-5/the-lost-mitten.json",
    "skeletons/10-13/the-clocktower-cipher.json",
    "skeletons/16+/the-sunken-signal.json",
]

# L2-14 quarantine (A14). EMPTY as of 2026-07-26: all four skeletons that once
# offered a reader a decision whose every option ended in death now pass.
#
# Two of the four never needed a content change at all. The rule originally
# treated `capture` as fatal, which was an implementation choice rather than the
# owner's instruction ("both result in death"), and narrowing it to `death`
# cleared `the-quiet-harbor-protocol` and `the-cinder-bazaar`, whose deliberately
# authored "closing dark" climaxes each offer a survivable capture.
#
# The remaining two were real and were fixed in the content:
#   the-sunken-signal  n_collapse  the survive-but-fail ending the author had
#                                  already written was gated behind equipment;
#                                  the gate now also opens at air=0.
#   the-serpent-vaults c22_drown_e death -> setback, so running the deep lock dry
#                                  ends the descent instead of the diver.
#
# The mechanism is kept, not deleted: it is strict, so a re-added entry that
# stops failing forces its own removal, and S4 has further catalog work to come.
_L2_14_QUARANTINE: frozenset[str] = frozenset()


def _param(rel: str) -> object:
    """Parametrize one skeleton, strict-xfail if it is L2-14 quarantined."""
    if rel in _L2_14_QUARANTINE:
        return pytest.param(
            rel,
            marks=pytest.mark.xfail(
                strict=True,
                reason="L2-14: all-fatal decision, quarantined pending slice S4",
            ),
        )
    return rel


@pytest.mark.unit
@pytest.mark.parametrize("rel", [_param(r) for r in _DEMO_SKELETONS])
def test_skeletons_load_under_schema_2_0(rel: str) -> None:
    """Each demo skeleton parses under schema 2.0 with typed endings."""
    data = load_skeleton(Path(rel))
    assert data["schema_version"] == "2.0"
    assert "topology" in data["metadata"]
    for node in data["nodes"]:
        ending = node.get("ending")
        if ending is not None:
            assert set(ending) == {"id", "valence", "kind", "title"}


def _assert_passes_full_gate(rel: str) -> None:
    """Load the skeleton at ``rel`` and assert it passes the full gate."""
    import json

    from cyo_adventure.validator.gate import run_gate

    data = json.loads(Path(rel).read_text(encoding="utf-8"))
    result = run_gate(data)
    assert not result.blocked, [f.message for f in result.report.errors]


@pytest.mark.unit
@pytest.mark.parametrize("rel", [_param(r) for r in _DEMO_SKELETONS])
def test_skeletons_pass_full_gate_including_policy(rel: str) -> None:
    """Each demo skeleton passes the full gate, including the policy layer."""
    _assert_passes_full_gate(rel)


@pytest.mark.unit
def test_demo_shell_is_production_eligible_by_default() -> None:
    """A skeleton with no ``production_eligible`` flag is production-eligible."""
    data = load_skeleton(_SKELETON)
    assert is_production_eligible(data) is True


@pytest.mark.unit
@pytest.mark.parametrize("rel", [_param(r) for r in _DEMO_SKELETONS])
def test_seed_skeletons_are_mvp_non_production(rel: str) -> None:
    """The three current hand-authored seeds are MVP/Test, not production."""
    data = load_skeleton(Path(rel))
    assert is_production_eligible(data) is False


@pytest.mark.unit
def test_is_production_eligible_missing_metadata_defaults_true() -> None:
    """A malformed skeleton with no metadata is treated as production-eligible."""
    assert is_production_eligible({}) is True


# Production-eligible (scale-classified) skeletons authored against ADR-011.
# Each declares ``length`` + ``narrative_style`` + ``production_eligible: true``,
# which arms the PL-17/19/20/21 story-scale rules, so passing the full gate here
# pins the seed as launch-ready in CI. Discovered by scanning ``skeletons/`` so
# new cells are picked up automatically (MVP/Test seeds are excluded by their
# ``production_eligible: false`` flag), and no per-cell list edit is needed.
def _discover_production_skeletons() -> list[str]:
    import json

    found: list[str] = []
    for path in sorted(Path("skeletons").glob("*/*.json")):
        # Skip sidecars (WS-2 theme contracts and WS-5 lineage records): they
        # share the .json suffix and this band-directory glob, but they are not
        # skeletons (see generation/skeleton.py::is_sidecar, the shared skip).
        if is_sidecar(path):
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if is_production_eligible(data):
            found.append(str(path))
    return found


_PRODUCTION_SKELETONS = _discover_production_skeletons()


@pytest.mark.unit
def test_at_least_one_production_skeleton_exists() -> None:
    """Guard the discovery glob: the launch corpus is never silently empty."""
    assert _PRODUCTION_SKELETONS, "no production-eligible skeletons discovered"


@pytest.mark.unit
@pytest.mark.parametrize("rel", [_param(r) for r in _PRODUCTION_SKELETONS])
def test_production_skeletons_pass_full_gate(rel: str) -> None:
    """Each production skeleton passes the full gate (blocked is False)."""
    _assert_passes_full_gate(rel)


@pytest.mark.unit
@pytest.mark.parametrize("rel", [_param(r) for r in _PRODUCTION_SKELETONS])
def test_production_skeletons_are_production_eligible(rel: str) -> None:
    """Each production skeleton is scale-classified as production-eligible."""
    data = load_skeleton(Path(rel))
    assert is_production_eligible(data) is True


@pytest.mark.unit
@pytest.mark.parametrize(
    "suffix",
    [
        pytest.param(":free", id="routing_variant"),
        pytest.param(":nitro", id="tier_variant"),
        pytest.param("-20260101", id="dated_variant"),
        pytest.param("-0813", id="short_dated_variant"),
    ],
)
def test_a_variant_slug_resolves_the_same_context_window_as_its_base_form(
    suffix: str,
) -> None:
    """A pinned or dated slug must not lose its window (`UW-C320` reopened).

    `resolve_context_window` was a bare `dict.get` while its declared companion
    `resolve_output_cap` already stripped these suffixes (`49d17a64`,
    `AL-500`), so `deepseek/deepseek-v3.2:free` resolved an output cap and a
    None window. None constrains nothing, so the chunked path's context bound
    went inert and the unbounded ask that `UW-C320` was filed for came back,
    silently: no warning, no refusal, just no bound.
    """
    base = "deepseek/deepseek-v3.2"
    expected = resolve_context_window(base)
    assert expected is not None, "fixture slug lost its row; pick another"
    assert resolve_context_window(base + suffix) == expected, (
        f"'{base}{suffix}' resolves no window while its base row does, so the "
        "context bound is inert for exactly the ids config pins"
    )


@pytest.mark.unit
def test_an_unknown_model_has_no_known_context_window() -> None:
    """Normalization must not invent a window for a slug nobody verified.

    The table is partial by construction and the fallback direction is the
    base row, never a guess: an unrecorded vendor stays None, because a wrong
    window fails or truncates real paid requests.
    """
    assert resolve_context_window("acme/entirely-unknown-model") is None
    assert resolve_context_window("acme/entirely-unknown-model:free") is None
    assert resolve_context_window(None) is None


@pytest.mark.unit
@pytest.mark.parametrize(
    "suffix",
    [":free", ":nitro", "-20260101", "-0813"],
)
@pytest.mark.parametrize(
    "slug",
    sorted(set(MODEL_CONTEXT_WINDOWS) | set(MODEL_OUTPUT_CAPS)),
)
def test_context_window_and_output_cap_normalize_variants_identically(
    slug: str, suffix: str
) -> None:
    """Both resolvers must share one normalizer, checked across both tables.

    Worth more than three hand-picked cases: this is the test that catches the
    NEXT divergence rather than the one just fixed. The defect was precisely
    that one resolver normalized and the other did not, so the invariant is
    stated per resolver (a variant resolves what its base resolves) and swept
    over every slug either table knows.
    """
    assert resolve_context_window(slug + suffix) == resolve_context_window(slug), (
        f"resolve_context_window disagrees with itself on '{slug}{suffix}'"
    )
    assert resolve_output_cap(slug + suffix) == resolve_output_cap(slug), (
        f"resolve_output_cap disagrees with itself on '{slug}{suffix}'"
    )


@pytest.mark.unit
def test_a_skeleton_commissioning_nothing_has_an_undefined_fill_rate() -> None:
    """A zero denominator yields None, which is not 0.0 and not 1.0.

    The branch was unasserted, and it is the branch on which ruling 9.3's
    fill-rate floor stops applying: `orchestrator._with_fill_rate` returns the
    outcome unchanged on None, stamping no rate and forcing no review. Pinning
    it here says the vanish is deliberate for an undefined ratio, and stops a
    later edit from substituting an invented 0.0 (a false total failure) or 1.0
    (a false full delivery).
    """
    filled = {"nodes": [{"id": "n1", "body": "some delivered prose"}]}
    assert story_fill_rate({"nodes": []}, filled) is None
    assert story_fill_rate({}, filled) is None


@pytest.mark.unit
def test_an_undefined_fill_rate_is_logged_rather_than_silent(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The floor may vanish, but never without a trace.

    Every production skeleton commissions words, so a zero total means a filled
    document, a non-skeleton, or a skeleton whose `words=` directives were
    stripped reached this call, and each of those disables a gate. A gate that
    disappears with no log entry is indistinguishable from a gate that passed.
    """
    with caplog.at_level(logging.WARNING):
        assert story_fill_rate({"nodes": []}, {"nodes": []}) is None
    assert "story_fill_rate_no_commission" in caplog.text, (
        "the fill-rate floor stopped applying and said nothing"
    )


@pytest.mark.unit
def test_a_commissioned_skeleton_still_reports_a_rate() -> None:
    """Guard the guard: the None branch must not swallow a real measurement."""
    skeleton = {"nodes": [{"id": "n1", "body": "<<FILL words=10>>"}]}
    filled = {"nodes": [{"id": "n1", "body": "one two three four five"}]}
    assert story_fill_rate(skeleton, filled) == pytest.approx(0.5)
