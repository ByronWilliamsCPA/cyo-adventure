import json
from collections import Counter
from cyo_adventure.validator.gate import run_gate

raw = json.load(open("skeletons/10-13/the-flooded-quarter.json"))
res = run_gate(raw, scale="standard")
print("blocked:", res.blocked, "safety_flagged:", res.safety_flagged)
rep = res.report
print("total findings:", len(rep.findings))
c = Counter(getattr(f,'severity','?') for f in rep.findings)
print("by severity:", dict(c))
codes = Counter(getattr(f,'code','?') for f in rep.findings)
print("by code:", dict(codes))
# Non-advisory (blocking) findings
for f in rep.findings:
    sev = str(getattr(f,'severity',''))
    if 'advis' not in sev.lower() and 'info' not in sev.lower():
        print("NONADV:", getattr(f,'code','?'), sev, getattr(f,'message','')[:90])
