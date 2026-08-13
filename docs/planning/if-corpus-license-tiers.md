---
title: "Legally-Tiered Interactive Fiction Corpus: Verification and Scope"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Evaluates a second round of externally-authored AI feedback proposing a license-tiered
  corpus of public-domain and copyrighted interactive fiction, verifies its specific legal and
  review-evidence claims against primary sources where this session's network access allowed, and
  re-scopes the proposal's 'training corpus' framing against this project's actual architecture."
tags:
  - planning
  - measurement
  - legal
  - authoring
---

# Legally-Tiered Interactive Fiction Corpus: Verification and Scope

## Origin

A second round of externally-authored AI feedback (pasted into a session on 2026-08-13, following
on from [craft-review-benchmark-corpus.md](./craft-review-benchmark-corpus.md) and its `UW-N11`
register row) proposes a three-tier interactive-fiction corpus split by copyright status: works
safe to use as full-text training material after license confirmation (Tier A/B in the source
feedback), and copyrighted-but-well-reviewed works usable only as human-readable reference,
labeled and never copied (Tier C). It names eight public-domain candidates and two
permission-required ones (*Lost Pig*, *All Things Devours*), and recommends an initial set of
five: *Consider the Consequences!*, *The Interlopers*, *The Tailgator*, *The Cavern of the
Morlocks*, and *Lost Pig*.

## Correction: this project has no fine-tuning pipeline

The proposal's framing repeatedly refers to "internal training," a "training corpus," and
"model-training implications." That framing does not have a consumer in this codebase.
[ADR-003](./adr/adr-003-frontier-llm-generation.md) commits this project to a frontier LLM
(Anthropic Claude primary, OpenRouter/Ollama fallback) behind a provider-agnostic interface, called
at generation time; `src/cyo_adventure/generation/providers/` has exactly the four provider
adapters (`anthropic.py`, `openrouter.py`, `ollama.py`, `modal.py`) plus `fallback.py`, and no
fine-tuning, LoRA, or local-training code exists anywhere in the tree. There is no local model
this project trains, so "safe to fine-tune on" is not a real distinction to make here, and the
proposal's copyright caution about "a model-training use could be legally characterized as
reproduction, adaptation, or both" does not describe any use this project would actually make of
these works.

That does not make the underlying license work wasted; it means the three tiers need different,
real consumers than the ones the proposal named:

| Proposal's tier | Proposal's use case | This project's actual matching consumer |
|---|---|---|
| Tier A (public domain, structural) | Internal training on graph extraction, path enumeration, choice-to-outcome mapping | **Real structural test fixtures.** [cyoa-book-benchmark-comparison.md](./cyoa-book-benchmark-comparison.md) already benchmarks the validator/condition-evaluator against published mechanics, but deliberately uses hand-built analogues, not real text, "to reproduce... only its publicly-documented branching mechanics." A verified-PD full text is the first chance to run the actual `validator/`/`diversity/` graph-analysis code against real branching prose instead of an analogue. |
| Tier B (public domain, prose/age calibration) | Internal training on sentence complexity, vocabulary, read-aloud suitability | **Calibration reference for `validator/reading_level.py` and `validator/band_profile.py`.** Validating that the FK-grade proxy tracks what a real published, age-banded PD children's book actually reads like, the same role `craft-review-benchmark-corpus.md` already proposed for professional reviews, from a different angle. |
| Tier C (copyrighted, reference-only) | Human reference; derived labels only, never copied | **Already built.** This is exactly [craft-review-benchmark-corpus.md](./craft-review-benchmark-corpus.md)'s existing schema and posture (title/ISBN/source/URL plus a short derived label, never full text), just extended to general interactive fiction rather than only published children's books. |

Tier A and Tier C are the two worth acting on. Tier B (open children's-literature prose for
reading-level calibration) is real but untouched this session; it needs its own title list and is
out of scope for this pass.

## Verification results: the proposal's "recommended initial set" of five

The proposal itself flagged that IFDB's license field is "community metadata rather than a legal
opinion" and that some entries should be added "if their rights metadata survives a manual
verification." This session ran that verification via `WebSearch` and attempted `WebFetch` against
primary sources for all five. Full entries with sources and caveats are in
[`data/if-corpus-licensing.yaml`](./data/if-corpus-licensing.yaml); this table summarizes what
changed versus the pasted claims.

