"""Tests for the PII egress guard (WP7).

Verifies word-boundary name matching, birthdate substring matching, no-PII
path, and the critical security property that the exception never echoes the
actual PII value.
"""

from __future__ import annotations

import pytest

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.pii import PiiContext, assert_prompt_pii_safe

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def make_ctx(
    names: frozenset[str] | None = None,
    birthdates: frozenset[str] | None = None,
) -> PiiContext:
    """Build a PiiContext with convenient defaults."""
    return PiiContext(
        child_names=names if names is not None else frozenset(),
        birthdates=birthdates if birthdates is not None else frozenset(),
    )


# ---------------------------------------------------------------------------
# Test 5: Prompt containing a seeded child name (standalone word, any case)
#         raises ValidationError.
# ---------------------------------------------------------------------------


def test_exact_name_raises() -> None:
    """Prompt containing the real child's name as a standalone word raises."""
    ctx = make_ctx(names=frozenset({"Mia"}))
    with pytest.raises(
        ValidationError, match=r"prompt contains a forbidden real-child identifier"
    ):
        assert_prompt_pii_safe("Write a story about Mia.", forbidden=ctx)


def test_name_case_insensitive_raises() -> None:
    """Name match is case-insensitive (uppercase, mixed case)."""
    ctx = make_ctx(names=frozenset({"Mia"}))
    with pytest.raises(
        ValidationError, match=r"prompt contains a forbidden real-child identifier"
    ):
        assert_prompt_pii_safe("MIA saves the day.", forbidden=ctx)

    with pytest.raises(
        ValidationError, match=r"prompt contains a forbidden real-child identifier"
    ):
        assert_prompt_pii_safe("mIa went exploring.", forbidden=ctx)


def test_name_at_start_of_prompt_raises() -> None:
    """Name at the very start of the prompt (no leading word boundary) raises."""
    ctx = make_ctx(names=frozenset({"Emma"}))
    with pytest.raises(
        ValidationError, match=r"prompt contains a forbidden real-child identifier"
    ):
        assert_prompt_pii_safe("Emma found a treasure map.", forbidden=ctx)


def test_name_at_end_of_prompt_raises() -> None:
    """Name at the end of the prompt with trailing punctuation raises."""
    ctx = make_ctx(names=frozenset({"Luca"}))
    with pytest.raises(
        ValidationError, match=r"prompt contains a forbidden real-child identifier"
    ):
        assert_prompt_pii_safe("The hero was Luca.", forbidden=ctx)


# ---------------------------------------------------------------------------
# Test 6: Name appearing only as a substring of another word does NOT raise.
# ---------------------------------------------------------------------------


def test_name_as_substring_does_not_raise() -> None:
    """'Mia' inside 'amiable' must not trigger the guard (word-boundary check)."""
    ctx = make_ctx(names=frozenset({"Mia"}))
    # 'amiable' contains 'mia' but not as a standalone token.
    assert_prompt_pii_safe("The character was amiable and brave.", forbidden=ctx)


def test_name_as_prefix_substring_does_not_raise() -> None:
    """A name that is a prefix of another word must not trigger the guard."""
    ctx = make_ctx(names=frozenset({"Ann"}))
    # 'announce' starts with 'ann' but is not a standalone word.
    assert_prompt_pii_safe("They will announce the winner.", forbidden=ctx)


def test_name_as_suffix_substring_does_not_raise() -> None:
    """A name that is a suffix of another word must not trigger the guard."""
    ctx = make_ctx(names=frozenset({"Ian"}))
    # 'guardian' ends with 'ian' but is not a standalone word.
    assert_prompt_pii_safe("The guardian opens the gate.", forbidden=ctx)


# ---------------------------------------------------------------------------
# Test 7: Prompt containing a seeded birthdate string raises ValidationError.
# ---------------------------------------------------------------------------


def test_birthdate_iso_format_raises() -> None:
    """Prompt containing an ISO-format birthdate substring raises."""
    ctx = make_ctx(birthdates=frozenset({"2018-04-07"}))
    with pytest.raises(
        ValidationError, match=r"prompt contains a forbidden real-child identifier"
    ):
        assert_prompt_pii_safe(
            "The child was born on 2018-04-07 in the village.", forbidden=ctx
        )


def test_birthdate_rendered_format_raises() -> None:
    """Prompt containing a rendered birthdate form raises."""
    ctx = make_ctx(birthdates=frozenset({"April 7, 2018"}))
    with pytest.raises(
        ValidationError, match=r"prompt contains a forbidden real-child identifier"
    ):
        assert_prompt_pii_safe("The story is set around April 7, 2018.", forbidden=ctx)


