import json,sys
sys.path.insert(0,'src')
from cyo_adventure.validator.reading_level import _flesch_kincaid_grade
d=json.load(open('out/the-clockwork-menagerie.filled.json'))
ids=[n['id'] for n in d['nodes'] if not (3.0<=_flesch_kincaid_grade(n['body'])<=6.0)]
print(len(ids))
print(ids)
