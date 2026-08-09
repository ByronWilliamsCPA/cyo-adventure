"""Book D prose: mutant D (M4 insert-decision reconvergence) in the terminus world.

Second draft. The first draft (kept as ``bodies_d_draft1.py``) was written as a
sentence-by-sentence world swap of Book S and measured 302 shared 4-grams per
1000 words against it, far above the 9 to 25 per 1000 the earlier pilots
recorded between independently authored sibling fills. That is an artefact of
the authoring method, not of the mutation under test, so this draft re-authors
every node in a different voice: shorter sentences, a different sensory palette,
information ordered action-first rather than setting-first, and no reuse of Book
S's sentence frames.
"""

from __future__ import annotations

TITLE = "The Midnight Terminus"

BODIES: dict[str, str] = {
    "n_open": (
        "Somebody counted heads wrong. That was all it took. By the time Tess "
        "came down from the gallery, still holding a leaflet about coal, the "
        "shutters were rolling shut across the booking hall and Kingsmoor "
        "Terminus had gone over to its night lighting, a dim blue that made "
        "everything look underwater. Nine per cent battery. No signal. What she "
        "did have was a torn timetable, salvaged from under a bench that "
        "afternoon, printed for a station that no longer quite existed, with one "
        "line inked down the margin in a stranger's hand: what Iris Halloway hid "
        "here has never left the building."
    ),
    "n_start": (
        "Three arches. Three enamel signs. Tess stood on the compass rose set "
        "into the concourse floor, listened to the iron roof tick as it cooled, "
        "and decided to stop standing still."
    ),
    "a_gems1": (
        "Umbrellas by the hundred. A cello case. A birdcage with a note tied to "
        "it. The Lost Property Hall kept everything Kingsmoor had ever mislaid, "
        "racked to the ceiling, and two emergency lamps lit about a tenth of it. "
        "Tess noticed the tall glass claim case straight away, because it did not "
        "line up. Its feet had worn a pale rectangle into the floor over eighty "
        "years, and it was standing a hand's width out of it. Then, somewhere "
        "behind the racks, a buzzer started. Soft. Regular. Not urgent, exactly. "
        "Just not stopping."
    ),
    "a_gems_case": (
        "Somebody had been at the claim case, and somebody had been quick about "
        "it. Bright scratches raked the little brass catch where a tool had "
        "jumped. The paper labels inside sat out of their rows. Tess crouched. "
        "Below the case the tipped drawer hung half off its runners, a thumbprint "
        "dragged clean through the dust on its handle, and behind everything the "
        "fallen claim ticket lay face down where it had slid. Nothing in this "
        "room had moved in years. Two things had moved this week. Iris Halloway's "
        "secret had company, and the company was careless."
    ),
    "a_gems_vitrine": (
        "Tess wrestled the tipped drawer out and turned it over across her knees. "
        "There, gouged into the raw underside of the wood: a chevron with a dot "
        "at its point, cut hard enough to leave splinters. She got the torn "
        "timetable out one-handed. Same chevron, printed small in the corner, "
        "with a hairline rule running away from it to a doorway that no modern "
        "sign in this station admitted to. Porters' passage. Somebody had left "
        "her arrows, and had carved them where a cleaner would never look."
    ),
    "a_gems_note": (
        "The fallen ticket was no ticket at all. Tess turned it over and found a "
        "parcels stub from another century, and across its back, in brown ink she "
        "recognised before she could say why, one word boxed twice over: PORTERS. "
        "She checked it against the timetable. There it sat, printed beside a thin "
        "doorway at the back of the hall, chevron alongside. She put the stub in "
        "her pocket. Then she went to find the door."
    ),
    "a_gems_corridor": (
        "White tiles to shoulder height, then flaking cream. The porters' passage "
        "had lamps whose glass had gone furry with age and whose bulbs had died "
        "before she was born. Tess walked it on the sides of her feet. The door at "
        "the far end was small and shut and its plate held no keyhole, only a "
        "cut-out chevron with a dot at its point, which was a lock she had no idea "
        "how to pick. She looked down. Along the skirting, a brass floor plate had "
        "risen at one corner, and the hollow under it took a whole hand."
    ),
    "a_gems_alarm": (
        "It was a grey box above the racks, an amber light going on, off, on, "
        "counting down to whatever grey boxes count down to. Tess had got two "
        "steps toward it when a torch beam came out of a doorway at the far end "
        "and started walking the shelves. Behind the beam came the night porter, "
        "in no hurry whatever, whistling the same two notes over and over. The "
        "light swung nearer. There was a pillar to her left. There was, apart from "
        "the pillar, nothing."
    ),
    "a_gems_hide": (
        "Behind the pillar Tess stopped being a girl and became an outline. The "
        "beam swept the rack above her, hung on the birdcage for a second and a "
        "half, and went on. The whistling thinned out. A door banged, far off, in "
        "some other part of the building. When she finally looked round the pillar "
        "the porters' passage was standing open, wedged with the porter's own "
        "rubber block."
    ),
    "b_egypt1": (
        "Cold came off the Locomotive Shed like cold off a river. Iron and old "
        "oil, and underneath that something faintly like soot. The great green "
        "engine took up the whole middle of the floor, higher than a house, and "
        "its smokebox door hung open a finger's width on wooden wedges where "
        "somebody's Tuesday volunteer had knocked off early. Behind it the faded "
        "route map covered a wall: Kingsmoor as it had been a century ago, "
        "platforms drawn confidently in places that were blank brick now."
    ),
    "b_egypt_sarco": (
        "The smokebox door weighed what a door of iron weighs, and it hung a "
        "degree or two out of true, which meant somebody had swung it and eased it "
        "back and not wanted to be heard doing either. A corner of clean rag "
        "showed inside. Clean rag, in a shed where everything was ninety years "
        "filthy. Three paces off, the nameplate case held eleven brass plates laid "
        "on green baize, and one rectangle of nothing where a twelfth belonged, "
        "its shape still printed in the cloth. Borrowed, said the card. The card "
        "did not say returned."
    ),
    "b_egypt_lid": (
        "Two hands, shoulder braced, and the smokebox door came round its last few "
        "degrees. Inside the fold of rag lay something flat and brass that had "
        "certainly not travelled from 1898: a disc, stamped with a chevron and a "
        "dot, twin to the mark on her timetable. Tess was still turning it over "
        "when the draught found her, cold across the ankles, steady, pulling in "
        "from the linking passage."
    ),
    "b_egypt_amulet": (
        "Taken for the record, I.H. The label under the empty rectangle was "
        "written in the brown ink Tess had been chasing since teatime. She pressed "
        "her cheek almost to the glass to make out the initials, and because she "
        "was at that angle she saw the second thing: a scratch in the frame so "
        "fine it disappeared if you looked at it straight on. An arrow. Fingernail "
        "length. Aimed steadily at the linking passage."
    ),
    "b_egypt_hall": (
        "Brick, cable clipped along it in loops, a smell of damp. The linking "
        "passage had never been meant for the public and did not pretend "
        "otherwise. At the end of it Tess found the door, small, shut, its plate "
        "cut in the shape of a chevron with a dot. Somebody had abandoned a bucket "
        "of sand and a canvas roll of spanners against the frame. She stepped "
        "round them, and one sleeper board took her weight with a hollow knock "
        "that she felt in her knees."
    ),
    "b_egypt_map": (
        "Tess traced the route map with a fingertip and found a platform that no "
        "modern plan would own up to: a long finger of concrete off the east side, "
        "drawn as firmly as everything else, chevron inked beside its gate. Below "
        "the map a signal lamp hung on a bracket, part of a display about night "
        "working. Beyond both, past a velvet rope and a very polite little sign, "
        "The Roped-Off Platform went away into the dark."
    ),
    "b_egypt_torch": (
        "The signal lamp was brass, heavier than it looked, and its bulb had life "
        "in it yet. Tess held it low and walked the line the route map drew, along "
        "a wall she had gone past twice without noticing anything at all, and it "
        "put her out in a linking passage she had never been down. At the end of "
        "it: a small locked door, chevron cut into its plate, exactly where a "
        "hundred-year-old map said one ought to be."
    ),
    "c_archive1": (
        "Down a flight, under the concourse, the Ticket Archive smelled of cold "
        "paper and pencil sharpenings. Green reading lamps stood dark in a row "
        "along an oak table nobody had sat at since March. The parcels ledger lay "
        "open on its stand by the door, furred over like a windowsill. Past the "
        "lamps the deep stacks began: shelf, shelf, shelf, and then the light gave "
        "up and the dark simply had the rest."
    ),
    "c_archive_ledger": (
        "Consignments. Dates. Signatures in a dozen hands, getting rounder and "
        "then squarer with the decades. And then, on a Tuesday in March, halfway "
        "down a page, the parcels ledger simply stopped, as if the station had "
        "shut a door on its own memory. Tess ran her finger past the last entry "
        "and found blank ruled paper. Behind the stand stood the card index in its "
        "oak drawers. Under that, the bottom drawer sat jammed three inches open "
        "on something folded. Whatever Iris Halloway had filed before Kingsmoor "
        "forgot her was in one of them."
    ),
    "c_archive_index": (
        "Two fingers, walking. The cards behaved themselves through E and F and G, "
        "and then stopped behaving: one card stood proud among the H's, out of "
        "sequence, stamped in the corner with a chevron and a dot. No title on it. "
        "A bay number, and a line of brown ink underneath. Low steel locker, deep "
        "stacks, cold wall."
    ),
    "c_archive_drawer": (
        "The bottom drawer came unstuck all at once and banged, and Tess stood "
        "very still for a count of ten. Nothing happened. Inside lay a plan, "
        "folded into eighths, one shelf ringed round twice in brown ink. She "
        "spread the torn timetable next to it on the floor. The two edges fitted, "
        "chevron to chevron, like the halves of a ticket that had been waiting a "
        "hundred years to be matched up."
    ),
    "c_archive_stack": (
        "The deeper she went the closer the shelves leaned, until the air stopped "
        "moving altogether. Cold wall, the card had said. There it was, and under "
        "a run of bound gazetteers that had not been opened since her "
        "grandmother's time sat the low steel locker, its plate cut in a chevron. "
        "Tess pulled the handle. Nothing. No key in the room, no key in the "
        "building as far as she knew. But the gazetteers hid a gap behind them, "
        "shallow, and about a hand wide."
    ),
    "c_archive_dark": (
        "Seven paces, and the light behind her stopped being any use whatsoever. "
        "The deep stacks went up past her reach and away in both directions, and "
        "the dark down here had a texture to it, papery, close, faintly warm. "
        "Somewhere along the left-hand shelf, Tess thought, a porter's hand lamp "
        "hung on a bracket. Probably. Or she could go on by touch and count the "
        "shelf ends as she passed."
    ),
    "c_archive_lantern": (
        "Bracket. Strap. Then the cool square weight of a porter's hand lamp, and "
        "a clack, and a hard white oblong laid down the aisle. Tess breathed out. "
        "Four bays along, painted small on a shelf end, was a chevron with a dot, "
        "and low underneath it, half swallowed by gazetteers, the grey corner of a "
        "steel locker."
    ),
}

