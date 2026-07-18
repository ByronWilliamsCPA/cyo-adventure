---
schema_type: planning
title: "WS-0 Phase 2: Diversity Eval Harness, Panel, Baseline, and CI Regression Gate"
description: "Implementation-ready design for WS-0 Phase 2: the aggregate/lexical/PS/RAR
  metrics, the committed eval panel, the baseline artifact and its regression rules, the
  run_diversity_eval harness, the diversity_eval nox session, the per-PR CI gate, and the
  Phase 3 judge-calibration seam."
tags:
  - planning
  - architecture
  - generation
  - metrics
status: proposed
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Resolve the open Phase 2 decisions from ws0-diversity-metrics-design.md
  (sections 2.6-2.8, 6, and the section 10 critique) into a spec Sonnet can implement
  directly: exact panel contents, baseline format, CI-fail rules, module signatures, and
  test plan, all grounded in a fresh probe over the committed corpus run 2026-07-18."
component: Strategy
source: "docs/planning/ws0-diversity-metrics-design.md; the shipped Phase 1 package
  src/cyo_adventure/diversity/; scripts/run_story_gate.py and check_fill_integrity.py;
  out/pilot/fills/ and the 22 committed out/*.filled.json inventory fills; noxfile.py;
  .github/workflows/ci.yml; a probe run 2026-07-18 (section 1.4) over the committed fills."
---

# WS-0 Phase 2: Diversity Eval Harness, Panel, Baseline, and CI Regression Gate

> **Status: proposed, ready for implementation.** This resolves the Phase 2 open decisions
> from [ws0-diversity-metrics-design.md](ws0-diversity-metrics-design.md) (the "WS-0 spec"):
> sections 2.6 (lexical guards), 2.7 (ECS), 2.8 (PS/RAR), 6 (harness, panel, baseline, nox,
> CI), under the section 10 constraints. It does not redesign anything; where it deviates
> from the spec's letter, the deviation is called out inline with its reason.
>
> **The one paragraph that governs everything else:** CI makes no network calls, so the
> panel is committed pre-generated fills, and only two things gate a build: the
> anti-template guard's expected verdicts on the committed panel, and regression deltas
> against a committed baseline. PS and RAR are trend-only; their weights are unvalidated
> priors until the Phase 3 judge run, and nothing in this design lets them fail CI.

---

## 0. What Phase 1 shipped, and what Phase 2 adds

Shipped and reused as-is (do not duplicate, do not modify unless noted):

| Phase 1 module | Reused by Phase 2 for |
| --- | --- |
| `diversity/normalize.py` | `extract_entities`, `mask_tokens`, `content_tokens`, `theme_signature`, `jaccard_similarity`, `coerce_storybook` |
| `diversity/structure.py` | `structure_fingerprint`, `structural_distance` |
| `diversity/leaf.py` | `leaf_distance_profile`, `anti_template_verdict` |
| `diversity/report.py` | `AntiTemplateReport`, `AntiTemplateVerdict` |
| `diversity/history.py`, `diversity/query.py` | untouched (WS-4 surface, not harness inputs) |

Phase 2 adds exactly these files:

```text
src/cyo_adventure/diversity/aggregate.py      # ECS, pair_score/PS, RAR          (section 3.1)
src/cyo_adventure/diversity/lexical.py        # distinct-n, self-BLEU-lite       (section 3.2)
src/cyo_adventure/diversity/panel.py          # manifest models, panel runner,
                                              # baseline compare                 (section 3.3)
scripts/run_diversity_eval.py                 # thin CLI over panel.py           (section 4.1)
tests/data/diversity_panel/panel.json         # the committed panel manifest     (section 1)
tests/data/diversity_panel/fills/*.json       # 7 copied fill fixtures           (section 1.2)
tests/data/diversity_panel/baseline.json      # the committed baseline           (section 2)
tests/unit/test_diversity_aggregate.py
tests/unit/test_diversity_lexical.py
tests/unit/test_diversity_panel.py            # incl. the harness smoke test     (section 6)
```

Plus three one-line edits: a `diversity_eval` session in `noxfile.py` (section 4.2), a
`diversity` job in `.github/workflows/ci.yml` (section 4.3), and `out/diversity/` appended
to `.gitignore` (live-fill and judge outputs must never be committed by accident).

Import discipline update (extends WS-0 spec section 1.1, does not change it):
`aggregate.py` and `lexical.py` are pure (stdlib + sibling pure modules + storybook models
only). `panel.py` reads committed fixture files from paths given by its caller; it is
filesystem-impure but remains DB-free and network-free, so `history.py` stays the only
DB-touching module. `panel.py` never imports `db`, `generation`, or `sqlalchemy`. The
judge integration (section 5) lives in the *script*, which may import `generation`
freely; scripts are composition roots, not package members.

Explicit non-scope for Phase 2: the dashboard surfacing of ECS/RAR trends (an ops/frontend
task once numbers exist), the DB loader for served-window ECS (lands with that dashboard
work; `effective_catalog_size` takes plain rows now, section 3.1), per-band ATG threshold
tables (WS-1, needs young-band panel pairs), and any change to `generation/` or prompts
(the metrics have no generation-facing API, WS-0 spec section 7.2).

---

## 1. Decision 1: the panel

### 1.1 The finding that reshapes the panel

The WS-0 spec assumed the panel starts from two committed fills. A probe on 2026-07-18
found the corpus is richer than the spec knew: `out/the-cave-of-echoes.filled.json` (the
original sea-caves fill from the initial inventory run) **shares its structure
fingerprint** with both pilot fills, because the parameterization pass rewrote only bodies
and ending titles, both of which `structure_fingerprint` excludes. The repo therefore
already contains **three same-tree fills of one skeleton under three distinct themes**,
and 21 more committed single fills across all six bands (`out/*.filled.json`).

Verified with the shipped Phase 1 code (masking without briefs, i.e. the conservative
direction):

| Same-tree pair | ATG verdict | median D_uni | p25 | mean D_big |
| --- | --- | --- | --- | --- |
| sea-caves vs space-station | PASS | 0.848 | 0.815 | 0.934 |
| sea-caves vs dino-dig | PASS | 0.793 | 0.760 | 0.910 |
| space-station vs dino-dig | PASS | 0.824 | 0.792 | 0.920 |
| space-station vs 18-noun swap of itself | FAIL | 0.069 | 0.037 | n/a |

So the minimum viable panel needs **zero new fill generation**. Every v1 entry below is a
file already in git or a run-time synthetic. The "operator step using the real fill path"
is required only for panel *growth* (section 1.5), not for shipping Phase 2.

### 1.2 v1 panel contents (the minimum viable panel, exact)

Seven committed fill fixtures, copied to `tests/data/diversity_panel/fills/` (~400 KB
total):

| Panel id | Copied from | Band | Skeleton | Role |
| --- | --- | --- | --- | --- |
| `cave-sea` | `out/the-cave-of-echoes.filled.json` | 8-11 | the-cave-of-echoes | same-tree cell, theme 1 |
| `cave-space` | `out/pilot/fills/the-cave-of-echoes.space-station.filled.json` | 8-11 | the-cave-of-echoes | same-tree cell, theme 2 |
| `cave-dino` | `out/pilot/fills/the-cave-of-echoes.dino-dig.filled.json` | 8-11 | the-cave-of-echoes | same-tree cell, theme 3 |
| `clockwork` | `out/the-clockwork-menagerie.filled.json` | 8-11 | the-clockwork-menagerie | cross-tree, same band |
| `skyship` | `out/the-sky-ship-stowaway.filled.json` | 8-11 | the-sky-ship-stowaway | cross-tree, same band |
| `clover` | `out/the-clover-and-the-butterfly.filled.json` | 3-5 | the-clover-and-the-butterfly | young-band lexical recording only |
| `lantern` | `out/the-lantern-festival.filled.json` | 5-8 | the-lantern-festival | young-band lexical recording only |

Two run-time synthetics (never committed as story files, per WS-0 spec section 6.2):

| Panel id | Derivation | Expected ATG |
| --- | --- | --- |
| `cave-space-swap` | `make_noun_swap_variant(cave-space, SWAPS)` from the committed 18-entry swap table | FAIL |
| `cave-space-identical` | identity copy of `cave-space` | FAIL (median 0.0; catches "compared it against itself" wiring bugs) |

The committed swap table (probed: FAIL at median 0.069, p25 0.037):

```json
{"station": "burrow", "drone": "ferret", "airlock": "gate", "hull": "wall",
 "corridor": "tunnel", "console": "desk", "oxygen": "air", "solar": "lunar",
 "panel": "plank", "module": "room", "gravity": "weight", "orbit": "circle",
 "engine": "motor", "signal": "whistle", "metal": "wood", "light": "lamp",
 "door": "hatch", "echo": "ring"}
```

Pair sets exercised over those ids:

- **ATG pairs (5, all hard-gated on expected verdict):** the three genuine PASS pairs from
  the table in 1.1, plus (`cave-space`, `cave-space-swap`) expected FAIL and
  (`cave-space`, `cave-space-identical`) expected FAIL.
- **Cross-tree structural pairs (3):** `cave-sea~clockwork` (probed 0.375),
  `cave-sea~skyship` (0.387), `clockwork~skyship` (0.130). Invariant-gated (`> 0`), values
  baseline-tracked. The additional structural smoke over `skeletons/8-11/*.json` skeleton
  files stays a unit test (Phase 1's `test_diversity_structure.py` already covers it), not
  a panel entry: skeleton files with `<<FILL>>` bodies are not fills and do not belong in
  a fill panel.
- **PS pairs:** every ATG pair plus every cross-tree pair (8 pairs), exercising both the
  same-fingerprint branch and the cross-fingerprint cosine branch. Recorded, never gated.
- **RAR pseudo-sequence (1):** `[cave-sea, clockwork, skyship, cave-space, cave-dino,
  cave-space-swap]` treated as one pseudo-family's chronological history. With the probe's
  PS values exactly one element repeats (the swap, PS 0.966 vs its base), giving a
  deterministic RAR of 0.2. Recorded, never gated; it exists so the RAR code path runs on
  real data every CI pass and its trend is visible in the report.
- **tau-theme brief pairs (8, gated on expected boolean):** all verified against the
  shipped `theme_signature` on 2026-07-18:

| Brief A | Brief B | Similarity | Expected |
| --- | --- | --- | --- |
| "a dragon who lost his fire" | "dragon story please" | 0.500 | similar |
| "a brave dragon guards her eggs" | "the wyvern of the north mountain" | 1.000 | similar |
| "a space station rescue mission" | "astronauts stranded in orbit" | 1.000 | similar |
| "a dinosaur dig in the desert" | "fossils hidden in the canyon" | 0.500 | similar |
| "a wizard's first spell goes wrong" | "the witch of the forest school" | 0.500 | similar |
| "a space station rescue mission" | "an undersea mermaid kingdom" | 0.000 | distinct |
| "a robot learns to bake bread" | "pirates hunt for buried treasure" | 0.000 | distinct |
| "a knight guards the old castle" | "a pirate ship full of treasure" | 0.000 | distinct |

  Deliberately no near-boundary pair (nothing in [0.25, 0.45]): boundary fixtures make the
  gate brittle to `_THEME_TAG_MAP` edits. A map edit that flips one of these robust
  expectations is a real behavior change and *should* fail CI loudly.

**Copy vs reference (judgment call).** The WS-0 spec (6.2) referenced fills at their
`out/` paths. Resolved: **copy into `tests/data/diversity_panel/fills/`**. Reason: `out/`
is a working area; the inventory run that produced `out/*.filled.json` may be re-run and
overwrite them, and a CI-gating fixture must be immutable and append-only. The 400 KB
duplication is the price of a gate that cannot be moved by an unrelated authoring rerun.
Alternative (reference in place) rejected for that mutability; alternative (git-move the
fills out of `out/`) rejected because `out/pilot/RESULTS.md` and the inventory report
document those paths as reproduction evidence. Fixture files are verbatim byte copies;
`provenance` in the manifest records the source path and date.

### 1.3 `panel.json` manifest schema

```json
{
  "schema_version": 1,
  "fills": [
    {"id": "cave-sea",
     "path": "tests/data/diversity_panel/fills/the-cave-of-echoes.sea-caves.filled.json",
     "band": "8-11", "skeleton_slug": "the-cave-of-echoes",
     "brief": {"premise": "two friends explore the glowing sea caves at low tide"},
     "provenance": "copied 2026-07-18 from out/the-cave-of-echoes.filled.json (initial inventory run)"}
  ],
  "synthetic": [
    {"id": "cave-space-swap", "base": "cave-space", "kind": "noun_swap",
     "swaps": {"station": "burrow", "...": "..."}},
    {"id": "cave-space-identical", "base": "cave-space", "kind": "identity"}
  ],
  "atg_pairs": [
    {"a": "cave-sea", "b": "cave-space", "expected_verdict": "pass"},
    {"a": "cave-space", "b": "cave-space-swap", "expected_verdict": "fail"}
  ],
  "cross_tree_pairs": [["cave-sea", "clockwork"]],
  "rar_sequence": ["cave-sea", "clockwork", "skyship", "cave-space", "cave-dino", "cave-space-swap"],
  "brief_pairs": [
    {"a": {"premise": "a dragon who lost his fire"},
     "b": {"premise": "dragon story please"}, "expected_similar": true}
  ],
  "lexical_gated_ids": ["cave-sea", "cave-space", "cave-dino", "clockwork", "skyship"]
}
```

Each fill carries a short `brief` with a theme-bearing premise so ATG masking gets
brief-declared entities and PS gets a per-theme signature component. Paths are
repo-root-relative, resolved against the manifest file's repo root, consistent with the
existing cwd-relative convention in `tests/unit/test_diversity_leaf.py`.

`lexical_gated_ids` scopes the distinct-2 regression rule (section 2.3, R3) to the 8-11
entries; `clover` and `lantern` are recorded-only until young bands have enough entries to
trust their numbers (WS-0 spec sections 2.6 and 7.4: floors are per-band, and gating a
band on a single sample invites false alarms).

**Known artifact, recorded for honesty:** all three cave fills inherit the skeleton's
`metadata.themes` (`exploration, courage, wonder, nature`) verbatim, so `theme_signature`
overlaps substantially for same-tree pairs even with distinct briefs, inflating
`theme_sim` and hence PS (probe: PS(cave-space, cave-dino) = 0.588 with no briefs; the
per-fill briefs above lower it moderately). This is acceptable because PS never gates and
the baseline records observed values, not ideals; WS-2's theme contract will make
`metadata.themes` theme-specific and the baseline will be legitimately updated then. Do
not "fix" this by special-casing the PS formula; keep the spec 2.8 definition.

### 1.4 Probe record (all numbers referenced in this doc)

Run 2026-07-18 against the shipped Phase 1 code, no briefs (conservative). ATG values in
section 1.1. Structural distances in section 1.2. Lexical values (masked content tokens,
per-node bigrams):

| Fill | distinct-1 | distinct-2 |
| --- | --- | --- |
| cave-sea | 0.335 | 0.883 |
| cave-space | 0.327 | 0.888 |
| cave-dino | 0.347 | 0.879 |
| clockwork | 0.187 | 0.819 |
| skyship | 0.287 | 0.889 |

PS proxy: PS(cave-space, cave-dino) = 0.588, PS(cave-sea, cave-space) = 0.576,
PS(cave-space, cave-space-swap) = 0.966. The 0.70 repeat threshold separates the swap from
every genuine pair with margin on both sides, consistent with the spec's anchors. The
authoritative baseline numbers are whatever the first `--update-baseline` run emits with
the manifest briefs attached; the probe numbers here are the sanity envelope reviewers
should expect that run to land inside (within ~0.05).

### 1.5 How the panel is produced and how it grows

Production procedure for any *new* panel fill (an operator step, never CI):

1. Author the fill through the real path: the `cyo-author` skill fills a committed
   skeleton from a written brief using the active model (this is exactly how the pilot and
   inventory fills were made). For same-tree cells, fill the same skeleton twice or more
   from different briefs.
2. Gate it: `scripts/check_fill_integrity.py <skeleton> <filled>` and
   `scripts/run_story_gate.py <filled>` must both exit 0. Only gate-passing fills enter
   the panel (the panel measures diversity of *shippable* stories, not of rejects).
3. Copy the file into `tests/data/diversity_panel/fills/`, add a `fills` entry with brief
   and provenance, add the new pairs to `atg_pairs`/`cross_tree_pairs` with expected
   verdicts, extend `rar_sequence` if desired.
4. `uv run python scripts/run_diversity_eval.py --update-baseline`, review the printed
   deltas, commit manifest + fixture + baseline in one PR.

The panel is **append-only in review** (WS-0 spec 7.6): entries are added, never retuned
or removed without an explicit justification in the PR that does it. Growth priorities, in
order:

1. **A second same-tree cell on a different topology** (2 fills of one
   `branch_and_bottleneck` 8-11 skeleton, e.g. a parameterized the-sky-ship-stowaway):
   currently every ATG panel pair lives on one `time_cave` tree, which is the single
   biggest overfitting risk (section 7).
2. **Young-band same-tree pairs** (2 fills each for one 3-5 and one 5-8 skeleton): the
   WS-1 prerequisite for calibrating `_BAND_THRESHOLDS`, and what promotes `clover`/
   `lantern`-class entries into `lexical_gated_ids`.
3. **Same-theme cross-tree pairs** (e.g. a dragon fill on two different skeletons) to
   anchor the cross-fingerprint PS branch, which is currently unanchored (spec section 10,
   "minor").

---

## 2. Decision 2: baseline artifact and regression mechanics

### 2.1 `baseline.json` format

One committed file, `tests/data/diversity_panel/baseline.json`, written only by
`--update-baseline`. Deterministic on purpose: keys sorted, floats rounded to 6 decimals,
**no timestamps and no git metadata** inside the file, so regenerating with no code change
is byte-identical and a diff always means a number moved. Pair keys are the two panel ids
sorted lexicographically and joined with `~`.

```json
{
  "schema_version": 1,
  "fills": {
    "cave-sea": {
      "fingerprint": "sha256hex...",
      "band": "8-11",
      "distinct_1": 0.335211,
      "distinct_2": 0.883402,
      "self_bleu_lite": 0.412345,
      "content_token_count": 3512
    }
  },
  "atg_pairs": {
    "cave-sea~cave-space": {
      "verdict": "pass",
      "median_distance": 0.848,
      "p25_distance": 0.815,
      "p10_distance": 0.770,
      "mean_bigram_distance": 0.934,
      "templated_node_count": 0,
      "big_over_uni_ratio": 1.101
    }
  },
  "struct_pairs": {"cave-sea~clockwork": 0.375421},
  "ps_pairs": {
    "cave-sea~cave-space": {
      "leaf_similarity": 0.152, "structural_similarity": 1.0,
      "theme_similarity": 0.571, "perceived_similarity": 0.576, "same_tree": true
    }
  },
  "rar_sequence": 0.2,
  "brief_pairs": [
    {"key": "a dragon who lost his fire~dragon story please",
     "similarity": 0.5, "similar": true}
  ]
}
```

Synthetic entries (`cave-space-swap`, `cave-space-identical`) appear in `atg_pairs` and
`ps_pairs` but not in `fills` (they have no committed file and their lexical profile is
meaningless). `big_over_uni_ratio` (`mean_d_big / mean_d_uni`, 0 when d_uni is 0) is
stored per genuine pair as the paraphrase-gaming tripwire the WS-0 spec 7.1 asks the
baseline to track; in Phase 2 it is recorded and printed, not gated (promotion to a gate
needs per-band baselines, per the spec).

**Authority split (judgment call):** expected ATG verdicts and expected brief-pair
booleans live in `panel.json` (they are *contract*, chosen by a human); observed numeric
values live in `baseline.json` (they are *measurement*, written by the tool). Alternative
(everything in the baseline, verdict flips detected as baseline diffs) rejected: it would
let `--update-baseline` silently bless a verdict flip, which is exactly the regression the
gate exists to catch. With the split, R1 below survives any baseline rewrite.

### 2.2 What `--check` does

1. Load manifest, load fixtures, synthesize variants, compute everything (one
   `PanelResult`).
2. Load `baseline.json`; if missing or `schema_version` unknown, fail with an instruction
   to run `--update-baseline` (rule R6).
3. Evaluate rules R1-R6 below; print every finding with rule id, subject, observed value,
   and allowed bound; exit 1 if any finding exists, else 0.

Checks are **one-sided**: drops fail, improvements pass. An improvement beyond the same
margin prints an informational note suggesting a baseline refresh, so drift upward does
not silently widen the effective allowance for a later drop.

### 2.3 The CI-fail rules (exact)

| Rule | Trips when | Source of truth |
| --- | --- | --- |
| **R1: verdict contract** | any `atg_pairs` entry's computed verdict differs from `expected_verdict` (PASS pairs must PASS, FAIL pairs must FAIL; an expected-PASS pair landing WARN is a fail of R1: the panel is curated so its pairs are unambiguous) | `panel.json` |
| **R2: genuine-pair erosion** | any expected-PASS pair's `median_distance` < baseline value minus 0.05 (absolute) | `baseline.json` |
| **R3: distinct-2 erosion** | any fill in `lexical_gated_ids` has `distinct_2` < 0.90 x baseline value (10% relative) | `baseline.json` |
| **R4: tau-theme flip** | any `brief_pairs` entry's computed `similarity >= 0.35` boolean differs from `expected_similar` | `panel.json` |
| **R5: structural invariants** | any same-fingerprint pair has `structural_distance != 0.0`; any `cross_tree_pairs` pair has `structural_distance <= 0.0`; or any fill's computed fingerprint differs from its baseline fingerprint (a fixture was edited, or the fingerprint algorithm changed; both demand a deliberate `--update-baseline`) | both |
| **R6: panel integrity** | a manifest path is missing/unreadable/fails `coerce_storybook`; a synthetic's `base` id is unknown; a panel item has no baseline entry (forces a baseline update in the same PR that grows the panel); baseline missing/unversioned | both |

Explicitly **never** rules: PS values, RAR, self-BLEU-lite, distinct-1,
`big_over_uni_ratio`, struct-distance magnitudes. All are computed, reported, and
baseline-diffed in the human output, and none can fail a build (WS-0 spec sections 7.5 and
10: only the guard and observed-distribution deltas gate).

### 2.4 Legitimate baseline updates

`--update-baseline` recomputes, prints an old-vs-new delta table for every changed value,
and rewrites `baseline.json`. Procedure and review contract:

- The baseline diff is committed **in the same PR** as the change that legitimately moved
  the numbers (a metric implementation change, a panel addition, a deliberate fixture
  re-authoring). A PR that touches `baseline.json` with no companion change is a review
  red flag by convention.
- The PR description must state which rule's numbers moved and why. `--update-baseline`
  and `--check` are mutually exclusive flags (argparse enforces it), so CI can never
  self-bless: CI runs `--check` only, and a stale baseline fails R2/R3/R5/R6 rather than
  being rewritten.
- Expected verdicts (R1/R4 inputs) can only change by editing `panel.json`, which the
  append-only-in-review convention covers.

---

## 3. Decision 3: metric implementations

All Phase 2 modules are stdlib + Pydantic + sibling `diversity` modules; no new
dependencies, BasedPyright strict, 88 cols, Google docstrings.

### 3.1 `diversity/aggregate.py`

```python
"""ECS, the PS pair score, and repeat-adventure rate (trend-only metrics)."""

_PS_WEIGHT_LEAF: Final[float] = 0.50      # declared priors (WS-0 spec 2.8);
_PS_WEIGHT_STRUCT: Final[float] = 0.30    # revisited only via the Phase 3
_PS_WEIGHT_THEME: Final[float] = 0.20     # calibration PR (section 5.3)
REPEAT_THRESHOLD: Final[float] = 0.70

T = TypeVar("T")

def effective_catalog_size(rows: Iterable[T], key: Callable[[T], str]) -> float:
    """Exponentiated Shannon entropy of the key-partition: exp(-sum p ln p).

    Returns 0.0 for zero rows, 1.0 for a single-key population. The caller
    owns the partition: for served-window ECS the key is skeleton_slug with
    NULL-slug rows mapped to a per-storybook pseudo-slug (WS-0 spec 2.7);
    the WS-2+ (tree, leaf-cluster) unit changes only the key function.
    """

@dataclass(frozen=True, slots=True)
class PairScore:
    leaf_similarity: float
    structural_similarity: float
    theme_similarity: float
    perceived_similarity: float   # the weighted sum, in [0, 1]
    same_tree: bool               # which leaf_similarity branch was taken

def pair_score(
    a: Storybook | Mapping[str, object],
    b: Storybook | Mapping[str, object],
    *,
    brief_a: Mapping[str, object] | None = None,
    brief_b: Mapping[str, object] | None = None,
) -> PairScore:
    """The WS-0 spec 2.8 offline proxy, both branches.

    same fingerprint:  leaf_sim = 1 - median D_uni (leaf_distance_profile);
                       struct_sim = 1.0
    else:              leaf_sim = cosine over masked content-token Counters
                       of the two whole stories (all bodies concatenated,
                       entities = union of both stories' extract_entities);
                       struct_sim = 1 - min(structural_distance(a, b), 1.0)
    always:            theme_sim = jaccard_similarity(
                           theme_signature(brief_a, a.metadata.themes),
                           theme_signature(brief_b, b.metadata.themes))
    PS = 0.50*leaf_sim + 0.30*struct_sim + 0.20*theme_sim
    """

def perceived_similarity(a, b, *, brief_a=None, brief_b=None) -> float:
    """Convenience: pair_score(...).perceived_similarity."""

def repeat_adventure_rate(
    stories: Sequence[Storybook | Mapping[str, object]],
    *,
    briefs: Sequence[Mapping[str, object] | None] | None = None,
    threshold: float = REPEAT_THRESHOLD,
) -> float:
    """Fraction of stories i >= 1 with max_{j<i} PS(s_i, s_j) >= threshold.

    Pure over an already-windowed chronological sequence: the caller (the
    future dashboard loader, or the harness's rar_sequence) applies the
    trailing-20 window; this function never touches the DB. Returns 0.0
    for fewer than two stories. O(m^2) pair scores with m <= 20 is fine.
    """
```

Internals: `_cosine(Counter[str], Counter[str]) -> float` with `math.sqrt`, 0.0 when
either vector is empty. Cosine (not Jaccard) for the cross-tree branch per spec 2.8:
whole-story token sets of two long unrelated stories converge in set space, and counts
carry the discriminating signal at story scale; the spec chose Jaccard at *node* scale for
the opposite reason (explainability over 90-word bodies).

### 3.2 `diversity/lexical.py`

```python
"""distinct-n and self-BLEU-lite: floors checked after the fact, never
optimization targets, never exposed to generation (WS-0 spec 2.6, 7.2)."""

@dataclass(frozen=True, slots=True)
class LexicalProfile:
    distinct_1: float
    distinct_2: float
    self_bleu_lite: float
    content_token_count: int

def lexical_profile(
    story: Storybook | Mapping[str, object],
    brief: Mapping[str, object] | None = None,
) -> LexicalProfile:
    """One fill's lexical guard profile over masked content tokens."""
```

Exact semantics (pin these in tests):

- Token stream: per node, `content_tokens(mask_tokens(body, extract_entities(story,
  brief)))`. Entities from the story's *own* fill (single-story metric, no pair partner).
- `distinct_1` = unique unigrams / total unigrams over all nodes pooled. `distinct_2`
  likewise over bigrams, with bigrams formed **within a node only** (never across node
  boundaries; a phantom bigram spanning two unrelated bodies is noise). Empty story: both
  0.0.
- `self_bleu_lite`: for each node with at least one token, p1 = fraction of its distinct
  unigrams present in the union of all *other* nodes' unigrams; p2 likewise over bigrams
  (nodes with no bigrams use p1 alone); node score = sqrt(p1 * p2), geometric mean, no
  brevity penalty; result = arithmetic mean of node scores. Set semantics rather than
  clipped counts: with 60+ reference nodes the clip is almost never binding, and set
  membership keeps it ~30 lines and trivially explainable. Recorded (baseline + report),
  not gated in Phase 2. Alternative (mean pairwise bigram Jaccard between nodes) remains
  the spec's named fallback if review prefers it; self-BLEU-lite is kept because the plan
  names self-BLEU.

### 3.3 `diversity/panel.py`

The testable core the script wraps. Filesystem-impure (reads committed fixtures), DB-free,
network-free; carries `#ASSUME: external-resources:` RAD tags on the file reads.

```python
class PanelFill(BaseModel):        # id, path, band, skeleton_slug, brief | None, provenance
class SyntheticSpec(BaseModel):    # id, base, kind: Literal["noun_swap", "identity"],
                                   # swaps: dict[str, str] = {}
class AtgPairSpec(BaseModel):      # a, b, expected_verdict: AntiTemplateVerdict
class BriefPairSpec(BaseModel):    # a: dict, b: dict, expected_similar: bool
class PanelManifest(BaseModel):    # schema_version, fills, synthetic, atg_pairs,
                                   # cross_tree_pairs, rar_sequence, brief_pairs,
                                   # lexical_gated_ids  (extra="forbid" throughout)

def load_panel(path: Path) -> PanelManifest
def make_noun_swap_variant(fill: Storybook, swaps: Mapping[str, str]) -> Storybook
    # word-boundary regex per swap key, lowercase and Capitalized forms,
    # bodies only; asserts the result keeps the source fingerprint

@dataclass(frozen=True, slots=True)
class PanelResult:                 # everything computed: per-fill LexicalProfile +
                                   # fingerprint, per-pair AntiTemplateReport,
                                   # struct distances, PairScores, rar value,
                                   # brief-pair similarities

def run_panel(manifest: PanelManifest, repo_root: Path) -> PanelResult
def baseline_payload(result: PanelResult) -> dict[str, object]
    # sorted keys, 6-dp rounding; json.dumps(..., sort_keys=True, indent=2)
    # of this is byte-stable

@dataclass(frozen=True, slots=True)
class RegressionFinding:           # rule: str ("R1".."R6"), subject: str,
                                   # message: str, observed: float | str,
                                   # allowed: float | str

def compare_to_baseline(
    result: PanelResult,
    baseline: Mapping[str, object],
    manifest: PanelManifest,
) -> list[RegressionFinding]       # empty list == gate passes
```

ATG calls inside `run_panel` pass each fill's manifest `brief` through to
`anti_template_verdict(..., brief_a=..., brief_b=...)`, so panel masking matches
production masking (Phase 1 probe masking was brief-less and therefore conservative).

---

## 4. Decision 4: harness, nox, CI

### 4.1 `scripts/run_diversity_eval.py`

Mirrors `run_story_gate.py` in shape: argparse over `main(argv) -> int`, project imports,
prints findings, exit code is the contract.

```text
uv run python scripts/run_diversity_eval.py                      # report + deltas, exit 0
uv run python scripts/run_diversity_eval.py --check              # + rules R1-R6, exit 1 on any
uv run python scripts/run_diversity_eval.py --update-baseline    # rewrite baseline, print deltas
uv run python scripts/run_diversity_eval.py --json out.json      # machine-readable PanelResult
uv run python scripts/run_diversity_eval.py --panel P --baseline B   # path overrides (tests)
uv run python scripts/run_diversity_eval.py --with-judge [--judge-cache PATH]   # section 5
```

- Default run computes and prints the human report (verdict table, lexical table, PS
  matrix, RAR, deltas vs baseline) and exits 0; **only `--check` gates**. Judgment call:
  the WS-0 spec 6.3 read as if the default run failed; resolved in favor of the explicit
  flag so that panel-growth iteration (baseline legitimately absent for new entries) is
  not a wall of red locally, and so the CI invocation is self-documenting. CI always
  passes `--check`.
- `--check` and `--update-baseline` are mutually exclusive (section 2.4).
- `--with-judge` refuses with a clear error when the resolved generation provider is
  `mock` or settings are absent; it is never combined with `--check` semantics (judge
  results affect nothing gate-shaped).
- The spec's `--live-fill` mode is **deferred out of Phase 2** (judgment call): it needs a
  provider and gate loop, its outputs are non-deterministic, and it gates nothing. It
  belongs with the Phase 3/weekly workflow when a provider is wired. The `.gitignore`
  entry for `out/diversity/` lands now regardless, since `--with-judge` writes its cache
  there by default.
- Exit codes: 0 clean, 1 any regression finding or unreadable panel/baseline, 2 argparse
  usage errors (argparse default).

### 4.2 nox session (append to `noxfile.py`)

```python
@nox.session(python="3.12")
def diversity_eval(session: nox.Session) -> None:
    """Run the offline diversity regression gate over the committed panel."""
    session.install("-e", ".")
    session.run("python", "scripts/run_diversity_eval.py", "--check")
```

Consistent with the project convention, no CI workflow invokes nox; the session exists for
local parity (`uv run nox -s diversity_eval`).

### 4.3 CI wiring: a standalone job, per-PR

The backend quality gate in `ci.yml` is **delegated to the org-level reusable workflow**
(`ByronWilliamsCPA/.github/.../python-ci.yml`), so a step cannot be added inside it. The
gate therefore lands as a small standalone job in `ci.yml`, structurally cloned from the
existing `contract` job (harden-runner, checkout, setup-python 3.12, install UV, editable
install, run):

```yaml
  diversity:
    name: Diversity Regression Gate
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - name: Harden the runner
        uses: step-security/harden-runner@...   # same pin as the contract job
        with: { egress-policy: audit }
      - name: Checkout repository
        uses: actions/checkout@...              # same pin
      - name: Set up Python
        uses: actions/setup-python@...          # same pin, python-version: "3.12"
      - name: Install UV
        run: ...                                # same as contract job
      - name: Install backend
        run: uv pip install --system -e .
      - name: Diversity eval (offline panel, regression rules R1-R6)
        run: uv run python scripts/run_diversity_eval.py --check
```

(Exact action pins: copy them from the `contract` job at implementation time; they are
Dependabot-managed and this doc must not freeze them.)

**Per-PR, not nightly.** Reasons: (a) the run is pure Python over ~400 KB of fixtures,
seconds of wall time, no secrets, no network, so there is no cost argument for batching;
(b) a regression gate is only cheap to act on when it fires *on the PR that caused it*; a
nightly red is archaeology; (c) the baseline-update workflow (section 2.4) requires the
gate and the causal change to meet in one PR, which only works if the gate runs on PRs.
Nightly/weekly is reserved for the networked judge run (section 5.4), which is
non-required precisely because it needs secrets and a provider. Making the `diversity` job
a required status check is a branch-ruleset change done at merge time, same as `contract`.

The R1-R6 logic is additionally covered inside the normal pytest job via
`test_diversity_panel.py` (section 6), so the guard is doubly wired exactly as the WS-0
spec 6.4 intended.

---

## 5. Decision 5: judge-model calibration (Phase 3) placement

Per the section 10 critique: run EARLY, once, on the panel, to validate the offline PS
proxy against perception; never CI-gating; minimal surface.

### 5.1 Where the code lives

In `scripts/run_diversity_eval.py` behind `--with-judge`, NOT in the `diversity` package.
The package's import rule (never import `generation`) is preserved; the script is the
composition root and builds the provider itself via the existing seam:

```python
provider = build_provider(settings)   # generation.provider; refuse if resolved
                                      # provider is "mock" (clear error telling the
                                      # operator to set GENERATION_PROVIDER etc.)
```

Anthropic in production, Ollama for homelab-free runs, exactly the pipeline's own settings
(WS-0 spec section 4). The judge loop is sequential over the panel's PS pairs (8 pairs in
v1; no concurrency machinery warranted). The scoring function takes the provider as a
parameter (`_judge_pair(provider, a_text, b_text, band) -> JudgeScore`), so unit tests
drive it with the existing `MockProvider` and zero network.

### 5.2 Prompt, response, cache

- Fixed rubric prompt (a module constant with `RUBRIC_VERSION: Final[int] = 1`): both
  stories' bodies (node order, titles included), the band, and the question "Would a child
  who read story A feel story B is the same adventure? Reply with `SCORE: <0-10>` on the
  first line (0 = a completely new adventure, 10 = the same adventure) and one sentence
  why." Parsed with a regex on `SCORE:`; an unparseable reply is recorded as `null` with a
  warning and never crashes the run.
- Cache file `out/diversity/judge-cache.json` (gitignored), keyed
  `sha256(text_a):sha256(text_b):RUBRIC_VERSION` with the two hashes sorted so (a, b) and
  (b, a) hit the same entry; `text_x` is the canonical `json.dumps` of the story's
  `(node_id, body)` pairs in node order. Reruns are incremental; `--judge-cache` overrides
  the path.

### 5.3 The one-time calibration output, and how it feeds back

`--with-judge` appends a `judge` section to the `--json` output and writes
`tests/data/diversity_panel/calibration.json` (committed, as provenance):

```json
{
  "rubric_version": 1,
  "pairs": [{"key": "cave-sea~cave-space", "ps_proxy": 0.576,
             "judge_score": 2, "judge_reason": "..."}],
  "spearman_rho": 0.83,
  "ps_bins": [{"lo": 0.0, "hi": 0.1, "mean_judge": null}, ...],
  "proposed_repeat_threshold": 0.72,
  "proposed_weights": {"leaf": 0.55, "struct": 0.25, "theme": 0.20}
}
```

- `spearman_rho`: rank correlation of `(ps_proxy, judge_score)` over scored pairs, stdlib
  implementation over ranks (ties by average rank).
- `ps_bins`: the "isotonic in spirit" binned monotone lookup from the WS-0 spec 4.2, ten
  0.1-wide bins.
- `proposed_repeat_threshold`: midpoint between the max PS among pairs the judge scored
  <= 3 and the min PS among pairs scored >= 7; `null` when the two sets overlap (that
  overlap itself is the finding).
- `proposed_weights`: grid search over the weight simplex in 0.05 steps maximizing
  Spearman rho. With 8 pairs this is a smoke calibration, honestly labeled as such in the
  report; it hardens as the panel grows.

**The feedback path is a human PR, not a data dependency.** The constants in
`aggregate.py` (`_PS_WEIGHT_*`, `REPEAT_THRESHOLD`) are code; if the calibration proposes
different values, a maintainer edits the constants in a reviewed PR citing
`calibration.json`, and runs `--update-baseline` in that PR (PS values in the baseline
shift; no gate rule involves them, so nothing else moves). `aggregate.py` never reads
`calibration.json` at runtime; CI has zero dependency on the judge ever having run.
Alternative (auto-loading calibrated weights from the JSON when present) rejected: it
makes metric behavior depend on an artifact CI cannot regenerate, and silently forks
local-vs-CI numbers.

### 5.4 Scheduling

One deliberate early run when a provider is wired (the Phase 3 kickoff task), then
re-run when the panel grows or `RUBRIC_VERSION` bumps. Optionally wrapped later in a
weekly non-required workflow with provider secrets that uploads the JSON as an artifact
(WS-0 spec 6.4); that workflow is not part of Phase 2's deliverable and never blocks
merges.

---

## 6. Test plan

All offline, no network, no DB; BasedPyright strict; committed panel fixtures loaded via
repo-relative paths like the existing `test_diversity_leaf.py`.

**`tests/unit/test_diversity_aggregate.py`**

- `test_ecs_uniform_four_slugs_is_four` (4 equal keys -> 4.0), `test_ecs_single_slug_is_one`,
  `test_ecs_empty_is_zero`, `test_ecs_pseudo_slug_keying_raises_ecs` (NULL-slug rows keyed
  per-storybook raise ECS vs collapsing them to one key).
- `test_pair_score_same_tree_branch_uses_median_leaf_distance` (panel fills: `same_tree`
  True, `structural_similarity == 1.0`).
- `test_pair_score_cross_tree_branch_uses_cosine_and_struct_distance` (cave vs clockwork:
  `same_tree` False, PS in [0, 1]).
- `test_perceived_similarity_orders_swap_above_genuine_pair` (PS(swap pair) > 0.9 >
  PS(genuine pair), the spec's anchor test).
- `test_rar_zero_below_two_stories`, `test_rar_counts_first_repeat_only_once` (sequence
  [A, B, A-swap, A-swap2] -> 2/3), `test_rar_threshold_parameter_respected`.

**`tests/unit/test_diversity_lexical.py`**

- Exact values on a hand-built 3-node story (known token lists, hand-computed distinct-1/2
  and self-BLEU-lite).
- `test_duplicating_a_node_body_lowers_distinct2_and_raises_self_bleu` (monotonicity).
- `test_bigrams_do_not_cross_node_boundaries`.
- `test_empty_story_profile_is_all_zero`.
- `test_entities_are_masked_before_counting` (a name repeated 20 times does not tank
  distinct-1 differently across two fills of different heroes).

**`tests/unit/test_diversity_panel.py`** (the harness acceptance)

- `test_load_panel_parses_committed_manifest` (schema_version 1, all ids unique,
  every path exists).
- `test_make_noun_swap_variant_preserves_fingerprint_and_word_boundaries` ("station" ->
  "burrow", "Station" -> "Burrow", "stationary" untouched; fingerprint unchanged).
- `test_run_panel_committed_expectations_hold` (all five ATG pairs land their expected
  verdicts; every cross-tree distance > 0; RAR equals the baseline value).
- `test_compare_to_baseline_clean_run_has_no_findings` (committed panel + committed
  baseline -> `[]`).
- Doctored-baseline cases in a tmp dir, one per rule: raised `median_distance` -> R2;
  raised `distinct_2` -> R3; edited stored fingerprint -> R5; deleted a baseline entry ->
  R6; edited manifest `expected_verdict` -> R1; edited `expected_similar` -> R4.
- **Harness smoke, subprocess-free:** import `main` from `scripts.run_diversity_eval`;
  `main(["--check"])` returns 0 on the committed tree;
  `main(["--check", "--baseline", str(doctored)])` returns 1;
  `main(["--update-baseline", "--baseline", str(tmp)])` writes a byte-stable file
  (two runs, identical bytes); `main(["--check", "--update-baseline"])` returns 2.
- Judge seam unit test: `_judge_pair` with `MockProvider(responses=["SCORE: 8\nvery
  similar."])` parses to 8; an unparseable response yields `None` without raising; cache
  round-trip hits the cache on the second call (MockProvider call count stays 1).

Coverage note: because the R1-R6 logic lives in `diversity/panel.py` (not the script),
it counts toward the 80% src coverage gate like any package code, and the script stays a
thin argparse shell like `run_story_gate.py`.

---

## 7. Top risks, stated plainly

1. **Panel monoculture (highest).** Every gating ATG pair sits on one skeleton
   (`the-cave-of-echoes`), one topology (`time_cave`), one band (8-11). Thresholds and
   the R2 margin could be accidentally tuned to that tree's prose rhythm. Mitigation:
   growth priority 1 in section 1.5 (a second same-tree cell on a
   `branch_and_bottleneck` tree) is the first post-merge panel PR; the append-only rule
   prevents retuning to fit; the swap-table FAIL pair is synthetic and thus
   tree-independent by construction.
2. **Baseline-update social engineering.** The gate is only as strong as review
   discipline on `baseline.json` and `panel.json` diffs; `--update-baseline` makes a
   regression one flag away from "blessed". Mitigation: the manifest/baseline authority
   split (R1/R4 cannot be silently blessed by a baseline rewrite), mutual exclusion of
   `--check` and `--update-baseline`, byte-stable output so any diff is a real change,
   and the same-PR-with-justification convention in section 2.4.
3. **Unvalidated PS as a de facto gate.** PS/RAR numbers printed on every PR will tempt
   informal gating ("PS went up, block it") before the weights mean anything.
   Mitigation: the report labels the PS/RAR section "trend-only, uncalibrated priors"
   verbatim until `calibration.json` exists with `spearman_rho >= 0.6` (WS-0 spec 7.5);
   the Phase 3 judge run is scheduled EARLY (section 5.4) to shrink this window; no rule
   in section 2.3 reads PS.

Secondary: theme-tag map drift (R4 fails loudly on flips, and boundary fixtures were
deliberately excluded); `metadata.themes` inheritance inflating same-tree theme_sim
(recorded artifact, section 1.3, resolved by WS-2's theme contract, PS trend-only
meanwhile).

---

## 8. Definition of done (Phase 2)

- `aggregate.py`, `lexical.py`, `panel.py` implemented to the section 3 signatures; all
  section 6 tests green; 80% coverage holds.
- `tests/data/diversity_panel/` committed: manifest (7 fills + 2 synthetics + 5 ATG pairs
  + 3 cross-tree pairs + 8 brief pairs + RAR sequence), 7 fixture copies, baseline
  written by `--update-baseline` on the implementer's machine and sanity-checked against
  the section 1.4 probe envelope.
- `scripts/run_diversity_eval.py` with the section 4.1 flag set; `--check` exits 0 on the
  committed tree and 1 on each doctored case.
- `noxfile.py` `diversity_eval` session; `ci.yml` `diversity` job green on the PR;
  `out/diversity/` gitignored.
- The judge path (`--with-judge`) implemented and unit-tested against `MockProvider`,
  refusing mock/unset providers at runtime; `calibration.json` NOT yet committed (Phase 3
  produces it).
- `ws0-diversity-metrics-design.md` section 10 Phase 2 line marked delivered with a
  pointer to this doc; `docs/planning/story-flexibility-plan.md` WS-0 status updated.

---

## 9. Supervisor critique and acceptance (Opus oversight, 2026-07-18)

This design was authored by a Fable subagent under the Fable-design -> Opus-oversee ->
Sonnet-implement loop. I probed its central claims against the shipped Phase 1 package
before accepting it. Findings:

**Accepted as-is.** The design is implementation-ready and its numbers reproduce. The two
structural choices that matter most are both correct:

1. **The authority split (section 2.1)** is the load-bearing decision. Expected verdicts
   and expected brief-pair booleans live in `panel.json` (contract, human-authored);
   observed numbers live in `baseline.json` (measurement, tool-written). Without this
   split, `--update-baseline` could silently bless a verdict flip, which is the exact
   regression the gate exists to catch. R1 and R4 surviving any baseline rewrite is the
   whole point; keep it.
2. **The zero-new-generation finding (section 1.1)** is real and I re-verified the
   mechanism: `structure_fingerprint` excludes bodies and ending titles, so the
   parameterization pass that produced the pilot fills left the fingerprint of
   `the-cave-of-echoes` intact across all three themes. Three same-tree fills already exist
   in git. Phase 2 ships with no operator fill run required, which unblocks it in this
   (import-less) environment.

**One elevated risk, one instruction to the implementer.** The design correctly names
panel monoculture as risk 1 (section 7): all five gating ATG pairs sit on one skeleton,
one topology (`time_cave`), one band. I am elevating its stated mitigation from a
"first post-merge PR" to a **named follow-up that must be filed as a tracked task the
moment Phase 2 merges**, so it does not evaporate. It is not a Phase 2 blocker (the
synthetic swap pair is tree-independent by construction, and the genuine PASS pairs are
real gate signal today), but the second same-tree cell must land on a different topology,
and I want it prioritized toward a `branch_and_bottleneck` 8-11 skeleton so the gamebook
work (WS-2 / Pathfinder exploration) and the panel-diversification work share a fixture.

**Scope confirmations for the Sonnet implementer:**

- Implement exactly the section 3 signatures. Do not add a gate rule that reads PS, RAR,
  self-BLEU-lite, distinct-1, or `big_over_uni_ratio`; section 2.3's "never" list is a hard
  constraint, not a default. The judge path is unit-tested against `MockProvider` only and
  must refuse a mock/unset provider at runtime.
- The `diversity` CI job clones the `contract` job's action pins verbatim
  (`harden-runner@bf7454d0...` v2.20.0, `checkout@9c091bb2...` v7.0.0,
  `setup-python@ece7cb06...` v6.3.0, `setup-uv@11f9893b...` v8.3.2). It installs with
  `uv pip install --system -e .` (the `contract` job uses `uv sync --extra api`; the
  diversity gate needs the base package only, but must be able to `import cyo_adventure`,
  so the editable install is correct). Do not freeze pins beyond copying what is current.
- `panel.py` must not import `db`, `generation`, or `sqlalchemy`; the judge seam lives in
  the script. RAD-tag the fixture file reads in `panel.py` per the file's own note.
- Green bar before handing back: `uv run ruff check .`, `uv run ruff format --check .`,
  `uv run basedpyright src/ tests/`, `uv run pytest` with coverage holding at 80%, and
  `uv run python scripts/run_diversity_eval.py --check` exiting 0 on the committed tree.

Verdict: **accepted, proceed to implementation.** The design does not need another Fable
pass.
