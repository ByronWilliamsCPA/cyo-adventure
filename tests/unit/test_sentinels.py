"""Unit tests for the canonical sentinel module (storybook/sentinels.py).

A sentinel is the machine-recognizable placeholder that survives verbatim
through fill, validation, moderation, approval, and storage, and strips to a
generic word for any non-opted-in reader. This test file asserts the four
shape constraints from the design (ADR-023, plan section 2) plus the public
API's round-trip and validation behavior.
"""

import pytest

from cyo_adventure.storybook.sentinels import (
    SENTINEL_RE,
    find_malformed_sentinels,
    find_sentinels,
    strip_sentinels,
    wrap,
)
from cyo_adventure.storybook.theme_contract import SLOT_TOKEN_RE

_SAMPLE_TOKEN = "{~HERO:Explorer~}"


class TestFourConstraints:
    """The four shape constraints the canonical sentinel format must satisfy."""

    def test_never_matches_slot_token_re(self) -> None:
        """A sentinel must never match the bare {SLOT} token grammar.

        render_bound_skeleton's post-condition requires zero {SLOT}-shaped
        tokens remain in the rendered doc; the sentinel's interior begins
        with ``~``, which is not ``[A-Z]``, so SLOT_TOKEN_RE cannot match at
        any offset.
        """
        assert SLOT_TOKEN_RE.search(_SAMPLE_TOKEN) is None

    def test_contains_no_directive_breaking_characters(self) -> None:
        """A sentinel must contain no `<<`, `>>`, or `'`.

        Those sequences could corrupt a
        ``<<FILL role=... words=... beats='...'>>`` directive.
        """
        assert "<<" not in _SAMPLE_TOKEN
        assert ">>" not in _SAMPLE_TOKEN
        assert "'" not in _SAMPLE_TOKEN

    def test_strips_to_exactly_the_inner_word(self) -> None:
        """strip_sentinels on a single token returns exactly the inner value."""
        assert strip_sentinels(_SAMPLE_TOKEN) == "Explorer"

    def test_slot_id_carried_inline_no_external_lookup(self) -> None:
        """find_sentinels parses the slot id straight out of the token text."""
        assert find_sentinels(_SAMPLE_TOKEN) == [("HERO", "Explorer")]


class TestSentinelRe:
    """Direct assertions on the compiled SENTINEL_RE pattern."""

    def test_matches_canonical_shape(self) -> None:
        """SENTINEL_RE matches the canonical `{~SLOTID:GenericWord~}` shape."""
        match = SENTINEL_RE.search(_SAMPLE_TOKEN)
        assert match is not None
        assert match.group(1) == "HERO"
        assert match.group(2) == "Explorer"

    def test_no_match_on_plain_text(self) -> None:
        """SENTINEL_RE does not match ordinary prose."""
        assert SENTINEL_RE.search("The hero walked into the forest.") is None

    def test_no_match_on_bare_slot_token(self) -> None:
        """SENTINEL_RE does not match a bare {SLOT} token (no sentinel shape)."""
        assert SENTINEL_RE.search("{HERO}") is None


