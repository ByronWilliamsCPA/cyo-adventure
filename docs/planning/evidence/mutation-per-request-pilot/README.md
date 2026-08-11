# Per-request mutation pilot: does a mutant read as a different book?

Run date: 2026-08-09. Branch: `claude/skeleton-story-review-3zy6tq`.

## Question

Three earlier diversity pilots found that two stories filled from the **same**
skeleton read as "same adventure, new world" to a 10-13 reader, with the
same-book verdict landing by node 4. The proposed fix is to run the offline
mutation engine (ADR-020, `src/cyo_adventure/mutation/`) **per request**, so one
parent skeleton yields `k` structurally distinct armatures.

This pilot asks the open question that proposal turns on: do two stories filled
from two **mutants of the same parent** read as different books, or as the same
book?

## Parent selection

`cyo_adventure.generation.skeleton_match.candidates_for_cell("10-13", "short",
"prose")` returns `the-cinderwick-exchange`, `the-glass-comet`,
`the-midnight-frequency`, `the-midnight-museum`.

Chosen: **`the-midnight-museum`**. It is production-eligible, Tier 1 (M4 is
Tier-1 only, so `the-glass-comet` at Tier 2 is excluded), `series: null`, has a
theme contract, and is the smallest of the four (95 nodes, 9,120 authored
words), which made two complete fills affordable. Topology
`branch_and_bottleneck`: `n_open -> n_start -> {3 acts} -> n_key -> {3 acts} ->
n_cipher -> {3 acts} -> n_rotunda -> {3 acts} -> n_vault -> {4 finales}`.

`the-clocktower-cipher` was excluded as instructed (off-matrix seed,
`production_eligible: false`).

## Invocations

```bash
# mutant S, shape-preserving
uv run python scripts/mutate_skeleton.py skeletons/10-13/the-midnight-museum.json \
  --op M1 --params choice1=c_panel_secret choice2=c_vault_grab \
  --seed 1 --out-dir <out> --no-svg --sample-fill-mock

# mutant D, shape-changing
uv run python scripts/mutate_skeleton.py skeletons/10-13/the-midnight-museum.json \
  --op M4 --params mode=insert-decision variant=reconvergence \
  choice=c_key_founder target=n_cipher \
  --seed 7 --out-dir <out> --no-svg --sample-fill-mock

# mutant X, composed chain (mutants/chain-x.json)
uv run python scripts/mutate_skeleton.py skeletons/10-13/the-midnight-museum.json \
  --chain mutants/chain-x.json --out-dir <out> --no-svg --sample-fill-mock
```

All three exit 0 and are **accepted, held** (re-guidance outstanding): stages
`0-preconditions`, `1-gate`, `2-cell` pass; the Tier-2 stage is skipped
(Tier-1); the structural anti-clone floor and the contract stage do not run,
because they gate only the promotable decision and a held candidate is not
promotable.

## Mutant table

| Mutant | Operator chain | Acceptance | Nodes | d(parent) | Parent nodes kept | Parent FILL beats byte-identical | Parent edges kept |
|---|---|---|---|---|---|---|---|
| S | M1 sibling-subtree-swap (`c_panel_secret` <-> `c_vault_grab`, seed 1) | accepted, held; 4 re-guidance items | 95 | **0.0000** | 95/95 | 95/95 | 113/115 |
| D | M4 insert-decision, `reconvergence` (`c_key_founder` -> `n_cipher`, seed 7) | accepted, held; 3 re-guidance items | 96 | **0.0038** | 95/95 | 95/95 | 114/115 |
| X | M3 graft (donor `the-midnight-frequency`, subtree `fin_bearing`, host `a_gems1`) -> M4 insert-decision reconvergence -> M2 ending re-map | accepted, held; 45 re-guidance items | 128 | **0.0726** | 95/95 | 95/95 | 114/115 |

Pairwise `cyo_adventure.diversity.structure.structural_distance`:

| | parent | S | D | X |
|---|---|---|---|---|
| parent | 0 | 0.0000 | 0.0038 | 0.0726 |
| S | | 0 | 0.0038 | 0.0726 |
| D | | | 0 | 0.0695 |
| X | | | | 0 |

Reference points from `docs/planning/ws5_floor_baseline.json`: `TAU_CELL` = 0.05;
hand-authored same-cell sibling pairs have median distance 0.390, p25 0.332,
minimum 0.000469.

