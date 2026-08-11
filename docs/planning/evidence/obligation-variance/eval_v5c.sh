#!/bin/bash
# v5b arm battery: bash eval_v5c.sh
# Run from /home/user/cyo-adventure.
# Guards are quality gates, not success criteria.
#
# Pair under test: filled_C (control, river lock-house, contract_v2)
#                  filled_V5c (treatment, salvage-and-triage, contract_v5,
#                              filled from a shell whose choice labels were
#                              FILL directives rather than skeleton text).
set -u
export EV=docs/planning/evidence/obligation-variance
export WD=$EV
FAIL=0

echo "=== 0. shell contamination check (the reason this arm was re-run) ==="
python3 - <<'EOF'
import json, os, sys
WD, EV = os.environ["WD"], os.environ["EV"]
shell = json.load(open(f"{WD}/armV5_shell2.json", encoding="utf-8"))
filled = json.load(open(f"{WD}/filled_V5c.json", encoding="utf-8"))
sh = {n["id"]: {c["id"]: c["label"] for c in n.get("choices") or []} for n in shell["nodes"]}
fl = {n["id"]: {c["id"]: c["label"] for c in n.get("choices") or []} for n in filled["nodes"]}
leaked = [f"{nid}.{cid}" for nid, b in sh.items() for cid, lab in b.items()
          if "<<FILL" not in lab]
still = [f"{nid}.{cid}" for nid, b in fl.items() for cid, lab in b.items()
         if "<<FILL" in lab]
print(f"shell labels carrying prose (must be 0): {len(leaked)}")
print(f"filled labels still unfilled (must be 0): {len(still)}")
sys.exit(1 if (leaked or still) else 0)
EOF
rc=$?; echo "contamination exit: $rc"; [ $rc -ne 0 ] && FAIL=1

echo "=== 0b. device collision vs the control binding ==="
uv run python scripts/check_device_collision.py \
  "$EV/armC_selection.json" "$WD/armV5b_selection.json" --check 2>&1 | head -14
rc=${PIPESTATUS[0]}; echo "device collision exit: $rc"; [ $rc -ne 0 ] && FAIL=1

echo "=== 1. fill integrity ==="
uv run python scripts/check_fill_integrity.py "$WD/armV5_shell2.json" \
  "$WD/filled_V5c.json" --allow-title-rewrite 2>&1 | tail -4
rc=${PIPESTATUS[0]}; echo "integrity exit: $rc"; [ $rc -ne 0 ] && FAIL=1

echo "=== 2. full validator gate ==="
mkdir -p tmp_cleanup
cp "$WD/filled_V5c.json" tmp_cleanup/.tmp-v5c.json
uv run python scripts/run_story_gate.py tmp_cleanup/.tmp-v5c.json 2>&1 | tail -3
rc=${PIPESTATUS[0]}; echo "gate exit: $rc"; [ $rc -ne 0 ] && FAIL=1

echo "=== 3. sibling grams + menu frames vs the control fill ==="
uv run python scripts/check_sibling_fills.py "$EV/filled_C.json" \
  "$WD/filled_V5c.json" 2>&1 | grep -E "^shared|^menu"
echo "-- for reference, the contaminated first fill --"
if [ -f "$WD/filled_V5.json" ]; then
  uv run python scripts/check_sibling_fills.py "$EV/filled_C.json" \
    "$WD/filled_V5.json" 2>&1 | grep -E "^shared|^menu"
fi
uv run python - <<'EOF'
import importlib.util, json, os, sys
spec = importlib.util.spec_from_file_location("csf", "scripts/check_sibling_fills.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
WD, EV = os.environ["WD"], os.environ["EV"]
stories = [json.load(open(p, encoding="utf-8"))
           for p in (f"{EV}/filled_C.json", f"{WD}/filled_V5c.json")]
frames = m.menu_frame_overlap(stories)
print(f"menu frames shared (margin 0): {len(frames)}")
for nid, idx, frame in frames:
    print(f"  {nid}[{idx}]: {' '.join(frame)}")
sys.exit(1 if frames else 0)
EOF
rc=$?; echo "menu frame exit: $rc"; [ $rc -ne 0 ] && FAIL=1

echo "=== 4. prose craft ==="
uv run python scripts/check_prose_craft.py "$WD/filled_V5c.json" --check 2>&1 | tail -20
rc=${PIPESTATUS[0]}; echo "prose craft exit: $rc"; [ $rc -ne 0 ] && FAIL=1

echo "=== 5. em-dash scan ==="
python3 - <<'EOF'
import os, sys
WD = os.environ["WD"]
raw = open(f"{WD}/filled_V5c.json", encoding="utf-8").read()
n = raw.count("—")
print(f"V5c: {n} em-dashes")
sys.exit(1 if n else 0)
EOF
rc=$?; echo "em-dash exit: $rc"; [ $rc -ne 0 ] && FAIL=1

echo "=== 6. title distinctness vs the control fill ==="
python3 - <<'EOF'
import json, os, sys
WD, EV = os.environ["WD"], os.environ["EV"]
def titles(p):
    s = json.load(open(p, encoding="utf-8"))
    out = [("BOOK", str(s.get("title", "")))]
    for n in s["nodes"]:
        e = n.get("ending")
        if e:
            out.append((n["id"], str(e.get("title", ""))))
    return out
c, v = titles(f"{EV}/filled_C.json"), titles(f"{WD}/filled_V5c.json")
frozen = {t.lower().strip() for _, t in c}
bad = 0
for nid, t in v:
    if t.lower().strip() in frozen:
        print(f"FAIL {nid}: reuses a control title {t!r}")
        bad += 1
    if nid != "BOOK" and len(t.split()) > 4:
        print(f"FAIL {nid}: title {t!r} exceeds 4 words")
        bad += 1
print("V5c |", " / ".join(t for _, t in v))
sys.exit(1 if bad else 0)
EOF
rc=$?; echo "titles exit: $rc"; [ $rc -ne 0 ] && FAIL=1

echo "=== 7. pairwise PS / leaf ==="
uv run python - <<'EOF'
import json, os
from cyo_adventure.diversity.aggregate import pair_score
from cyo_adventure.storybook.models import Storybook
WD, EV = os.environ["WD"], os.environ["EV"]
def load(p):
    return Storybook.model_validate(json.load(open(p, encoding="utf-8")))
s = pair_score(load(f"{EV}/filled_C.json"), load(f"{WD}/filled_V5c.json"))
print(f"C vs V5c: PS={s.perceived_similarity:.3f} leaf={s.leaf_similarity:.3f}")
EOF

echo "=== 8. branch obligations, contract_v2 vs contract_v5 ==="
uv run python scripts/check_branch_obligations.py \
  "$WD/armV5_shell2.json" "$EV/contract_v2.json" "$EV/contract_v5.json" 2>&1 | head -12

echo "=== battery overall: $([ $FAIL -eq 0 ] && echo GREEN || echo RED) ==="
exit $FAIL
