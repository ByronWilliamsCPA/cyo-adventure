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
is precisely the calibration signal: on clean children's prose Perspective's
observed ceiling is ~6e-4, so a successor's separation between "clean fiction"
and "adversarial passage" is invisible once the floor has flattened it.

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
        --out docs/planning/safety/stage0-baseline-2026-07-28.json

The output artifact is self-describing (schema version, capture timestamp,
probed attribute set, OpenAI model id, per-passage text digests) so a future
comparison run can prove it is scoring the same passages against the same
probe.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import random
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from cyo_adventure.moderation.classifiers import (
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
# to diff two baselines that do not mean the same thing.
_SCHEMA_VERSION = 1

_OPENAI_URL = "https://api.openai.com/v1/moderations"
_OPENAI_MODEL = "omni-moderation-latest"
_TIMEOUT = 30.0

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

    @property
    def text_sha256(self) -> str:
        """Digest of the exact scored text, so silent corpus drift is detectable."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


@dataclass
class PassageScores:
    """Raw provider output for one passage, or the error that prevented it."""

    passage_id: str
    population: str
    source_ref: str
    text_sha256: str
    text: str
    expected_min_verdict: str | None
    taxonomy_class: str | None
    perspective: dict[str, float | None] = field(default_factory=dict)
    openai_scores: dict[str, float | None] = field(default_factory=dict)
    openai_flags: dict[str, bool] = field(default_factory=dict)
    perspective_error: str | None = None
    openai_error: str | None = None


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


def _load_adversarial_passages(corpus_path: Path) -> list[Passage]:
    """Read every text-bearing unit from the adversarial corpus.

    Items carrying no text at all (classes D1/D2, which assert structural
    bypasses rather than prose) contribute nothing and are skipped.
    """
    raw = json.loads(corpus_path.read_text(encoding="utf-8"))
    items = raw["items"] if isinstance(raw, dict) else raw
    passages: list[Passage] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id", f"corpus-{len(passages)}"))
        expected = item.get("expected_min_verdict")
        taxonomy = item.get("taxonomy_class")
        for suffix, text in _corpus_item_texts(item):
            passages.append(
                Passage(
                    id=f"{item_id}{suffix}",
                    population="adversarial",
                    text=text,
                    source_ref=f"{corpus_path.name}#{item_id}{suffix}",
                    expected_min_verdict=(
                        expected if isinstance(expected, str) else None
                    ),
                    taxonomy_class=taxonomy if isinstance(taxonomy, str) else None,
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

    scores: dict[str, float | None] = dict.fromkeys(PERSPECTIVE_ATTRIBUTES)
    attribute_scores = data.get("attributeScores") if isinstance(data, dict) else None
    if not isinstance(attribute_scores, dict):
        return scores
    for attribute, payload in attribute_scores.items():
        if not isinstance(payload, dict):
            continue
        summary = payload.get("summaryScore")
        if not isinstance(summary, dict):
            continue
        scores[str(attribute)] = _finite_or_none(summary.get("value"))
    return scores


async def _score_openai(
    text: str, key: str, client: httpx.AsyncClient
) -> tuple[dict[str, float | None], dict[str, bool]]:
    """Return OpenAI's raw category scores and its own boolean flags.

    Raises:
        httpx.HTTPError: on transport failure or a non-2xx response.
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

    if not isinstance(data, dict):
        return {}, {}
    results = data.get("results")
    if not isinstance(results, list) or not results:
        return {}, {}
    result = results[0]
    if not isinstance(result, dict):
        return {}, {}

    raw_scores = result.get("category_scores")
    raw_flags = result.get("categories")
    scores = (
        {str(k): _finite_or_none(v) for k, v in raw_scores.items()}
        if isinstance(raw_scores, dict)
        else {}
    )
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
    """Score one passage with every configured provider, recording failures.

    A provider failure is captured per passage rather than raised: a partial
    baseline over 300 passages is still usable calibration data, whereas an
    abort on passage 4 of a rate-limited run yields nothing.
    """
    record = PassageScores(
        passage_id=passage.id,
        population=passage.population,
        source_ref=passage.source_ref,
        text_sha256=passage.text_sha256,
        text=passage.text,
        expected_min_verdict=passage.expected_min_verdict,
        taxonomy_class=passage.taxonomy_class,
    )
    # #CRITICAL: external-resource: both classifiers are network calls against
    # rate-limited third-party quota. Neither failure may abort the capture, and
    # neither may be silent: an unrecorded failure would read downstream as a
    # genuine all-zero score, which is exactly the miscalibration this baseline
    # exists to prevent.
    # #VERIFY: perspective_error / openai_error are non-null on every failure and
    # _summarize reports the counts before the artifact is written.
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
    """Count captured and failed scores per provider, for the run summary."""
    return {
        "passages": len(records),
        "perspective_ok": sum(
            1 for r in records if r.perspective and not r.perspective_error
        ),
        "perspective_failed": sum(1 for r in records if r.perspective_error),
        "openai_ok": sum(1 for r in records if r.openai_scores and not r.openai_error),
        "openai_failed": sum(1 for r in records if r.openai_error),
    }


def _build_artifact(
    records: Sequence[PassageScores], *, captured_at: str, counts: dict[str, int]
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
            "openai_url": _OPENAI_URL,
            "openai_model": _OPENAI_MODEL,
        },
        "counts": counts,
        "records": [asdict(record) for record in records],
    }


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
    clean = len(passages) - adversarial
    print(
        f"Passage set: {len(passages)} total "
        f"({adversarial} adversarial, {clean} clean)",
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