BODIES.update(
    {
        "n_key": (
            "Oilcloth, gone hard as bark, and inside it an iron switch key as long "
            "as her forearm. Tess sat back on her heels and weighed it in both "
            "hands. Somebody had punched a chevron and a dot into the bow of it, "
            "hard, the way you mark a thing you never want to lose. Wired to the "
            "shank was a punched card: buff board, a scatter of holes, paired "
            "letters running along one edge, and no meaning whatsoever yet. Three "
            "chevrons showed on her timetable. The drawing office on the "
            "mezzanine. The trophy cabinet in the refreshment room. And the signal "
            "box stairs, behind the parcels office, where nobody had gone for "
            "years."
        ),
        "k_founder": (
            "The lock gave up without much argument. Inside, the drawing office "
            "had been holding its breath since long before Tess was born: chalk "
            "dust, cold ink, a smell like a cupboard in a school that had closed. "
            "A roll-top desk sat shut under the window with a grey pelt over it. "
            "And above the empty grate hung Iris Halloway in oils, arms folded, "
            "keeping an eye on a room that fifty years of staff had walked past "
            "and never cleared."
        ),
        "k_founder_desk": (
            "The roll-top went up with a noise like shingle. Pigeonholes, dozens "
            "of them, each one stuffed: dockets, pay slips, a pressed leaf, a "
            "shopping list. Tess dug behind the lot and came out with a "
            "canvas-bound notebook worn soft at the spine. She opened it and "
            "forgot to breathe for a second. Paired letters. The same paired "
            "letters as the card wired to her key, set out in neat columns. Half a "
            "cipher, sitting in the dark for a century, waiting for the other "
            "half."
        ),
        "k_founder_portrait": (
            "Iris Halloway swung away from the wall on a hinge, which Tess had "
            "not expected and nearly dropped her for. Behind the portrait a "
            "shallow safe hung open on one twisted bracket. Grit. A dead wasp. And "
            "the timetable slide rule: two strips of boxwood with a brass slider, "
            "the wood worn pale in one place where a thumb had run it perhaps ten "
            "thousand times. Whatever the punched card was for, this was the thing "
            "it was for."
        ),
        "k_display": (
            "Half the refreshment room wall was cabinet. Behind clouded glass, "
            "Iris Halloway's survey journals lay propped on wire stands, open at "
            "pages of writing so small it looked like weather. The iron switch key "
            "turned the end latch first go, with a clack that carried further than "
            "Tess wanted. Then nothing. The lid had been shut since decimalisation "
            "and the frame had swollen tight along its whole length."
        ),
        "k_display_open": (
            "A knuckle at a time, the way you free a painted-shut window: lift, "
            "let it settle, lift. Tess worked the whole length twice before the "
            "swollen wood let go, and it let go quietly. Inside, a slim ledger lay "
            "across the journals with a tape marker in it. The marked page carried "
            "no words at all. Only paired letters, line after line, in brown ink."
        ),
        "k_cabinet": (
            "Both hands and both elbows to lift the ledger clear. Tess got it out, "
            "set it on a table top, and checked the coded page against the punched "
            "card. Letter for letter, the same pairings. Which meant one of them "
            "was a lock and the other was its key, and she was not going to work "
            "out which crouched over a cabinet in the dark. Out on the mezzanine "
            "there was a drafting table under a hooded lamp. Flat. Big. Lit."
        ),
        "k_display_force": (
            "Fingers under the lip, weight on it. The lid rose about the thickness "
            "of a coin and the glass along the front made a noise, a small dry "
            "tick, and Tess felt it behind her eyes. Coax it, said the noise. One "
            "decent pull, said her shoulders, which had been at this for five "
            "minutes and had opinions."
        ),
        "k_display_careful": (
            "She stopped. She put her palms flat under the lip instead of hooking "
            "her fingertips in, and she lifted straight up, slowly, the way you "
            "carry something full to the brim. The lid came free without a sound. "
            "The slim ledger slid out with its coded page uppermost, and the glass "
            "along the front was still as whole as the day it was fitted, which "
            "mattered to Tess more than she would have predicted."
        ),
        "k_stairs": (
            "Rust, and then the lock. The signal box stairs opened on the second "
            "attempt. Above her the flight climbed into a dark that the emergency "
            "lighting had never once been asked to reach, and the handrail carried "
            "enough dust to sign her name in. Tess tested the bottom step. Silent. "
            "At the foot of the flight the lamp cupboard stood with its door ajar, "
            "and something pale showed in the gap."
        ),
        "k_stairs_up": (
            "At the top, a landing no school trip would ever see. Iris Halloway's "
            "drafting table stood there under its hooded lamp with a high stool "
            "pushed back at an angle, as though whoever sat on it had got up to "
            "answer a bell and simply not come back. Laid out beside the lamp, "
            "side by side, tidy as a place setting: a buff card of paired letters, "
            "and a boxwood slide rule."
        ),
        "k_stairs_base": (
            "In the lamp cupboard: a rolled gradient chart tied with tape, and "
            "spectacles with one arm missing. Tess unrolled the chart across her "
            "knees, expecting a hill. It was not a hill. It was columns of paired "
            "letters, hundreds of them, and squinting at it here by torchlight was "
            "hopeless. This wanted a flat surface and a decent lamp."
        ),
        "k_study": (
            "However she had got there, Tess ended up at the drafting table with "
            "her finds set out in front of her: the punched card, and the "
            "timetable slide rule with its slider stiff from a century of standing "
            "still. She hooked the stool in with her ankle and put the hooded lamp "
            "on. That small warm circle changed everything. For the first time all "
            "night Kingsmoor stopped being somewhere she was shut inside and "
            "became somewhere people had worked. She lined the outer letters up "
            "against the inner ones and read off the first line."
        ),
        "m1_dec_n_key": (
            "The drawing office door swung inward, and Tess did not go through it. "
            "The landing outside turned out to be a little room of its own. There "
            "was the drafting table under its hooded lamp. There was the high "
            "stool. And there on the blotter, set out as neatly as a lesson, lay a "
            "boxwood slide rule with its slider halfway along. Everything the "
            "punched card needed was on this side of the doorway. Everything Iris "
            "Halloway had actually been was on the other side, in the dark, "
            "unopened for fifty years. Tess stood between the two with the key "
            "still warm in her fist."
        ),
        "n_cipher": (
            "Letter by letter it came off the slide rule, and it was not a name "
            "and it was not an amount in pounds. FOLLOW THE STARS TO THE HEART. "
            "Tess sat back so hard the stool rocked. Stars. Three rooms in this "
            "station had stars in them, and her timetable put all three round the "
            "concourse like figures on a dial: the Star Ceiling Hall with its "
            "painted zodiac, the Survey Room where every chart was a sky of its "
            "own, and the Clock Tower Walk, where the dials had been set by the "
            "stars for a hundred years."
        ),
        "ci_stars": (
            "Even with the lights down, the Star Ceiling Hall glowed. Gold leaf, "
            "flaking in places, laid out in constellations across the whole "
            "ceiling, and a smell of size and old varnish that got into the back "
            "of Tess's throat. A wide stair curved up toward the gallery with a "
            "rope across the bottom and a notice about conservation work. Against "
            "the side wall, a maintenance ladder went the same distance in a "
            "quarter of the steps."
        ),
        "ci_stars_dome": (
            "Tess turned slowly under the ceiling with the cipher running on a "
            "loop in her head, and on the third turn she had it: one constellation "
            "gilded brighter than any of its neighbours, three stars linked inside "
            "a square of black. Directly beneath it, set flush into the panelling, "
            "sat a small door with a chevron on it, and behind the door a stair "
            "going down toward the concourse."
        ),
        "ci_stars_ladder": (
            "The ladder went up faster than Tess entirely liked and put her out on "
            "the narrow catwalk above the cornice. From up here the tiles were a "
            "very long way down and the painted ceiling was near enough to breathe "
            "on. Thirty paces along, a grey service door. Straight above her head, "
            "a second ladder carried on into the roof space, where the dark had no "
            "edges at all."
        ),
        "ci_stars_cross": (
            "One hand on the rail. Eyes on the grey door. Tess did not look down "
            "once, not even when the catwalk rang under her shoes and the sound "
            "fell all the way to the floor and came back up at her a moment later. "
            "Thirty paces, counted. The service door opened on a back stair that "
            "dropped flight by flight past two locked landings and let her out at "
            "the edge of the concourse."
        ),
        "ci_map": (
            "Charts to the ceiling. Coastlines, cuttings, rivers that had been "
            "argued into new courses by men with theodolites. In the middle of the "
            "Survey Room the great brass globe stood on its rails, taller than "
            "Tess by a head, its oceans gone the colour of stewed tea. Next to it "
            "the route atlas lay open on a slanted stand with one page folded "
            "back, as though a reader had stepped out for a moment in 1911 and was "
            "expected back."
        ),
        "ci_map_globe": (
            "Tess read the cipher's figures off twice to be sure, then leaned into "
            "the globe and turned it until the named latitude came up under the "
            "meridian arch. Something inside the thing closed. One click, like a "
            "lock agreeing with her. Low on the wall behind the stand a panel let "
            "itself out on its own weight, and past it a short passage ran toward "
            "concourse light."
        ),
        "ci_map_atlas": (
            "The atlas would not stay where it had been left. Tess turned two "
            "pages and it fell open under its own weight at a sheet that had never "
            "been printed at all: a plan of Kingsmoor, drawn by hand and pasted "
            "in, in Iris Halloway's brown ink. Straight across it, red and faded "
            "and perfectly clear, ran a route from this room to the middle of the "
            "station."
        ),
        "ci_atlas2": (
            "The red route made no sense at all. Back stair. Store room full of "
            "folding chairs. A doubling-back round a lift shaft for no reason Tess "
            "could see. She followed it exactly anyway, counting corners under her "
            "breath, twice certain she had lost it, and it delivered her through a "
            "plain grey door onto the concourse, precisely where a hundred-year-old "
            "line said it would."
        ),
        "ci_clock": (
            "The Clock Tower Walk ticked, and not one of the ticks agreed with "
            "another. Station clocks stood and hung down both walls, faces pale as "
            "moons, each with its own firm opinion about the length of a second. "
            "At the far end one doorway glowed where the clock room's dials were "
            "lit from inside. Beside it, a lower arch ran under the tower's master "
            "pendulum."
        ),
        "ci_clock_gears": (
            "In the clock room the master movement stood open like a wardrobe. "
            "Brass wheels, oiled arbors, a governor spinning away at nothing in "
            "particular. Its hands had stopped at no time at all. Tess read the "
            "hour off the cipher, took the long hand between finger and thumb, and "
            "walked it round until it sat true. Behind the frame something let go "
            "with a knock, and a maintenance door drifted open toward the "
            "concourse."
        ),
        "ci_clock_pendulum": (
            "Out, hang, back, hang. The master pendulum crossed the only doorway "
            "on a beat Tess could have counted in her sleep, and it was longer "
            "than she was tall, and nothing in the world had ever made it hurry. "
            "She could learn the beat and step through in the gap. Or she could go "
            "now, while it was away at the far end of its swing, and be quick "
            "about it."
        ),
        "ci_clock_cross": (
            "Four beats, counted. The fifth, waited out. Then Tess walked through "
            "at a completely ordinary speed, which turned out to be the hard part, "
            "because everything in her wanted to run. The pendulum went by behind "
            "her with a sound like a long breath. Beyond the arch the passage "
            "sloped down, the ticking thinned out clock by clock, and the concourse "
            "opened ahead of her."
        ),
    }
)

