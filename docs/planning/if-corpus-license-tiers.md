---
title: "Legally-Tiered Interactive Fiction Corpus: Verification and Scope"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Evaluates a second round of externally-authored AI feedback proposing a license-tiered
  corpus of public-domain and copyrighted interactive fiction, verifies its specific legal and
  review-evidence claims against primary sources, and re-scopes the proposal's 'training corpus'
  framing against this project's actual architecture. Re-verified 2026-08-30 against live primary
  sources and against current main."
tags:
  - planning
  - measurement
  - legal
  - authoring
---

# Legally-Tiered Interactive Fiction Corpus: Verification and Scope

## Origin

A second round of externally-authored AI feedback (pasted into a session on 2026-08-13, following
on from [craft-review-benchmark-corpus.md](./craft-review-benchmark-corpus.md) and its proposed
`UW-N11` register row) proposes a three-tier interactive-fiction corpus split by copyright status: works
safe to use as full-text training material after license confirmation (Tier A/B in the source
feedback), and copyrighted-but-well-reviewed works usable only as human-readable reference,
labeled and never copied (Tier C). It names eight public-domain candidates and two
permission-required ones (*Lost Pig*, *All Things Devours*), and recommends an initial set of
five: *Consider the Consequences!*, *The Interlopers*, *The Tailgator*, *The Cavern of the
Morlocks*, and *Lost Pig*.

## Correction: this project has no fine-tuning pipeline

The proposal's framing repeatedly refers to "internal training," a "training corpus," and
"model-training implications." That framing does not have a consumer in this codebase.
[ADR-003](./adr/adr-003-frontier-llm-generation.md) commits this project to a frontier LLM behind
a provider-agnostic interface, called at generation time. Its 2026-06-22 amendment made OpenRouter
the primary provider (Claude is reached through it), and its 2026-08-18 amendment retired the local
Ollama leg entirely, leaving the cascade as OpenRouter primary, then the OpenRouter fallback model,
then Modal. `src/cyo_adventure/generation/providers/` accordingly holds three provider adapters
(`anthropic.py`, `openrouter.py`, `modal.py`) plus `_base.py` and `fallback.py`, and no
fine-tuning, LoRA, or local-training code exists anywhere in the tree.

> **Corrected 2026-08-30.** This paragraph previously named `ollama.py` as a fourth adapter and
> restated ADR-003 as "Anthropic Claude primary, OpenRouter/Ollama fallback". Both were true at
> this document's 2026-08-13 merge base and false by the time it landed: `167c29da` (#729) removed
> the `OllamaProvider` adapter, the `OLLAMA_*` configuration surface, and the `ollama` enum and
> allowlist rows. The retirement strengthens rather than weakens this section's argument, since it
> removes the last locally-hosted model from the tree, but a doc arguing "there is no local model
> here" while naming a local adapter invites exactly the objection it is answering. There is no local model
this project trains, so "safe to fine-tune on" is not a real distinction to make here, and the
proposal's copyright caution about "a model-training use could be legally characterized as
reproduction, adaptation, or both" does not describe any use this project would actually make of
these works.

That does not make the underlying license work wasted; it means the three tiers need different,
real consumers than the ones the proposal named:

| Proposal's tier | Proposal's use case | This project's actual matching consumer |
| --- | --- | --- |
| Tier A (public domain, structural) | Internal training on graph extraction, path enumeration, choice-to-outcome mapping | **Real structural test fixtures.** [cyoa-book-benchmark-comparison.md](./cyoa-book-benchmark-comparison.md) already benchmarks the validator/condition-evaluator against published mechanics, but deliberately uses hand-built analogues, not real text, "to reproduce... only its publicly-documented branching mechanics." A verified-PD full text is the first chance to run the actual `validator/`/`diversity/` graph-analysis code against real branching prose instead of an analogue. |
| Tier B (public domain, prose/age calibration) | Internal training on sentence complexity, vocabulary, read-aloud suitability | **Calibration reference for `validator/reading_level.py` and `validator/band_profile.py`.** Validating that the FK-grade proxy tracks what a real published, age-banded PD children's book actually reads like, the same role `craft-review-benchmark-corpus.md` already proposed for professional reviews, from a different angle. |
| Tier C (copyrighted, reference-only) | Human reference; derived labels only, never copied | **Already built.** This is exactly [craft-review-benchmark-corpus.md](./craft-review-benchmark-corpus.md)'s existing schema and posture (title/ISBN/source/URL, short attributed quotation, and derived labels, never full text), just extended to general interactive fiction rather than only published children's books. That doc's consumer is now the LLM quality panel in [cyo-measurement-workplan-2026-08-12.md](./cyo-measurement-workplan-2026-08-12.md), so a Tier C extension inherits that consumer too. |

