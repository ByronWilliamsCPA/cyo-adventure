"""The similarity vocabulary (diversity/similarity_vocab.py).

A1. This is the **second** theme vocabulary, deliberately separate from
``normalize._THEME_TAG_MAP``, and the separation is the whole point.

Why two vocabularies rather than one grown map
----------------------------------------------

``_THEME_TAG_MAP`` is the **echo** vocabulary. Its values are read back to a
child: ``generation/worker.py::_degraded_set_aside_decisions`` turns
``theme_signature(theme_brief)`` tags into ``SET_ASIDE`` phrases that reach the
kid surface. Growing that map therefore changes what a child is shown, which is a
content-safety change wearing the costume of a similarity fix. It stays frozen.

This vocabulary is never echoed. It exists only to make two signatures
comparable, so it can be as large and as abstract as the corpus needs.

Why the two sides did not overlap
---------------------------------

Measured over the committed catalog, **none** of the 132 curated
``metadata.themes`` is a value in the echo map, and the reason is a category
mismatch rather than a missing entry:

- the echo map's 12 values are **concrete subjects** a child names in a request
  (``dragon``, ``castle``, ``space``, ``pirate``, ...);
- the curated themes are **abstract authorial themes** (``courage``,
  ``friendship``, ``mystery``, ``perseverance``, ...).

A child asking for "a dragon story" and a book tagged ``courage, friendship``
describe different axes, so no amount of synonym-mapping inside one flat space
makes them intersect. This vocabulary therefore spans **both** axes and maps both
sides into the one space: a request premise contributes subject tags and whatever
theme tags its wording implies, and a story contributes both its curated themes
and its premise.

What it is not
--------------

Not a taxonomy anyone reads, and not a safety surface. Nothing here is shown to a
child, which is why it may safely normalise the three themes the echo floor
withholds (``lethal checkpoints``, ``lethal missteps``, ``the drowned descent``);
they are ordinary corpus signal to a distance measure and must never become echo
input. Keep the two maps in separate modules so a future edit cannot confuse
them.

Coverage against the real corpus is measured, not asserted: see
``scripts/measure_theme_coverage.py`` and A4/A5.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# The canonical similarity space
# ---------------------------------------------------------------------------

# Subject tags: what a story is *about*, concrete enough that a child names them.
# Deliberately a superset of the echo map's 12 values, so a request premise lands
# in this space too.
SUBJECT_TAGS: frozenset[str] = frozenset(
    {
        "animals",
        "castle",
        "cave",
        "city",
        "dinosaur",
        "dragon",
        "fire",
        "forest",
        "ice",
        "knight",
        "machines",
        "magic",
        "mountain",
        "music",
        "ocean",
        "pirate",
        "river",
        "science",
        "space",
        "sport",
        "train",
        "weather",
    }
)

# Theme tags: what a story is *about* in the authorial sense. Derived by grouping
# the 132 curated catalog themes into families rather than invented up front.
THEME_TAGS: frozenset[str] = frozenset(
    {
        "community",
        "courage",
        "danger",
        "discovery",
        "family",
        "friendship",
        "honesty",
        "kindness",
        "loss",
        "moral-cost",
        "mystery",
        "perseverance",
        "play",
        "survival",
        "uncanny",
    }
)

CANONICAL_TAGS: frozenset[str] = SUBJECT_TAGS | THEME_TAGS


# ---------------------------------------------------------------------------
# The mapping
# ---------------------------------------------------------------------------

# Every key is matched against a lowercased whole phrase (for a curated theme) or
# against lowercased content unigrams and bigrams (for free premise text), so a
# multi-word key only ever fires on that exact phrase.
#
# Grouping decisions worth contesting are noted inline. Where a curated theme
# carries two families at once ("grief and repair", "mastery and inheritance"),
# it maps to the one that dominates how a reader would describe the book, because
# the map is one-to-one; a one-to-many map is a later refinement and would need
# its own coverage measurement.
SIMILARITY_TAG_MAP: dict[str, str] = {
    # -- subject: creatures and fantasy ---------------------------------------
    "dragon": "dragon",
    "dragons": "dragon",
    "monster": "uncanny",
    "monsters": "uncanny",
    "the uncanny": "uncanny",
    "silence and awe": "uncanny",
    "ghost": "uncanny",
    "ghosts": "uncanny",
    "magic": "magic",
    "magical": "magic",
    "wizard": "magic",
    "witch": "magic",
    "spell": "magic",
    "fairy": "magic",
    "knight": "knight",
    "knights": "knight",
    "castle": "castle",
    "palace": "castle",
    "dinosaur": "dinosaur",
    "dinosaurs": "dinosaur",
    "fossil": "dinosaur",
    # -- subject: places ------------------------------------------------------
    "cave": "cave",
    "caves": "cave",
    "cavern": "cave",
    "forest": "forest",
    "woods": "forest",
    "jungle": "forest",
    "the wild": "forest",
    "nature": "forest",
    "garden": "forest",
    "ocean": "ocean",
    "sea": "ocean",
    "the sea": "ocean",
    "underwater": "ocean",
    "island": "ocean",
    "pirate": "pirate",
    "pirates": "pirate",
    "the canals": "river",
    "the river": "river",
    "river": "river",
    "rain": "weather",
    "weather": "weather",
    "storm": "weather",
    "snow": "ice",
    "winter": "ice",
    "the polar dark": "ice",
    "the signal under the ice": "ice",
    "ice": "ice",
    "mountain": "mountain",
    "the long climb up": "mountain",
    "the formal ascent trial": "mountain",
    "conduct carried up the wall": "mountain",
    "city": "city",
    "what a city hides to survive": "city",
    "night trains": "train",
    "train": "train",
    "trains": "train",
    # -- subject: making and knowing ------------------------------------------
    "robot": "machines",
    "robots": "machines",
    "invention": "machines",
    "machine": "machines",
    "clockwork": "machines",
    "space": "space",
    "rocket": "space",
    "planet": "space",
    "astronomy": "space",
    "science": "science",
    "experiment": "science",
    "fire": "fire",
    "music": "music",
    "song": "music",
    "singing": "music",
    "animal": "animals",
    "animals": "animals",
    "pet": "animals",
    "dog": "animals",
    "cat": "animals",
    "horse": "animals",
    "racing": "sport",
    "sportsmanship": "sport",
    "sport": "sport",
    "sports": "sport",
    # -- theme: courage and nerve ---------------------------------------------
    "courage": "courage",
    "brave": "courage",
    "bravery": "courage",
    "nerve": "courage",
    "disciplined nerve": "courage",
    "nerve and timing": "courage",
    "nerve over haste": "courage",
    "counted breath": "courage",
    "endurance": "courage",
    "hold or fall": "courage",
    "the price of a whole skin": "courage",
    # -- theme: friendship and belonging --------------------------------------
    "friendship": "friendship",
    "friend": "friendship",
    "friends": "friendship",
    "connection": "friendship",
    "belonging": "friendship",
    "reunion": "friendship",
    "rivalry into friendship": "friendship",
    "rivalry": "friendship",
    # -- theme: family and inheritance ----------------------------------------
    "family": "family",
    "siblings": "family",
    "sibling": "family",
    "brother": "family",
    "sister": "family",
    "heritage": "family",
    "inheritance": "family",
    "legacy": "family",
    "succession": "family",
    "pressure from home": "family",
    "coming-of-age": "family",
    "mastery and inheritance": "family",
    "compromise as inheritance": "family",
    # -- theme: kindness ------------------------------------------------------
    "kindness": "kindness",
    "kind": "kindness",
    "gentleness": "kindness",
    "helping": "kindness",
    "sharing": "kindness",
    "listening": "kindness",
    "compassion": "kindness",
    # -- theme: honesty and integrity -----------------------------------------
    "honesty": "honesty",
    "truth": "honesty",
    "integrity": "honesty",
    "fairness": "honesty",
    "the cost of the truth": "honesty",
    "records and the unrecorded": "honesty",
    "one line, one law": "honesty",
    "the count and the counted": "honesty",
    # -- theme: mystery and puzzle --------------------------------------------
    "mystery": "mystery",
    "mysteries": "mystery",
    "investigation": "mystery",
    "suspense": "mystery",
    "tension": "mystery",
    "puzzle": "mystery",
    "puzzles": "mystery",
    "codes": "mystery",
    "code": "mystery",
    "clue": "mystery",
    "clues": "mystery",
    "detective": "mystery",
    "secret": "mystery",
    "suspicion and trust": "mystery",
    "trust and paranoia": "mystery",
    "tradecraft": "mystery",
    "heist": "mystery",
    "the mirror labyrinth": "mystery",
    # -- theme: discovery and wonder ------------------------------------------
    "discovery": "discovery",
    "curiosity": "discovery",
    "exploration": "discovery",
    "explore": "discovery",
    "wonder": "discovery",
    "adventure": "discovery",
    "imagination": "discovery",
    "journey and passage": "discovery",
    "journey": "discovery",
    "the salt pilgrimage": "discovery",
    "history": "discovery",
    "astronomy and wonder": "discovery",
    "what a place keeps": "discovery",
    # -- theme: perseverance and craft ----------------------------------------
    "perseverance": "perseverance",
    "patience": "perseverance",
    "craft": "perseverance",
    "problem-solving": "perseverance",
    "talent and work": "perseverance",
    "recovery": "perseverance",
    "baking": "play",
    "practice": "perseverance",
    # -- theme: community and duty --------------------------------------------
    "community": "community",
    "teamwork": "community",
    "leadership": "community",
    "responsibility": "community",
    "diplomacy": "community",
    "loyalty": "community",
    "loyalty and honor": "community",
    "loyalty to a crew": "community",
    "the weight of command": "community",
    "crew": "community",
    # -- theme: loss and memory -----------------------------------------------
    "grief": "loss",
    "grief and repair": "loss",
    "letting go": "loss",
    "impermanence": "loss",
    "memory": "loss",
    "what we choose to forget": "loss",
    "the cost of the past": "loss",
    "sacrifice": "loss",
    "loss": "loss",
    # -- theme: survival and scarcity -----------------------------------------
    "survival": "survival",
    "isolation": "survival",
    "resource-management": "survival",
    "supplies and morale": "survival",
    "trade and scarcity": "survival",
    "the blockade run": "survival",
    "night work": "survival",
    # -- theme: moral cost ----------------------------------------------------
    "moral cost": "moral-cost",
    "divided loyalties": "moral-cost",
    "institutional abuse": "moral-cost",
    "institutions and complicity": "moral-cost",
    "political intrigue": "moral-cost",
    "the cost of the crossing": "moral-cost",
    "the cost of the hoard": "moral-cost",
    "the cost of the take": "moral-cost",
    "what holding costs": "moral-cost",
    # -- theme: danger --------------------------------------------------------
    # These three are the themes the ECHO floor withholds. They are ordinary
    # corpus signal here because this vocabulary is never read back to a child,
    # and normalising them to one tag keeps a lethal-gauntlet book measurably
    # similar to another lethal-gauntlet book. They must never be routed to an
    # echo surface; see the module docstring.
    "lethal checkpoints": "danger",
    "lethal missteps": "danger",
    "the drowned descent": "danger",
    "the ten assaults": "danger",
    "the road that unmakes the unprepared": "danger",
    "danger": "danger",
    # -- theme: play and celebration ------------------------------------------
    "play": "play",
    "celebration": "play",
    "festival": "play",
    "party": "play",
    "bedtime": "play",
    "game": "play",
    # -- mechanical tags, deliberately excluded -------------------------------
    # "state-gated locks" is a structural property of the graph, not a theme a
    # reader would name. It is dropped rather than mapped, so it cannot inflate
    # a similarity score between two books that merely share a topology.
}
