import json, sys
sys.path.insert(0, 'src')
from cyo_adventure.validator.reading_level import _flesch_kincaid_grade
from cm_bodies import B
from cm_over import O
B=dict(B); B.update(O)
sk = json.load(open('skeletons/8-11/the-clockwork-menagerie.json'))
ids = {n['id'] for n in sk['nodes']}
assert not [i for i in ids if i not in B], 'missing'
assert not [k for k in B if k not in ids], 'extra'
for n in sk['nodes']: n['body']=B[n['id']]
with open('out/the-clockwork-menagerie.filled.json','w',encoding='utf-8') as f:
    json.dump(sk,f,indent=2,ensure_ascii=False)
counts=[]; bad=[]
for n in sk['nodes']:
    b=n['body']; w=len(b.split()); counts.append(w)
    if '—' in b: print('EMDASH',n['id'])
    if '<<FILL' in b: print('FILL',n['id'])
    fk=_flesch_kincaid_grade(b)
    if not (3.0<=fk<=6.0): bad.append((round(fk,2),n['id'],w))
print('MEAN',round(sum(counts)/len(counts),2),'min',min(counts),'max',max(counts))
print('FK out of [3,6]:',len(bad))
for r in sorted(bad): print('  ',r)
