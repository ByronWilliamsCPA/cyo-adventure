import json,sys,re
sys.path.insert(0,'src')
from cyo_adventure.validator.reading_level import _flesch_kincaid_grade,_WORD_RE,_SENTENCE_RE,_count_syllables
d=json.load(open('out/the-clockwork-menagerie.filled.json'))
rows=[]
for n in d['nodes']:
    b=n['body']
    words=[m.group() for m in _WORD_RE.finditer(b)]
    wc=len(words); sc=max(len(_SENTENCE_RE.findall(b)),1)
    syl=sum(_count_syllables(w) for w in words)
    fk=_flesch_kincaid_grade(b)
    rows.append((round(fk,2),n['id'],round(wc/sc,1),round(syl/wc,3),wc,sc))
rows.sort()
over=[r for r in rows if r[0]>6.0]
under=[r for r in rows if r[0]<3.0]
print('total over 6:',len(over),' under 3:',len(under))
print('buckets: 6-6.5:',len([r for r in over if r[0]<=6.5]),' 6.5-7:',len([r for r in over if 6.5<r[0]<=7]),' >7:',len([r for r in over if r[0]>7]))
print('--- UNDER 3 ---')
for r in under: print(r)
print('--- WORST (>6.8) ---')
for r in rows:
    if r[0]>6.8: print(r)
