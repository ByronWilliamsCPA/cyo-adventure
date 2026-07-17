import json, collections
d = json.load(open("skeletons/10-13/the-flooded-quarter.json"))
nodes = {n["id"]: n for n in d["nodes"]}

# finale nodes
print("=== FINALE (fin_*) nodes ===")
for nid,n in nodes.items():
    if nid.startswith("fin"):
        tgts = [c["target"] for c in n.get("choices",[])]
        print(f"{nid} end={n.get('is_ending')} -> {tgts}")

print("\n=== SUCCESS/COMPLETION endings & their parents ===")
succ = [nid for nid,n in nodes.items() if n.get("is_ending") and (n.get("ending") or {}).get("kind") in ("success","completion")]
print("success/completion endings:", succ)
# find parents
parents = collections.defaultdict(list)
for nid,n in nodes.items():
    for c in n.get("choices",[]):
        parents[c["target"]].append(nid)
for e in succ:
    print(f"  {e} <- {parents[e]}  valence={(nodes[e].get('ending') or {}).get('valence')}")

# BFS shortest path start->any success/completion ending ignoring conditions
from collections import deque
start=d["start_node"]
adj=collections.defaultdict(list)
for nid,n in nodes.items():
    for c in n.get("choices",[]):
        adj[nid].append(c["target"])
def bfs(goalset):
    q=deque([(start,[start])]); seen={start}
    while q:
        u,p=q.popleft()
        if u in goalset: return p
        for v in adj[u]:
            if v not in seen:
                seen.add(v); q.append((v,p+[v]))
    return None
p=bfs(set(succ))
print("\nShortest node path to success/completion (ignoring conds), len=",len(p))
print(" ->".join(p))
# all-finale endings
finends=[nid for nid,n in nodes.items() if n.get("is_ending") and nid.startswith("fin")]
allfin=[nid for nid,n in nodes.items() if n.get("is_ending")]
print("\nfinale endings (fin_*):",finends)
print("endings NOT in finale:",[e for e in allfin if not e.startswith("fin")][:40])
