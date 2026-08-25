# SPDX-FileCopyrightText: 2026 Byron Williams <byronawilliams@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Freeze raw Stage-0 classifier scores before the Perspective sunset.

Google sunsets the Perspective API on 2026-12-31 with no migration path. Until
then it is a working oracle: a replacement classifier can be scored against
Perspective's own numbers on this project's own content. After that date the
oracle is gone and any successor has to be threshold-tuned against nothing.
This script captures that oracle while it still answers.

It deliberately records **raw** per-attribute scores rather than
:class:`~cyo_adventure.moderation.report.Finding` objects.
:func:`~cyo_adventure.moderation.classifiers.run_classifiers` drops graded
scores below ``_ADVISORY_SCORE_FLOOR`` (0.01) as noise, but that sub-floor band
carries calibration signal a successor needs: flatten it and the separation
between "clean fiction" and "adversarial passage" is no longer visible.

The pre-capture expectation was a Perspective ceiling of ~6e-4 on clean
children's prose. The first run of this script (2026-08-01) refuted it: all 120
clean passages scored at or above 0.01 on at least one attribute, and the clean
maximum exceeded the adversarial maximum. That is a result of the capture, not
a premise of it; see the note on ``_ADVISORY_SCORE_FLOOR``.

Two populations are captured, because a replacement has to be judged on both:

- ``adversarial``: passages from ``docs/planning/safety/adversarial-corpus.json``
  (the true positives, where a successor must score high).