| Work | Claimed | Verified finding | Status |
|---|---|---|---|
| *Consider the Consequences!* | PD in the US, historical press + modern discussion | PD claim plausible (non-renewal basis, matches Wikisource's standard pre-1964 template practice), but only at medium confidence: `WebFetch` was blocked for wikisource.org, wikidata.org, and archive.org, so the exact PD rationale was never read first-hand. Modern discussion is real and well-corroborated (LOC blog, MetaFilter, an IF community forum thread, a 2024/25 commercial reprint); the "historical press coverage" claim has exactly one unverified lead, not a confirmed body of coverage | `green`, medium confidence |
| *The Interlopers* (adaptation) | PD source + PD adaptation | Saki's original story is solidly PD (high confidence, cross-corroborated, life+70 expired since 1987, US 95-year rule also satisfied). The adaptation itself (a 2014 Quest 5 game) states on IFDB that it "contains the complete Feedbooks public-domain text" and offers both play and full source download, but no independent author-signed PD statement was found and the adaptation's own author could not be identified | `green`, medium confidence |
| *The Tailgator* | PD, "5 ratings and 1 written review" on IFDB | **Could not be found at all.** Extensive search under the exact title, spelling variants, and title-plus-IFDB-terms surfaced only unrelated products (a monster truck, a taillight brand, a generator, a golf game). This claim should be treated as unconfirmed, possibly a misremembered or fabricated title, not merely "unverified" | `reference_only` pending re-identification; **do not add to any corpus under this title** |
| *The Cavern of the Morlocks* | PD, "3 ratings and 1 detailed review" | Real work found (François Coulon, 1985 French magazine type-in, `L'Ordinateur Individuel` issue 77), IFDB does list "Public Domain," but that is community metadata with no located author PD statement, and the actual count is **2 ratings, 1 review**, not 3, a minor but real correction | `yellow`, medium confidence |
| *Lost Pig* | CC BY-NC-ND 3.0, 500+ ratings, multiple awards | **Confirmed, not an overstatement.** License, rating count (~523-526), and awards (4 XYZZY wins: Best Game, Best Writing, Best Individual NPC, Best Individual PC; 4 more finalist nods; 1st place IFComp 2007) all check out. NonCommercial and NoDerivs both block reuse outright without the rights holder's written permission | `red`; the proposal's own "contact the author for permission" recommendation is the only path, and that is a human, outward-facing action this session did not take |

**One correction and one omission worth flagging plainly:** *The Tailgator* appears not to exist
under that title, which is a real finding, not a formatting nitpick, since acting on an
unverifiable title risks citing a wrong or nonexistent work in a legal-status table. *All Things
Devours* (the proposal's other permission-required title) was not checked this session; treat it
as fully unverified.

**Methodology caveat that held across every one of these four verification runs, plus this
session's own direct `WebFetch` attempt against `en.wikisource.org`:** the network egress proxy
blocked every relevant domain (wikisource.org, wikidata.org, archive.org, ifdb.org, grunk.org,
textadventures.co.uk, and others). Every finding above is `WebSearch`-snippet-derived, not a
first-hand page read; `data/if-corpus-licensing.yaml`'s `checked_method_caveat` field states this
explicitly so it cannot be silently dropped in a later edit. **No entry here should be treated as
legal sign-off.** Before any work's actual text enters this repository, re-verify with a session
or a human that has unrestricted access to the primary source, and route anything that will
actually ship (not just an internal test fixture) through the same counsel-engagement pattern this
project already uses for other rights questions (see
[counsel-engagement-brief.md](../compliance/counsel-engagement-brief.md)).

## What this doc is not proposing

- **No text has been downloaded or committed to this repository this session.** Verifying a
  license is not the same decision as ingesting a work's full text; that is a separate, larger
  step this doc deliberately stops short of, especially given every finding above is
  search-snippet-derived rather than primary-source-verified.
- **No contact with the *Lost Pig* author.** The proposal's "most valuable single action" is
  exactly that outreach, but it is a human, outward-facing action on the user's behalf, not
  something to take without being asked.
- **No change to the licensing register's `status` fields based on anything short of a
  primary-source re-verification.** `green` here means "strong lead," not "cleared."

## Recommendation

Two pieces of real, checkable work came out of this pass: the verification table above (which
corrects two of the proposal's specific claims, one materially: *The Tailgator* likely does not
exist under that title) and the licensing-register schema in
[`data/if-corpus-licensing.yaml`](./data/if-corpus-licensing.yaml), which is reusable for every
future candidate regardless of which titles end up in scope. What remains genuinely owner-gated:

1. **Whether to pursue Tier A at all** (real PD branching text as structural test fixtures for
   `validator/`/`diversity/`), given `cyoa-book-benchmark-comparison.md` already covers the same
   ground with hand-built analogues and has no open gap calling for real text specifically.
2. **Whether to contact the *Lost Pig* rights holder** for written permission, given it is by far
   the strongest quality/review signal of anything checked across both this doc and
   `craft-review-benchmark-corpus.md`.
3. **Tier B** (open children's-literature prose for reading-level calibration) has no title list
   yet and was not scoped this session.

See `UW-N12` in [unscheduled-work-register.md](./unscheduled-work-register.md) for the
phase-linkage entry this doc's own conventions require.
