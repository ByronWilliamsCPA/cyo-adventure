"""Independent check of all 13 stated constraints. Trusts no self-report."""
import json, sys, glob
from collections import deque

KINDS={"completion","success","setback","retreat","discovery"}
VALS={"positive","neutral","negative"}

def check(path):
    f=[]
    d=json.load(open(path))
    nodes=d.get("nodes") or []
    nodes=nodes if isinstance(nodes,list) else list(nodes.values())
    ids=[n.get("id") for n in nodes]
    byid={n["id"]:n for n in nodes}
    start=d.get("start_node")
    succ={n["id"]:[c.get("target") for c in (n.get("choices") or [])] for n in nodes}

    if not (28<=len(nodes)<=34): f.append(f"C1 node count {len(nodes)}")
    if len(set(ids))!=len(ids): f.append("C12 duplicate node id")
    cids=[c.get("id") for n in nodes for c in (n.get("choices") or [])]
    if len(set(cids))!=len(cids): f.append("C12 duplicate choice id")
    if start not in byid: f.append("C7 start_missing"); return f,len(nodes)
    dang=[(n,t) for n,ts in succ.items() for t in ts if t not in byid]
    if dang: f.append(f"C2 dangling_target x{len(dang)}")
    seen={start}; q=deque([start])
    while q:
        x=q.popleft()
        for t in succ.get(x,[]):
            if t in byid and t not in seen: seen.add(t); q.append(t)
    if len(seen)!=len(byid): f.append(f"C3 unreachable x{len(byid)-len(seen)}")
    for n in nodes:
        if not n.get("is_ending") and not (n.get("choices") or []): f.append(f"C4 sink {n['id']}")
        if n.get("is_ending") and (n.get("choices") or []): f.append(f"C5 ending_with_choices {n['id']}")
        if n.get("is_ending") and not n.get("ending"): f.append(f"C5 ending missing object {n['id']}")
    ends={n["id"] for n in nodes if n.get("is_ending")}
    # backward reachability to an ending (fixed point)
    good=set(ends); ch=True
    while ch:
        ch=False
        for n,ts in succ.items():
            if n not in good and any(t in good for t in ts): good.add(n); ch=True
    trapped=[n for n in byid if n not in good]
    if trapped: f.append(f"C6 no_ending_reachable x{len(trapped)}")
    # C8 opening floor
    if len(succ.get(start,[]))<2: f.append(f"C8 opening choices {len(succ.get(start,[]))}")
    # C9/C10 path lengths (BFS shortest; DFS longest over DAG-ish, cap)
    INF=10**6
    dist={start:1}; q=deque([start])
    while q:
        x=q.popleft()
        for t in succ.get(x,[]):
            if t in byid and t not in dist: dist[t]=dist[x]+1; q.append(t)
    pos=[n["id"] for n in nodes if n.get("is_ending") and (n.get("ending") or {}).get("valence")=="positive"]
    sp=min([dist.get(p,INF) for p in pos], default=INF)
    if sp<9: f.append(f"C9 shortest positive path {sp}")
    # longest simple path, bounded search
    best=0
    def dfs(x,depth,onpath):
        nonlocal best
        best=max(best,depth)
        if depth>40: return
        for t in succ.get(x,[]):
            if t in byid and t not in onpath: dfs(t,depth+1,onpath|{t})
    dfs(start,1,{start})
    if best>16: f.append(f"C10 longest path {best}")
    # C11 ending schema
    es=[n["ending"] for n in nodes if n.get("is_ending") and n.get("ending")]
    if not (5<=len(es)<=8): f.append(f"C11 ending count {len(es)}")
    ks={e.get("kind") for e in es}; vs={e.get("valence") for e in es}
    if ks-KINDS: f.append(f"C11 bad kind {ks-KINDS}")
    if vs-VALS: f.append(f"C11 bad valence {vs-VALS}")
    if len(vs)<3: f.append(f"C11 only {len(vs)} valences")
    if len(ks)<3: f.append(f"C11 only {len(ks)} kinds")
    return f,len(nodes)

for p in sorted(glob.glob("/tmp/claude-0/-home-user-cyo-adventure/8209cdae-3734-5b89-b6c4-9f834b3614c2/scratchpad/redo/freegen/g*.json")):
    try:
        f,n=check(p)
    except Exception as e:
        print(f"{p.split('/')[-1]:8s} PARSE FAIL: {e}"); continue
    print(f"{p.split('/')[-1]:8s} nodes={n:3d}  {'PASS' if not f else 'FAIL: '+'; '.join(f)}")
