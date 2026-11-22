"""Build the WP-3.1 validation set shared by the continuity reader and plan reviewer.

Usage:
    uv run python scripts/build_validation_set.py            # write the JSON
    uv run python scripts/build_validation_set.py --check    # rebuild, compare
    uv run python scripts/build_validation_set.py --summary  # print the counts

Writes ``docs/planning/evidence/continuity-reader/validation-set.json``: one
``items`` list holding the continuity reader's labelled items (WP-3.2, owner
decision D6) and the plan reviewer's labelled plans (WP-3.7, D12), with one
split by book into a ``tuning`` and a ``held_out`` half, so neither stage is
tuned on the other's held-out half.

Every item is regenerated from committed sources: the frozen WP-1.3 answer key
(``known-defects.json``), the WP-0.4 findings files, the WP-1.6 second reads,
the 2026-11-20 structural-verification evidence, the two residual checks of
the five held-out post-fix books (2026-11-21, and 2026-11-22 after the fixes),
the WP-1.4, WP-1.6 and clean-plan blind plan manifests, the hand-written
post-fix plans and the WP-2.3 smoke runs. The findings files are prose, so
their entries are transcribed below as ``FINDINGS`` rows (and the 2026-11-22
minor residuals as ``RESIDUAL_MINORS`` rows); each row is checked against its
source file (the finding id and every node id must appear there) and against
the exact book revision it names (every node id must exist there, and the file
must hash to the pinned sha256).

The split is computed, not hand-picked: books seen in reviewer-prompt design
are forced into tuning, and the free books are assigned by an exhaustive
search that maximises held-out balance, ties broken by a per-book coin flip
seeded with ``SPLIT_SEED``. The split is also frozen: the search is re-run on
every build and must reproduce ``RECORDED_SPLIT``, so new items can never move
a book between halves as a side effect. The README beside the JSON documents
every field.

Reads no network and calls no model.

Exit codes: 0 written or up to date; 1 ``--check`` found drift or a source
failed verification; 2 a pinned git revision is not in this checkout.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import re
import subprocess  # nosec B404: fixed git argv, no shell, no untrusted input
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

REPO: Final = Path(__file__).resolve().parents[1]
OUT_FILE: Final = REPO / "docs/planning/evidence/continuity-reader/validation-set.json"

EV: Final = "docs/planning/evidence"
RETRO: Final = f"{EV}/story-plan-retro"
FRESH: Final = f"{EV}/fresh-corpus-2026-11-21"
SV: Final = f"{EV}/structural-verification-2026-11-20"
SMOKE: Final = f"{EV}/plan-generation-smoke-2026-11-21"
PILOT: Final = f"{EV}/plan-review-pilot-2026-11-21/README.md"
CR: Final = f"{EV}/continuity-reader"
R21: Final = f"{CR}/residuals-2026-11-21.md"
R22: Final = f"{CR}/residuals-2026-11-22.md"

# The full hash of commit 990054d ("docs(planning): record D12 and D6 as
# decided"), fixed before the split was first computed.
SPLIT_SEED: Final = "990054da2cc73d8b2b4c6b5744dc197288c40213"

TUNING: Final = "tuning"
HELD_OUT: Final = "held_out"

EXIT_OK: Final = 0
EXIT_FAIL: Final = 1
EXIT_NO_REVISION: Final = 2

JsonObj = dict[str, object]


class MissingRevisionError(RuntimeError):
    """A pinned git revision is not available here (for example a shallow clone)."""


class SourceError(RuntimeError):
    """A source did not verify: a hash, node id or anchor mismatch."""


# ---------------------------------------------------------------------------
# Split units: one per book (the skeleton slug for model fills of a skeleton)
# ---------------------------------------------------------------------------

UNIT_BANDS: Final[dict[str, str]] = {
    "the-hollow-lighthouse": "10-13",
    "the-lantern-keepers-list": "8-11",
    "the-orchard-signal": "10-13",
    "the-vanishing-orchard": "13-16",
    "the-sky-ship-stowaway": "8-11",
    "the-midnight-museum": "10-13",
    "the-signal-in-the-static": "13-16",
    "the-cave-of-echoes": "8-11",
    "the-mapmakers-island": "10-13",
    "the-thornwood-trial": "13-16",
    "the-clockwork-menagerie": "8-11",
    "the-clocktower-cipher": "10-13",
    "the-last-train-north": "16+",
    "the-locked-carousel": "8-11",
}

FORCED_TUNING: Final[dict[str, str]] = {
    "the-hollow-lighthouse": (
        "plan-review pilot 2026-11-21: blind plan x1 of the pre-fix book and "
        "the post-fix plan were shown to the reviewer prompt"
    ),
    "the-lantern-keepers-list": (
        "plan-review pilot: Run B fills B-lkl-new-1 (plan x3) and B-lkl-new-2 (plan x4)"
    ),
    "the-orchard-signal": (
        "plan-review pilot: Run B fill B-os-new-1 (plan x5); B-os-new-2 is a "
        "fill of the same skeleton carrying the same public-plant defect at the "
        "same node ids, so it goes with it"
    ),
    "the-vanishing-orchard": "plan-review pilot: post-fix plan",
}

# ---------------------------------------------------------------------------
# Pinned files
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Pinned:
    """One exact file: where it lives, the revision, and its sha256."""

    key: str
    unit: str
    path: str
    revision: str  # "git:<commit>" or "working-tree"
    sha256: str
    role: str


def _out(slug: str, rev: str, sha: str, role: str, kind: str = "filled") -> Pinned:
    """Pin ``out/<slug>.<kind>.json`` at a git revision."""
    key = f"{slug}@{rev}" if kind == "filled" else f"{slug}.plan@{rev}"
    return Pinned(key, slug, f"out/{slug}.{kind}.json", f"git:{rev}", sha, role)


def _fill(label: str, unit: str, sha: str) -> Pinned:
    """Pin a 2026-11-20 structural-verification fill (an evidence file)."""
    path = f"{SV}/runs/{label}/filled.json"
    return Pinned(label, unit, path, "working-tree", sha, "model fill 2026-11-20")


PRE: Final = "pre-fix (WP-0.4 input)"
POST: Final = "post-fix (WP-0.4 output)"
CAT: Final = "catalog book as read (WP-1.6); never fixed"
FIXED: Final = "fixed 2026-11-22 (residual check)"

BOOKS: Final[tuple[Pinned, ...]] = (
    _out(
        "the-sky-ship-stowaway",
        "60f1001",
        "bb215b407e972124f4f646c194916059bd96b0c76f00fb51006ea21d2b765d24",
        PRE,
    ),
    _out(
        "the-sky-ship-stowaway",
        "e9adcd1",
        "73a5c0d5d1976891b1f4e1f773344ac3698ac230e517d3c6b3144cb6da1f1441",
        POST,
    ),
    _out(
        "the-sky-ship-stowaway",
        "da5c467",
        "3621f39c156ad9fa64360889dd24a63dbdbf0e6030e48b2d3fa5158c71a1a66f",
        FIXED,
    ),
    _out(
        "the-hollow-lighthouse",
        "f3ba310",
        "acd8740b1ee7b42da44131c7bab2a4ad745eb40e93b2af2e5409a17a59d44430",
        "original fill before the 2026-11-20 revision",
    ),
    _out(
        "the-hollow-lighthouse",
        "15b14a1",
        "82817aa48b088b2d5a154d9d76589410c9af376401bde8449c984f9d06561183",
        PRE,
    ),
    _out(
        "the-hollow-lighthouse",
        "3e29e04",
        "31ed53bfd03edbe3fc2956072dde3368f3dc80407cb17cf2defbb63129aa3bbe",
        POST,
    ),
    _out(
        "the-midnight-museum",
        "ac61bd3",
        "39ee5a8c474b157f214a80497e63e47ff55405930996061bc33af7f75c556cd4",
        PRE,
    ),
    _out(
        "the-midnight-museum",
        "a0b61e9",
        "e466cce64d9fafbc8a37adc68c9d15efc47e17bf5b5bcfed62128c51917b0234",
        POST,
    ),
    _out(
        "the-midnight-museum",
        "fcd389e",
        "af54082e1ac3cc015ba8a1e3bd19b01f75f67890af7f0288082e383fbbe594f1",
        FIXED,
    ),
    _out(
        "the-signal-in-the-static",
        "aa5fd8c",
        "f0c851f90618cb43b7a7891e3e13cd6e8c3c9ac5c59ff337f6643be7cb1da5db",
        PRE,
    ),
    _out(
        "the-signal-in-the-static",
        "38f6a5a",
        "d701b7891ff2141196634800c84e0f2565c8df2d389dbd994f6ba495ebcc7cd8",
        POST,
    ),
    _out(
        "the-signal-in-the-static",
        "161e1e7",
        "2636ac09b73244731fc09cb4c4fa561b890a336df19093ca6b58be40b6bc36a7",
        FIXED,
    ),
    _out(
        "the-cave-of-echoes",
        "846d9fc",
        "178216418ccb8efaff396d405b7f2f40c8267167de7ee3118a7fbc16628e4d4f",
        "pre-fix control (parent of fix commit 6f78853)",
    ),
    _out(
        "the-cave-of-echoes",
        "1e2c853",
        "3a3606f4a0bee7fa42c399b18847d62260b3efd074cf69328087c53f13928273",
        POST,
    ),
    _out(
        "the-cave-of-echoes",
        "a6b399d",
        "a4a7c090391572dc58e3c31166f53fbe51a03aba18fa4a086a26b6f833fbc7fe",
        FIXED,
    ),
    _out(
        "the-mapmakers-island",
        "846d9fc",
        "b2d5a0dc960979c4f08bbe0bc770a9d965c6ec9ed9ada47fa968b866b2973d91",
        PRE,
    ),
    _out(
        "the-mapmakers-island",
        "16932c1",
        "2bb129096f67e9f45e1f9b19c2b2b63623c1fa492e1a5ca4c2d373ae65b1d4d1",
        POST,
    ),
    _out(
        "the-mapmakers-island",
        "c085d3c",
        "ce7e80a923c4090aa180a84a6dbfa141ef4468496b477cfe9058c4b364a3b853",
        FIXED,
    ),
    _out(
        "the-vanishing-orchard",
        "846d9fc",
        "75fa2655dffc880aa69704d27d85b9423fa0190bd6f34bc0c61752d5349d76e9",
        PRE,
    ),
    _out(
        "the-vanishing-orchard",
        "db7fb22",
        "46e02987d637f13acb6115f36807c820d324a0cd113cd1e2870516ee336e2716",
        POST,
    ),
    _out(
        "the-thornwood-trial",
        "f68c4f7",
        "cd3f45ad0d3d8075e57fdd203612a66ce59d65f1b2613c5ba7419caaf165476d",
        CAT,
    ),
    _out(
        "the-clockwork-menagerie",
        "f68c4f7",
        "f69e13d99a242a3478066522deb123f564cc556c1661ff14f824a8482274204e",
        CAT,
    ),
    _out(
        "the-clocktower-cipher",
        "dc71080",
        "2d476787f5e61104d2e8f87765820496488f2780d3c08cd19cfcc7516b305bb5",
        CAT,
    ),
    _fill(
        "B-lkl-new-1",
        "the-lantern-keepers-list",
        "4874b76254b5e21f5f859717c800cbf5387a4f4e90265f994b93bbb972f6fe50",
    ),
    _fill(
        "B-lkl-new-2",
        "the-lantern-keepers-list",
        "904b126589216729e132cd2a4b0d4325e004bbef651538c4a0beb1d99c6159ab",
    ),
    _fill(
        "B-os-new-1",
        "the-orchard-signal",
        "e86eb8a116868732c2b953c257873343606fd6cfb5de8fb4d5e4088e75c3dba7",
    ),
    _fill(
        "B-os-new-2",
        "the-orchard-signal",
        "d014a9e2c42bfb7de19beb7c38d18e8e32b31584bbf753b396f8cf97b644df09",
    ),
)

POSTFIX_PLANS: Final[tuple[Pinned, ...]] = (
    _out(
        "the-sky-ship-stowaway",
        "600536d",
        "d2e15b531b1e4b39e212f48bebea77d91fab000df07585a8307cd619d759279e",
        "hand-written plan, post-fix",
        "plan",
    ),
    _out(
        "the-hollow-lighthouse",
        "b016455",
        "0e92869d2721f423f960bd8ad92f98c88dc0bfbc405a38f161b499181690813e",
        "hand-written plan, post-fix",
        "plan",
    ),
    _out(
        "the-midnight-museum",
        "600536d",
        "1a13383f7c10e89566d321e8d88b0b0a0afe2cf8b6094e8cc20a099bcf543ee0",
        "hand-written plan, post-fix",
        "plan",
    ),
    _out(
        "the-signal-in-the-static",
        "b016455",
        "ea2d9b23285baeaf764a6d8510ef8b57125d0f5d62001593b375570cacb12089",
        "hand-written plan, post-fix",
        "plan",
    ),
    _out(
        "the-cave-of-echoes",
        "b016455",
        "0705d7a3395846ef14029ad0a8b1bb12df7549eed10ee58e4d2ee6ed33c65d0f",
        "hand-written plan, post-fix",
        "plan",
    ),
    _out(
        "the-mapmakers-island",
        "b016455",
        "55928627f839c275a41a64cca2d58ab94104d11a4ac29530424f9aa1ba6111d8",
        "hand-written plan, post-fix",
        "plan",
    ),
    _out(
        "the-vanishing-orchard",
        "b016455",
        "f9de5dd2e8fd8c15138ed4fb189d259384156f084083f7e8a626e7dee553b630",
        "hand-written plan, post-fix",
        "plan",
    ),
)

POSTFIX_OF: Final[dict[str, str]] = {
    "the-sky-ship-stowaway": "the-sky-ship-stowaway@e9adcd1",
    "the-hollow-lighthouse": "the-hollow-lighthouse@3e29e04",
    "the-midnight-museum": "the-midnight-museum@a0b61e9",
    "the-signal-in-the-static": "the-signal-in-the-static@38f6a5a",
    "the-cave-of-echoes": "the-cave-of-echoes@1e2c853",
    "the-mapmakers-island": "the-mapmakers-island@16932c1",
    "the-vanishing-orchard": "the-vanishing-orchard@db7fb22",
}

# The five held-out books fixed on 2026-11-22 after the 2026-11-21 residual
# check found defects in their WP-0.4 post-fix revisions (fix records:
# continuity-reader/fixes-2026-11-22-<slug>.md). These revisions, not the
# post-fix ones, are the clean books and the clean plans' books.
FIXED_OF: Final[dict[str, str]] = {
    "the-sky-ship-stowaway": "the-sky-ship-stowaway@da5c467",
    "the-midnight-museum": "the-midnight-museum@fcd389e",
    "the-signal-in-the-static": "the-signal-in-the-static@161e1e7",
    "the-cave-of-echoes": "the-cave-of-echoes@a6b399d",
    "the-mapmakers-island": "the-mapmakers-island@c085d3c",
}

# Post-fix books still clean under WP-0.4 ('Open continuity findings: 0').
WP04_CLEAN_UNITS: Final = ("the-hollow-lighthouse", "the-vanishing-orchard")

PREFIX_OF: Final[dict[str, str]] = {
    "the-sky-ship-stowaway": "the-sky-ship-stowaway@60f1001",
    "the-hollow-lighthouse": "the-hollow-lighthouse@15b14a1",
    "the-midnight-museum": "the-midnight-museum@ac61bd3",
    "the-signal-in-the-static": "the-signal-in-the-static@aa5fd8c",
    "the-cave-of-echoes": "the-cave-of-echoes@846d9fc",
    "the-mapmakers-island": "the-mapmakers-island@846d9fc",
    "the-vanishing-orchard": "the-vanishing-orchard@846d9fc",
}

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

CLASSES: Final[dict[str, str]] = {
    "u": "unestablished_fact_on_route",
    "s": "state_contradiction",
    "t": "two_backstories",
    "r": "repeated_reveal",
    "l": "location_or_physical_state",
    "tl": "timeline",
    "lo": "label_outcome_mismatch",
    "cp": "cross_payoff_reference",
    "o": "other",
}
SEVERITIES: Final[dict[str, str]] = {
    "B": "blocker",
    "S": "should-fix",
    "M": "minor",
    "U": "unrated",
}
SEVERITY_RANK: Final[dict[str, int]] = {
    "blocker": 0,
    "should-fix": 1,
    "leak": 2,
    "unearned": 3,
    "thin": 4,
    "minor": 5,
    "unrated": 6,
}

# ---------------------------------------------------------------------------
# Findings transcribed from the WP-0.4 findings files and WP-1.6 second reads
# ---------------------------------------------------------------------------

Row = tuple[str, str, str, str]  # (id, severity code, class code, nodes)


@dataclass(frozen=True, slots=True)
class FindingSource:
    """One findings file, the book revision it read, and its transcribed rows.

    Attributes:
        doc: The findings file, repository-relative.
        book: The :class:`Pinned` key of the book revision the reader read.
        prefix: Item-id prefix.
        class_from_source: Finding ids whose class the source states; every
            other class was assigned by this builder from the finding's text.
        severity_note: How the source states severity.
        rows: ``(id, severity, class, nodes)``; ``nodes`` is space-separated,
            primary node first. A node may be a choice id.
    """

    doc: str
    book: str
    prefix: str
    class_from_source: frozenset[str]
    severity_note: str
    rows: tuple[Row, ...]


def _ids(text: str) -> frozenset[str]:
    return frozenset(text.split())


_SKY = FindingSource(
    f"{RETRO}/findings-the-sky-ship-stowaway.md",
    "the-sky-ship-stowaway@60f1001",
    "SS",
    _ids("F3 F8"),
    "section headings Blockers / Should-fix / Minor",
    (
        ("F3", "B", "u", "b_steer1 b_steer_purr b_tell_doubt"),
        ("F8", "B", "s", "p_people_b"),
        ("F1", "S", "u", "n_secret p_people1"),
        ("F2", "S", "u", "e_neu_kite"),
        ("F4", "M", "u", "n_bridge"),
        ("F5", "M", "t", "p_people1 f_cabin_a f_cabin_b2"),
        ("F6", "M", "u", "b_steer_purr f_galley_a"),
        ("F7", "M", "u", "f_cabin1"),
    ),
)

_LH = FindingSource(
    f"{RETRO}/findings-the-hollow-lighthouse.md",
    "the-hollow-lighthouse@15b14a1",
    "LH",
    frozenset(),
    "M-ids under Minor; N-ids (added by the read) carry no severity, so 'unrated'. "
    "B1 to S4 are the KD-LH entries of known-defects.json and are not repeated",
    (
        ("M1", "M", "lo", "c_arch_gap c_c_arch_gap_1 c_gather"),
        ("M2", "M", "lo", "tn_gate_open c_tn_gate_open_1"),
        ("M3", "M", "l", "e_set_stair st_wind"),
        ("M4", "M", "u", "cm_light_true cm_letter_plea"),
        ("M5", "M", "lo", "tn_store_box c_tn_store_box_1"),
        ("M7", "M", "o", "e_win_signal"),
        ("N1", "U", "u", "cm_light_study"),
        ("N2", "U", "u", "cm_smug_photo"),
        ("N3", "U", "l", "b_gallery_fog n_light"),
        ("N4", "U", "t", "cm_smug cm_smug_hoard e_win_hoard e_win_ledger"),
        ("N5", "U", "u", "e_set_cellar"),
    ),
)

_MUSEUM = FindingSource(
    f"{RETRO}/findings-the-midnight-museum.md",
    "the-midnight-museum@ac61bd3",
    "MM",
    _ids("F1 F2 F3 F4 F5 F6 F7 F16"),
    "section headings Blocker / Should-fix / Minor",
    (
        (
            "F2",
            "B",
            "s",
            (
                "ro_records_guard v_share v_share_curator v_reveal2 "
                "e_set_dawn e_set_caught v_grab_run"
            ),
        ),
        ("F1", "S", "t", "k_stairs_up k_stairs_base k_cabinet k_display_careful"),
        ("F3", "S", "u", "v_map v_share"),
        (
            "F4",
            "S",
            "u",
            "e_win_donate e_neutral_evidence e_win_quiet_keeper v_share_secret",
        ),
        (
            "F5",
            "S",
            "s",
            "v_share v_letter_keep v_share_secret e_win_secret_kept v_share_museum",
        ),
        ("F6", "S", "u", "n_rotunda ro_pym"),
        ("F7", "S", "u", "e_win_lost_wing v_map_follow"),
        ("F16", "S", "u", "k_display_careful"),
        ("F8", "M", "l", "e_set_caught v_grab_run"),
        ("F9", "M", "u", "n_vault v_share v_share_curator"),
        ("F10", "M", "o", "v_letter"),
        ("F11", "M", "t", "n_open v_map"),
        ("F12", "M", "l", "n_key k_stairs"),
        ("F13", "M", "l", "ci_clock_pendulum ci_clock"),
        ("F14", "M", "l", "c_archive_chalk"),
        ("F15", "M", "l", "a_gems_hide a_gems_corridor"),
        ("F17", "M", "o", "c_archive1"),
        ("F18", "M", "l", "v_share_curator"),
        ("F19", "M", "l", "v_share_museum v_share"),
    ),
)

_SIGNAL = FindingSource(
    f"{RETRO}/findings-the-signal-in-the-static.md",
    "the-signal-in-the-static@aa5fd8c",
    "SG",
    frozenset(),
    "section headings Blockers / Should-fix / Minor",
    (
        ("B1", "B", "u", "f_he_act mm_count_tide"),
        ("B2", "B", "u", "e_he_safe"),
        ("B3", "B", "tl", "e_re_photo"),
        (
            "B4",
            "B",
            "u",
            (
                "m_numbers_1 m_num_cipher m_num_cracked c_m_numbers_1_1 "
                "c_m_num_cipher_1 r_no_trunk"
            ),
        ),
        ("B5", "B", "t", "n_b2_under e_re_found"),
        ("S1", "S", "u", "e_re_answer mm_list_daughter"),
        ("S2", "S", "u", "f_he_cg"),
        ("S3", "S", "u", "mm_listener_1"),
        ("S4", "S", "l", "mm_count_1"),
        ("S5", "S", "u", "mm_count_tide r_re_lane"),
        ("S6", "S", "o", "e_st_wait"),
        ("S7", "S", "u", "e_st_record"),
        ("S8", "S", "t", "n_b3_choice"),
        ("S9", "S", "t", "mm_list_daughter e_re_found"),
        ("M1", "M", "o", "n_open"),
        ("M2", "M", "o", "r_coord_base_out r_coord_beat"),
        ("M3", "M", "tl", "e_who_warn"),
        ("M4", "M", "o", "e_he_complete"),
        ("M5", "M", "o", "m_numbers_1 f_he_act"),
    ),
)

_CAVE = FindingSource(
    f"{RETRO}/findings-the-cave-of-echoes.md",
    "the-cave-of-echoes@846d9fc",
    "CE",
    frozenset(),
    "source column Sev: high mapped to blocker, med to should-fix, low to minor",
    (
        ("1", "B", "l", "ra_lake2 ra_fork ra_lake_way"),
        ("2", "B", "l", "da_compass da_compass2"),
        ("3", "B", "u", "da_cache_back"),
        ("4", "S", "t", "da_roost da_skylight"),
        ("5", "S", "l", "la_bell3 la_bell4"),
        ("6", "S", "u", "la_song da_bat_back"),
        ("7", "S", "u", "ra_starfish ra_starfish2"),
        ("8", "M", "u", "ra_islet"),
        ("9", "M", "u", "la_bell3 ra_starfish n_start"),
        ("10", "M", "l", "la_crystal_take"),
    ),
)

_ORCHARD = FindingSource(
    f"{RETRO}/findings-the-vanishing-orchard.md",
    "the-vanishing-orchard@846d9fc",
    "VO",
    frozenset(),
    "source column Sev: B blocker, S should-fix, M minor",
    (
        ("1", "B", "t", "pho_conv cel_t_p3"),
        ("2", "B", "t", "pho_t_p1"),
        ("3", "B", "t", "b2t_p1"),
        ("4", "B", "t", "e_b2tb b2t_p1"),
        ("5", "B", "t", "kee_t_p1 n_open"),
        ("6", "B", "t", "b1at_p1"),
        ("7", "M", "t", "b1at_p3 b2tt_p2"),
        ("8", "M", "t", "fin_one_1"),
        ("9", "S", "u", "b1bt_p1 n_b2"),
        ("10", "B", "l", "kee_b_p1 kee_entry"),
        ("11", "S", "u", "kee_conv"),
        ("12", "B", "l", "kee_t_p3 n_b3"),
        ("13", "B", "t", "kee_a_p3 rec_b_p4 n_b1"),
        ("14", "B", "tl", "n_open cel_a_p1 rec_t_p4 pho_clue e_cel_a e_cel_b"),
        ("15", "S", "tl", "e_b2ta"),
        ("16", "M", "tl", "n_b5 fin_trade_2"),
        ("17", "S", "tl", "kee_t_p4"),
        ("18", "B", "u", "n_b1"),
        (
            "19",
            "S",
            "u",
            (
                "pho_a_p3 pho_b_p1 pho_b_p4 pho_t_p3 e_pho_a e_pho_b "
                "cel_b_p2 cel_t_p1 n_b1"
            ),
        ),
        ("20", "S", "u", "cel_a_p3 cel_a_p4 cel_t_p1"),
        ("21", "S", "u", "cel_b_p1 cel_b_p2 cel_b_p3 cel_b_p4"),
        ("22", "M", "u", "cel_entry cel_clue"),
        ("23", "S", "u", "e_cel_a e_cel_b"),
        ("24", "S", "u", "rec_clue"),
        ("25", "S", "u", "rec_conv rec_clue"),
        ("26", "S", "u", "kee_a_p1 kee_b_p2"),
        ("27", "S", "u", "pho_t_p1 pho_t_p4 pho_clue"),
        ("28", "S", "u", "b1a_p3"),
        ("29", "S", "u", "b1bt_p2"),
        ("30", "S", "u", "b2k_p1 b2k_d1 b2k_m e_b2ka e_b2kb b2kt_p2"),
        ("31", "S", "u", "e_b2ka n_b3"),
        ("32", "M", "l", "b1ct_p3 n_b3"),
        ("33", "S", "u", "b3u_p1 b3u_p2"),
        ("34", "B", "u", "n_b4"),
        ("35", "B", "u", "fin_all_1 fin_all_2"),
        ("36", "B", "u", "fin_share_1 fin_share_2 e_share_lost"),
        ("37", "S", "u", "n_b5 n_b5_2"),
        ("38", "M", "o", "n_b5_2"),
        ("39", "M", "o", "e_all_grandmother cel_t_p3"),
        ("40", "M", "u", "e_one_hesitate e_one_saved"),
        ("41", "M", "u", "e_trade_photo"),
        ("42", "M", "u", "kee_conv"),
    ),
)

_ALDER = "S", "u"  # every row of the "Alder named ..." section of the island file

_ISLAND = FindingSource(
    f"{RETRO}/findings-the-mapmakers-island.md",
    "the-mapmakers-island@846d9fc",
    "MI",
    frozenset(),
    "per finding '(blocker)' etc., or the section heading ('Alder named ...' is "
    "should-fix, 'Smaller unestablished references' is minor)",
    (
        ("1", "B", "u", "ch_pencil ch_table cv_glitter cove_rise mg_ruin cf_hollow"),
        ("2", "B", "u", "summit_signal"),
        ("3", "B", "u", "meet_boat race_down"),
        ("4", "S", "u", "e_rescue_pup cv_warm cv_pup"),
        ("5", "B", "l", "e_rescue_turtle"),
        ("6", "B", "s", "e_ch_clean"),
        ("7", "B", "t", "tf_cargo cove_starrock e_tf_bell"),
        ("8", "B", "t", "camp_journal ch_farshore camp_chart"),
        ("9", "S", "t", "ch_ink camp_journal"),
        ("10", "S", "l", "mg_readmarks cf_notes tf_bottle L_camp"),
        ("11", "M", "tl", "summit_signal n_open"),
        ("12", "M", "l", "tf_deck c_tf_deck_1"),
        ("13", *_ALDER, "mg_dam e_mg_stake"),
        ("14", *_ALDER, "mg_blind e_mg_tidetable"),
        ("15", *_ALDER, "mg_ruin"),
        ("16", *_ALDER, "cf_fallpool e_cf_gauge"),
        ("17", *_ALDER, "cf_dellcarve e_cf_carve"),
        ("18", *_ALDER, "cf_treetop"),
        ("19", *_ALDER, "cf_shrine"),
        ("20", *_ALDER, "cv_ochre"),
        ("21", *_ALDER, "tw_tube e_tw_draft"),
        ("22", *_ALDER, "tw_wallcharts e_tw_charts"),
        ("23", *_ALDER, "tw_seachest e_tw_drawing"),
        ("24", *_ALDER, "tw_cache e_tw_cache"),
        ("25", *_ALDER, "tw_viewdial e_tw_dial"),
        ("26", *_ALDER, "tw_fuelstore e_tw_note"),
        ("27", *_ALDER, "cove_seacave e_cove_tin"),
        ("28", *_ALDER, "cove_rockpool"),
        ("29", *_ALDER, "fresh_cairn e_fresh_cairn"),
        ("30", *_ALDER, "camp_ascent5 L_camp"),
        ("31", *_ALDER, "camp_chart"),
        ("32", "S", "u", "cf_bench"),
        ("33", "S", "u", "cove_ridge"),
        ("34", "S", "u", "tw_toridge"),
        ("35", "S", "u", "cf_campapproach tw_supplies"),
        ("36", "M", "u", "tw_salvage"),
        ("37", "M", "u", "tw_top"),
        ("38", "M", "u", "cv_tohigh"),
        ("39", "S", "u", "L_fresh cv_ochre"),
        ("40", "M", "u", "cf_upper"),
        ("41", "M", "u", "e_ascent_daunted"),
        ("42", "M", "u", "tw_cellar"),
        ("43", "B", "u", "L_summit summit_signal L_camp camp_trunk"),
        ("44", "S", "u", "camp_ready"),
        ("45", "S", "u", "ch_farshore ch_ink"),
        ("46", "B", "u", "ch_sightings tw_salvage"),
        ("47", "B", "u", "ch_sign"),
        ("48", "M", "u", "e_ch_survey tw_wallcharts"),
        ("49", "M", "u", "ship_turns"),
        ("50", "M", "u", "race_down"),
        ("51", "M", "u", "cv_deepglow"),
        ("52", "M", "u", "cv_enter"),
        ("53", "M", "u", "mg_seep"),
        ("54", "M", "u", "cove_rise"),
        ("55", "M", "t", "tf_cliffgap camp_chart"),
        ("56", "M", "u", "cf_shelf cf_ledge"),
    ),
)

_SECOND_READ_ALL = "every class is the source's own (its Class column)"

_THORNWOOD = FindingSource(
    f"{FRESH}/second-read-the-thornwood-trial.md",
    "the-thornwood-trial@f68c4f7",
    "TT",
    _ids(
        "B1 B2 B3 B4 S1 S2 S3 S4 S5 S6 S7 S8 S9 S10 S11 M1 M2 M3 M4 M5 M6 M7 M8 M9 M10"
    ),
    "section headings Blockers / Should-fix / Minor; " + _SECOND_READ_ALL,
    (
        ("B1", "B", "tl", "b_maze_2"),
        ("B2", "B", "tl", "rc_maze_1_2"),
        ("B3", "B", "tl", "x_mazeh_1_2"),
        ("B4", "B", "u", "e_ridge2_49"),
        ("S1", "S", "u", "e_maze_5_0"),
        ("S2", "S", "u", "h_council"),
        ("S3", "S", "u", "e_win_wild"),
        ("S4", "S", "o", "h_council"),
        ("S5", "S", "l", "h_maze"),
        ("S6", "S", "l", "f_dusk"),
        ("S7", "S", "tl", "f_wild"),
        ("S8", "S", "lo", "x_maze5_10_1"),
        ("S9", "S", "lo", "x_maze1_2_1"),
        ("S10", "S", "lo", "e_council_5_0"),
        ("S11", "S", "tl", "x_grove1_13_2"),
        ("M1", "M", "lo", "e_council5_44"),
        ("M2", "M", "lo", "e_maze_1_0"),
        ("M3", "M", "lo", "e_maze_3_0"),
        ("M4", "M", "l", "rc_ridge_2_3"),
        ("M5", "M", "l", "e_warren_3_0"),
        ("M6", "M", "l", "e_maze1_3"),
        ("M7", "M", "l", "b_grove_3"),
        ("M8", "M", "tl", "e_gate_late"),
        ("M9", "M", "lo", "f_wild"),
        ("M10", "M", "lo", "x_mazeh_1_1"),
    ),
)

_CLOCKWORK_ROWS: Final[tuple[Row, ...]] = (
    ("B1", "B", "tl", "av_x0 n_open"),
    ("B2", "B", "l", "av_conv av_a5"),
    ("B3", "B", "l", "ds_conv ds_a5"),
    ("B4", "B", "l", "cg_conv cg_a5 cg_b4"),
    ("B5", "B", "u", "av_conv3 av_b1 av_b4"),
    ("B6", "B", "o", "fh_fx1 n_spring fh_dawn_o2"),
    ("B7", "B", "l", "fh_sec1 n_hub"),
    ("B8", "B", "l", "fh_sec_c1 n_key fh_sec_c2"),
    ("B9", "B", "cp", "e_neu_caretaker fh_sec_j1"),
    ("B10", "B", "l", "fh_fx_fly cg_a3"),
    ("B11", "B", "o", "e_win_most fh_rw_b_ok"),
    ("S1", "S", "u", "ds_b3"),
    ("S2", "S", "u", "av_b4"),
    ("S3", "S", "u", "sv_b4"),
    ("S4", "S", "u", "ds_b4"),
    ("S5", "S", "u", "sv_a5 ds_a5 cg_a5 av_conv sv_conv cg_conv"),
    ("S6", "S", "l", "sv_conv sv_a5 sv_b4"),
    ("S7", "S", "u", "sv_conv3 ds_conv3 cg_conv3"),
    ("S8", "S", "u", "n_key"),
    ("S9", "S", "r", "sv_a1 sv_a2 sv_rec sv_risk"),
    ("S10", "S", "u", "s_c3"),
    ("S11", "S", "u", "n_shop"),
    ("S12", "S", "l", "n_shop s_a3 p_a3"),
    ("S13", "S", "u", "n_hub n_shop fh_dawn_w2"),
    ("S14", "S", "u", "fh_sec1 n_hub n_shop"),
    ("S15", "S", "u", "e_win_eleph fh_fx_eleph"),
    ("S16", "S", "tl", "e_neu_mouse n_hub av_conv2"),
    ("M1", "M", "tl", "p_c1 n_shop"),
    ("M2", "M", "lo", "s_a1 c_s_a1 s_a2"),
    ("M3", "M", "lo", "s_b1 c_s_b1 s_b2"),
    ("M4", "M", "lo", "p_a1 c_p_a1 p_a2"),
    ("M5", "M", "lo", "p_b1 c_p_b1 p_b2"),
    ("M6", "M", "lo", "fh_sec1 c_sec_m fh_sec_m1"),
    ("M7", "M", "l", "n_spring k_c3 k_b3"),
    ("M8", "M", "tl", "fh_rw1 e_set_spring fh_dawn_s1"),
    ("M9", "M", "tl", "fh_sec_j1 n_start n_shop"),
    ("M10", "M", "l", "av_conv av_a4 av_a5 cg_conv"),
    ("M11", "M", "l", "e_set_av"),
    ("M12", "M", "l", "e_set_ds"),
    ("M13", "M", "l", "e_set_sv"),
    ("M14", "M", "l", "e_set_key k_c1"),
    ("M15", "M", "l", "fh_dawn_s1 n_hub"),
    ("M16", "M", "l", "fh_fx_whale"),
    ("M17", "M", "o", "e_win_mouse fh_sec_m2"),
    ("M18", "M", "o", "e_set_cabinet n_shop"),
    ("M19", "M", "t", "fh_sec_j2 k_b1 k_b2"),
    ("M20", "M", "t", "fh_sec_j2 fh_sec_c3"),
    ("M21", "M", "u", "e_set_shop p_c1"),
)

_CLOCKWORK = FindingSource(
    f"{FRESH}/second-read-the-clockwork-menagerie.md",
    "the-clockwork-menagerie@f68c4f7",
    "CM",
    frozenset(r[0] for r in _CLOCKWORK_ROWS),
    "section headings Blockers / Should-fix / Minor; " + _SECOND_READ_ALL,
    _CLOCKWORK_ROWS,
)

_CLOCKTOWER_ROWS: Final[tuple[Row, ...]] = (
    ("B1", "B", "u", "n_clockface n_setcorrect n_backpanel"),
    ("B2", "B", "u", "n_setjam c_jam_oil n_vault"),
    ("B3", "B", "s", "n_end_stuck c_jam_stuck"),
    ("B4", "B", "u", "n_stairs n_backpanel n_end_caught"),
    ("B5", "B", "u", "n_stairs n_keeper_story"),
    ("B6", "B", "l", "n_end_library n_open n_end_hero"),
    ("S1", "S", "u", "n_study n_inside n_basement n_setcorrect n_vault"),
    ("S2", "S", "u", "n_inside n_study"),
    ("S3", "S", "u", "n_backpanel n_end_library"),
    ("S4", "S", "u", "n_setjam n_end_stuck"),
    ("S5", "S", "u", "n_keeper_story"),
    ("S6", "S", "u", "n_vault n_setjam c_jam_oil"),
    ("S7", "S", "u", "n_end_keepsake n_vault c_vault_keep"),
    ("S8", "S", "u", "n_end_timeout n_open"),
    ("M1", "M", "r", "n_clockface n_inside n_keeper_story"),
    ("M2", "M", "l", "n_inside n_window"),
    ("M3", "M", "o", "n_inside c_note_inside n_keeper_story"),
    ("M4", "M", "u", "n_window n_open n_note"),
    ("M5", "M", "lo", "c_keeper_enter n_inside"),
    ("M6", "M", "lo", "c_vault_share n_end_hero"),
    ("M7", "M", "lo", "c_vault_grab n_end_caught"),
    ("M8", "M", "o", "c_panel_secret n_backpanel"),
    ("M9", "M", "s", "n_setjam n_pendulum"),
    ("M10", "M", "l", "n_end_giveup n_pendulum"),
    ("M11", "M", "tl", "n_end_giveup n_inside"),
    ("M12", "M", "l", "n_clockface n_pendulum"),
    ("M13", "M", "l", "n_end_library n_inside"),
    ("M14", "M", "o", "n_keeper_story n_stairs"),
)

_CLOCKTOWER = FindingSource(
    f"{FRESH}/second-read-the-clocktower-cipher.md",
    "the-clocktower-cipher@dc71080",
    "CC",
    frozenset(r[0] for r in _CLOCKTOWER_ROWS),
    "section headings Blockers / Should-fix / Minor; " + _SECOND_READ_ALL,
    _CLOCKTOWER_ROWS,
)

# ---------------------------------------------------------------------------
# Residual check of the five held-out post-fix books (2026-11-21)
# ---------------------------------------------------------------------------
#
# The ten blind c/d plans of the WP-0.4 post-fix revisions raised suspects that
# an independent check verified with StoryEngine witnesses. Every verdict
# "real: blocker / should-fix / minor" is transcribed here as a defect of the
# post-fix revision. The nine "not a defect" verdicts (SS-4, SG-3, MI-3, MI-4,
# MI-6, CE-3, MM-1, MM-2, MM-3) are left out: the set has no item kind for a
# verified clean judgement at a node (``node_assertion`` is defect-only).

_R21_PREFIX: Final = "R1121"
_R21_SEVERITY: Final = (
    "verdict column 'real: blocker', 'real: should-fix' or 'real: minor'; "
    "'not a defect' verdicts are left out"
)


def _residual_source(book: str, rows: tuple[Row, ...]) -> FindingSource:
    """Return the 2026-11-21 residual rows of one post-fix book."""
    return FindingSource(
        R21,
        book,
        _R21_PREFIX,
        frozenset(r[0] for r in rows),  # the report states every class
        _R21_SEVERITY,
        rows,
    )


_R21_SKY = _residual_source(
    "the-sky-ship-stowaway@e9adcd1",
    (
        ("SS-1", "M", "u", "e_win_discovery"),
        ("SS-2", "M", "u", "b_free1"),
        ("SS-3", "S", "s", "c_nest_a f_rig_a"),
    ),
)

_R21_SIGNAL = _residual_source(
    "the-signal-in-the-static@38f6a5a",
    (
        ("SG-1", "M", "u", "m_numbers_1"),
        ("SG-2", "B", "u", "m_num_countdown n_b2"),
        ("SG-4", "S", "t", "m_who_article f_he_colleague e_he_dead"),
        ("SG-5", "S", "u", "e_he_complete"),
        ("SG-6", "M", "u", "r_re_hut"),
    ),
)

_R21_ISLAND = _residual_source(
    "the-mapmakers-island@16932c1",
    (
        (
            "MI-1",
            "M",
            "u",
            (
                "tf_enter mg_readmarks cv_ochre e_cv_paintings cove_starrock "
                "e_star_map ch_double e_ch_alder_name e_ch_spare signal_flash "
                "mg_ruin e_ch_clean e_cv_fish e_tf_bell"
            ),
        ),
        (
            "MI-2",
            "S",
            "u",
            (
                "e_tf_stranded camp_ascent4 e_mg_canoe e_cf_slip e_tw_charts "
                "e_mg_chick e_cf_canopy e_cv_raft"
            ),
        ),
        ("MI-5", "M", "u", "camp_journal"),
        ("MI-7", "M", "u", "cv_upflow cv_glowworm"),
        ("MI-8", "M", "u", "cv_deepglow"),
        ("MI-9", "S", "lo", "tw_brazier c_tw_brazier_2 e_tw_nofuel"),
        ("MI-10", "S", "s", "ch_pencil e_ch_dusk"),
        ("MI-11", "S", "u", "ch_gather summit_signal"),
    ),
)

_R21_CAVE = _residual_source(
    "the-cave-of-echoes@1e2c853",
    (
        ("CE-1", "M", "u", "da_skylight da_coins2"),
        ("CE-2", "M", "u", "ra_starfish2"),
        ("CE-4", "S", "lo", "da_compass c_da_out da_compass2"),
    ),
)

_R21_MUSEUM = _residual_source(
    "the-midnight-museum@a0b61e9",
    (("MM-4", "M", "u", "k_study c_base_study e_win_hero_curator"),),
)

FINDINGS: Final[tuple[FindingSource, ...]] = (
    _SKY,
    _LH,
    _MUSEUM,
    _SIGNAL,
    _CAVE,
    _ORCHARD,
    _ISLAND,
    _THORNWOOD,
    _CLOCKWORK,
    _CLOCKTOWER,
    _R21_SKY,
    _R21_SIGNAL,
    _R21_ISLAND,
    _R21_CAVE,
    _R21_MUSEUM,
)

# Run A merge openings (structural-verification-2026-11-20.md section 3).
# (fill label, skeleton, hand seam count, detector seam count)
MERGE_COUNTS: Final[tuple[tuple[str, str, int, int], ...]] = (
    ("A-ltn-old-1", "the-last-train-north", 17, 12),
    ("A-ltn-old-2", "the-last-train-north", 3, 0),
    ("A-ltn-old-3", "the-last-train-north", 12, 5),
    ("A-ltn-new-1", "the-last-train-north", 1, 2),
    ("A-ltn-new-2", "the-last-train-north", 9, 1),
    ("A-ltn-new-3", "the-last-train-north", 15, 2),
    ("A-ltn-new-chunked", "the-last-train-north", 14, 12),
    ("A-cm-old-1", "the-clockwork-menagerie", 8, 8),
    ("A-cm-old-2", "the-clockwork-menagerie", 8, 8),
    ("A-cm-old-3", "the-clockwork-menagerie", 8, 8),
    ("A-cm-new-1", "the-clockwork-menagerie", 3, 3),
    ("A-cm-new-2", "the-clockwork-menagerie", 0, 0),
    ("A-cm-new-3", "the-clockwork-menagerie", 1, 1),
)
MERGE_NODE_TOTALS: Final[dict[str, int]] = {
    "the-last-train-north": 21,
    "the-clockwork-menagerie": 12,
}

# Known residuals of a clean book revision, keyed by its BOOK_BY_KEY key: a
# verified defect left unfixed. A reader flag or a plan-review reject citing
# one is a true positive, not a false flag; it is not a reader defect item and
# does not turn the book's plans into ``reject``. The orchard pilot finding is
# one a post-fix control still carries (pilot README); the 2026-11-22 minors
# below are added by known_residuals().
KNOWN_RESIDUALS: Final[dict[str, list[JsonObj]]] = {
    "the-vanishing-orchard@db7fb22": [
        {
            "nodes": ["b1a_dec", "e_b1a"],
            "choice": "c_b1a_dec_2",
            "defect_class": "label_outcome_mismatch",
            "source": PILOT,
            "note": (
                "'Pull back from it.' leads to an ending where Rowan held on too "
                "long; found by the plan-review pilot, missed by the WP-0.4 read, "
                "verified against the book. Not fixed. A reader flag here is a "
                "true positive, not a false flag."
            ),
        }
    ],
}

# The 2026-11-22 check of the fixed revisions found them clean (no blocker, no
# should-fix) with nine minor residuals, left unfixed. They are verified the
# same way as FINDINGS rows (id and nodes in the source, nodes in the pinned
# fixed revision) and become known residuals, not reader defect items. Cave of
# Echoes and Sky-Ship have none.
_R22_NOTE: Final = (
    "minor residual found by the 2026-11-22 check of the fixed book and left "
    "unfixed. A reader flag or plan-review reject citing it is a true "
    "positive, not a false flag."
)

RESIDUAL_MINORS: Final[tuple[FindingSource, ...]] = (
    FindingSource(
        R22,
        "the-signal-in-the-static@161e1e7",
        "",
        _ids("SG-7 SG-8"),
        "bottom line per book: every residual is minor",
        (
            ("SG-7", "M", "u", "r_relay_beat"),
            ("SG-8", "M", "u", "r_relay_1 r_relay_beat"),
        ),
    ),
    FindingSource(
        R22,
        "the-midnight-museum@fcd389e",
        "",
        _ids("MM-5"),
        "bottom line per book: every residual is minor",
        (("MM-5", "M", "u", "e_win_mystery_solved"),),
    ),
    FindingSource(
        R22,
        "the-mapmakers-island@c085d3c",
        "",
        _ids("MI-12 MI-13 MI-14 MI-15 MI-16 MI-17"),
        "bottom line per book: every residual is minor",
        (
            ("MI-12", "M", "u", "e_tw_log"),
            ("MI-13", "M", "u", "cf_bench"),
            ("MI-14", "M", "u", "tf_gap"),
            ("MI-15", "M", "u", "tf_gully c_tf_gully_1"),
            ("MI-16", "M", "u", "L_cove c_L_cove_1"),
            ("MI-17", "M", "u", "mg_blind"),
        ),
    ),
)

# The split as first computed (before the 2026-11-22 sources were added). It
# is frozen: tuning prompts are written against it, so a book moving halves
# would leak held-out data into tuning. build() re-runs the search and fails
# if it would move any unit; a new split must be an explicit owner decision.
RECORDED_SPLIT: Final[dict[str, str]] = {
    "the-hollow-lighthouse": TUNING,
    "the-lantern-keepers-list": TUNING,
    "the-locked-carousel": TUNING,
    "the-orchard-signal": TUNING,
    "the-thornwood-trial": TUNING,
    "the-vanishing-orchard": TUNING,
    "the-cave-of-echoes": HELD_OUT,
    "the-clocktower-cipher": HELD_OUT,
    "the-clockwork-menagerie": HELD_OUT,
    "the-last-train-north": HELD_OUT,
    "the-mapmakers-island": HELD_OUT,
    "the-midnight-museum": HELD_OUT,
    "the-signal-in-the-static": HELD_OUT,
    "the-sky-ship-stowaway": HELD_OUT,
}

# ---------------------------------------------------------------------------
# File access
# ---------------------------------------------------------------------------

_CACHE: dict[str, bytes] = {}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git_blob(revision: str, path: str) -> bytes:
    """Return ``git show <revision>:<path>``.

    Raises:
        MissingRevisionError: The object is not in this checkout.
    """
    # #ASSUME: external-resource: git is on PATH and REPO is a checkout.
    # #VERIFY: a failed lookup raises MissingRevisionError so callers (the
    # unit test) can tell a shallow clone apart from a wrong hash.
    proc = subprocess.run(  # nosec B603, B607: fixed argv, no shell
        ["git", "-C", str(REPO), "show", f"{revision}:{path}"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        msg = f"git object {revision}:{path} is not available in this checkout"
        raise MissingRevisionError(msg)
    return proc.stdout


def read_pinned(pin: Pinned) -> bytes:
    """Return the bytes of a pinned file, verified against its sha256.

    The working-tree file is used when it still has the pinned hash, so a
    shallow clone can verify every file that has not changed since the pin.

    Raises:
        SourceError: The file does not hash to the pinned value.
    """
    if pin.key in _CACHE:
        return _CACHE[pin.key]
    local = REPO / pin.path
    data = local.read_bytes() if local.is_file() else b""
    if _sha(data) != pin.sha256 and pin.revision.startswith("git:"):
        data = _git_blob(pin.revision.removeprefix("git:"), pin.path)
    if _sha(data) != pin.sha256:
        msg = f"{pin.key}: {pin.path} does not hash to the pinned sha256"
        raise SourceError(msg)
    _CACHE[pin.key] = data
    return data


def _load_obj(data: bytes) -> JsonObj:
    return cast("JsonObj", json.loads(data))


def _read_repo(path: str) -> bytes:
    return (REPO / path).read_bytes()


def _book_ids(pin: Pinned) -> tuple[set[str], set[str]]:
    """Return the node ids and choice ids of a pinned book."""
    book = _load_obj(read_pinned(pin))
    nodes = cast("list[JsonObj]", book["nodes"])
    node_ids = {cast("str", n["id"]) for n in nodes}
    choice_ids = {
        cast("str", c["id"])
        for n in nodes
        for c in cast("list[JsonObj]", n.get("choices") or [])
    }
    return node_ids, choice_ids


def _merge_nodes(pin: Pinned) -> list[str]:
    """Return the node ids with two or more distinct inbound nodes."""
    book = _load_obj(read_pinned(pin))
    parents: dict[str, set[str]] = {}
    for node in cast("list[JsonObj]", book["nodes"]):
        for choice in cast("list[JsonObj]", node.get("choices") or []):
            parents.setdefault(cast("str", choice["target"]), set()).add(
                cast("str", node["id"])
            )
    return sorted(n for n, p in parents.items() if len(p) >= 2)


BOOK_BY_KEY: Final[dict[str, Pinned]] = {b.key: b for b in BOOKS}
BOOK_BY_SHA: Final[dict[str, Pinned]] = {b.sha256: b for b in BOOKS}


def _book_ref(pin: Pinned) -> JsonObj:
    return {
        "unit": pin.unit,
        "key": pin.key,
        "file": pin.path,
        "revision": pin.revision,
        "sha256": pin.sha256,
    }


def _resolve_nodes(pin: Pinned, nodes: list[str], where: str) -> list[str]:
    """Check every id exists in the book; return those that are choice ids."""
    node_ids, choice_ids = _book_ids(pin)
    missing = [n for n in nodes if n not in node_ids and n not in choice_ids]
    if missing:
        msg = f"{where}: ids not in {pin.key}: {missing}"
        raise SourceError(msg)
    return [n for n in nodes if n not in node_ids]


# ---------------------------------------------------------------------------
# Reader items
# ---------------------------------------------------------------------------


def _anchor_ok(text: str, fid: str) -> bool:
    """Return True when the finding id appears as an entry in the source."""
    esc = re.escape(fid)
    patterns = (
        rf"^\| *{esc} *\|",  # table row
        rf"\*\*{esc}\.",  # **F3. Title**
        rf"\*\*{esc}\*\*",  # **M1**
        rf"^### {esc}\b",  # ### B1
        rf"^\s*{esc}\. \*\*",  # 12. **node**
    )
    return any(re.search(p, text, re.MULTILINE) for p in patterns)


def _verify_row(
    src: FindingSource, row: Row, text: str
) -> tuple[Pinned, list[str], list[str]]:
    """Check a transcribed row against its source text and its pinned book.

    Returns:
        tuple: The book pin, the row's ids in order, and those that are
        choice ids.

    Raises:
        SourceError: The id is not an entry in the source, a node id is not
            named there, or a node id is not in the pinned book.
    """
    fid, _, _, nodes_text = row
    nodes = nodes_text.split()
    where = f"{src.doc} {fid}"
    if not _anchor_ok(text, fid):
        msg = f"{where}: finding id not found as an entry in the source"
        raise SourceError(msg)
    absent = [n for n in nodes if not re.search(rf"\b{re.escape(n)}\b", text)]
    if absent:
        msg = f"{where}: node ids not named in the source: {absent}"
        raise SourceError(msg)
    pin = BOOK_BY_KEY[src.book]
    return pin, nodes, _resolve_nodes(pin, nodes, where)


def _finding_item(src: FindingSource, row: Row, text: str) -> JsonObj:
    fid, sev, cls, _ = row
    pin, nodes, choices = _verify_row(src, row, text)
    return {
        "id": f"{src.prefix}-{fid}",
        "kind": "node_assertion",
        "book": _book_ref(pin),
        "node": nodes[0],
        "other_nodes": nodes[1:],
        "choice_ids": choices,
        "expected_verdict": "defect",
        "defect_class": CLASSES[cls],
        "class_source": "source" if fid in src.class_from_source else "builder",
        "severity": SEVERITIES[sev],
        "severity_source": src.severity_note,
        "source": {"doc": src.doc, "anchor": fid},
        "scored_for": "D6",
        "label_strength": "strong",
    }


def finding_items() -> list[JsonObj]:
    """Return one ``node_assertion`` item per transcribed finding."""
    items: list[JsonObj] = []
    for src in FINDINGS:
        text = _read_repo(src.doc).decode("utf-8")
        items.extend(_finding_item(src, row, text) for row in src.rows)
    return items


def known_residuals() -> dict[str, list[JsonObj]]:
    """Return every clean revision's known residuals, keyed by book key.

    ``KNOWN_RESIDUALS`` plus the verified ``RESIDUAL_MINORS`` rows.

    Raises:
        SourceError: A row does not verify, is not minor, or names more than
            one choice.
    """
    out = {k: list(v) for k, v in KNOWN_RESIDUALS.items()}
    for src in RESIDUAL_MINORS:
        text = _read_repo(src.doc).decode("utf-8")
        for row in src.rows:
            fid, sev, cls, _ = row
            _, nodes, choices = _verify_row(src, row, text)
            if SEVERITIES[sev] != "minor" or len(choices) > 1:
                msg = f"{src.doc} {fid}: a known residual is one minor defect"
                raise SourceError(msg)
            out.setdefault(src.book, []).append(
                {
                    "id": fid,
                    "nodes": [n for n in nodes if n not in choices],
                    "choice": choices[0] if choices else None,
                    "defect_class": CLASSES[cls],
                    "severity": SEVERITIES[sev],
                    "source": src.doc,
                    "note": _R22_NOTE,
                }
            )
    return out


def _kd_entries() -> list[JsonObj]:
    data = _load_obj(_read_repo(f"{RETRO}/known-defects.json"))
    return cast("list[JsonObj]", data["entries"])


def kd_items() -> list[JsonObj]:
    """Return the WP-1.3 answer-key entries as reader items.

    The four public-plant entries are payoff judgments (does the payoff only
    the planted reader sees connect to something only that reader has?), so
    they are ``payoff_judgment`` items beside the 18 clean pairs; the other 13
    are ``node_assertion`` items.
    """
    items: list[JsonObj] = []
    for entry in _kd_entries():
        book = cast("JsonObj", entry["book"])
        pin = BOOK_BY_SHA[cast("str", book["sha256"])]
        node = cast("str", entry["node"])
        others = cast("list[str]", entry.get("other_nodes") or [])
        kd_id = cast("str", entry["id"])
        choices = _resolve_nodes(pin, [node, *others], kd_id)
        cls = cast("str", entry["defect_class"])
        sev_raw = cast("str", entry["severity"])
        is_payoff = cls == "public_plant"
        source = cast("JsonObj", entry["source"])
        items.append(
            {
                "id": kd_id,
                "kind": "payoff_judgment" if is_payoff else "node_assertion",
                "book": _book_ref(pin),
                "node": node,
                "other_nodes": others,
                "choice_ids": choices,
                "expected_verdict": "defect",
                "defect_class": cls,
                "class_source": "source",
                "severity": sev_raw.split(" ", 1)[0],
                "severity_source": f"known-defects.json: {sev_raw}",
                "source": {
                    "doc": f"{RETRO}/known-defects.json",
                    "anchor": kd_id,
                    "origin": source.get("doc"),
                },
                "scored_for": "D6-payoff" if is_payoff else "D6",
                "label_strength": "strong",
            }
        )
    return items


_PROP_MISMATCH: Final = ("B-os-new-2", "cq_payoff_did_go_down_read")


def payoff_items(kd: list[JsonObj]) -> list[JsonObj]:
    """Return the 18 payoff sites judged connected (section 4.2 of the 2026-11-20 doc).

    The other four of the 22 pairs are the public-plant entries already in
    ``kd``; this function checks that the two sets partition the 22 sites.
    """
    kd_sites = {
        (cast("JsonObj", i["book"])["key"], i["node"])
        for i in kd
        if i["kind"] == "payoff_judgment"
    }
    items: list[JsonObj] = []
    labels = ("B-lkl-new-1", "B-lkl-new-2", "B-os-new-1", "B-os-new-2")
    for label in labels:
        pin = BOOK_BY_KEY[label]
        node_ids, _ = _book_ids(pin)
        for node in sorted(n for n in node_ids if n.startswith("cq_payoff_")):
            if (label, node) in kd_sites:
                continue
            note = None
            if (label, node) == _PROP_MISMATCH:
                note = (
                    "judged connected with a prop mismatch: the plant copies the "
                    "words onto the back of his hand, the payoff recalls them "
                    "from the exercise book"
                )
            items.append(
                {
                    "id": f"PJ-{label}-{node.removeprefix('cq_payoff_')}",
                    "kind": "payoff_judgment",
                    "book": _book_ref(pin),
                    "node": node,
                    "other_nodes": [],
                    "choice_ids": [],
                    "expected_verdict": "clean",
                    "defect_class": None,
                    "class_source": None,
                    "severity": None,
                    "severity_source": None,
                    "source": {
                        "doc": "docs/planning/structural-verification-2026-11-20.md",
                        "anchor": "4.2 Plant to payoff, played in both states",
                        "detail": f"{SV}/playthroughs/{label}.md",
                    },
                    "scored_for": "D6-payoff",
                    "label_strength": "strong",
                    "note": note,
                }
            )
    total = len(items) + len(kd_sites)
    if total != 22:
        msg = f"expected 22 plant-payoff pairs, found {total}"
        raise SourceError(msg)
    return items


def _detector_seams(label: str) -> list[str]:
    metrics = _load_obj(_read_repo(f"{SV}/runs/{label}/metrics.json"))
    prose = cast("JsonObj", metrics["prose_craft"])
    return cast("list[str]", prose["merge_seams"])


def merge_items() -> list[JsonObj]:
    """Return one ``merge_count`` item per Run A fill.

    The 2026-11-20 hand read recorded seam counts per fill, not per node, so
    these items are scored by count: the number of the listed merge nodes a
    reader flags against ``hand_seams``.
    """
    items: list[JsonObj] = []
    for label, unit, hand, detector in MERGE_COUNTS:
        path = f"{SV}/runs/{label}/filled.json"
        data = _read_repo(path)
        pin = Pinned(label, unit, path, "working-tree", _sha(data), "Run A fill")
        merges = _merge_nodes(pin)
        if len(merges) != MERGE_NODE_TOTALS[unit]:
            msg = f"{label}: {len(merges)} merge nodes, evidence says "
            msg += str(MERGE_NODE_TOTALS[unit])
            raise SourceError(msg)
        if len(_detector_seams(label)) != detector:
            msg = f"{label}: detector seam count disagrees with the evidence table"
            raise SourceError(msg)
        is_ltn = unit == "the-last-train-north"
        items.append(
            {
                "id": f"MC-{label}",
                "kind": "merge_count",
                "book": _book_ref(pin),
                "node": None,
                "merge_nodes": merges,
                "hand_seams": hand,
                "detector_seams": detector,
                "expected_verdict": "count",
                "defect_class": "merge_seam",
                "class_source": "source",
                "severity": None,
                "severity_source": None,
                "source": {
                    "doc": "docs/planning/structural-verification-2026-11-20.md",
                    "anchor": "3.1 table, 'Merge seams, hand'"
                    if is_ltn
                    else "3.2 table, 'Merge seams (detector = hand)'",
                },
                "scored_for": "D6-merge",
                "label_strength": "strong" if is_ltn else "count-agreement",
            }
        )
    return items


_WP04_CLEAN_SOURCE: Final[JsonObj] = {
    "doc": "post-fix book (WP-0.4 'Open continuity findings: 0')"
}
_R22_CLEAN_SOURCE: Final[JsonObj] = {
    "doc": R22,
    "anchor": "Bottom line per book",
}


def _defect_items(reader: list[JsonObj], book_key: str) -> list[JsonObj]:
    return [
        i
        for i in reader
        if cast("JsonObj", i["book"])["key"] == book_key
        and i["expected_verdict"] == "defect"
        and i["kind"] in {"node_assertion", "payoff_judgment"}
    ]


def clean_items(
    reader: list[JsonObj], residuals: dict[str, list[JsonObj]]
) -> list[JsonObj]:
    """Return one ``clean_book`` item per clean revision, plus B-lkl-new-1 (weak).

    The clean revisions are the two WP-0.4 post-fix books still clean
    (``fixed_nodes``: the primary node of each pre-fix defect) and the five
    books fixed on 2026-11-22 (``fixed_nodes``: every node a 2026-11-21
    residual of the post-fix revision names).

    Raises:
        SourceError: A fixed revision has no residual behind it, or a node is
            both a fixed node and a known residual.
    """
    items: list[JsonObj] = []
    for unit in WP04_CLEAN_UNITS:
        pin = BOOK_BY_KEY[POSTFIX_OF[unit]]
        node_ids, _ = _book_ids(pin)
        fixed = sorted(
            {
                cast("str", i["node"])
                for i in reader
                if cast("JsonObj", i["book"])["key"] == PREFIX_OF[unit]
                and i["node"] in node_ids
            }
        )
        res = residuals.get(pin.key, [])
        items.append(_clean_item(pin, len(node_ids), fixed, res, _WP04_CLEAN_SOURCE))
    for unit, key in FIXED_OF.items():
        pin = BOOK_BY_KEY[key]
        node_ids, _ = _book_ids(pin)
        before = _defect_items(reader, POSTFIX_OF[unit])
        if not before:
            msg = f"{key}: no 2026-11-21 residual on {POSTFIX_OF[unit]}"
            raise SourceError(msg)
        named = (
            n
            for i in before
            for n in [cast("str", i["node"]), *cast("list[str]", i["other_nodes"])]
        )
        fixed = sorted({n for n in named if n in node_ids})
        res = residuals.get(key, [])
        both = set(fixed) & {n for r in res for n in cast("list[str]", r["nodes"])}
        if both:
            msg = f"{key}: nodes both fixed and a known residual: {sorted(both)}"
            raise SourceError(msg)
        items.append(_clean_item(pin, len(node_ids), fixed, res, _R22_CLEAN_SOURCE))
    lkl = BOOK_BY_KEY["B-lkl-new-1"]
    weak = _clean_item(lkl, len(_book_ids(lkl)[0]), [], [], _WP04_CLEAN_SOURCE)
    weak["label_strength"] = "weak"
    weak["note"] = (
        "no answer-key entry and every plant-payoff pair judged connected, but "
        "never given a full continuity read; reported apart from the D6 "
        "false-flag denominator"
    )
    items.append(weak)
    return items


def _clean_item(
    pin: Pinned,
    node_count: int,
    fixed: list[str],
    residuals: list[JsonObj],
    source: JsonObj,
) -> JsonObj:
    return {
        "id": f"CB-{pin.key}",
        "kind": "clean_book",
        "book": _book_ref(pin),
        "node": None,
        "node_count": node_count,
        "fixed_nodes": fixed,
        "known_residuals": residuals,
        "expected_verdict": "clean",
        "defect_class": None,
        "class_source": None,
        "severity": None,
        "severity_source": None,
        "source": dict(source),
        "scored_for": "D6",
        "label_strength": "strong",
    }


# ---------------------------------------------------------------------------
# Plan items
# ---------------------------------------------------------------------------


def _manifest_plans(manifest: str, plans_dir: str, prompt: str) -> list[JsonObj]:
    data = _load_obj(_read_repo(manifest))
    out: list[JsonObj] = []
    for pid, raw in cast("dict[str, JsonObj]", data["extractions"]).items():
        path = f"{plans_dir}/{pid}.plan.json"
        plan_bytes = _read_repo(path)
        prov = cast("JsonObj", _load_obj(plan_bytes)["provenance"])
        book_sha = cast("str", raw["book_sha256"])
        if prov.get("book_sha256") != book_sha:
            msg = f"{path}: provenance.book_sha256 differs from the manifest"
            raise SourceError(msg)
        out.append(
            {
                "plan_id": pid,
                "plan": {"file": path, "sha256": _sha(plan_bytes), "pointer": None},
                "book_pin": BOOK_BY_SHA[book_sha],
                "producer": f"blind extraction ({manifest.rsplit('/', 2)[-2]}), "
                f"{raw.get('model_family', 'opus')} agent, prompt {prompt}",
                "manifest": manifest,
            }
        )
    return out


def _plan_label(book_key: str, reader: list[JsonObj]) -> tuple[JsonObj, list[JsonObj]]:
    """Return a plan's label fields and the minor defects it carries as residuals.

    Reader defect items count. When every defect of the revision is minor
    (owner ruling 2026-11-22, AL-882), the plan is ``pass`` and those minors are
    returned as known residuals instead of defects; any should-fix or blocker
    makes it ``reject``. A clean revision's recorded residuals are not defect
    items, so a plan of a clean revision stays ``pass`` either way.
    """
    # #ASSUME: data-integrity: every defect of a book revision is a reader
    # defect item keyed to that exact revision; known residuals never are.
    # #VERIFY: the unit tests assert every e/f plan and every minor-only plan
    # is ``pass`` with the minors listed, and every other plan keeps its defects.
    items = _defect_items(reader, book_key)
    severities = [cast("str", i["severity"]) for i in items]
    minor_only = bool(items) and all(sev == "minor" for sev in severities)
    minors: list[JsonObj] = []
    if minor_only:
        minors = [
            {
                "id": i["id"],
                "nodes": [i["node"], *cast("list[str]", i["other_nodes"])],
                "choice": next(iter(cast("list[str]", i["choice_ids"])), None),
                "defect_class": i["defect_class"],
                "severity": "minor",
                "source": cast("JsonObj", i["source"])["doc"],
                "note": _MINOR_ONLY_NOTE,
            }
            for i in items
        ]
        items = []
        severities = []
    defects: list[JsonObj] = [
        {
            "id": i["id"],
            "defect_class": i["defect_class"],
            "severity": i["severity"],
        }
        for i in items
    ]
    worst = min(severities, key=SEVERITY_RANK.__getitem__) if severities else None
    label: JsonObj = {
        "expected_verdict": "reject" if defects else "pass",
        "defect_class": sorted({cast("str", d["defect_class"]) for d in defects}),
        "class_source": "the book's reader items",
        "severity": worst,
        "severity_source": "highest severity among the book's defects",
        "blocker_entries": sum(1 for sev in severities if sev == "blocker"),
        "defects": defects,
    }
    return label, minors


_MINOR_ONLY_NOTE: Final = (
    "minor defect of a revision whose every defect is minor; recorded as a known "
    "residual of its plans, not a reason to reject them (owner ruling 2026-11-22, "
    "AL-882). A reviewer flag here is a true positive"
)


def _plan_item(
    spec: JsonObj, reader: list[JsonObj], residuals: dict[str, list[JsonObj]]
) -> JsonObj:
    pin = cast("Pinned", spec["book_pin"])
    weak = pin.key == "B-lkl-new-1"
    label, minors = _plan_label(pin.key, reader)
    return {
        "id": f"PL-{spec['plan_id']}",
        "kind": "plan",
        "book": _book_ref(pin),
        "plan": spec["plan"],
        "producer": spec["producer"],
        **label,
        "known_residuals": [*residuals.get(pin.key, []), *minors],
        "source": {"doc": spec["manifest"], "anchor": spec["plan_id"]},
        "scored_for": "D12",
        "label_strength": "weak" if weak else "strong",
        "note": (
            "negative control in the WP-1.4 manifest: no answer-key entry, but "
            "the book never had a full continuity read"
            if weak
            else None
        ),
    }


def blind_plan_items(
    reader: list[JsonObj], residuals: dict[str, list[JsonObj]]
) -> list[JsonObj]:
    """Return every blind plan, labelled by the defects of its book revision.

    WP-1.4, the G1 re-run and WP-1.6, then the clean-plan passes: c/d of the
    five WP-0.4 post-fix revisions (``reject`` since the 2026-11-21 residual
    check) and e/f of the revisions fixed on 2026-11-22 (``pass``).
    """
    specs = [
        *_manifest_plans(
            f"{RETRO}/plans/manifest.json",
            f"{RETRO}/plans",
            "EXTRACTION-PROMPT.md (v1)",
        ),
        *_manifest_plans(
            f"{RETRO}/rerun/manifest.json",
            f"{RETRO}/rerun/plans",
            "EXTRACTION-PROMPT-v2.md",
        ),
        *_manifest_plans(
            f"{FRESH}/manifest.json", f"{FRESH}/plans", "EXTRACTION-PROMPT-v2.md"
        ),
        *_manifest_plans(
            f"{CR}/clean-plans/manifest.json",
            f"{CR}/clean-plans/plans",
            "EXTRACTION-PROMPT-v2.md",
        ),
        *_manifest_plans(
            f"{CR}/clean-plans-fixed/manifest.json",
            f"{CR}/clean-plans-fixed/plans",
            "EXTRACTION-PROMPT-v2.md",
        ),
    ]
    return [_plan_item(s, reader, residuals) for s in specs]


_POSTFIX_REJECT_NOTE: Final = (
    "binds the WP-0.4 post-fix revision, which the 2026-11-21 residual check "
    "found to carry defects; labelled with them. The clean plans of this book "
    "are the e/f blind plans of the revision fixed on 2026-11-22"
)


def _postfix_note(*, rejected: bool, minors: bool) -> str | None:
    if rejected:
        return _POSTFIX_REJECT_NOTE
    if minors:
        return (
            "binds the WP-0.4 post-fix revision, whose only residuals are minor; "
            "pass with those minors as known residuals (AL-882)"
        )
    return None


def postfix_plan_items(
    reader: list[JsonObj], residuals: dict[str, list[JsonObj]]
) -> list[JsonObj]:
    """Return the seven hand-written post-fix plans, labelled by their book.

    Lighthouse and orchard stay ``pass``; the five held-out ones bind
    post-fix revisions that now carry 2026-11-21 residuals, so ``reject``.
    """
    items: list[JsonObj] = []
    for plan_pin in POSTFIX_PLANS:
        plan = _load_obj(read_pinned(plan_pin))
        book_pin = BOOK_BY_KEY[POSTFIX_OF[plan_pin.unit]]
        prov = cast("JsonObj", plan["provenance"])
        if prov.get("book_sha256") != book_pin.sha256:
            msg = f"{plan_pin.key}: provenance.book_sha256 is not the post-fix book"
            raise SourceError(msg)
        label, minors = _plan_label(book_pin.key, reader)
        rejected = label["expected_verdict"] == "reject"
        if not rejected:
            label["class_source"] = None
            label["severity_source"] = None
        items.append(
            {
                "id": f"PL-{plan_pin.unit}-postfix",
                "kind": "plan",
                "book": _book_ref(book_pin),
                "plan": {
                    "file": plan_pin.path,
                    "revision": plan_pin.revision,
                    "sha256": plan_pin.sha256,
                    "pointer": None,
                },
                "producer": "hand-written (WP-0.3), revised with the WP-0.4 fixes",
                **label,
                "known_residuals": [*residuals.get(book_pin.key, []), *minors],
                "source": {"doc": plan_pin.path},
                "scored_for": "D12",
                "label_strength": "strong",
                "note": _postfix_note(rejected=rejected, minors=bool(minors)),
            }
        )
    return items


def smoke_plan_items() -> list[JsonObj]:
    """Return the six WP-2.3 generated plans, unlabelled (observe only)."""
    items: list[JsonObj] = []
    for n in range(1, 7):
        path = f"{SMOKE}/runs/{n}.json"
        data = _read_repo(path)
        run = _load_obj(data)
        shape = cast("JsonObj", run["shape"])
        unit = cast("str", shape["id"])
        if "plan" not in run or unit not in UNIT_BANDS:
            msg = f"{path}: no plan, or shape {unit} has no split unit"
            raise SourceError(msg)
        items.append(
            {
                "id": f"PL-smoke-{n}",
                "kind": "plan",
                "book": {
                    "unit": unit,
                    "key": None,
                    "file": None,
                    "revision": None,
                    "sha256": None,
                    "shape_hash": shape["hash"],
                },
                "plan": {"file": path, "sha256": _sha(data), "pointer": "/plan"},
                "producer": f"generated by {run['model']} (WP-2.3 paid smoke)",
                "expected_verdict": "unknown",
                "defect_class": [],
                "class_source": None,
                "severity": None,
                "severity_source": None,
                "blocker_entries": None,
                "defects": [],
                "source": {"doc": f"{SMOKE}/README.md", "anchor": f"run {n}"},
                "scored_for": "observe-only",
                "label_strength": "unlabelled",
            }
        )
    return items


# ---------------------------------------------------------------------------
# Split
# ---------------------------------------------------------------------------


def _unit_of(item: JsonObj) -> str:
    return cast("str", cast("JsonObj", item["book"])["unit"])


def _plan_stats(items: list[JsonObj]) -> tuple[Counter[str], Counter[str]]:
    """Count real defective plans and strong clean plans per unit."""
    defective: Counter[str] = Counter()
    clean: Counter[str] = Counter()
    for item in items:
        if item["kind"] != "plan" or item["label_strength"] != "strong":
            continue
        if item["expected_verdict"] == "reject":
            defective[_unit_of(item)] += 1
        elif item["expected_verdict"] == "pass":
            clean[_unit_of(item)] += 1
    return defective, clean


def coin(unit: str) -> int:
    """Return the seeded coin flip for a unit: 1 means held out."""
    digest = hashlib.sha256(f"{SPLIT_SEED}:{unit}".encode()).hexdigest()
    return int(digest, 16) % 2


def compute_split(items: list[JsonObj]) -> dict[str, str]:
    """Assign every unit to a half.

    Forced units go to tuning. Over every assignment of the free units, pick
    the one that maximises, in order: (1) the smaller of the held-out
    defective-plan and clean-plan counts; (2) the number of (band, defective
    or clean) plan cells the held-out half covers; (3) agreement with the
    seeded coin flips. Any remaining tie goes to the first assignment in
    ``itertools.product`` order, so the result is deterministic.

    Args:
        items: Every item; only strong-label plan items enter the score.

    Returns:
        dict[str, str]: Unit slug to ``tuning`` or ``held_out``.

    Raises:
        SourceError: No assignment was scored (cannot happen with free units).
    """
    defective, clean = _plan_stats(items)
    free = sorted(u for u in UNIT_BANDS if u not in FORCED_TUNING)
    best: tuple[tuple[int, int, int], frozenset[str]] | None = None
    for bits in itertools.product((0, 1), repeat=len(free)):
        held = frozenset(u for u, b in zip(free, bits, strict=True) if b)
        d = sum(defective[u] for u in held)
        c = sum(clean[u] for u in held)
        cells = {(UNIT_BANDS[u], "d") for u in held if defective[u]}
        cells |= {(UNIT_BANDS[u], "c") for u in held if clean[u]}
        agree = sum(1 for u, b in zip(free, bits, strict=True) if b == coin(u))
        score = (min(d, c), len(cells), agree)
        if best is None or score > best[0]:
            best = (score, held)
    if best is None:  # pragma: no cover - free is never empty
        msg = "no split computed"
        raise SourceError(msg)
    return {u: HELD_OUT if u in best[1] else TUNING for u in UNIT_BANDS}


def frozen_split(items: list[JsonObj]) -> dict[str, str]:
    """Return the split, checked against ``RECORDED_SPLIT``.

    Raises:
        SourceError: The search would move a unit to the other half.
    """
    # #CRITICAL: data-integrity: a prompt tuned on the tuning half must never
    # be scored on a book it saw. New items change the search's counts, so a
    # silently recomputed split could move a tuned book into held_out.
    # #VERIFY: compare with the recorded split and fail the build on drift.
    split = compute_split(items)
    moved = sorted(u for u in UNIT_BANDS if split[u] != RECORDED_SPLIT[u])
    if moved:
        msg = (
            f"the split search would move {moved}; the split is frozen at "
            "RECORDED_SPLIT, so change it only by an owner decision"
        )
        raise SourceError(msg)
    return split


# ---------------------------------------------------------------------------
# Thresholds (quoted from the plan, decided 2026-11-21)
# ---------------------------------------------------------------------------

THRESHOLDS: Final[JsonObj] = {
    "source": "docs/planning/story-plan-implementation-plan.md, decision table "
    "rows D6 and D12 (with its 2026-11-21 amendment) and the note 'D12 as "
    "decided 2026-11-21'",
    "decided": "2026-11-21 (owner, in session), before any WP-3.2 or WP-3.7 "
    "prompt was written",
    "D6": {
        "applies_to": "continuity reader (WP-3.2), held-out half",
        "recall_on_known_defects_min": 0.8,
        "false_flags_per_50_nodes_on_clean_books_max": 1,
        "two_run_agreement_min": 0.9,
    },
    "D12": {
        "applies_to": "plan reviewer (WP-3.7), held-out half",
        "defect_recall": "reject or unsure on at least 90 percent of labelled "
        "defective plans, and on every blocker-severity entry",
        "clean_flag_rate_max": "reject or unsure on at most 20 percent",
        "run_agreement_min": "identical verdicts on at least 90 percent of plans "
        "across two runs",
        "minimum_validation_size": "at least 15 defective and 15 clean held-out "
        "plans, supplemented with seeded-defect plans reported as synthetic; if "
        "the minimum cannot be met the reviewer is not validated",
        "minimum_validation_size_amended": (
            "amended 2026-11-21 (AL-853): the clean held-out minimum is met "
            "by a fresh blind extraction plus a second independent blind "
            "extraction of each of the five held-out post-fix books, results "
            "reported per book (the effective clean sample is five books); "
            "synthetic defective plans seed both checker-visible defects (the "
            "WP-1.2 witnesses) and checker-invisible ones (a choice outcome "
            "contradicting its label, a fact contradicting truth), each reported "
            "separately. Since the 2026-11-21 residual check, the five books are "
            "the revisions fixed on 2026-11-22 and the two passes are the e/f plans"
        ),
        "sample_rate": "1 in 10 in steady state; 100 percent through the pilot "
        "(WP-4.2, WP-4.3)",
        "suspension": "the owner overturns any blocker-class pass, or more than 1 "
        "in 5 of the last 10 sampled passes (at least 5 sampled)",
        "scope_of_authority": "per defect class: only classes with measured "
        "recall; others advisory",
    },
}

# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def _summary(items: list[JsonObj], split: dict[str, str]) -> JsonObj:
    """Count items per half: reader items by kind, class and severity; plans."""
    out: JsonObj = {}
    for half in (TUNING, HELD_OUT):
        mine = [i for i in items if split[_unit_of(i)] == half]
        defects = [
            i
            for i in mine
            if i["kind"] in {"node_assertion", "payoff_judgment"}
            and i["expected_verdict"] == "defect"
        ]
        clean_books = [i for i in mine if i["kind"] == "clean_book"]
        plans = [i for i in mine if i["kind"] == "plan"]
        out[half] = {
            "units": sorted(u for u, h in split.items() if h == half),
            "items_by_kind": dict(
                sorted(Counter(cast("str", i["kind"]) for i in mine).items())
            ),
            "reader_defects_by_class": dict(
                sorted(Counter(cast("str", i["defect_class"]) for i in defects).items())
            ),
            "reader_defects_by_severity": dict(
                sorted(Counter(cast("str", i["severity"]) for i in defects).items())
            ),
            "payoff_judgments_clean": sum(
                1
                for i in mine
                if i["kind"] == "payoff_judgment" and i["expected_verdict"] == "clean"
            ),
            "merge_openings": sum(
                len(cast("list[str]", i["merge_nodes"]))
                for i in mine
                if i["kind"] == "merge_count"
            ),
            "clean_books_strong": sum(
                1 for i in clean_books if i["label_strength"] == "strong"
            ),
            "clean_nodes_strong": sum(
                cast("int", i["node_count"])
                for i in clean_books
                if i["label_strength"] == "strong"
            ),
            "plans": dict(
                sorted(
                    Counter(
                        f"{i['expected_verdict']}/{i['label_strength']}" for i in plans
                    ).items()
                )
            ),
            "plans_with_blocker": sum(
                1 for i in plans if (cast("int | None", i["blocker_entries"]) or 0)
            ),
            "d12_plans_by_unit": _d12_by_unit(plans),
        }
    return out


def _d12_by_unit(plans: list[JsonObj]) -> JsonObj:
    """Count D12-scored plans per book unit by verdict and label strength."""
    by_unit: dict[str, Counter[str]] = {}
    for i in plans:
        if i["scored_for"] != "D12":
            continue
        key = f"{i['expected_verdict']}/{i['label_strength']}"
        by_unit.setdefault(_unit_of(i), Counter())[key] += 1
    return {u: dict(sorted(c.items())) for u, c in sorted(by_unit.items())}


def build() -> JsonObj:
    """Build the whole validation-set document."""
    kd = kd_items()
    residuals = known_residuals()
    reader = [*kd, *finding_items()]
    reader += payoff_items(kd)
    reader += merge_items()
    reader += clean_items(reader, residuals)
    plans = [
        *blind_plan_items(reader, residuals),
        *postfix_plan_items(reader, residuals),
        *smoke_plan_items(),
    ]
    items = [*reader, *plans]
    ids = [cast("str", i["id"]) for i in items]
    if len(ids) != len(set(ids)):
        msg = "duplicate item ids"
        raise SourceError(msg)
    split = frozen_split(items)
    for item in items:
        item["half"] = split[_unit_of(item)]
    return {
        "schema": "validation-set/v1",
        "work_package": "WP-3.1",
        "generator": "scripts/build_validation_set.py",
        "readme": "docs/planning/evidence/continuity-reader/README.md",
        "thresholds": THRESHOLDS,
        "split": {
            "by": "book (book.unit)",
            "seed": SPLIT_SEED,
            "seed_note": "full hash of commit 990054d, which recorded D6 and D12",
            "method": "forced units to tuning; exhaustive search over the free "
            "units maximising (min(held-out defective plans, held-out clean "
            "plans), held-out band cells, agreement with seeded coin flips)",
            "frozen": (
                "the search is re-run on every build and must reproduce "
                "the split as first recorded; a build whose search would move a "
                "unit fails rather than change the split"
            ),
            "forced_tuning": FORCED_TUNING,
            "units": {
                u: {"half": split[u], "band": UNIT_BANDS[u], "coin": coin(u)}
                for u in UNIT_BANDS
            },
        },
        "summary": _summary(items, split),
        "items": items,
    }


def render(doc: JsonObj) -> str:
    """Serialise deterministically (sorted keys, two-space indent, newline)."""
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Run the builder CLI."""
    parser = argparse.ArgumentParser(description="Build the WP-3.1 validation set.")
    parser.add_argument("--check", action="store_true", help="compare, do not write")
    parser.add_argument("--summary", action="store_true", help="print the counts")
    args = parser.parse_args(argv)
    check = cast("bool", args.check)
    summary = cast("bool", args.summary)
    try:
        doc = build()
    except MissingRevisionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_NO_REVISION
    except SourceError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_FAIL
    text = render(doc)
    if summary:
        print(json.dumps(doc["summary"], indent=2))
        print(json.dumps(cast("JsonObj", doc["split"])["units"], indent=2))
    if check:
        current = OUT_FILE.read_text("utf-8") if OUT_FILE.is_file() else ""
        if current != text:
            print(
                f"drift: {OUT_FILE.relative_to(REPO)} is not what the "
                "sources build; rerun without --check",
                file=sys.stderr,
            )
            return EXIT_FAIL
        return EXIT_OK
    if not summary:
        OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        OUT_FILE.write_text(text, "utf-8")
        count = len(cast("list[JsonObj]", doc["items"]))
        print(f"wrote {OUT_FILE.relative_to(REPO)} ({count} items)")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
