"""Blind-contract driver for the `moonshot-kimi-k3-modal` S-1 leg.

Runs the identical shared repair-loop contract the other legs get (same system
prompt, same emitted author prompts, same validator feedback via the harness's
`--score-shell` mode, same round cap), against the owner's dedicated Modal
Kimi-K3 endpoint. Experimental transport per ADR-010: this file lives in the
evidence directory precisely because it must never join the production
provider cascade.

Endpoint facts (verified 2026-08-21, see
`handoff-modal-deepseek-v4-smoke-test-2026-08-20.md`, Modal leg results):
OpenAI chat-completions shape at ``<base>/v1/chat/completions``, auth via
``Modal-Key``/``Modal-Secret`` headers (env ``MODAL_KEY`` / ``MIDAL_SECRET``,
the second name's typo is the environment's, checked before ``MODAL_PROXY_*``),
``usage.reasoning_tokens`` at the top level, NO cost field, and a reasoning
model that returns ``content: ""`` with ``finish_reason: "length"`` when the
budget is too small; that empty content is treated as a failed round exactly
like unparseable output, never as prose.

Usage:
    uv run python scripts/modal_kimi_leg.py \
        --cell A --replicates 3 \
        --prompts <dir from --emit-prompts> \
        --out-dir docs/planning/evidence/skeleton-author-vendors/runs/e1r3-2026-08-21
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = Path(__file__).resolve().parent
for _p in (str(_REPO_ROOT), str(_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from compare_skeleton_authors import (  # noqa: E402
    _AUTHOR_SYSTEM,
    _REPAIR_PROMPT,
    _extract_json,
)

BASE_URL = os.environ.get(
    "MODAL_KIMI_BASE_URL",
    "https://williaby--ep-kimi-k3-server.us-west.modal.direct",
)
MODEL = "moonshotai/Kimi-K3"
LEG = "moonshot-kimi-k3-modal"
FAMILY = "moonshot"
MAX_TOKENS = 65_536  # the registered e1r3 run condition
MAX_REPAIR_ROUNDS = 6  # ditto
CALL_TIMEOUT_S = 900.0


def _auth_headers() -> dict[str, str]:
    """Resolve the wk-/ws- proxy pair without ever printing it."""
    key = os.environ.get("MODAL_PROXY_KEY") or os.environ.get("MODAL_KEY") or ""
    secret = (
        os.environ.get("MODAL_PROXY_SECRET") or os.environ.get("MIDAL_SECRET") or ""
    )
    if not key.startswith("wk-") or not secret.startswith("ws-"):
        print("Error: Modal proxy token pair missing or malformed.", file=sys.stderr)
        raise SystemExit(1)
    return {"Modal-Key": key, "Modal-Secret": secret}


def _complete(client: httpx.Client, system: str, prompt: str) -> tuple[str, dict]:
    """One chat completion; returns (content, usage-ish metadata)."""
    response = client.post(
        f"{BASE_URL}/v1/chat/completions",
        json={
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        },
    )
    response.raise_for_status()
    body = response.json()
    choice = body["choices"][0]
    content = choice["message"].get("content") or ""
    usage = body.get("usage") or {}
    meta = {
        "finish_reason": choice.get("finish_reason"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "reasoning_tokens": usage.get("reasoning_tokens"),
    }
    if not content.strip() and choice.get("finish_reason") == "length":
        # Empty-string content under length is the Modal budget signature;
        # returning it as-is would hand an empty shell downstream as if it
        # were output. The caller treats it as a failed round.
        content = ""
    return content, meta


def _score(
    shell_text: str, cell: str, replicate: int, out_dir: Path, attempt_dir: Path
) -> tuple[bool, str]:
    """Persist the attempt and accumulate the grid record via --score-shell."""
    attempt = attempt_dir / f"{cell}__r{replicate}__{LEG}.attempt.json"
    attempt.write_text(shell_text, encoding="utf-8")
    proc = subprocess.run(
        [
            sys.executable,
            str(_SCRIPTS / "compare_skeleton_authors.py"),
            "--score-shell",
            str(attempt),
            "--score-cell",
            cell,
            "--score-replicate",
            str(replicate),
            "--score-leg",
            LEG,
            "--score-family",
            FAMILY,
            "--out-dir",
            str(out_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_REPO_ROOT),
    )
    output = (proc.stdout or "") + (proc.stderr or "")
    passed = proc.returncode == 0
    feedback_lines = [
        line for line in output.splitlines() if not line.startswith("score: ")
    ]
    return passed, "\n".join(feedback_lines)


def run_grid_point(
    client: httpx.Client,
    cell: str,
    replicate: int,
    prompts_dir: Path,
    out_dir: Path,
    attempt_dir: Path,
) -> None:
    """Author one shell under the blind contract, to pass or the round cap."""
    base_prompt = (prompts_dir / f"{cell}__r{replicate}.prompt.md").read_text(
        encoding="utf-8"
    )
    prompt = base_prompt
    for attempt in range(1 + MAX_REPAIR_ROUNDS):
        started = time.monotonic()
        content, meta = _complete(client, _AUTHOR_SYSTEM, prompt)
        elapsed = round(time.monotonic() - started, 1)
        passed, feedback = _score(content, cell, replicate, out_dir, attempt_dir)
        print(
            f"{cell} r{replicate} attempt {attempt + 1}: "
            f"{'PASS' if passed else 'fail'} in {elapsed}s "
            f"(completion {meta['completion_tokens']}, "
            f"reasoning {meta['reasoning_tokens']}, "
            f"finish {meta['finish_reason']})",
            flush=True,
        )
        if passed:
            return
        doc, _reason = _extract_json(content)
        previous = json.dumps(doc) if doc is not None else content
        prompt = (
            base_prompt
            + "\n\n"
            + _REPAIR_PROMPT.format(previous=previous[:60_000], feedback=feedback)
        )
    print(f"{cell} r{replicate}: censored at round cap", flush=True)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--cell", required=True)
    parser.add_argument("--replicates", type=int, default=3)
    parser.add_argument("--prompts", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--attempt-dir", default="")
    args = parser.parse_args(argv)

    prompts_dir = Path(args.prompts)
    out_dir = Path(args.out_dir)
    attempt_dir = (
        Path(args.attempt_dir) if args.attempt_dir else out_dir / "kimi-attempts"
    )
    attempt_dir.mkdir(parents=True, exist_ok=True)

    with httpx.Client(headers=_auth_headers(), timeout=CALL_TIMEOUT_S) as client:
        models = client.get(f"{BASE_URL}/v1/models")
        models.raise_for_status()
        print(f"preflight ok: {BASE_URL} serves {MODEL}", flush=True)
        for replicate in range(1, args.replicates + 1):
            run_grid_point(
                client, args.cell, replicate, prompts_dir, out_dir, attempt_dir
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
