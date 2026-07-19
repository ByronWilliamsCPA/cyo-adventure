---
schema_type: planning
title: "WS-0 Design: Diversity Metrics and Evaluation Harness"
description: "Implementation-ready design for the WS-0 workstream of the story flexibility plan:
  offline-computable perceived-similarity metrics, the anti-template guard, the request-time
  similarity query WS-4 consumes, the diversity eval harness, and the CI regression gate."
tags:
  - planning
  - architecture
  - generation
  - metrics
status: proposed
owner: core-maintainer
authors:
  - name: "Byron Williams"
purpose: "Give Sonnet engineers a directly implementable spec for the diversity metric suite,
  including exact formulas, module and function signatures, thresholds grounded in an empirical
  probe of the two pilot fills, the harness and CI gate, and the validity risks and their guards."
component: Strategy
source: "story-flexibility-plan.md section 5 (WS-0); storybook/models.py; db/models.py
  (StorybookVersion); generation/skeleton_match.py; scripts/run_story_gate.py and
  check_fill_integrity.py; out/pilot/ (the two proven fills of the-cave-of-echoes); an offline
  probe run 2026-07-18 over those fills to calibrate thresholds."
---

# WS-0 Design: Diversity Metrics and Evaluation Harness

> **Status: proposed, ready for review.** This is a design spec, not an implementation. It defines
> the WS-0 deliverable from [story-flexibility-plan.md](story-flexibility-plan.md): the metric
> suite that makes "each story must feel like a new adventure" falsifiable, the anti-template
> guard that fails a dog-for-cat noun swap, and the request-time query WS-4's escalating selection
> consumes. All thresholds in section 3 are grounded in a probe run against the two committed
> pilot fills (`out/pilot/fills/`); the probe results are reproduced in section 3.4.

---

## 0. Scope, constraints, and the two-layer rule

The objective is perceptual (plan section 1): no reader should feel two stories are similar. The
tree (structure) may be shared; the leaves (per-node prose) must genuinely differ. A dog-for-cat
noun swap is the canonical failure.

Hard constraints this design is built around:

1. **CI and unit tests make no network calls** (tests/CLAUDE.md). Therefore the suite is split
   into two layers with a bright line between them:
   - **Offline core (CI-gating):** structural graph features, lexical distances, and
     proper-noun-normalized leaf overlap. Pure functions over Storybook JSON. Stdlib plus
     `networkx` (already a dependency, used by the validator). This layer stands alone: the
     anti-template guard, the structural metrics, the lexical guards, the aggregate metrics, and
     the request-time query are ALL offline-core.
   - **Optional enhancement layer (never CI-gating):** judge-model perceived-similarity scoring
     and (secondarily) embedding distance. Runs only via explicit harness flags, batch/offline,
     through the existing generation provider abstraction. Used to calibrate the offline proxy,
     never to gate a build.
2. **No new dependencies.** The core uses `re`, `math`, `statistics`, `collections`, `hashlib`,
   `json`, `dataclasses`, plus `networkx` (present) and Pydantic (present) for report models. No
   NLTK, no numpy, no scikit-learn, no embedding client. Rationale per metric is inline below.
3. **Project standards:** BasedPyright strict, Ruff, 88-col Python, Google docstrings, RAD tags on
   every I/O boundary (`src/CLAUDE.md`), project exceptions from `core/exceptions.py`, pure/impure
   split in the style of `skeleton_match.py` (pure scoring core, one thin impure DB loader).

Terminology used throughout:

- **Fill:** a filled Storybook (nodes carry prose bodies), as stored in `StorybookVersion.blob`.
- **Same-tree pair:** two fills whose structure fingerprints (section 2.4) are equal, in practice
  two fills of one skeleton; node ids correspond 1:1, so leaves can be compared per node.
- **Cross-tree pair:** two fills of different skeletons; leaves are compared at whole-story level.
- **Cell:** a `(band, length, style)` triple, exactly as in `skeleton_match.py`.

---

## 1. Package layout and integration points

### 1.1 New package: `src/cyo_adventure/diversity/`

```text
src/cyo_adventure/diversity/
├── __init__.py       # public API re-exports (the names below, nothing else)
├── normalize.py      # tokenization, entity extraction, entity masking, theme signatures
├── leaf.py           # per-node leaf distance, leaf distance profile, anti-template guard
├── structure.py      # structure fingerprint, structural feature vector, structural distance
├── lexical.py        # distinct-n, self-BLEU-lite, cross-node repetition (guards, not goals)
├── aggregate.py      # perceived similarity, repeat-adventure rate, effective catalog size
├── report.py         # Pydantic report models (mirrors validator/report.py style)
├── history.py        # HistoryEntry + load_family_history() (the ONLY impure module)
└── query.py          # pure score_history() + thin async similarity_context() wrapper
```

Import discipline (this is what prevents the circular import):

- `normalize`, `leaf`, `structure`, `lexical`, `aggregate`, `report`, `query` (the pure part)
  import **only** stdlib, `networkx`, Pydantic, and `cyo_adventure.storybook.models` /
  `cyo_adventure.core.exceptions`. They never import `db`, `generation`, or `sqlalchemy`.
- `history.py` imports `db.models` and SQLAlchemy (exactly like the impure half of
  `skeleton_match.py`). It is the single I/O boundary and carries the RAD tags.
- `generation.skeleton_match` is **not** modified by WS-0 and never imports `diversity`. WS-4
  will extend selection by having the caller (`story_requests/authoring_plan.py`) call
  `diversity.query.similarity_context(...)` and pass the resulting values into (an extended)
  `select_skeleton_for_cell`. Data flows caller -> both modules; neither imports the other.
  `skeleton_match` may later take a `dict[str, float]` of similarity penalties rather than a
  `SimilarityContext` object, keeping even the type dependency one-way. That choice belongs to
  WS-4; WS-0 only guarantees `diversity` has no import edge toward `generation`.

Alternative considered: putting the metrics under `validator/` (they gate quality). Rejected:
the validator is the safety gate with block semantics and its own report vocabulary; diversity is
a quality/selection concern with different consumers (harness, WS-4, dashboards) and must be
importable without dragging in gate policy. A sibling package keeps both honest.

### 1.2 Input type

Every pure function takes either a validated `Storybook` (from `storybook.models`) or a plain
`dict[str, object]` blob and validates it at the boundary:

```python
def coerce_storybook(blob: Mapping[str, object] | Storybook) -> Storybook:
    """Validate a raw blob into a Storybook, or pass a Storybook through."""
```

lives in `diversity/__init__.py` (or `normalize.py`) and raises the project `ValidationError` on
schema failure. Rationale: `StorybookVersion.blob` is loosely-typed JSONB; the metric suite must
not crash on a malformed historical row (see section 5.4 for the degraded-row policy in the
query path), and pure metric functions should assume a valid model.

