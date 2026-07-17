import json
from cyo_adventure.storybook.models import Storybook
from cyo_adventure.validator.walk import walk_configurations
from cyo_adventure.validator import layer2

raw = json.load(open("skeletons/10-13/the-flooded-quarter.json"))
sb = Storybook.model_validate(raw)
res = walk_configurations(sb, cap=200000)
print("walk type:", type(res))
for attr in dir(res):
    if not attr.startswith("_"):
        print("  attr:", attr)
