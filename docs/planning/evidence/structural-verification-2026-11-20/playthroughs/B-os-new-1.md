# Plant-to-payoff playthrough: The October Blossom

## `did_ask_whether_notebooks`

**Plant** at `n01d0`: choice "Ask whether the notebooks have seen this before." leads to `n02c0`:

> Ada turned back through decades of her own handwriting. Page after page, October after October, the dates ran backwards under her thumb. She looked at blossom dates, frost dates, and picking dates. Not one of them was like this one. The shed smelled of old apples and paraffin. The silence grew. Jonah watched her search and saw a loose sheet of paper tucked inside the back of the 1952 book. It was in a different hand. It was a note from Ada's own mother, listing every strange thing the orchard had ever done. Ada had forgotten it was there. She pressed it flat on the bench and read it twice. Then she nodded slowly.

### Payoff site `n08d3`, choice "Say something about Faulks you cannot support."

Site body (both readers):

> Dr Abara walked the rows for two hours in the rain, her coat getting dark with water, and said almost nothing. At the bottom of the hill she stopped by the pond and looked back up the slope. Then she asked if anybody had ever measured the frost pocket. The question hung in the wet air. Jonah saw that he had walked past that dip in the ground a hundred times without ever thinking to put a thermometer in it. Abara nodded slowly, as if the lack of an answer was itself an answer.

Planted reader (route of 9 nodes: n00c0 > n01d0 > n02c0 > n03d0 > n04d1 > n05d3 > n06c5 > n07d1 > n08d3) sees `cq_payoff_did_ask_whether_notebooks`:

> Jonah recalled the loose sheet from 1952. It was Ada's mother's list of strange events, and he pulled it from the notebook. The list had a bloom in November 1948 and a frost in June 1953. It proved the orchard had done odd things before. Those things had been written down, checked, and found to be real. Instead of blaming Faulks, Jonah showed Abara the list. He asked if a pattern of odd events was itself proof. Abara read it and said softly, "Yes. That is exactly what it is." The blame faded before it was spoken, and the argument grew stronger.

Unplanted reader (route: n00c0 > n01d0 > n02c1 > n03d1 > n04c1 > n05d3 > n06c5 > n07d1 > n08d3) gets `e09_1` instead:

> Jonah said, in front of others, that the survey was made to order. That Faulks knew what the builder wanted and gave it to him. He believed this deeply and fully. Yet he could not show one scrap of proof. The charge went round the room and came back changed. After that, every honest thing Jonah said arrived with that claim stuck to it. He had said the one thing he could not prove. It stained all his other words, like ink dropped in water. The notebooks were still true. But the person speaking for them was no longer trusted. And trust was the one thing the fight could not do without.

### Payoff site `n10d3`, choice "Read the survey data when it arrives."

Site body (both readers):

> Four of the nine writers had living family in the city. Ada knew the names and roughly where they lived. A letter to each of them could be a kindness or a rude shock, based on how it was written. Jonah sat with a blank page. He tried to find words that would not feel like a demand. The families might know nothing about the notebooks. Or they might have tales that were never put on paper. Asking felt like opening a door you could not shut again.

Planted reader (route of 11 nodes: n00c0 > n01d0 > n02c0 > n03d0 > n04d1 > n05d3 > n06c4 > n07d0 > n08d0 > n09d1 > n10d3) sees `cq_payoff_did_ask_whether_notebooks_site2`:

> When the survey data came, Jonah knew what to look for. The loose sheet from 1952 had shown the oddities were not chance. They bunched up in years when the winter was mild or the spring came late. He checked the survey's four visits against Ada's mother's list. He found August had been the driest month in a dry year. An orchard in drought looks nothing like an orchard in bloom. The pattern was there, and he had the proof to show it.

Unplanted reader (route: n00c0 > n01d0 > n02c1 > n03d1 > n04c0 > n05d2 > n06c0 > n07d7 > n08d5 > n09d6 > n10d3) gets `n11d0` instead:

> The raw data came in a PDF. It was twenty-two pages of tables and notes, and it felt scant. Four visits, one line across the slope, and a list of just twenty-two plants. The note at the bottom said the site was dry at the time of the survey. That was August. August in a dry year is the worst time to see what really lives in an old orchard. Jonah read the data twice. He felt the thinness of it, a weak spot where pressure could be pushed.

## `did_go_down_read`

**Plant** at `n01d0`: choice "Go down and read the notice on the gate." leads to `n02c2`:

> A covered notice had appeared on the orchard gate since morning. It was tied at all four corners by someone who meant it to stay. It was an early science survey summary, typed and official. It looked out of place against the old wood and the wet weeds. Jonah read it through twice. The second time the words felt heavier. He took out his phone and took a photo. The bare trees were behind it. He only thought he wanted a record. Later that would turn out to be the only picture anyone had of the notice in place.

### Payoff site `n06d3`, choice "Take the four lines a year approach."

Site body (both readers):

> Ada had never let a notebook leave the shed, not once in sixty years. The archive would not take anything it could not see and check in person. Both sides made sense, and both meant the notebooks stayed right where they were. On the six shelves, with the single bulb, the paraffin heater, and the draft under the door. Jonah stood in the middle of the shed, feeling two walls of the argument pushing in from both sides. Neither one would move.

