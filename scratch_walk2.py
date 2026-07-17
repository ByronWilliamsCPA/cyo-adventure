import json
from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.walk import walk_configurations
from cyo_adventure.validator import layer2

raw = json.load(open("skeletons/10-13/the-flooded-quarter.json"))
sb = Storybook.model_validate(raw)
res = walk_configurations(sb, cap=200000)
print("reachable configs:", len(res.configs))
print("edges:", len(res.edges))
print("capped:", res.capped)

# Run layer2 findings
findings = layer2.run(sb, cap=200000)
print("L2 findings count:", len(findings))
for f in findings[:20]:
    print("  ", f)