BODIES.update(
    {
        "n_rotunda": (
            "Whichever way you went in Kingsmoor, you ended up on the concourse. "
            "Tess came out under the iron and glass with one line still going round "
            "in her head, and there it stood in the middle of the tiled floor: the "
            "departure orrery, a cage of brass rings taller than a grown man, "
            "collecting what light there was and giving none of it back. To the "
            "heart. Iris Halloway had put her archive down there, under everyone's "
            "shoes, for a century. Three ways at it. Set the rings. Work over the "
            "plinth for a seam. Or chance the porters' office and read what the "
            "station kept saying about itself."
        ),
        "ro_align": (
            "Close up, the rings ran quiet, the way brass runs when somebody has "
            "loved it. Figures were etched small round every edge and the cipher "
            "named an exact setting for all four of them. The problem was the feel "
            "of them: stiff for the first inch, then suddenly not stiff at all, so "
            "that a figure you were creeping up on went sailing past and you had to "
            "come the whole way round again."
        ),
        "ro_align_set": (
            "Tess refused to rush. Ring one to its figure, check. Ring two, check. "
            "Ring three, check twice because her hands were shaking a little now. "
            "When the fourth seated itself the whole orrery let go a sigh, and gears "
            "found each other somewhere down inside the plinth, and a panel of tiled "
            "floor drew back the way a held breath goes out. Steps. Going down."
        ),
        "ro_align_guess": (
            "She spun them by feel, on the theory that her hands knew better than "
            "her notes, and the four rings clunked home into an arrangement that was "
            "nearly right, which in a machine means wrong. The orrery groaned at "
            "her. Underneath the tiles something ground once, thought about it, and "
            "quit. Start again from zero and do it out of the cipher properly. Or "
            "put a shoulder in and insist."
        ),
        "ro_align_retry": (
            "Zero, zero, zero, zero. Tess took every ring back and then flattened "
            "the decoded line out on the tiles and read it twice over before she let "
            "her hands anywhere near the brass again. Ring, check. Ring, check. This "
            "time the orrery sighed like something agreeing, and the floor let "
            "itself open on the steps going down."
        ),
        "ro_panel": (
            "The plinth was not one block of stone, which Tess only found out by "
            "leaning on it. Its face was cut into small squares, and the squares "
            "moved under her thumb, sliding about into a gap the way the puzzle out "
            "of a cracker does. She got down on her knees to see it properly, and "
            "that was when she felt the other thing: a thin cold draught out of the "
            "seam at the back, steady as somebody breathing."
        ),
        "ro_panel_solve": (
            "The squares wanted to make a picture and the picture wanted to be a "
            "chevron with a dot at its point. Tess slid them one at a time. She had "
            "to unpick a whole corner twice and start it again, and her thumbnail "
            "split, and then the last square dropped home. A catch under the plinth "
            "went clack, and the tiled panel by her knee swung down on the steps "
            "going below."
        ),
        "ro_panel_secret": (
            "The draught was coming out of a door at the back of the strongroom, no "
            "higher than Tess's shoulder, painted the same tired cream as the wall "
            "so that you could look straight at it and not see it. It gave when she "
            "put a hand on it. Cold, still air on the other side, and a room stacked "
            "with half-built signal gear under a hundred years of dust."
        ),
        "ro_workshop": (
            "Iris Halloway's own workshop. Nobody had been in here since she stopped "
            "coming. Benches ran round three walls under a felt of dust, and on the "
            "nearest one a signal lamp sat with its case off and every one of its "
            "parts laid out beside it in order, waiting for a hand that never came "
            "back. Labelled drawers. A board of tools each hanging inside its own "
            "painted outline. A stool pushed back. This was not the archive the "
            "cipher had promised Tess. It was better, because not one living person "
            "knew it was here."
        ),
        "ro_records": (
            "Nine grey screens, nine empty platforms, and a hum you could feel in "
            "your teeth. Tess stood inside the door of the porters' office without "
            "moving until she was certain the chair was empty. The rounds log lay "
            "open on the desk at tonight's date, half filled in, a biro dropped "
            "across it. Beside the log squatted a telephone from another era, black, "
            "heavy, its cord going into the wall."
        ),
        "ro_records_guard": (
            "Tess turned the log back. Years. Then decades. The handwriting kept "
            "changing and changing until, near the front, it turned into brown ink "
            "she had been reading all night. Iris Halloway's own entry, the oldest "
            "in the book: the floor beneath the orrery opens at the cipher's hour, "
            "and the stair below is sound. Tess was out of the door before she had "
            "finished the sentence. On the concourse the tiles were already sliding "
            "quietly apart."
        ),
        "ro_records_phone": (
            "The dial went all the way round with a clatter and the handset weighed "
            "like a brick, and when Tess lifted it there was a tone, patient, "
            "waiting. She could ring home right now. A warm car in ten minutes. Two "
            "extremely relieved faces. And a mystery left at exactly half solved, "
            "sitting safe in her notebook until whenever."
        ),
        "n_vault": (
            "Eleven steps down, and then cedar and cold brick. Tess swung her light "
            "along the shelving and it snagged on things, one after another, and she "
            "kept having to bring it back. Framed drawings racked upright. Trays of "
            "medals. A stuffed heron with its wings half up, entirely unbothered "
            "about any of it. Everything Kingsmoor had ever been given, and Iris "
            "Halloway had meant every piece of it for the town and had not lived "
            "long enough to hand it over. On a table in the middle: a letter with a "
            "chevron pressed into the wax. A survey map. And, waiting underneath "
            "both of them, the question of what one person on her own is supposed to "
            "do with a room like this."
        ),
        "v_letter": (
            "The wax broke clean. Iris Halloway had not written to anybody in "
            "particular, which somehow made it worse and better at once. A bad year, "
            "she wrote. A board that wanted the lot sold off by the crate. A "
            "decision, taken alone, to hide it until Kingsmoor deserved it back. "
            "Whoever finds this, give it to the town, and do it in daylight. Then, "
            "at the bottom, no sentence at all: a count, a direction, and a shelf "
            "sketched in pencil."
        ),
        "v_letter_reveal": (
            "Count along, the letter said, and push. Tess counted along and pushed, "
            "and a shelf that was not a shelf came out on hinges. Behind it, "
            "standing upright in a slot cut to take it and nothing else, was the "
            "catalogue: every object in the strongroom set down in brown ink, with "
            "where it had come from and where it actually belonged. A hundred years "
            "of mystery, alphabetised."
        ),
        "v_reveal2": (
            "Kneeling, then sitting, then flat on her front with the lamp propped on "
            "her bag. It was not a list. That was the thing Tess had not expected. A "
            "driver's long service watch. A signalwoman's box of photographs. A "
            "shunter's whistle, carved. Next to each one a name, a family, a street "
            "she could walk to. It was a whole town, handed back to itself in "
            "columns. When she looked up the glass roof had gone from black to grey, "
            "and she knew where the archive was, and why it had been hidden, and "
            "exactly how to give it back."
        ),
        "v_letter_keep": (
            "Tess folded the letter along its old creases, buttoned it into her "
            "inside pocket, and put her hands behind her back. Nothing else moved. "
            "The strongroom had waited a hundred years and could manage another "
            "eight hours until people were awake. A stranger had left an instruction "
            "for whoever turned up. Doing it properly, in daylight, with adults who "
            "had keys, felt like the first half of doing it at all."
        ),
        "v_map": (
            "Linen, inked, and marked with a red cross that made no apology for "
            "being a red cross. What the survey map showed was the bricked-up "
            "platform: a whole finger of Kingsmoor walled off, rendered smooth, and "
            "left off every plan since. More of the archive was through there. Tess "
            "could go now, while she was inside and awake. She could photograph the "
            "map and let somebody with a permit open the wall. Or she could sit down "
            "and trace every faded line until she was sure of it."
        ),
        "v_map_follow": (
            "Back up, and along a passage she had walked twice already, until the "
            "render sounded wrong under her knuckles. A cable hatch at knee height, "
            "and then Tess was through it and standing on the bricked-up platform "
            "with her lamp up, and there they were: carriages, four of them, cleaned "
            "and lined and lettered for an opening day that never happened. She "
            "marked the hatch and photographed every window."
        ),
        "v_map_photo": (
            "Flat on the table, and eleven photographs, twice over, close enough to "
            "read the smallest pencilled note in the margin. Then Tess folded the "
            "survey map back along its own creases, set it exactly where it had "
            "been, and left the strongroom looking as though nobody had ever been "
            "down there. The proof was in her pocket. The decision belonged to "
            "somebody with keys and a budget."
        ),
        "v_share": (
            "Tess sat on the bottom step with the lamp across her knees and thought "
            "about whose this actually was. Tell the heritage manager, and he would "
            "know what to do and do it right, and it would stop being hers inside an "
            "hour. Tell Femi and Row, and it would stay wonderful and small and "
            "secret. Or tell nobody, leave a trail, and let Kingsmoor Terminus find "
            "its own lost heart without ever knowing she had been down here at all."
        ),
        "v_share_curator": (
            "Letter, catalogue, staff door, and then a long cold wait until the "
            "first car turned in at ten to seven. The heritage manager came through "
            "with a tea in one hand and stopped so completely that he forgot he was "
            "holding it. Tess laid the whole night out along the bonnet of his car "
            "in order, item by item, and watched a grown man's face do something she "
            "had never seen a grown man's face do."
        ),
        "v_share_secret": (
            "Hers, Femi's and Row's. Nobody else's, at least until the three of them "
            "had worked out how to give it away properly, which Tess suspected might "
            "take a while. A strongroom under the concourse. A heron. An oath sworn "
            "on the top deck of the 41. It was, she thought, the single best secret "
            "anybody in her year had ever had to sit on."
        ),
        "v_share_museum": (
            "She propped the map open on the porters' desk, squared the letter "
            "beside it, and wrote a note in her best handwriting: THE FLOOR UNDER "
            "THE ORRERY OPENS. START HERE. She read it back. She put a stapler on "
            "the corner so it could not blow about. Then Tess let herself out into a "
            "grey morning and left Kingsmoor to finish what its engineer had "
            "started."
        ),
        "v_grab": (
            "It was on the nearest shelf, on its own square of baize: a silver "
            "signal lamp no bigger than her two fists, lens the deep green of a "
            "bottle. Tess knew it instantly. It was the thing from the missing "
            "photograph in the guidebook, the one with the caption and no picture. "
            "In her bag it would prove every single word she said tomorrow, to "
            "anybody, in about four seconds. Her hand went out over it and stopped "
            "there, and did not come down, and did not go back."
        ),
        "v_grab_run": (
            "She took it. Bag, zip, go. Tess was three steps up when the baize she "
            "had cleared rose about a millimetre on a spring underneath, and "
            "somewhere over her head a bell began, small and silvery and entirely "
            "unhurried, and it did not stop, and it came with her all the way out "
            "into the hall."
        ),
        "v_grab_return": (
            "Tess put it back. She squared the little lamp up on its baize with two "
            "fingers and stepped away from the shelf before her hands could start "
            "arguing with her. A trophy would have made a better story and a "
            "distinctly worse morning, and she knew which of the two she would "
            "actually have to live in. Out she went, with a notebook, some "
            "photographs, and nothing at all to hide."
        ),
    }
)