Tier A and Tier C are the two worth acting on. Tier B (open children's-literature prose for
reading-level calibration) is real but untouched this session; it needs its own title list and is
out of scope for this pass.

## Verification results: the proposal's "recommended initial set" of five

The proposal itself flagged that IFDB's license field is "community metadata rather than a legal
opinion" and that some entries should be added "if their rights metadata survives a manual
verification." That verification ran in two passes: 2026-08-13 via `WebSearch` alone, with
`WebFetch` blocked by network egress policy, and **2026-08-30 from a session with working egress,
which performed a direct page read for all five entries**. Full entries with sources and caveats are
in [`data/if-corpus-licensing.yaml`](./data/if-corpus-licensing.yaml); the table below states the
current position, flagging where it differs from the 2026-08-13 one.

| Work | Claimed | Verified finding (2026-08-30 unless noted) | Status |
| --- | --- | --- | --- |
| *Consider the Consequences!* | PD in the US, historical press + modern discussion | **Confirmed by direct read, and on a better basis than first recorded.** Wikisource's licence banner reads "This work is in the public domain in the United States because it was published before January 1, 1931", which is **term expiry, not copyright non-renewal**. Term expiry needs no renewal-record search to hold, so the finding is stronger than the 2026-08-13 pass claimed. Author, publisher (The Century Co.), 1930 date, and the branching structure all confirmed on the same page. Modern discussion is real and well-corroborated (LOC blog, MetaFilter, an IF community forum thread, a 2024/25 commercial reprint); the "historical press coverage" claim still has exactly one unverified lead | `green`, **high** confidence (was medium); `commercial_use_claimed` and `derivatives_claimed` both moved to `null`, because the banner states a PD finding and does not address either permission specifically. The term-expiry basis is unchanged |
| *The Interlopers* (adaptation) | PD source + PD adaptation | Saki's original story is solidly PD. The adaptation is a **separate rights object and was never cleared**: IFDB credits it to "Saki and IF Classics", a project label rather than an identifiable rights holder, its License field is community metadata reading "Public Domain", and no author-signed dedication exists. The page now also states "There are no known download links for this game", so the 2026-08-13 entry's download URL is withdrawn (it returns HTTP 403) | **`yellow`, downgraded from `green`**; `covers` narrowed to `[text]`, and the `commercial_use_claimed` / `derivatives_claimed` booleans withdrawn to null |
| *The Tailgator* | PD, "5 ratings and 1 written review" on IFDB | The 2026-08-13 pass found nothing under this title. Re-searching refines that: a real Twine IF game titled *The Tailgator* exists on itch.io (creator NegativeSector), but a direct read shows **no licence statement and no ratings or reviews**, so it is not the work the proposal described and supplies no rights basis. The proposal's claim remains unconfirmed | `reference_only`; **do not add to any corpus under this title** |
| *The Cavern of the Morlocks* | PD, "3 ratings and 1 detailed review" | Real work confirmed by direct read (François Coulon, 1985, Matra-Hachette Alice, French). IFDB's License field does read "Public Domain" but **there is no author statement anywhere on the page**, only the field, and the count is **2 ratings, 1 review**, not 3. Decisively: French `droit moral` is perpetual, inalienable, and unwaivable, so a living French author has **no clean public-domain-dedication route available** in the first place. Waiting for an author statement would not resolve this, because the bar is structural rather than evidentiary | **`reference_only`, downgraded from `yellow`** |
| *Lost Pig* | CC BY-NC-ND 3.0, 500+ ratings, multiple awards | **Confirmed verbatim from the rights holder's own site**, the only entry here resting on the author's own words: "Lost Pig by Admiral Jota and Grunk is licensed under a Creative Commons Attribution-NonCommercial-NoDerivs 3.0 Unported License". Awards confirmed on the same page (1st of 27 in IFComp 2007; 4 XYZZY wins of 8 nominations). Note the licence names **two** parties, so a permission request must reach both | `red`, **high** confidence (was medium); permission request remains the only path, and that is a human, outward-facing action |

