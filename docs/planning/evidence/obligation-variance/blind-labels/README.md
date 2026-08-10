# Blind decision-signature annotations

Every annotation behind section 9.5 of
[the decision-variance experiment spec](../../decision-variance-experiment-spec-2026-08-10.md).

Each file is one annotator's signatures for one contract, produced under the
[decision signature labelling principle](../../decision-signature-labelling-principle.md) v1.
Annotators received the contract stripped of any prior `decisions` block, renamed neutrally, with
no knowledge of what was being compared, which artifact was the control, or that divergence was
the goal. No annotator authored any contract it labelled.

| File | Contract | Arm |
| --- | --- | --- |
| `annotator0_v2.json`, `annotator0_v5.json` | v2, v5 | control base, treatment |
| `annotator1_v2.json`, `annotator1_v3.json` | v2, v3 | control base, control |
| `annotator2_v2.json`, `annotator2_v3.json` | v2, v3 | control base, control |
| `annotator3_v2.json`, `annotator3_v3.json`, `annotator3_v5.json` | v2, v3, v5 | all three, one hand |

`annotator3` is the within-annotator series and is the one quoted in the spec's headline table,
because a single hand labelling all three plans removes cross-annotator variance from the
comparison of the two pairs. Annotators 0 to 2 replicate it across hands.

## Reproducing the numbers

The checkers read a contract with a per-node `decisions` block, so graft a label file onto its
contract before scoring (the spec's section 9.5 numbers come from exactly this):

```python
import json
contract = json.load(open("../contract_v2.json"))
labels = json.load(open("annotator3_v2.json"))
for node_id, block in labels.items():
    contract["nodes"][node_id]["decisions"] = block
```

Then:

```bash
uv run python scripts/check_decision_overlap.py <grafted_v2.json> <grafted_v3.json>   # control pair
uv run python scripts/check_decision_overlap.py <grafted_v2.json> <grafted_v5.json>   # treatment pair
uv run python scripts/check_annotator_agreement.py annotator1_v2.json annotator2_v2.json
```

## The result these files carry

The signatures rank the treatment pair as **more** decision-repetitive than the control pair
(28/28 against 24/28; 1.000 against 0.929 on action family), and two blind readers of the finished
books rank it as **less** repetitive. Agreement between annotators on the same artifacts is kappa
0.96 on `action_family` and 1.000 on `consequence`, so the inversion is not annotator noise. See
`AL-200` and `AL-201`.
