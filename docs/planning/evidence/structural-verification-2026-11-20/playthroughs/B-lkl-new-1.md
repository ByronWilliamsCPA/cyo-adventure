# Plant-to-payoff playthrough: The Lantern Keepers' List

## `did_start_beacon_steps`

**Plant** at `n_list`: choice "Start at the Beacon Steps." leads to `bs_hub`:

> The Beacon Steps were ninety-one stone stairs cut into the ridge. A lantern bracket was fixed into the rock every fourth step. Ice had pulled three brackets right out of their holes. The seventh step from the bottom was gone. It left a knee-deep gap over loose stones. You could not use wheels here. Every crate had to be carried by hand. Wren stood at the bottom and looked up into the cloud. She had one afternoon to learn these stairs. The first thing she did was light a lantern. She put it on the lowest bracket, right where the wind hit hardest. She wanted to see what the ridge would do to it.

### Payoff site `fn_count`, choice "Wait at the sheepfold gate with a light."

Site body (both readers):

> Seventy-one lanterns were lit. Six were out and three were never hung. The six that were out all sat within two hundred paces on the open part of the hill where the wind came across. Wren walked the count slowly. She touched each bracket. The tally grew in her head like a song.

Planted reader (route of 12 nodes: n_open > n_list > bs_hub > bs_brackets > bs_plugs > bs_flight > gt_oil > oil_can > oil_school > oil_line > oil_relight > fn_count) sees `cq_payoff_did_start_beacon_steps_site2`:

> Wren had tested the wind on the steps earlier. She knew just where to stand so the flame would not flicker. She cupped her hand around the lantern at the gate. It burned as steady as it would in the shed.

Unplanted reader (route: n_open > n_list > sf_hub > sf_gate > sf_reroute > sf_walk > gt_wind > oil_can > oil_school > oil_line > oil_relight > fn_count) gets `fx_gate` instead:

> The gate was the pinch point of the whole evening. Fourteen people, one hurt, a wired hinge, and a field of ewes. Whoever stood there with a lamp decided how the next ten minutes went. The wire was off. The gate stood wide. Wren held the lantern high as the first walker came out of the dark.

### Payoff site `fn_up`, choice "Give the turn the last two lanterns."

Site body (both readers):

> Going up meant walking away from every light on the path. You went into the part of the hill that never had a lantern. It meant someone at the bottom had to know just where you went and when. The dark past the last lantern was total. The wind on the open moor had a voice in it.

Planted reader (route of 12 nodes: n_open > n_list > bs_hub > bs_brackets > bs_plugs > bs_flight > gt_oil > oil_can > oil_school > oil_line > oil_taper > fn_up) sees `cq_payoff_did_start_beacon_steps`:

> Wren remembered the wind test from earlier: how it came across, not up. She moved the last two lanterns into the lee of a low wall, and they caught and held immediately. The turn was lit, and the steps would be too. She turned back toward the hall, the list crisp in her pocket, and started writing the new version in her head.

Unplanted reader (route: n_open > n_list > sf_hub > sf_gate > sf_reroute > sf_walk > gt_wind > oil_can > oil_school > oil_line > oil_taper > fn_up) gets `fx_short_end` instead:

> The turn was lit. The top of the steps was not. The party came down the steps in the dark with one head torch between fourteen people. Nobody fell and everybody noticed. The steps got talked about at the hall in the voice the village kept for near misses. If someone had known how the wind really moved across those top steps, those last two lanterns might have been enough.

## `did_start_sheepfold_turn`

**Plant** at `n_list`: choice "Start at the Sheepfold Turn." leads to `sf_hub`:

> The Sheepfold Turn was where the path had been moved. The hillside gave way there in February. The list named an old stretch of ground that walkers no longer used. It said nothing about the new line. Mr Ovens kept his ewes in the field the new path crossed. He had wired the gate shut with three tight turns of fence wire. A small note in pen said SHUT MEANS SHUT. Mr Ovens was gruff and exact. He had strong views about gates. But he was also the only person on the hill who knew where the village's old fuel stores were. He told Wren about three of them before she even asked.

### Payoff site `oil_can`, choice "Ration what there is across the route."

Site body (both readers):

> Four litres behind the shop, a half can in the church boiler room that might be paraffin and might be lamp oil, and a full can that Mrs Trewin swore went to the school for the harvest lanterns and never came back. Dot Mallow pointed at the boiler room with her chin. "Smell it before you pour it," she said. "Harry once put white spirit in the lanterns and nearly singed the vicar."

Planted reader (route of 8 nodes: n_open > n_list > sf_hub > sf_gate > sf_reroute > sf_walk > gt_wind > oil_can) sees `cq_payoff_did_start_sheepfold_turn_site2`:

> Wren remembered Mr Ovens talking about the old fuel store in the church gate. Inside, behind the hymn books, was a full can. A five-litre one with a label in his writing: LANTERNS. She carried it back to the shed. The short supply problem suddenly looked much less worrying.