BODIES.update(
    {
        "e_set_alarm": (
            "The beam found her and stayed on her. Tess put her hands out to the "
            "sides, which she had not decided to do, and stood there with her pulse "
            "banging. The night porter lowered the torch. He looked at her for a "
            "while. Then he sighed the sigh of a man who has turned up a great deal "
            "worse than one stranded schoolgirl in thirty years of nights, and "
            "walked her to the booking hall to sit on the good bench until a lift "
            "came. There was a tin of biscuits. Iris Halloway's secret stayed "
            "exactly where it had always been."
        ),
        "e_set_locked_gallery": (
            "The gate closed behind Tess with a soft, expensive click and turned out "
            "to have nothing on the inside to pull. She tried twice. She laughed "
            "once, briefly, without much in it. Then she got practical: a bench, a "
            "heating pipe still faintly warm, and a rolled banner about Victorian "
            "Kingsmoor that made an acceptable blanket. Safe, dry, and completely "
            "stuck until seven. Through the wall, the engineer's secret carried on "
            "keeping itself."
        ),
        "e_set_stuck_dark": (
            "Six bays in, Tess turned to check the way back and discovered that the "
            "dark had rearranged the room while she was not looking. Left and right "
            "had stopped meaning anything useful. So she did the sensible thing: sat "
            "down with a shelf at her back and her bag on her knees, and waited for "
            "the lights at opening. Dusty. Long. Not actually frightening after the "
            "first ten minutes. The steel locker stayed shut, and nobody ever knew "
            "how near she had got."
        ),
        "e_set_broken_case": (
            "The crack went through the glass with a noise like the building saying "
            "no. Tess got her hands away fast. Nothing was harmed except the cabinet "
            "itself, but there was a split running corner to corner now that had not "
            "been there a second earlier, and feet were already coming at a run "
            "across the tiles. She spent the rest of that night in the booking hall "
            "explaining herself, first to the porter and then to a very tired woman "
            "on the telephone. The punched card stayed in her pocket, unread."
        ),
        "e_set_stuck_dome": (
            "Past the catwalk the ladder went on up into the roof space, and Tess "
            "went with it, rung by rung, until her head touched boards. The hatch "
            "had been closed off from the far side, years ago, properly. There was "
            "nothing up here. She came down slowly, both hands, eyes on her own "
            "feet, and sat on the bottom rung until her legs stopped buzzing. Tired, "
            "dizzy, entirely unhurt, and finished with this route. The concourse "
            "could wait for another night."
        ),
        "e_set_pendulum": (
            "Tess went on three. The pendulum was working to two. It met her "
            "shoulder without any malice whatsoever, the way a bus door does, and "
            "posted her back onto the safe side of the arch, where she sat down hard "
            "on the tiles feeling far more surprised than sore. A hundred clocks "
            "ticked their hundred opinions over her head. Fine, she told them. "
            "Tonight you win."
        ),
        "e_set_jammed_globe": (
            "She put a shoulder in. Something inside the plinth said clack, once, in "
            "a tone that did not invite discussion, and after that the brass would "
            "not move in either direction at all. The floor stayed shut. Tess sat "
            "down against the stone beside the silent orrery, close enough to the "
            "stair to have drawn it from memory, and watched the glass roof go "
            "slowly grey above her."
        ),
        "e_set_caught": (
            "A tiled concourse offers nowhere at all to be invisible, and the bell "
            "brought the porter at a trot. Tess went red to the ears. She opened her "
            "bag and put the silver lamp into his hands before he had to ask, which "
            "she was glad of afterwards. He was stern. He was also fair, and he made "
            "her say out loud what she had done, which was worse than the sternness. "
            "Then he found a chair and rang her father. She came back in daylight "
            "and showed the heritage manager the stair, and everything ended up "
            "where it belonged, Tess included."
        ),
        "e_set_dawn": (
            "There was always one more faded line, one more crease worth flattening "
            "out. When Tess finally lifted her head from the survey map the glass "
            "above her had gone the colour of washing-up water, and there were keys "
            "and voices somewhere overhead. She folded it. She put it back on its "
            "table. Then she slipped out of the staff door into a morning full of "
            "buses with the bricked-up platform half traced, promising herself, "
            "properly, that she would come back and finish it."
        ),
        "e_win_secret_workshop": (
            "Photographs: the half-built lamp, the labelled drawers, the tools each "
            "in its painted outline, the stool pushed back for a hundred years. Tess "
            "took thirty of them and touched not one single thing. The workshop "
            "stayed as Iris Halloway had left it. In the morning she held her phone "
            "out to the heritage manager and watched him sit down slowly on the edge "
            "of a desk. A whole lost room, he kept saying. A whole lost room, and "
            "none of us knew."
        ),
        "e_win_mystery_solved": (
            "Tess came up the stairs into daylight, actual daylight, with a letter "
            "buttoned in her pocket and a catalogue under one arm and a hundred "
            "years of somebody else's careful thinking in her head. She gave all of "
            "it back that morning, in order, to the people it had been meant for in "
            "the first place. The archive came out of the dark. Iris Halloway's name "
            "came out with it. And Kingsmoor Terminus was not quite the same "
            "building afterwards."
        ),
        "e_win_quiet_keeper": (
            "A folded letter and a promise, and nothing else at all. Over the "
            "following weeks Tess asked the heritage manager small, extremely "
            "innocent questions about engineers and floors and old drawings, and "
            "left photocopies where somebody was bound to trip over them, and let "
            "the station work itself out one step at a time. Nobody ever quite "
            "established who had started it off. Keeping a trust gently turned out "
            "to be a thing she was good at."
        ),
        "e_win_lost_wing": (
            "The bricked-up platform was hers to give away and she gave it away "
            "properly. Photographs to the heritage manager at nine. A conservator by "
            "lunchtime. The local paper on Thursday. When the builders came they "
            "opened the render with a care that made Tess want to cheer out loud, "
            "and half the town queued down the steps to look at four carriages that "
            "had been standing six inches behind a wall their entire lives."
        ),
        "e_win_hero_curator": (
            "The heritage manager listened at the staff door with his tea going "
            "cold, said only, may I see, and then moved remarkably quickly for a man "
            "in a duffel coat. By ten there was a team on the stair with lamps and "
            "gloves and a clipboard, and Tess was at the top of it answering "
            "questions she had not expected. Eight weeks later somebody made a "
            "speech and thanked her as the girl who gave Iris Halloway's gift back "
            "to everybody, which was, word for word, what the letter had asked for."
        ),
        "e_win_secret_kept": (
            "It stayed theirs. Three of them, one strongroom, one heron, and an oath "
            "sworn upstairs on the 41. They went back four times that term, always "
            "in daylight, always putting every last thing back where they found it, "
            "and they argued cheerfully all year about when to tell. Some wonders "
            "work better shared between two people than two hundred. For a while, "
            "anyway."
        ),
        "e_win_donate": (
            "Map open, letter squared, note in capitals, stapler on the corner. Then "
            "Tess went home and slept until two in the afternoon. Nine days later "
            "Kingsmoor Terminus announced the rediscovery of its engineer's lost "
            "archive beneath the concourse floor, and there were banners, and a "
            "ribbon, and a brass band that was not very good. Nobody ever found out "
            "whose careful handwriting had set them off. Tess read about it in the "
            "paper and grinned into her cereal."
        ),
        "e_neutral_call_home": (
            "She dialled. Her father went from asleep to alarmed to on my way in "
            "roughly four seconds, and then Tess sat in the warm booking hall with "
            "her notebook open on her knees, working through what she had. The key. "
            "The code. The direction. Not the ending. Headlights swung across the "
            "shutters at twenty past three, and she went out to meet them already "
            "working out how to get back in and finish the job."
        ),
        "e_neutral_evidence": (
            "Eleven photographs on a phone at nine per cent, and a strongroom left "
            "exactly as she found it, down to the fold in the letter. Tess got out "
            "at first light past a cleaner who took her for somebody's daughter and "
            "said good morning. She had enough to bring the right people back with "
            "the right equipment, and she found she was perfectly happy to let the "
            "adults argue about what happened next."
        ),
        "e_neutral_wiser": (
            "Empty bag. Full notebook. Tess climbed out having solved nothing in "
            "particular and brought home nothing at all to wave about at school. "
            "What she did have was a very clear idea of what she was and was not "
            "prepared to do at three in the morning with nobody watching, which is "
            "not the sort of thing you can borrow off anybody else. She walked home "
            "through streets that were just starting up, wiser than she had gone in."
        ),
    }
)

