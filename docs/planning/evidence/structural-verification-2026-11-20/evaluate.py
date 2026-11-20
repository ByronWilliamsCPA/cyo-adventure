"""Measure every completed fill with the repo's deterministic instruments.

Run from the verify-runs worktree so both arms are scored by the same, newest
instruments::

    uv run python docs/planning/evidence/structural-verification-2026-11-20/evaluate.py \
        <run_dir> --skeleton skeletons/<band>/<slug>.json --out <metrics.json>

``run_dir`` is what ``run_fill.py`` wrote (``filled.json``, ``run.json``,
``calls/``). Instruments: ``run_fill_gate`` (blocked, findings by rule),
``scripts/check_fill_integrity.py`` (structure and fill rate),
``scripts/check_prose_craft.py --json`` (agency counts and headline),
``scripts/measure_consequence.py --json``, ``validator.dialogue`` (dialogue
share and the share of nodes with any dialogue), plus an exact comparison of
every choice's ``condition`` and ``effects`` against the skeleton, made on
BOTH the delivered book and the model's raw first reply (before
``normalize_filled_story`` restores frozen fields, so the raw comparison is the
one that says whether the model itself kept the state contract).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from cyo_adventure.generation.skeleton import story_fill_rate
from cyo_adventure.validator.dialogue import dialogue_share, has_dialogue
from cyo_adventure.validator.gate import run_fill_gate

_WORD = re.compile(r"[A-Za-z0-9'’-]+")


def _nodes(doc: dict[str, Any]) -> list[dict[str, Any]]:
    story = doc.get("story", doc)
    return list(story.get("nodes", []))


def _choice_state(doc: dict[str, Any]) -> dict[tuple[str, str], tuple[str, str]]:
    out: dict[tuple[str, str], tuple[str, str]] = {}
    for node in _nodes(doc):
        for choice in node.get("choices") or []:
            out[(node["id"], choice.get("id", choice.get("target", "")))] = (
                json.dumps(choice.get("condition"), sort_keys=True),
                json.dumps(choice.get("effects"), sort_keys=True),
            )
    return out


def _state_diff(skel: dict[str, Any], doc: dict[str, Any] | None) -> dict[str, Any]:
    if doc is None:
        return {"compared": False}
    want, got = _choice_state(skel), _choice_state(doc)
    missing = sorted(k for k in want if k not in got)
    changed = sorted(k for k in want if k in got and want[k] != got[k])
    extra = sorted(k for k in got if k not in want)
    sv = json.dumps(skel.get("variables"), sort_keys=True)
    dv = json.dumps(doc.get("variables"), sort_keys=True)
    with_state = sum(1 for v in want.values() if v != ("null", "null"))
    return {
        "compared": True,
        "choices_with_state": with_state,
        "missing_choices": [list(k) for k in missing],
        "changed_condition_or_effects": [list(k) for k in changed],
        "extra_choices": [list(k) for k in extra],
        "variables_identical": sv == dv,
        "exact": not (missing or changed or extra),
    }


def _parse_reply(text: str) -> dict[str, Any] | None:
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", stripped, re.DOTALL)
    candidates = [fence.group(1)] if fence else []
    candidates.append(stripped)
    first, last = stripped.find("{"), stripped.rfind("}")
    if first != -1 and last > first:
        candidates.append(stripped[first : last + 1])
    for cand in candidates:
        try:
            value = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return None


def _run_json(cmd: list[str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return proc.returncode, proc.stdout


def evaluate(run_dir: Path, skeleton_path: Path) -> dict[str, Any]:
    run = json.loads((run_dir / "run.json").read_text("utf-8"))
    skel = json.loads(skeleton_path.read_text("utf-8"))
    filled_path = run_dir / "filled.json"
    result: dict[str, Any] = {
        "label": run["label"],
        "arm": run["arm"],
        "skeleton": skeleton_path.name,
        "status": run.get("status"),
        "error": run.get("error"),
        "attempts": run.get("attempts"),
        "stage_log": run.get("stage_log"),
        "served_models": run.get("served_models"),
        "elapsed_s": run.get("elapsed_s"),
        "calls": len(run.get("calls", [])),
        "input_tokens": run.get("input_tokens"),
        "output_tokens": run.get("output_tokens"),
        "estimated_cost_usd": run.get("estimated_cost_usd"),
        "provider_reported_spend_usd": run.get("provider_reported_spend_usd"),
        "force_cap": run.get("force_cap"),
    }
    # Raw first reply (call-00) fidelity, before normalization. On the chunked
    # path call-00 is one batch, so it is not a whole book; skip it there.
    raw_path = run_dir / "calls" / "call-00.response.txt"
    if raw_path.exists() and not run.get("force_cap"):
        raw = _parse_reply(raw_path.read_text("utf-8"))
        result["raw_first_reply_state"] = _state_diff(skel, raw)
    if not filled_path.exists():
        result["completed"] = False
        return result
    doc = json.loads(filled_path.read_text("utf-8"))
    result["completed"] = True
    result["delivered_state"] = _state_diff(skel, doc)

    gate = run_fill_gate(doc)
    findings = [f.to_dict() for f in gate.report.findings]
    by_rule: Counter[str] = Counter()
    for f in findings:
        by_rule[f"{f.get('rule_id')}:{f.get('severity')}"] += 1
    result["gate"] = {
        "blocked": bool(gate.blocked),
        "findings_by_rule": dict(sorted(by_rule.items())),
    }

    code, out = _run_json(
        [sys.executable, "scripts/check_fill_integrity.py", str(skeleton_path),
         str(filled_path), "--min-fill-rate", "0"]
    )
    result["fill_integrity"] = {
        "exit": code,
        "fail_lines": [ln.strip() for ln in out.splitlines() if "FAIL" in ln][:12],
    }

    commissioned = 0
    for node in _nodes(skel):
        m = re.search(r"words=(\d+)", node.get("body", ""))
        if m:
            commissioned += int(m.group(1))
    bodies = [n.get("body", "") for n in _nodes(doc)]
    delivered = sum(len(_WORD.findall(b)) for b in bodies)
    result["words"] = {
        "commissioned": commissioned,
        "delivered": delivered,
        "raw_ratio": round(delivered / commissioned, 3) if commissioned else None,
        "story_fill_rate": round(story_fill_rate(skel, doc), 3),
    }
    result["dialogue"] = {
        "share": round(dialogue_share(bodies), 3),
        "nodes_with_dialogue": round(
            sum(1 for b in bodies if has_dialogue(b)) / max(len(bodies), 1), 3
        ),
    }

    code, out = _run_json(
        [sys.executable, "scripts/check_prose_craft.py", str(filled_path), "--json"]
    )
    craft = json.loads(out)["books"][0]
    agency = craft["agency"]
    result["prose_craft"] = {
        "headline": agency["headline"],
        "merge_nodes": agency["merge_nodes"],
        "merge_seams": agency["merge_seams"],
        "option_recaps": agency["option_recaps"],
        "meta_labels": agency["meta_labels"],
        "jargon_labels": agency["jargon_labels"],
        "second_person_labels": agency["second_person_labels"],
        "give_up_endings": agency["give_up_endings"],
        "early_setbacks": agency["early_setbacks"],
        "negative_endings": agency["negative_endings"],
        "decision_nodes": agency["decision_nodes"],
        "tense_unstable": len(craft["tense"]["unstable"]),
        "moral_tag_nodes": len(craft["moral_tags"]["nodes"]),
        "told_emotion_per_1000": craft["told_emotion"]["per_1000"],
        "second_person_node_rate": craft["person"]["rate"],
    }
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / "consequence.json"
        _run_json(
            [sys.executable, "scripts/measure_consequence.py", str(filled_path),
             "--json", str(target)]
        )
        if target.exists():
            result["consequence"] = json.loads(target.read_text("utf-8"))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--skeleton", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(args.run_dir, args.skeleton)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, default=str) + "\n", "utf-8")
    print(json.dumps({k: result.get(k) for k in ("label", "status", "completed")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
