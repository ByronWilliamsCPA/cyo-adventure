<!--
Skeleton-promotion PR template (WS-8 D4, ADR-020 decision 4 / design 5.4, 4.3).
Open with ?template=skeleton_promotion.md, or let prepare_promotion_pr.py fill the
body. This PR IS the human structure-approval instrument. Automation prepared it;
a human must review and merge it. There is no auto-merge, ever.
-->

## Skeleton promotion

<!-- prepare_promotion_pr.py fills the lineage, acceptance transcript, re-guidance
     table, and diagram reference above/below this checklist. -->

Promoting a gate-passed, human-approved mutated skeleton into `skeletons/`. The
`skeleton-promotion` CI job re-proves the gate, contract, anti-clone floor, and
lineage/hash from scratch; this checklist is the human structure approval it
cannot mechanize.

### Structure-approval checklist (ADR-020 decision 4; all required)

- [ ] I reviewed the **structure diagram** and it is a sensible, playable tree.
- [ ] I read the **acceptance transcript** (`acceptance.json`) and it is
      `promotable`, with every stage passing.
- [ ] I confirmed the **lineage** parent, op-chain, and donors, and the CI
      `skeleton-promotion` job is green (gate + contract + floor + hash re-proved).
- [ ] I reviewed and **approved every agent-drafted re-guidance item** in the PR
      body: each row whose `Author` starts with `agent:`. (One approval per item;
      the drafted text becomes beats guidance that re-enters future fill prompts.)
- [ ] For every **CHOICE / ENDING** re-guidance row, I performed a specific
      **action-semantic** review: the drafted label/title still honors the frozen
      action-semantic obligation of that choice or ending (design 5.4; this is the
      check the deterministic floor cannot make).
- [ ] The `sample-fill/` evidence (when present) reads acceptably for the band.

### Do NOT enable auto-merge

- [ ] I understand this PR is **human-merge-only**. Auto-merge must not be enabled
      on a `skeleton-promotion` PR (ADR-020 decision 4); the CI `no-auto-merge` job
      fails the PR if it is.

---
<!-- @coderabbitai review -->