---

## 2. Metric definitions (offline core)

Each metric states: formula, data source, and where it is consumed. Section 3 covers the
anti-template guard in full detail; section 4 covers the headline metric's judge-validated form.

### 2.1 Normalization primitives (`normalize.py`)

All lexical metrics share one normalization pipeline. Exact definitions:

**Sentence split.** `re.split(r"[.!?]\s+", text)`. This is deliberately crude; it only needs to
identify sentence-initial vs sentence-medial capitalization, not linguistic sentences.

**Word tokens.** `re.findall(r"[A-Za-z][A-Za-z'-]*", text)`. Numbers and punctuation are dropped;
apostrophes and hyphens stay word-internal ("kestrel's", "repair-drone").

**Stopword list.** A frozen module-level set of ~120 English function words (articles, pronouns,
auxiliaries, prepositions, conjunctions), committed in `normalize.py`. No NLTK. "Content tokens"
means tokens not in this set after lowercasing and entity masking.

**Entity extraction (NER-free), `extract_entities(story, brief) -> frozenset[str]`.** The union
of:

1. **Brief-declared entities:** from the theme brief when available: `protagonist.name`, every
   name in `anchor_context.character_names`, and every multi-token value of any brief field that
   looks like a name (single capitalized token or Title Case phrase). The brief travels with the
   job (`authoring_metadata["theme_brief"]`) and with history rows via `Concept.brief`; for a
   bare blob with no brief this source is empty.
2. **Medial-caps tokens:** every token that appears with an uppercase first letter in
   sentence-medial position (index > 0 within its split sentence) anywhere in either story of the
   pair, lowercased. This catches "Priya", "Pip", "Halcyon", "Comet", "Redwall" without NER.
3. **Sentence-initial recovery:** a sentence-initial capitalized token whose lowercase form is
   already in the medial-caps set from the *other* positions ("Priya drifts..." at node start).
   This is automatic because set membership is checked on the lowercased token; no extra rule is
   needed beyond taking the union over both stories.

**Entity masking, `mask_tokens(text, entities) -> list[str]`.** Lowercase, tokenize, and replace
every token whose lowercase form is in the entity set with the single placeholder token `<ent>`.
All entities collapse to one placeholder, deliberately: "Priya" vs "Theo" must contribute zero
distance. Alternative considered: role-preserving placeholders (`<hero>`, `<companion>`, keyed
from the brief). Rejected for v1: it needs reliable role attribution, and the single-placeholder
form is strictly more conservative (it can only *lower* measured distance, never inflate it, so
it cannot create false PASSes; see section 3.3).

