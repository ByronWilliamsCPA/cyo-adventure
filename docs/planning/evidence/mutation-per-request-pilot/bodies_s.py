"""Book S prose: mutant S (M1 sibling-subtree-swap) filled in the museum world."""

from __future__ import annotations

TITLE = "The Midnight Museum"

BODIES: dict[str, str] = {
    "n_open": (
        "The coach pulled out of the car park without her. Nadia watched its "
        "tail lights swing away through the glass doors of the Ellery Museum, "
        "and heard the locks go over behind her with a sound like a full stop. "
        "Her phone was flat. The lobby lights dimmed to a low amber. In her "
        "coat pocket was the torn map she had picked up off the floor by the "
        "cloakroom, half a plan of a building that no longer matched this one, "
        "with a note along the bottom in old ink: what Josiah Ellery left "
        "behind is still inside."
    ),
    "n_start": (
        "The rotunda opened around her, cold and enormous, its dome a grey coin "
        "of sky. Three archways led off it into the dark, each labelled in "
        "brass. Nadia turned slowly on the spot and made herself choose."
    ),
    "a_gems1": (
        "The Gallery of Gems glittered under the low security lights, a hundred "
        "small fires trapped in glass. Nadia walked between the plinths with "
        "her arms tight to her sides. The big central case sat crooked, shoved "
        "a hand's width off the outline worn into its plinth, as though "
        "somebody had moved it and not quite put it back. Then, somewhere off "
        "to her left, a soft electronic beeping started up, patient and "
        "regular, like a question being asked over and over."
    ),
    "a_gems_case": (
        "Up close the big central case had been opened and shut in a hurry. The "
        "seal was pinched. One corner of the lining had folded under itself and "
        "stayed folded. Beside it the tilted vitrine leaned on a bad foot, its "
        "glass smeared where a hand had steadied it, and behind the whole "
        "arrangement the little fallen card lay face down in the dust, printed "
        "side hidden. Two things disturbed, in a room where nothing had been "
        "touched in years. Whoever had hidden Josiah Ellery's secret had come "
        "this way and had not been careful."
    ),
    "a_gems_vitrine": (
        "Nadia crouched and tipped her head under the tilted vitrine. On the "
        "underside of the base, scratched deep enough to catch her fingernail, "
        "was a brass symbol: three linked rings inside a square. She dug the "
        "torn map out of her pocket and there it was again, inked in the "
        "corner, with a line running from it toward a corridor the modern plan "
        "did not show. The service corridor, then. The mark was a signpost, and "
        "somebody had left it for her."
    ),
    "a_gems_note": (
        "The little fallen card was an old exhibit label, typed once and then "
        "corrected by hand in spidery brown ink. Josiah Ellery's writing, the "
        "same as on her torn map. One word had been underlined twice: "
        "SERVICE. On the map, that word marked a door tucked behind the "
        "gallery, drawn as a thin rectangle with three rings beside it. Nadia "
        "read it twice, folded the card into her pocket, and looked toward the "
        "service corridor."
    ),
    "a_gems_corridor": (
        "The service corridor smelled of dust and floor polish, and the "
        "carpet gave way to bare boards halfway along. At the far end a small "
        "locked door waited, and its keyhole was not a keyhole shape at all: it "
        "was three linked rings inside a square, cut clean through the plate. "
        "No key hung near it. No key hung anywhere. But at the foot of the wall "
        "a loose skirting board had lifted away from the plaster, and the gap "
        "behind it was dark and exactly the size of a hand."
    ),
    "a_gems_alarm": (
        "The beeping came from a motion sensor blinking amber above the "
        "doorway, counting down to something. At the far end of the Gallery of "
        "Gems a torch beam swung out of a side door and began to travel along "
        "the cases, and behind it came the night guard's slow footsteps and the "
        "jingle of a big ring of keys. The beam swept nearer. There was a "
        "plinth two steps to her right, and open floor everywhere else."
    ),
    "a_gems_hide": (
        "Nadia folded herself behind the plinth and made herself into a very "
        "small, very still shape. The torch beam crossed the case above her "
        "head, paused, and moved on. The footsteps went away down the gallery "
        "and a door sighed shut somewhere. When she lifted her head the "
        "service corridor stood open a hand's width, propped by the night "
        "guard's own doorstop."
    ),
    "b_egypt1": (
        "The Egyptian Wing was all long shadows and painted eyes, and every "
        "one of them seemed to be looking somewhere just past her shoulder. The "
        "great sarcophagus stood in the middle of the floor with its lid "
        "raised a finger's width on wooden blocks, waiting for a conservator "
        "who had gone home hours ago. On the wall behind it the faded wall map "
        "showed the museum as it had been a hundred years ago, with rooms in "
        "places where there were now only walls."
    ),
    "b_egypt_sarco": (
        "The loose lid was heavier than it looked and sat slightly askew, as "
        "though it had been lifted and lowered by someone in a hurry. Nadia "
        "could see a stripe of cotton wool packing beneath it. Two steps away "
        "the amulet display held nine small carved beetles on velvet and one "
        "empty dent where a tenth had lain, the shape of it still pressed into "
        "the cloth. Borrowed, said the little card. Borrowed, and never "
        "returned."
    ),
    "b_egypt_lid": (
        "Nadia braced both hands and eased the loose lid up its last inch. "
        "Tucked into the cotton wool, where no ancient hand had ever put it, lay "
        "a flat disc of brass stamped with three linked rings inside a square: "
        "the twin of the brass symbol on her torn map. A draught moved past her "
        "ankles as she straightened, cold and steady, coming from the connecting "
        "hall."
    ),
    "b_egypt_amulet": (
        "The empty dent in the amulet display was labelled in spidery brown "
        "ink, in the same hand as her torn map: removed for study, J.E. Nadia "
        "leaned closer and found something else, scratched into the case frame "
        "so lightly that it only showed at an angle: a thin arrow, no longer "
        "than her thumbnail, pointing steadily away from the display toward the "
        "connecting hall."
    ),
    "b_egypt_hall": (
        "The connecting hall was bare, just cream paint and a smell of old "
        "radiators. At the end of it a small locked door waited, and cut into "
        "its plate was a keyhole shaped like three linked rings inside a square. "
        "Beside the door somebody had left a fire bucket of sand and a canvas "
        "roll of old tools. Nadia stepped toward it and felt one loose floor "
        "tile rock under her heel, hollow as a drum."
    ),
    "b_egypt_map": (
        "The faded wall map showed a wing that appeared on no modern floor "
        "plan: a long room off the east side, drawn in confident lines, with "
        "three linked rings inked beside its door. A display torch hung on a "
        "bracket below the map, part of an exhibit about tomb explorers. Beyond "
        "it, past a velvet rope and a small polite sign, The Roped-Off Gallery "
        "stood dark and inviting."
    ),
    "b_egypt_torch": (
        "The display torch was heavier than a real one and its beam was "
        "yellow, but it worked. Nadia followed the faded wall map's forgotten "
        "wing along a wall she had walked past twice without seeing, and came "
        "out in a connecting hall she had never been in. At its end stood a "
        "small locked door with three linked rings cut into the plate, waiting "
        "exactly where the old map said it would be."
    ),
    "c_archive1": (
        "The old Archive smelled of paper and cold stone, and the stairs down "
        "to it complained under her feet. Green-shaded reading lamps stood in a "
        "row along a long table, all switched off. The dusty visitor ledger lay "
        "open on a lectern by the door, its page furred with dust. Past the "
        "lamps the back stacks began, shelf after shelf marching away until the "
        "light gave up and the dark simply took over."
    ),
    "c_archive_ledger": (
        "The dusty visitor ledger held a century of names in a dozen "
        "handwritings, and then it stopped, mid-page, mid-year, as though the "
        "museum had shut a door on its own memory. Nadia ran her finger down to "
        "the last line and found nothing after it. Behind the lectern stood the "
        "card index in its oak drawers, and beneath that the sticking bottom "
        "drawer, half open, jammed on something folded. Whatever Josiah Ellery "
        "had filed away before the Ellery Museum forgot him was in one of the "
        "two."
    ),
    "c_archive_index": (
        "Nadia walked the card index with two fingers. The cards went in "
        "order, neat and obedient, and then one sat wrong: an out-of-order "
        "index card shoved between the R's, stamped in the corner with three "
        "linked rings inside a square. It gave no title, only a shelf number "
        "and a line of brown ink: a low cabinet, back stacks, north wall."
    ),
    "c_archive_drawer": (
        "The sticking bottom drawer came free with a bang that made her freeze "
        "for a full ten seconds. Inside was a folded plan with one shelf "
        "circled, drawn in the same brown ink, the circle gone over twice. "
        "Nadia unfolded her torn map beside it and the two matched along one "
        "edge, brass symbol to brass symbol, like the halves of a torn ticket."
    ),
    "c_archive_stack": (
        "Deep in the back stacks the shelves closed in and the air went still. "
        "At the north wall, under a run of dictionaries nobody had opened since "
        "before she was born, stood a low cabinet with a keyhole shaped like "
        "three linked rings inside a square. She tried it with her fingers. "
        "Locked, and no key anywhere. But the dictionaries hid a shallow gap "
        "behind the books, just wide enough for a hand."
    ),
    "c_archive_dark": (
        "Six steps into the back stacks the light behind her stopped being any "
        "use at all. The shelves went up past where she could reach and on "
        "forever in both directions, and the dark had a texture to it, dusty and "
        "close. Somewhere along the left-hand shelf, she was fairly sure, hung a "
        "battery lantern on a hook. Or she could keep going by feel and count "
        "shelves as she passed them."
    ),
    "c_archive_lantern": (
        "Her fingers walked the shelf edge, found a bracket, found a strap, and "
        "closed on a battery lantern. It came on with a clunk and a wide white "
        "beam. Three shelves ahead, painted small on the shelf end, was a brass "
        "symbol of three linked rings, and tucked behind it, low to the floor, "
        "the pale corner of a low cabinet."
    ),
}

