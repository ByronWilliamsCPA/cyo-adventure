# Plant-to-payoff playthrough: The Orchard Signal

## `did_ask_whether_notebooks`

**Plant** at `n01d0`: choice "Ask whether the notebooks have seen this before." leads to `n02c0`:

> Ada turned and pulled down a volume from 1947, then 1952, then 1961, her fingers moving across the spines the way they always did when she was thinking. She opened them one by one on the bench, and Jonah watched her trace the columns of dates backwards through decades of her own handwriting, looking for another October like this one. She did not find it. The shed smelled of paraffin and old fruit and dust from the top shelf. "Nothing," she said finally, and Jonah watched her write the word *October bloom* in the margin of the current volume in small, deliberate letters, the ink still wet. "It's the first time anyone has written that down," she said. "It matters."

### Payoff site `n08d3`, choice "Say something about Faulks you cannot support."

Site body (both readers):

> Dr Abara walked the rows for two hours in the rain and said almost nothing. She stopped at the pond and stood looking at the low ground for a long time, rain streaming off her umbrella. Then she asked if anyone had ever measured the frost pocket. It was the dip in the land where cold air pooled on clear nights, and the temperature stayed lower than anywhere else on the hill. Nobody had. The notebooks held frost dates for the whole orchard. But nobody had ever put a gauge in that pocket and recorded what happened there.

Planted reader (route of 9 nodes: n00c0 > n01d0 > n02c0 > n03d0 > n04d1 > n05d3 > n06c5 > n07d1 > n08d3) sees `cq_payoff_did_ask_whether_notebooks`:

> Jonah remembered Ada turning through those decades of her own writing, looking for another October like this one and not finding it. He had watched her write the words *October bloom* in the margin. That moment of careful record-keeping was proof she had looked properly and found nothing. That was not the same as guessing. He stopped himself before he said the thing about Faulks, because it was not something he could prove. But he had the notebooks' silence on his side now. That was what he would need when he spoke to Priya Raval.

Unplanted reader (route: n00c0 > n01d0 > n02c1 > n03d1 > n04c1 > n05d3 > n06c5 > n07d1 > n08d3) gets `e09_1` instead:

> Jonah said in front of others that the survey was written to order. He believed it but he could not prove it. The gap between those two things was the gap between an attack and a real point. The words left his mouth and could not be called back. After that, every honest thing he said arrived with that attack tied to it. The chart, the notebooks, the method part: all of it was read through what he had said about Faulks. None of it landed cleanly.

### Payoff site `n10d3`, choice "Read the survey data when it arrives."

Site body (both readers):

> Four of the nine writers had living family in the city. Jonah found their old homes through the voting list and the phone book. He wrote four letters by hand at the kitchen table while Ada watched him from the doorway. The letters told what the notebooks were and why they mattered now. Each one ended by asking them to come and see the shelves. A letter to a stranger is either a kindness or a bother, based on the letter. Jonah read each one three times before he sealed the flap.

Planted reader (route of 11 nodes: n00c0 > n01d0 > n02c0 > n03d0 > n04d1 > n05d3 > n06c4 > n07d0 > n08d0 > n09d1 > n10d3) sees `cq_payoff_did_ask_whether_notebooks_site2`:

> When the survey data at last came, Jonah opened the folder with Ada's copy of the current notebook by his side. It was the one where she had jotted *October bloom* in the edge. He had watched her trace the decades and find no year like this one. That empty proof was not nothing. It was proof the survey was done in weather the notebooks had never once seen. He could say that now with the records to back him up.

Unplanted reader (route: n00c0 > n01d0 > n02c1 > n03d1 > n04c0 > n05d2 > n06c0 > n07d7 > n08d5 > n09d6 > n10d3) gets `n11d0` instead:

> The base data was thin. Jonah spread the pages across the kitchen table and read them in order. The picture that came out was smaller than he had hoped. Four visits, one survey line across the widest part of the orchard, a species list of twenty-two, and a note that the site was dry at the time. That was all. Thirty pages of method and extras and small print, and at the heart of it was four hours of watching in August.

## `did_go_down_read`

**Plant** at `n01d0`: choice "Go down and read the notice on the gate." leads to `n02c2`:

> A note had appeared on the orchard gate since morning. Someone had zip-tied it at all four corners, tight and neat, as if they planned for it to be there a while. The ties were pulled with a tool, not fingers. The plastic was already misted with condensation. Jonah read it twice. He pulled a stub of pencil from his pocket and wrote the key sentence on the back of his hand before he went back up the hill. He knew he would need the exact words later and he did not trust his memory to keep them.

### Payoff site `n06d3`, choice "Take the four lines a year approach."

Site body (both readers):

> Ada had never let a notebook leave the shed. She said so in a voice that did not invite more talk. The archive, for its part, would not accept anything it could not see in person and check against its own rules. Both of those stands made sense. And both of them made the work harder. The notebooks could not go to the archive. The archive could not come to the notebooks. The only thing both sides agreed on was that the records were too dear to risk and too weak to move. The deadlock sat in the middle of the kitchen table like a third person who had come to stay.

