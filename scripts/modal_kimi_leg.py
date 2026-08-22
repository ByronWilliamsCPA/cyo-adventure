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
``Modal-Key``/``Modal-Secret`` headers (env ``MODAL_PROXY_KEY`` /
``MODAL_PROXY_SECRET``, falling back to ``MODAL_KEY`` / ``MIDAL_SECRET``; the
fallback secret name's typo is the environment's),
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

_PRESETS = {
    "kimi": {
        "base_url": "https://williaby--ep-kimi-k3-server.us-west.modal.direct",
        "model": "moonshotai/Kimi-K3",
        "leg": "moonshot-kimi-k3-modal",
        "family": "moonshot",
    },
    "deepseek-v4-pro": {
        "base_url": (
            "https://williaby--ep-deepseek-v4-pro-server.us-west.modal.direct"
        ),
        "model": "",  # resolved from /v1/models at preflight
        "leg": "deepseek-v4-pro-modal",
        "family": "deepseek",
    },
    "openrouter-deepseek-v4-pro": {
        "base_url": "https://openrouter.ai/api",
        "model": "deepseek/deepseek-v4-pro",
        "leg": "deepseek-v4-pro",
        "family": "deepseek",
        "auth": "openrouter",
        "provider_order": ["azure/us"],
    },
    "openrouter-deepseek-v4-flash": {
        "base_url": "https://openrouter.ai/api",
        "model": "deepseek/deepseek-v4-flash",
        "leg": "deepseek-v4-flash",
        "family": "deepseek",
        "auth": "openrouter",
        "provider_order": ["novita/fp8"],
    },
}
BASE_URL = ""
MODEL = ""
LEG = ""
FAMILY = ""
AUTH = "modal"
PROVIDER_ORDER: tuple[str, ...] = ()
MAX_TOKENS = 65_536  # the registered e1r3 run condition
MAX_REPAIR_ROUNDS = 6  # ditto
CALL_TIMEOUT_S = 900.0


def _auth_headers() -> dict[str, str]:
    """Resolve credentials for the selected transport, never printing them."""
    if AUTH == "openrouter":
        token = os.environ.get("OPENROUTER_API_KEY") or ""
        if not token:
            print("Error: OPENROUTER_API_KEY missing.", file=sys.stderr)
            raise SystemExit(1)
        return {"Authorization": f"Bearer {token}"}
    key = os.environ.get("MODAL_PROXY_KEY") or os.environ.get("MODAL_KEY") or ""
    secret = (
        os.environ.get("MODAL_PROXY_SECRET") or os.environ.get("MIDAL_SECRET") or ""
    )
    if not key.startswith("wk-") or not secret.startswith("ws-"):
        print("Error: Modal proxy token pair missing or malformed.", file=sys.stderr)
        raise SystemExit(1)
    return {"Modal-Key": key, "Modal-Secret": secret}


def _retryable(exc: Exception) -> bool:
    """True for transient failures worth a backoff retry.

    Transport errors and HTTP 408/429/5xx retry; any other HTTP status (401,
    402, 404, ...) is deterministic and re-raising it immediately keeps the
    provider's response in the traceback instead of burning two more calls.
    """
    if isinstance(exc, httpx.TransportError):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status in (408, 429) or status >= 500
    return False


def _pin_payload(payload: dict) -> dict:
    """Attach the OpenRouter backend pin; no cascade, same as every leg."""
    if AUTH == "openrouter" and PROVIDER_ORDER:
        payload["provider"] = {
            "order": list(PROVIDER_ORDER),
            "allow_fallbacks": False,
        }
    return payload


