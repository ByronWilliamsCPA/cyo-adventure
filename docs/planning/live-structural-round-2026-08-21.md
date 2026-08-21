# Live structural round: frozen-field mutation rate, directed delta, chunked path

**Date**: 2026-08-21
**Status**: planned; results appended below as they land
**Predecessor**: `deepseek-v4-pro-live-fill-plan-2026-08-20.md` (PR #731 merged 2026-08-20)
**Branch**: `claude/cyo-live-story-generation-kxm0ya`
**Goal**: find remaining STRUCTURAL defects in the skeleton/fill contract before bulk skeleton and
story generation, where any per-book defect becomes a catalog-wide defect. Not prose quality, and
not publishable books.

---

## 1. Preconditions, verified this session

| Check | Result |
| --- | --- |
| `GET https://openrouter.ai/api/v1/models` | `200` (the 2026-08-20 session's 403-to-CONNECT no longer holds) |
| `OPENROUTER_API_KEY` in environment | present |
| Commit signing (`commit.gpgsign` via SSH key) | configured; predecessor commits verify |
| `uv sync --all-extras` | clean |

Endpoint pinning is treated as a correctness requirement (predecessor finding F2:
`MODEL_OUTPUT_CAPS` is keyed per slug while endpoints for one slug span 16,384 to 1,048,576 output
tokens; an unpinned low route truncates non-empty and burns the repair budget). Every leg below is
pinned with `allow_fallbacks: false`, and every pin is chosen by PROBING candidates with one small
completion, never from declared attributes (the predecessor's probe found 429, 404-data-policy and
200 behind one slug).

## 2. What this round measures that the offline census cannot

Six open questions, each mapped to a sub-run or an offline computation:

1. **Frozen-field mutation as a RATE** (the deciding question for bulk). Previous round: 3 of 3
   passing books mutated a frozen or ambiguous field, a different field each time (`id`,
   `metadata.themes`, `title`, `ending.title`). Three books cannot distinguish "always" from
   "coin flip". Run B fills ten books across all six bands and counts, per frozen field class,
   how many books mutate it.
2. **`ending.title` writability** (`UW-C311`, status `decision`; NOT resolved here). Run B counts
   one-shot ending-title reskins per book; Run C shows what the chunked path does with the same
   affordance. Both are evidence for the owner ruling, not a ruling.
3. **Outbound-choice staging** (`AL-495`/`UW-C312`). No live run needed: a measurement script
   prototypes the outbound companion to `CG-4` and reports the rate on Run B's books AND on all
   committed filled books, so the rate arrives with a committed baseline.
4. **Sibling convergence under the production directive** (`AL-498`/`UW-C315`). Run A executes the
   committed best-case directed spec against the exact `the-tin-whistle-map` pair whose raw
   undirected floor is 96.3 shared four-grams per 1000 mean leaf words (budget 4.0). The question
   is whether the strongest directive moves 96.3 materially toward 4.0.
5. **Protagonist presence.** Offline measurement across Run B books plus all committed filled
   books: fraction of nodes containing second-person address, versus the skeleton's declared
   narrative style, to decide whether this is measurable enough to become a rule.
6. **Chunked vs one-shot divergence** (`UW-C302` aftermath). The chunked path has NEVER run live.
   Predecessor F1 proved it unreachable on v4-pro (cap 131,072 clears every skeleton), but it IS
   reachable with a committed low-cap model: `deepseek/deepseek-v3.2` has a
   `MODEL_OUTPUT_CAPS` row of 65,536, giving a feasibility ceiling of 52,429 tokens, and
   `the-hollow-crown-gambit` (28,426 commissioned words, 56,852 expected tokens, plain skeleton,
   no sidecar) sits over it. Run C is the first live datapoint on whether the degraded path works
   at all and what it does to ending titles (`merge_fill_batch` whitelists only `body` and choice
   `label` by construction). Known confound, stated up front: Run C changes model AND path, so
   prose differences are not attributable; only the contractual behavior (which fields moved, did
   the merge hold, did the fill complete) is the evidence.

## 3. The three sub-runs

### Run A: UW-C315 directed delta (first, already specified, cheapest per answer)

- Skeleton: `skeletons/8-11/the-tin-whistle-map.json` (broadcast to both briefs)
- Briefs: `docs/planning/vendor-comparison/runs/deepseek-v4-pro-2026-08-20/shared-skeleton-pair/briefs.json`
  (the exact committed pair: canal boatyard; school lost-property)
- Differentiation: `docs/planning/vendor-comparison/runs/deepseek-v4-pro-2026-08-20/shared-skeleton-pair-directed/differentiation.json`
  (committed best-case spec: catalog level, opposed axes, sibling title carried)
- Vendor: `vendors-deepseek-v4-pro.json` (azure/us pin, re-probed before running)
- Output: `out/live-structural-2026-08-21/pair-directed/`
- Read-out: `check_sibling_fills.py --check` on the two directed books; report shared four-grams
  per 1000 against the recorded raw floor of 96.3 for this exact pair. Decision-grade either way:
  if even this spec cannot move the number materially toward 4.0, the differentiation directive is
  not the lever for cross-family skeleton reuse.

### Run B: frozen-field mutation grid (ten books, six bands, v4-pro, undirected)

Same model and pin as the predecessor so the mutation rate is comparable to its 3-of-3. All
skeletons are non-sidecar (no `{SLOT}` contract), all distinct, chosen to spread band, size, tier
and style while keeping cost proportionate. Briefs are operator-authored fixtures (no real child
identity), each deliberately DISTANT from the native theme in vocabulary and register while
compatible with the skeleton's physics; `AL-497` showed physics-incompatible reskins produce
incoherent worlds, and this round measures contract adherence, not incoherence tolerance.

| # | Skeleton | Cell | Nodes | Comm. words | Why this one |
| --- | --- | --- | ---: | ---: | --- |
| 0 | `3-5/the-market-morning.json` | 3-5 prose t1 | 21 | 846 | Tightest envelope; cheapest rate sample |
| 1 | `3-5/the-big-cardboard-box.json` | 3-5 prose t1 | 44 | 1,904 | Largest 3-5; time_cave |
| 2 | `5-8/the-seedling-thief.json` | 5-8 prose t1 | 31 | 2,160 | open_map, small |
| 3 | `5-8/the-bridge-of-stones.json` | 5-8 prose t1 | 58 | 3,888 | open_map, larger 5-8 |
| 4 | `8-11/the-half-hour-call.json` | 8-11 prose t1 | 61 | 5,960 | Small 8-11; band with the ending-kind safety line |
| 5 | `8-11/the-lantern-keepers-list.json` | 8-11 prose t1 | 125 | 12,676 | Mid 8-11; same band as Run A for context |
| 6 | `10-13/the-glass-comet.json` | 10-13 prose t2 | 105 | 10,750 | Tier-2 prose: state-aware rules on live prose outside gamebook |
| 7 | `10-13/the-observatory-shift.json` | 10-13 prose t1 | 145 | 14,815 | sorting_hat topology; second 10-13 for a same-band pair |
| 8 | `13-16/the-iron-spire-trial.json` | 13-16 gamebook t2 | 277 | 17,266 | Tier-2 gamebook, gauntlet; the cell the previous tier-2 book failed worst in |
| 9 | `16+/the-quarantine-ledger.json` | 16+ prose t1 | 141 | 22,605 | 16+ prose, unmeasured last round (only 16+ gamebook ran) |

Total: 1,008 nodes, 92,870 commissioned words. Output: `out/live-structural-2026-08-21/grid/`.

What each book contributes beyond the shared mutation tally: every book is also a fill-rate
sample against the new `--min-fill-rate` floor (does the v4-pro under-delivery reproduce, and at
what rate); books 4+5 and 6+7 form same-band different-skeleton pairs for `check_sibling_fills`
context on whether 96.3 is a shared-skeleton phenomenon or a model idiom; books 6 and 8 are the
tier-2 state-aware samples.

### Run C: chunked path, first live datapoints (two books, v3.2, low cap)

- Skeletons: `skeletons/13-16/the-hollow-crown-gambit.json` (434 nodes, 28,426 words) and
  `skeletons/16+/the-obsidian-relay.json` (393 nodes, 32,652 words); both plain, both tier 1 so
  state-awareness does not confound the path question, both over the 52,429-token feasibility
  ceiling so both chunk. (Two books rather than one because `compare_vendors.py` requires at
  least two briefs; the second doubles the chunked-path evidence for about ten cents.)
- Model: `deepseek/deepseek-v3.2` (cap row 65,536; feasibility ceiling 52,429 < 56,852 expected
  tokens, so `fill_skeleton` takes the chunked path with no new harness flags)
- Pre-flight: probe v3.2 endpoints (candidates with declared ceiling >= 65,536: DigitalOcean
  128,000; AtlasCloud fp8 163,840; SiliconFlow fp8 163,840; Novita fp8 65,536), pin the
  reachable one matching the account's hosting posture, and add the pinned endpoint's price row
  to `core/pricing.py` (run enablement, as the predecessor did for v4-pro; not a production fix)
- Output: `out/live-structural-2026-08-21/chunked-v32/`
- Read-out: did the chunked fill complete; which fields moved (expected: `body` and `label` only,
  by merge construction); fill rate; leftover markers. This is UW-C311 evidence and the first
  live exercise of the `UW-C302` machinery, on the plain path only (the BOUND chunked path stays
  unreachable on this harness, unchanged from predecessor F1; still out of scope).

### Execution order and rehearsal

Plan committed first, then: probes (Task 2), `--mock` rehearsal of each sub-run with the real
vendor file, Run A, Run B, Run C, analysis, journal. Mid-run commits after each sub-run's
artifacts land, per the predecessor's practice.

## 4. Expected cost, stated before spending

Azure/us prices $1.91 in / $3.83 out per MTok; input estimated at 185 tokens per node plus ~2k
template per call; output at 2.0 tokens per commissioned word; a 1.4x multiplier covers Stage D
passes (the predecessor measured 1.3x; the ledger sums fill plus Stage D, which is why its $1.03
plan became $1.99 measured).

| Item | First pass | With repairs |
| --- | ---: | ---: |
| Endpoint probes (~12 x 32 tokens) | $0.05 | $0.05 |
| Run A (2 x tin-whistle-map, directive overhead) | $0.75 | $0.95 |
| Run B (10 books, 92,870 words, ~206k in / ~186k out) | $1.10 | $1.55 |
| Run C (v3.2 x 2 books, ~270k in / ~122k out at $0.25/$0.80) | $0.17 | $0.30 |
| **Total expected** | | **~$2.85** |

**Stop rule**: if measured spend exceeds **$5.70** (twice the estimate), stop and report, per the
round's instructions. Content-filter failures (`AL-492`) are budgeted inside the repair margin and
classified by (skeleton, brief) pair, never by brief or skeleton alone.

## 5. Instrument blind spots carried into interpretation

- A green gate is not a clean book: the predecessor's gate passed all three unpublishable books.
- `check_fill_integrity`'s structural verdict fires on every filled book via the
  `schema_version` 2.0/2.1 pipeline stamp; only the per-field diff is informative, so the
  mutation census classifies fields itself and treats the script's exit code as a floor.
- Word-list noun-substitution checks fail in both directions (`AL-497`); none is used as a
  verdict here.
- Beats-overlap does not order books by quality (`AL-496`); not used for ranking.
- The 0.6 fill-rate floor's real headroom over known-good is 0.035, not 0.115; the floor is not
  raised or tuned this round.
- Band conformance is reported only next to fill rate (`AL-491`).

## 6. Non-goals

No production-code fixes (defects become lessons plus register rows); no resolution of `UW-C311`
or the `UW-C307` gate-carriage question (owner decisions; this round only produces evidence); no
new skeletons.

---

## 7. Results

### 7.1 Offline results (no network; computed while Run A executed)

**The mutation census instrument reproduces the predecessor's findings exactly**, which validates
it before it grades anything new: book 1 `story.id` only; book 2 `title` plus 27/36 ending
titles; book 3 `metadata.themes` plus `title` plus 15/35 ending titles. Extending it to the two
raw shared-skeleton pair books and the book-4 rerun (all committed by the predecessor run but
never censused): pair book 0 reskinned `title` plus 10/35 ending titles, pair book 1 `title`
plus 21/35, rerun-book4 `title` plus 2/6; none of the three touched a frozen field. Prior-model
tally across all six committed v4-pro one-shot books: **frozen-field mutation 2/6, ambiguous-field
drift (title or ending.title) 5/6**. Run B extends the denominator.

**Outbound-choice staging (AL-495/UW-C312) separates cleanly and the defect tracks fill rate.**
A prototype outbound companion to `CG-4` (content-word overlap between a node's own choice labels
and its body, same caveat as CG-4) scores the 39 committed known-good fills at **median 0.037
dangling rate** (range 0.000 to 0.327; the high tail is the two 551-node twins and other
gamebooks, where terse labels legitimately paraphrase). The five live v4-pro books score
**0.690 to 0.854**. A factor-of-20 separation on committed data means the rule is buildable and
the live fills are systematically breaking it, as AL-495 predicted from the word shortfall.

**Sibling convergence: shared structure is the driver, and it is not a DeepSeek idiom.** Pairwise
`check_sibling_fills` across every same-band pair of committed filled books (70 pairs): median
**1.2** shared four-grams per 1000, and only one pair exceeds 13. That one pair is
`the-harrowstone-keep` x `the-sunken-temple`: two deliberately distinct committed books (different
ids, titles, themes; exactly one byte-identical body out of 551) that share a 551-node structure,
and they score **202.0 per 1000**, twice the DeepSeek pair's 96.3. So the convergence `UW-C315`
measures is intrinsic to filling a shared structure, not a vendor defect, and cross-skeleton
same-band reuse is comfortably inside budget while same-skeleton reuse is 24-50x over it,
whoever the author is. This sharpens what Run A's directed delta has to prove.

**Fill rate varies book-to-book on one (skeleton, model) pair.** The raw pair's two books,
re-scored with the new `--min-fill-rate` floor: book 0 delivers 65.2 percent (passes 0.6),
book 1 delivers 42.9 percent (fails). Same skeleton, same model, same pin, same undirected
condition: the floor is a coin flip at this vendor's delivery variance, which is itself a
bulk-relevant fact.

**Protagonist presence is measurable, but the rule has to key on the declared person, not a
universal floor.** Across 31 committed fills, gamebooks score second-person node rates of 0.715
to 1.0 while third-person prose books sit at 0.0 to 0.27, so a single threshold cannot serve
both. The beats themselves carry the signal: skeletons whose `beats=` text uses second-person
pronouns at a high rate (0.45 to 0.69 on the two live gamebooks) got fills whose second-person
rate tracks it closely (0.448 and 0.88), while `the-tin-whistle-map`'s beats are only 0.03
second-person, and its three fills scatter to 0.073, 0.13 and 0.715. So AL-496's "worst defect"
book was not violating a stated contract: the contract never pins narrative person for prose,
and same-skeleton siblings can legitimately land in DIFFERENT persons. That unpinned degree of
freedom is the finding.

### 7.2 Run A: the directed delta (UW-C315). The directive is not the lever.

Both directed fills passed the gate first-attempt; measured cost $0.7190 against the $0.75
estimate. The delta:

| Condition | Shared 4-grams | Per 1000 mean leaf words |
| --- | ---: | ---: |
| Raw undirected pair (2026-08-20, committed) | 1,350 | 96.3 |
| Best-case directed pair (this run) | 1,565 | **110.7** |
| Budget | | 4.0 |

The strongest spec the production `build_differentiation_directive` can emit (catalog level,
opposed axes, sibling title carried) moved the number the WRONG way: +16 percent in absolute
shared grams on near-identical delivered volume (mean leaf words 10,575 raw vs 10,657 directed),
+15 percent normalized. Both measurements used the same instrument and normalization
(`compare_vendors`' internal figure for the raw pair is 96.28, matching the committed
`check_sibling_fills` 96.3). Combined with 7.1's finding that the committed hand-authored
same-skeleton twins score 202.0, the conclusion is decision-grade: **shared-structure convergence
is intrinsic and the differentiation directive does not counter it.** Cross-family skeleton reuse
needs a structural lever (per-family skeleton mutation per ADR-020 machinery, or a reuse cap),
not a prompt block. `check_sibling_fills` still belongs in the pipeline as the detector either
way.

Secondary observations from the same two books, feeding the round's other questions:

- Both books under-delivered and FAIL the new floor: 50.0 and 58.9 percent fill rate. With the
  raw pair's 65.2/42.9, four fills of this (skeleton, model) pair span 42.9 to 65.2 percent,
  straddling 0.6: the floor is a per-book coin flip at this vendor's delivery variance.
- Mutation census: zero frozen-field mutations in either book; ending titles reskinned in both
  (13/35 and 21/35); book 1 also retitled the story. Book 0 kept the skeleton's title "The Tin
  Whistle Map" on a book whose object is an enamel compass, so BOTH behaviors are reader-visible
  defects depending on the unresolved `UW-C311` ruling: a reskinned title violates the freeze
  reading, a kept title mislabels the re-themed book.
- Outbound dangling rates 0.760 and 0.738, consistent with the fill shortfall mechanism.
- Narrative person split again on the same skeleton: second-person node rates 0.648 vs 0.254,
  confirming 7.1's unpinned-person finding under the directed condition too.

### 7.3 Run C: the chunked path took three takes to reach, and the blockers are the finding

**Take 1 (committed as `chunked-v32/`): the cap table is never consulted on any OpenRouter leg,
harness or production.** Both legs died in 0.6s with a flattened "HTTP 400 (invalid or
unavailable model)". Root cause, proven by direct construction: `OpenRouterProvider` exposes only
`complete` and `name`; it has no `model` attribute. `MeteredProvider` and `PiiGuardedProvider`
both dutifully forward `.model` by `getattr`, so they forward `None`, and
`fill_skeleton`'s `resolve_output_cap(provider.model)` resolves the permissive 131,072 default
for EVERY OpenRouter model. Consequences: `MODEL_OUTPUT_CAPS` is dead configuration on the
`openrouter` backend (the `AL-428` "clamp silently does nothing" defect, reintroduced one layer
up); the `UW-C302` chunked path can never engage on the one backend with low-cap models; and
Stage B over-asks every low-ceiling endpoint. The direct-`anthropic` adapter DOES expose
`.model` (property, `providers/anthropic.py`), which is why the orchestrator's own cap tests
pass: they exercise the adapter that has the attribute. This answers the predecessor's 8.2
question (does the production path pin or clamp?) worse than either hypothesis: on openrouter
the clamp is not mis-keyed, it is blind. Fixed at the harness boundary only
(`_ModelStampedProvider` in `compare_vendors.py`, commit 956dec9); the adapter itself is
deliberately left for the register row.

**Take 2 (committed as `chunked-v32-take2/`): the chunked path has no context accounting, and it
overflowed by exactly one token.** With the model visible, the cap resolved to 65,536, chunking
engaged, and the first batch call was rejected: the raw provider error (surfaced only by
monkeypatching the HTTP client; the adapter flattens 400 bodies) reads "maximum context length is
163840 tokens. However, you requested 58983 output tokens and your prompt contains at least
104858 input tokens, for a total of at least 163841". `plan_fill_batches` bounds each batch's
OUTPUT under the cap, but the batch prompt carries the whole document, so input grows with
skeleton size while nothing checks input + ask against the endpoint's context window. Every
committed v3.2 endpoint has the same 163,840 context, so no pin escapes it for a skeleton this
large (`the-hollow-crown-gambit`'s batch prompt alone is ~104.9k tokens). The feasibility
machinery reasons entirely in output tokens; the chunked path it gates inherits the assumption
that context is unbounded, which is false exactly on the low-cap backends the path exists for.

Take 3 re-targets `the-hollow-sea` (129,926-byte skeleton, 27,068 words, still over the 52,429
feasibility ceiling, so it chunks with context slack), filled twice from two distant briefs,
which also yields a same-skeleton chunked pair. Its result is below.

**Take 3 (committed as `chunked-v32-take3/`): a 512-token probe does not qualify an endpoint.**
With context fitting, both legs failed at the merge: the DigitalOcean endpoint answered the
~40k-token batch asks with 2,133 and 7,349 output tokens of unusable shape (one reply not a JSON
object, one an empty mapping covering zero of 190 asked nodes). The same batch prompt sent to
`novita/fp8` directly returned a complete 77,599-character fenced-JSON batch. So the pre-flight
convention ("one small completion per pin") passes endpoints that cannot serve large structured
asks; endpoint qualification needs one representative large ask, not a ping. The pin and price
row moved to `novita/fp8` together (commit 4f0d0f0-era; see git history).

**Take 4 (committed as `chunked-v32-take4/`): the chunked path produced its first live book, and
the chunked book is the only measured book with ZERO mutations.** Leg 1 (railway brief) passed
the gate through the two-batch chunked path in 1,077s at $0.070:
`check_fill_integrity` reports a CLEAN structural pass (the first of the whole live program),
0 of 40 ending titles moved, story title kept. Leg 0 (glacier brief) failed at batch 1 with an
empty mapping on the same pin, while the same brief had succeeded in the direct take-3
replication, so the empty-batch failure is per-call nondeterminism, not a poisoned pair.
The `UW-C311` evidence is now concrete in both directions: one-shot v4-pro books reskin ending
titles in 7 of 8 measured cases, and the chunked path structurally cannot and measurably did
not. The two paths produce contractually different books today. Costs of the datapoint, stated:
the chunked book delivered 37.5 percent of its commissioned words (the worst fill rate measured,
on a model chosen for its cap rather than its prose) and its reading level sits far under the
13-16 target (2.5 percent of nodes in band), so "the path works" is a statement about contract
mechanics, not about publishable output from this model.

### 7.4 Run B: the ten-book grid

Eight of ten books passed the gate; two legs died with the harness's flattened "transient
failure persisted" and were re-probed directly: book 2 (`the-seedling-thief` x the aquarium
hermit-crab brief) is a zero-content `content_filter` stop, and book 7 (`the-observatory-shift`
x the flood-warden brief) is a zero-content HTTP 200 with `finish_reason: None`, the same
signature the predecessor's book 0 showed before it proved to be a filter. Two of ten benign
children's briefs, against the predecessor's two of five: the pair-failure rate is holding
around 20 to 40 percent and the harness still cannot name it (`UW-C309`).

Per-book instrument results (fill rate is delivered/commissioned; staging is the dangling
outbound-label rate whose known-good median is 0.037; person is the second-person node rate):

| # | Skeleton (band) | Fill rate | Floor | FK / in-band | Staging | Person | Frozen mutated | Ambiguous mutated |
| ---: | --- | ---: | :-: | --- | ---: | ---: | --- | --- |
| 0 | market-morning (3-5) | 124.6% | ok | 0.79 / 71% | 0.100 | 1.000 | none | title, 5/6 endings |
| 1 | big-cardboard-box (3-5) | 117.0% | ok | 0.97 / 84% | 0.029 | 0.932 | none | title, 18/18 endings |
| 2 | seedling-thief (5-8) | failed leg: content_filter, 0 content | | | | | | |
| 3 | bridge-of-stones (5-8) | 62.8% | ok | 2.20 / 50% | 0.652 | 0.379 | none | title, 8/12 endings |
| 4 | half-hour-call (8-11) | 58.9% | FAIL | 3.90 / 67% | 0.710 | 0.098 | none | 4/14 endings |
| 5 | lantern-keepers-list (8-11) | 44.1% | FAIL | 3.63 / 65% | 0.740 | 0.104 | none | title, 15/24 endings |
| 6 | glass-comet (10-13, t2) | 48.8% | FAIL | 4.89 / 67% | 0.345 | 0.581 | **variables, metadata.themes** | title, 8/20 endings |
| 7 | observatory-shift (10-13) | failed leg: empty 200, finish None | | | | | | |
| 8 | iron-spire-trial (13-16 gb, t2) | 56.7% | FAIL | 5.27 / 43% | 0.279 | 0.834 | **variables, metadata.themes** | title, 63/79 endings |
| 9 | quarantine-ledger (16+) | 136.4% | ok | 8.38 / 50% | 0.726 | 0.035 | none | title, 11/38 endings |

Four load-bearing patterns:

1. **The fill-rate defect is band-shaped, not a constant.** 3-5 over-delivers (117 to 125
   percent), 16+ prose delivers everything and more (136.4 percent raw, 95.3 percent once
   per-node surplus is capped, FK 8.38 in range), and every band from 5-8 through 13-16
   delivers 44 to 63 percent. The predecessor measured its "words= is not honored" defect
   almost entirely on gamebooks and mid bands; this grid adds the two ends and the constant-
   shortfall story does not survive them. The floor's coin-flip zone is specifically the
   middle bands.
2. **Both tier-2 books, and only the tier-2 books, mutated `variables`.** In both cases the
   mutation is confined to `description` text, rethemed to the brief (plates to glass slides,
   crown-seal to brass grommet); names, types, bounds and initials are intact, so conditions
   still evaluate. `fill.md` freezes `variables` wholesale. The pattern with `metadata.themes`
   (also rethemed in the same two books, and in the predecessor's book 3) is now clear: **the
   model reliably rethems every theme-bearing text field the contract happens to freeze**, and
   the freeze mixes machine-critical fields with documentation prose in one block.
3. **The outbound-staging defect is not only a fill-rate symptom.** Book 9 delivered 136
   percent and still dangles 72.6 percent of its outbound labels (known-good median 0.037).
   Short fills guarantee the defect (books 3-5 at 0.65-0.74) but full delivery does not cure
   it; `UW-C312`'s rule is needed on its own merits.
4. **Live same-band different-skeleton pairs are inside budget: mean 1.27, max 3.30 per 1000
   over 28 pairs**, agreeing with the committed-book sweep (median 1.2). Cross-skeleton reuse
   is diversity-safe even for this vendor; ALL the convergence risk is concentrated on
   same-skeleton reuse.

### 7.5 The round's tally and the bulk recommendation

**Frozen-field mutation rate (the round's headline question): 4 of 16 one-shot v4-pro books
(25 percent) mutated at least one frozen field; 15 of 16 (94 percent) mutated an ambiguous one
(story title or ending titles).** The frozen mutations are: one story `id` rewrite
(predecessor book 1), and three theme-bearing-documentation reskins (`metadata.themes` x3,
`variables[].description` x2). The one chunked book measured is the only book with zero
mutations of any kind, because its merge is a whitelist. So the answer to "is frozen-field
mutation a per-book coin flip?" is: **structure-critical mutation is rare (1 of 16); frozen
theme-text mutation is common (3 of 16, and 2 of 2 on tier-2 skeletons where variable
descriptions exist to retheme); ambiguous-field drift is near-universal (15 of 16).** At bulk
scale, per hundred one-shot books, that is roughly six books violating the letter of the freeze
on theme text, one book with a corrupted identity field, and ninety-four books whose titles
differ from their skeletons under a contract that cannot say whether that is legal.

**Cost**: measured $3.28 metered (Run A $0.719, Run B $2.432, takes 3-4 $0.133) plus roughly
$0.45 unmetered probing and replication, about **$3.75 total against the $2.85 estimate**,
inside the twice-estimate stop rule. The grid alone ran 57 percent over its line item, almost
entirely book 9's 136-percent delivery and 2,810-second latency, which is worth knowing for
bulk budgeting: a 16+ prose book can cost 3x a mid-band book of the same node count.

**Go or no-go on bulk generation: NO-GO as currently configured**, on five specific defects
that would replicate across a bulk catalog, in priority order:

1. **Same-skeleton reuse produces near-duplicate books and no existing lever fixes it.** Raw
   96.3, best-case directed 110.7, careful hand-authored twins 202, against a budget of 4.0;
   the directive is measurably not the lever (`UW-C315`). Bulk reuse of one skeleton across
   families ships recognizably the same book until a structural lever (ADR-020 per-family
   mutation, or a reuse cap) exists and is measured. Cross-skeleton reuse is safe (1.27 mean).
2. **The mid-band fill-rate hole.** Every 5-8 to 13-16 one-shot book delivered 44 to 63
   percent; four of eight grid books fail the new floor. In bulk, half the mid-band catalog
   fails integrity or ships thin (and the deterministic gate alone blocks none of it).
3. **The contract cannot say what a legal reskin is.** Near-universal title/ending-title
   drift, plus systematic retheming of frozen documentation fields (`metadata.themes`,
   `variables[].description`), plus one id corruption. Until the freeze is split into
   machine-critical (hard, gate-enforced) versus theme-bearing (explicitly writable or
   explicitly kept), bulk books will randomly violate whichever reading the tooling assumes
   (`UW-C311` generalizes).
4. **A fifth to two-fifths of (skeleton, brief) pairs die with zero content on benign
   children's briefs**, reported as a generic transient failure (`UW-C309`). Bulk needs the
   real `finish_reason` surfaced and a pair-level unfillable policy before it can even
   budget.
5. **The chunked path and the cap machinery are not production-ready on OpenRouter**: the
   adapter's missing `.model` disables the clamp and chunking entirely, the path has no
   context accounting, and endpoint qualification by small probe is insufficient. Any bulk
   plan that includes books over ~52k output tokens on a low-cap backend is running on a path
   that has produced exactly one live book ever, behind a harness-only fix.

None of these blocks bulk *skeleton* authoring (the offline strict census and mutation
machinery are unaffected); the no-go is specifically for bulk one-shot STORY generation
against the current contract and instruments. The five defects above are each carried as a
lesson with a register row; items 2 through 5 are tooling-scale work, and item 1 is a design
decision the owner already holds (`UW-C315`'s lever question).

## 8. Owner rulings (2026-08-21)

Three rulings were made by the owner on 2026-08-21, in this round's session, on the three
decisions section 7.5 left open. This section is the site of record for all three; other
documents cite it rather than restating it.

### 8.1 Reuse (`UW-C315`): the diversity bar is any-reader, not social distance

The owner rejects scoping reuse by social distance. The product intent is a global catalog:
ideally every book goes into the global skeleton pool and a single reader could pick up ANY
books that share a skeleton. Therefore same-skeleton reuse must be diverse enough that any
given reader does not feel they are reading the same book twice. Consequences:

- The bar for a same-skeleton pair is reader-perceived difference for the SAME reader, so the
  relevant comparators are the cross-skeleton range (1.2 to 3.3 per 1000, which readers
  experience as different books) versus the measured same-structure floor (96.3 to 202).
- The differentiation directive is measurably not the lever (section 7.2), so per-family or
  per-book STRUCTURAL mutation (the ADR-020 machinery) is the only candidate lever, and its
  effect on the sibling metric is the single most decision-relevant unmeasured number in the
  catalog plan. The mutation-diversity experiment (mutate a committed skeleton, fill the
  mutant, score against the committed sibling fill) is now the critical-path measurement.
- Until a lever is measured to reach the bar, same-skeleton books must not be served to the
  same reader; that is an interim serving constraint, not the ruling's end state.

### 8.2 Freeze split (`UW-C316`): adopted as recommended

- Machine-critical fields (every `id`, `target`, `condition`, `effects`, `on_enter`,
  `start_node`, `is_ending`, variable `name`/`type`/`min`/`max`/`initial`, ending
  `kind`/`valence`) are frozen, and the pipeline stops depending on model obedience: the
  import path NORMALIZES these fields back from the skeleton after fill, so model drift on
  them becomes a non-event rather than a shipped defect or a wasted repair cycle.
- Theme-bearing text is ruled per field: story `title` writable; `variables[].description`
  writable; `ending.title` writable (section 8.3); `metadata.themes` neither model-written
  nor kept stale, but re-derived at import time, because it feeds matching and
  recommendations.
- `fill.md` may keep instructing the model not to touch frozen fields, but enforcement is
  normalization plus the integrity check, not the instruction.

### 8.3 `ending.title` (`UW-C311`): leaf content, writable

`ending.title` and the story `title` are leaf content, consistent with the WS-0
labels-are-leaves principle and the `AL-161` recognition-channel finding. `ending.id`,
`ending.kind`, and `ending.valence` remain frozen (they carry the PL-15 fail-state policy).
Implementation: `merge_fill_batch` widens its whitelist to carry ending titles (and the story
title) so the chunked path stops producing contractually different books;
`check_fill_integrity` treats title rewrites as legal by default; `fill.md` and `SKILL.md`
cite this section.
