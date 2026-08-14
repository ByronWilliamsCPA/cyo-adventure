#!/bin/bash
# Obligation-variance battery: bash eval_battery.sh
# Run from /home/user/cyo-adventure.
# Guards (not success criteria) per spec section 6.
set -u
export WD=/tmp/claude-0/-home-user-cyo-adventure/8209cdae-3734-5b89-b6c4-9f834b3614c2/scratchpad/obligation-variance
FAIL=0

echo "=== 1. fill integrity (--allow-title-rewrite) ==="
for x in C D; do
  uv run python scripts/check_fill_integrity.py "$WD/arm${x}_shell.json" "$WD/filled_${x}.json" --allow-title-rewrite 2>&1 | tail -4
  rc=${PIPESTATUS[0]}
  echo "integrity $x exit: $rc"
  [ $rc -ne 0 ] && FAIL=1
done

echo "=== 2. full validator gate ==="
mkdir -p tmp_cleanup
for x in C D; do
  cp "$WD/filled_${x}.json" "tmp_cleanup/.tmp-obligation-$x.json"
  uv run python scripts/run_story_gate.py "tmp_cleanup/.tmp-obligation-$x.json" 2>&1 | tail -2
  rc=${PIPESTATUS[0]}
  echo "gate $x exit: $rc"
  [ $rc -ne 0 ] && FAIL=1
done

echo "=== 3. sibling grams + menu frames, MATCHED PROTOCOL STAGE ==="
# The 4.0 budget is calibrated on POST-revision output (the control pair went
# through a gate-revise-regate round; AL-165). Comparing a pre-revision
# treatment pair against it is a stage mismatch, not a result, so report both
# stages for both pairs and gate only on the post-revision treatment numbers.
SPP=/tmp/claude-0/-home-user-cyo-adventure/8209cdae-3734-5b89-b6c4-9f834b3614c2/scratchpad/clocktower-pilot
echo "-- control pre-revision (filled_B_a vs filled_B_b) --"
uv run python scripts/check_sibling_fills.py "$SPP/filled_B_a.json" "$SPP/filled_B_b.json" 2>&1 | grep -E "^shared|^menu"
echo "-- control post-revision (filled_H_a vs filled_H_b) --"
uv run python scripts/check_sibling_fills.py "$SPP/filled_H_a.json" "$SPP/filled_H_b.json" 2>&1 | grep -E "^shared|^menu"
if [ -f "$WD/filled_C_pre.json" ] && [ -f "$WD/filled_D_pre.json" ]; then
  echo "-- treatment pre-revision (filled_C_pre vs filled_D_pre) --"
  uv run python scripts/check_sibling_fills.py "$WD/filled_C_pre.json" "$WD/filled_D_pre.json" 2>&1 | grep -E "^shared|^menu"
fi
echo "-- treatment post-revision (filled_C vs filled_D)  [GATED] --"
uv run python scripts/check_sibling_fills.py "$WD/filled_C.json" "$WD/filled_D.json" --check 2>&1 | head -20
rc=${PIPESTATUS[0]}
echo "sibling exit: $rc"
[ $rc -ne 0 ] && FAIL=1

