import json
d = json.load(open("skeletons/10-13/the-flooded-quarter.json"))
def is_cond(ch): return bool(ch.get("condition"))
# Nodes that have at least one conditional choice
print("=== NODES WITH CONDITIONAL CHOICES: full choice list ===")
for n in d["nodes"]:
    chs = n.get("choices",[])
    if any(is_cond(c) for c in chs):
        n_uncond = sum(1 for c in chs if not is_cond(c))
        flag = "  <-- NO UNCOND BASE!" if n_uncond==0 else ""
        print(f"\n{n['id']}  (uncond={n_uncond}){flag}")
        for c in chs:
            cnd = c.get("condition")
            print(f"    {'[C]' if cnd else '[ ]'} {c['id']} -> {c['target']}  {cnd if cnd else ''}")
