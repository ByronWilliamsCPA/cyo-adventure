import json, sys
from pathlib import Path
import cyo_adventure
from cyo_adventure.generation.binding import load_contract_for, personalizable_slot_ids, render_bound_skeleton
from cyo_adventure.generation import prompts
sk_path=Path(sys.argv[1]); brief=json.load(open(sys.argv[2])); out=sys.argv[3]
sk=json.loads(sk_path.read_text())
c=load_contract_for(sk_path, sk)
if c is not None:
    b=dict(c.default_binding); sk=render_bound_skeleton(sk,b,personalizable_slot_ids(c))
    p = prompts.build_bound_fill_prompt(json.dumps(sk), json.dumps(b), json.dumps(brief), "")
else:
    p = prompts.build_fill_prompt(json.dumps(sk), json.dumps(brief), "")
system,user=p.system,p.user
open(out+".system.txt","w").write(system); open(out+".user.txt","w").write(user)
print(cyo_adventure.__file__, len(system), len(user))