# check_sibling_fills --check gates on grams only; the spec's menu-frame margin
# is 0, so gate it explicitly rather than relying on eyeballing the report.
uv run python - <<'EOF'
import importlib.util, json, os, sys
spec = importlib.util.spec_from_file_location("csf", "scripts/check_sibling_fills.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
WD = os.environ["WD"]
stories = [json.load(open(f"{WD}/filled_{x}.json", encoding="utf-8")) for x in ("C", "D")]
frames = m.menu_frame_overlap(stories)
print(f"menu frames shared (margin 0): {len(frames)}")
for nid, idx, frame in frames:
    print(f"  {nid}[{idx}]: {' '.join(frame)}")
sys.exit(1 if frames else 0)
EOF
rc=$?
echo "menu frame exit: $rc"
[ $rc -ne 0 ] && FAIL=1

echo "=== 4. prose craft ==="
uv run python scripts/check_prose_craft.py "$WD/filled_C.json" "$WD/filled_D.json" --check 2>&1 | tail -20
rc=${PIPESTATUS[0]}
echo "prose craft exit: $rc"
[ $rc -ne 0 ] && FAIL=1

echo "=== 5. em-dash scan ==="
python3 - <<'EOF'
import json, os, sys
WD = os.environ["WD"]
bad = 0
for x in ("C", "D"):
    raw = open(f"{WD}/filled_{x}.json", encoding="utf-8").read()
    n = raw.count("—")  # em-dash-ok: counts the character
    print(f"{x}: {n} em-dashes")
    bad += n
sys.exit(1 if bad else 0)
EOF
rc=$?
echo "em-dash exit: $rc"
[ $rc -ne 0 ] && FAIL=1

echo "=== 6. title compliance vs the control pair's frozen titles ==="
python3 - <<'EOF'
import json, os, sys
WD = os.environ["WD"]
SP = "/tmp/claude-0/-home-user-cyo-adventure/8209cdae-3734-5b89-b6c4-9f834b3614c2/scratchpad/clocktower-pilot"
frozen = set()
for f in ("filled_H_a.json", "filled_H_b.json"):
    p = f"{SP}/{f}"
    if not os.path.exists(p):
        continue
    s = json.load(open(p, encoding="utf-8"))
    frozen.add(str(s.get("title", "")).lower().strip())
    for n in s["nodes"]:
        e = n.get("ending")
        if e:
            frozen.add(str(e.get("title", "")).lower().strip())
frozen.discard("")
bad = 0
titles = {}
for x in ("C", "D"):
    s = json.load(open(f"{WD}/filled_{x}.json", encoding="utf-8"))
    titles[x] = [("BOOK", s.get("title", ""))]
    for n in s["nodes"]:
        e = n.get("ending")
        if e:
            titles[x].append((n["id"], e.get("title", "")))
    for nid, t in titles[x]:
        low = str(t).lower().strip()
        if low in frozen:
            print(f"FAIL {x} {nid}: reuses a control-arm title {t!r}")
            bad += 1
        if nid != "BOOK" and len(str(t).split()) > 4:
            print(f"FAIL {x} {nid}: title {t!r} exceeds 4 words")
            bad += 1
for nid, _ in titles["C"]:
    vals = [dict(titles[x]).get(nid, "").lower() for x in ("C", "D")]
    if len(set(vals)) < 2:
        print(f"FAIL title collision at {nid}: {vals}")
        bad += 1
for x in ("C", "D"):
    print(x, "|", " / ".join(str(t) for _, t in titles[x]))
sys.exit(1 if bad else 0)
EOF
rc=$?
echo "titles exit: $rc"
[ $rc -ne 0 ] && FAIL=1

echo "=== 7. pairwise PS / leaf / structural ==="
uv run python - <<'EOF'
import json, os
from cyo_adventure.diversity.aggregate import pair_score
from cyo_adventure.storybook.models import Storybook
WD = os.environ["WD"]
SP = "/tmp/claude-0/-home-user-cyo-adventure/8209cdae-3734-5b89-b6c4-9f834b3614c2/scratchpad/clocktower-pilot"
def load(p):
    return Storybook.model_validate(json.load(open(p, encoding="utf-8")))
c, d = load(f"{WD}/filled_C.json"), load(f"{WD}/filled_D.json")
s = pair_score(c, d)
print(f"treatment C vs D: PS={s.perceived_similarity:.3f} leaf={s.leaf_similarity:.3f}")
try:
    a, b = load(f"{SP}/filled_H_a.json"), load(f"{SP}/filled_H_b.json")
    s2 = pair_score(a, b)
    print(f"control  A vs B: PS={s2.perceived_similarity:.3f} leaf={s2.leaf_similarity:.3f}")
except FileNotFoundError as exc:
    print(f"control pair unavailable: {exc}")
EOF

echo "=== 8. device divergence (bible_c vs armD_bible) ==="
uv run python scripts/check_bible_diversity.py \
  /tmp/claude-0/-home-user-cyo-adventure/8209cdae-3734-5b89-b6c4-9f834b3614c2/scratchpad/clocktower-pilot/bible_c.json \
  "$WD/armD_bible.json" --check 2>&1 | tail -12
rc=${PIPESTATUS[0]}
echo "bible diversity exit: $rc"
[ $rc -ne 0 ] && FAIL=1

echo "=== battery overall: $([ $FAIL -eq 0 ] && echo GREEN || echo RED) ==="
exit $FAIL
