# C4. Safety, moderation, and human approval: component audit

Audit date 2026-08-22. Scope: `moderation/`, `validator/` safety rules, `publishing/`,
`api/{approval,review_surface,node_edit,rescreen,remoderate,moderation_dashboard,moderation_thresholds}.py`,
`frontend/src/admin/`, ADR-005, ADR-010, `docs/planning/safety/`.
Brief under audit: `docs/planning/cyo-generation-research-brief-2026-08-22.md` sections 3.5, F8, `S-5`.

## Measured facts this audit rests on

Computed from the committed catalog (`skeletons/`, 84 shells, 81 production-eligible, 15,400 nodes):

| Shell | Band | Nodes | Edges | Commissioned words | Endings | Distinct root-to-ending paths |
|---|---|---|---|---|---|---|
| `the-big-cardboard-box` | 3-5 | 44 | - | 1,904 | 18 | 18 |
| `the-tin-whistle-map` | 8-11 | 193 | 466 | 19,574 | 35 | 3,324,033 |
| `the-cartographers-apprentice` | 10-13 | 254 | - | 22,258 | 43 | 85,753,081 |
| `the-tenfold-siege` | 16+ | 677 | 767 | 42,233 | 209 | >10^9 (enumeration capped) |

Reading time for the brief's worked example (677 nodes): 42,233 commissioned words is
**~3.0 h** at 238 wpm adult silent reading, **~1.8 h** at a 400 wpm skim. Taking the brief's
own 118,000-word figure instead: **~8.3 h** / **~4.9 h**. ADR-005's stated budget is
"a few minutes" ("the Phase 3 review UI makes it a few minutes"). The gap is **35x to 100x**.

Reproduce: `python3 -c` over `skeletons/**/*.json` summing `words=(\d+)` in `<<FILL>>` bodies and
DFS-counting root-to-ending paths with a cycle guard.

---

## C4-1: Safety is evaluated per node and nothing evaluates a path; the path machinery exists and is unused