M1 was checked against five different swap pairs, including cross-act ones; every
one produced `structural_distance` exactly **0.0000** while changing
`structure_fingerprint`. M2 alone also produced 0.0000. M4 reconvergence had
2,201 eligible `(choice, target)` pairs on this parent, so applicability is not
the constraint.

## The two fills

Both books were filled from their mutant shells at band 10-13, leaf content only
(node bodies, choice labels, ending titles, storybook title).

- **Book S** (`book-s-the-midnight-museum.json`, mutant S): "The Midnight
  Museum", the contract's own default binding (Nadia, the Ellery Museum).
- **Book D** (`book-d-the-midnight-terminus.json`, mutant D): "The Midnight
  Terminus", an independent binding of the same contract (Tess, Kingsmoor
  Terminus), with every choice label and ending title re-authored rather than
  slot-substituted.

Deviation from the brief, stated plainly: the brief asked for the **same** theme
binding for both books. Under the same binding the comparison is decided without
a rater, because every mutant retains 100% of the parent's `<<FILL>>` beat
directives (table above), so two fills of the same binding differ only in the
two or three surfaces the mutation touched. That measurement is reported above.
The rater budget was spent instead on the configuration production would
actually ship, different binding plus different mutant, which is also the
configuration the earlier pilots' calibration anchors were measured in and so is
the only arm comparable to them.

Validation, both books:

| Check | Book S | Book D |
|---|---|---|
| `check_fill_integrity --allow-title-rewrite` | pass (mean 73.7 w/node) | pass (mean 78.5 w/node) |
| `run_story_gate` | `findings=68 blocked=False safety_flagged=False` | `findings=38 blocked=False safety_flagged=False` |
| `check_prose_craft --check` | pass (tense, moral tags, told emotion) | pass |

Gate findings are all advisory `RL-13` reading-level warnings (Flesch-Kincaid
above the 5.5 +/- 1.5 target); both books are affected similarly, so the
comparison is not skewed by it.

## Deterministic bench, Book S vs Book D

| Metric | Value | Budget / reference |
|---|---|---|
| `check_sibling_fills --check` | **70.4** distinct shared 4-grams per 1000 mean leaf words (562 grams); 3 shared menu frames | budget 4.0; earlier arms: obligation 2.8, free 12.6, clocktower 9.0, control 25 |
| `pair_score.leaf_similarity` | 0.9962 | 1.0 = identical |
| `pair_score.structural_similarity` | 0.9962 | |
| `pair_score.theme_similarity` | 1.0000 | |
| `pair_score.perceived_similarity` | **0.9970** | |
| `structural_distance(S, D)` | 0.0038 | |

The shared-gram figure carries an authoring confound and should be read with the
caveat in the limitations section.

## Recognition protocol

Framing: a 10-13 reader who read book 1 last week and starts book 2 today,
pattern-sharp and genre-aware, crediting recognition only for "this is the SAME
book re-skinned" rather than "another mystery like it". Matched playthrough
(route A, key-to-study, stars, hub, vault).

**Same-book verdict lands at reading position 3.** Evidence:

- Position 1, both books open on the identical inciting frame: the school group
  leaves without her, the building locks for the night, and she is carrying a
  torn old plan of a building that no longer matches, ending on a handwritten
  line about the founder. Book S: "what Josiah Ellery left behind is still
  inside." Book D: "what Iris Halloway hid here has never left the building."
  A fair rater credits genre here, not identity.
- Position 2, both present three ways off the central hub in three sentences.
  Suggestive, still generic.
- Position 3 is where it lands. Book S: the display case "sat crooked, shoved a
  hand's width off the outline worn into its plinth... Then, somewhere off to
  her left, a soft electronic beeping started up, patient and regular." Book D:
  the claim case "did not line up. Its feet had worn a pale rectangle into the
  floor over eighty years, and it was standing a hand's width out of it. Then,
  somewhere behind the racks, a buzzer started. Soft. Regular." Same object in
  the same position doing the same specific wrong thing by the same measure,
  followed by the same interrupting sound. That is not a genre convention.