class TestWrap:
    """wrap() builds the canonical token and validates its inputs."""

    def test_wrap_builds_canonical_token(self) -> None:
        """wrap produces the exact canonical shape."""
        assert wrap("HERO", "Explorer") == "{~HERO:Explorer~}"

    def test_wrap_round_trips_with_find_sentinels(self) -> None:
        """A wrapped token, when parsed back, yields the original (id, value)."""
        token = wrap("HERO", "Explorer")
        assert find_sentinels(token) == [("HERO", "Explorer")]

    def test_wrap_allows_value_with_space(self) -> None:
        """A generic value containing a space is valid and round-trips."""
        token = wrap("PLACE", "Sunny Meadow")
        assert token == "{~PLACE:Sunny Meadow~}"
        assert find_sentinels(token) == [("PLACE", "Sunny Meadow")]
        assert strip_sentinels(token) == "Sunny Meadow"

    @pytest.mark.parametrize(
        "bad_slot_id",
        [
            "hero",  # lowercase
            "1HERO",  # leading digit
            "HERO-1",  # hyphen not allowed
            "",  # empty
            "HERO LOC",  # embedded space
        ],
    )
    def test_wrap_rejects_bad_slot_id(self, bad_slot_id: str) -> None:
        """wrap raises ValueError for any slot id not matching [A-Z][A-Z0-9_]*."""
        with pytest.raises(ValueError, match="slot"):
            wrap(bad_slot_id, "Explorer")

    @pytest.mark.parametrize(
        "bad_value",
        [
            "Ex{plorer",
            "Ex}plorer",
            "Ex<plorer",
            "Ex>plorer",
            "Ex'plorer",
            "Ex~plorer",
        ],
    )
    def test_wrap_rejects_bad_value(self, bad_value: str) -> None:
        """wrap raises ValueError when value contains a forbidden character."""
        with pytest.raises(ValueError, match="value"):
            wrap("HERO", bad_value)

    def test_wrap_rejects_empty_value(self) -> None:
        """wrap raises ValueError when value is empty."""
        with pytest.raises(ValueError, match="empty"):
            wrap("HERO", "")

    def test_wrap_rejects_trailing_newline_slot_id(self) -> None:
        """wrap raises ValueError for slot id with trailing newline.

        Regression test for regex anchor bypass: Python's $ matches before a
        trailing newline without re.MULTILINE, so .match("HERO\\n") would
        previously succeed. This must be rejected to prevent unstripped
        sentinels leaking to readers.
        """
        with pytest.raises(ValueError, match="slot"):
            wrap("HERO\n", "Explorer")

    def test_wrap_output_always_round_trips(self) -> None:
        """wrap output is always recognizable and round-trips cleanly.

        Asserts that for any valid (slot_id, value) pair, the output of
        wrap() is parseable by SENTINEL_RE and round-trips through both
        find_sentinels and strip_sentinels. This guards the core invariant
        that every token wrap() can build is also recognizable by the
        sentinel parser.
        """
        test_cases = [
            ("HERO", "Explorer"),
            ("PET_NAME", "Good Dog"),
            ("H2O", "Water Drop"),
        ]
        for slot_id, value in test_cases:
            token = wrap(slot_id, value)
            # Round-trip through find_sentinels.
            found = find_sentinels(token)
            assert found == [(slot_id, value)], (
                f"find_sentinels failed for {token!r}: got {found!r}"
            )
            # Round-trip through strip_sentinels.
            stripped = strip_sentinels(token)
            assert stripped == value, (
                f"strip_sentinels failed for {token!r}: got {stripped!r}"
            )


class TestStripSentinels:
    """strip_sentinels replaces every sentinel with its inner value."""

    def test_strip_multi_sentinel_text(self) -> None:
        """Multiple sentinels in one passage all strip to their inner values."""
        text = (
            f"{wrap('HERO', 'Explorer')} met {wrap('PLACE', 'Sunny Meadow')} at dawn."
        )
        assert strip_sentinels(text) == "Explorer met Sunny Meadow at dawn."

    def test_strip_no_sentinel_text_unchanged(self) -> None:
        """Text with no sentinels is returned unchanged."""
        text = "A perfectly ordinary sentence with no placeholders."
        assert strip_sentinels(text) == text

    def test_strip_empty_string(self) -> None:
        """Stripping an empty string returns an empty string."""
        assert strip_sentinels("") == ""


class TestFindSentinels:
    """find_sentinels returns every (slot_id, value) match, in order."""

    def test_find_multiple_in_order(self) -> None:
        """Multiple sentinels are returned in left-to-right order."""
        text = f"{wrap('A', 'One')} then {wrap('B', 'Two')} then {wrap('C', 'Three')}"
        assert find_sentinels(text) == [
            ("A", "One"),
            ("B", "Two"),
            ("C", "Three"),
        ]

    def test_find_none_returns_empty_list(self) -> None:
        """Text with no sentinels returns an empty list."""
        assert find_sentinels("no sentinels here") == []