Planted reader (route of 7 nodes: n00c0 > n01d0 > n02c2 > n03d2 > n04c3 > n05d5 > n06d3) sees `cq_payoff_did_go_down_read`:

> Jonah remembered the photo on his phone, the notice zip-tied to the gate with the bare trees behind it. He pulled it up on the screen. The eleven words were sharp and clear, and the date stamp proved exactly when the notice had appeared. Tobe looked at it. "That's evidence they didn't put it up until October," he said. The picture changed the argument. It was not just a record now, but proof that the survey had been posted late. This cut the objection window shorter than it should have been. Tobe added the photo to the file.

Unplanted reader (route: n00c0 > n01d0 > n02c0 > n03d0 > n04d1 > n05d5 > n06d3) gets `n07d0` instead:

> First bloom, full bloom, last frost, first picking: those were the four dates that mattered. They told the story of the orchard year by year. A century of four dates was four hundred and fifty-six numbers instead of forty thousand. Four hundred and fifty-six was a number you could hold in your head. It was a task that could be finished before the deadline. Tobe set up the spreadsheet with four columns and a hundred and fourteen rows. The empty cells looked almost manageable, like a field waiting to be planted.

## `did_find_who_wrote`

**Plant** at `n03d0`: choice "Find out who wrote the survey." leads to `cq_plant_did_find_who_wrote`:

> The survey was signed at the bottom of the last page: D. Faulks, dated in August. Jonah wrote the name down in the back of his exercise book and stared at it. A name was a starting point. It felt like a loose thread you could pull, and Jonah had a feeling that pulling it would unravel something. He closed the notebook and went to find Ada.

### Payoff site `n11d1`, choice "Decide what to say to Halvor."

Site body (both readers):

> The four survey visits fell in the driest eleven days of that August. Tobe could show this from public rain records in about nine minutes. He pulled up the Met Office data on his laptop and there it was. Four visits, all on days when the ground was dry. The plants were stressed and the orchard had shut down to save water. The survey saw the site at its least active, its least clear. The eleven words had been written based on four hours in a drought.

Planted reader (route of 13 nodes: n00c0 > n01d0 > n02c0 > n03d0 > cq_plant_did_find_who_wrote > n04d0 > n05d0 > n06d0 > n07d0 > n08d0 > n09d0 > n10d0 > n11d1) sees `cq_payoff_did_find_who_wrote_site2`:

> Jonah recalled the name on the survey: D. Faulks. He thought of the note he had made in his book weeks ago. Knowing who wrote it changed the talk with Halvor. It was not a nameless report now. It was a real person's work. Jonah could ask Halvor straight out if the builder had ordered the survey in August, knowing the site would be dry. The question hit harder when you could name the surveyor.

Unplanted reader (route: n00c0 > n01d0 > n02c0 > n03d0 > n04d1 > n05d3 > n06c4 > n07d0 > n08d0 > n09d0 > n10d0 > n11d1) gets `n12d3` instead:

> The honest answer to Halvor's question was that nothing would make Jonah stop. Saying that out loud would close a door he might want later. The developer could offer ways to soften the blow, trade-offs, and deals. If Jonah said now that only saving the whole orchard would do, there would be no room to talk later. The words sat in his mouth, true but risky. He had to choose if being honest was worth closing a door that had not opened yet.

### Payoff site `n11d5`, choice "Let the deadline decide for you."

Site body (both readers):

> Each of the four objections Tobe had written got a paragraph and a piece of evidence, laid out in order on the page. Two of them were easy to answer: the method section covered consistency, and the custody note covered the chain of evidence. The other two were harder, because they asked questions that could not be settled by pointing at a document, and the answers required Jonah to make an argument rather than simply present one. The four paragraphs sat on the screen, and two of them were solid and two of them were not.

Planted reader (route of 13 nodes: n00c0 > n01d0 > n02c0 > n03d0 > cq_plant_did_find_who_wrote > n04d0 > n05d0 > n06d0 > n07d0 > n08d0 > n09d0 > n10d1 > n11d5) sees `cq_payoff_did_find_who_wrote`:

> Jonah recalled what he had learned about Faulks: the surveyor's other work, the pattern of reports that always matched what the client wanted. He did not have to make the charge. He could let the facts sit on the page and speak for themselves. The deadline was close, but the file was stronger now. He could let it go knowing he had put in everything that could be shown. He attached the file and pressed send.

Unplanted reader (route: n00c0 > n01d0 > n02c0 > n03d0 > n04d1 > n05d3 > n06c4 > n07d0 > n08d0 > n09d0 > n10d1 > n11d5) gets `e12_1` instead:

> Jonah did not pick a release date, so the deadline picked one. What went in was the version that happened to be done that Friday. The dossier was nearly complete, but not quite. Anyone who read it closely could see the missing pieces. The committee noted the gaps and the rushed sections. They considered the objection on its merits, which were less than they could have been. The work was done, but it wasn't done as well as possible. The gap between finished and ready was the gap between the dossier and what it might have been. Jonah thought later that knowing who Faulks was might have made the difference. It might have given the dossier a shape it lacked. But that knowledge had stayed unused