Known limitation, accepted: **common-noun theme swaps are not masked** ("the station" -> "the
cave"; "drone" -> "dog"). The probe (section 3.4) shows this residue is small: a 18-substitution
common-noun swap over 90-word nodes moves mean node distance only to 0.055 (0.128 unmasked),
still an order of magnitude below the FAIL threshold. The margin absorbs it. WS-2's theme
contract will later supply slot values (world, props) as additional entities for masking, which
tightens this further at no design change.

**Theme signature, `theme_signature(brief, metadata_themes) -> frozenset[str]`.** For request-vs-
history theme matching (section 5), where nouns are the *signal*, not noise:

```text
T = content-unigrams(premise) ∪ content-bigrams(premise) ∪ {t.lower() for t in metadata.themes}
```

with bigrams encoded as `"w1 w2"` strings. Entities are NOT masked here; "dragon", "dinosaur",
"space station" are exactly what theme similarity is about.

### 2.2 Per-node leaf distance (`leaf.py`)

The primitive under the anti-template guard and the leaf-diversity metric.

For a same-tree pair `(a, b)` with shared node ids `N`:

```text
E        = extract_entities(a, brief_a) ∪ extract_entities(b, brief_b)
U_x(n)   = set(content tokens of mask_tokens(body_x(n), E))         # unigrams
B_x(n)   = set(bigrams of mask_tokens(body_x(n), E))                # ALL tokens, incl. stopwords
D_uni(n) = 1 - |U_a(n) ∩ U_b(n)| / |U_a(n) ∪ U_b(n)|                # Jaccard distance
D_big(n) = 1 - |B_a(n) ∩ B_b(n)| / |B_a(n) ∪ B_b(n)|
```

Both distances are defined as 0.0 when both sets are empty (two empty bodies are identical).
`D_uni` is the **primary** distance; `D_big` is the secondary anti-paraphrase signal (section 7.1)
and is computed over all tokens because function-word *order* patterns ("she has to choose a",
"there is no time left") are precisely what survives a synonym pass.

`leaf_distance_profile(a, b, brief_a, brief_b) -> LeafDistanceProfile` returns per-node
`(node_id, d_uni, d_big, word_count_a, word_count_b)` plus the summary statistics (mean, median,
p10, p25, min, max of `d_uni`).

**Distance function choice.** Alternatives considered:

- *Jaccard over content unigrams (chosen, primary).* Set semantics ignore length imbalance
  between two fills of one node (92.7 vs 75.6 mean words/node in the pilot), are trivially
  explainable in a report ("these nodes share 94% of their vocabulary"), and gave the widest
  observed separation in the probe (0.685 min genuine vs 0.246 max swap).
- *Cosine over content-token counts.* Also probed; separation is real but narrower (0.430 min
  genuine vs 0.167 max swap) because repeated common verbs dominate the counts. Kept out.
- *Normalized edit distance / difflib ratio.* Sensitive to reordering in the wrong direction (a
  reordered template scores as different) and O(len^2) per node. Rejected.
- *Character n-gram cosine.* Robust to morphology but blind to the noun-swap failure unless
  masked anyway, and harder to explain. Rejected.

### 2.3 Cross-fill leaf diversity for one tree

The direct "leaf diversity of a skeleton" signal (plan section 5, supporting metrics). For the
set of fills `F = {f_1..f_k}` of one skeleton (k >= 2):

```text
leaf_diversity(F) = mean over unordered pairs (f_i, f_j) of median_n D_uni(n)
```

Reported per skeleton per cell by the harness and, over `StorybookVersion` history, per family.
No threshold gates this number directly; it trends on the dashboard and feeds the aggregate.

### 2.4 Structural fingerprint and structural distance (`structure.py`)

**Fingerprint (identity).** Reuse the `check_fill_integrity.py` convention: strip every node
`body` and every choice `label`, canonicalize (`json.dumps(..., sort_keys=True)` after also
dropping `title` and each `ending.title`, which are leaf content), and hash:

```text
structure_fingerprint(s) = sha256(canonical_structure_json(s)).hexdigest()
```

Two fills of one skeleton have equal fingerprints provided the fill touches only bodies and
choice labels, which is the shipped `fill.md` contract (`generation/templates/fill.md` instructs
the automated fill to rewrite every choice label per theme, so labels cannot be relied on to stay
byte-identical across fills). Titles and choice labels are excluded from the fingerprint because
both are leaf content the automated fill rewrites per theme: the pilot's parameterized skeleton
rewrites ending titles per theme, and the shipped fill contract rewrites every choice label; both
are leaves, not structure (WS-0 labels-are-leaves decision,
`docs/planning/ws0-label-fingerprint-evaluation.md`). `sha256` per FIPS guidance (no MD5).

**Feature vector (graded distance).** `structure_features(s) -> StructureFeatures`, computed
with one `networkx.DiGraph` built from choices:

| Feature | Definition |
| --- | --- |
| `n_nodes` | `len(nodes)` |
| `n_endings` | count of `is_ending` nodes |
| `n_choices` | total choice edges |
| `mean_branching` | mean out-degree over decision nodes (out-degree >= 2) |
| `decision_ratio` | decision nodes / non-ending nodes |
| `max_depth` | longest shortest-path from `start_node` (BFS; cycles safe) |
| `min_ending_depth` | shortest path from start to any ending |
| `reconvergence_ratio` | nodes with in-degree >= 2 / `n_nodes` |
| `n_variables`, `n_conditions`, `n_effects` | Tier-2 state surface counts |
| `ending_kind_hist` | 6-bin normalized histogram over `EndingKind` |
| `valence_hist` | 3-bin normalized histogram over `Valence` |
| `topology` | the declared `metadata.topology` (categorical) |

**Distance.**

```text
struct_dist(a, b) = 0.5 * canberra_mean(numeric features)
                  + 0.3 * 0.5 * (L1(kind_hist) / 2 + L1(valence_hist) / 2)
                  + 0.2 * [topology_a != topology_b]

canberra_mean(x, y) = mean over features i of |x_i - y_i| / (x_i + y_i)   (0 when both are 0)
```

Range [0, 1]. Canberra is chosen over Euclidean/L1 because features live on wildly different
scales (node counts 8..64, ratios 0..1) and Canberra self-normalizes per feature without
maintaining a scaling table. Alternative considered: graph edit distance (`networkx` has an
approximation). Rejected: exponential worst case, unstable approximations, and the feature vector
already answers the actual product question ("does this branch differently?") explainably.

Invariant the tests pin: `struct_dist(a, b) == 0.0` exactly when fingerprints are equal, and
`> 0` for any two current skeletons in `skeletons/8-11/` (they differ in at least node count or
ending histogram).

### 2.5 Thematic proper-noun overlap

For two *fills* (post-hoc, not request-time):

```text
noun_overlap(a, b) = |ents(a) ∩ ents(b)| / |ents(a) ∪ ents(b)|      (Jaccard, 0 when both empty)
```

where `ents(x) = extract_entities(x, brief_x)`. Target for a family's consecutive stories: ~0
(plan section 5). A nonzero overlap between consecutive same-family stories is a WARN in the
family report (deliberate series continuations share cast legitimately; `metadata.series` set on
both stories suppresses the warning).

### 2.6 Lexical guards (`lexical.py`), guards not goals

These exist to catch degenerate generation and metric gaming, cross-checked with RL-13; they are
never optimization targets and never appear in fill prompts (section 7.2).

- **distinct-n (n = 1, 2)** for one fill: `distinct_n = |unique n-grams| / |total n-grams|` over
  the concatenated masked content tokens of all bodies. Floor-guarded per band (young bands have
  legitimately smaller vocabularies; baselines are recorded per band by the harness, section 6).
- **self-BLEU-lite** for one fill: for each node, modified n-gram precision (n = 1, 2) of its
  masked token list against the union of all *other* nodes' n-grams, geometric-mean combined, no
  brevity penalty, averaged over nodes. High self-BLEU means the story repeats itself node to
  node. Implemented in ~30 lines of stdlib; full BLEU with smoothing is not needed for a
  monotone within-story repetition signal. Alternative considered and available if review
  prefers it: mean pairwise bigram Jaccard between nodes ("cross-node repetition rate"),
  which is simpler still; self-BLEU-lite is chosen only because the plan names self-BLEU and
  reviewers can map it to literature.

### 2.7 Aggregate: effective catalog size (`aggregate.py`)

Over a serving window (default 90 days) and a scope (a cell, or a family):

```text
p_i  = share of served StorybookVersion rows with skeleton_slug == slug_i
ECS  = exp(-Σ p_i ln p_i)            # exponentiated Shannon entropy, "effective # of trees"
```

Rows with `skeleton_slug IS NULL` (fresh_generation, imports) form their own pseudo-slug per
storybook id, so bespoke trees *raise* ECS as they should. Later (WS-2+), the unit becomes
`(tree fingerprint, leaf-cluster)` pairs; the formula is unchanged, only the partition function
changes, so the v1 implementation keys on an injected `key(row) -> str` callable.

### 2.8 Headline metric: perceived-similarity and repeat-adventure rate

**Pair score (offline proxy).** For two fills `a, b`:

```text
leaf_sim(a, b)   = 1 - median_n D_uni(n)                    if same fingerprint
                 = cosine(masked content-token count vectors of full stories)   otherwise
struct_sim(a, b) = 1                                        if same fingerprint
                 = 1 - min(struct_dist(a, b), 1.0)          otherwise
theme_sim(a, b)  = Jaccard(theme_signature(a), theme_signature(b))

PS(a, b) = 0.50 * leaf_sim + 0.30 * struct_sim + 0.20 * theme_sim          in [0, 1]
```

Probe-grounded anchors: the two pilot fills (same tree, genuinely re-authored, near-disjoint
themes) score `PS ≈ 0.50*0.18 + 0.30*1.0 + 0.20*~0.05 ≈ 0.40`; the dog-for-cat pair scores
`PS ≈ 0.50*0.97 + 0.30*1.0 + 0.20*~0.9 ≈ 0.96`. The repeat flag threshold sits between:

```text
repeat(a, b)  <=>  PS(a, b) >= 0.70        (proxy default; calibrated per section 4)
```

**Repeat-adventure rate (RAR).** For a reader/family and a trailing window of their served
versions `v_1..v_m` (chronological, default window 20 to match `_RECENT_WINDOW`):

```text
RAR = |{ i : max_{j<i} PS(v_i, v_j) >= 0.70 }| / (m - 1)         for m >= 2, else 0
```

"The probability that the next story feels like one already read." Reported per family and
aggregated (mean and p90 across families). The weights (0.50/0.30/0.20) are declared priors
reflecting the plan's leaf-first stance, not fitted constants; section 4 defines how they get
calibrated and section 6 explains why RAR trends on the dashboard but only the guard and
regression deltas gate CI.

---

## 3. The anti-template guard (the most important deliverable)

### 3.1 Contract

```python
def anti_template_verdict(
    fill_a: Storybook,
    fill_b: Storybook,
    *,
    brief_a: Mapping[str, object] | None = None,
    brief_b: Mapping[str, object] | None = None,
    thresholds: AntiTemplateThresholds | None = None,   # per-band override, section 3.5
) -> AntiTemplateReport:
    """Judge whether two fills of one tree are genuinely different leaves.

    Raises:
        ValidationError: If the two fills do not share a structure fingerprint
            (the guard is only defined for same-tree pairs).
    """
```

`AntiTemplateReport` (Pydantic, `report.py`):

```python
class AntiTemplateVerdict(StrEnum):
    PASS_ = "pass"          # genuinely re-authored leaves
    WARN = "warn"           # gray zone: human look, does not block
    FAIL = "fail"           # template / noun-swap: hard regression

class AntiTemplateReport(BaseModel):
    verdict: AntiTemplateVerdict
    median_distance: float
    p25_distance: float
    p10_distance: float
    mean_bigram_distance: float
    entity_count: int
    templated_nodes: tuple[str, ...]   # node ids with d_uni < node_flag_floor
    node_count: int
```

### 3.2 Algorithm

1. Assert `structure_fingerprint(fill_a) == structure_fingerprint(fill_b)`; else raise.
2. `E = extract_entities(fill_a, brief_a) | extract_entities(fill_b, brief_b)` (section 2.1:
   brief-declared entities plus medial-caps tokens from both fills, all lowercased).
3. For every shared node id, mask both bodies with `E`, compute `D_uni(n)` and `D_big(n)`
   (section 2.2).
4. Verdict from the `D_uni` distribution:

```text
FAIL  if median < 0.40  or  p25 < 0.30
PASS  if median >= 0.60 and p25 >= 0.45
WARN  otherwise
```

5. `templated_nodes` = node ids with `D_uni(n) < 0.30` (the per-node flag floor), regardless of
   verdict. These are the repair targets WS-1 hands back to the fill/repair loop.

Threshold semantics, stated plainly: a dog-for-cat pair concentrates near zero after masking, so
it lands far below the FAIL line; two genuinely re-authored fills have never been observed below
0.685 per node, so they clear PASS with margin. The 0.40-0.60 WARN band exists because the two
distributions in section 3.4 are separated by a 0.44-wide empty region; anything landing there is
novel behavior worth a human look, not an automatic block or an automatic pass.

### 3.3 Directionality of masking errors (why this is safe)

Masking errors are one-sided in the safe direction. Over-masking (a common word wrongly treated
as an entity) removes shared and unshared tokens alike and can only *reduce* measured distance,
pushing toward FAIL, never toward a false PASS. Under-masking (a swapped common noun not caught)
*increases* measured distance of a true template, the only direction that could cause a false
PASS, and the probe bounds that inflation: an aggressive 18-noun swap reached at most 0.246 on
its worst node and 0.055 mean, still 0.35 below the FAIL median line. The guard therefore fails
templates even when normalization is imperfect. Gaming by *systematic paraphrase* (not noun
swap) is a different threat, handled in section 7.1.

### 3.4 Probe results (the empirical grounding)

Reproducible offline probe over the two committed pilot fills of `the-cave-of-echoes`
(64 matched nodes; masking = medial-caps only, no brief entities, i.e. *worse* than production):

| Pair | metric | mean | min | p10 | max |
| --- | --- | --- | --- | --- | --- |
| space-station vs dino-dig (genuine) | `D_uni` | 0.820 | 0.685 | 0.765 | 0.920 |
| space-station vs dino-dig (genuine) | `D_big` | 0.920 | 0.799 | 0.871 | 0.976 |
| space-station vs 18-noun swap of itself | `D_uni` | 0.055 | 0.000 | 0.000 | 0.246 |
| space-station vs 18-noun swap of itself | `D_big` | 0.070 | 0.000 | 0.000 | 0.269 |
| space-station vs itself (sanity) | `D_uni` | 0.000 | 0.000 | 0.000 | 0.000 |

Without masking, the noun-swap pair's mean `D_uni` is 0.128: masking matters (it removes the
proper-noun contribution entirely), and the residual 0.055 is the unmasked common-noun residue
discussed in 2.1. The genuine pair's minimum node (0.685) and the swap pair's maximum node
(0.246) leave the [0.30, 0.60] threshold region empty by a wide margin on both sides.