class TestFindMalformedSentinels:
    """find_malformed_sentinels detects sentinel-shaped near-misses (plan risk R9).

    The near-miss grammar anchors on the two sentinel-distinctive markers,
    the opener ``{~`` and the closer ``~}``, rather than on generic
    non-nested ``{...}`` brace spans. An ordinary prose brace with no tilde
    involved (e.g. a templating placeholder like ``{blank}``, or a
    tilde-less ``{SLOT}`` theme token) is never a sentinel attempt and is
    never reported.
    """

    def test_clean_sentinel_reports_nothing(self) -> None:
        """A single well-formed sentinel is not reported."""
        text = f"The hero met {wrap('HERO', 'Explorer')} at dawn."
        assert find_malformed_sentinels(text) == []

    def test_multiple_clean_sentinels_report_nothing(self) -> None:
        """Several well-formed sentinels in one passage are all clean."""
        text = f"{wrap('HERO', 'Explorer')} found {wrap('PRIZE', 'Gem')}."
        assert find_malformed_sentinels(text) == []

    def test_ordinary_prose_brace_not_reported(self) -> None:
        """A literal brace unrelated to a sentinel (no tilde) is not reported."""
        assert find_malformed_sentinels("Fill in the {blank} form.") == []

    def test_plain_text_with_no_braces_reports_nothing(self) -> None:
        """Text with no braces at all reports nothing."""
        assert find_malformed_sentinels("A perfectly ordinary sentence.") == []

    @pytest.mark.parametrize(
        "text",
        [
            "Fill in the {HERO} form.",
            "Fill in the {HERO_2} form.",
        ],
    )
    def test_legitimate_slot_token_not_reported(self, text: str) -> None:
        """A `{SLOT}`-style theme token (no tilde) is never a sentinel attempt.

        Regression guard for the near-miss redesign: anchoring on the ``{~``
        opener must not start flagging plain, tilde-less theme tokens that
        `theme_contract.SLOT_TOKEN_RE` already legitimately matches.
        """
        assert find_malformed_sentinels(text) == []

    @pytest.mark.parametrize(
        "text",
        [
            "It takes approx ~5 minutes to read this page.",
            "Pack a set {a, b} of camping gear.",
            "A stray { appears with no partner here.",
            "A stray } appears with no partner here.",
        ],
    )
    def test_lone_unrelated_marks_not_reported(self, text: str) -> None:
        """A lone brace or tilde with no sentinel-attempt marker is ignored.

        None of these strings contain either sentinel-distinctive marker
        (``{~`` or ``~}``), so none is a candidate attempt.
        """
        assert find_malformed_sentinels(text) == []

    @pytest.mark.parametrize(
        ("label", "text", "expected_hit"),
        [
            (
                "whitespace after opening tilde",
                "{~ HERO:Explorer~}",
                "{~ HERO:Explorer~}",
            ),
            (
                "whitespace around colon",
                "{~HERO : Explorer~}",
                "{~HERO : Explorer~}",
            ),
            (
                "lowercase slot id",
                "{~hero:Explorer~}",
                "{~hero:Explorer~}",
            ),
            (
                "missing opening tilde",
                "{HERO:Explorer~}",
                "{HERO:Explorer~}",
            ),
            (
                "missing closing tilde",
                "{~HERO:Explorer}",
                "{~HERO:Explorer}",
            ),
            (
                "forbidden char in value",
                "{~HERO:Ex'plorer~}",
                "{~HERO:Ex'plorer~}",
            ),
            (
                "empty value",
                "{~HERO:~}",
                "{~HERO:~}",
            ),
        ],
    )
    def test_each_near_miss_class_is_reported(
        self, label: str, text: str, expected_hit: str
    ) -> None:
        """Each documented near-miss class is caught, embedded in prose."""
        embedded = f"The hero found {text} on the path."
        assert find_malformed_sentinels(embedded) == [expected_hit], label

    def test_mixed_clean_and_malformed_reports_only_malformed(self) -> None:
        """A passage with one clean sentinel and one near-miss reports only the miss."""
        text = f"{wrap('HERO', 'Explorer')} passed {{~PRIZE:~}} on the way."
        assert find_malformed_sentinels(text) == ["{~PRIZE:~}"]

    def test_multiple_near_misses_reported_in_order(self) -> None:
        """Two near-misses in one passage are both reported, left to right."""
        text = "{~hero:Explorer~} then {~PRIZE:Gem}"
        assert find_malformed_sentinels(text) == [
            "{~hero:Explorer~}",
            "{~PRIZE:Gem}",
        ]

    def test_empty_string_reports_nothing(self) -> None:
        """An empty string reports no near-misses."""
        assert find_malformed_sentinels("") == []

    @pytest.mark.parametrize(
        ("label", "text"),
        [
            ("embedded brace in value", "{~HERO:El{evated}~}"),
            ("angle bracket in value", "{~HERO:Ex<plorer~}"),
        ],
    )
    def test_forbidden_char_near_miss_reported_whole_span(
        self, label: str, text: str
    ) -> None:
        """A forged value with a forbidden char is reported, whole span.

        Regression test for the review-found brace blind spot: the previous
        non-nested ``{...}`` scan ended the span at the embedded ``{`` (or,
        for a non-brace forbidden char, matched a shorter inner span), so
        this forgery was never reported at all. The redesigned grammar
        anchors on the ``{~``/``~}`` markers, tolerates the embedded brace in
        between, and reports the full outer span.
        """
        embedded = f"The hero found {text} on the path."
        assert find_malformed_sentinels(embedded) == [text], label

    def test_unterminated_opener_reports_truncated_fragment_not_later_sentinel(
        self,
    ) -> None:
        """An unterminated `{~` opener is reported, not silently dropped.

        Regression test for round-2 Defect 1 (critical false negative): the
        previous `_closer_end` returned `None` when neither `~}` nor a bare
        `}` appeared before the next `{~` opener, and the caller then treated
        the opener as ordinary prose, producing zero violations even though a
        truncated, never-closed sentinel-shaped opener was present. The fix
        must report the truncated fragment up to the next independent opener,
        and must still recognize that next opener as its own, separate, clean
        attempt.
        """
        text = (
            "The hero {~HERO:starts an adventure that never quite finishes "
            f"and then {wrap('PRIZE', 'Gem')} appears."
        )
        opener_index = text.index("{~HERO")
        prize_opener_index = text.index("{~PRIZE")
        expected_fragment = text[opener_index:prize_opener_index]
        hits = find_malformed_sentinels(text)
        assert hits == [expected_fragment]
        assert wrap("PRIZE", "Gem") not in hits

    def test_unterminated_opener_at_end_of_text_reports_to_end(self) -> None:
        """A truncated opener with no closer anywhere in the text is reported.

        Regression test for round-2 Defect 1: with no later `{~` opener and
        no closer at all, the unterminated span must run to the end of text.
        """
        text = "The hero found {~HERO:blah"
        opener_index = text.index("{~HERO")
        assert find_malformed_sentinels(text) == [text[opener_index:]]

    def test_missing_closing_tilde_then_stray_closer_reports_only_near_span(
        self,
    ) -> None:
        """A nearer bare `}` closer is preferred over a farther stray `~}`.

        Regression test for round-2 Defect 2 (over-broad span): the previous
        `_closer_end` preferred the first `~}` found anywhere in range over a
        nearer bare `}`, so a missing-closing-tilde near miss followed by an
        unrelated stray `~}` produced one over-broad span swallowing
        unrelated text. The fix must resolve the closer via a strict
        left-to-right scan, so the nearer bare `}` closes the span first and
        the trailing stray `~}` is left unpaired (no preceding unclaimed `{`
        remains once the floor advances past it).
        """
        text = "{~HERO:Explorer} some unrelated ~} marker."
        assert find_malformed_sentinels(text) == ["{~HERO:Explorer}"]