Planted reader (route of 7 nodes: n00c0 > n01d0 > n02c2 > n03d2 > n04c3 > n05d5 > n06d3) sees `cq_payoff_did_go_down_read`:

> Jonah opened the exercise book and read the eleven words again. They were the ones he had copied from the plastic-covered notice. They gave him the exact phrasing he was arguing against. Knowing the words exactly made the four-lines-a-year plan feel less like giving in and more like a strike back. He now had the survey's own words to measure himself against. The target was clearer for it.

Unplanted reader (route: n00c0 > n01d0 > n02c0 > n03d0 > n04d1 > n05d5 > n06d3) gets `n07d0` instead:

> First bloom, full bloom, last frost, first picking. Four dates a year, repeated across a century, came to four hundred and fifty-six numbers instead of forty thousand. Tobe set up the spreadsheet with the columns already labelled, and the blank cells waited in neat rows. The smaller number was manageable in a way the larger one had never been. It could be typed in a fortnight if they worked evenings. It could be checked by a second person. It could be explained to a planning officer in under a minute. Four lines a year was a decision about what mattered, and making it felt like the first actual step anyone had taken since the blossom appeared.

## `did_find_who_wrote`

**Plant** at `n03d0`: choice "Find out who wrote the survey." leads to `cq_plant_did_find_who_wrote`:

> The survey was signed at the bottom of the final page in a small, neat hand: *D. Faulks, August*. Jonah wrote the name in the back of Ada's current notebook and underlined it twice. The ink was still drying when he closed the cover and carried it with him out of the shed, the name already settling into his mind like a fact he would need later.

### Payoff site `n11d1`, choice "Decide what to say to Halvor."

Site body (both readers):

> The four visits fell in the driest eleven days of that August. Tobe pulled the public rain records from the Met Office website while Jonah watched. The data filled the screen in neat rows. The survey was done in two weeks when the ground was baked hard and the grass brown. Nothing was flowering. The team had said the site held no special science interest. They made that call when the land showed nothing of what was really there. Tobe sat back and said nothing. The silence was the kind that meant the work was done.

Planted reader (route of 13 nodes: n00c0 > n01d0 > n02c0 > n03d0 > cq_plant_did_find_who_wrote > n04d0 > n05d0 > n06d0 > n07d0 > n08d0 > n09d0 > n10d0 > n11d1) sees `cq_payoff_did_find_who_wrote_site2`:

> Before Jonah answered, he recalled the name he had written in the back of Ada's book. He had underlined it twice. *D. Faulks, August*. Knowing who did the survey made his answer to Halvor sharper. This was not a vague gripe about building. It was a clear strike at how one surveyor worked. And Halvor would only respect a clear point.

Unplanted reader (route: n00c0 > n01d0 > n02c0 > n03d0 > n04d1 > n05d3 > n06c4 > n07d0 > n08d0 > n09d0 > n10d0 > n11d1) gets `n12d3` instead:

> If you asked Jonah what would make him stop, the plain truth was nothing would. But saying that out loud shut a door he might want to use later. He knew it even as the thought took shape. Halvor had asked a work-like question and was waiting for a work-like answer. The answer Jonah wanted to give was not one he could afford to give. The quiet between the question and the reply grew across the café table. The coffee sat there, not touched by either of them.

### Payoff site `n11d5`, choice "Let the deadline decide for you."

Site body (both readers):

> Each of the four gripes Tobe wrote got a bit of proof and a short part of the plan. Jonah worked through them in turn at the kitchen table. He matched the writing gripe to the marked list of bad figures. He matched the method gripe to the three-page method part. He matched the cold spot gripe to the six weeks of dawn checks. Two were easy and two were not. The hard ones sat on the page like blocks he could see but not yet move. The answer to the fourth gripe rested on facts he still needed. And the choice of what to do next would shape the rest of the file.

Planted reader (route of 13 nodes: n00c0 > n01d0 > n02c0 > n03d0 > cq_plant_did_find_who_wrote > n04d0 > n05d0 > n06d0 > n07d0 > n08d0 > n09d0 > n10d1 > n11d5) sees `cq_payoff_did_find_who_wrote`:

> Jonah started to let the deadline decide, then stopped. He had found out who wrote the survey, and knowing the name D. Faulks gave him a specific target for the rainfall argument. He could show that Faulks had visited in the driest fortnight of the year, and that fact changed everything. The deadline would not decide. The data would.

Unplanted reader (route: n00c0 > n01d0 > n02c0 > n03d0 > n04d1 > n05d3 > n06c4 > n07d0 > n08d0 > n09d0 > n10d1 > n11d5) gets `e12_1` instead:

> Jonah did not pick a release date, so the deadline picked one for him. The version that went in was whatever was finished on Friday. The fourth objection still had no answer, and the frost pocket data was still marked as early. It was not the worst version and it was not the best. It was the version the deadline made. In the weeks that followed, he often thought about what might have been different. What if he had known more about who wrote the survey? What if he had tracked down the name sooner? What if he had understood earlier that the key to fighting the words was knowing who wrote them?