def _complete(client: httpx.Client, system: str, prompt: str) -> tuple[str, dict]:
    """One chat completion via SSE streaming; returns (content, metadata).

    Streaming is load-bearing, not cosmetic: the first non-streamed
    multi-minute authoring call was dropped with "server disconnected
    without sending a response" (2026-08-21), because something on the
    path does not hold an idle connection for the full generation. The
    handoff's shape findings were all from tiny completions and did not
    surface this. Transient disconnects are retried with backoff.
    """
    payload = _pin_payload(
        {
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "stream": True,
            "stream_options": {"include_usage": True},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
        }
    )
    last_exc: Exception | None = None
    for retry in range(3):
        if retry:
            time.sleep(5 * 2**retry)
        try:
            parts: list[str] = []
            finish_reason = None
            usage: dict = {}
            with client.stream(
                "POST", f"{BASE_URL}/v1/chat/completions", json=payload
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    chunk = json.loads(data)
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        piece = delta.get("content")
                        if piece:
                            parts.append(piece)
                        if choice.get("finish_reason"):
                            finish_reason = choice["finish_reason"]
            content = "".join(parts)
            meta = {
                "finish_reason": finish_reason,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "reasoning_tokens": usage.get("reasoning_tokens"),
            }
            # Empty content under length is the Modal budget signature; the
            # caller treats it as a failed round, never as output.
            return content, meta
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            if not _retryable(exc):
                raise
            last_exc = exc
    raise RuntimeError(f"kimi call failed after retries: {last_exc}") from last_exc


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


_TOOLS_CHECKER_CAP = 10
_TOOLS_FEEDBACK_TEMPLATE = """\
Here is the full validator output for your current draft:

{feedback}

Revise your skeleton to fix every finding and return the COMPLETE corrected
JSON object (the whole skeleton, not a diff). Output JSON only.
"""


def _full_check(shell_path: Path, cell_meta: dict) -> tuple[bool, str]:
    """Run the strict checker directly, returning its full untruncated output.

    The tools condition mirrors the subagent regime, where authors saw the
    checker's raw stdout; the blind path's 120-line truncation stays blind-only.
    """
    proc = subprocess.run(
        [
            sys.executable,
            str(_SCRIPTS / "check_skeleton.py"),
            str(shell_path),
            "--strict",
            "--allow-mvp",
            "--band",
            cell_meta["band"],
            "--length",
            cell_meta["length"],
            "--style",
            cell_meta["style"],
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(_REPO_ROOT),
    )
    return proc.returncode == 0, (proc.stdout or "") + (proc.stderr or "")


def _complete_messages(client: httpx.Client, messages: list[dict]) -> tuple[str, dict]:
    """Streamed completion over an explicit message history (tools mode)."""
    payload = _pin_payload(
        {
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "stream": True,
            "stream_options": {"include_usage": True},
            "messages": messages,
        }
    )
    last_exc: Exception | None = None
    for retry in range(3):
        if retry:
            time.sleep(5 * 2**retry)
        try:
            parts: list[str] = []
            usage: dict = {}
            with client.stream(
                "POST", f"{BASE_URL}/v1/chat/completions", json=payload
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    chunk = json.loads(data)
                    if chunk.get("usage"):
                        usage = chunk["usage"]
                    for choice in chunk.get("choices") or []:
                        piece = (choice.get("delta") or {}).get("content")
                        if piece:
                            parts.append(piece)
            return "".join(parts), usage
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            if not _retryable(exc):
                raise
            last_exc = exc
    raise RuntimeError(
        f"kimi tools call failed after retries: {last_exc}"
    ) from last_exc


def run_grid_point_tools(
    client: httpx.Client,
    cell_meta: dict,
    replicate: int,
    prompts_dir: Path,
    out_dir: Path,
    attempt_dir: Path,
) -> None:
    """Tool-assisted authoring for one grid point.

    Mirrors the subagent tools condition as closely as an API permits:
    persistent conversation across iterations, the checker's full output
    fed back verbatim, at most ``_TOOLS_CHECKER_CAP`` checker invocations,
    and a single score-shell record of the final draft (checker counts go
    to tools-meta.json, maintained by the caller from this function's
    printed result line).
    """
    cell = cell_meta["id"]
    base_prompt = (prompts_dir / f"{cell}__r{replicate}.prompt.md").read_text(
        encoding="utf-8"
    )
    messages: list[dict] = [
        {"role": "system", "content": _AUTHOR_SYSTEM},
        {"role": "user", "content": base_prompt},
    ]
    draft_path = attempt_dir / f"{cell}__r{replicate}__{LEG}.tools-draft.json"
    checker_runs = 0
    passed = False
    content = ""
    llm_calls = 0
    while checker_runs < _TOOLS_CHECKER_CAP and llm_calls < _TOOLS_CHECKER_CAP + 2:
        content, usage = _complete_messages(client, messages)
        llm_calls += 1
        doc, reason = _extract_json(content)
        if doc is None:
            feedback = f"(no skeleton to check) {reason}"
        else:
            draft_path.write_text(
                json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8"
            )
            checker_runs += 1
            passed, feedback = _full_check(draft_path, cell_meta)
        print(
            f"{cell} r{replicate} tools: call {llm_calls}, checker {checker_runs}, "
            f"{'PASS' if passed else 'fail'} "
            f"(completion {usage.get('completion_tokens')}, "
            f"reasoning {usage.get('reasoning_tokens')}, "
            f"prompt {usage.get('prompt_tokens')})",
            flush=True,
        )
        if passed:
            break
        messages.append({"role": "assistant", "content": content})
        messages.append(
            {
                "role": "user",
                "content": _TOOLS_FEEDBACK_TEMPLATE.format(feedback=feedback),
            }
        )
    _score(
        draft_path.read_text(encoding="utf-8") if draft_path.exists() else content,
        cell,
        replicate,
        out_dir,
        attempt_dir,
    )
    # The score-shell record above sees only the final draft, so its attempts
    # and repair_rounds fields are NOT the tools-condition iteration counts.
    # Persist the real counts in a sidecar next to the draft, so they survive
    # without depending on stdout capture (the loop bound is llm_calls <=
    # _TOOLS_CHECKER_CAP + 2: unparseable drafts burn a completion without
    # advancing checker_runs, and the +2 caps that leak).
    sidecar = attempt_dir / f"{cell}__r{replicate}__{LEG}.tools-counts.json"
    sidecar.write_text(
        json.dumps(
            {
                "checker_runs": checker_runs,
                "llm_calls": llm_calls,
                "final_pass": passed,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    print(
        f"RESULT {cell} r{replicate} checker_runs={checker_runs} "
        f"final={'PASS' if passed else 'FAIL'}",
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--endpoint", default="kimi", choices=sorted(_PRESETS))
    parser.add_argument("--mode", default="blind", choices=["blind", "tools"])
    parser.add_argument("--cell", required=True, choices=["A", "D"])
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

    global BASE_URL, MODEL, LEG, FAMILY, AUTH, PROVIDER_ORDER  # noqa: PLW0603
    preset = _PRESETS[args.endpoint]
    BASE_URL = preset["base_url"]
    LEG = preset["leg"]
    FAMILY = preset["family"]
    AUTH = preset.get("auth", "modal")
    PROVIDER_ORDER = tuple(preset.get("provider_order", ()))
    with httpx.Client(headers=_auth_headers(), timeout=CALL_TIMEOUT_S) as client:
        models = client.get(f"{BASE_URL}/v1/models")
        models.raise_for_status()
        served = [m.get("id") for m in models.json().get("data", [])]
        MODEL = preset["model"] or (served[0] if served else "")
        if not MODEL or (preset["model"] and preset["model"] not in served):
            print(f"Error: endpoint serves {served}", file=sys.stderr)
            return 1
        print(f"preflight ok: {BASE_URL} serves {MODEL}", flush=True)
        cell_meta = {
            "A": {"id": "A", "band": "5-8", "length": "short", "style": "prose"},
            "D": {"id": "D", "band": "10-13", "length": "short", "style": "prose"},
        }[args.cell]
        for replicate in range(1, args.replicates + 1):
            if args.mode == "tools":
                run_grid_point_tools(
                    client, cell_meta, replicate, prompts_dir, out_dir, attempt_dir
                )
            else:
                run_grid_point(
                    client, args.cell, replicate, prompts_dir, out_dir, attempt_dir
                )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