Unplanted reader (route: n_open > n_list > bs_hub > bs_brackets > bs_plugs > bs_flight > gt_oil > oil_can) gets `oil_ration` instead:

> Four litres would fill about fifty lanterns properly. Or it would fill eighty poorly. A badly filled lantern did not fail at seven in the evening. It failed at ten past five with the whole village watching the ridge. Wren lined up the first row of lanterns on the bench. She measured the paraffin with a steady hand and a kitchen measuring jug.

### Payoff site `oil_bench`, choice "Ask the village for anything that burns."

Site body (both readers):

> Filling eighty lanterns needed a funnel, a rag, a flat space, and a firm rule about where the full ones go. Doing it off a tailgate in the wind was how a village ended up with fuel down the inside of every crate it owned. The shed bench was cluttered with old tins and a dried-up brush. But it was out of the wind and it was flat.

Planted reader (route of 8 nodes: n_open > n_list > sf_hub > sf_gate > sf_reroute > sf_walk > gt_wind > oil_bench) sees `cq_payoff_did_start_sheepfold_turn`:

> Wren remembered the second shop Mr Ovens talked about. It was a camping lamp in the chapel vestry. She fetched it, and the vicar pushed a box of night-light candles into her hands too. The pile of borrowed things on the bench was suddenly useful.

Unplanted reader (route: n_open > n_list > bs_hub > bs_brackets > bs_plugs > bs_flight > gt_oil > oil_bench) gets `oil_borrow` instead:

> There were storm lanterns from the pub. The chapel and three kitchens gave a camping lamp and a box of stubby candles in jam jars. None of them matched the route. But all of them made light. Wren stacked the borrowed things on the shed bench. Brass, glass, tin and wax. Every one of them could burn through an October evening.

## `did_knock_doors_that`

**Plant** at `gt_hands`: choice "Knock on the doors that used to say yes." leads to `cq_plant_did_knock_doors_that`:

> The first door was the one with the blue paint and the brass letterbox. Wren knocked, and old Mrs Kitto opened it before the echo had died. She had hung lanterns on this ridge for thirty years before her knees gave out, and she was holding a tin of boiled sweets and a list of her own. "I've been waiting," she said, and she was already putting on her coat.

### Payoff site `pp_runner`, choice "Let the village finish it however it likes."

Site body (both readers):

> You could not see the orchard from the top of the steps. One end could not hear the other. A runner who knew both ends was worth more than a phone with no signal. It was also the coldest job on the hill, and nobody ever picked it. The wind was getting up. The run between the two ends now felt much longer than it had at two.

Planted reader (route of 11 nodes: n_open > n_list > bs_hub > bs_brackets > bs_plugs > bs_flight > gt_hands > cq_plant_did_knock_doors_that > pp_doors > pp_teams > pp_runner) sees `cq_payoff_did_knock_doors_that`:

> Old Mrs Kitto, who had been a lantern keeper longer than anyone, was already there, directing three volunteers with the calm authority of someone who had done this thirty times. She caught Wren's eye and nodded. "Go on," she said. "I've got this end. Get them all down safe." Wren turned and ran for the steps.

Unplanted reader (route: n_open > n_list > bs_hub > bs_brackets > bs_plugs > bs_flight > gt_hands > pp_gate > pp_twins > pp_runner) gets `pp_village` instead:

> The ridge got lit by fourteen people who mostly did not know each other at two o'clock. Because of that, half the lanterns hung at slightly wrong heights. The list went back in the envelope with eleven new names in the column. One of them was underlined. The village had turned up in its messy, unpractised way. The hill was brighter than it had been in years.

### Payoff site `pp_keep`, choice "Ask Mr Ovens for the quad bike."

Site body (both readers):

> The steps team learned the route in one afternoon. They knew exactly which brackets turned in their holes. Giving all that away at five o'clock to new people cost more than fresh legs were worth. The team looked at Wren, waiting. Their hands still held the motions they had practised.

Planted reader (route of 12 nodes: n_open > n_list > bs_hub > bs_brackets > bs_plugs > bs_flight > gt_hands > cq_plant_did_knock_doors_that > pp_doors > pp_teams > pp_rota > pp_keep) sees `cq_payoff_did_knock_doors_that_site2`:

> Old Mrs Kitto had known Mr Ovens for forty years. She picked up the phone in the hall and spoke five words into it. Two minutes later, the quad's engine started in his yard.

Unplanted reader (route: n_open > n_list > bs_hub > bs_brackets > bs_plugs > bs_flight > gt_hands > pp_gate > pp_twins > pp_kettle > pp_keep) gets `fn_ovens` instead:

> The quad could climb the track to the sheepfold turn in four minutes. It had a person and a bag on the back. Asking for it twice in one afternoon was a different kind of ask than the first. The quad was parked by the barn. Its engine was still warm from the last run. Mr Ovens was wiping his hands on a rag.