BODIES.update(
    {
        "n_key": (
            "It was in the gap, wrapped in oilcloth gone stiff with age: a brass "
            "key as long as her palm, stamped at the bow with three linked rings "
            "inside a square. Tied to it with garden twine was the coded note, a "
            "single card of paired letters and numbers that meant nothing at all "
            "yet. Nadia turned the key over twice. Her torn map showed three "
            "doors wearing that mark. Josiah Ellery's study, up on the landing. "
            "The sealed display cabinet in the long gallery. And the service "
            "stairs behind the cloakroom, locked since before she was born."
        ),
        "k_founder": (
            "The brass key turned in Josiah Ellery's study door as though it had "
            "been oiled that morning. Inside, the air was still and smelled of "
            "pipe smoke that had faded fifty years ago. The roll-top desk stood "
            "closed under the window, its slats furred with dust, and above the "
            "fireplace a stern painted portrait of Ellery himself looked out "
            "over a room that nobody had bothered to change or clear."
        ),
        "k_founder_desk": (
            "The roll-top rattled up and showed a honeycomb of pigeonholes, "
            "every one stuffed with receipts and pressed flowers and railway "
            "tickets. Wedged behind them was a leather notebook, its cover soft "
            "as cloth. Nadia opened it and stopped. The first page carried the "
            "same paired letters as the coded note on the key: half a cipher, "
            "written out in a careful hand, waiting for its other half."
        ),
        "k_founder_portrait": (
            "The stern painted portrait swung out on a hinge she had not "
            "expected, and behind it a shallow wall safe stood open, its door "
            "hanging on one bracket. Inside was nothing but dust, a dead moth, "
            "and the cipher wheel: two discs of card riveted together, letters "
            "around the rim, worn shiny where a thumb had turned it a thousand "
            "times. Exactly the tool the coded note seemed to be asking for."
        ),
        "k_display": (
            "The sealed display cabinet ran the length of the wall, and behind "
            "its stiff glass lay Josiah Ellery's travel journals, propped open "
            "at pages of tiny handwriting. The brass key fitted the latch at the "
            "end and turned with a satisfying clack. The lid, though, had been "
            "shut for decades and the wood had swollen into the frame all the "
            "way along."
        ),
        "k_display_open": (
            "Nadia worked along the lid a finger's width at a time, lifting and "
            "settling and lifting again, until the swollen wood let go without a "
            "sound. Inside, a slim ledger lay on top of the journals with a "
            "ribbon marking its place, and the marked page was not words at all "
            "but line after line of paired letters."
        ),
        "k_cabinet": (
            "She lifted the slim ledger out with both hands. Its coded page used "
            "the same pairings as the note tied to the brass key, letter for "
            "letter, which meant one of them was a lock and one was a key. Down "
            "in the middle of the landing stood the reading table under its "
            "green lamp, wide enough to lay everything out side by side and "
            "actually think."
        ),
        "k_display_force": (
            "She got her fingers under the lip and leaned. The lid rose an "
            "eighth of an inch and the old glass along the front made a small "
            "dry sound, a sort of tick, that Nadia felt in her back teeth. Ease "
            "off and try it gently, said the sound. One good yank and it is "
            "open, said her arms."
        ),
        "k_display_careful": (
            "She let her breath out, changed her grip, and lifted with her palms "
            "instead of her fingertips, straight up and slow. The lid came away "
            "clean. The slim ledger slid free with its coded page uppermost, and "
            "the glass stayed exactly as whole as she had found it."
        ),
        "k_stairs": (
            "The brass key opened the service stairs on the second try. Beyond "
            "the door the steps went up into a shadow the emergency lighting "
            "could not be bothered with, and the handrail was thick with dust. "
            "At the foot of the stairs stood the small cupboard, its door ajar, "
            "and something pale showed in the gap."
        ),
        "k_stairs_up": (
            "At the top the stairs let out onto a landing she had never seen "
            "from the public side: Josiah Ellery's old reading table, a green "
            "lamp still standing on it, and a chair pushed back as though "
            "somebody had just stood up. Beside the lamp, side by side, lay a "
            "card of paired letters and the cipher wheel."
        ),
        "k_stairs_base": (
            "The small cupboard held a rolled chart tied with tape and a pair of "
            "spectacles with one arm missing. Nadia unrolled the chart on her "
            "knees. It was not a picture of anything. It was a page of code, "
            "column after column of paired letters, and reading it here in the "
            "dark by feel was hopeless. It wanted a table and a lamp."
        ),
        "k_study": (
            "However she had come, she came at last to Josiah Ellery's reading "
            "table on the upper landing, and set out what she had brought. The "
            "coded note. The cipher wheel, its two discs stiff with age. She "
            "pulled the chair in, clicked the green lamp on, and its small warm "
            "circle made the museum feel, for the first time all night, like a "
            "place where somebody worked instead of a place she was trapped in. "
            "She lined the outer letters against the inner ones and read off the "
            "first line."
        ),
        "n_cipher": (
            "The first line came out of the wheel one letter at a time, and it "
            "was not a treasure or a name. It was a direction: FOLLOW THE STARS "
            "TO THE HEART. Nadia sat back. Three rooms in this building had "
            "stars in them, and the torn map put all three around the rotunda "
            "like numbers on a clock face. The Astronomy Hall, with its painted "
            "ceiling. The Map Room, where every chart was a sky of its own. And "
            "the Clock Corridor, where a hundred dials had been set by the "
            "stars for a century."
        ),
        "ci_stars": (
            "The Astronomy Hall glimmered even in the dark. Above her the "
            "painted star dome held its constellations in flaking gold, and the "
            "whole room smelled faintly of varnish. A spiral stair went up "
            "toward the dome in polite museum curves, roped off at the bottom "
            "with a sign about restoration work. Against the side wall the "
            "maintenance ladder went up the same distance in a quarter of the "
            "steps."
        ),
        "ci_stars_dome": (
            "Under the painted star dome, Nadia turned in a slow circle with the "
            "cipher's clue in her head, and found it: one constellation picked "
            "out in fresher gold than the rest, three linked stars in a square "
            "of black. Beneath it, set into the panelling, a small marked door "
            "opened onto a stair heading down toward the rotunda at the heart of "
            "the museum."
        ),
        "ci_stars_ladder": (
            "The maintenance ladder took her up faster than she liked, and let "
            "her out on the narrow catwalk that ran around the hall above the "
            "cornice. From here the floor was a long way down and the painted "
            "star dome was near enough to touch. Across the catwalk, thirty "
            "steps away, was a grey service door. Above her, a second ladder "
            "went on up into the dome's dark."
        ),
        "ci_stars_cross": (
            "Nadia put one hand on the rail, fixed her eyes on the grey door, "
            "and did not look down once. The catwalk rang softly under her "
            "shoes. The service door opened on a dusty back stair that stepped "
            "down and down, and let her out at last on the edge of the rotunda."
        ),
        "ci_map": (
            "The Map Room was papered floor to ceiling with charts of coasts "
            "that had changed shape since they were drawn. In the middle stood "
            "the great floor globe on brass rails, taller than Nadia, its "
            "oceans gone the colour of weak tea. Beside it the giant bound "
            "atlas lay open on a slanted stand, one page turned back and "
            "waiting."
        ),
        "ci_map_globe": (
            "Nadia read the cipher's numbers again and turned the great floor "
            "globe until the marked latitude came round under the brass "
            "meridian. Something inside it clicked, once, like a jaw closing. "
            "Low on the wall behind the stand a panel swung aside on its own "
            "weight, showing a short passage with the rotunda's light at the "
            "end of it."
        ),
        "ci_map_atlas": (
            "The giant bound atlas would not stay on the page it was open at. "
            "It fell instead, heavily and with obvious opinion, to a page that "
            "was not printed at all: a hand-drawn plan of the museum, added in "
            "brown ink by Josiah Ellery himself. Across it ran a route in faded "
            "red, from this very room toward the centre of the building."
        ),
        "ci_atlas2": (
            "The red route did not go the way she expected. It threaded a back "
            "stair, crossed a store room full of stacked chairs, and dog-legged "
            "around a lift shaft. Nadia followed it exactly, counting corners, "
            "half sure she was lost, and came out through a door that opened, "
            "precisely as drawn, onto the rotunda."
        ),
        "ci_clock": (
            "The Clock Corridor ticked. Not together, which would have been "
            "restful, but in a hundred slightly different opinions about what a "
            "second was. Long-case clocks stood shoulder to shoulder down both "
            "walls. At the far end one doorway glowed faintly where the gear "
            "room's dials were lit, and beside it a lower arch led under the "
            "slow, heavy pendulum of the museum's master clock."
        ),
        "ci_clock_gears": (
            "In the gear room the master clock stood open like a cupboard, all "
            "brass wheels and oiled shafts. Its hands were stopped at nothing "
            "in particular. Nadia read the cipher's hour, took the minute hand "
            "between two fingers, and walked it round until it was true. "
            "Somewhere behind the mechanism a catch let go, and a maintenance "
            "door drifted open toward the rotunda."
        ),
        "ci_clock_pendulum": (
            "The slow, heavy pendulum swung across the only doorway on a beat "
            "she could have counted in her sleep: out, hang, back, hang. It was "
            "taller than she was and moved as though nothing in the world could "
            "hurry it. She could time her steps and walk through in the gap, or "
            "go now, while it was at the far end of its swing, and be quick."
        ),
        "ci_clock_cross": (
            "Nadia counted four beats to be sure, waited for the fifth, and "
            "walked through at an ordinary speed without hurrying at all. The "
            "pendulum sighed past behind her. Beyond the doorway the passage "
            "sloped gently down, and the ticking faded, and the rotunda opened "
            "up ahead."
        ),
    }
)