**Two downgrades, one correction, one omission, and one field-level fix.** The two downgrades are
the load-bearing changes: *The Interlopers* and *The Cavern of the Morlocks* both moved to a
stricter status because in each
case the machine-readable fields were asserting more than the prose beside them could support. The
correction is *The Tailgator*, where the proposal's described work still cannot be located and a
same-titled itch.io game is not it; acting on an unverifiable title risks citing a wrong or
nonexistent work in a legal-status table. The omission is *All Things Devours* (the proposal's
other permission-required title), which has still not been checked; treat it as fully unverified. The
field-level fix is *Consider the Consequences!*, whose finding did not change at all: only the two
permission fields beside it did, for the reason set out immediately below.

**A note on how the downgrades happened, because the pattern will recur.** Neither downgrade rested
on new facts. Both facts were already in the 2026-08-13 entries' own `verification_notes`: no
author-signed dedication for the Quest adaptation, community metadata only for the Morlocks entry.
What changed is that those hedges now reach the fields a script reads. A `status: green` beside
`commercial_use_permitted: true` outlives the paragraph explaining why neither is settled, and the
paragraph is the part a machine consumer never sees. When a caveat and a field disagree, move the
field.

**The rule had one entry left to apply to, and applying it took three changes.** *Consider the
Consequences!* was the one entry still carrying `true` in both permission fields, so it was also the
one entry a script filtering on them would have added to an ingestion allowlist, off the strongest
`status` value in the file, in a public repository. Three changes close that:

1. **The permission fields are renamed.** `commercial_use_permitted` is now
   `commercial_use_claimed`, and `derivatives_permitted` is now `derivatives_claimed`. No field name
   in the register asserts a permission the register is not granting; every one of them now names
   what it actually holds, which is a relayed claim.
2. **Both of that entry's claim fields are `null`.** Wikisource's banner states a public-domain
   finding for the United States. It does not speak to commercial use or to derivative works
   specifically, so `null` ("no located source addresses this permission") is the accurate value and
   `true` was an inference. **The term-expiry basis is untouched and undiminished**: it lives in
   `license_claimed` and in the entry's `verification_notes`, which is where a rights basis belongs.
   Nulling a claim field is not a downgrade of the finding; `status` stays `green` and confidence
   stays `high`.
3. **The definitions became data.** See the following section: the header comment block that
   previously carried them is not something a parser can read.

**Methodology, and what changed between the two passes.** The 2026-08-13 pass ran behind a network
egress proxy that blocked every relevant domain (wikisource.org, wikidata.org, archive.org,
ifdb.org, grunk.org, textadventures.co.uk, and others), so every finding it produced was
`WebSearch`-snippet-derived rather than a first-hand page read, and it said so. The 2026-08-30 pass
had unrestricted egress and read a page directly for **all five** entries, so all five now carry
`verification_method: primary_source_fetch`.

That count needs its meaning stated, because `5 of 5` reads like a clean sweep and is not one. **A
fetch records that a page was read, never that the page supported the entry.** *The Tailgator*'s
pass-2 fetch confirmed a **non-match**: the page that was read turned out to describe a different
work from the one the external proposal named, which is why that entry pairs
`verification_method: primary_source_fetch` with `verification_confidence: unable_to_verify`.
Reading the method field alone would make that entry look checked. `data/if-corpus-licensing.yaml`'s
`checked_method_caveat` now says exactly this, so a later edit can neither quietly launder a pass-1
entry into a pass-2 one nor read a fetch as a confirmation.

The re-verification changed two statuses and one rationale, which is the argument for not treating
a snippet-derived legal claim as settled: a search snippet reproduced the *outcome* for *Consider
the Consequences!* while getting its *basis* wrong, and it carried IFDB's License field for two
entries without carrying the absence of any author statement behind it.