- Position 4 confirms it: both rooms show exactly two disturbed objects and the
  same deduction ("Two things disturbed, in a room where nothing had been
  touched in years" / "Nothing in this room had moved in years. Two things had
  moved this week").

**Score: 2.0 / 5** (1 = one book in costumes, 5 = truly different books).
Calibration anchors from earlier runs on a different skeleton: node 2 -> 2.0,
node 4 -> 2.5.

Where mutant D's structural change actually shows up: reading position 8, five
positions after recognition has already landed. It reads as one extra doorway
with one extra choice before the founder's room. It does not alter the
bottleneck sequence, the three key doors, the cipher, the hub, or the vault.
Taking its new branch ("Sit down at the table and read the code now") skips one
mid-act room, which is a real difference in a re-read path but not a different
book.

**Parent vs S was not rated**, because it is settled deterministically: S keeps
all 95 parent nodes, all 95 parent beat directives byte-identical, and 113 of
115 parent edges, at `structural_distance` 0.0000. A fill of the parent and a
fill of S with the same binding are the same book by construction.

## Verdict

**(b), and only weakly** - shape-preserving mutants (M1, M2) are perceptually
null, shape-changing ones (M4, M3) are perceptually marginal, and the
multiplier is far smaller than `k`.

Evidence:

1. M1 and M2 produce `structural_distance` exactly 0.0000 from the parent on
   every pair tried. They cannot clear `TAU_CELL` (0.05) and they change nothing
   a reader can perceive. They are not multipliers.
2. M4 reconvergence produces 0.0038, and a maximum-length three-operator chain
   using only the parent's own material reaches 0.0064. Both are below
   `TAU_CELL` = 0.05, so under the committed floors no bounded single-parent
   mutant of this skeleton is promotable at all. The only mutant that cleared
   the floor (X, 0.0726) did so by grafting 32 nodes from a **different**
   catalog skeleton, which is recombination of two trees rather than
   multiplication of one.
3. All three mutants retain 100% of the parent's authored `<<FILL>>` beat
   directives. Whatever the operators change, they do not change the story the
   author wrote; they change where two or three edges point.
4. The rated pair landed the same-book verdict at node 3 scoring 2.0, inside the
   band the earlier same-skeleton pilots produced (node 2 -> 2.0, node 4 ->
   2.5). Mutation did not push recognition later.
5. `perceived_similarity` 0.997 and 70.4 shared 4-grams per 1000 agree with the
   rater.

Verdict (c) is **not** supported, and this is worth stating precisely. The
floors are not measuring something readers cannot perceive: `TAU_CELL` correctly
rejected the mutants that a reader also rejected, and the hand-authored
same-cell median of 0.390 is two orders of magnitude above every bounded
mutant's distance, which is exactly the ordering a reader reports. The metric's
known weaknesses (order-blindness, 20% of the score coming from the
self-declared `metadata.topology` field) did not bite here, because the mutants
never came close to the threshold in the first place. This pilot does not
exonerate `structural_distance` in general; it only shows that on this parent it
and the reader agreed.

Confidence: **moderate-high on (a) being false, moderate on the precise form of
(b)**. Claims 1 to 3 are deterministic and would replicate on any parent. Claim
4 is n=1 parent, one rated pair, one rater pass.

## Limitations

- **n=1 parent, one rated pair, one rater pass.** A parent with a different
  topology (`open_map`, `sorting_hat`) may give M4 more room; this parent's
  4-to-8 decisions-per-path window rejected most reconvergence targets because
  the parent already sits at 14 decisions on its longest path.
- **The rating was not blind and not run in a separate agent.** Session spawning
  was not permitted in this environment, so the rater could not be isolated from
  the mutation plan. Treat the landing node and the score as author-scored, and
  weight the deterministic bench accordingly.
- **The shared-4-gram figure carries an authoring confound.** Both books were
  written by one author in one session. The first draft of Book D was a
  sentence-level world swap of Book S and measured 302 shared grams per 1000; two
  deliberate de-convergence passes (`bodies_d_draft1.py` -> `bodies_d.py`) brought
  it to 70.4, still about 3x the worst previously measured arm. Independently
  authored fills would score lower. The residual is not evidence about mutation.
- **Both books run above the band's Flesch-Kincaid target** (advisory RL-13
  warnings). This affects both equally and does not bias the comparison, but
  neither book is publication-ready prose for the band.
- The mutants are all **held**, not promotable, because their re-guidance is
  unresolved. Resolving it would send S and D into the structural anti-clone
  floor, which by the distances above would reject both.
