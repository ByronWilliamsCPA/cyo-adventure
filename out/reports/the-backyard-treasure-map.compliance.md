# Compliance report: the-backyard-treasure-map (filled)

- **Cell**: 5-8 / medium / prose (Wave 2)
- **Skeleton**: `skeletons/5-8/the-backyard-treasure-map.json` (61 nodes, time_cave, tier 1)
- **Author models**: haiku (initial fill + 2 repair cycles), then **opus escalation**
  (full-file voice rewrite), then supervisor finishing pass (2 line edits)
- **Reviewer model**: sonnet (full review, then full re-review of the rewrite)
- **Disposition**: APPROVED (supervisor adjudication after re-review)

## Deterministic checks (final)

```text
ok   structure: only node bodies differ
ok   markers: no <<FILL markers remain
ok   words: mean 66.4/node over 61 nodes (target 70, advisory 50-95, max 155)
findings=0 blocked=False safety_flagged=False
```

Zero RL-13 warnings (all 61 nodes in FK 1.0-4.0 against target 2.5 +/- 1.5).

## Pipeline history (the run's first Opus escalation)

1. **Initial fill (haiku)**: structure/markers clean but lean (mean 45.2 vs
   the skeleton's 70.5-word hints; PL-19 fired) with 4 below-floor RL-13
   nodes; the report rationalized the undershoot.
2. **Repair cycle 1 (haiku)**: expanded to mean 55.6 but pushed 26 nodes
   below the FK floor (short-sentence expansion lowered grade).
3. **Repair cycle 2 (haiku)**: word mean 58.8, zero gate findings; but the
   independent review then FAILED 5 of 7 categories: two clashing
   mechanical registers (fragment staccato vs "and"-chains), an 8-instance
   doubling motif, 3 dropped lemonade beats, a templated setback closer,
   an ungrounded 3-way opening choice, and an unmodeled crate-climb risk.
4. **ESCALATION (opus)** per the plan's two-cycle bound: full-file rewrite
   into one warm past-tense early-reader voice; all six fix areas resolved;
   mean 66.5; zero findings.
5. **Full re-review**: 6 of 7 PASS; two one-sentence residuals (an
   unconverted present-tense opening line; a near-duplicate setback closer),
   applied by the supervisor with one self-correction (an initially
   incoherent replacement line was caught against the beat and fixed), then
   re-verified.

## Final review verdict

Age-appropriateness, content policy, beats fidelity, choice setup, ending
quality, safety: PASS. Continuity: the single tense break found was fixed.
Reviewer's craft note: the rewrite achieves one consistent authorial voice
with a deliberate onomatopoeia-plus-tag device ("Creak, went the door")
reading as style, not mechanics.

## Process lessons recorded

1. Haiku's lean-fill failure mode (undershooting words= hints, then
   rationalizing) consumed both repair cycles without converging on voice
   quality; the escalation path worked exactly as designed and the Opus
   rewrite was cheaper than a third failed cycle.
2. For remaining young-band fills, author prompts now state: expansion must
   come from sensory beats in short sentences, never connector-joins alone,
   and words= hints are hard targets, with PL-19 named in the exit criteria.
3. Supervisor finishing edits must be checked against the node's beat
   before applying (the box/swirls slip caught here).
