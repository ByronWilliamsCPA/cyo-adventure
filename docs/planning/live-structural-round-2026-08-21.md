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

### 7.2 Live results

Appended after execution.