- **Severity**: critical
- **Category**: path-level escape
- **Locus**: `src/cyo_adventure/moderation/stages.py:110` (batch prompt: "Judge each passage
  independently of the others"), `stages.py:566` (`run_safety_stage`),
  `src/cyo_adventure/moderation/pipeline.py:942-1006` (`_run_all_stages`),
  `src/cyo_adventure/validator/paths.py:395` (`covering_paths`, no production caller)
- **Problem**: Stage 1, the only LLM hard safety gate, takes `(node_id, prose)` pairs, chunks them
  in **node-list iteration order** (not choice order), and instructs the reviewer to judge each
  passage independently against the declared band. Stage 3 (coherence) receives the whole book but
  asks only about plot/character/world-state *inconsistency*, is soft, and fails open to PASS.
  Stage 4 is advisory. Stage 0 classifies one node body at a time. **No stage in the publish path
  ever assembles a reader's path.** The repository already owns the missing instrument:
  `validator/paths.py` builds `covering_paths` (every reachable choice read at least once) and
  `reader_sample_paths` (uniform-over-choices sampling, the reader model), driven through the real
  `StoryEngine` so conditions and `once` effects behave as for a child. Its only caller is the
  offline `scripts/measure_per_path.py`, which measures **reading level and prose craft**, never
  safety. `UW-E12` records the gap ("no whole-story or per-path safety pass exists", priority 5,
  unscheduled); the 2026-07-01 adversarial evaluation records it as Class C, Finding 4.
- **The escape, concretely**: a 10-13 gamebook on `the-cartographers-apprentice`. Node `n_meet`:
  a friendly adult stranger at the harbour offers to show the protagonist a shortcut, warm,
  ordinary, verdict `safe`. Node `n_secret`: the stranger asks the protagonist not to mention the
  shortcut to their aunt, "so she won't worry", a plausible beat in a hundred children's books,
  verdict `safe`. Node `n_gift`: the stranger gives them a compass and says it's *their* secret,
  verdict `safe`. Node `n_alone`: they follow the stranger down a lane away from the market,
  verdict `safe`. Node `e_trust_rewarded`: the shortcut works, the protagonist wins the day, and
  the book's payoff is that keeping the secret from the aunt was the right call:
  `ending.kind = "triumph"`, so PL-15 (forbidden ending kinds) is silent, PL-24 (ending mix) is
  silent, and per-node Stage 1 is silent on every one. The assembled path is a textbook
  grooming-shaped escalation, isolate, secrecy, gift, separate from the caregiver, reward the
  secrecy, and the pipeline has no unit of analysis that can see it. The same construction works
  for step-by-step real-world hazard instructions (one step per node), for cumulative peril
  intensity that no single node carries, and for a cruelty arc whose individual beats are each
  defensible.
- **Batching does not help and the brief should not treat it as coverage.** `review_batch_size`
  defaults to 8, so up to 8 nodes share a prompt, but the prompt *demands* independent verdicts,
  chunks are cut in list order rather than along choice paths, and any path crossing a chunk
  boundary is unaccumulated. That converts a stable, known miss into a configuration-dependent
  incidental catch, which is worse.
- **Why it matters for the goal**: this is the single largest safety hole in the system, it is
  structural rather than probabilistic, and it is exactly the harm class that a branching book
  makes possible and a linear book does not. The product's differentiator is the branching; the
  safety architecture is inherited from linear-text moderation.
- **Recommendation**: (1) Add a Stage 1b path-safety pass over `covering_paths(story)`, bounded by
  edge count, so ~767 edges for the largest shell in the catalog and far fewer paths after greedy
  covering; at ~50-100 path prompts this costs less than the 85 node-batch calls the same book
  already makes. Prompt it with the path's node bodies **in reading order** and ask the escalation
  question explicitly (isolation, secrecy, escalating danger, reward-for-unsafe-choice), not the
  per-node question again. (2) Make the endings the priority unit: 209 endings on the largest shell
  means 209 "what does this book reward" judgements, which is tractable today. (3) Feed `PathSet`'s
  `complete=False` flag through as a structural FLAG so a truncated enumeration is visible.
  (4) Present paths, not nodes, to the human (see C4-3).
- **How to check I'm right**: `grep -rn "covering_paths\|reader_sample_paths" --include=*.py src/`
  returns only `validator/paths.py` itself and `scripts/measure_per_path.py`. Read
  `stages.py:106-118` for the independence instruction and `stages.py:640-650` for the
  list-order chunking (`_chunks(nodes, batch_size)`). Confirm no aggregation exists:
  `grep -rn "path" src/cyo_adventure/moderation/` returns nothing path-aware.

---

## C4-2: A bright-line BLOCK is reversible by one admin in two clicks, with no re-screen and no distinct audit record

- **Severity**: critical
- **Category**: review ergonomics
- **Locus**: `src/cyo_adventure/publishing/service.py:412` (`if version_row.moderation_report is
  None`), `src/cyo_adventure/publishing/service.py:104-152` (`submit`, same None-only check),
  `src/cyo_adventure/api/approval.py:145-176` (`approve_storybook`),
  `src/cyo_adventure/api/node_edit.py:666-676`
- **Problem**: a Stage-0 bright-line hit (`sexual/minors`, `self-harm/instructions`,
  `illicit/violent`, `hate/threatening`, `harassment/threatening`, Perspective
  `SEXUALLY_EXPLICIT >= 0.8`) or a Stage-1 `block` routes the story `draft -> needs_revision` via
  `auto_reject`. From `needs_revision`, `POST /storybooks/{id}/submit` moves it back to
  `in_review`, the only guard is `moderation_report is None`, and the blocked report is not None.
  `POST /storybooks/{id}/approve` then publishes it, again the only content guard is
  `moderation_report is None`. **Neither `submit` nor `approve` ever reads `summary.hard_block`.**
  No re-moderation runs on the resubmit path. `api/node_edit.py:666` compounds it: a guardian or
  admin may edit any node of an `in_review`/`needs_revision` book, and a **fresh hard BLOCK on the
  edited text does not reject the write**, it is persisted and surfaced. The `RELEASED` event's
  payload allowlist is `{"visibility"}` (`events/writer.py:44`), so the audit log cannot
  distinguish "published clean" from "published over a bright-line block".
- **The escape, concretely**: a guardian who also holds `is_admin` (the dual-role adult the
  codebase explicitly supports, `api/deps.py:128-142`) requests a book, gets it auto-rejected on a
  Stage-0 bright line, edits the offending node (or does not), clicks Submit, clicks Approve,
  clicks Confirm. Total: three clicks, no second person, no re-screen, no re-run of the classifier
  that blocked it, and `Principal.acting_role` stamps the event **`guardian`** because the target
  family is their own, so the audit trail records a routine guardian publish.
- **Why it matters for the goal**: ADR-005's entire claim is that the human is an *additional*
  layer on top of automation. Here the human is a *subtractive* layer with unlimited authority over
  the automation's hardest verdict, exercised by the person with the least independence from the
  request. The bright-line categories are precisely the ones that must not be single-click
  overridable.
- **Recommendation**: (1) Make `approve` refuse a version whose stored report carries
  `summary.hard_block == true` unless the version has been **re-moderated since** (compare a
  `moderated_at` stamp against `version_row.updated_at`), and record a distinct
  `BLOCK_OVERRIDDEN` event type carrying the overridden concern slugs (closed vocabulary, PII-safe).
  (2) Force re-moderation on `needs_revision -> in_review`, not merely permit it. (3) Forbid
  self-approval of a bright-line override: require a `principal.acting_role(family) == ADMIN`
  (cross-family) approver for that one case, which is a two-line rule and the only four-eyes
  requirement the product needs. (4) Make `node_edit` on a node that produces a fresh BLOCK flip
  the story back to `needs_revision` rather than leaving it approvable in place.
- **How to check I'm right**: read `publishing/service.py:104-152` and `:400-420`, the string
  `has_hard_block` does not appear in `publishing/`. `grep -rn "has_hard_block" src/` returns only
  `moderation/report.py`, `moderation/pipeline.py`, `api/node_edit.py`, `api/remoderate.py`.
  Integration test to write: seed a version whose `moderation_report.summary.hard_block` is true,
  in status `needs_revision`, then POST submit + approve as an admin, both currently return 200.

---

## C4-3: The review surface is a 677-passage scroll in depth-first order, and Approve requires no evidence that anything was read

- **Severity**: critical
- **Category**: review ergonomics
- **Locus**: `frontend/src/admin/ReviewDetailPage.tsx:601-637` (whole-book render),
  `frontend/src/guardian/storyReadThrough.ts:175-208` (`buildReadThrough`, DFS pre-order),
  `frontend/src/admin/ReviewDetailPage.tsx:719,804` (Approve button, Confirm dialog),
  `src/cyo_adventure/api/approval.py:145` (`approve_storybook` takes only `storybook_id` and an
  optional visibility)
- **Problem**: what the approver is given is: a summary strip (finding count, hard-block /
  soft-flag / repaired / independent badges), a collapsible structure overview, a "Flagged
  passages" block, three ranked finding buckets, RL-13/PL-19 validator notes, and then **every
  node in the book rendered as a card in one page**, ordered by a depth-first traversal from
  `start_node`, with unreachable nodes appended. There is **no sampling**, nothing is elided,
  and therefore also no risk weighting, no pagination, no progress tracking, and no path view.
  DFS pre-order is not a reading order: a reviewer scrolling top-to-bottom reads a traversal that
  jumps between branches and never experiences a single coherent playthrough. The Approve action
  is a POST carrying only the storybook id; it does not reference the version the reviewer saw,
  does not require acknowledgement of any finding, has no dwell requirement, and can be issued
  from the queue-adjacent page without the detail view having been loaded at all
  (`reviewApi.approve(storybookId, visibility)`). The page's own comment describes the intended
  behaviour, the overview is "the skim entry point ... before deciding whether to read every
  passage **or jump straight to the flagged ones**", which is de facto sampling **by classifier
  flag**, and the classifiers cover an adult taxonomy (C4-4), so the highlighted set correlates
  poorly with child-relevant risk.
- **The economics**: the largest shell is 3.0-8.3 h of reading against ADR-005's "a few minutes"
  budget. A book at the 8-11 band is still 82 min. At any plausible per-book review cost the
  product can bear, the approver reads the flagged passages and the first few screens. That is not
  a defect of the reviewer; it is what the surface is built to permit.
- **Why it matters for the goal**: the human approver is named as the compensating control for
  every automated gap in this audit: Class C aggregate harm, cover art, imitable practice,
  unreviewed shells. A compensating control that cannot be exercised in the time the unit economics
  allow is not a control; it is an attribution of liability. The brief's F8 says sourcing
  architectures "are judged on what they ask that human to review". Today they ask for something
  no one performs.
- **Recommendation**: (1) Change the unit from node to **path**: render `reader_sample_paths` (say
  8-12 sampled playthroughs) plus every ending, as the primary surface, with the full node dump
  behind a toggle. A sampled path at the 8-11 band is ~1,500 words; ten of them is 60 min of real
  reading that corresponds to what children actually experience. (2) Add a **risk-ranked** reading
  order for the residual node dump (Stage-0 graded scores, imitable-hazard cues, peril/violence
  lexicon density) so the reviewer's first hour is spent where risk is, not at DFS index 0.
  (3) Make Approve carry the reviewed `version` and a per-finding acknowledgement, and reject a
  version that changed since the surface was rendered (the `#EDGE: timing dependencies` note at
  `node_edit.py:60` already identifies this and defers it). (4) Record review dwell time and
  scroll coverage as an operational metric, not as a gate, but so "did anyone read this" becomes
  answerable in an incident. (5) Amend ADR-005: "a few minutes" is false above the 5-8 band and
  should be replaced with a per-band stated review budget the surface is designed to fit.
- **How to check I'm right**: load a 193-node book in the admin console and count rendered
  `.review-card` elements; read `buildReadThrough` and confirm the traversal is a stack-based DFS,
  not a path enumeration. Read `ReviewDetailPage.tsx:784-810`: the confirm dialog's only state is
  `visibility`. `grep -n "approve" frontend/src/admin/*.ts`, the API call takes no version and no
  attestation.

---

## C4-4: The automated safety taxonomy is adult-content moderation; most child-relevant harms are uncovered

- **Severity**: high
- **Category**: safety coverage
- **Locus**: `src/cyo_adventure/moderation/classifiers.py:172-183` (`_OPENAI_BRIGHTLINE`),
  `classifiers.py:44-51` (`PERSPECTIVE_ATTRIBUTES`), `classifiers.py:72`
  (`_ADVISORY_SCORE_FLOOR`), `src/cyo_adventure/moderation/stages.py:63-92`
  (`_CONTENT_CONCERNS`, `_SAFETY_RUBRIC`), `src/cyo_adventure/validator/policy.py:311-360`
  (PL-15/PL-16)
- **Problem**: what actually gates is a short list. **Hard block**: OpenAI `sexual`,
  `sexual/minors`, `self-harm/instructions`, `self-harm/intent`, `illicit/violent`,
  `hate/threatening`, `harassment/threatening` (per node, boolean flag only); Perspective
  `SEXUALLY_EXPLICIT >= 0.8` (per node); Stage-1 LLM verdict `block` against a four-clause rubric
  (sexual content, self-harm instructions, real-world danger modeled as achievable, cruelty
  rewarded as the good outcome). **Soft flag** (routes to one repair, then to the human): Stage-1
  `flag` for "too mature for the band". **Advisory, never gates**: every Perspective attribute
  other than the explicit bright line, every OpenAI graded score, and, critically, the
  `has_soft_flag` property counts only `FLAG`, so `ADVISORY` findings have no effect on routing at
  all (`report.py:186-196`). Deterministic policy adds only PL-15 (forbidden *ending kinds* per
  band, e.g. no `death` at 3-5) and PL-16 (declared content flags vs band ceiling, self-declared,
  see C4-6).

  Coverage against the harms this product must handle:

  | Harm | Status | Basis |
  |---|---|---|
  | Sexual content | **covered** (node level) | OpenAI bright line + Perspective + Stage-1 rubric |
  | Self-harm instructions / intent | **covered** (node level) | OpenAI bright line + Stage-1 concern `self_harm` |
  | Self-harm *ideation/depiction* (non-instructional) | **partial** | plain `self-harm` is not in `_OPENAI_BRIGHTLINE`; reaches ADVISORY only, which never gates |
  | Violent *threats* | **covered** | `hate/threatening`, `harassment/threatening` |
  | Violence intensity (non-threatening depiction) | **uncovered by gate** | OpenAI `violence` is not bright-line; Perspective has no violence attribute; PL-16 checks a self-declared flag |
  | Age-inappropriate peril / horror | **partial, band-relative only** | Stage-1 `frightening_content` / `too_mature` concerns exist but are a soft FLAG on one model's judgement of one passage; nothing deterministic |
  | Grooming-shaped narrative | **uncovered** | requires path assembly (C4-1); no concern slug exists for it |
  | Bullying (non-threatening, non-slur) | **uncovered by gate** | `insult`/`toxicity` are ADVISORY-only; no gating path |
  | Discriminatory content / stereotyping | **partial** | only `hate/threatening` gates; `identity_attack` is ADVISORY; stereotyping in a sympathetic register is invisible to both |
  | Substance use | **uncovered** | no category, no concern slug, no lexicon anywhere |
  | Medically dangerous / imitable instruction | **uncovered in production** | Stage-1's "real-world danger modeled as achievable" is the only channel, and it is one model on one passage; `validator/imitable.py` is dead code (C4-8) |
  | Religious / political content | **uncovered** | out of every taxonomy; not necessarily a defect, but it is undeclared |
  | Profanity | **covered** | `_CONTENT_CONCERNS` + Perspective `PROFANITY` |
  | Cover art imagery | **uncovered** (C4-7) | no image classifier exists |
  | Path-cumulative harm | **uncovered** (C4-1) | no path unit exists |

  Two aggravating details. The advisory floor `0.01` is **known to be wrong**: the module's own
  comment records that the 2026-08-01 Stage-0 baseline refutes the rationale, all 120 clean
  passages carry at least one attribute at or above the floor, and the *clean* maximum (0.397
  SEXUALLY_EXPLICIT) **exceeds the adversarial maximum** (0.161). So the graded signal is noise at
  this floor, and the admin noise floor (default 0.05) then filters some of it back out of the
  reviewer's view. And Perspective sunsets 2026-12-31, after which OpenAI is the sole bright-line
  classifier and the only redundancy in Stage 0 disappears.
- **Why it matters for the goal**: the uncovered column is, with the exception of sexual content,
  most of what a parent means by "is this safe for my child". The system is strong on the harms
  adult platforms are sued over and weak on the harms children's publishers are judged on.
- **Recommendation**: (1) Write an explicit, versioned **child-safety policy document** enumerating
  the harm classes in scope and out of scope, per band, and derive the concern taxonomy from it
  rather than from the classifier vendors' categories. (2) Add gating concern slugs for
  `substance_use`, `bullying`, `stereotyping`, and `grooming_pattern` and put them in the Stage-1
  rubric with band-relative thresholds. (3) Promote plain `self-harm` and `violence` OpenAI
  categories to a **score-thresholded soft FLAG** for the young bands rather than leaving them
  ADVISORY. (4) Recalibrate `_ADVISORY_SCORE_FLOOR` against `stage0-baseline-2026-08-01.json`,
  the data to do it is already committed. (5) Plan the Perspective replacement now, before the
  sunset, or accept single-vendor Stage-0 explicitly.
- **How to check I'm right**: `_OPENAI_BRIGHTLINE` at `classifiers.py:172` is seven strings;
  `_CONTENT_CONCERNS` at `stages.py:63` is eight. Grep the repo for `substance`, `bullying`,
  `stereotyp`, `grooming`, no hits in `src/`. `ModerationReport.has_soft_flag` at `report.py:186`
  tests `Verdict.FLAG` only.

---

## C4-5: `validator/safety.py` is a Phase-2 stub, so the deterministic gate contributes zero safety: in the fresh-fill path, the repair-adoption gate, and the published-catalog re-screen

- **Severity**: high
- **Category**: safety coverage
- **Locus**: `src/cyo_adventure/validator/safety.py:41-57` (`check_safety` returns an empty
  report), `src/cyo_adventure/validator/gate.py:213` (`merged.extend(check_safety(story))`),
  `gate.py:238` (`safety_flagged` computation)
- **Problem**: SAFE-14, the deterministic safety rule the gate advertises, has never been
  implemented. `check_safety` discards its argument and returns an empty `ValidationReport`. Every
  consumer of `GateResult.safety_flagged` is therefore reading a constant `False`. This matters in
  three places that each *look* like a safety check and are not: `run_gate` at fresh fill;
  `moderation/pipeline.py::_repair_is_adoptable`, which re-proves a repaired blob "on the
  deterministic gate ... the same gate the original draft passed" (structure only, no safety); and
  `moderation/rescreen.py`, the published-catalog policy sweep, whose stated purpose is to check
  the existing catalog against a *safety* policy change and which runs `run_gate` plus Stage-0
  classifiers. The gate's own docstring is honest ("Phase-2 stub, always empty"), but the module
  and the flag survive in four call paths where a reader will take them for coverage.
  `validator/blind_spots.py`, the module explicitly built so "a gate's silence stops reading as a
  pass", declares three OBSERVED dimensions (graph integrity, quantitative reading level, filled
  prose) and four UNOBSERVED ones, and **safety appears in neither list**; it also has no caller
  outside a test comment, so its declaration never reaches a verdict a human sees.