Caveat recorded for honesty: this is one skeleton, one band, two fills, and a synthetic swap. The
thresholds are defaults, expected to hold for 8-11 prose; section 3.5 handles bands where they
may compress, and the harness baseline (section 6) re-derives the observed distributions as the
panel grows.

### 3.5 Per-band thresholds (young-band false positives)

Band 3-5 and 5-8 bodies are short (the per-node envelope from
`validator.band_profile.words_per_node_profile` is far below 8-11's) and the band vocabulary is
deliberately restricted, so two legitimate re-authorings share more tokens by construction.
Design response, in order of preference:

1. `AntiTemplateThresholds` is a small frozen dataclass `(fail_median, fail_p25, pass_median,
   pass_p25, node_flag_floor)` with the section 3.2 values as the default and a per-band table
   in `leaf.py` (`_BAND_THRESHOLDS: dict[str, AntiTemplateThresholds]`). Until a band has panel
   data, its entry is absent and the default applies; the young-band entries are added when the
   harness has same-skeleton multi-brief fills for those bands (a WS-1 panel task), by placing
   FAIL at (observed swap p95 + 0.05) and PASS at (observed genuine p05 - 0.05).
2. The WARN band absorbs compression in the meantime: a young-band genuine pair that lands at
   0.55 warns for a human look instead of failing the build.

The guard never compares stories across bands, and it only ever runs on same-tree pairs, where
re-authoring is the explicit contract; it cannot flag "legitimately similar" cross-tree young
stories because it refuses cross-tree input by construction (section 3.1).

---

## 4. Judge-model validation of the headline proxy (optional layer)

The offline `PS` proxy is a stand-in for a perceptual judgment. The validation loop:

1. **Judge-model score (batch, networked, never CI):** `scripts/run_diversity_eval.py
   --with-judge` sends story *pairs* (both texts, band context) to a judge model through the
   existing generation provider abstraction (`generation/providers/`, provider chosen by the
   same settings the pipeline uses; Anthropic in production, Ollama for homelab-free runs) with
   a fixed rubric prompt: "Would a child who read story A feel story B is the same adventure?
   Answer a 0-10 similarity and one sentence why." Responses are cached to
   `out/diversity/judge-cache.json` keyed by `(sha256(a), sha256(b), rubric_version)` so reruns
   are incremental. No embedding dependency is required for v1 of the optional layer; if
   embedding distance is later wanted, the concrete path is the Ollama `/api/embeddings`
   endpoint (already a reachable provider host in the homelab deployment) behind the same
   `--with-embeddings` flag, cached the same way. Judge-first is deliberate: the plan's headline
   is defined as a judge question, and one networked mechanism is cheaper to maintain than two.
2. **Calibration table:** the harness emits `(PS_proxy, judge_score)` pairs; a Spearman rank
   correlation and a fitted monotone mapping (isotonic in spirit, implemented as a simple
   binned lookup, stdlib only) are written to `tests/data/diversity_panel/calibration.json`.
   The repeat threshold (0.70) and the PS weights are revisited when correlation drops below
   0.6 or K18 data arrives.
3. **K18 ground truth (over time):** once K18 reader ratings accumulate on served stories,
   RAR-proxy is validated against "rated it feels-like-a-repeat" (or the closest K18 signal) per
   family; the calibration table gains a third column. This is a standing quarterly task, not a
   build step.

---

## 5. The request-time similarity query (the WS-4 interface)

### 5.1 Data types (`history.py`, `query.py`)

```python
@dataclass(frozen=True, slots=True)
class HistoryEntry:
    """One prior story of the family, reduced to what similarity needs."""
    storybook_id: str
    version: int
    skeleton_slug: str | None
    theme_sig: frozenset[str]        # theme_signature() of its brief + metadata.themes
    created_at: datetime

@dataclass(frozen=True, slots=True)
class StoryNeighbor:
    storybook_id: str
    version: int
    skeleton_slug: str | None
    theme_similarity: float          # Jaccard vs the request signature

class DifferentiationLevel(StrEnum):
    TREE = "tree"                    # pick a different skeleton; plenty of room
    LEAF = "leaf"                    # cell saturated for this theme; push leaf variation
    CATALOG = "catalog"              # even leaf room is thin; grow the catalog (WS-5/WS-8)

@dataclass(frozen=True, slots=True)
class SimilarityContext:
    neighbors: tuple[StoryNeighbor, ...]     # desc by theme_similarity, capped at 10
    cell_theme_saturation: float             # [0, 1], section 5.3
    used_slugs: frozenset[str]               # slugs already used for similar-theme stories
    similar_count_per_slug: Mapping[str, int]
    recommendation: DifferentiationLevel
```

### 5.2 Function signatures

The pure core (unit-testable with hand-built entries, no DB):

```python
def score_history(
    *,
    request_theme_sig: frozenset[str],
    history: Sequence[HistoryEntry],
    cell_slugs: Sequence[str],                 # from candidates_for_cell(band, length, style)
    theme_threshold: float = 0.35,             # tau_theme, calibrated like section 4
) -> SimilarityContext: ...
```

The impure loader (the only DB touch, mirrors `recent_skeleton_usage`):

```python
async def load_family_history(
    session: AsyncSession,
    family_id: uuid.UUID | None,
    *,
    window: int = 20,                          # matches skeleton_match._RECENT_WINDOW
) -> list[HistoryEntry]: ...
```

And the thin composition WS-4 actually calls from `authoring_plan.py`:

```python
async def similarity_context(
    session: AsyncSession,
    *,
    family_id: uuid.UUID | None,
    brief: Mapping[str, object],               # the request's ConceptBrief dump
    band: str,
    length: str,
    style: str,
) -> SimilarityContext:
    """load_family_history + candidates_for_cell + score_history, composed."""
```

Note: `similarity_context` calls `generation.skeleton_match.candidates_for_cell`... it must NOT
(import rule, section 1.1). Instead it takes `cell_slugs: Sequence[str]` as a parameter and the
caller passes `candidates_for_cell(band, length, style)` in. Final signature:

```python
async def similarity_context(
    session: AsyncSession,
    *,
    family_id: uuid.UUID | None,
    brief: Mapping[str, object],
    cell_slugs: Sequence[str],
) -> SimilarityContext: ...
```

This keeps `diversity` import-free of `generation` and makes the function trivially testable.

### 5.3 Saturation: definition and threshold semantics

Given the request signature `T_r`, history `H`, and the cell's candidate slugs `C`:

```text
similar(h)             <=>  jaccard(T_r, h.theme_sig) >= tau_theme          (default 0.35)
used                    =   { h.skeleton_slug : h in H, similar(h), h.skeleton_slug in C }
cell_theme_saturation   =   |used| / |C|          (1.0 when C is empty: nothing to pick anyway)
similar_count_per_slug  =   count of similar h per slug in C
recommendation:
    TREE     if saturation < 1.0                       # an unused-for-this-theme tree exists
    LEAF     if saturation == 1.0 and max(similar_count_per_slug.values()) < 2
    CATALOG  if saturation == 1.0 and max(similar_count_per_slug.values()) >= 2
```

This is the plan's escalation ladder made computable: "the second dragon story" finds
`saturation < 1` and WS-4 de-weights `used_slugs` (a fresh tree alone suffices); "the tenth
dragon story" finds every cell tree already carrying a dragon fill, so the signal escalates to
LEAF and WS-4 raises `needs_leaf_differentiation` to the fill; when trees are each carrying two
or more similar-theme fills, the honest answer is CATALOG (WS-5 mutation / WS-8 flywheel).
WS-4, not WS-0, decides what to do with the recommendation; WS-0 guarantees only that the scalar
and enum are deterministic functions of `(brief, history, cell)`. The novelty-floor invariant
(plan section 7.5) stays WS-4's obligation: `used_slugs` is advisory de-weighting input, and
nothing in this contract permits zeroing a candidate's weight.

`tau_theme = 0.35` is a prior: theme signatures are short noun-heavy sets, and pilot briefs for
unrelated themes overlap near 0 while same-theme rewordings ("a dragon who lost his fire" vs
"dragon story please") share the head noun and its bigrams. The harness panel includes
same-theme-reworded brief pairs to pin this threshold; it is a named constant, not magic.

### 5.4 How the loader reads `StorybookVersion`

Query shape (one round trip, mirroring `recent_skeleton_usage`'s join):

```sql
SELECT sv.storybook_id, sv.version, sv.skeleton_slug, sv.created_at,
       sv.blob #> '{metadata,themes}'      AS themes,      -- JSONB path, no full-blob transfer
       c.brief                                             -- Concept.brief via GenerationJob
FROM storybook_version sv
JOIN storybook s          ON s.id = sv.storybook_id
LEFT JOIN generation_job g ON g.storybook_id = sv.storybook_id
LEFT JOIN concept c        ON c.id = g.concept_id
WHERE s.family_id = :family_id
ORDER BY sv.created_at DESC
LIMIT :window
```

In SQLAlchemy: `StorybookVersion.blob["metadata"]["themes"]` JSONB path extraction, so the ~50 KB
blobs never cross the wire; only the themes array and the (small) brief do. Design notes the
implementation must carry as RAD tags:

- `#ASSUME: external-resources:` live DB query; caller holds an open `AsyncSession` (same
  contract as `recent_skeleton_usage`).
- `#ASSUME: data-integrity:` `blob` and `Concept.brief` are loosely-typed JSONB; a row with a
  missing/malformed themes array or brief degrades to an empty theme signature for that entry
  (it simply never counts as "similar"), never raises. `#VERIFY:` unit test feeds malformed rows.
- `#EDGE: data-integrity:` multiple `GenerationJob` rows per storybook are possible; order by
  `GenerationJob.created_at` and take the first, matching `anchoring.py`'s convention.
- Family-less requests (`family_id is None`) return `[]`, mirroring `recent_skeleton_usage`.
- The window counts every authored version like `recent_skeleton_usage` does (documented there
  as a product decision); WS-0 inherits it verbatim so the two signals cannot disagree about
  what "recent" means.

Per-request cost: one indexed query, `window <= 20` rows, then pure set arithmetic over
signatures of a few dozen tokens. No caching needed at current scale; if `POST /authoring-plan`
latency ever matters, the signature per version is immutable and could be persisted on the row,
a schema change deliberately deferred (YAGNI until measured).

---

## 6. The eval harness and CI regression gate

### 6.1 Script: `scripts/run_diversity_eval.py`

Mirrors `run_story_gate.py` in shape: argparse, stdlib + project imports, prints findings,
returns an exit code. Modes:

```text
uv run python scripts/run_diversity_eval.py                     # offline core over the panel
uv run python scripts/run_diversity_eval.py --json out.json     # machine-readable suite output
uv run python scripts/run_diversity_eval.py --update-baseline   # rewrite baseline (deliberate)
uv run python scripts/run_diversity_eval.py --with-judge        # + judge scoring (networked)
uv run python scripts/run_diversity_eval.py --live-fill         # + fresh fills via provider
```

`--with-judge` and `--live-fill` require provider settings and are refused (clear error) when
unset; they are for manual runs and a scheduled non-required workflow, never `ci.yml`.

### 6.2 Panel

`tests/data/diversity_panel/panel.json` declares the fixed panel; v1 contents:

1. **Same-tree, multiple briefs (the anti-template exercise):** the two committed pilot fills
   `out/pilot/fills/the-cave-of-echoes.{space-station,dino-dig}.filled.json` (repo paths,
   cwd-relative per the existing `skeletons/` convention), expected verdict PASS.
2. **Degenerate baseline:** a dog-for-cat variant is synthesized *at run time* by
   `diversity_eval`'s helper `make_noun_swap_variant(fill, swaps)` from the space-station fill
   and a committed swap table in the panel file, expected verdict FAIL. Synthesizing rather than
   committing the variant avoids checking a deliberately-bad story into the corpus and keeps the
   fixture byte-deterministic anyway.
3. **Cross-tree pairs:** the pilot fills vs one or two committed 8-11 skeleton fills as the
   library grows; until then, cross-tree structural distance is exercised directly on
   `skeletons/8-11/*.json` (bodies are `<<FILL>>` markers, which structural metrics ignore).
4. **Brief pairs for `tau_theme`:** a small committed list of (brief, brief, expected
   similar: bool) triples, including same-theme rewordings and distinct themes.

`--live-fill` extends the panel by running `fill_skeleton` on one skeleton x three briefs and
gating the fresh outputs through `run_story_gate` first (only gate-passing fills are scored),
exactly the plan's "fixed (skeleton x theme-brief) panel" loop. Live-fill outputs land in
`out/diversity/` (gitignored... note: `out/pilot` is committed, so add `out/diversity/` to
`.gitignore` explicitly).

### 6.3 Baseline and regression rules

`tests/data/diversity_panel/baseline.json` stores, per panel pair/story: the ATG verdict and
distance stats, distinct-n, self-BLEU-lite, structural distances, and the PS matrix. The script
compares a fresh run to baseline and **fails (exit 1)** when:

1. Any panel pair's ATG verdict differs from its expected verdict (PASS pairs must PASS, FAIL
   pairs must FAIL). This is the hard CI contract.
2. Any genuine pair's `median D_uni` drops more than 0.05 below its baseline value.
3. Any fill's `distinct_2` drops more than 10% relative below baseline.
4. Any expected-similar brief pair flips under `tau_theme`, or expected-distinct flips over it.
5. Any structural invariant breaks (same-skeleton distance != 0; cross-skeleton distance == 0).

Baseline updates only via `--update-baseline`, committed and reviewed in the same PR as the
change that legitimately moved a number.

### 6.4 nox session and CI wiring

```python
@nox.session(python="3.12")
def diversity_eval(session: nox.Session) -> None:
    """Run the offline diversity metric suite over the fixed panel."""
    session.install("-e", ".")
    session.run("python", "scripts/run_diversity_eval.py")
```

CI: consistent with the project's "no CI workflow invokes nox" convention, `ci.yml` gets one
step in the existing quality-gate job that runs `uv run python scripts/run_diversity_eval.py`
directly (seconds of pure Python; no DB, no network). The unit tests in section 8 additionally
run inside the normal pytest job, so the guard is doubly covered. A separate scheduled workflow
(weekly, non-required) may run `--with-judge` with provider secrets; it posts results as an
artifact and never blocks merges.

---

## 7. Metric-gaming and validity risks, and their guards

### 7.1 Paraphrase gaming (the successor to dog-for-cat)

Once the fill (or its repair loop) is optimized against `D_uni`, the cheapest way to score high
is a systematic synonym pass: same sentences, same beat rhythm, every content word thesaurused.
`D_uni` goes to ~1.0 while a reader still feels the template. Guards, layered:

- `D_big` over ALL tokens (function words included): synonym passes preserve function-word
  scaffolding and word order, so all-token bigram distance stays low when unigram distance is
  gamed. The ATG report already carries `mean_bigram_distance`; the harness baseline tracks the
  `D_big / D_uni` ratio per genuine pair, and a pair with high `D_uni` but `D_big` below its
  band baseline is surfaced as WARN in the eval output (not a v1 build-failure; promoted to one
  once band baselines exist).
- **Sentence-shape correlation** (cheap, recorded not gated in v1): Pearson correlation of the
  two bodies' sentence-length sequences per node; a paraphrased template correlates near 1.0.
  Listed as a v1.1 addition to `leaf.py` so implementation is not blocked on it.
- The judge-model audit (section 4) is the backstop: paraphrase templates are exactly what a
  judge rubric catches and lexical metrics cannot; calibration drift (proxy says different,
  judge says same) is the alarm.

### 7.2 Goodhart on lexical guards

If distinct-n or self-BLEU ever leak into a fill prompt or a repair objective, generation will
buy vocabulary variety with reading-level drift, breaking band fit. Guards: (a) the plan's rule
is restated as an implementation invariant, lexical metrics are *floors checked after the fact*,
cross-checked against RL-13 findings from the same gate run (the harness runs `run_gate` and
refuses to trade one for the other: a fill whose distinct-n rose while RL-13 warnings appeared
is a regression, not an improvement); (b) prompt templates (`generation/templates/`) are
grep-checked in review for metric names; the design deliberately gives the metrics no
generation-facing API.

### 7.3 Novelty-floor interaction (homogenization by selection)

WS-4 will de-weight `used_slugs`. If saturation-driven de-weighting could zero a weight, a
family could be locked out of a tree forever and the selector could homogenize toward whatever
scores "different". The `SimilarityContext` contract therefore ships counts and sets, never
weights, and the plan's `_weight`-style nonzero floor stays a WS-4 acceptance criterion (pinned
there, referenced here). WS-0's own aggregate (ECS) is the watchdog: a selection change that
homogenizes serving *lowers* ECS, and the dashboard trend makes it visible.

