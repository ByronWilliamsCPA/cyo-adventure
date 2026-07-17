import json, collections
d = json.load(open("skeletons/10-13/the-flooded-quarter.json"))
nodes = {n["id"]: n for n in d["nodes"]}
indeg = collections.defaultdict(list)
for nid,n in nodes.items():
    for c in n.get("choices",[]):
        indeg[c["target"]].append(nid)
multi = {k:v for k,v in indeg.items() if len(v)>=2}
print("=== MULTI-PARENT NODES ===")
for k in sorted(multi):
    print(f"{k}  <- {multi[k]}   (ending={nodes[k].get('is_ending')})")