- **Why it matters for the goal**: F2 of the brief says "deterministic gates come first ... safety
  classification ... checked by code before any model or human judges anything". For safety
  specifically that is not true: there is no deterministic safety code in the gate at all. Every
  safety judgement in the system is made by a third-party classifier or an LLM.
- **Recommendation**: either implement SAFE-14 as the deterministic floor the docs claim (a
  band-scoped lexicon plus the imitable-hazard screen of C4-8 plus a declared-vs-measured
  content-flag check per C4-6), or **delete `check_safety`, the `safety_flagged` field, and the
  SAFE-14 references from `gate.py`'s docstring** and replace them with a `blind_spots.UNOBSERVED`
  entry named `content_safety`. A stub that returns `ok=True` on a child-safety dimension is worse
  than an absent one, for the reason `blind_spots.py` itself argues. Wire `blind_spots.annotate()`
  into the persisted `validation_report` so the review surface can render "this verdict did not
  examine: content safety".
- **How to check I'm right**: read `validator/safety.py` end to end (57 lines, body is
  `_ = story; return ValidationReport()`). `grep -rn "safety_flagged" src/`, every read is of a
  provably-constant `False`. `grep -rn "blind_spots" --include=*.py src/ scripts/ tests/` returns
  one test comment.

---

## C4-6: The band content ceiling is self-certified: `content_flags` are declared by the shell/model and never measured against the prose, and the guardian's per-child caps are never enforced

- **Severity**: high
- **Category**: safety coverage
- **Locus**: `src/cyo_adventure/validator/policy.py:337-360` (`_check_content_ceiling`, PL-16),
  `src/cyo_adventure/validator/band_profile.py:31-43` (`content_ceiling`),
  `src/cyo_adventure/db/models.py:770` (`ChildProfile.allowed_content_flags`),
  `src/cyo_adventure/api/assignments.py:285-312` (assignment gate: age band only)
- **Problem**: PL-16 compares `story.metadata.content_flags` (violence / scariness / peril, each
  `none|mild|moderate|intense`) against the band ceiling. Those flags are **written into the blob
  by the generator, or inherited verbatim from the skeleton's metadata**. Nothing anywhere in the
  repo measures the prose and compares it to the declaration. A generator that writes intense peril
  and declares `peril: "mild"` clears PL-16 unconditionally. Separately, `ChildProfile.
  allowed_content_flags`, the per-child cap a guardian sets in `ProfileFormDialog`, is read only
  by `story_requests/brief.py` (as *generation guidance*) and echoed by `/v1/me`; it is **not
  checked at assignment**. `api/assignments.py` enforces the age-band rank ceiling only, and fails
  open when either side is unparseable. So a guardian who sets "violence: none" for their
  six-year-old has expressed a preference that steers a prompt and gates nothing.