BODIES.update(
    {
        "n_rotunda": (
            "Every road in the Ellery Museum came back to the rotunda, and Nadia "
            "arrived under the great glass dome with the cipher's last line still "
            "turning in her head. In the centre of the marble floor stood the "
            "clockwork globe, a cage of brass rings taller than a person, "
            "gathering what little light there was. The heart, the cipher had "
            "said. Josiah Ellery had hidden his real hidden collection here, "
            "under everybody's feet, for a hundred years. She could set the rings. "
            "She could search the pedestal for a seam. Or she could risk the "
            "night guard's records room and read what the building said about "
            "itself."
        ),
        "ro_align": (
            "Up close the clockwork globe's rings turned with a whisper of "
            "well-kept brass. Each one carried numbers etched small around its "
            "edge, and the cipher gave an exact setting for all four. The trouble "
            "was that the rings were stiff for the first inch and then suddenly "
            "were not, so it was very easy to sail straight past a mark and have "
            "to come back."
        ),
        "ro_align_set": (
            "Nadia went slowly. She set each ring to its decoded mark and checked "
            "it twice before touching the next, and when the fourth clicked home "
            "the whole globe sighed. Gears met somewhere deep in the plinth. A "
            "section of the marble floor slid back with a sound like a held "
            "breath, and showed the stair below the floor."
        ),
        "ro_align_guess": (
            "She spun the rings by feel, trusting her hands, and the numbers "
            "clunked into a pattern that was almost right and therefore entirely "
            "wrong. The clockwork globe groaned. Something under the floor made a "
            "grinding complaint and stopped. She could reset it all and work the "
            "cipher through properly, or put her shoulder into the rings and make "
            "them go."
        ),
        "ro_align_retry": (
            "Nadia backed every ring off to zero, spread the decoded line on the "
            "marble, and read it twice before she touched anything. Then she "
            "turned each ring to its true mark, one at a time. The clockwork "
            "globe sighed again, kindly this time, and the floor opened onto the "
            "stair below."
        ),
        "ro_panel": (
            "The pedestal under the clockwork globe was not plain stone after "
            "all. Its face was cut into small square tiles, and the tiles "
            "shifted under her thumb, sliding into gaps like a puzzle from a "
            "Christmas cracker. Nadia crouched to look and felt something else "
            "along one seam at the back: a thin cold draught, steady as "
            "breathing, coming from somewhere behind the stone."
        ),
        "ro_panel_solve": (
            "The tiles wanted to make a picture, and the picture wanted to be "
            "three linked rings inside a square. Nadia slid them one by one, "
            "backtracking twice, until the last tile dropped into place. Under "
            "the pedestal a catch let go with a clack, and the marble beside her "
            "knee swung down onto the stair below the floor."
        ),
        "ro_panel_secret": (
            "The draught came from a low door at the back of the chamber, no "
            "taller than her shoulder, painted the same colour as the wall and "
            "shown on no plan she had seen all night. It opened when she leaned "
            "on it. Beyond was a dusty room crowded with half-built clockwork, "
            "and the cold air of a place that had been shut a very long time."
        ),
        "ro_workshop": (
            "This was Josiah Ellery's private workshop, sealed and forgotten, "
            "and it was better than any treasure. Benches ran round three walls "
            "under a skin of dust. A brass heron stood half finished with its "
            "neck opened up and its gears laid out beside it in order. There "
            "were labelled drawers, a wall of small tools hung in outlines drawn "
            "for them, and a stool pushed back as though he had gone to make tea "
            "and never come back. Not the collection the cipher had promised. "
            "Something better, because nobody in the world knew it was here."
        ),
        "ro_records": (
            "The night guard's records room hummed with old monitors showing "
            "nine grey views of empty galleries. Nadia stood very still by the "
            "door until she was sure the chair was empty. On the desk the rounds "
            "log lay open at tonight's date, half filled in, and beside it sat "
            "the heavy black telephone, the sort with a dial, plugged into the "
            "wall and probably still working."
        ),
        "ro_records_guard": (
            "Nadia turned the rounds log back through years and then decades, "
            "and the handwriting changed and changed again until it became the "
            "spidery brown ink she knew. The oldest entry was Josiah Ellery's "
            "own: the floor beneath the globe opens at the cipher's hour, and "
            "the stair below is safe. She ran back to the rotunda and found the "
            "marble already sliding quietly open."
        ),
        "ro_records_phone": (
            "The heavy black telephone had a proper dial that clattered round "
            "and a receiver that weighed like a brick, and when she lifted it "
            "there was a dial tone, patient as anything. She could call home "
            "right now. Warm car, worried faces, hot chocolate, and a mystery "
            "left half solved but safe in her notebook until another day."
        ),
        "n_vault": (
            "The stair below the floor went down eleven steps and opened on a "
            "chamber that smelled of cedar and cold stone. Nadia's light "
            "travelled along shelves and stopped, and travelled again. Paintings "
            "stacked in racks. Cases of coins. A stuffed albatross with its wings "
            "half spread. A whole museum's worth of donated treasures that Josiah "
            "Ellery had meant the town to have and had never lived to hand over. "
            "On a small table in the middle lay the sealed letter with her "
            "brass symbol on its wax, and beside it the old treasure map, and "
            "beside that, waiting, the question of what one person was supposed "
            "to do with all of this."
        ),
        "v_letter": (
            "The wax cracked cleanly and the sealed letter opened out in her "
            "hands. Josiah Ellery had written it to nobody in particular. He "
            "explained it all: a bad year, a board that wanted the collection "
            "sold, and a decision to hide it until the museum deserved it back. "
            "Whoever finds this, he wrote, please give it to the town, and do it "
            "in daylight. The last line was not a sentence at all. It was a "
            "measurement, and a direction, and a small drawing of a shelf."
        ),
        "v_letter_reveal": (
            "Nadia counted along the racks the way the last line said and pushed. "
            "A shelf that was not a shelf swung out on hinges, and behind it, in "
            "a slot cut for it exactly, stood Josiah Ellery's catalogue: every "
            "piece in the chamber listed in his brown ink, with where it came "
            "from and where it truly belonged. The whole mystery lay open in her "
            "hands, in alphabetical order."
        ),
        "v_reveal2": (
            "She read it kneeling, then sitting, then lying on her front with "
            "the lamp propped on her bag. The catalogue was not a list. It was "
            "the town's own history, given back: a fisherman's medal, a "
            "schoolteacher's shell collection, a bride's inked fan. Beside each "
            "entry, a name and a family and a street. By the time the windows "
            "above her went from black to grey, Nadia understood not just where "
            "the hidden collection was, but why it had been hidden, and how to "
            "give it back."
        ),
        "v_letter_keep": (
            "Nadia folded the sealed letter along its old creases and buttoned it "
            "into her inside pocket, and touched nothing else. The chamber had "
            "waited a hundred years; it could wait until people were awake. "
            "Josiah Ellery had trusted a stranger with an instruction, and doing "
            "it properly, in daylight, with the right grown-ups, felt like the "
            "first half of keeping that trust."
        ),
        "v_map": (
            "The old treasure map was drawn on linen and marked with a red X "
            "that was not embarrassed about being a red X. It showed the walled-up "
            "wing, a whole room of the museum bricked over and plastered smooth "
            "and left out of every plan since. More of the collection waited "
            "there. She could follow it now, while she was here and awake. She "
            "could photograph it and let somebody else open the wall. Or she "
            "could sit down and trace every faded line to be sure."
        ),
        "v_map_follow": (
            "The map took her back up and along a corridor she had walked twice, "
            "to a stretch of plaster that sounded wrong when she knocked it. A "
            "service hatch at knee height opened on the walled-up wing, and her "
            "beam found a small sealed gallery of paintings, hung and lit for a "
            "visit that never happened. She marked the hatch, and photographed "
            "every frame."
        ),
        "v_map_photo": (
            "Nadia laid the old treasure map flat and photographed it corner to "
            "corner, twice over, close enough to read the smallest note. Then she "
            "folded it exactly as she had found it, put it back on the table, and "
            "left the chamber precisely as it was. The proof was on her phone. "
            "The decision belonged to somebody with keys."
        ),
        "v_share": (
            "Nadia sat on the bottom step with the lamp on her knees and thought "
            "about who this belonged to. The curator would know exactly what to "
            "do, and would do it right, and it would stop being hers. Her friends "
            "would keep it, and it would stay wonderful and secret and small. Or "
            "she could leave a trail and let the Ellery Museum find its own lost "
            "heart without ever knowing she had been here."
        ),
        "v_share_curator": (
            "She gathered up the sealed letter and the catalogue and waited by "
            "the staff door until the first car pulled in. The curator came in "
            "with a takeaway coffee, stopped, and forgot she was holding it. "
            "Nadia laid the whole night out on the bonnet of the car, in order, "
            "and watched a grown-up's face do something she had never seen "
            "before."
        ),
        "v_share_secret": (
            "This, Nadia decided, was going to be hers and Priya's and Oscar's "
            "and nobody else's, at least until they had worked out how to give it "
            "away properly. A chamber under the rotunda with an albatross in it. "
            "A shared, guarded, ridiculous wonder to visit on wet Saturdays and "
            "talk about in code."
        ),
        "v_share_museum": (
            "She propped Josiah Ellery's own map open on the night guard's desk "
            "with the letter beside it and a note in her neatest writing: THE "
            "FLOOR UNDER THE GLOBE OPENS. START HERE. Then she let herself out "
            "into the grey morning and left the Ellery Museum to finish what its "
            "founder had started."
        ),
        "v_grab": (
            "Behind the pedestal the niche was barely a cupboard, and on its one "
            "velvet shelf, alone, sat the small jewelled owl: silver, "
            "green-eyed, no bigger than her fist, and unmistakably the thing from "
            "the missing photograph in the guidebook. In her bag it would prove "
            "every word she said tomorrow. Nadia's hand hovered over it, and did "
            "not come down, and did not go back."
        ),
        "v_grab_run": (
            "She closed her fingers round the small jewelled owl, put it in her "
            "bag, and went. She was three steps up the stair below the floor when "
            "the shelf she had emptied rose a millimetre on its spring, and a "
            "gentle silvery chime started somewhere above her and did not stop, "
            "and followed her all the way into the hall."
        ),
        "v_grab_return": (
            "Nadia set the small jewelled owl back down on its velvet, squared it "
            "up with two fingers, and stepped away. A trophy would have made a "
            "better story and a worse morning. She climbed out with nothing but "
            "her notebook, her photographs, and hands she did not have to keep in "
            "her pockets."
        ),
    }
)