# De-convergence pass: the eighteen nodes carrying the most shared 4-grams with
# Book S, re-authored again from the beat rather than from Book S's sentences.
BODIES.update(
    {
        "ci_stars_cross": (
            "Rail in the left hand. Grey door straight ahead. Tess made a rule for "
            "herself before she started, which was that her eyes were not allowed "
            "below the rail, and she kept to it for all thirty paces, even when the "
            "metal grating sang under her shoes and the note dropped away beneath "
            "her and came back a moment later off the tiles. The door was not "
            "locked. Behind it a back stair went down past two shut landings and "
            "put her out at the edge of the concourse."
        ),
        "e_win_secret_workshop": (
            "Thirty photographs and not one fingerprint. Tess got the half-built "
            "lamp from three angles, the drawers with their inked labels, the tool "
            "board with an outline painted round every spanner, and the stool where "
            "somebody had pushed it back in about 1962. Then she left it precisely "
            "alone. She showed the heritage manager her phone at half past eight. "
            "He looked at four pictures, put a hand on a desk, and lowered himself "
            "onto it. Nobody knew, he said, twice. Nobody had any idea."
        ),
        "v_share": (
            "Tess parked herself on the bottom step with the lamp on her knees and "
            "did some arithmetic about ownership. Option one: the heritage manager. "
            "Competent, kind, and it would be out of her hands by nine. Option two: "
            "Femi and Row, and a wonder small enough to hold. Option three: say "
            "nothing to anybody, but leave enough of a trail that Kingsmoor "
            "stumbled on its own missing heart, and never learned that a girl in a "
            "school coat had got there first."
        ),
        "v_grab_return": (
            "Down it went, back on the baize, squared up with a fingertip at each "
            "corner. Tess made herself step backwards twice before her hands got a "
            "chance to reopen the argument. There was a version of tomorrow where "
            "she produced a silver lamp out of a rucksack, and there was a version "
            "where she did not, and only one of them was a morning she fancied "
            "living in. She went up the steps carrying a notebook and some "
            "photographs and nothing anybody could take off her."
        ),
        "e_set_dawn": (
            "One more line. One more crease worth flattening. Tess was still "
            "kneeling over the linen when she registered that the glass overhead "
            "was no longer black, and that the noise she had been ignoring for a "
            "while was a shutter going up. She refolded the survey map. She put it "
            "on the table with the letter square beside it. Then she walked out of "
            "the staff door into engine noise and traffic and other people's "
            "Tuesday, with half a route traced and an appointment to keep with "
            "herself."
        ),
        "n_cipher": (
            "It came off the slide rule a letter at a time, and it was an "
            "instruction, not a treasure: FOLLOW THE STARS TO THE HEART. Tess put "
            "the rule down. Stars, in a railway station. But there were three "
            "places in Kingsmoor where stars turned up, and the torn timetable set "
            "all three in a ring round the middle of the building. Gold ones on the "
            "ceiling of the booking hall. Paper ones on the charts in the Survey "
            "Room. And the Clock Tower Walk, where every dial in the place had been "
            "set by them for a century."
        ),
        "e_set_caught": (
            "There is nowhere to hide on a tiled floor. The bell brought the porter "
            "round the corner at a trot and Tess just stood there, going hot from "
            "the neck up. She got the lamp out and held it towards him before he "
            "could ask, which she was glad about later. He did not shout. He asked "
            "her to say, in her own words, what she had taken and why, which turned "
            "out to be considerably harder than being shouted at. Then a chair, and "
            "a phone call to her dad. She was back at ten in the morning, in "
            "daylight, showing the manager where the floor opened."
        ),
        "e_neutral_call_home": (
            "Three rings, and her dad went from fast asleep to fully upright to "
            "coming now in under five seconds. Tess put the handset down and went "
            "to sit in the booking hall where the heating still ticked, notebook "
            "open, taking stock. Key: found. Code: broken. Direction: known. "
            "Ending: no. That was the honest column. Headlights crossed the "
            "shutters at twenty past, and she was already sketching how a person "
            "might get back inside on a Saturday."
        ),
        "e_win_hero_curator": (
            "May I see, was all the heritage manager said, and then he moved faster "
            "than Tess would have credited a man in a duffel coat. Gloves and lamps "
            "and a clipboard were on the concourse before ten. She stood at the top "
            "of the opening and fielded questions from people who kept forgetting "
            "she was twelve. Two months later there was a small ceremony, and "
            "somebody read out that she had handed Iris Halloway's gift back to the "
            "town, which was the exact thing the letter had asked for."
        ),
        "e_set_stuck_dark": (
            "Somewhere around the sixth bay the dark quietly swapped the room "
            "round. Tess turned to go back and could not have told anybody which "
            "way back was. So she stopped. She sat on the floor with a shelf "
            "against her spine and her bag across her lap, worked out that opening "
            "was at seven, and settled in for it. It was cold. It was extremely "
            "dusty. After about ten minutes it also stopped being frightening. The "
            "locker never opened, and no one ever learned she had been within four "
            "bays of it."
        ),
        "e_win_secret_kept": (
            "Three people knew. Tess, Femi, and Row, and a promise made on the top "
            "deck of the 41 with a bag of chips going cold between them. They got "
            "in four times before Christmas, never after dark, never moving so much "
            "as a label, and they spent the whole of that year disagreeing about "
            "when the right moment to tell somebody would be. A heron. A strongroom. "
            "It was, in Femi's opinion, worth more kept than spent."
        ),
        "v_grab": (
            "There it stood, one shelf up, alone on a square of baize: silver, "
            "small enough to close a hand round, its lens the green of a bottle "
            "bottom. Tess recognised it before she had finished looking. Page "
            "sixty-one of the guidebook, caption and no photograph. Put that on a "
            "table tomorrow and nobody would ask her a single sceptical question. "
            "Her hand went out. It stayed out. It neither picked the thing up nor "
            "came back to her side."
        ),
        "ci_clock_pendulum": (
            "Out. Hang. Back. Hang. The master pendulum crossed the only way "
            "through on a rhythm so regular that Tess had it after two swings, and "
            "it was taller than she was, and no force on earth had ever persuaded "
            "it to go quicker. There was a gap. There was a decision about whether "
            "to trust the gap. Or she could move right now, while the thing was "
            "away over at the end of its arc, and simply be fast."
        ),
        "v_map": (
            "Linen, hand-inked, and a red cross that was entirely unembarrassed "
            "about being a red cross. Tess spread it flat. What it showed was the "
            "bricked-up platform: a whole limb of Kingsmoor sealed off, rendered "
            "over, and dropped from every plan drawn since. Whatever else Iris "
            "Halloway had put away was through there. She was inside. She was "
            "awake. She could also do the careful thing and photograph it for "
            "somebody with a permit, or the thorough thing and read every line "
            "before moving at all."
        ),
        "v_share_secret": (
            "Three names, no more. Tess, Femi, Row. It would stay that way at "
            "minimum until the three of them had a proper plan for handing it over, "
            "and Tess had a strong suspicion that a proper plan would take them the "
            "better part of a year to agree on. A heron with its wings up. A room "
            "nobody had walked into since before their parents were born. Some "
            "things are better carried by three people than announced to three "
            "hundred."
        ),
        "e_win_lost_wing": (
            "Tess handed it straight over, and she handed it over correctly. "
            "Photographs to the manager before nine. A conservation officer on site "
            "by two. Local paper Thursday, regional news the week after. When the "
            "builders finally cut the render they did it so gently that she had to "
            "bite her lip, and then four carriages came out into the light with "
            "their lettering still gold, and the queue to see them went down the "
            "steps and round the corner."
        ),
        "e_neutral_evidence": (
            "Eleven photographs, a phone on nine per cent, and a strongroom she had "
            "left so exactly as she found it that even the letter lay at its "
            "original angle. Tess walked out at ten past six past a cleaner who "
            "said good morning and assumed she belonged to somebody. That was "
            "enough. Enough to bring adults back with lamps and gloves and forms, "
            "and Tess discovered she did not mind at all letting them argue about "
            "the rest."
        ),
        "ci_map": (
            "Charts covered the Survey Room to the picture rail: coastlines, "
            "cuttings, and a river that had been talked into a new course by men "
            "with theodolites. The brass globe stood on rails in the middle, a head "
            "taller than Tess, oceans the shade of stewed tea. The route atlas was "
            "open on a slanted stand with one corner turned down, and somebody's "
            "pencil still lay in the gutter of the page, as though the room "
            "expected to be used again shortly."
        ),
    }
)