- **The escape, concretely**: the committed shell `the-tenfold-siege` declares
  `violence: moderate, scariness: intense, peril: intense` at 16+. A fill of that shell whose
  metadata declares `peril: mild` would clear PL-16 for a lower band. More realistically: any
  fill's declared flags are one line of model output that no gate audits, and the guardian's own
  cap does not bind at the point of assignment where it would matter.
- **Why it matters for the goal**: PL-16 reads, in the code and in the docs, as the age-safety
  ceiling. It is a consistency check between two model-authored fields. This is the same defect
  class the audit-remediation doc calls "a safety floor defeated by unvalidated data" (`UW-C285(b)`,
  where the theme denylist trusts the contract's own band).
- **Recommendation**: (1) Add a deterministic **declared-vs-measured** check: a peril/violence/
  scariness lexicon density per band, producing an ERROR when measured intensity exceeds the
  declared level by more than one rank, and a FLAG when it exceeds the band ceiling. This is the
  natural home for the SAFE-14 body of C4-5. (2) Enforce `allowed_content_flags` in
  `assignments.py` alongside the band-rank check, with the same fail-open-on-unparseable posture
  but a loud advisory. (3) Route the story's declared flags into the review surface's summary strip
  so the approver sees what the book claims about itself.
- **How to check I'm right**: `grep -rn "content_flags" --include=*.py src/`, every hit is a
  read or a passthrough; nothing derives them from prose. `_check_content_ceiling` at
  `policy.py:337` reads `story.metadata.content_flags` directly.
  `grep -rn "allowed_content_flags" --include=*.py src/`, no hit in `assignments.py` or
  `library.py`.

---

## C4-7: Cover art has no automated safety check of any kind

- **Severity**: high
- **Category**: safety coverage
- **Locus**: `src/cyo_adventure/covers/service.py:207-220` (`#CRITICAL: security` marker stating
  no image-safety classifier exists), `covers/prompt.py:10-30` (`_safety_clause`),
  `frontend/src/admin/ReviewDetailPage.tsx:645-680` (cover approval UI)
- **Problem**: the cover pipeline is: build a prompt with a safety clause scaled to the story's
  (self-declared, see C4-6) content flags → call the image provider → optimize → upload → set
  `cover_status = "pending_review"` → a human clicks "Approve cover". The service's own comment is
  explicit: "An automated image-safety classifier (the `moderation/` analogue of the story-text
  gate) does **not** exist in this codebase yet ... human approval via `approve_cover` is the sole
  gate right now, not a second independent layer the way text has validator+moderation+approval."
  The only automated control is the provider's own refusal behaviour and prompt-side wording. The
  human control is one thumbnail and one button on a page where the approver is already saturated
  by 677 passages (C4-3).
- **Why it matters for the goal**: the cover is the single most-seen artefact of a book, it is on
  the library card, the shelf, and the recommendation surface, and it is the one thing a child sees
  before choosing to read. Scary or age-inappropriate imagery on a card is a higher-frequency
  exposure than any single node's prose. This is also the asset most likely to be screenshotted and
  shared, so it is the highest-reputational-risk output in the system.
- **Recommendation**: (1) Add an image-safety classifier call between the provider response and
  `pending_review`, every major moderation vendor offers one, and the seam is already marked in
  the code with the `#VERIFY` instruction for exactly this. Make a hit set `cover_status =
  "blocked"` rather than `pending_review`. (2) Until that lands, make the cover approval a
  **separate, explicitly-blocking step** in the review flow rather than an optional widget on the
  story page, and render the cover at full size, not as a card thumbnail. (3) `_safety_clause`
  scales off `content_flags`, which are self-declared; scale it off the band instead, which is
  validated.
- **How to check I'm right**: `grep -rn "moderat\|classifier\|nsfw" src/cyo_adventure/covers/`,
  the only hits are the comment saying no classifier exists and a `ProviderError` docstring for
  provider-side refusals. Read `covers/service.py:207-220`.

---

## C4-8: The imitable-hazard screen has zero callers: a named, measured harm class is unscreened in production while the work register records it as delivered

- **Severity**: high
- **Category**: safety coverage
- **Locus**: `src/cyo_adventure/validator/imitable.py:112` (`screen_for_review`),
  `docs/planning/unscheduled-work-register.md:516` (`UW-C264`),
  `docs/planning/authoring-lessons-log.md:477` (`AL-397`)
- **Problem**: `AL-397` names a harm class the rest of the pipeline is structurally blind to:
  "every safety check in the pipeline scores what happens **to** a character and none scores what a
  child is invited to imitate", instanced on three committed books (an enclosed snow tunnel crawled
  repeatedly as the "Greatest fort ever" ending; a bravery payoff for a small child lighting a wick
  solo; a hot oven opened as a choice whose depicted cost is slumped buns). `validator/imitable.py`
  was written to route such endings to a human, endings only, young bands only, hazard-plus-action
  co-occurrence, measured at 13 of 167 young-band endings. **It is never called.**
  `grep -rn "screen_for_review\|imitable"` across `src/`, `scripts/`, and `frontend/` returns only
  the module itself and its own unit test. `UW-C264` records the state as "**Screen half done
  2026-08-15 (`AL-405`)**: `validator/imitable.py` routes 13 of 167 young-band endings to human
  attention", a claim in the present tense about behaviour that does not occur, because nothing
  invokes it.
- **Why it matters for the goal**: this is the one harm class the programme discovered on its own,
  from its own corpus, with two independent readers converging, the highest-quality safety signal
  in the whole evidence base, and it produces no effect on any book. It is also the cheapest fix
  in this report: the screen is deterministic, local, already measured for precision, and the
  review surface already has a slot for per-node findings to render into.
- **Recommendation**: call `screen_for_review(story)` from the moderation pipeline (or from
  `run_gate` under `context="fill_result"`) and emit one `ADVISORY`-or-`FLAG` `Finding` per cue
  with `concern="real_world_danger"` and the cue name in the message, so the endings land in the
  approver's "Flagged passages" block with the reason attached. This is a ~15-line change. Then
  correct `UW-C264`'s status line: a screen with no caller is not half done, it is unshipped.
- **How to check I'm right**: `grep -rn "imitable\|screen_for_review\|HazardCue" --include=* .`,
  outside `validator/imitable.py`, `tests/unit/test_imitable.py`, and planning prose, there are no
  hits. Run the moderation pipeline over `the-snow-day-expedition` and confirm no
  imitable-hazard finding appears.

---

## C4-9: Repair can restructure the graph and break skeleton fidelity, and neither the fidelity gate nor the fill-integrity checks re-run on a repaired blob

- **Severity**: high
- **Category**: repair
- **Locus**: `src/cyo_adventure/moderation/pipeline.py:711-745` (`_repair_preserves_identity`),
  `pipeline.py:748-833` (`_repair_is_adoptable`), `src/cyo_adventure/moderation/repair.py:36-46`
  (`_REPAIR_SYSTEM`), `src/cyo_adventure/generation/fidelity_gate.py` (not imported by
  `pipeline.py`)
- **Problem**: the repair loop's bounds are genuinely good in three respects: it is **one** attempt
  (`attempt_repair` is called once, no loop, so it cannot cycle); the revised blob is **fully
  re-moderated from scratch** (`_run_all_stages` re-runs Stage 0 classifiers and Stages 1/3/4 over
  the revision); and a repair that fails the deterministic gate, changes the story's identity, or
  violates sentinel integrity is discarded with the pre-repair report driving routing. Three real
  gaps remain. (a) **Identity preservation is too weak for what the prompt promises.** The repair
  system prompt says "Preserve the exact node ids, choices, and branching structure. Only revise
  prose." `_repair_preserves_identity` verifies only `id`, `metadata.tier`, and **node count**. A
  repair that renames every node, rewires every choice target, deletes one ending and adds another,
  or changes `on_enter` effects and conditions passes all three checks so long as the count matches
  and `run_gate` still finds the result structurally valid. (b) **Skeleton fidelity is never
  re-checked.** `generation/fidelity_gate.py::run_stage1_gate` (deterministic
  `run_fidelity_checks` plus the semantic `run_semantic_fidelity_check` over beats and choice-label
  intent) runs at fill time from `orchestrator.py` and `import_story.py`, and is **not imported by
  `moderation/pipeline.py`**. So a repaired book can silently depart from the beats it was
  commissioned to depict, and the departure is invisible. (c) **Delivery measurements do not
  re-run.** `check_fill_integrity.py`'s 0.6 fill-rate floor and `check_sibling_fills.py`'s 4-gram
  budget, the two checks that exist precisely because "a passing gate is not quality" (`AL-490`),
  are script-side and never re-applied to a repair. A repair asked to soften a flagged passage
  can legitimately shorten it, and nothing notices the delivered-words regression.