BODIES.update(
    {
        "e_set_alarm": (
            "The torch beam stopped on her and stayed there. Nadia stood in the "
            "open with her hands out and her heart going like a bird. The night "
            "guard lowered the light, sighed the sigh of a man who has found "
            "worse things than a stranded schoolgirl, and walked her down to the "
            "lobby to wait on the good sofa for a lift home. He even found her a "
            "biscuit. Josiah Ellery's secret stayed exactly where it was, and "
            "Nadia went home safe, warm, and extremely embarrassed."
        ),
        "e_set_locked_gallery": (
            "The Roped-Off Gallery's door swung shut behind her with a soft "
            "expensive click, and had no handle at all on the inside. Nadia "
            "tried it twice, laughed once without much in it, and then found a "
            "bench, a radiator that was still faintly warm, and a folded "
            "exhibition banner that made a passable blanket. She was safe, dry, "
            "and completely stuck. Somewhere on the other side of the wall, the "
            "founder's secret went on keeping itself."
        ),
        "e_set_stuck_dark": (
            "Six shelves in, Nadia turned round to check the way back and found "
            "that the dark had rearranged itself. Left and right stopped meaning "
            "anything. She did the sensible thing, sat down with her back against "
            "the shelf and her bag on her knees, and waited for the lights to "
            "come on at opening. It was dusty, and long, and not frightening "
            "after the first ten minutes. The low cabinet stayed locked, and "
            "nobody found out how close she had come."
        ),
        "e_set_broken_case": (
            "The glass went with a sharp snap that sounded like the whole "
            "building saying no. Nadia snatched her hands back. Nothing was hurt "
            "but the case, and one long crack ran corner to corner where there "
            "had been none. Feet came at a run. She spent the rest of the night "
            "in the lobby explaining herself to the night guard and then to a "
            "very tired woman on the telephone, and the coded note stayed folded "
            "in her pocket, unread."
        ),
        "e_set_stuck_dome": (
            "Nadia climbed past the catwalk into the dome's dark, one rung at a "
            "time, until the ladder ended at a hatch that had been bricked up "
            "from the other side. There was nothing there. She came down "
            "carefully, both hands, not looking anywhere but her feet, and sat on "
            "the bottom step until her legs stopped humming. Tired, dizzy, and "
            "entirely unhurt, she gave the route up. The rotunda would have to "
            "wait for another night."
        ),
        "e_set_pendulum": (
            "Nadia went on three and the pendulum was working on two. It caught "
            "her shoulder without any malice at all, the way a bus door does, "
            "and put her firmly back on the safe side of the doorway. She sat "
            "down hard on the tiles, more startled than sore. The clocks ticked "
            "their hundred opinions at her. All right, she told the Clock "
            "Corridor. You win tonight."
        ),
        "e_set_jammed_globe": (
            "Nadia put her shoulder into the rings and something inside the "
            "plinth said clack in a final sort of way. After that the brass "
            "would not move at all, in either direction. The floor stayed shut. "
            "She sat down beside the silent clockwork globe with her back against "
            "the plinth, so close to the stair below that she could have drawn "
            "it, and watched the dome go slowly grey."
        ),
        "e_set_caught": (
            "The chime brought the night guard at a trot, and there was nowhere "
            "in a marble rotunda to be invisible. Nadia went red to her ears, "
            "opened her bag, and put the small jewelled owl back into his hands "
            "before he had to ask. He was stern about it, and fair, and made her "
            "say out loud what she had done. Then he found her a chair and rang "
            "her mother. In the morning she came back in daylight and showed the "
            "curator the stair, and everything ended up exactly where it "
            "belonged, including Nadia."
        ),
        "e_set_dawn": (
            "There was always one more faded line to follow, one more crease to "
            "flatten. When Nadia finally looked up from the old treasure map, the "
            "windows above her had gone the colour of dishwater and there were "
            "voices and keys somewhere overhead. She folded the map, put it back "
            "on its table, and slipped out through the staff door into a morning "
            "full of buses, with the walled-up wing half traced and a promise to "
            "herself that she would come back and finish it properly."
        ),
        "e_win_secret_workshop": (
            "Nadia photographed the brass heron, the labelled drawers, the tools "
            "in their painted outlines, and the stool pushed back for a hundred "
            "years, and touched nothing at all. Josiah Ellery's forgotten "
            "workshop stayed exactly as he had left it. In the morning she showed "
            "the curator her phone and watched him sit down slowly on the edge of "
            "a desk. A whole lost room, he kept saying. A whole lost room, and "
            "nobody knew."
        ),
        "e_win_mystery_solved": (
            "Nadia came up the stair below the floor into a rotunda full of "
            "actual daylight, with the sealed letter in one pocket, the catalogue "
            "under her arm, and the whole hundred-year-old truth in her head. She "
            "gave it all back that morning, in order, to the people it had been "
            "meant for. The hidden collection came out of the dark, Josiah "
            "Ellery's name came out of the dark with it, and the Ellery Museum "
            "was never quite the same building again."
        ),
        "e_win_quiet_keeper": (
            "She went home with nothing but a folded letter and a promise. Over "
            "the next few weeks Nadia asked the curator small, careful questions "
            "about founders and floors and old plans, and left photocopies where "
            "they would be found, and let the museum discover itself one step at "
            "a time. Nobody ever quite worked out who had started it. She turned "
            "out to be very good at keeping a trust gently."
        ),
        "e_win_lost_wing": (
            "The walled-up wing was hers to give away, and she gave it away "
            "properly. Her photographs went to the curator at nine, to a "
            "conservator by lunchtime, and into the local paper by Thursday. "
            "Restorers opened the plaster with a care that made her want to "
            "cheer. Half the town queued down the steps to see paintings that "
            "had been six inches behind a wall their whole lives."
        ),
        "e_win_hero_curator": (
            "The curator listened at the staff door with his coffee going cold, "
            "said only, may I see, and then moved very fast for a man in an "
            "overcoat. By ten there was a careful team on the stair below the "
            "floor with lights and gloves and a clipboard. Nadia stood at the top "
            "and answered questions, and was thanked in a speech eight weeks "
            "later as the girl who gave Josiah Ellery's gift back to everybody, "
            "which was exactly what he had asked for."
        ),
        "e_win_secret_kept": (
            "It stayed theirs. Three of them, one chamber, one stuffed albatross, "
            "and an oath sworn on a bus. They went back four times that term, "
            "always in daylight, always leaving everything exactly as they found "
            "it, and they argued happily for a year about when to tell. Some "
            "wonders are better shared with two people than two hundred, at least "
            "for a while."
        ),
        "e_win_donate": (
            "Nadia left the map open, the letter beside it, and her note in "
            "capitals, and went home to bed. Nine days later the Ellery Museum "
            "announced the rediscovery of its founder's lost collection beneath "
            "the rotunda floor. There were banners. There was a ribbon. Nobody "
            "ever found out whose small careful handwriting had set them on the "
            "path, and Nadia read about it in the paper and grinned into her "
            "cereal."
        ),
        "e_neutral_call_home": (
            "Nadia dialled from the night guard's desk, listened to her mother go "
            "from asleep to alarmed to on my way in about four seconds, and then "
            "sat in the warm lobby with her notebook open on her knees. She had "
            "half of it: the key, the code, the direction. Not the ending. The "
            "car headlights swung across the glass doors and she went out to meet "
            "them already planning how to come back and finish it."
        ),
        "e_neutral_evidence": (
            "The old treasure map was safe on her phone in eleven photographs, "
            "and the chamber was exactly as she had found it, down to the fold in "
            "the letter. Nadia slipped out at first light past a cleaner who "
            "assumed she was somebody's daughter. She had enough proof to bring "
            "the right people back with the right equipment, and she was quite "
            "content to let the grown-ups decide what happened next."
        ),
        "e_neutral_wiser": (
            "Nadia climbed out of the chamber with an empty bag and a full "
            "notebook. She had not solved everything. She had not brought "
            "anything home to wave about. What she had was a clear idea of "
            "exactly what she was and was not willing to do at three in the "
            "morning with nobody watching, which turned out to be worth carrying. "
            "She walked home through the waking streets wiser than she had gone "
            "in."
        ),
    }
)