- ``clean``: node prose sampled from ``out/*.filled.json``, real generated
  children's fiction (the true negatives, where a successor must stay quiet).
  This is the population that answers whether an open-weight classifier trained
  on adversarial internet comments false-positives on fantasy prose such as
  "the Wolf Queen threatened to flood the quarter".

Real network I/O and real quota, so it is opt-in and never runs in CI::

    PYTHONPATH=. uv run python scripts/capture_stage0_baseline.py \\
        --env-file .env \\
        --out "docs/planning/safety/stage0-baseline-$(date +%F).json"

Every passage passes the same PII egress guard production runs immediately
before ``run_classifiers`` (``api/node_edit.py``, ``story_requests/screening``),
so the corpus's own PII positive control is recorded as blocked rather than
POSTed to Google and OpenAI. A blocked passage is the honest class-F datum, not
a failure and not a success.

The output artifact is self-describing (schema version, capture timestamp,
probed attribute set, OpenAI model id, per-passage text digests, plus the run
parameters, corpus digest, git commit, and Stage-0 decision boundary) so a
future comparison run can prove it is scoring the same passages against the
same probe and reading them against the same thresholds.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import random
import subprocess  # nosec B404 -- read-only `git rev-parse`; audited below
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from cyo_adventure.core.exceptions import ValidationError
from cyo_adventure.generation.pii import PiiContext, assert_prompt_pii_safe
from cyo_adventure.moderation.classifiers import (
    _ADVISORY_SCORE_FLOOR,  # pyright: ignore[reportPrivateUsage]
    _OPENAI_BRIGHTLINE,  # pyright: ignore[reportPrivateUsage]
    PERSPECTIVE_ATTRIBUTES,
    PERSPECTIVE_URL,
)
from scripts.adversarial_harness import (
    _load_env_file,  # pyright: ignore[reportPrivateUsage]
)

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Bumped whenever the artifact's shape changes, so a comparison run can refuse
# to diff two baselines that do not mean the same thing. v2 added the PII
# outcome, the population split, the reproduction block, and the decision
# boundary.
_SCHEMA_VERSION = 2

_OPENAI_URL = "https://api.openai.com/v1/moderations"
_OPENAI_MODEL = "omni-moderation-latest"
_TIMEOUT = 30.0

# Historical literal: mirrored the bright-line threshold that
# ``classifiers._perspective_attribute_finding`` used before Google Perspective
# was retired as a Stage-0 signal source (ratified sunset). That function no
# longer exists in classifiers.py, so this constant no longer tracks a live
# classifier; it is kept only so this script's own pre-sunset scoring path
# (used for historical baseline comparisons) still runs. SEXUALLY_EXPLICIT at
# or above this score was a hard BLOCK, every other attribute graded against
# ``_ADVISORY_SCORE_FLOOR``. Recorded in the artifact because raw scores are
# meaningless without the boundary they were read against.
_PERSPECTIVE_BRIGHTLINE_ATTRIBUTE = "SEXUALLY_EXPLICIT"
_PERSPECTIVE_BRIGHTLINE_MIN_SCORE = 0.8

# A capture that screened less than this share of its scorable passages is a
# record of an outage, not a baseline.
_MIN_COVERAGE = 0.99

# Distinct from the "no passages" (1) and "no Perspective key" (2) exits so a
# caller can tell an unusable capture from one that never started.
_EXIT_PARTIAL_CAPTURE = 3

# Perspective's default free-tier quota is ~1 query/second; exceeding it earns a
# 429 that would silently truncate the capture. One request per second per
# provider is the conservative default.
_DEFAULT_QPS = 1.0

# Node bodies shorter than this carry too little signal to calibrate against,
# and Perspective rejects trivially short comments outright.
_MIN_PASSAGE_CHARS = 120

_DEFAULT_CORPUS = (
    _REPO_ROOT / "docs" / "planning" / "safety" / "adversarial-corpus.json"
)
_DEFAULT_FILLED_DIR = _REPO_ROOT / "out"


class MalformedProviderResponseError(ValueError):
    """A provider answered HTTP 200 with a body carrying no usable score.

    A :class:`ValueError` subclass so it joins the same per-passage failure path
    as a JSON decode error. An unusable payload is a *failed* screen: recording
    it as a success is how a throttled or post-sunset provider writes a
    fully-null baseline that reports itself as complete.
    """


@dataclass(frozen=True)
class Passage:
    """One unit of text to score, plus enough provenance to re-fetch it."""

    id: str
    population: str
    text: str
    source_ref: str
    # Corpus items carry an expected verdict; clean prose does not. Retained so a
    # comparison run can weight misses on known-bad passages.
    expected_min_verdict: str | None = None
    taxonomy_class: str | None = None
    # F1-pii-positive-control states its only outcome as ``expected:
    # "raise_before_egress"`` and carries no ``expected_min_verdict`` at all, so
    # without this field the corpus's one PII control records no expectation.
    expected: str | None = None
    negative_control: bool = False
    known_gap: bool = False
    age_band: str | None = None
    target_stage: str | int | None = None
    # Real-child names this corpus item seeds, from its ``pii_context`` block.
    # Deliberately not carried into PassageScores: the artifact records that a
    # passage was blocked, never the identifier that blocked it.
    pii_child_names: tuple[str, ...] = ()

    @property
    def text_sha256(self) -> str:
        """Digest of the exact scored text, so silent corpus drift is detectable."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


@dataclass
class PassageScores:
    """Raw provider output for one passage, or the reason there is none."""

    passage_id: str
    population: str
    source_ref: str
    text_sha256: str
    text: str
    expected_min_verdict: str | None
    taxonomy_class: str | None
    expected: str | None = None
    negative_control: bool = False
    known_gap: bool = False
    age_band: str | None = None
    target_stage: str | int | None = None
    # Set when the PII egress guard raised: no provider ever saw this text, so
    # it is neither a success nor a failure but its own third outcome.
    pii_blocked: bool = False
    perspective: dict[str, float | None] = field(default_factory=dict)
    openai_scores: dict[str, float | None] = field(default_factory=dict)
    openai_flags: dict[str, bool] = field(default_factory=dict)
    perspective_error: str | None = None
    openai_error: str | None = None


@dataclass(frozen=True)
class RunContext:
    """Everything a later run needs to reconstruct and interpret this capture.

    The clean population is sampled from ``out/*.filled.json``, whose contents
    drift with every authoring run, and the corpus is versioned in git. A
    baseline that cannot be reconstructed cannot be compared against, and
    comparison is the entire purpose of taking one.
    """

    corpus_path: str
    corpus_sha256: str | None
    filled_dir: str
    clean_limit: int
    seed: int
    qps: float
    git_commit: str | None
    perspective_configured: bool
    openai_configured: bool


def _finite_or_none(value: object) -> float | None:
    """Coerce a provider score to a JSON-portable float, or ``None``.

    Mirrors the live classifier's ``math.isfinite`` guards. httpx's ``.json()``
    parses NaN/Infinity, which would then abort the artifact write under
    ``allow_nan=False``; a non-finite score is unusable for calibration anyway,
    so it is recorded as an explicit null rather than crashing the capture.
    """
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _corpus_item_texts(item: dict[str, object]) -> list[tuple[str, str]]:
    """Return the ``(id_suffix, text)`` units one corpus item contributes.

    The corpus stores text under three different keys, and all three reach a
    Stage-0 classifier in production, so all three belong in the baseline:

    - ``passage``: a single node body (classes A, B, F, and two E items).
    - ``nodes``: the class-C aggregate items, whose harm only emerges across
      several individually-innocuous bodies. Each body is scored separately,
      exactly as the pipeline screens them.
    - ``payload``: the class-E brief-injection string, which reaches Stage 0
      through ``story_requests.screening`` rather than the moderation pipeline.
    """
    passage = item.get("passage")
    if isinstance(passage, str) and passage.strip():
        return [("", passage)]

    payload = item.get("payload")
    if isinstance(payload, str) and payload.strip():
        return [("#payload", payload)]

    nodes = item.get("nodes")
    if not isinstance(nodes, list):
        return []
    texts: list[tuple[str, str]] = []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            continue
        body = node.get("body")
        if not isinstance(body, str) or not body.strip():
            continue
        node_id = node.get("id")
        suffix = f"#{node_id}" if isinstance(node_id, str) else f"#node{index}"
        texts.append((suffix, body))
    return texts


def _corpus_pii_names(item: dict[str, object]) -> tuple[str, ...]:
    """Return the real-child names a corpus item seeds, from its ``pii_context``.

    ``F1-pii-positive-control`` is the only item carrying one today. Its own
    rationale is that a real child's name in prose bound for an external review
    model must raise before egress, so these names are exactly what the PII
    guard screens that passage against before any provider call.
    """
    context = item.get("pii_context")
    if not isinstance(context, dict):
        return ()
    names = context.get("child_names")
    if not isinstance(names, list):
        return ()
    return tuple(name for name in names if isinstance(name, str) and name.strip())


def _corpus_population(item: dict[str, object]) -> str:
    """Return the population label for a corpus item.

    ``A4-control-onband-8-11`` is ``negative_control: true``, on-band wholesome
    prose whose expected verdict is ``pass``. Labelling every corpus item
    ``adversarial`` would file a true negative in the positive population, so
    any separation statistic computed from the baseline would understate the
    gap it exists to measure.
    """
    return "control" if item.get("negative_control") is True else "adversarial"


def _str_or_none(value: object) -> str | None:
    """Narrow a raw JSON value to a string, or ``None`` if it is not one."""
    return value if isinstance(value, str) else None


def _load_adversarial_passages(corpus_path: Path) -> list[Passage]:
    """Read every text-bearing unit from the adversarial corpus.

    Items carrying no text at all (classes D1/D2, which assert structural
    bypasses rather than prose) contribute nothing and are skipped. Every
    classification field the corpus carries is propagated, because a comparison
    run has to be able to split known gaps, negative controls, age bands, and
    target stages apart without reverse-engineering them from the ids.
    """
    raw = json.loads(corpus_path.read_text(encoding="utf-8"))
    items = raw["items"] if isinstance(raw, dict) else raw
    passages: list[Passage] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", f"corpus-{len(passages)}"))
        target_stage = item.get("target_stage")
        for suffix, text in _corpus_item_texts(item):
            passages.append(
                Passage(
                    id=f"{item_id}{suffix}",
                    population=_corpus_population(item),
                    text=text,
                    source_ref=f"{corpus_path.name}#{item_id}{suffix}",
                    expected_min_verdict=_str_or_none(item.get("expected_min_verdict")),
                    taxonomy_class=_str_or_none(item.get("taxonomy_class")),
                    expected=_str_or_none(item.get("expected")),
                    negative_control=item.get("negative_control") is True,
                    known_gap=item.get("known_gap") is True,
                    age_band=_str_or_none(item.get("age_band")),
                    target_stage=(
                        target_stage
                        if isinstance(target_stage, (str, int))
                        and not isinstance(target_stage, bool)
                        else None
                    ),
                    pii_child_names=_corpus_pii_names(item),
                )
            )
    return passages


def _iter_filled_nodes(filled_dir: Path) -> Iterator[Passage]:
    """Yield every usable node body from the filled storybooks in *filled_dir*."""
    for book_path in sorted(filled_dir.glob("*.filled.json")):
        try:
            book = json.loads(book_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(book, dict):
            continue
        nodes = book.get("nodes")
        if not isinstance(nodes, list):
            continue
        book_id = str(book.get("id", book_path.stem))
        for node in nodes:
            if not isinstance(node, dict):
                continue
            body = node.get("body")
            node_id = node.get("id")
            if not isinstance(body, str) or not isinstance(node_id, str):
                continue
            # An unfilled skeleton still carries <<FILL ...>> directives; scoring
            # those would baseline the directive syntax, not children's prose.
            if "<<FILL" in body or len(body) < _MIN_PASSAGE_CHARS:
                continue
            yield Passage(
                id=f"{book_id}:{node_id}",
                population="clean",
                text=body,
                source_ref=f"{book_path.name}#{node_id}",
            )


def _load_clean_passages(filled_dir: Path, limit: int, seed: int) -> list[Passage]:
    """Deterministically sample up to *limit* clean node passages."""
    candidates = list(_iter_filled_nodes(filled_dir))
    if len(candidates) <= limit:
        return candidates
    # Seeded sample so a later comparison run scores the identical passage set.
    return random.Random(seed).sample(candidates, limit)


async def _score_perspective(
    text: str, key: str, client: httpx.AsyncClient
) -> dict[str, float | None]:
    """Return every requested attribute's raw summary score, floor-free.

    Raises:
        httpx.HTTPError: on transport failure or a non-2xx response.
        MalformedProviderResponseError: when a 200 body carries no usable score.
        ValueError: when the body is not JSON.
    """
    # #CRITICAL: security: the key travels in the x-goog-api-key header, never the
    # query string. httpx.HTTPStatusError.__str__ embeds the request URL, so a
    # keyed URL would leak the credential into this script's error output and
    # into the artifact's *_error fields.
    # #VERIFY: PERSPECTIVE_URL is key-free; the header is the only carrier.
    response = await client.post(
        PERSPECTIVE_URL,
        headers={"x-goog-api-key": key},
        json={
            "comment": {"text": text},
            "languages": ["en"],
            "requestedAttributes": {name: {} for name in PERSPECTIVE_ATTRIBUTES},
        },
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()

    # #CRITICAL: data-integrity: a screen counts as captured only on evidence of
    # an actual score, never on the mere absence of an exception. Returning an
    # all-null dict here made `{}`, an error-shaped 200 such as
    # `{"error": {"code": 429, ...}}`, and `{"attributeScores": null}` read
    # downstream as perspective_ok, because that dict is truthy: a 300-passage
    # run against a throttled or post-sunset Perspective wrote
    # "perspective_ok: 300" over 300 empty rows, printed no warning, and exited
    # 0. Google Perspective was later retired as a Stage-0 signal source
    # (ratified sunset) and classifiers.py no longer has a live Perspective
    # path at all; this script's own pre-sunset scoring path is unaffected and
    # deliberately not changed here.
    # #VERIFY: tests/unit/test_capture_stage0_baseline.py::TestProviderPayloads
    # ::test_perspective_error_shaped_body_is_recorded_as_a_failure and
    # ::test_perspective_null_attribute_scores_is_recorded_as_a_failure.
    if not isinstance(data, dict):
        msg = f"Perspective 200 body is a {type(data).__name__}, not an object"
        raise MalformedProviderResponseError(msg)
    attribute_scores = data.get("attributeScores")
    if not isinstance(attribute_scores, dict):
        msg = (
            "Perspective 200 body carries no 'attributeScores' object (got "
            f"{type(attribute_scores).__name__}); top-level keys: "
            f"{sorted(str(key) for key in data)}"
        )
        raise MalformedProviderResponseError(msg)

    scores: dict[str, float | None] = dict.fromkeys(PERSPECTIVE_ATTRIBUTES)
    for attribute, payload in attribute_scores.items():
        if not isinstance(payload, dict):
            continue
        summary = payload.get("summaryScore")
        if not isinstance(summary, dict):
            continue
        scores[str(attribute)] = _finite_or_none(summary.get("value"))
    if all(value is None for value in scores.values()):
        msg = (
            "Perspective 200 body yielded no finite score for any of the "
            f"{len(PERSPECTIVE_ATTRIBUTES)} requested attributes"
        )
        raise MalformedProviderResponseError(msg)
    return scores


async def _score_openai(
    text: str, key: str, client: httpx.AsyncClient
) -> tuple[dict[str, float | None], dict[str, bool]]:
    """Return OpenAI's raw category scores and its own boolean flags.

    Raises:
        httpx.HTTPError: on transport failure or a non-2xx response.
        MalformedProviderResponseError: when a 200 body carries no usable score.
        ValueError: when the body is not JSON.
    """
    response = await client.post(
        _OPENAI_URL,
        headers={"Authorization": f"Bearer {key}"},
        json={"model": _OPENAI_MODEL, "input": text},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()

    # #CRITICAL: data-integrity: returning an empty dict here landed a malformed
    # 200 in NEITHER bucket. `{}` is falsy so openai_ok skipped it, and
    # openai_error stayed None so openai_failed skipped it too, leaving
    # openai_ok + openai_failed silently short of the passage count. Every
    # non-score-bearing shape is an explicit error instead.
    # #VERIFY: tests/unit/test_capture_stage0_baseline.py::TestProviderPayloads
    # ::test_openai_empty_results_is_recorded_as_a_failure and
    # TestSummaryAccounting::test_provider_buckets_account_for_every_passage.
    if not isinstance(data, dict):
        msg = f"OpenAI 200 body is a {type(data).__name__}, not an object"
        raise MalformedProviderResponseError(msg)
    results = data.get("results")
    if not isinstance(results, list) or not results:
        msg = "OpenAI 200 body carries no non-empty 'results' array"
        raise MalformedProviderResponseError(msg)
    result = results[0]
    if not isinstance(result, dict):
        msg = f"OpenAI results[0] is a {type(result).__name__}, not an object"
        raise MalformedProviderResponseError(msg)

    raw_scores = result.get("category_scores")
    if not isinstance(raw_scores, dict):
        msg = (
            "OpenAI results[0] carries no 'category_scores' object (got "
            f"{type(raw_scores).__name__})"
        )
        raise MalformedProviderResponseError(msg)
    scores = {str(k): _finite_or_none(v) for k, v in raw_scores.items()}
    if all(value is None for value in scores.values()):
        msg = "OpenAI 'category_scores' yielded no finite score"
        raise MalformedProviderResponseError(msg)

    raw_flags = result.get("categories")
    flags = (
        {str(k): v for k, v in raw_flags.items() if isinstance(v, bool)}
        if isinstance(raw_flags, dict)
        else {}
    )
    return scores, flags


async def _score_passage(
    passage: Passage,
    *,
    perspective_key: str | None,
    openai_key: str | None,
    client: httpx.AsyncClient,
) -> PassageScores:
    """Screen one passage for PII, then score it with every configured provider.

    A provider failure is captured per passage rather than raised: a partial
    baseline over 300 passages is still usable calibration data, whereas an
    abort on passage 4 of a rate-limited run yields nothing. A PII match is not
    a failure at all: it is the recorded outcome, and it suppresses both calls.
    """
    record = PassageScores(
        passage_id=passage.id,
        population=passage.population,
        source_ref=passage.source_ref,
        text_sha256=passage.text_sha256,
        text=passage.text,
        expected_min_verdict=passage.expected_min_verdict,
        taxonomy_class=passage.taxonomy_class,
        expected=passage.expected,
        negative_control=passage.negative_control,
        known_gap=passage.known_gap,
        age_band=passage.age_band,
        target_stage=passage.target_stage,
    )
    # #CRITICAL: security: production runs assert_prompt_pii_safe immediately
    # before run_classifiers on every Stage-0 egress path (api/node_edit.py, and
    # story_requests/screening.py ahead of the intake screen), so a passage
    # carrying a real-child identifier never reaches Perspective or OpenAI.
    # Without the same guard here this capture would POST the corpus's own PII
    # positive control (F1-pii-positive-control, whose whole purpose is to raise
    # before egress) to commentanalyzer.googleapis.com and api.openai.com. That
    # defeats the control and baselines a passage production would never have
    # scored. The guard also runs its unconditional email/phone/address patterns
    # over every other passage, exactly as production does.
    # #VERIFY: tests/unit/test_capture_stage0_baseline.py::TestPiiGuard::
    # test_pii_positive_control_is_blocked_before_any_provider_call.
    try:
        assert_prompt_pii_safe(
            passage.text,
            forbidden=PiiContext(child_names=frozenset(passage.pii_child_names)),
        )
    except ValidationError:
        # generation/pii.py never echoes the matched value, and neither does this
        # record: that a passage was blocked is the class-F datum, the
        # identifier that blocked it is not.
        record.pii_blocked = True
        return record
    # #CRITICAL: external-resource: both classifiers are network calls against
    # rate-limited third-party quota. Neither failure may abort the capture, and
    # neither may be silent: an unrecorded failure would read downstream as a
    # genuine all-zero score, which is exactly the miscalibration this baseline
    # exists to prevent.
    # #VERIFY: tests/unit/test_capture_stage0_baseline.py::TestSummaryAccounting
    # ::test_provider_buckets_account_for_every_passage pins that every passage
    # lands in exactly one of ok / failed / pii_blocked per configured provider,
    # and TestProviderPayloads pins that each malformed shape sets a non-null
    # *_error.
    if perspective_key:
        try:
            record.perspective = await _score_perspective(
                passage.text, perspective_key, client
            )
        except (httpx.HTTPError, ValueError) as exc:
            record.perspective_error = str(exc)
    if openai_key:
        try:
            record.openai_scores, record.openai_flags = await _score_openai(
                passage.text, openai_key, client
            )
        except (httpx.HTTPError, ValueError) as exc:
            record.openai_error = str(exc)
    return record


async def capture(
    passages: Sequence[Passage],
    *,
    perspective_key: str | None,
    openai_key: str | None,
    qps: float,
) -> list[PassageScores]:
    """Score every passage in order, pacing requests to respect provider quota."""
    delay = 1.0 / qps if qps > 0 else 0.0
    records: list[PassageScores] = []
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        for index, passage in enumerate(passages, start=1):
            records.append(
                await _score_passage(
                    passage,
                    perspective_key=perspective_key,
                    openai_key=openai_key,
                    client=client,
                )
            )
            print(
                f"  [{index}/{len(passages)}] {passage.population}: {passage.id}",
                file=sys.stderr,
            )
            # Sequential and paced on purpose: this runs once, and a 429 storm
            # would cost more wall-clock in retries than the pacing costs here.
            if delay and index < len(passages):
                await asyncio.sleep(delay)
    return records


def _summarize(records: Sequence[PassageScores]) -> dict[str, int]:
    """Count outcomes per provider and per population, for the run summary.

    Every passage lands in exactly one bucket per *configured* provider:
    ``ok``, ``failed``, or ``pii_blocked``. A provider that was never configured
    scores zero in all three, which is why configuration is reported separately
    in the artifact's ``probe`` block rather than inferred from these counts.
    """
    return {
        "passages": len(records),
        "pii_blocked": sum(1 for r in records if r.pii_blocked),
        "adversarial": sum(1 for r in records if r.population == "adversarial"),
        "control": sum(1 for r in records if r.population == "control"),
        "clean": sum(1 for r in records if r.population == "clean"),
        "perspective_ok": sum(
            1
            for r in records
            if r.perspective and not r.perspective_error and not r.pii_blocked
        ),
        "perspective_failed": sum(1 for r in records if r.perspective_error),
        "openai_ok": sum(
            1
            for r in records
            if r.openai_scores and not r.openai_error and not r.pii_blocked
        ),
        "openai_failed": sum(1 for r in records if r.openai_error),
    }


def _decision_boundary() -> dict[str, object]:
    """The Stage-0 thresholds this baseline's raw scores must be read against.

    Raw sub-floor scores are the calibration signal, but they only mean
    something relative to the boundary the live gate applies. Recording it here
    means a comparison run does not have to guess which boundary was in force
    when the baseline was taken.
    """
    return {
        "advisory_score_floor": _ADVISORY_SCORE_FLOOR,
        "openai_brightline_categories": sorted(_OPENAI_BRIGHTLINE),
        "perspective_brightline_attribute": _PERSPECTIVE_BRIGHTLINE_ATTRIBUTE,
        "perspective_brightline_min_score": _PERSPECTIVE_BRIGHTLINE_MIN_SCORE,
    }


def _build_artifact(
    records: Sequence[PassageScores],
    *,
    captured_at: str,
    counts: dict[str, int],
    run: RunContext | None = None,
) -> dict[str, object]:
    """Assemble the self-describing baseline artifact."""
    return {
        "schema_version": _SCHEMA_VERSION,
        "captured_at": captured_at,
        "purpose": (
            "Raw Stage-0 classifier scores captured before the Google "
            "Perspective sunset on 2026-12-31, for calibrating a replacement "
            "classifier against this project's own content."
        ),
        "probe": {
            "perspective_url": PERSPECTIVE_URL,
            "perspective_attributes": list(PERSPECTIVE_ATTRIBUTES),
            # A provider with no key is never called, so advertising its URL and
            # model without saying so would describe a probe that did not run.
            "perspective_configured": bool(run and run.perspective_configured),
            "openai_url": _OPENAI_URL,
            "openai_model": _OPENAI_MODEL,
            "openai_configured": bool(run and run.openai_configured),
        },
        "reproduction": asdict(run) if run else None,
        "decision_boundary": _decision_boundary(),
        "counts": counts,
        "records": [asdict(record) for record in records],
    }


def _file_sha256(path: Path) -> str | None:
    """Digest a file's bytes, or ``None`` when it cannot be read."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _repo_relative(path: Path) -> str:
    """Render *path* relative to the repo root when it lives inside it."""
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(_REPO_ROOT))
    except ValueError:
        return str(resolved)


def _git_commit() -> str | None:
    """Return the repo's HEAD sha, or ``None`` when git cannot answer."""
    # #ASSUME: external-resource: git is on PATH and _REPO_ROOT is a work tree.
    # list-form argv and no shell, and `rev-parse` is read-only, so this can
    # never mutate the repository. A git failure degrades to a null commit
    # rather than aborting a capture that has already spent provider quota.
    # #VERIFY: tests/unit/test_capture_stage0_baseline.py::TestReproduction::
    # test_git_commit_is_null_when_git_is_unavailable.
    try:
        result = subprocess.run(  # nosec B603 B607
            ["git", "-C", str(_REPO_ROOT), "rev-parse", "HEAD"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = result.stdout.strip()
    return commit if result.returncode == 0 and commit else None


def _run_context(
    args: argparse.Namespace, *, perspective_key: str | None, openai_key: str | None
) -> RunContext:
    """Capture everything needed to reconstruct and interpret this run."""
    corpus_path: Path = args.corpus
    return RunContext(
        corpus_path=_repo_relative(corpus_path),
        corpus_sha256=_file_sha256(corpus_path),
        filled_dir=_repo_relative(args.filled_dir),
        clean_limit=args.clean_limit,
        seed=args.seed,
        qps=args.qps,
        git_commit=_git_commit(),
        perspective_configured=bool(perspective_key),
        openai_configured=bool(openai_key),
    )


def _coverage_shortfalls(
    counts: dict[str, int], *, openai_configured: bool
) -> list[str]:
    """Describe every reason this capture is not a complete baseline.

    Perspective is always configured by the time this runs (``main`` exits
    early otherwise), so its coverage is always checked; OpenAI's is checked
    only when a key was present, since an absent provider is a declared gap
    rather than a shortfall.
    """
    shortfalls: list[str] = []
    if counts["perspective_failed"] or counts["openai_failed"]:
        shortfalls.append(
            f"{counts['perspective_failed']} Perspective and "
            f"{counts['openai_failed']} OpenAI call(s) failed"
        )
    scorable = counts["passages"] - counts["pii_blocked"]
    checks = [
        ("Perspective", "perspective_ok", True),
        ("OpenAI", "openai_ok", openai_configured),
    ]
    for label, key, configured in checks:
        if not configured:
            continue
        covered = counts[key] / scorable if scorable else 0.0
        if covered < _MIN_COVERAGE:
            shortfalls.append(
                f"{label} covered {counts[key]}/{scorable} scorable passage(s), "
                f"below the {_MIN_COVERAGE:.0%} floor"
            )
    return shortfalls


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Capture raw Perspective and OpenAI Stage-0 scores over the "
            "adversarial corpus and clean generated prose, before the "
            "Perspective sunset on 2026-12-31."
        )
    )
    parser.add_argument("--corpus", type=Path, default=_DEFAULT_CORPUS)
    parser.add_argument("--filled-dir", type=Path, default=_DEFAULT_FILLED_DIR)
    parser.add_argument(
        "--clean-limit",
        type=int,
        default=120,
        help="Max clean passages to sample (default: 120). 0 disables them.",
    )
    parser.add_argument(
        "--seed", type=int, default=20261231, help="Seed for the clean-passage sample."
    )
    parser.add_argument(
        "--qps",
        type=float,
        default=_DEFAULT_QPS,
        help=f"Requests per second per provider (default: {_DEFAULT_QPS}).",
    )
    parser.add_argument("--env-file", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Assemble and report the passage set without calling any provider.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    args = _parse_args(argv)
    if args.env_file:
        _load_env_file(args.env_file)

    passages = _load_adversarial_passages(args.corpus)
    if args.clean_limit > 0:
        passages.extend(
            _load_clean_passages(args.filled_dir, args.clean_limit, args.seed)
        )
    if not passages:
        print("No passages found; nothing to capture.", file=sys.stderr)
        return 1

    adversarial = sum(1 for p in passages if p.population == "adversarial")
    control = sum(1 for p in passages if p.population == "control")
    clean = len(passages) - adversarial - control
    print(
        f"Passage set: {len(passages)} total "
        f"({adversarial} adversarial, {control} control, {clean} clean)",
        file=sys.stderr,
    )

    if args.dry_run:
        print("--dry-run: no provider calls made.", file=sys.stderr)
        return 0

    perspective_key = os.environ.get("PERSPECTIVE_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    if not perspective_key:
        # The whole point of this capture is the Perspective oracle; an
        # OpenAI-only run produces an artifact that cannot calibrate anything
        # against the provider that is disappearing.
        print(
            "ERROR: PERSPECTIVE_API_KEY is not set. This capture exists to "
            "record Perspective's scores before its 2026-12-31 sunset; without "
            "it there is no baseline to take.",
            file=sys.stderr,
        )
        return 2
    if not openai_key:
        print(
            "WARNING: OPENAI_API_KEY is not set; the artifact will hold no "
            "OpenAI comparison column.",
            file=sys.stderr,
        )

    records = asyncio.run(
        capture(
            passages,
            perspective_key=perspective_key,
            openai_key=openai_key,
            qps=args.qps,
        )
    )
    counts = _summarize(records)
    artifact = _build_artifact(
        records,
        captured_at=datetime.now(UTC).isoformat(),
        counts=counts,
        run=_run_context(args, perspective_key=perspective_key, openai_key=openai_key),
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    # allow_nan=False guarantees a portable artifact; _finite_or_none has already
    # converted every non-finite provider score to an explicit null.
    args.out.write_text(
        json.dumps(artifact, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    print(f"\nWrote {args.out}", file=sys.stderr)
    for label, value in counts.items():
        print(f"  {label}: {value}", file=sys.stderr)
    if counts["perspective_failed"]:
        print(
            f"\nWARNING: {counts['perspective_failed']} Perspective call(s) "
            "failed; the baseline is partial. Re-run with a lower --qps.",
            file=sys.stderr,
        )
    # #CRITICAL: data-integrity: exit non-zero on a partial capture. A zero exit
    # is the only signal automation reads, so returning 0 after writing a
    # half-empty artifact is how a record of an outage gets filed as the
    # pre-sunset baseline, which cannot be retaken after 2026-12-31.
    # #VERIFY: tests/unit/test_capture_stage0_baseline.py::TestCoverageGate.
    shortfalls = _coverage_shortfalls(counts, openai_configured=bool(openai_key))
    if shortfalls:
        for shortfall in shortfalls:
            print(f"\nERROR: {shortfall}.", file=sys.stderr)
        print(
            "The artifact was written but is NOT a complete baseline; "
            "exiting non-zero so it is not recorded as a clean run.",
            file=sys.stderr,
        )
        return _EXIT_PARTIAL_CAPTURE
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