def test_birthdate_case_insensitive_raises() -> None:
    """Birthdate substring match is case-insensitive."""
    ctx = make_ctx(birthdates=frozenset({"april 7, 2018"}))
    with pytest.raises(
        ValidationError, match=r"prompt contains a forbidden real-child identifier"
    ):
        assert_prompt_pii_safe("Set around April 7, 2018 in a forest.", forbidden=ctx)


# ---------------------------------------------------------------------------
# Test 8: Clean prompt with empty PiiContext or no matches does NOT raise.
# ---------------------------------------------------------------------------


def test_empty_context_no_raise() -> None:
    """An empty PiiContext never triggers the guard."""
    ctx = make_ctx()
    # Should not raise for any content.
    assert_prompt_pii_safe("Write a grand adventure about dragons.", forbidden=ctx)


def test_no_match_no_raise() -> None:
    """A prompt that contains no forbidden tokens does not raise."""
    ctx = make_ctx(
        names=frozenset({"Mia", "Luca"}),
        birthdates=frozenset({"2018-04-07"}),
    )
    # Prompt has no child names or birthdates.
    assert_prompt_pii_safe(
        "The wizard cast a spell on the enchanted forest.", forbidden=ctx
    )


def test_empty_name_strings_ignored() -> None:
    """Empty strings in child_names/birthdates are skipped silently."""
    ctx = make_ctx(
        names=frozenset({""}),
        birthdates=frozenset({""}),
    )
    # Empty strings must not cause false positives.
    assert_prompt_pii_safe("Any prompt at all.", forbidden=ctx)


# ---------------------------------------------------------------------------
# Test 9: The raised ValidationError does NOT contain the actual PII value.
# ---------------------------------------------------------------------------


def test_exception_does_not_echo_name() -> None:
    """The ValidationError message must not contain the actual child name."""
    secret_name = "SuperSecretChildName"
    ctx = make_ctx(names=frozenset({secret_name}))
    with pytest.raises(
        ValidationError, match=r"prompt contains a forbidden real-child identifier"
    ) as exc_info:
        assert_prompt_pii_safe(f"Tell me about {secret_name}.", forbidden=ctx)
    # The secret must not appear anywhere in the string representation.
    assert secret_name not in str(exc_info.value)
    assert secret_name.lower() not in str(exc_info.value).lower()


def test_exception_does_not_echo_birthdate() -> None:
    """The ValidationError message must not contain the actual birthdate."""
    secret_date = "1999-12-31"
    ctx = make_ctx(birthdates=frozenset({secret_date}))
    with pytest.raises(
        ValidationError, match=r"prompt contains a forbidden real-child identifier"
    ) as exc_info:
        assert_prompt_pii_safe(f"The event happened on {secret_date}.", forbidden=ctx)
    assert secret_date not in str(exc_info.value)


def test_exception_details_name_kind() -> None:
    """ValidationError raised on a name match includes kind='name' in details."""
    ctx = make_ctx(names=frozenset({"Rosa"}))
    with pytest.raises(
        ValidationError, match=r"prompt contains a forbidden real-child identifier"
    ) as exc_info:
        assert_prompt_pii_safe("Rosa crossed the bridge.", forbidden=ctx)
    assert exc_info.value.details.get("kind") == "name"


def test_exception_details_birthdate_kind() -> None:
    """ValidationError raised on a birthdate match includes kind='birthdate'."""
    ctx = make_ctx(birthdates=frozenset({"2020-01-15"}))
    with pytest.raises(
        ValidationError, match=r"prompt contains a forbidden real-child identifier"
    ) as exc_info:
        assert_prompt_pii_safe("Born on 2020-01-15 was a hero.", forbidden=ctx)
    assert exc_info.value.details.get("kind") == "birthdate"


# ---------------------------------------------------------------------------
# Test 10: Protagonist name (fictional) is NOT screened; only PiiContext is.
# ---------------------------------------------------------------------------


def test_protagonist_name_not_screened() -> None:
    """A prompt containing the fictional protagonist name but no real-child
    name must not raise, because only PiiContext names are screened."""
    # The PiiContext has a different name; the fictional protagonist "Captain Rosa"
    # is used in the prompt and must not trigger the guard.
    real_child_name = "ActualChildName"
    fictional_protagonist = "Captain Rosa"

    ctx = make_ctx(names=frozenset({real_child_name}))

    # Prompt includes the fictional protagonist name, not the real child name.
    prompt = (
        f"You are {fictional_protagonist}, a brave explorer. "
        "Your quest begins at the ancient ruins."
    )
    # Must not raise: fictional name is not in PiiContext.
    assert_prompt_pii_safe(prompt, forbidden=ctx)


