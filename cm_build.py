import json, sys
sys.path.insert(0, 'src')
from cyo_adventure.validator.reading_level import _flesch_kincaid_grade
SK = 'skeletons/8-11/the-clockwork-menagerie.json'
OUT = 'out/the-clockwork-menagerie.filled.json'
from cm_bodies import B
sk = json.load(open(SK))
ids = {n['id'] for n in sk['nodes']}
missing = [i for i in ids if i not in B]
extra = [k for k in B if k not in ids]
print('MISSING:', missing)
print('EXTRA:', extra)
if missing or extra:
    sys.exit('ID mismatch')
for n in sk['nodes']:
    n['body'] = B[n['id']]
import os
os.makedirs('out', exist_ok=True)
with open(OUT,'w',encoding='utf-8') as f:
    json.dump(sk,f,indent=2,ensure_ascii=False)
counts=[]; fk_bad=[]
for n in sk['nodes']:
    b=n['body']; w=len(b.split()); counts.append((n['id'],w))
    if '—' in b: print('EMDASH in',n['id'])
    if '<<FILL' in b: print('FILL remains in',n['id'])
    fk=_flesch_kincaid_grade(b)
    if not (3.0<=fk<=6.0): fk_bad.append((n['id'],round(fk,2),w))
mean=sum(w for _,w in counts)/len(counts)
print('MEAN', round(mean,2),'min',min(w for _,w in counts),'max',max(w for _,w in counts))
print('FK out of [3,6]:',len(fk_bad))
for nid,fk,w in sorted(fk_bad,key=lambda x:x[1]): print('  ',nid,'FK',fk,'w',w)
