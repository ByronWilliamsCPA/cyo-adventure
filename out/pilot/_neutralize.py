"""Parameterize the-cave-of-echoes skeleton: rewrite ONLY beats and ending titles.

Loads the production skeleton, and for each node replaces the ``beats='...'``
text inside its ``<<FILL role=... words=... beats='...'>>`` body with a
theme-neutral, slotted version (preserving role= and words= exactly), and
replaces each ending ``title`` with a neutral function label. All ids, choices,
targets, ending kinds/valences, and metadata are left byte-for-byte identical.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SRC = Path("/home/user/cyo-adventure/skeletons/8-11/the-cave-of-echoes.json")
DST = Path("/home/user/cyo-adventure/out/pilot/the-cave-of-echoes.parameterized.json")

# node id -> new neutral beats text (slots in {CURLY_CAPS})
BEATS: dict[str, str] = {
    "n_start": (
        "{HERO} and {COMPANION} enter {THRESHOLD} at {OPENING_MOMENT}; three dark "
        "openings breathe cool air and each throws back its own signal, "
        "{ROUTE_A_LURE}, {ROUTE_B_LURE}, and {ROUTE_C_LURE}; {HERO} must choose "
        "which signal to follow before {DEADLINE}"
    ),
    # ---- Route A entry + fork ------------------------------------------------
    "la_tunnel": (
        "the first way, {ROUTE_A_CHAR}, draws them in as {ROUTE_A_LURE} steadies "
        "into a held note; {COMPANION} perks up; {HERO} edges toward a distant "
        "glow and a soft stirring ahead"
    ),
    "la_fork": (
        "the way splits into two tracks: on one side {A1_SIGN} catches the light, "
        "on the other {A2_SIGN} deepens into a warm, pulling sound"
    ),
    # ---- Route A, track 1 (glowing zone, two prizes) -------------------------
    "la_glitter": (
        "the track toward {A1_SIGN} runs past {A1_LANDMARK} that catches {HERO}'s "
        "light; the floor slopes gently down toward a narrow gap breathing cold air"
    ),
    "la_glitter2": (
        "the slope opens into a small antechamber; {A1_ZONE_HINT} shows in the far "
        "wall and the air smells of clean wet stone, a sign the greater find lies "
        "just beyond"
    ),
    "la_grotto_app": (
        "the gap is just wide enough to pass, but {A1_GATE} blocks easy passage as "
        "{DEADLINE_SIGN} begins to gather at their feet; {HERO} can press through "
        "toward the reward or turn back toward {ENTRANCE} while the way stays safe"
    ),
    "la_retreat_pool": (
        "{HERO} and {COMPANION} make their way back toward {ENTRANCE} as "
        "{DEADLINE_SIGN} rises around them; they reach the open air damp and safe, "
        "the greater find left for a better return, promising to come back at the "
        "next {OPENING_MOMENT}"
    ),
    "la_squeeze": (
        "they slip through {A1_GATE} and come out the other side; {COMPANION} "
        "shakes off and the glow ahead brightens into {A1_ZONE}"
    ),
    "la_grotto": (
        "{A1_ZONE} opens around them, full of light and wonder; within reach sits "
        "{A1_OFFER1}, while a deeper way, {A1_OFFER2}, pulls onward toward "
        "something greater"
    ),
    "la_crystal_take": (
        "{HERO} carefully gathers {A1_OFFER1}; it is theirs to keep and lights a "
        "low passage that seems to curve back toward the way out"
    ),
    "la_crystal_out": (
        "the find lights their way up and out to {ENTRANCE}; {HERO} steps into the "
        "open carrying {A1_PRIZE1} for real, with {COMPANION} close behind, proud "
        "of the safe treasure won"
    ),
    "la_crystal_deeper": (
        "the deeper way, {A1_OFFER2}, grows stronger; the passage widens and its "
        "walls smooth into {A1_PRIZE2_PATH}, shaped as if to carry sound"
    ),
    "la_song_app": (
        "ahead the walls curve into {A1_PRIZE2_ZONE}; every drip and footstep rings "
        "and layers; {COMPANION} gives a wondering sound that echoes back many "
        "times over"
    ),
    "la_song": (
        "{HERO} makes a single sound and the whole place answers in shimmering "
        "harmony; they have found {A1_PRIZE2}, a secret almost no one knew, and "
        "carry the wonder of it all the way home"
    ),
    # ---- Route A, track 2 (deep single-prize chain) --------------------------
    "la_hum": (
        "{A2_SIGN} leads down a rounded way; the sound is not wind but "
        "{A2_LANDMARK}, coming from far below; {COMPANION} pads ahead confidently"
    ),
    "la_hum2": (
        "the way steepens; {A2_LANDMARK} steadies into a slow, deep pulse, and pale "
        "light leaks up from a chamber below where {A2_ZONE_HINT} catches the glow"
    ),
    "la_bell_app": (
        "{A2_GATE} offers a way down, left behind by someone long ago; {HERO}'s "
        "sense of {DEADLINE} says time is short; they can go down toward the reward "
        "or climb back up while they still safely can"
    ),
    "la_hum_back": (
        "{HERO} decides the find can wait for a safer day; they and {COMPANION} "
        "climb back up the rounded way and out to {ENTRANCE}, a little breathless "
        "but perfectly safe"
    ),
    "la_bell": (
        "{A2_GATE} holds; at the bottom waits {A2_FIND}, old and weathered, still "
        "faintly sounding as slow drips strike it"
    ),
    "la_bell2": (
        "marks are set into {A2_FIND}, {A2_DETAIL1}; nearby a dry ledge holds "
        "useful leftovers from an earlier visitor"
    ),
    "la_bell3": (
        "{HERO} records what {A2_DETAIL1} tells them; {A2_DETAIL2}, enough to help "
        "them climb back out the way they came"
    ),
    "la_bell4": (
        "with what {A2_FIND} revealed kept safe and the old gear put to use, {HERO} "
        "and {COMPANION} climb back to daylight; everyone will want to hear about "
        "{A2_PRIZE}"
    ),
    # ---- Route B entry + fork ------------------------------------------------
    "ra_drip": (
        "the second way, {ROUTE_B_CHAR}, follows {ROUTE_B_LURE} deeper; {HERO}'s "
        "light shows a trickle running on into the dark and the air turns cold"
    ),
    "ra_fork": (
        "the trickle reaches a split: one way {B1_SIGN} grows louder, the other way "
        "{B2_SIGN} drifts from a low side-passage"
    ),
    # ---- Route B, track 1 (open expanse, two prizes) -------------------------
    "ra_lake_way": (
        "following {B1_SIGN}, the floor turns to {B1_LANDMARK1} and the ceiling "
        "lifts away into a darkness {HERO}'s light cannot reach"
    ),
    "ra_lake2": (
        "the way gives onto {B1_LANDMARK2}; the sound is only {COMPANION} testing "
        "the cold edge with one paw"
    ),
    "ra_lake_app": (
        "the shelf narrows into {B1_GATE}; below waits {B1_ZONE}; {HERO} can climb "
        "carefully down toward it or back off before anyone slips"
    ),
    "ra_lake_back": (
        "{B1_GATE} is too risky; {HERO} coaxes {COMPANION} back along the shelf and "
        "they retrace the way to {ENTRANCE}, arriving safe, the greater find left "
        "for braver footing"
    ),
    "ra_descend": (
        "they pick their way down to {B1_ZONE}; here at the edge of it, something "
        "waits for a bold explorer"
    ),
    "ra_lakeshore": (
        "two chances appear: nearby rests {B1_OFFER1}, and further along "
        "{B1_OFFER2} beckons with its own promise"
    ),
    "ra_boat": (
        "{B1_OFFER1} proves usable; {HERO} {B1_PRIZE1_PREP} until it is ready to "
        "carry them onward across {B1_ZONE}"
    ),
    "ra_row": (
        "{HERO} takes {COMPANION} across {B1_ZONE} to a far side where daylight "
        "leaks in; they climb out having done {B1_PRIZE1}, likely the first in a "
        "lifetime to manage it"
    ),
    "ra_wade": (
        "{B1_OFFER2} lights up as {HERO} disturbs it, {B1_PRIZE2_PATH} leading "
        "toward a low, bright opening"
    ),
    "ra_islet": (
        "the path leads to {B1_PRIZE2}, a hidden spot under open sky; {HERO} takes "
        "a small keepsake and makes their way back into daylight, sworn to keep the "
        "place secret"
    ),
    # ---- Route B, track 2 (tight chamber, two prizes) ------------------------
    "ra_pool_way": (
        "the side-passage toward {B2_SIGN} is tight; {HERO} crouches under dripping "
        "ledges while {COMPANION} squeezes ahead toward {B2_LANDMARK1}"
    ),
    "ra_pool2": (
        "the way opens a little; {B2_LANDMARK2} runs along the floor toward a "
        "rounded chamber ahead"
    ),
    "ra_pool_app": (
        "the channel ends at {B2_GATE}; beyond it the light is bright, but "
        "{DEADLINE_SIGN} is filling the way behind them, so {HERO} must choose "
        "quickly to press on or hurry back"
    ),
    "ra_pool_back": (
        "{HERO} will not risk {B2_GATE} closing behind them; they and {COMPANION} "
        "hurry back and reach {ENTRANCE} just as {DEADLINE_SIGN} pours in, hearts "
        "thumping, entirely safe"
    ),
    "ra_pool_enter": (
        "through {B2_GATE} the chamber opens into {B2_ZONE}, its water so clear it "
        "looks like air, alive with small creatures"
    ),
    "ra_pool_chamber": (
        "{B2_ZONE} is a whole tiny world; in one corner {B2_OFFER1} stands out, and "
        "on the far side {B2_OFFER2} leads to a deeper, darker basin"
    ),
    "ra_starfish": (
        "{B2_OFFER1} is a rare thing; {HERO} {B2_PRIZE1_ACT}, leaving it exactly "
        "where it belongs and recording the wonder of it"
    ),
    "ra_starfish2": (
        "{HERO} backs out with a full record of {B2_PRIZE1}; the experts will not "
        "believe it until they see the proof, and {HERO} and {COMPANION} climb out "
        "grinning"
    ),
    "ra_pool_deep": (
        "{B2_OFFER2} leads to a darker basin where the water is deep; "
        "{B2_PRIZE2_FIND} gleams at the bottom, half-buried, catching the last of "
        "the light"
    ),
    "ra_pool_deep2": (
        "{HERO} lifts out {B2_PRIZE2}, the finest thing they have ever found, and "
        "carries it up into daylight like a trophy, {COMPANION} celebrating "
        "alongside"
    ),
    # ---- Route C entry + fork ------------------------------------------------
    "da_dark": (
        "the third way, {ROUTE_C_CHAR}, is the darkest; {ROUTE_C_LURE} turns out to "
        "be only a draft over stone; {HERO} keeps one hand on the wall and "
        "{COMPANION} close as they go down"
    ),
    "da_fork": (
        "the dark way forks: from one branch comes {C1_SIGN}, from the other "
        "{C2_SIGN}"
    ),
    # ---- Route C, track 1 (living hazard to cross, single prize) -------------
    "da_bat_way": (
        "{C1_SIGN} grows busier; the ceiling lifts and {HERO}'s light catches "
        "{C1_LANDMARK} above; {COMPANION} presses close, uncertain"
    ),
    "da_bat2": (
        "it is {C1_LANDMARK}, at rest in a great vaulted chamber; the air is warm "
        "and earthy, and {C1_ZONE_HINT} shows the way onward"
    ),
    "da_bat_app": (
        "{C1_ZONE_HINT} may be a way up and out, but reaching it means {C1_GATE}; "
        "{HERO} can go carefully on toward the reward or back away and leave things "
        "undisturbed"
    ),
    "da_bat_back": (
        "{HERO} will not risk disturbing what rests here; they and {COMPANION} ease "
        "back out and return along the dark way to {ENTRANCE}, dusty and awed and "
        "safe"
    ),
    "da_bat_enter": (
        "they cross carefully; nothing stirs; beyond lies {C1_CLIMB1}, a rough way "
        "up toward the light far above"
    ),
    "da_roost": (
        "{C1_CLIMB1} is steep but solid; partway up {HERO} finds {C1_CLIMB2}, proof "
        "that someone came this secret way long before"
    ),
    "da_roost2": (
        "the way narrows to {C1_CLIMB3}; light and fresh air pour down; {HERO} "
        "boosts {COMPANION} ahead and hauls up the last stretch"
    ),
    "da_skylight": (
        "they climb out through {C1_PRIZE}, high above {THRESHOLD}, blinking in the "
        "light; {HERO} has found a secret way in and out, and a discovery worth "
        "telling"
    ),
    # ---- Route C, track 2 (hidden store, two prizes) -------------------------
    "da_cache_way": (
        "{C2_SIGN} grows nearer; {HERO}'s light finds {C2_LANDMARK1} wedged into a "
        "side-cave, weathered and old"
    ),
    "da_cache2": (
        "{C2_LANDMARK1} gives way with a groan; behind it {C2_LANDMARK2} has been "
        "made by hand, a hiding place with shapes stacked in the shadows"
    ),
    "da_cache_app": (
        "it is {C2_ZONE}, forgotten for a long time; but {DEADLINE_SIGN} already "
        "glistens on the floor, so {HERO} can step in for a quick look or leave it "
        "for a drier day"
    ),
    "da_cache_back": (
        "{DEADLINE_SIGN} decides it; {HERO} marks the spot and hurries out with "
        "{COMPANION} ahead of the rising water, reaching {ENTRANCE} safe, the find "
        "saved for a better day"
    ),
    "da_cache_enter": (
        "inside, {C2_INNER}; most have crumbled, but two smaller boxes sit dry on a "
        "stone shelf, their lids stiff but whole"
    ),
    "da_cache_room": (
        "the first box holds {C2_OFFER1}; the second is heavy and rattles like "
        "{C2_OFFER2}; the water is creeping in, and {HERO} can only carry one out "
        "cleanly"
    ),
    "da_compass": (
        "{HERO} cleans {C2_OFFER1}; {C2_PRIZE1_ACT}, pointing the quickest way back "
        "toward {ENTRANCE} and the fading light"
    ),
    "da_compass2": (
        "{C2_OFFER1} leads them straight out to {ENTRANCE} just as {DEADLINE_SIGN} "
        "returns; {HERO} carries {C2_PRIZE1}, and a story everyone will beg to hear"
    ),
    "da_coins": (
        "the heavy box holds {C2_OFFER2}; {HERO} cannot count them now, but can "
        "carry the whole box out if they go at once"
    ),
    "da_coins2": (
        "{HERO} hauls the box up to daylight just ahead of {DEADLINE_SIGN}; the "
        "experts will study {C2_PRIZE2} and put {HERO}'s name to the find"
    ),
}

# node id -> new neutral ending title (function label)
TITLES: dict[str, str] = {
    "la_retreat_pool": "Turned Back at {A1_GATE}",
    "la_crystal_out": "{A1_PRIZE1}",
    "la_song": "{A1_PRIZE2}",
    "la_hum_back": "Turned Back at {A2_GATE}",
    "la_bell4": "{A2_PRIZE}",
    "ra_lake_back": "Turned Back at {B1_GATE}",
    "ra_row": "{B1_PRIZE1}",
    "ra_islet": "{B1_PRIZE2}",
    "ra_pool_back": "Turned Back at {B2_GATE}",
    "ra_starfish2": "{B2_PRIZE1}",
    "ra_pool_deep2": "{B2_PRIZE2}",
    "da_bat_back": "Turned Back at {C1_GATE}",
    "da_skylight": "{C1_PRIZE}",
    "da_cache_back": "Turned Back at {C2_GATE}",
    "da_compass2": "{C2_PRIZE1}",
    "da_coins2": "{C2_PRIZE2}",
}

FILL_RE = re.compile(r"^<<FILL role=(\w+) words=(\d+) beats='(.*)'>>$", re.DOTALL)


def main() -> int:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    nodes = data["nodes"]
    seen_beats: set[str] = set()
    seen_titles: set[str] = set()
    for node in nodes:
        nid = node["id"]
        body = node.get("body")
        if isinstance(body, str) and body.startswith("<<FILL"):
            m = FILL_RE.match(body)
            if m is None:
                raise SystemExit(f"body did not match FILL pattern: {nid}")
            role, words, _old = m.group(1), m.group(2), m.group(3)
            if nid not in BEATS:
                raise SystemExit(f"no neutral beat mapped for node: {nid}")
            new_beats = BEATS[nid]
            node["body"] = f"<<FILL role={role} words={words} beats='{new_beats}'>>"
            seen_beats.add(nid)
        ending = node.get("ending")
        if isinstance(ending, dict):
            if nid not in TITLES:
                raise SystemExit(f"no neutral title mapped for ending node: {nid}")
            ending["title"] = TITLES[nid]
            seen_titles.add(nid)

    missing_beats = set(BEATS) - seen_beats
    missing_titles = set(TITLES) - seen_titles
    if missing_beats:
        raise SystemExit(f"unused beat mappings: {missing_beats}")
    if missing_titles:
        raise SystemExit(f"unused title mappings: {missing_titles}")

    DST.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {DST}: {len(seen_beats)} beats, {len(seen_titles)} titles rewritten")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
