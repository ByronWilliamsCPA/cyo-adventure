---
title: "Reviewer SOP"
schema_type: common
status: published
owner: core-maintainer
purpose: >-
  Decision procedure for the human reviewer at the mandatory approval gate.
  This covers the moderation review workflow, verdict interpretation, and
  escalation paths for books that fail automated checks or require judgment calls.
tags:
  - guide
  - deployment
---

## Purpose

The decision procedure for the human reviewer at the mandatory approval gate
(ADR-005). Automated moderation only hard-stops on BLOCK at generation time;
everything else accumulates for you. You are the last gate before a child
reads this book.

## Before you start

- The queue badge counts DISTINCT findings by tier ("1 block · 3 flags ·
  47 advisories"). The passage wall shows one card per finding-passage pair,
  so a single finding spanning many nodes produces many cards; that is
  deliberate (never hide flagged prose), not many independent problems.
- Content flags (Violence/Scariness/Peril) are AUTHOR-DECLARED at intake and
  validated only against the age-band ceiling. They are not derived from the
  moderation review; do not treat them as a summary of it.

## Decision table

| You see | It means | Do this |
| --- | --- | --- |
| "Moderation unavailable · re-run required" | The pipeline failed (mock reviewer or fail-safe artifacts); there is NO content judgment | Do not review the wall. Re-run moderation (ops script `scripts/remoderate_books.py --book-id <id> --execute`, or `POST /admin/remoderate/{storybook_id}/{version}`), then review the fresh report. Approval is blocked until then |
| A structural finding (badge "pipeline") | A pipeline condition, not a content judgment | Same as above: re-run before reviewing |
| BLOCK verdict | The automated reviewer judged a passage unsafe for the band | Read the passage in full. Default action: edit the node or send back. Approving over a block is exceptional, admin-only, and requires a written override reason that is logged for audit; the audit event records the override counts |
| FLAG, severity high | Serious concern (e.g. self-harm, real-world danger) | Read the passage in full. Approving requires a written override reason. Prefer node-edit + rescreen, or send back |
| FLAG, severity medium/low | Age-band judgment call | Read the passage; approve, edit, or send back on your judgment. No override reason needed |
| ADVISORY | Classifier signal below the concern line; never gates | Skim the collapsed section if the counts look unusual for the genre; otherwise no action |
| Repaired: yes | The bounded repair loop rewrote flagged prose | Spot-check the repaired nodes; repair never bypasses this gate |

## Send back vs edit

Edit-and-rescreen when the problem is one passage and the fix is obvious.
Send back when the problem is thematic (many nodes), the story does not match
the request, or you would be rewriting the book in the editor.

## Escalation

A published book with a block or high-severity finding is an incident:
re-moderate it immediately and raise it with the owner before taking any
publish-state action.