### 7.4 Young-band false positives

Handled structurally in section 3.5 (per-band thresholds, WARN buffer, same-tree-only scope).
Residual risk: a 3-5 band panel does not exist yet, so the default thresholds are untested
there; the guard must not be wired as blocking for bands with no panel entry until WS-1 produces
those fills. The implementation encodes this as: bands absent from `_BAND_THRESHOLDS` use
defaults for *reporting*, and the CI gate only hard-fails pairs that are in the committed panel
(all currently 8-11).

### 7.5 Proxy validity drift

PS weights and thresholds are priors. Guard: the calibration loop (section 4) with a standing
quarterly re-check, Spearman floor 0.6, and K18 integration when available. Until then, the
*only* numbers that gate CI are the ones grounded in observed distributions (ATG thresholds,
baseline deltas); PS/RAR are reported, trended, and used by WS-4 relatively (ranking neighbors),
where monotonicity matters more than calibration.

### 7.6 Panel overfitting

A two-fill panel can be gamed by accident (thresholds tuned to one skeleton). Guard: the panel
is append-only in review (new skeletons/bands/briefs get added, existing entries are not
retuned without `--update-baseline` justification), and the live-fill mode regularly produces
out-of-panel pairs whose stats are compared against the committed distributions.

---

## 8. Acceptance criteria and test plan