- **The escape, concretely**: a book soft-flags on one node. The repair model, asked to revise
  prose, also "helpfully" reroutes two choices to avoid the flagged branch entirely, keeping the
  node count identical by adding a filler node. Result: the branch a human would have been shown as
  flagged is now unreachable-by-design, the graph differs from the approved skeleton, the beats of
  three nodes no longer match their `<<FILL>>` directives, and the adopted blob is what a guardian
  approves. `_repair_is_adoptable` returns `True` at every step.
- **Why it matters for the goal**: the whole architecture rests on F1, structure and prose are
  separate engineering problems, and structure is proven at catalog time by a human-reviewed PR.
  Repair is the one production path that can silently edit structure after that proof.
- **Recommendation**: (1) Strengthen `_repair_preserves_identity` to compare the **exact multiset
  of node ids and the exact choice-target edge set** between original and revision, not the node
  count. That is a five-line change and closes (a) completely. (2) Re-run `run_stage1_gate` on an
  adopted repair, or at minimum the deterministic half (`run_fidelity_checks`), which needs no LLM
  call. (3) Re-run the fill-rate floor on the revision and reject a repair that reduces delivered
  words below the floor. (4) Record on the report that the blob was repaired **and by which model**
  (today only `repaired: bool` survives).
- **How to check I'm right**: read `_repair_preserves_identity` (three comparisons, one of which is
  `len(original_nodes) == len(revised_nodes)`). `grep -n "fidelity" src/cyo_adventure/moderation/
  pipeline.py` returns nothing. Unit test to write: a repair that returns the same node count with
  every `choices[].target` permuted, it is currently adopted.

---

## C4-10: The first-pass safety reviewer is an unallowlisted, unrecorded, single-owner-anecdote choice

- **Severity**: high
- **Category**: reviewer model
- **Locus**: `src/cyo_adventure/api/schemas.py:1239-1240` (`review_stage1_model`,
  `review_stage2_model` as bare `str | None`),
  `src/cyo_adventure/story_requests/authoring_plan.py:273` (allowlist check applied to the
  **generation** provider/model only), `src/cyo_adventure/moderation/review_provider.py:104-155`
  (`build_review_provider`), `src/cyo_adventure/moderation/report.py:171-176`
  (`ModerationReport` has no reviewer-model field), `src/cyo_adventure/core/config.py:611-613`
- **Problem, four parts.**
  (a) **Grounding.** The brief states "DeepSeek V4 Flash currently performs well as the
  deterministic-style first-pass reviewer ahead of costlier review (owner practice, 2026-08)". The
  evidence class is a single practitioner's impression, weaker than the brief's own weakest
  declared class ("model-judged"), and applied to the one component whose failure is existential.
  The brief cites the review-model distillation plan as the formalization path, but that plan
  explicitly scopes itself out: "It does not touch `A6` ... and it does not replace any part of
  `S7`'s moderation pipeline. Nothing in this plan changes what a child can be shown."
  **There is no tracked workstream formalizing the safety reviewer choice.** The `S-1` evidence
  cited in section 4.2 measures DeepSeek V4 Flash as a *structure author* (1/3 and 2/3 tool-assisted
  passes), which says nothing about its safety judgement.
  (b) **Governance.** The generation provider/model is validated against a DB-backed enabled
  allowlist before anything is persisted or billed, with a `#CRITICAL: security` marker explaining
  why. The **review** model has no such check: `review_stage1_model` and `review_stage2_model` are
  free strings on the admin's authoring plan, threaded straight through `resolve_review_settings`
  into `build_openrouter_leg`. An admin (or an admin-console defect) can point the child-safety
  reviewer at any model id OpenRouter will route, with no allowlist, no per-model record, and no
  audit event.
  (c) **Provenance.** `StorybookVersion` records the generation `model`, `provider`, and
  `prompt_version`, but **nothing records the review model**. `ModerationReport` carries only
  `reviewer_independent: bool`. So no persisted artefact answers "which model made the safety
  judgement on this book" (see C4-14).
  (d) **Jurisdiction and data handling.** Every node body of a children's book egresses to a
  third-party inference host. The PII guard (`PiiGuardedProvider` + `assert_prompt_pii_safe`) is a
  genuine strength and blocks registered child names, but it does not change that the *content*,
  a book personalised to a specific child's request, leaves the deployment. OpenRouter routes to
  whichever upstream endpoint it selects; `docs/planning/review-model-distillation-plan.md` records
  that floating `~vendor/model-latest` aliases "move across both checkpoint and serving provider
  without notice" and that "this account's own data policy can silently remove a judge's serving
  stack" (`AL-384`). For an app targeting the Kids Category under ADR-008/ADR-018, the serving
  jurisdiction and retention terms of the safety reviewer are a compliance fact, not a
  configuration detail, and today they are neither pinned nor recorded.
- **Why it matters for the goal**: a non-frontier model at the first-pass safety position is
  defensible *if* its false-negative rate on this corpus is measured. It is not (C4-13). Absent
  measurement, "performs well" is an assessment of its *agreement with the owner on books the owner
  already believed were fine*, which is exactly the quantity that cannot detect a miss.
- **Recommendation**: (1) Put the review model on the same enabled allowlist as the generation
  model, with a distinct `reviewer` capability flag, and reject an off-allowlist override at 422.
  (2) Persist `review_provider` and `review_model` on `StorybookVersion` (or in the report's
  summary block) alongside `reviewer_independent`. (3) Pin the reviewer to a dated model id, never
  a `-latest` alias, and record the pin in an ADR with its data-handling terms and serving
  jurisdiction. (4) Validate the choice: run the adversarial harness (C4-13) with DeepSeek V4 Flash
  as the reviewer leg against at least one frontier leg and one refusal-heavy leg, on a corpus ten
  times the current size, and publish per-class catch rates and the benign-control false-positive
  rate. Until then, keep the frontier default (`anthropic/claude-sonnet-4.6` is the configured
  default today) and treat V4 Flash as a **pre-filter that can only escalate, never clear**, i.e.
  a `flag`/`block` from Flash gates, a `safe` from Flash does not conclude the review.
- **How to check I'm right**: read `schemas.py:1239` (no `Field`, no validator) and contrast with
  `authoring_plan.py:264-279`. `grep -rn "review_model\|reviewer_model" src/cyo_adventure/db/`,
  no column. Read `review-model-distillation-plan.md` lines 25-29 for the explicit exclusion of the
  moderation pipeline.

---

## C4-11: The threshold flywheel is a desensitisation loop: it converts an approver's override habit into hidden findings on the guardian's assignment screen

- **Severity**: high
- **Category**: thresholds
- **Locus**: `src/cyo_adventure/moderation/insights.py:34-45` (`SUGGESTION_MIN_DECIDED = 5`,
  `SUGGESTION_MIN_OVERRIDE_RATE = 0.8`, `_VERDICT_RAISE`),
  `src/cyo_adventure/api/moderation_dashboard.py:135`,
  `src/cyo_adventure/api/moderation_thresholds.py:153-244` (upsert),
  `src/cyo_adventure/moderation/thresholds.py:76-120` (`ThresholdPolicy.surfaces`),
  `src/cyo_adventure/api/assignments.py:239` (guardian content summary)
