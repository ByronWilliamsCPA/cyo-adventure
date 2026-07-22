"""WS-8 catalog-flywheel discard ledger (design section 6.3).

The flywheel's per-attempt memory. Every candidate attempt (a parent plus a
bounded operator chain) is recorded here exactly once, keyed by a
timestamp-independent ``attempt_sig``, so the candidate strategy never re-runs
a signature whose outcome is already known: operators are deterministic, so
re-running a recorded signature provably reproduces its outcome (design
principle 7, "discard never weaken").

The ledger lives under the gitignored ``out/mutations/_ledger/attempts.jsonl``
(append-only JSON Lines). It is scratch, not source of truth: a lost ledger
costs only recomputation, never correctness, because ``attempt_sig`` is a pure
function of ``(parent_sha256, chain)`` and the same signature always re-derives
the same candidate (design 6.3 #EDGE).

Pure-ish module: standard library plus the ``mutation`` value types. It reads
and appends one file, both under ``out/`` only; it never writes under
``skeletons/`` and holds no database or network dependency.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Sequence

    from cyo_adventure.mutation.compose import ChainStep

# The ledger path, relative to the repository root. Under gitignored ``out/``
# (design 6.3): scratch memory, re-derivable, never committed.
LEDGER_REL_PATH = Path("out") / "mutations" / "_ledger" / "attempts.jsonl"

# The closed set of attempt outcomes the ledger records. A surviving candidate
# is ``promotable`` or ``held``; a non-selected survivor is ``shelved`` (design
# 6.4); anything acceptance rejects is ``discarded``.
OUTCOME_PROMOTABLE = "promotable"
OUTCOME_HELD = "held"
OUTCOME_DISCARDED = "discarded"
OUTCOME_SHELVED = "shelved"
_OUTCOMES: frozenset[str] = frozenset(
    {OUTCOME_PROMOTABLE, OUTCOME_HELD, OUTCOME_DISCARDED, OUTCOME_SHELVED}
)


def chain_signature(steps: Sequence[ChainStep]) -> list[dict[str, object]]:
    """Return a chain's canonical, JSON-round-trippable step list.

    Each step is reduced to ``{"op", "params", "seed"}`` with the params as a
    plain dict, so the same chain always serializes identically regardless of
    how the :class:`~cyo_adventure.mutation.compose.ChainStep` values were
    built. This is the exact shape hashed into :func:`attempt_sig` and stored in
    the ledger ``chain`` field.

    Args:
        steps: The chain steps, in application order.

    Returns:
        list[dict[str, object]]: One canonical entry per step.
    """
    return [
        {"op": step.op_id, "params": step.params.mapping, "seed": step.seed}
        for step in steps
    ]


def attempt_sig(parent_sha256: str, steps: Sequence[ChainStep]) -> str:
    """Return the deterministic, timestamp-independent signature of an attempt.

    ``attempt_sig = sha256(parent_sha256 + canonical-JSON(chain))`` (design
    6.3). It is a pure function of the parent content hash and the operator
    chain, so it is stable across runs and independent of when the attempt ran.
    A parent content change changes ``parent_sha256`` and therefore the
    signature, which correctly invalidates any stale memory for that parent.

    Args:
        parent_sha256: The parent's canonical content hash
            (:func:`~cyo_adventure.mutation.bundle.content_sha256`).
        steps: The chain steps, in application order.

    Returns:
        str: The hex SHA-256 digest.
    """
    # #CRITICAL: data-integrity: the signature must be a pure function of
    # content only (no timestamp, no run id), so a recorded outcome is a valid
    # skip decision on any later cycle and a lost ledger re-derives identically.
    # SHA-256 is a FIPS-approved digest, safe on FIPS-enabled deployments.
    # #VERIFY: tests assert two builds of the same (parent_sha256, chain) yield
    # the same sig, that a differing seed changes it, and that it never depends
    # on wall-clock time.
    canonical = json.dumps(
        chain_signature(steps),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    payload = f"{parent_sha256}{canonical}".encode()
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class AttemptRecord:
    """One append-only ledger record for a single flywheel attempt (design 6.3).

    Attributes:
        attempt_sig: The attempt's deterministic signature (:func:`attempt_sig`).
        parent_slug: The parent skeleton's catalog slug.
        parent_sha256: The parent's canonical content hash at attempt time.
        cell: The saturated cell coordinate ``{band, length, style}`` the
            attempt targets (enum values only; no theme text, design principle
            5).
        chain: The canonical chain step list (:func:`chain_signature`).
        outcome: The attempt's final disposition (one of :data:`_OUTCOMES`).
        failing_stage: The acceptance stage that discarded the candidate, or
            None when it survived.
        discard_reason: The discard reason, or an empty string when it survived.
        distances: The structural distances recorded for a surviving candidate
            (``parent_distance`` and ``min_in_cell_distance``); empty otherwise.
        timestamp: The ISO-8601 record time, supplied by the caller. NOT part of
            :attr:`attempt_sig` (design 6.3), so replay determinism holds.
    """

    attempt_sig: str
    parent_slug: str
    parent_sha256: str
    cell: dict[str, str]
    chain: list[dict[str, object]]
    outcome: str
    failing_stage: str | None
    discard_reason: str
    distances: dict[str, float]
    timestamp: str

    def to_json(self) -> dict[str, object]:
        """Return the record as a JSON-serializable dict.

        Returns:
            dict[str, object]: The one-line ledger payload.
        """
        return {
            "attempt_sig": self.attempt_sig,
            "parent_slug": self.parent_slug,
            "parent_sha256": self.parent_sha256,
            "cell": self.cell,
            "chain": self.chain,
            "outcome": self.outcome,
            "failing_stage": self.failing_stage,
            "discard_reason": self.discard_reason,
            "distances": self.distances,
            "timestamp": self.timestamp,
        }


def ledger_path(repo_root: Path) -> Path:
    """Return the ledger file path under a repository root.

    Args:
        repo_root: The repository root the ``out/`` tree hangs off.

    Returns:
        Path: The ``out/mutations/_ledger/attempts.jsonl`` path (not created).
    """
    return repo_root / LEDGER_REL_PATH


def load_outcomes(path: Path) -> dict[str, str]:
    """Return the known ``attempt_sig -> outcome`` map from the ledger file.

    A missing ledger is an empty map (the pre-first-cycle bootstrap, or a fresh
    checkout that lost the gitignored scratch file); this is acceptable by
    design because determinism means recomputation is free (design 6.3 #EDGE).
    A malformed line is skipped rather than aborting the read, so a partial
    write can never wedge the strategy. A later record for the same signature
    supersedes an earlier one (last-write-wins), which is how a shelved survivor
    is re-recorded across cycles.

    Args:
        path: The ledger file path.

    Returns:
        dict[str, str]: Each recorded signature mapped to its latest outcome.
    """
    # #EDGE: external-resources: the ledger is gitignored scratch, so a fresh
    # checkout legitimately has none; a missing file is an empty map, never an
    # error. A corrupt line (interrupted append) is skipped, not fatal.
    # #VERIFY: tests round-trip an append then load, assert a missing file loads
    # empty, and assert a junk line is skipped.
    if not path.is_file():
        return {}
    outcomes: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            record = cast("object", json.loads(stripped))
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        row = cast("dict[str, object]", record)
        sig = row.get("attempt_sig")
        outcome = row.get("outcome")
        if isinstance(sig, str) and isinstance(outcome, str):
            outcomes[sig] = outcome
    return outcomes


def _coerce_record(row: dict[str, object]) -> AttemptRecord | None:
    """Return an :class:`AttemptRecord` from a parsed ledger row, or None on junk.

    Every field is type-checked defensively so a hand-edited or partially written
    line can never crash the reader (the D7 flywheel report reads this): a row
    missing a required scalar, or carrying the wrong type, is dropped rather than
    coerced. A row whose ``outcome`` is not a known outcome is also dropped, so the
    funnel only ever aggregates interpretable records.

    Args:
        row: One parsed JSONL object.

    Returns:
        AttemptRecord | None: The typed record, or None when the row is malformed.
    """
    sig = row.get("attempt_sig")
    parent_slug = row.get("parent_slug")
    parent_sha256 = row.get("parent_sha256")
    outcome = row.get("outcome")
    timestamp = row.get("timestamp")
    if not (
        isinstance(sig, str)
        and isinstance(parent_slug, str)
        and isinstance(parent_sha256, str)
        and isinstance(outcome, str)
        and outcome in _OUTCOMES
        and isinstance(timestamp, str)
    ):
        return None
    raw_cell = row.get("cell")
    cell = (
        {
            k: v
            for k, v in cast("dict[str, object]", raw_cell).items()
            if isinstance(v, str)
        }
        if isinstance(raw_cell, dict)
        else {}
    )
    raw_chain = row.get("chain")
    chain: list[dict[str, object]] = (
        [
            cast("dict[str, object]", step)
            for step in cast("list[object]", raw_chain)
            if isinstance(step, dict)
        ]
        if isinstance(raw_chain, list)
        else []
    )
    raw_distances = row.get("distances")
    distances = (
        {
            k: float(v)
            for k, v in cast("dict[str, object]", raw_distances).items()
            if isinstance(v, (int, float)) and not isinstance(v, bool)
        }
        if isinstance(raw_distances, dict)
        else {}
    )
    failing_stage = row.get("failing_stage")
    discard_reason = row.get("discard_reason")
    return AttemptRecord(
        attempt_sig=sig,
        parent_slug=parent_slug,
        parent_sha256=parent_sha256,
        cell=cell,
        chain=chain,
        outcome=outcome,
        failing_stage=failing_stage if isinstance(failing_stage, str) else None,
        discard_reason=discard_reason if isinstance(discard_reason, str) else "",
        distances=distances,
        timestamp=timestamp,
    )


def load_records(path: Path) -> list[AttemptRecord]:
    """Return every parsed :class:`AttemptRecord` from the ledger, in file order.

    Where :func:`load_outcomes` collapses the ledger to a ``sig -> outcome`` map
    (all the strategy's replay memory needs), the flywheel report's promotion
    funnel needs the full records (the failing stage, the cell, the outcome), so
    this reader keeps every field. A missing ledger is an empty list (the
    pre-first-cycle bootstrap or a fresh checkout that lost the gitignored scratch
    file); a malformed or non-interpretable line is skipped, never fatal, exactly
    as :func:`load_outcomes` does, so a partial write can never wedge the report.

    Records are returned in file (append) order, so a later record for a signature
    does NOT supersede an earlier one here (unlike :func:`load_outcomes`'s
    last-write-wins map); a caller that wants the latest disposition per signature
    reduces the list itself.

    Args:
        path: The ledger file path.

    Returns:
        list[AttemptRecord]: One record per interpretable line, in file order.
    """
    # #EDGE: external-resources: the ledger is gitignored scratch; a missing file
    # is an empty list, never an error (design 6.3 #EDGE), and a corrupt line is
    # skipped. This reader is read-only: it never writes or creates the file.
    # #VERIFY: tests round-trip appended records, assert a missing file loads
    # empty, and assert a junk line is skipped.
    if not path.is_file():
        return []
    records: list[AttemptRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = cast("object", json.loads(stripped))
        except json.JSONDecodeError:
            continue
        if not isinstance(parsed, dict):
            continue
        record = _coerce_record(cast("dict[str, object]", parsed))
        if record is not None:
            records.append(record)
    return records


def append_record(path: Path, record: AttemptRecord) -> None:
    """Append one attempt record to the ledger, creating parent dirs as needed.

    Args:
        path: The ledger file path (under ``out/`` only).
        record: The attempt record to append.

    Raises:
        ValueError: If ``record.outcome`` is not a known outcome (a corrupt
            outcome must never enter the append-only log).
    """
    # #CRITICAL: data-integrity: the ledger is append-only and its outcome
    # vocabulary is closed; rejecting an unknown outcome here keeps every
    # recorded signature interpretable by :func:`load_outcomes` forever.
    # #VERIFY: tests assert an unknown outcome raises and a valid record
    # round-trips through append then load.
    if record.outcome not in _OUTCOMES:
        msg = f"unknown ledger outcome {record.outcome!r}; expected one of {sorted(_OUTCOMES)}"
        raise ValueError(msg)
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record.to_json(), ensure_ascii=False)
    with path.open("a", encoding="utf-8") as handle:
        _ = handle.write(line + "\n")