All tests below are offline unit tests under `tests/unit/` (no network, no DB except where the
`AsyncSession` rolled-back fixture is noted), BasedPyright-strict, fixtures typed. The two pilot
fills are loaded via repo-relative paths (`out/pilot/fills/...`), consistent with the existing
cwd-relative `skeletons/` convention; they are committed files.

**`test_diversity_normalize.py`**

- `test_extract_entities_finds_medial_caps_from_pilot_fill` (Priya, Pip, Halcyon found; "The"
  at sentence starts not treated as entity unless seen medially).
- `test_extract_entities_includes_brief_names` (brief protagonist name masked even if the fill
  only uses it sentence-initially).
- `test_mask_tokens_collapses_all_entities_to_one_placeholder`.
- `test_theme_signature_keeps_nouns_and_drops_stopwords`.

**`test_diversity_leaf.py`** (the core acceptance tests)

- `test_anti_template_guard_pilot_fills_score_as_different`: space-station vs dino-dig returns
  `PASS`, `median_distance >= 0.60`, `p25_distance >= 0.45`, `templated_nodes == ()`.
- `test_anti_template_guard_noun_swap_variant_fails`: `make_noun_swap_variant(space_station,
  SWAPS)` (the committed swap table) vs the original returns `FAIL`,
  `median_distance <= 0.25`.
