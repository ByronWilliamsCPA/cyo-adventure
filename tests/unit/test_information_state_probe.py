"""W15's decisive test, run as a probe. Outcome: DROP.

W15 proposed extending the skeleton node schema with an ``unknowns_to_preserve``
list and adding a checker that fails a filled node whose prose reveals one of the
declared secrets. Its pre-registered rule:

    Keep iff the paraphrase test passes and the false-positive rate on
    already-shipped catalogue nodes is zero. If it only catches literal
    restatement, drop it and record that the information-state dimension stays
    uninstrumented, because a checker that catches only the naive case and
    reports clean otherwise is the AL-337 harm rather than its fix.

This module runs that test rather than predicting it. The candidate checker is
implemented here, in the tests, deliberately: shipping it under ``validator/``
and then deleting it would leave the evidence in a commit message, and the point
of a pre-registered rule is that the negative result is a deliverable.

**Result.** The checker passes the three easy cases and fails the decisive one. A
declared secret restated in different words goes undetected, because detecting it
is an entailment question and nothing in this repository can answer one: there is
no lexical resource and no embedding model in the dependency set (`nltk`, `spacy`,
`gensim` and `scikit-learn` are all absent), and adding one would not close the
gap anyway. "The lighthouse keeper is the thief" leaks just as completely through
"the man who tends the light had taken it", which shares no content word with the
declaration.

So the honest report is the one the rule prescribes: **the information-state
dimension stays uninstrumented**, and it belongs in `blind_spots.UNOBSERVED`
alongside the four qualitative age dimensions rather than behind a checker that
would report clean on everything but a copy-paste.
"""

from __future__ import annotations

import re


def _leaks(body: str, unknowns_to_preserve: list[str]) -> list[str]:
    """Return declared secrets this prose reveals, by the only means available.

    Word-boundary matching over each declared secret's content words, requiring
    all of them to appear. This is the strongest purely lexical form of the
    check: looser than it (any content word) fires on innocent prose, stricter
    than it (exact phrase) misses ordinary reordering.

    Args:
        body: The filled node's prose.
        unknowns_to_preserve: Facts the node declared it would withhold.

    Returns:
        The declarations judged revealed.
    """
    lowered = body.lower()
    hits: list[str] = []
    for secret in unknowns_to_preserve:
        words = [w for w in re.findall(r"[a-z]+", secret.lower()) if len(w) > 3]
        if words and all(
            re.search(rf"\b{re.escape(word)}\b", lowered) for word in words
        ):
            hits.append(secret)
    return hits


_SECRET = "the lighthouse keeper is the thief"


def test_a_node_that_states_its_declared_secret_plainly_is_caught() -> None:
    """The easy case, which any substring check passes."""
    body = (
        "Mara climbed the stairs and saw at once that the lighthouse keeper "
        "is the thief, and her stomach went cold."
    )

    assert _leaks(body, [_SECRET]) == [_SECRET]


def test_a_node_that_withholds_its_declared_secret_passes() -> None:
    """The companion case: the checker must not fire on prose that withholds."""
    body = (
        "Mara climbed the stairs. The lamp room was empty, and the logbook "
        "lay open at a page nobody had signed."
    )

    assert _leaks(body, [_SECRET]) == []


def test_a_node_declaring_nothing_is_unaffected() -> None:
    """The field's absence must never be a finding."""
    body = "Mara climbed the stairs and counted them under her breath."

    assert _leaks(body, []) == []


def test_the_decisive_case_fails_and_this_is_why_w15_drops() -> None:
    """A paraphrase of the declared secret goes straight through.

    This is the test W15's rule turns on, and it fails. The prose below reveals
    the withheld fact completely to any reader while sharing no content word with
    the declaration, so no lexical rule can separate it from the withholding case
    above.

    The assertion is written to the observed behaviour rather than the desired
    one, on purpose. A test asserting the desired behaviour would sit red as a
    to-do; asserting the actual behaviour records a measurement, and the
    measurement is that this dimension cannot be instrumented deterministically
    here.
    """
    paraphrase = (
        "Mara climbed the stairs and understood: the man who tended the light "
        "had been taking the cargo all along."
    )

    # Reveals the secret to a reader. Detected by nothing.
    assert _leaks(paraphrase, [_SECRET]) == []


def test_the_checker_is_a_substring_match_wearing_other_language() -> None:
    """Name what the candidate actually is, so nobody re-proposes it as more.

    Reordering the declared words still trips it and paraphrase still does not,
    which is the signature of a lexical matcher rather than an information-state
    check. W15's own wording anticipated this outcome; the value of running it is
    that the anticipation is now a measurement.
    """
    reordered = "The thief, it turned out, is the keeper of the lighthouse."
    paraphrase = "The man who tended the light had been taking the cargo."

    assert _leaks(reordered, [_SECRET]) == [_SECRET]
    assert _leaks(paraphrase, [_SECRET]) == []
