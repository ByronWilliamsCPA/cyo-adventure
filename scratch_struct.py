import json
d = json.load(open("skeletons/10-13/the-flooded-quarter.json"))
nodes = {n["id"]: n for n in d["nodes"]}

# on_enter effects
print("=== ON_ENTER EFFECTS ===")
for n in d["nodes"]:
    oe = n.get("on_enter")
    if oe:
        print(n["id"], "->", oe)

print("\n=== CHOICE CONDITIONS & EFFECTS ===")
for n in d["nodes"]:
    for ch in n.get("choices",[]):
        cond = ch.get("condition") or ch.get("visible_if") or ch.get("requires")
        eff = ch.get("effects") or ch.get("on_choose") or ch.get("set")
        if cond or eff:
            print(f"{n['id']} / {ch['id']} -> {ch['target']}")
            if cond: print("     COND:", cond)
            if eff: print("     EFF :", eff)