- `test_anti_template_guard_identical_fill_fails_with_zero_distance`.
- `test_anti_template_guard_rejects_cross_tree_pair_with_validation_error`.
- `test_leaf_distance_zero_when_both_bodies_empty`.
- `test_band_threshold_override_changes_verdict_boundaries`.

**`test_diversity_structure.py`**

- `test_structure_fingerprint_equal_for_two_fills_of_one_skeleton` (pilot fills).
- `test_structural_distance_zero_for_same_skeleton_fills` (exactly 0.0).
- `test_structural_distance_positive_across_skeletons`: any two distinct files in
  `skeletons/8-11/` give `struct_dist > 0`.
- `test_fingerprint_ignores_titles_bodies_and_labels` (retitle an ending, retitle a node body,
  and rewrite every choice label; fingerprint unchanged).
- `test_fingerprint_equal_for_label_rewritten_fill_of_same_skeleton` (a label-only rewrite keeps
  the fingerprint; a rewritten `target` still changes it; WS-0 labels-are-leaves decision).
- `test_features_handle_cyclic_topologies` (an `open_map`/`loop_and_grow` skeleton does not
  hang or crash BFS).

**`test_diversity_lexical.py`**

- distinct-n and self-BLEU-lite on hand-built 3-node stories with known values; monotonicity
  (repeating a node's body raises self-BLEU, lowers distinct-2).

**`test_diversity_aggregate.py`**

- `test_effective_catalog_size_uniform_and_degenerate` (4 equal slugs -> 4.0; one slug -> 1.0).
- `test_perceived_similarity_orders_swap_above_genuine_pair` (PS(swap pair) > 0.9 >
  PS(pilot pair)).

**`test_diversity_query.py`**

- Pure `score_history` tests with hand-built `HistoryEntry` rows:
  - `test_saturation_increases_as_same_theme_stories_accumulate`: with cell slugs {s1, s2, s3},
    adding similar-theme entries for s1, then s2, then s3 moves saturation 1/3 -> 2/3 -> 1.0 and
    the recommendation TREE -> TREE -> LEAF; a second similar fill on any slug at saturation 1.0
    moves it to CATALOG.
  - `test_dissimilar_theme_history_does_not_saturate`.
  - `test_neighbors_sorted_and_capped`.
  - `test_empty_cell_slugs_reports_saturation_one`.
- Loader tests (integration, rolled-back `AsyncSession` fixture):
  - `test_load_family_history_extracts_themes_without_full_blob` (rows with themes arrays).
  - `test_malformed_blob_degrades_to_empty_signature_not_error`.
  - `test_family_none_returns_empty`.

**Harness acceptance** (checked by running it, and by one subprocess-free unit test that calls
its `main()` on the committed panel):

- `uv run python scripts/run_diversity_eval.py` exits 0 on a clean tree, exits 1 when any
  section 6.3 rule trips (exercised by pointing it at a doctored baseline in a tmp dir).
- `uv run nox -s diversity_eval` runs it.

**Definition of done for WS-0:** all tests above green; the panel + baseline committed; `ci.yml`
running the eval step; `similarity_context` importable and documented for WS-4;
`docs/planning/story-flexibility-plan.md` WS-0 marked delivered with a pointer to this doc.

---

## 9. Judgment calls, recorded for the reviewer

- **Primary leaf distance: Jaccard over masked content unigrams.** Alternatives: cosine over
  counts (narrower separation in the probe, 0.430 vs 0.685 genuine minimum); normalized edit
  distance (order-sensitive in the wrong direction, O(n^2) per node); character n-gram cosine
  (opaque to reviewers and still needs masking).
- **Entity normalization: brief entities + medial-caps extraction, single `<ent>` placeholder.**
  Alternatives: an NER model (network calls and new dependencies, both forbidden in the core);
  role-typed placeholders like `<hero>`/`<companion>` (needs reliable role attribution; the
  single placeholder is fail-safe per section 3.3 and can be upgraded later).
- **ATG thresholds: FAIL below 0.40 median, PASS at or above 0.60, WARN between.** Grounded in
  the probe (genuine minimum 0.685 vs swap maximum 0.246); a single cut line would waste the
  observed 0.44-wide empty margin and remove the human-look zone.
- **Structural distance: Canberra over the feature vector + histogram L1 + topology flag.**
  Alternatives: graph edit distance (NP-hard, unstable approximations in networkx); fingerprint
  only (no graded signal for WS-4 de-weighting or WS-5 mutation evaluation).
- **Optional layer mechanism: judge model via the existing chat providers, cached batch runs.**
  Alternative: embeddings-first (a new client surface; the judge form matches the plan's own
  definition of the headline metric; Ollama `/api/embeddings` is named as the concrete later
  path if embedding distance is wanted).
- **Saturation definition: fraction of cell slugs already used for a similar-theme story.**
  Alternative: a continuous soft-saturation score (harder to threshold into the plan's
  TREE/LEAF/CATALOG ladder; can be added later as a secondary scalar without breaking the
  contract).
- **Query composition: pure `score_history` + impure loader, with `cell_slugs` passed in by the
  caller.** Alternative: `diversity` importing `candidates_for_cell` directly (creates exactly
  the `generation` import edge this design forbids).
- **Panel degenerate fixture: noun-swap variant synthesized at run time from a committed swap
  table.** Alternative: committing the bad fill itself (pollutes the corpus with a deliberate
  template; run-time synthesis is byte-deterministic anyway).

Open items intentionally left to later workstreams: per-band threshold tables for 3-5/5-8/10-13+
(WS-1 panel fills), WS-2 slot values as additional masking entities, sentence-shape correlation
promotion to a gating signal, persisting theme signatures on `StorybookVersion` if query latency
is ever measured to matter, and the `(tree, leaf-cluster)` partition for ECS.

---

## 10. Reviewer notes (supervisor critique, 2026-07-18)

The design is approved for implementation with the adjustments below. It is
rigorous, honest about its priors, and the anti-template guard (ATG) is
empirically grounded and correctly the only hard gate.

**Strengths accepted as-is:** ATG algorithm and the one-sided masking-error
argument (section 3.3); the two-layer offline-core-vs-optional rule; keeping PS
/ RAR as trend-only (not gating) since their weights are unvalidated priors; the
import-acyclic module layout (caller passes `cell_slugs` in); the escalation
ladder made computable in section 5.3.

**Adjustment 1 (highest priority): request-time theme similarity is the weakest
link.** Section 5 compares the incoming *brief* (free-form, pre-generation, no
`metadata.themes` yet) against history via lexical Jaccard on noun sets. Short
briefs paraphrasing the same theme routinely fall below `tau_theme` (the doc's
own example, "a dragon who lost his fire" vs "dragon story please", is Jaccard
~0.25 < 0.35), so the ladder will UNDER-escalate, exactly the tenth-dragon case
it exists to catch. Lexical Jaccard on short briefs cannot fix this by
threshold tuning alone. Required: add a lightweight **theme-normalization step**
that maps a brief to a small set of normalized theme tags (a curated keyword/
synonym map first; a cheap classifier later), and compute `theme_signature` over
those tags on BOTH sides. This is a soft prerequisite for WS-4's ladder and
should ship with the query, not be deferred to calibration. Until it exists,
document the ladder as best-effort and lean on `metadata.themes` where present.

**Adjustment 2: specify ATG's production trigger.** The guard is inherently a
second-use, pairwise check (new fill vs a prior fill of the SAME skeleton). WS-1
integration must define "compare against which prior": recommend the nearest
prior fill of the same skeleton in the family (else the cell), and a no-op when
none exists (first use of a tree has nothing to be similar to). Add this to the
WS-1 hand-off, it is not WS-0's job to decide, but WS-0 must expose a helper
that selects the comparison partner from history.

**Adjustment 3: phase the build.** Do not implement all 933 lines at once.
- **Phase 1 (implement now, the WS-4 MVP):** `normalize`, `structure`, `leaf`
  (incl. ATG), `report`, `history`, `query` (pure core + loader), with the
  section 8 offline unit tests (pilot fills score PASS; synthetic dog-for-cat
  scores FAIL; structural distance 0 within a tree, >0 across; saturation rises
  with same-theme history). Include the theme-normalization tags from
  Adjustment 1.
- **Phase 2 (fast-follow):** `aggregate` (ECS), `lexical` guards, the headline
  PS/RAR, `scripts/run_diversity_eval.py`, the `diversity_eval` nox session, the
  committed panel, and the CI regression gate. **Delivered**: see
  [ws0-phase2-harness-design.md](ws0-phase2-harness-design.md) for the exact
  panel contents, baseline format, CI-fail rules (R1-R6), module signatures,
  and test plan this phase implemented.
- **Phase 3 (when a provider is wired):** the judge-model calibration (section
  4). Run it once on the panel EARLY, not "quarterly", to validate the offline
  PS proxy against perception, since the whole objective is perceptual.

**Minor:** cross-tree PS (different fingerprints) is not empirically anchored
(the probe was same-tree); fine while RAR only trends. Masking start-of-sentence
protagonist names relies on brief-declared entities; the probe shows the
residual is safe, but Phase-1 tests should include a fill whose protagonist name
appears only sentence-initially to confirm brief-entity coverage.