def test_real_child_name_in_prompt_raises_even_when_protagonist_present() -> None:
    """If the real child's name appears alongside the protagonist name, it raises."""
    real_child_name = "ActualChildName"
    fictional_protagonist = "Captain Rosa"

    ctx = make_ctx(names=frozenset({real_child_name}))

    prompt = (
        f"You are {fictional_protagonist}. "
        f"This story was created for {real_child_name}."
    )
    with pytest.raises(
        ValidationError, match=r"prompt contains a forbidden real-child identifier"
    ):
        assert_prompt_pii_safe(prompt, forbidden=ctx)


# ---------------------------------------------------------------------------
# Adversarial / robustness tests (lookaround anchor correctness)
# ---------------------------------------------------------------------------


def test_name_with_regex_metacharacters_matches_literally() -> None:
    """A child name containing regex metacharacters is matched as a literal string.

    re.escape ensures '.' is not treated as a wildcard, so 'A.B' only matches
    the literal sequence A-period-B, not 'AxB' or 'AyB'.
    """
    # "A.B" -- the period is a regex metacharacter (matches any char) without
    # re.escape.  With re.escape it becomes a literal period match.
    ctx = make_ctx(names=frozenset({"A.B"}))

    # Literal match: 'A.B' present in prompt -> must raise.
    with pytest.raises(
        ValidationError, match=r"prompt contains a forbidden real-child identifier"
    ):
        assert_prompt_pii_safe("Hello A.B today", forbidden=ctx)

    # Dot-as-wildcard would match 'AxB', but re.escape prevents that.
    assert_prompt_pii_safe("Hello AxB today", forbidden=ctx)

    # Additional metacharacter: '+' in name must be literal.
    ctx2 = make_ctx(names=frozenset({"C+C"}))
    with pytest.raises(
        ValidationError, match=r"prompt contains a forbidden real-child identifier"
    ):
        assert_prompt_pii_safe("Music by C+C Factory.", forbidden=ctx2)
    # 'CxC' should not trigger the 'C+C' guard.
    assert_prompt_pii_safe("Music by CxC Factory.", forbidden=ctx2)


def test_name_with_trailing_nonword_char_matches() -> None:
    """A child name whose trailing character is non-word (e.g. 'J.R.') is matched.

    This is the regression case: the old r'\\b...\\b' anchors could not fire
    after the trailing '.' in 'J.R.', so 'Ask J.R. about it' would slip through.
    The lookaround anchors fix this because they only require that no WORD
    character appears immediately outside the match, regardless of whether the
    name's own edge character is a word character.
    """
    ctx = make_ctx(names=frozenset({"J.R."}))

    # 'J.R.' appears as a standalone token surrounded by spaces/sentence end.
    with pytest.raises(
        ValidationError, match=r"prompt contains a forbidden real-child identifier"
    ):
        assert_prompt_pii_safe("Ask J.R. about it", forbidden=ctx)

    # Verify the non-match case: 'JR' (no dots) should not trigger 'J.R.' guard.
    assert_prompt_pii_safe("Ask JR about it", forbidden=ctx)


def test_name_as_substring_still_not_matched_after_lookaround_fix() -> None:
    """Confirm the substring false-positive rejection still holds after the fix.

    'Mia' inside 'amiable': the 'a' immediately before 'mia' is a word char,
    so (?<!\\w) fails and the guard correctly does not fire.  This is the same
    property that \\b provided, now verified against the lookaround implementation.
    """
    ctx = make_ctx(names=frozenset({"Mia"}))
    # 'amiable' contains 'mia' (case-insensitive) but preceded by 'a' (word char).
    assert_prompt_pii_safe("The character was amiable and brave.", forbidden=ctx)


# ---------------------------------------------------------------------------
# Anti-evasion: NFKC normalization and invisible-character folding.
#
# These pin the fold added to close confirmed bypasses of the sole PII egress
# guard: a real-child name split by a zero-width character, or spelled in an
# NFKC-equivalent compatibility form, must still be caught before egress.
# Special characters are built with chr()/\u escapes so this source stays valid
# UTF-8 with no raw control bytes.
# ---------------------------------------------------------------------------

_ZWSP = "\u200b"  # ZERO WIDTH SPACE
_ZWNJ = "\u200c"  # ZERO WIDTH NON-JOINER
_ZWJ = "\u200d"  # ZERO WIDTH JOINER
_BOM = "\ufeff"  # ZERO WIDTH NO-BREAK SPACE / BOM
_SOFT_HYPHEN = "\u00ad"  # SOFT HYPHEN (category Cf)


