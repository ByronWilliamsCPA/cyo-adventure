import json, sys
d = json.load(open("skeletons/10-13/the-flooded-quarter.json"))
nodes = d["nodes"]
print("total nodes:", len(nodes))
endings = [n for n in nodes if n.get("is_ending")]
print("endings:", len(endings))
decision = [n for n in nodes if not n.get("is_ending") and len(n.get("choices",[]))>=2]
print("decision nodes (>=2 choices):", len(decision))
single = [n for n in nodes if not n.get("is_ending") and len(n.get("choices",[]))==1]
print("single-choice nodes:", len(single))
zero = [n for n in nodes if not n.get("is_ending") and len(n.get("choices",[]))==0]
print("zero-choice non-ending:", [n["id"] for n in zero])
print("variables:", [(v["name"], v.get("type"), v.get("initial"), v.get("min"), v.get("max")) for v in d["variables"]])
print("start:", d["start_node"])
# ending kinds
from collections import Counter
kinds = Counter()
for n in endings:
    e = n.get("ending") or {}
    kinds[(e.get("kind"), e.get("valence"))]+=1
print("ending kind/valence:", dict(kinds))