**No entry here is legal sign-off, and no `status` value in the companion YAML means "cleared".**
Until 2026-08-30 that statement lived in the YAML's `#` comment header, which made it true of a
*human* or an agent reading the raw text and false of the reader it was written for: a parser
discards every comment line, so `yaml.safe_load()` returned five records and no caveat at all. The
definitions are now top-level YAML data. A script that loads the file sees
`is_legal_clearance: false`, a `clearance_note` saying in as many words that filtering `works` on
`status` plus the claim fields to build an ingestion allowlist is a misuse of the file, a
`status_definitions` mapping with an entry for every status value the file uses (each written to say
what that status is *not*), and a matching `verification_method_definitions` mapping. Before any work's
actual text enters this repository, re-verify again against the primary source, and route anything
that will actually ship (not just an internal test fixture) through the same counsel-engagement
pattern this project already uses for other rights questions (see
[counsel-engagement-brief.md](../compliance/counsel-engagement-brief.md)).

## What this doc is not proposing

- **No text has been downloaded or committed to this repository this session.** Verifying a
  license is not the same decision as ingesting a work's full text; that is a separate, larger
  step this doc deliberately stops short of. (This bullet previously justified itself with "every
  finding above is search-snippet-derived rather than primary-source-verified", which the
  2026-08-30 pass made false. The bullet does not need that premise: a primary-source read is
  still not legal sign-off, so the gap between verifying a licence and ingesting a text is exactly
  as wide as it was.)
- **No contact with the *Lost Pig* author.** The proposal's "most valuable single action" is
  exactly that outreach, but it is a human, outward-facing action on the user's behalf, not
  something to take without being asked.
- **No change to the licensing register's `status` fields based on anything short of a
  primary-source re-verification.** `green` here means "strong lead," not "cleared." As of
  2026-08-30 that definition is **parsed data** in
  [`data/if-corpus-licensing.yaml`](./data/if-corpus-licensing.yaml) (`is_legal_clearance`,
  `clearance_note`, `status_definitions`), not a comment header and not prose living only here. The
  two files previously disagreed outright: the YAML defined `green` as "public domain in the
  intended jurisdiction, source and rights documented", which reads as a clearance. Moving that
  definition into the comment header fixed the disagreement for a human reader and left it
  untouched for the machine one, since the YAML is the file a script opens alone and comments are
  the first thing a parser throws away.

## Recommendation

Two pieces of real, checkable work came out of this pass: the verification table above (which
corrects three of the proposal's specific claims, one materially: *The Tailgator* likely does not
exist under that title as described) and the licensing-register schema in
[`data/if-corpus-licensing.yaml`](./data/if-corpus-licensing.yaml), which is reusable for every
future candidate regardless of which titles end up in scope. The 2026-08-30 re-verification pass
adds a third: the register now demonstrates that its own statuses move under scrutiny, in both
directions (one entry strengthened, two downgraded), which is the property a rights register needs
and the one a single-pass table cannot show.

Where this sits relative to work that landed after this doc's 2026-08-13 merge base:
[cyo-measurement-workplan-2026-08-12.md](./cyo-measurement-workplan-2026-08-12.md) now governs how
this project measures story quality, and its W7 known-bad battery is where a Tier A structural
fixture would actually be consumed, if Tier A is ever pursued. Nothing in that workplan calls for
real third-party text, so the owner gate below is unchanged; the consumer is simply now named.

What remains genuinely owner-gated:

1. **Whether to pursue Tier A at all** (real PD branching text as structural test fixtures for
   `validator/`/`diversity/`), given `cyoa-book-benchmark-comparison.md` already covers the same
   ground with hand-built analogues and has no open gap calling for real text specifically.
2. **Whether to contact the *Lost Pig* rights holder** for written permission, given it is by far
   the strongest quality/review signal of anything checked across both this doc and
   `craft-review-benchmark-corpus.md`.
3. **Tier B** (open children's-literature prose for reading-level calibration) has no title list
   yet and was not scoped this session.

**Register linkage.** `UW-N12` is the id proposed for this doc's row in
[unscheduled-work-register.md](./unscheduled-work-register.md); main's `UW-N` cluster stops at
`UW-N10`, so it is free. As with `UW-N11` in the companion document, the row is not added here:
register ids collide when concurrent branches allocate from the same cluster, and the fix is a
renumber plus merge rather than a text merge, so rows are batched into a single consolidation
change. Treat `UW-N12` as proposed rather than assigned until that lands.