- **Problem, and the provenance answer**: the thresholds are **surfacing** thresholds, not gating
  thresholds, this is the most important thing to state, because it is easy to misread in both
  directions. Changing one cannot let more content past the gate. What it *can* do is decide which
  recorded findings a **guardian** sees on the content summary they read before assigning a book to
  their child (`assignments.py:239` → `build_content_summary` → `policy.surfaces`). The code
  default is `min_verdict=FLAG, min_score=None`; the DB table is a sparse override set; the admin
  surface is deliberately unfiltered. **Provenance of the numbers**: `DEFAULT_THRESHOLD` is a code
  constant with no cited derivation; `ADMIN_NOISE_FLOOR_DEFAULT = 0.05` is a code constant mirrored
  by hand into a migration's frozen literal, also underived; `_ADVISORY_SCORE_FLOOR = 0.01` is
  documented as **refuted by the project's own 2026-08-01 baseline** and kept anyway. So: no
  threshold in this subsystem has a measured basis. **Who can change them**: any admin, via
  `PUT /admin/moderation-thresholds/{age_band}` and `PUT /admin/moderation/noise-floor`. **Is it
  audited**: yes, and well, `THRESHOLD_CHANGED` carries `{age_band, category, action,
  min_verdict, min_score}` and `NOISE_FLOOR_CHANGED` carries `{value}`, both on the append-only
  event log, and the dashboard renders the last 20 changes. That part is a strength.
  **The loop is the problem.** `suggest_thresholds` correlates persisted reports with `released` /
  `sent_back` events and proposes **raising** `min_verdict` one step for any (band, category) where
  at least 5 decided versions carried the finding and at least **80%** were released anyway. The
  input is the *admin's* override behaviour; the output hides findings from the *guardian*. Two
  different humans, and the causal direction is exactly wrong: an approver who is saturated by
  C4-3 and approves everything generates, within five books, a standing recommendation to stop
  telling parents about whatever they approved through. `SUGGESTION_MIN_DECIDED = 5` is a very
  small n for a child-safety decision, and nothing in the suggestion distinguishes "this category
  is noisy" from "this reviewer is not reading".
- **Why it matters for the goal**: this is the concrete mechanism by which "lowering a threshold
  silently widens what reaches children" is true here, not by widening the gate, but by
  narrowing what the second human in the chain is told. It also degrades over time, automatically,
  in proportion to how rushed the first human is.
- **Recommendation**: (1) Exclude from the override-rate numerator any release where the finding
  was not acknowledged (which requires the acknowledgement of C4-3(3)), an unread finding is not
  an override. (2) Raise `SUGGESTION_MIN_DECIDED` substantially (30+) and require the suggestion to
  cite the per-finding *false-positive* evidence (a reviewer-supplied "this was noise" reason code)
  rather than mere release. (3) Never allow a suggestion to raise `min_verdict` past `FLAG` for any
  concern in the bright-line or `real_world_danger`/`sexual_content`/`self_harm` set, make that a
  hard floor in `_VERDICT_RAISE`. (4) Derive `DEFAULT_THRESHOLD` and the noise floors from the
  committed `stage0-baseline-2026-08-01.json` and record the derivation.
- **How to check I'm right**: read `insights.py:30-45` and `suggest_thresholds`; then follow
  `policy.surfaces` from `assignments.py:239` into `review_surface.py:709` and confirm the
  guardian content summary is the consumer. Confirm the admin path passes `admin_noise_floor` and
  **not** the policy (`approval.py:380`).

---

## C4-12: `S-5`: an unreviewed shell transfers content authority into the one stage nothing screens

- **Severity**: high
- **Category**: shell risk
- **Locus**: `src/cyo_adventure/generation/templates/fill.md:32-69` (beats as a mandatory content
  contract), `src/cyo_adventure/moderation/fidelity_review.py:33-50` (fidelity reviewer *enforces*
  beat compliance), `scripts/check_skeleton.py` (no safety check anywhere),
  `.github/workflows/skeleton-promotion.yml`, `src/cyo_adventure/validator/policy.py:311-360`
- **Problem, the risk transfer, concretely**: a skeleton is not a neutral armature. Three of its
  properties are content decisions that survive the fill unchanged and are enforced *against* the
  filling model:
  1. **`beats` are a binding content contract.** `fill.md` instructs: "Your prose MUST depict this
     exact beat, the same events and outcome, even though you are changing names, setting
     details, and surface theme." The Stage-1 semantic fidelity reviewer then *flags a fill that
     deviates*. So an unsafe beat is not merely permitted, it is **mandated and audited for
     compliance**. `check_skeleton.py --strict` runs schema, reachability, termination, budgets,
     topology admissibility, pacing, reading clock, ending mix, first-decision window, corridor
     density, choice grammar, walk floors, and anti-clone distance, and **no content check of any
     kind on the beat text**.
  2. **`content_flags` and `age_band` are declared in the shell's metadata** and inherited by the
     fill, which means the shell chooses its own PL-15/PL-16 ceiling (see C4-6). A shell declaring
     `peril: mild` while commissioning intense peril in its beats passes the band ceiling by
     construction.
  3. **The decision structure creates framing the per-node gate cannot see.** A shell that
     repeatedly offers "tell the grown-up / handle it yourself" and routes the self-reliant branch
     to `triumph` endings and the tell-an-adult branch to `setback` endings has encoded a message
     no node states. PL-15 constrains ending *kinds*; PL-24 constrains the *mix*; nothing
     constrains what the mix **rewards**. This is the `AL-397` gap (C4-8) elevated from a single
     ending to the graph's whole incentive structure.

  Structural traps are, by contrast, well covered: dead-ends that read as endings, unreachable
  nodes, trap loops, and depth-unqualified endings are all caught deterministically by Layer 1 and
  the walk floors, on every changed shell, in CI. **The S-5 risk is semantic, not topological**,
  and the fill-stage human review is the worst possible place to catch it, because the reviewer is
  reading rendered prose (C4-3), one node at a time, with no view of the beat that commissioned it,
  no view of the shell's provenance, and no signal that this shell has never been read by anyone.
- **The escape**: a mutation-derived or LLM-authored shell for the 8-11 band whose beats commission
  a sympathetic adult character who repeatedly asks the child protagonist to keep confidences, and
  whose ending mix rewards the branches where they do. Every gate passes: topology admissible,
  budgets met, anti-clone distance cleared, endings depth-qualified, no forbidden kind, declared
  flags within ceiling. Every filled node reads as warm, ordinary children's prose and gets
  `safe` from Stage 1. The book is published. The framing is in the shell, and no human ever read
  the shell.
- **Why it matters for the goal**: the brief's F5 ("reuse structure freely") and ADR-020's offline
  mutation are the programme's answer to catalog cost, and both increase the number of shells per
  human-hour. `Q-1` says a child exhausts a cell by roughly the fourth request at 3-4 skeletons per
  cell, so demand pressure on shell supply is structural and permanent. This is the axis along
  which the safety floor will be eroded, quietly, by economics.
- **Recommended safety floor** (four rules, in order of cost):
  1. **A shell may not be `production_eligible` until a named human has read its beats and its
     ending mix.** Record the reviewer and the date in the shell's metadata (or a sidecar), and
     make `skeleton-promotion.yml` fail a `production_eligible: true` shell with no such record.
     This is the floor; the PR merge alone is not it, because a PR can be merged on a green CI
     check without anyone reading 677 beat strings.
  2. **Run the content gate over beats at catalog time.** The beats are prose; run Stage-0
     classifiers and a beats-specific LLM safety pass over them in `check_skeleton --strict`. Cheap
     (677 short strings), deterministic to re-run, and it moves the check from the per-book path
     (where it costs money every time the shell is used) to the per-shell path (where it is paid
     once).
  3. **Derive, do not declare, the shell's `content_flags`**, or at minimum require the promotion
     PR to justify a declared level below what the beats commission.
  4. **Distinguish reviewed from unreviewed shells on the approver's surface.** The review detail
     page should say "this book was filled over shell `X`, human-reviewed on `date` by `person`"
     or "over an unreviewed shell", because the correct amount of reading the approver should do
     differs by a lot between those two cases, and today the approver cannot tell.

  For `S-5` as an experiment: the falsifier should be a seeded-defect run, take a known-good
  shell, seed an unsafe framing into its beats and ending mix only (no unsafe node prose), fill it,
  and measure whether the fill-stage gate or a fill-stage human reviewer catches it. My prediction
  from the code is that neither does, and that is the number the decision needs.
