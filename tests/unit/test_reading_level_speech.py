"""WP-2.7: the reading-level measure scores speech as joined sentences.

Pins the before/after for dialogue (AL-771), the abbreviation guard (AL-785),
and that speech-free prose across the committed ``out/`` books is unmeasurably
different from the old terminator-run count.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from cyo_adventure.validator import reading_level as rl

_REPO = Path(__file__).resolve().parents[2]
_OLD_SENTENCE_RE = re.compile(r"[.!?]+")
# Quotation marks: straight double, curly double. A body with none of these is
# "speech-free"; apostrophes (straight or U+2019) are contractions, not speech.
_QUOTE_CHARS = '"“”'


def _old_score(body: str) -> float | None:
    """Score *body* with the pre-WP-2.7 sentence count (every terminator run)."""
    original = rl._count_sentences
    rl._count_sentences = lambda t: len(_OLD_SENTENCE_RE.findall(t))  # type: ignore[assignment]  # pyright: ignore[reportPrivateUsage]
    try:
        return rl.score_body(body)
    finally:
        rl._count_sentences = original  # type: ignore[assignment]


def _has_speech(body: str) -> bool:
    return any(ch in body for ch in _QUOTE_CHARS)


def _out_nodes() -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []
    for path in sorted((_REPO / "out").glob("*.filled.json")):
        nodes = json.loads(path.read_text(encoding="utf-8"))["nodes"]
        items = nodes.values() if isinstance(nodes, dict) else nodes
        rows.extend((path.name, n["id"], n["body"]) for n in items)
    return rows


FILLER = "The keeper walked down to the old lamp and looked at the sea again. "


class TestSpeechJoined:
    def test_consecutive_quote_only_lines_are_one_sentence(self) -> None:
        text = '"Yes." "Go." "Now." "Hurry." "Please."'
        assert rl._count_sentences(text) == 1

    def test_quote_with_lowercase_tag_is_one_sentence(self) -> None:
        assert rl._count_sentences('"Run now!" she called.') == 1

    def test_narration_between_lines_still_splits(self) -> None:
        text = '"Yes." Pip nodded. "Go."'
        assert rl._count_sentences(text) == 3

    def test_curly_quotes_join_too(self) -> None:
        text = "“Yes.” “Go.” “Now.”"
        assert rl._count_sentences(text) == 1

    def test_dialogue_heavy_body_scores_higher_than_before(self) -> None:
        body = FILLER + '"Yes." "Go." "Now." "Wait." "Look." "Run." "Hide." "Stay."'
        old = _old_score(body)
        new = rl.score_body(body)
        assert old is not None
        assert new is not None
        assert new > old


class TestAbbreviationGuard:
    def test_titles_do_not_end_sentences(self) -> None:
        body = FILLER + "Mr. Fez and Dr. Vole waited by the door for the tide. "
        assert rl._count_sentences(body) == 2
        old = _old_score(body)
        new = rl.score_body(body)
        assert old is not None
        assert new is not None
        assert new > old


def _git_show(rev: str, path: str) -> str | None:
    result = subprocess.run(
        ["git", "show", f"{rev}:{path}"],  # noqa: S607
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout if result.returncode == 0 else None


class TestHollowLighthouseDraft:
    """First dialogue draft of the-hollow-lighthouse (commit 15b14a1)."""

    def test_dialogue_node_pin(self) -> None:
        raw = _git_show("15b14a1", "out/the-hollow-lighthouse.filled.json")
        if raw is None:
            pytest.skip("commit 15b14a1 not reachable in this checkout")
        nodes = json.loads(raw)["nodes"]
        items = list(nodes.values()) if isinstance(nodes, dict) else nodes
        by_id = {n["id"]: n["body"] for n in items}
        node_id, old_expected, new_expected = _PINNED
        old = _old_score(by_id[node_id])
        new = rl.score_body(by_id[node_id])
        assert old is not None
        assert new is not None
        assert round(old, 2) == old_expected
        assert round(new, 2) == new_expected
        assert new > old


_PINNED: tuple[str, float, float] = ("e_win_rescue", 4.18, 4.88)


# Reasons a quote-free node may legitimately move. Measured over out/: every
# quote-free node that changed falls in one of these two, nothing else does.
#  - an abbreviation period (AL-785, the guard is the point of the change);
#  - the corpus's unquoted speech convention, "Ting! went the little bell.",
#    where a "!"/"?" is followed by a lowercase speech tag (AL-771 joins it).
_ABBREVIATION_RE = re.compile(r"\b(?:Mr|Mrs|Ms|Dr|St|Jr|Sr|vs|etc)\.|\b[ei]\.[ge]\.")
_UNQUOTED_TAG_RE = re.compile(r"[!?]+\s+[a-z]")


def _explained(body: str) -> bool:
    return bool(_ABBREVIATION_RE.search(body) or _UNQUOTED_TAG_RE.search(body))


class TestSpeechFreeUnchanged:
    def test_no_change_for_speech_free_nodes_across_out(self) -> None:
        rows = _out_nodes()
        assert rows, "no out/*.filled.json books found"
        unexplained: list[tuple[str, str, float | None, float | None]] = []
        free = 0
        for book, node_id, body in rows:
            if _has_speech(body):
                continue
            free += 1
            old, new = _old_score(body), rl.score_body(body)
            if old != new and not _explained(body):
                unexplained.append((book, node_id, old, new))
        assert free > 0
        assert unexplained == []

    def test_plain_quote_free_prose_is_identical(self) -> None:
        body = FILLER * 3 + "The tide came in. Pip waited. Then Pip ran home!"
        assert rl.score_body(body) == _old_score(body)
