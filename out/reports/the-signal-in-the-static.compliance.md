# Compliance report: the-signal-in-the-static (filled)

- **Cell**: 13-16 / medium / prose (Wave 2)
- **Skeleton**: `skeletons/13-16/the-signal-in-the-static.json` (123 nodes, branch_and_bottleneck, tier 1, 32 endings)
- **Author model**: sonnet (fill + reading-level passes); **repairs on opus** + supervisor dominator fix (Fable-outage routing)
- **Reviewer model**: opus (full review, then a focused independent confirmation)
- **Disposition**: APPROVED (independent Opus confirmation after the repairs)

## Deterministic checks (final)

```text
ok   structure: only node bodies differ
ok   markers: no <<FILL markers remain
ok   words: mean 118.0/node over 123 nodes (target 140, advisory 100-185, max 310)
findings=37 blocked=False safety_flagged=False
```

**Reading-level waiver (bounded)**: 37 residual RL-13 warnings, all at or
below FK 9.6 (band 5.5-8.5). The original above-band tail (up to FK 15.3) was
driven down across two passes; the mild residue is waived for the YA register
per the run's bounded-waiver rule. No node above 9.6.

## Review history

Full independent review returned REVISE across categories 1, 2, 3, 5, 6:
route-neutrality/fair-play leaks at merge nodes, a valence mismatch, and a
heavy intensifier tic. The Opus repair addressed all findings (name leaks at
`mm_count_*` -> "M", `n_b3` synthesis rewritten path-universal, scrap/logbook
leaks removed, time-of-day collision resolved, `e_he_takeover` rewritten to a
dignified setback matching its negative valence, and an intensifier copyedit:
fully 44->3, really 76->10, at last 45->11, patient 29->13, simply 34->11).

## Supervisor-caught leak (missed by both the review and the repair)

Structural graph analysis found a residual fair-play leak: the daughter's name
"Marin" is a who-thread-only discovery (revealed in `mm_list_*`), but ~19
post-convergence nodes and three IMMUTABLE choice labels (`f_st_answer`,
`f_re_rig`, `f_he_act`) use it, so count/coordinate/relay-thread readers met
the name cold. Because the labels are structure, scrubbing "Marin" from bodies
would leave labels contradicting them. The fix exploited a dominator: removing
`n_b3_choice` disconnects all 12 Marin-using endings and all three
Marin-label nodes from the start (38 nodes lost) while the who-thread reveals
stay reachable. A single edit to `n_b3_choice` now establishes the name
universally at the synthesis ("the listener he called M, the daughter the
county records name Marin"), attributing it to an external universal fact so
it reads correctly on every thread and licenses every downstream use.

## Focused independent confirmation (Opus)

Re-verified: (1) name-leak resolved (dominator reachability numbers
reproduced; `mm_count_*` confirmed "M"); (2) the `n_b3` "half the answer" vs
`n_b3_choice` name-reveal tension judged acceptable (records-attributed
convergence reveal, not a contradiction); (3) intensifier copyedit left no
broken prose; (4) no new fragments in the nine repaired nodes; (5)
`e_he_takeover` valence correct. OVERALL: APPROVE.

## Supervisor adjudication

Approved. Completes the 13-16 medium cell and **Wave 2 (all 7 stories)**.

## Skeleton defects filed (pre-run production skeleton)

1. Three post-convergence choice labels (`f_st_answer`, `f_re_rig`,
   `f_he_act`) hardcode the who-thread-only name "Marin", forcing the
   universal-reveal workaround; a skeleton revision should genericize them to
   "M" or ensure every thread earns the name.
2. `n_b2_choice` forces a hard who-vs-count choice, yet the skeleton's
   downstream design assumes both threads' findings; a revision should
   reconcile the "half the answer" framing with the named-daughter payoff.
