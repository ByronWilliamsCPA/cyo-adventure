# Plant-to-payoff playthrough: The Lantern Keepers' List

## `did_start_beacon_steps`

**Plant** at `n_list`: choice "Start at the Beacon Steps." leads to `bs_hub`:

> The Beacon Steps were ninety-one stone stairs cut into the ridge. An iron hook waited for a lantern on every fourth step. Three hooks had been pried clean out of the stone by frost. Their screws still sat in the rusty cups. The seventh step from the bottom was just gone. It left a dark gap that dropped knee-high onto loose stones. Nothing on wheels could come here. Every box would have to come up by hand. Wren knelt to study the broken stone. The bottom of her shoe brushed something in the heather. It was an old leather glove, dried stiff. Its cuff was marked in pencil with the letters A.T. A faded phone number was on a scrap of paper tucked inside. Someone had dropped it last season and never found it. The paper told Wren exactly who to call if the top of the ridge ran short.

### Payoff site `fn_count`, choice "Wait at the sheepfold gate with a light."

Site body (both readers):

> Seventy-one lamps lit, six out, and three never hung. The numbers came together in Wren's head as she walked the route. It was a tally of flame and darkness. The six out sat inside the same two hundred paces on the open shoulder. There, the wind came across the ridge in steady, strong gusts. The list's tally box was still empty, waiting for what she chose to write.

Planted reader (route of 12 nodes: n_open > n_list > bs_hub > bs_brackets > bs_plugs > bs_flight > gt_oil > oil_can > oil_school > oil_line > oil_relight > fn_count) sees `cq_payoff_did_start_beacon_steps_site2`:

> The old leather glove with the initials A.T. and the faded phone number. Wren had called it on a hunch, and A.T. - Arthur Tremlett, retired postman - had answered on the second ring. He had been replacing ridge brackets for forty years. He arrived at the sheepfold gate with two spare storm shades and a roll of wire, muttering that he'd wondered when someone would finally ask. The gate was lit and steady within minutes.

Unplanted reader (route: n_open > n_list > sf_hub > sf_gate > sf_reroute > sf_walk > gt_wind > oil_can > oil_school > oil_line > oil_relight > fn_count) gets `fx_gate` instead:

> The sheepfold gate was the pinch point of the whole evening. There were fourteen people, one with a strapped ankle, a wired hinge, and a field of ewes on the other side. Whoever stood there with a lamp decided how the next ten minutes went. It decided if the walkers filed through calmly or bunched up in the dark. Wren held the lamp high and steady. Its glow caught the first face that appeared out of the dusk.

### Payoff site `fn_up`, choice "Give the turn the last two lanterns."

Site body (both readers):

> Going up meant walking away from every light on the route. It meant heading into the part of the hill that had never had a lamp on it. The bare, open shoulder and the dark lip of the moor. It meant someone at the bottom knew just where you had gone and when. And it meant being the first face the walking party saw. Wren tightened the strap on her head torch. She felt the cold rising off the heather.

Planted reader (route of 12 nodes: n_open > n_list > bs_hub > bs_brackets > bs_plugs > bs_flight > gt_oil > oil_can > oil_school > oil_line > oil_taper > fn_up) sees `cq_payoff_did_start_beacon_steps`:

> Arthur Tremlett was still at the sheepfold gate when Wren came back down, his spare storm shades protecting the last two lanterns on the turn. He handed over the shades without a word and nodded at the ridge. "Go on, then. I'll watch these." The turn was safe. And because the turn was safe, the whole route held. Wren tucked the spare wire he'd given her into a pocket and went back to the shed to rewrite the list with everything the afternoon had taught her.

Unplanted reader (route: n_open > n_list > sf_hub > sf_gate > sf_reroute > sf_walk > gt_wind > oil_can > oil_school > oil_line > oil_taper > fn_up) gets `fx_short_end` instead:

> The turn was lit and the top of the steps was not, and the party came down those ninety-one stone stairs in the dark with one head torch between fourteen people. Nobody fell. Everyone noticed. The steps got talked about in the hall afterwards in the particular voice the village kept for near misses - low, careful, with long pauses. If someone had known the steps better, if someone had had the spare fixings, the top pair would have been lit. Wren could see exactly where the last two lanterns should have gone.

## `did_start_sheepfold_turn`

**Plant** at `n_list`: choice "Start at the Sheepfold Turn." leads to `sf_hub`:

> The Sheepfold Turn was where the path had been rerouted after the landslip, so the list named a stretch of hillside the walkers no longer used and said nothing at all about the one they did. Mr Ovens kept his ewes in the field the new track crossed and had wired the gate shut with three tight turns of fencing wire. A note in blue biro read SHUT MEANS SHUT. As Wren pushed a damp curl of wool caught in the wire, a hand fell on the gatepost - not Mr Ovens, but the postmistress, Dot Mallow, out walking her terrier. "He'll thaw if you ask him right," she said, nodding toward the barn. "Take him the last of the oat biscuits from the shop tin. He's partial." She pressed a small paper bag into Wren's palm and continued on her way.

### Payoff site `oil_can`, choice "Ration what there is across the route."

Site body (both readers):

> Four litres in the blue can behind the shop. A half-can in the church boiler room that might be lamp oil - nobody had written on it. And a full can that Mrs Trewin swore went to the school for the harvest lanterns and never came back. Wren stared at the small blue square of the four-litre can. She felt the weight of the missing fuel pressing on the whole afternoon.

Planted reader (route of 8 nodes: n_open > n_list > sf_hub > sf_gate > sf_reroute > sf_walk > gt_wind > oil_can) sees `cq_payoff_did_start_sheepfold_turn_site2`:

> Wren remembered the paper bag of oat biscuits Dot Mallow had pressed into her palm near the gate. Mr Ovens had taken them with a grunt that was almost a smile. In return he had told her about the old paraffin store behind the milking shed - a two-litre can he used for the barn heater. It was nearly full. That was enough to tip the ration sums from not possible to tight.

Unplanted reader (route: n_open > n_list > bs_hub > bs_brackets > bs_plugs > bs_flight > gt_oil > oil_can) gets `oil_ration` instead:

> Four litres would fill about fifty lanterns well. Or it would fill eighty badly. A badly filled lantern did not fail at seven in the evening when nobody was watching. It failed at ten past five, with the whole village looking up at the ridge. Wren opened the blue can. She caught the sharp, clean smell of the paraffin. She was trying to make the numbers come out right.

### Payoff site `oil_bench`, choice "Ask the village for anything that burns."

Site body (both readers):

> Filling eighty lanterns needed a funnel, a rag, a flat surface, and a firm rule about where the full ones went. Doing it off a tailgate in the wind was how a village ended up with paraffin down the inside of every crate. The shed doorstep was flat. The funnel was Dot Mallow's, the one that didn't leak. The rag was an old tea towel that still smelled faintly of washing powder.

Planted reader (route of 8 nodes: n_open > n_list > sf_hub > sf_gate > sf_reroute > sf_walk > gt_wind > oil_bench) sees `cq_payoff_did_start_sheepfold_turn`:

> The oat biscuits had done their work. When Wren went round asking for spare fuel, Mr Ovens was already in a useful mood. He handed over the barn-heater can without a single word about gates. "You're the only one who thought to ask nicely," he said. The extra two litres changed the whole filling table. Every lantern could now have its full share.

Unplanted reader (route: n_open > n_list > bs_hub > bs_brackets > bs_plugs > bs_flight > gt_oil > oil_bench) gets `oil_borrow` instead:

> The pub, the chapel, and three kitchens together could make a plain backup group. They gave a mix of storm lanterns, a camping lamp with a cracked glass, and a box of stubby candles in old jam jars. None of them matched the paper lanterns. All of them made light. Wren lined them up on the shed step - a small, mismatched army of backup.

## `did_knock_doors_that`

**Plant** at `gt_hands`: choice "Knock on the doors that used to say yes." leads to `cq_plant_did_knock_doors_that`:

> The first door opened on Mrs Chen, who had not been asked for two years and had kept her old lantern hook wrapped in brown paper in the hall drawer. "I wondered if you'd ever come round again," she said, and handed it over. The second door opened on Mr Riley, who still had a spare crate of storm shades in his shed from the year the ridge blew out. Wren wrote both names down.

### Payoff site `pp_runner`, choice "Let the village finish it however it likes."

Site body (both readers):

> The top of the steps could not see the orchard. Neither end could hear the other. So a runner who knew both was worth more than a mobile phone with no signal. It was also the coldest job on the hill and the one nobody chose to do. A long, open trudge back and forth while the wind did its work. Wren knew exactly who would say yes if asked directly.

Planted reader (route of 11 nodes: n_open > n_list > bs_hub > bs_brackets > bs_plugs > bs_flight > gt_hands > cq_plant_did_knock_doors_that > pp_doors > pp_teams > pp_runner) sees `cq_payoff_did_knock_doors_that`:

> Mrs Chen and Mr Riley had arrived fifteen minutes ago with their old hooks and their crate of storm shades. They were already setting up the orchard line without being told. Their quiet, practised hands changed the whole mood on the hill. What had been a scramble of volunteers became a team. The village didn't need managing. It just needed the right people to remember they had been asked. Wren took a breath and turned toward the next job.

Unplanted reader (route: n_open > n_list > bs_hub > bs_brackets > bs_plugs > bs_flight > gt_hands > pp_gate > pp_twins > pp_runner) gets `pp_village` instead:

> The ridge got lit by fourteen people. Most of them had not known each other at two in the afternoon. Because of this, half the lamps hung at slightly wrong heights. A little high on the steps, a little low in the orchard. But they burned anyway, their flames steady in the dusk. The list went back in its envelope. It had eleven new names in the column, one of them underlined, and a coffee ring on the corner of page two.

### Payoff site `pp_keep`, choice "Ask Mr Ovens for the quad bike."

Site body (both readers):

> The steps team had learned the steps in one afternoon. They knew exactly which brackets turned in their holes, which stones took the wire, and where the wind came from. Handing that knowledge away at five o'clock to someone fresh, who would have to learn it all from scratch in the dark, cost more than the fresh legs were worth. Wren looked at the small, wind-burned group who had been on the ridge since two. She knew they should stay.

Planted reader (route of 12 nodes: n_open > n_list > bs_hub > bs_brackets > bs_plugs > bs_flight > gt_hands > cq_plant_did_knock_doors_that > pp_doors > pp_teams > pp_rota > pp_keep) sees `cq_payoff_did_knock_doors_that_site2`:

> When Wren asked for the quad bike, Mr Riley and Mrs Chen both nodded. They had known Mr Ovens for twenty years. They knew exactly how to ask him - a short sentence, no fuss, while helping him stack hay bales. The quad arrived four minutes later. Its engine rattled cheerfully across the field. The last crate reached the steps before the light gave out.

Unplanted reader (route: n_open > n_list > bs_hub > bs_brackets > bs_plugs > bs_flight > gt_hands > pp_gate > pp_twins > pp_kettle > pp_keep) gets `fn_ovens` instead:

> The quad bike could get up the track to the sheepfold turn in four minutes with a person and a bag on the back. Its engine was loud and steady across the field. Asking for it a second time in one afternoon was a different sort of asking than the first. It was not the careful, biscuit-offering politeness of earlier. It was the direct sentence of someone who had already been told yes once and meant to hear it again. Wren could see the quad parked by the barn, its key still in the ignition.

