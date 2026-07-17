import json
from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.layer2 import validate_layer2
from cyo_adventure.validator.gate import run_gate

raw = json.load(open("skeletons/10-13/the-flooded-quarter.json"))
sb = Storybook.model_validate(raw)
rep = validate_layer2(sb, cap=200000)
print("L2 report:", type(rep))
print("findings:", len(rep.findings))
from collections import Counter
c = Counter(f.severity if hasattr(f,'severity') else '?' for f in rep.findings)
print("severity:", dict(c))
for f in rep.findings[:30]:
    code = getattr(f,'code',None)
    print("  ", code, getattr(f,'severity','?'), getattr(f,'message','')[:80])