# Length-balancing pass: the fifteen shortest bodies extended so Book S's mean
# words-per-node matches Book D's, removing story length as a confound in the
# S-vs-D comparison.
BODIES.update(
    {
        "ci_clock_cross": (
            "Nadia counted four beats to be sure, waited for the fifth, and "
            "walked through at an ordinary speed without hurrying at all. The "
            "pendulum sighed past behind her, close enough to stir her hair. "
            "Beyond the doorway the passage sloped gently down, and the ticking "
            "thinned out behind her one clock at a time, and then there was only "
            "the sound of her own shoes, and then the rotunda opened up ahead "
            "with its grey coin of sky."
        ),
        "k_display_careful": (
            "She let her breath out, changed her grip, and lifted with her palms "
            "flat under the lip instead of digging in with her fingertips, "
            "straight up and very slow. The lid came away clean, and the smell of "
            "old paper came up with it. The slim ledger slid free with its coded "
            "page uppermost, and the glass along the front stayed exactly as "
            "whole as she had found it, which mattered more to Nadia than she "
            "expected it to."
        ),
        "k_stairs": (
            "The brass key opened the service stairs on the second try, grinding "
            "against a century of rust. Beyond the door the steps climbed into a "
            "shadow the emergency lighting had never been asked to reach, and the "
            "handrail wore dust thick enough to write her name in. Nadia put one "
            "foot on the bottom step and it held without a sound. At the foot of "
            "the flight stood the small cupboard, its door ajar, and something "
            "pale showed in the gap between door and frame."
        ),
        "ro_align_retry": (
            "Nadia backed every ring off to zero, spread the decoded line flat on "
            "the marble, and read it twice before she let herself touch anything "
            "at all. Then she turned each ring to its true mark, one at a time, "
            "checking after every one, refusing to be hurried by her own hands. "
            "The clockwork globe sighed again, kindly this time, and the floor "
            "opened onto the stair below."
        ),
        "ci_stars_cross": (
            "Nadia put one hand on the rail, fixed her eyes on the grey door, and "
            "did not look down once, not even when the catwalk rang softly under "
            "her shoes and the sound went all the way to the floor and came back. "
            "Thirty steps. She counted them. The service door opened on a dusty "
            "back stair that stepped down and down past two locked landings, and "
            "let her out at last on the edge of the rotunda."
        ),
        "v_grab_return": (
            "Nadia set the small jewelled owl back down on its velvet, squared it "
            "up with two fingers, and stepped away from the shelf before her "
            "hands could argue. A trophy would have made a better story and a "
            "considerably worse morning, and she knew which of the two she would "
            "have to live in. She climbed out with nothing but her notebook, her "
            "photographs, and hands she did not have to keep in her pockets."
        ),
        "v_share_museum": (
            "She propped Josiah Ellery's own map open on the night guard's desk "
            "with the letter squared beside it and a note in her neatest, most "
            "grown-up writing: THE FLOOR UNDER THE GLOBE OPENS. START HERE. Then "
            "she checked it twice, weighted the corner with a stapler, let "
            "herself out into the grey morning, and left the Ellery Museum to "
            "finish what its founder had started a hundred years ago."
        ),
        "v_share_secret": (
            "This, Nadia decided, was going to be hers and Priya's and Oscar's "
            "and absolutely nobody else's, at least until the three of them had "
            "worked out how to give it away properly. A chamber under the rotunda "
            "with a stuffed albatross in it. A shared, guarded, faintly "
            "ridiculous wonder to visit on wet Saturdays and discuss in code on "
            "the top deck of the bus home."
        ),
        "ci_atlas2": (
            "The red route did not go the way she expected. It threaded a back "
            "stair, crossed a store room full of stacked chairs, and dog-legged "
            "around a lift shaft for no reason she could see at all. Nadia "
            "followed it exactly, counting corners under her breath, twice "
            "convinced she had lost it, and came out through a plain grey door "
            "that opened, precisely as drawn a century ago, onto the rotunda."
        ),
        "k_display_force": (
            "She got her fingers under the lip and leaned her weight on it. The "
            "lid rose an eighth of an inch and the old glass along the front made "
            "a small dry sound, a sort of tick, that Nadia felt in her back "
            "teeth and did not like at all. Ease off and coax it, said the sound. "
            "One good yank and it is open, said her arms, which had been at this "
            "for five minutes and were bored."
        ),
        "ci_map": (
            "The Map Room was papered floor to ceiling with charts of coasts that "
            "had changed shape since anybody drew them, and rivers that had been "
            "persuaded to go elsewhere. In the middle stood the great floor globe "
            "on brass rails, taller than Nadia, its oceans gone the colour of "
            "weak tea. Beside it the giant bound atlas lay open on a slanted "
            "stand, one page turned back and waiting, as though a reader had "
            "stepped out for a moment in 1911."
        ),
        "ro_align_guess": (
            "She spun the rings by feel, trusting her hands to know better than "
            "her notes, and the numbers clunked into a pattern that was almost "
            "right and therefore entirely wrong. The clockwork globe groaned. "
            "Something under the floor made a grinding complaint, thought about "
            "it, and stopped. She could reset the whole thing and work the cipher "
            "through properly, or put her shoulder into the rings and make them "
            "go where she wanted them."
        ),
        "k_display": (
            "The sealed display cabinet ran the length of the wall, and behind "
            "its stiff clouded glass lay Josiah Ellery's travel journals, propped "
            "open on wire stands at pages of very small handwriting. The brass "
            "key fitted the latch at the end and turned with a satisfying clack "
            "that echoed further than Nadia wanted. The lid, though, had been "
            "shut for decades, and the wood had swollen into the frame all the "
            "way along both sides."
        ),
        "k_display_open": (
            "Nadia worked along the lid a finger's width at a time, lifting and "
            "settling and lifting again, the way you ease a stuck window, until "
            "the swollen wood let go without a single sound. Inside, a slim "
            "ledger lay on top of the journals with a faded ribbon marking its "
            "place, and the marked page was not words at all, but line after line "
            "of paired letters in brown ink."
        ),
        "k_stairs_up": (
            "At the top the stairs let out onto a landing she had never seen from "
            "the public side, and had certainly never been shown on a school "
            "trip: Josiah Ellery's old reading table, a green lamp still standing "
            "on it, and a chair pushed back as though somebody had just got up to "
            "answer a bell. Beside the lamp, laid out side by side, lay a card of "
            "paired letters and the cipher wheel."
        ),
    }
)
