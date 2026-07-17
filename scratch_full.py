import json
from cyo_adventure.validator.gate import run_gate

raw = json.load(open("skeletons/10-13/the-flooded-quarter.json"))
res = run_gate(raw, scale="standard")
print("gate result type:", type(res))
for a in dir(res):
    if not a.startswith("_"): print("  ", a)