@pytest.mark.parametrize(
    "invisible",
    [_ZWSP, _ZWNJ, _ZWJ, _BOM, _SOFT_HYPHEN, "\x00", "\x07"],
    ids=["zwsp", "zwnj", "zwj", "bom", "soft_hyphen", "nul", "bell"],
)
def test_name_split_by_invisible_char_is_still_matched(invisible: str) -> None:
    """A name broken by a zero-width or control char is caught, not bypassed."""
    ctx = make_ctx(names=frozenset({"Emma"}))
    prompt = f"A story about Em{invisible}ma at the park."
    with pytest.raises(
        ValidationError, match=r"prompt contains a forbidden real-child identifier"
    ):
        assert_prompt_pii_safe(prompt, forbidden=ctx)


def test_name_wrapped_in_invisible_chars_is_still_matched() -> None:
    """Leading and trailing zero-width chars around a name do not hide it."""
    ctx = make_ctx(names=frozenset({"Emma"}))
    prompt = f"about {_BOM}{_ZWSP}Emma{_ZWJ} today"
    with pytest.raises(ValidationError):
        assert_prompt_pii_safe(prompt, forbidden=ctx)


def test_name_in_fullwidth_form_is_matched_via_nfkc() -> None:
    """A full-width (NFKC-compatibility) spelling of a name is caught."""
    ctx = make_ctx(names=frozenset({"Emma"}))
    # Full-width Latin letters U+FF25 U+FF4D U+FF4D U+FF41 -> NFKC 'Emma'.
    # Full-width Latin U+FF25 U+FF4D U+FF4D U+FF41.
    fullwidth = "\uff25\uff4d\uff4d\uff41"
    with pytest.raises(ValidationError):
        assert_prompt_pii_safe(f"A story about {fullwidth}.", forbidden=ctx)


def test_name_with_ligature_is_matched_via_nfkc() -> None:
    """A name containing an 'fi' ligature is caught after NFKC folding."""
    ctx = make_ctx(names=frozenset({"Fiona"}))
    # U+FB01 LATIN SMALL LIGATURE FI -> NFKC 'fi'.
    with pytest.raises(ValidationError):
        assert_prompt_pii_safe("A tale of \ufb01ona the brave.", forbidden=ctx)


def test_birthdate_in_fullwidth_digits_is_matched_via_nfkc() -> None:
    """A birthdate written in full-width digits is caught after NFKC folding."""
    ctx = make_ctx(birthdates=frozenset({"2018-04-07"}))
    # Full-width digits U+FF10.. -> NFKC ASCII digits.
    # Full-width digits U+FF10..U+FF19 around ASCII hyphens.
    fullwidth_date = "\uff12\uff10\uff11\uff18-\uff10\uff14-\uff10\uff17"
    with pytest.raises(ValidationError):
        assert_prompt_pii_safe(f"born on {fullwidth_date}", forbidden=ctx)


def test_forbidden_name_carrying_invisible_char_still_screens() -> None:
    """Folding is symmetric: an invisible char in the stored name is handled.

    A ``child_profile`` value that itself carries a zero-width character must
    still screen the plain-text prompt, rather than folding to something that
    never matches.
    """
    ctx = make_ctx(names=frozenset({f"Em{_ZWSP}ma"}))
    with pytest.raises(ValidationError):
        assert_prompt_pii_safe("A story about Emma.", forbidden=ctx)


def test_name_that_is_only_invisible_chars_is_a_noop() -> None:
    """A stored name that folds to empty does not match everything.

    Without the post-fold emptiness check, a name of only zero-width chars
    would compile to an empty pattern that matches at every position and block
    every prompt.
    """
    ctx = make_ctx(names=frozenset({f"{_ZWSP}{_ZWJ}"}))
    # Must not raise: the folded name is empty and is skipped.
    assert_prompt_pii_safe("An ordinary story with no PII.", forbidden=ctx)


def test_name_with_cyrillic_homoglyph_is_not_matched() -> None:
    """Known residual: confusable homoglyphs are NOT folded (documented #EDGE).

    NFKC does not treat Cyrillic 'E' (U+0415) as equivalent to Latin 'E', and
    full UTS-39 confusable folding risks false positives on legitimate
    multilingual names, so it is deliberately out of scope. This test pins the
    current behavior so a future change to fold homoglyphs is a conscious one;
    if that fold is added, invert this assertion to expect a raise.
    """
    ctx = make_ctx(names=frozenset({"Emma"}))
    homoglyph = "\u0415mma"  # Cyrillic capital IE (U+0415) + 'mma'
    # Currently NOT caught; this documents the residual, it is not an endorsement.
    assert_prompt_pii_safe(f"A story about {homoglyph}.", forbidden=ctx)


def test_nfkc_fold_does_not_over_match_plain_unrelated_text() -> None:
    """Folding must not turn unrelated prose into a spurious PII hit."""
    ctx = make_ctx(names=frozenset({"Emma"}))
    # 'dilemma' contains 'emma' but preceded by a word char -> anchors reject.
    assert_prompt_pii_safe("The hero faced a dilemma at dawn.", forbidden=ctx)
