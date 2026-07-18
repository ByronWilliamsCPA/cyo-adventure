# Compliance report: the-last-train-north (filled)

- **Cell**: 16+ / medium / prose (Wave 2)
- **Skeleton**: `skeletons/16+/the-last-train-north.json` (143 nodes, branch_and_bottleneck, tier 1)
- **Author model**: sonnet (fill + reading-level passes); **repair on opus** (Fable-outage routing)
- **Reviewer model**: opus (independent, fresh context; verified all 25 kind/valence pairs programmatically)
- **Disposition**: APPROVED (supervisor-verified after the Opus repair)

## Deterministic checks (final)

```text
ok   structure: only node bodies differ
ok   markers: no <<FILL markers remain
ok   words: mean 160.3/node over 143 nodes (target 175, advisory 125-230, max 385)
findings=21 blocked=False safety_flagged=False
```

**Reading-level waiver (bounded)**: 21 residual RL-13 warnings, all at or
below FK 11.0 (band 7.5-10.5). The above-band tail (originally up to FK 12.9)
was driven down in a prior pass; the remaining mild residue (10.5-11.0) is
waived as acceptable for the 16+ adult register, per the run's bounded-waiver
rule. No node above 11.0.

## Independent review (initial verdict)

Categories 2 (content policy), 3 (beats), 4 (choice setup), 6 (endings),
7 (safety) PASS. Categories 1 and 5 FAIL:

- Language: one fragment scar (`g0a2_2`, a verbless noun phrase from a
  comma-split); the parallel gate structure also produces a same-shape
  refrain across a playthrough (noted as motif, not defect).
- Continuity (critical): the true bottlenecks (4 pivots + 16 `g?a?_4`
  converge nodes) were praised as cleanly route-neutral, but five
  object-thread nodes asserted route-specific prior actions (a warm seat
  "beside the traveler she has been helping" at the all-thread `r_dawn`
  convergence; letter possession/prior-reading and a map-decode callback
  at pivot-offered nodes; "pressed twice now").

## Repair cycle (opus; supervisor-verified)

All six fixes applied and confirmed by direct inspection + stale-phrase scan:
fragment rejoined; the traveler reframed as freshly introduced; letter/map
prior-action assumptions removed from `g2a1_1` and `r_truth1`; "pressed twice"
cut; two punch-clock callbacks softened. The `p4` leave-label setting mismatch
lives only in the immutable choice label; no body prose contradicts it, so no
edit was needed. All edited nodes FK-verified <= 11.0.

## Supervisor adjudication

Approved. This is accomplished 16+ literary CYOA (controlled adult register,
a coherent passage-not-arrival through-line, model handling of the real
convergence nodes). Completes the 16+ medium cell. Publication still requires
the ADR-005 human approval flow after DB import.

## Skeleton defect filed (pre-run production skeleton)

`skeletons/16+/the-last-train-north.json`: the ending id/title
`e_truth_early` / "Half the Timetable" belongs to the timetable, but the
entire `r_truth` thread (and thus the ending's declared beat) is about the
letter. The fill correctly matched prose to the thread; the title mismatch is
structural and should be corrected in a future skeleton revision (also worth a
`docs/template_feedback.md` note: `role=` scaffolding on `g3a1_end`/`g3a2_end`
contradicted their declared positive ending objects).
