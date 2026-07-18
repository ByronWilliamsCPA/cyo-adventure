# Compliance report: the-teddy-bears-picnic (filled)

- **Cell**: 3-5 / medium / prose (Wave 2)
- **Skeleton**: `skeletons/3-5/the-teddy-bears-picnic.json` (29 nodes, loop_and_grow hub-gather, tier 1)
- **Author model**: haiku (initial fill + 2 repair cycles) + supervisor finishing pass (2 line edits)
- **Reviewer model**: sonnet (initial review + delta re-review)
- **Disposition**: APPROVED (supervisor adjudication after delta re-review)

## Deterministic checks (final)

```text
ok   structure: only node bodies differ
ok   markers: no <<FILL markers remain
ok   words: mean 40.4/node over 29 nodes (target 40, advisory 28-55, max 90)
findings=9 blocked=False safety_flagged=False
```

**Waiver (RL-13 x9)**: all residual advisories at or below the grade target
(FK -1.1 to 2.0 against target 1.0 +/- 1.0, none above 2.0); simpler-than-
target is acceptable for 3-5 read-aloud.

## Pipeline history

1. **Initial fill (haiku)** passed structure/markers but undershot word
   density: mean 28.0 vs the skeleton's 41.9-word hints; the gate's PL-19
   caught it. Repair cycle 1 expanded to mean 39.9 and cleared the two
   above-target RL-13 nodes.
2. **Independent review**: REVISE with substantive findings: hub node
   asserting "basket is empty" on every revisit, an invented item list at
   `n_welcome` breaking path-neutrality, ungrounded bell/ball/kite choices,
   five grammar slips, ending padding from the expansion.
3. **Repair cycle 2 (haiku)**: all statelessness, grounding, beats, grammar,
   and rhythm fixes applied.
4. **Delta re-review**: all five areas FIXED except two trivial items
   (a missed word-order fix in `e_owl_oops`; one orphan fragment in
   `e_nap`), applied directly by the supervisor and re-verified. No new
   problems introduced by the repairs.

## Skeleton defect logged (not a fill issue)

The delta re-review surfaced that `n_arrange` and `n_share` name honey and
berries specifically, and the skeleton's OWN beats specify this (as they do
for `e_nap`'s "full of honey and berries"), while those nodes are reachable
on paths where neither item was fetched. The fill is beat-faithful there;
where beats and statelessness conflicted at `n_welcome`/`e_song`/`e_nap`,
the supervisor ruled for statelessness (item-neutral prose) as the safer
reading. **Follow-up**: the teddy-bears-picnic skeleton's finale spine
(`n_arrange`, `n_share`, and the `e_nap` beat) should be made item-neutral
in a future skeleton revision; logged here as the tracking record.

## Supervisor adjudication

Approved. Craft: warm, rhythmic hub-gather with onomatopoeia well-suited to
read-aloud; the repair cycles removed the mechanical seams. Process note:
this story consumed Haiku's full two-cycle repair budget; the lean-fill
failure mode (undershooting words= hints) is now pre-empted in author
prompts, and the supervisor finishing pass covered two one-line residuals
rather than escalating to Opus for trivia.