- **How to check I'm right**: `grep -n "safety\|classifier\|moderat" scripts/check_skeleton.py`,
  one hit, and it is about an iteration cap. Read `templates/fill.md:36` and
  `moderation/fidelity_review.py:33-50` together: the second enforces the first. Read
  `skeletons/16+/the-tenfold-siege.json`'s metadata: `content_flags` and `age_band` live in the
  shell.

---

## C4-13: The false-negative rate of the safety gate has never been measured; the corpus is 13 items and no live run exists

- **Severity**: medium
- **Category**: thresholds
- **Locus**: `docs/planning/safety/adversarial-corpus.json` (13 items, 9 executable),
  `docs/planning/safety/adversarial-safety-evaluation.md` (attempted-run log, acceptance
  thresholds), `scripts/adversarial_harness.py`, `.github/workflows/safety-eval.yml`
- **Problem**: the answer to "what is the false-negative rate and how is it measured" is: it is not
  measured, and the project knows this and has documented it unusually honestly. The evaluation
  doc's attempted-run log records one dated attempt (2026-07-28) blocked on absent credentials, and
  **no `adversarial-results-*.json` exists in the repo**. Acceptance thresholds are stated (100% of
  Class A and B routed to a human; 0 bypass paths; 100% PII blocked) and Classes A, B, and E are
  marked unmeasured. The corpus itself is the deeper problem: 13 items, 9 executable, four of them
  Class A (three probes plus one on-band control), two Class C, three Class E injection probes, one
  PII control. There is **one benign control**, so the false-positive rate is unmeasurable, and by
  the corpus's own content policy the items "deliberately do not contain gratuitous harmful
  detail", which bounds how hard a probe can be. Nothing in the corpus covers substance use,
  bullying, stereotyping, discriminatory content, or medically dangerous instruction, the
  uncovered rows of C4-4, so even a successful live run would not measure them. The CI workflow
  was correctly repaired (PR #435) so a credential-less scheduled run now goes **red** rather than
  vacuously green; that is the right state and should not be "fixed" by relaxing it.
- **Why it matters for the goal**: every claim in this audit about what the gate catches is an
  argument from reading code and prompts. Whether a real model actually returns `flag` on an
  off-band passage is unknown. For the reviewer-model decision (C4-10) this is the missing
  measurement that makes the decision unmakeable.
- **Recommendation**: (1) Configure the secrets and run it, this is the single highest-value
  unblocked action in this report, and the harness already exists and already refuses to report a
  mock run as evidence. (2) Grow the corpus to at least 100 items with ≥30 benign controls, one
  arm per harm class in C4-4's table, and a Class-C arm expressed as **multi-node paths** so the
  path gap of C4-1 is measured rather than assumed. (3) Add a reviewer-model axis so the corpus
  becomes the acceptance test for any change to `review_openrouter_model`. (4) Publish per-class
  catch rate *and* the benign false-positive rate together, a gate that flags everything is not a
  pass.
- **How to check I'm right**: `ls docs/planning/safety/`, no results file.
  `python3 -c "import json; d=json.load(open('docs/planning/safety/adversarial-corpus.json')); print(len(d['items']))"`
  → 13. Read the "Attempted run log" table in the evaluation doc.

---

## C4-14: Incident reconstruction fails on three of the four questions it must answer

- **Severity**: medium
- **Category**: audit/incident
- **Locus**: `src/cyo_adventure/db/models.py:1458-1520` (`StorybookVersion` columns),
  `src/cyo_adventure/events/writer.py:17-90` (payload allowlist),
  `src/cyo_adventure/api/node_edit.py:690-720` (in-place blob mutation, `node_id`-only event),
  `src/cyo_adventure/api/audit.py:244`
- **Problem**: test the four questions against the schema.
  **"Who approved it?", answerable, well.** `storybook_version.approved_by` + `published_at` are
  stamped inside the sole publish path, and the `RELEASED` event stamps the acting role
  (distinguishing a dual-role adult's self-review from cross-family review). This is a strength.
  **"Which prompt and model produced each node?", not answerable.**
  `StorybookVersion.{model, provider, prompt_version, skeleton_slug}` are **whole-book** fields.
  Large books are filled in chunks (`generation/chunking.py`), and a resume or a repair can involve
  a different model, but only one string is stored. There is no per-node provenance anywhere.
  **"What did the model see / which model reviewed?", not answerable.** The review model and
  provider are recorded nowhere (C4-10); the report keeps only `reviewer_independent: bool` and
  `nodes_reviewed: int`. The review *prompts* are not retained.
  **"What did the approver see?", not answerable after any edit.** `api/node_edit.py` assigns
  `version_row.blob = new_blob` **in place**, no new version row, and the `NODE_EDITED` event
  payload is `{node_id}` only, "never the edited prose". So the pre-edit text is destroyed, and the
  moderation report is spliced rather than regenerated. Reconstructing the state a book was in when
  it was approved is impossible for any book that was edited.
  **"What else needs recall?", partially answerable, and this is the good news.**
  `skeleton_slug` and `model`/`prompt_version` are on every version row, so "every other book from
  the same skeleton / model / prompt" is a straightforward query, and `STORYBOOK_ARCHIVED` already
  drives the pull-everywhere path including offline cache eviction
  (`frontend/src/offline/revocation.ts`). The recall *mechanism* exists; the *forensics* do not.
  One smaller gap: the `RELEASED` event's payload allowlist is `{"visibility"}` and its `entity_id`
  is the bare storybook id, so the event alone does not name the published version.
- **Why it matters for the goal**: after an incident the questions are "how far does this go" and
  "what changed the outcome". The first is answerable; the second is not, and the second is what
  drives the fix.
- **Recommendation**: (1) Make `node_edit` create a **new version row** rather than mutating in
  place, the state machine already tolerates multiple versions and the review surface already has
  a version-compare view (`ReviewCompare.tsx`). This single change fixes the "what did the approver
  see" question and makes the compare view meaningful. (2) Persist `review_provider`/`review_model`
  and a `moderated_at` timestamp on the version row. (3) Add per-chunk (not per-node) model
  provenance to the version row as a small JSONB array. (4) Add `version` to the `RELEASED` payload
  allowlist, an integer, so the PII-free contract is unaffected.
- **How to check I'm right**: `grep -n "Mapped\[" src/cyo_adventure/db/models.py` in the
  `StorybookVersion` block, one `model`, one `prompt_version`, no reviewer fields. Read
  `node_edit.py:690` (`version_row.blob = new_blob`). Read `events/writer.py:44` for the
  `RELEASED` allowlist.

---

## C4-15: A re-screen that finds a published book unsafe cannot remove it, and does not run the safety stage at all

- **Severity**: medium
- **Category**: audit/incident
- **Locus**: `src/cyo_adventure/moderation/rescreen.py:11-42` (scope and no-auto-unpublish),
  `src/cyo_adventure/api/remoderate.py:44-60` (StateTransitionError swallowed by design),
  `src/cyo_adventure/publishing/state_machine.py` (no machine-reachable exit from `published`)
- **Problem**: two remediation tools exist and neither can act. `POST /admin/rescreen` re-runs the
  deterministic gate and the Stage-0 classifiers over the published catalog but **explicitly does
  not run the LLM safety stage** ("adding their LLM cost/latency to every sweep would buy no
  signal"), which means the sweep cannot detect anything the Stage-1 reviewer would catch, and
  Stage 1 is the only gate that judges against the age band. It also does not write its result back
  onto `moderation_report`. `POST /admin/remoderate/{id}/{version}` does run the full pipeline over
  a published version, but its terminal `submit`/`auto_reject` call is always an illegal transition
  from `published` and is caught and discarded, so **a fresh hard BLOCK on a published book leaves
  the book published, assigned, readable, and cached offline**. The only exit is a human clicking
  Archive. The no-auto-unpublish decision is deliberate and well argued (ADR-005 governs both
  directions; a child mid-story should not have a book vanish), and I am not arguing against the
  decision: I am arguing that the compensating alert does not exist.
- **Why it matters for the goal**: the incident path is "we discovered a harm class; sweep the
  catalog; pull the affected books". Today step two cannot see LLM-detectable harm and step three
  requires an admin to notice a summary field and act by hand, per book, with no notification, no
  queue, and no SLA.
- **Recommendation**: (1) Add an **LLM safety leg to the rescreen sweep**, opt-in per run, so a
  policy change involving the age-band rubric can actually be checked against the catalog. (2) When
  a re-moderation of a published book produces a hard block, write a distinct pipeline event, raise
  a notification to the admin queue, and surface the book in a "published books now failing"
  bucket on the moderation dashboard. (3) Consider an intermediate `quarantined` state, invisible
  to new assignment, still readable to a child mid-book, so the machine has an action short of
  archive that does not defeat ADR-005.
- **How to check I'm right**: read `rescreen.py:11-20` (explicit exclusion of `moderation.stages`)
  and `remoderate.py:44-60` (the caught `StateTransitionError`). Grep `publishing/state_machine.py`
  for any transition out of `PUBLISHED` other than `ARCHIVE`, there is none.

---

## C4-16: Stage-0 advisories never gate, on a floor the project's own baseline refutes, with a sole-vendor bright line arriving in December

- **Severity**: medium
- **Category**: safety coverage
- **Locus**: `src/cyo_adventure/moderation/classifiers.py:52-72` (the floor and its refutation),
  `classifiers.py:684` (Perspective bright line is `SEXUALLY_EXPLICIT` only),
  `src/cyo_adventure/moderation/report.py:186-196` (`has_soft_flag` counts `FLAG` only)
- **Problem**: every Perspective attribute except `SEXUALLY_EXPLICIT >= 0.8`, and every OpenAI
  graded score, produces an `ADVISORY` finding. `ModerationReport.has_soft_flag` counts only
  `FLAG`, so **no advisory has any effect on routing**, it does not trigger repair, does not
  prevent `submit`, and on the admin surface is additionally filtered by the noise floor and then
  collapsed into a "low advisory" toggle if its severity is LOW. So a node scoring 0.79 on
  `SEVERE_TOXICITY` or 0.75 on `THREAT` produces a row behind a toggle and nothing else. The
  advisory floor is `0.01`, and the module's own comment records that the committed 2026-08-01
  baseline refutes the rationale for it: all 120 clean passages cross it on some attribute, and the
  clean maximum (0.397) exceeds the adversarial maximum (0.161). The `#VERIFY` says "recalibrate
  against the Stage-0 baseline before the 2026-12-31 Perspective sunset", and that sunset also
  removes the only second opinion in Stage 0. The genuinely strong parts of this module should be
  said plainly: per-node retry with backoff, a circuit breaker, and, importantly, a
  `classifier_coverage_incomplete` **FLAG** (not advisory) naming every unscreened node, which is
  exactly the right call and closes the "93% of the book was never screened and it looked clean"
  hole.
- **Why it matters for the goal**: the graded band between "clearly fine" and "bright line" is
  where most real children's-content risk lives, and it is currently a display-only channel on a
  miscalibrated scale.
- **Recommendation**: (1) Recalibrate `_ADVISORY_SCORE_FLOOR` from the committed baseline
  (the clean-passage 95th percentile per attribute, not one global constant). (2) Introduce a
  **band-scoped soft-FLAG tier** between advisory and bright line: e.g. `THREAT`/`SEVERE_TOXICITY`
  ≥ 0.6 at bands 3-5 and 5-8 becomes a `FLAG`, which routes to repair and guarantees the human sees
  it above the toggle. (3) Choose and integrate the Perspective successor before December.
- **How to check I'm right**: read `classifiers.py:52-72`, the comment states the refutation
  explicitly. `report.py:190`: `any(f.verdict is Verdict.FLAG ...)`.

---

## C4-17: The mock-reviewer escape hatch can publish outside local; it is stamped but never refused

- **Severity**: low
- **Category**: reviewer model
- **Locus**: `src/cyo_adventure/core/config.py:657-667`, `moderation/pipeline.py:252-268`
  (`_stamp_mock_reviewer`), `publishing/service.py:412`
- **Problem**: `CYO_ADVENTURE_ALLOW_MOCK_REVIEW=1` permits `review_provider="mock"` outside
  `environment="local"`. The mock returns `"{}"` for every call, which the parser maps to the
  Stage-1 fail-safe `FLAG`, so a mock-moderated book soft-flags, attempts one (pointless) repair,
  and reaches `in_review`. The report is stamped in two ways: `reviewer_independent = False` plus
  a structural ADVISORY saying "no real safety review ran", and the stamp is deliberately
  re-applied to an adopted repair's fresh report so it cannot be laundered. That design is good.
  What is missing is the refusal: `approve` checks only `moderation_report is None`, so a
  mock-moderated book **can be published**, and the reviewer sees only a "Not independently
  reviewed" badge among four badges plus one row in the structural-findings block.
- **Why it matters for the goal**: this is the one configuration in which the automated layer is
  entirely absent, and it is exactly the configuration a staging-to-production misconfiguration
  produces.
- **Recommendation**: make `approve` refuse any version whose report carries the
  `mock_reviewer_active` concern, with an explicit admin override that writes its own event. The
  stamp already exists and is reliable; only the check is missing.
- **How to check I'm right**: read `_stamp_mock_reviewer` and then `grep -n "mock_reviewer_active"
  src/cyo_adventure/publishing/`, no hits.

---

## What is genuinely strong, and should not be traded away in fixing the above

Stated so remediation does not regress it:

- **The publish choke point is real.** `publishing/service.py::approve` is the sole writer of
  `status="published"` in `src/`, it re-checks `is_admin` at the service boundary independently of
  its callers, it holds the row under `SELECT ... FOR UPDATE`, and it stamps `approved_by` and
  `published_at` atomically with the transition. No pipeline code path writes `published`.
- **Fail-safe discipline in the stages is consistently correct.** Stage-1 parse failure, a
  non-`Completion` return, a non-str `text`, a duplicate `node_id` in a batch, a partially-matching
  batch, a non-finite classifier score, and a malformed provider response shape each route to
  `FLAG` or to a degraded/coverage finding rather than to a silent pass. The
  `classifier_coverage_incomplete` **FLAG** (not advisory) is the right severity for
  "we did not look at most of this book".
- **Prompt-injection hardening is thorough**: instruction-hierarchy suffix on every stage prompt,
  `<untrusted_passage>` delimiters, delimiter-token escaping, and node-id label sanitisation
  outside the delimited zone (with a deliberate fall-back to per-node fail-safe when an id will not
  round-trip).
- **PII egress control is wrapper-enforced, not call-site discipline**: `PiiGuardedProvider` wraps
  the review provider outermost, and the classifier path (a separate egress) gets its own explicit
  `assert_prompt_pii_safe` loop.
- **The event log's PII-free payload contract is enforced by a per-event-type key allowlist**, not
  by convention.
- **The self-assessment culture is unusually good.** `adversarial-safety-evaluation.md` refuses to
  treat a mock run as evidence and unchecked its own project-plan checkbox; `blind_spots.py` exists
  to stop a gate's silence reading as a pass; `classifiers.py` documents the refutation of its own
  floor rather than deleting it. Several findings above are things the project found first and has
  not yet scheduled. The defect is throughput on the safety backlog, not blindness.

## Suggested order

1. **C4-8** (wire `screen_for_review`, ~15 lines) and **C4-9(a)** (edge-set identity check,
   ~5 lines), hours of work, immediate coverage.
2. **C4-2** (block-override guard + forced re-moderation on resubmit) and **C4-17**, days, and
   they close the two paths where the machine's hardest verdict is silently discardable.
3. **C4-13** (configure secrets, run the harness), unblocked today, and it is the prerequisite for
   any defensible statement about C4-10.
4. **C4-1** (path-safety pass over `covering_paths`) and **C4-3** (path-based review surface),
   the same change from two ends; do them together.
5. **C4-12** (the S-5 floor) before the next shell-supply expansion, not after.
