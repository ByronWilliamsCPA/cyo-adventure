# A3 fresh-eyes: editorial and QA standard (goal-only, no brief or repo access)

# Editorial and QA Standard for Branching Children's Books

Fresh-eyes control specification, written from first principles of children's publishing, interactive-fiction craft, and developmental reading. No repository material consulted. Numeric bars are calibrated defaults a serious publisher would start from and tune with evidence; they are written as [bar: ...].

Band shorthand used throughout: **B1** = 3-5 (pre-reader, read-aloud), **B2** = 6-8 (early reader), **B3** = 9-12 (middle grade), **B4** = 13-15 (younger YA), **B5** = 16+ (older YA).

---

## 0. Scope, definitions, governing principles

- 0.1 Unit definitions: node (one passage), decision point (node ending in options), edge (one option), path (root-to-ending traversal), merge (node with 2+ inbound edges), state (flags/items/relationships carried across nodes), ending (terminal node).
- 0.2 Two gates, never conflated: the safety gate (binary, child-protective, zero tolerance) and the quality gate (graded, editorial). A book can be perfectly safe and still unpublishable because it is dull, unfair, or condescending.
- 0.3 Design intent precedes generation: every book has a one-page intent doc (band, theme, tone, agency profile, ending mix targets, scare ceiling, representation notes). QA scores against intent, not against rater taste.
- 0.4 The reader's dignity principle: the book may surprise, scare (within band), and defeat the reader; it may never mock, shame, or trick the reader for having trusted the text.
- 0.5 The central economics fact: paths grow exponentially, but nodes and edges grow linearly. All human QA is therefore organized per-node, per-edge, and per-merge, plus a bounded set of full-path walks. Review effort scales with edges, not paths.
- 0.6 Design-for-reviewability is an editorial requirement, not an engineering nicety: books must be commissioned within verifiable complexity budgets (see 14.3.12) or they cannot be honestly approved by a human.

---

## 1. Per-band product norms

### 1.1 B1 (3-5, read-aloud / pre-reader)
- Path 150-500 words; node 15-60 words; whole book 300-1,500 words.
- 2 options per decision, always pictured; 2-4 decisions per path; [bar: first decision within 100 words].
- Agency type: participatory and expressive ("which hat?", "make the sound"); the next page must visibly honor the pick.
- Consequences: immediate, visible, benign, reversible.
- Endings: 2-4, all warm and settling (home, hug, sleep, snack); no failure endings at all; "uh-oh" beats resolve before any ending.
- Scare ceiling: brief dark, brief separation, silly monsters; resolved within one to two spreads; never end a page session on fear.
- Language: read-aloud rhythm, refrains, present tense welcome, high-frequency vocabulary; guardian co-reading assumed.
- Illustration: every node; choices depicted as pictures; tap targets picture-first.

### 1.2 B2 (6-8, early reader)
- Path 600-2,500 words; node 40-120 words.
- 2 options standard, 3 rare; 4-7 decisions per path; [bar: first decision within 250 words].
- Agency type: tactical (how do we solve it), light moral (kind vs impulsive), curiosity.
- Endings: 4-8; [bar: at least 60% clearly positive]; failures are gentle, comic, reversible setbacks; no death of "you", ever; every failure ends with an appetizing invitation to try again.
- Scare ceiling: chases, storms, getting lost, creepy-but-cozy; peril resolved in the same scene; reassurance beat after each spike.
- Language: decodable-to-fluent transition; short sentences; heavy dialogue; humor is slapstick and wordplay.
- Illustration: every 1-2 nodes; decision spreads visually distinctive.

### 1.3 B3 (9-12, middle grade, the genre heartland)
- Path 2,500-9,000 words; node 100-300 words.
- 2-3 options; 7-15 decisions per path; [bar: first decision within 500 words].
- Agency type: strategic and moral; information-gathering choices matter; light state (items, allies).
- Endings: 6-16; mix roughly 30-50% good, 30-50% instructive failure, at most 20% hard failure; one "true/best" ending earnable by attentive single-playthrough reading; offscreen, non-graphic death permitted sparingly.
- Failure feel: earned, specific, sometimes wry; names the missed cue without lecturing; target reader reaction is "argh, I should have..." not "that's not fair".
- Scare ceiling: genuine danger, menacing antagonists, supernatural dread; no gore, no torture, no sensory description of harm to children; dread resolved within the act.
- Illustration: per scene or per decision hub; endings gallery and path map unlock post-read.

### 1.4 B4 (13-15)
- Path 6,000-20,000 words; node 200-500 words.
- 2-4 options; 10-25 decisions; relationship/reputation/values state; [bar: first decision within 900 words].
- Agency type: identity, trust, and values; delayed consequences allowed if traceable in retrospect.
- Endings: bittersweet is the sweet spot; real cost allowed; protagonist death rare, meaningful, foreshadowed, non-graphic; [bar: at least 25% of endings preserve clear hope, and a hopeful ending is reachable from every act-two state].
- Failure feel: reflective, dignified, implies a path to repair; guilt and grief allowed with support on the page.
- Scare/dark ceiling: betrayal, loss, injustice, restrained violence (aftermath over act); no glamorized self-harm, substance use, or sexualized threat.

### 1.5 B5 (16+)
- Path 10,000-40,000 words within graphs up to ~600 nodes / ~118k words; node 250-800 words.
- Full moral complexity; ambiguous and tragic endings allowed with documented intent; unreliable narration permitted.
- Still a children's/teen platform: no explicit sexual content, no gratuitous gore, no nihilism-as-house-style; hope must exist in the ending set.

### 1.6 Cross-band structural invariants
- [bar: 0 unreachable nodes, 0 dead ends that are not authored endings, 0 softlock loops, 0 endings unreachable by any choice sequence].
- [bar: branch factor 2-4; ending-to-node ratio between 1:8 and 1:40 for B3+; shortest path at least ~40% of median path length unless it is a deliberate, fully satisfying early ending].
- Band metadata must match content on every branch, not on average (see defect 15.7.5).

---

## 2. Choice design and meaningful agency

- 2.1 Choice taxonomy to design with: expressive (flavor/identity), tactical (how), strategic (which goal), moral/values, informational (investigate/ask), relational (whom to trust), pacing (press on/rest). Each book's intent doc states its intended mix; B1 skews expressive, B3 tactical/moral, B4-B5 relational/values.
- 2.2 Materiality bar: [bar: at least 70% of decision points change the immediate next scene in events, not just adjectives; at least 50% (B3+) have consequences persisting 2+ nodes; cosmetic choices at most 10% and never at moments framed as major].
- 2.3 One-unique-beat rule: every option buys at least one node of differentiated consequence before any merge. [bar: 90%+ of edges lead to a unique first child].
- 2.4 Choosability: everything needed to choose appears before the options; no essential information revealed only after the pick.
- 2.5 Distinguishable options: options differ in verb and stake, not just noun ("sneak past" vs "talk your way past", not "left" vs "right"). Blind luck picks: [bar: 0 at B1-B2; at most 1 per book at B3+, never for terminal failure].
- 2.6 Option text standards: parallel grammar, verb-first, mutually exclusive; [bar: max 8 words per option B1-B2, 12 words B3+]; option text must be the easiest text in the book (it is load-bearing).
- 2.7 No agency collapse: avoid one obviously correct option paired with a strawman ("share the cookies" vs "steal everything"); at B3+, [bar: at least 30% of decisions are true dilemmas where both options are defensible].
- 2.8 No pre-moralized labels: never mark an option as "the selfish choice" in stem or option text; judgment belongs to consequences.
- 2.9 Choice echo: the chosen action is enacted within the first sentence or two of the next node, confirming the reader was heard.
- 2.10 Desire coverage: at big moments, the two or three actions most readers will crave must be offered or explicitly acknowledged; playtest probe: "what did you want to do that you couldn't?"
- 2.11 Choices test judgment, not trivia: no options that hinge on knowledge the book never gave; no external general-knowledge gates below B4.
- 2.12 Persona-plausible options only: nothing a child protagonist of that band could not or would not do (driving, casual weapon use, adult transactions).
- 2.13 Don't punish curiosity as policy: at B1-B3, exploration mostly rewards; the worst outcomes must not systematically attach to the most inviting options.
- 2.14 No dead options: [bar: post-launch, any option picked by under 2% of readers triggers editorial review as a probable authoring failure].
- 2.15 Decision spam ban: no choices about trivia (breakfast picking) used to pad interactivity counts; every decision earns its place in stakes or characterization.
- 2.16 Consistent risk grammar: within a book (ideally the catalogue), the same class of cue signals the same class of risk, so children can learn to read the world.

---

## 3. Fairness and legibility of consequences

- 3.1 Retrospective fairness test: a reader who fails must be able to reconstruct why from text already seen. Rater probe on every failure ending: "could a child in band explain why this happened?" [bar: yes for 100% of failure endings].
- 3.2 Foreshadowing requirement: every materially bad outcome traces to a perceivable in-fiction cue (a growl, a sign, a warning) proportional to severity; authorial finger-wagging does not count as a cue.
- 3.3 Cause-to-effect distance caps: B1 same spread; B2 within 1 node; B3 within 3 nodes or an explicit callback line at payoff; B4-B5 long-range allowed with a callback at payoff ("because you pocketed the key...").
- 3.4 Proportionality: consequence severity matches signaled risk; small kindnesses never trigger catastrophe; prosocial defaults (helping, honesty) are not punished below B4, and above only with documented intent.
- 3.5 World-rule consistency: the same action under the same conditions yields consistent outcomes across branches; the dragon cannot be lethal on one path and cuddly on another without an in-fiction reason.
- 3.6 Luck quota: [bar: outcomes decided by pure chance at most 10% of decisions at B3, ~0% below, never terminal].
- 3.7 Recoverability: below B4, at least one recovery route exists after most setbacks; being wrong once is rarely fatal to the playthrough.
- 3.8 Best-ending fairness: the top ending is reachable by attentive reading and fair inference on a single playthrough (B1-B3); never gated on exhaustive search or luck, unless the book is explicitly framed as a re-read puzzle.
- 3.9 No mind-reading: success must not require guessing an unstated authorial preference between two equally signaled options.
- 3.10 Fairness telemetry proxy: [bar: post-launch, back-button/retry spikes immediately after an outcome node flag it for a perceived-unfairness review].

---

## 4. Pacing and structure

- 4.1 Time-to-first-decision bars (words from story start, front matter minimized): B1 100, B2 250, B3 500, B4 900, B5 1,200. The first decision must already matter (not "wake up or snooze five minutes").
- 4.2 Before the first decision, establish: who you are, what you want, where you are, why it matters; nothing more.
- 4.3 Inter-decision spacing: min and max words between decisions per band [bar: B3 roughly 100-800, average 250-400]; long choiceless corridors and machine-gun choice runs both fail.
- 4.4 Node discipline: every node ends in a decision, a genuine turn (new information or reversal), or an ending. [bar: corridor nodes with none of these at most 5%].
- 4.5 Per-path arc: every path above minimal length carries setup, rising action, climax, and resolution; climax in the final third; resolution 5-15% of path length.
- 4.6 No premature climax or rushed act three: word budget by act is planned in the skeleton and checked on sampled walks.
- 4.7 Session fit: B1-B2 one path fits one sitting (5-15 minutes); B3 20-45 minutes; B4-B5 support chapter checkpoints; endings should not land mid-session-cliff for B1-B2.
- 4.8 Recap ban at pace points: nodes do not open by summarizing the previous node; momentum carries.
- 4.9 Path-length variance is designed, not accidental: any very short path is a deliberate early ending delivering a complete experience.

---

## 5. Endings: mix, tone, failure design

- 5.1 Every ending must: follow from identifiable choices; land a complete emotional beat; close this path's open threads (or leave designed ambiguity, B4+ only); be memorably distinct ("the one where...").
- 5.2 Length floors: [bar: B1 30+ words, B2 50+, B3 80+, B4-B5 150+]; no one-sentence "THE END" stubs.
- 5.3 Mix quotas by count AND by likelihood: quotas from section 1 apply to the ending list and to the play-probability-weighted distribution. [bar: a first-time reader making reasonable choices lands a satisfying ending at least 50% of the time at B2-B3].
- 5.4 Failure tone ladder (the feel per band): B1 none; B2 giggle, not sting ("the jam is everywhere; maybe knock first next time; try again?"); B3 earned and instructive, sometimes darkly funny, names the missed cue; B4 costly and reflective, dignity intact, repair implied; B5 tragedy allowed as craft, never as house nihilism.
- 5.5 Failure endings never: mock the reader, moralize in narrator voice, punish the reader's identity, or arrive from nowhere (see 3.1-3.2).
- 5.6 Retry affordance: B1-B3 failure endings end warm toward the retry ("you know what you'd do differently"), and the app's back-to-fork flow is part of the authored experience.
- 5.7 No agency-erasing trick endings ("all a dream" as punishment) except as designed comedy or a declared motif.
- 5.8 Ending distinctness: [bar: no two endings that are paraphrases; automated similarity screen plus the human endings pass, 14.1.4].
- 5.9 One "true/best" ending at B3+ rewarding attentiveness; its gate obeys 3.8.
- 5.10 Final-image hygiene: B1-B2 endings never leave a frightening last image (the bedtime test).
- 5.11 Endings-gallery labels: memorable, spoiler-safe names for collection UIs.
- 5.12 Early endings are legitimate design (classic to the genre) but must be consequence-endings, not content shortage, and must obey the length and tone floors.

---

## 6. Emotional stakes and scary-content calibration

- 6.1 Stakes must be personal and concrete below B4 (save the dog, find your sister), not abstract (save the economy).
- 6.2 Fear requires attachment: establish at least one relationship the reader cares about before threatening anything.
- 6.3 Scare shape: build, peak, release; release within 1-2 nodes at B1-B2, within the scene at B3, within the act at B4-B5; below B4 never end a path on unresolved dread.
- 6.4 Scares are steerable: frightening sequences are telegraphed so a spooked reader can choose away; [bar: B1-B3, every scary sequence has a lower-intensity chooseable route (the "flashlight path")].
- 6.5 Ceiling by band as in section 1; additionally, calibrate fear to the sensitive quartile of the band, comprehension to the median.
- 6.6 Uniform ceiling across ALL branches: the scare ceiling applies to the rarest path exactly as to the modal path; a heatmap of per-node intensity is reviewed for spikes in low-traffic regions.
- 6.7 Absent adults, safe world: adventure requires adult absence, but below B4 the world must not read as systemically unsafe; trusted help exists or is plausibly offstage.
- 6.8 Sad content is welcome with support: loss, moving, pet death (gently from B2-B3 up) require named feelings, modeled coping, and a supporting relationship on the page.
- 6.9 Hard bans at all bands (safety gate, not a style question): graphic violence/gore, sexual content, self-harm methods or ideation modeling, substance instruction or glamor, abuse framed approvingly, grooming dynamics framed positively, hate speech, weapon how-to, dangerous imitable acts rewarded or consequence-free.
- 6.10 Imitability review: any act a child could copy (hiding places, eating found things, approaching animals, online contact, dares) is checked across every branch where it appears for how the outcome frames it.
- 6.11 Crisis-adjacent content (bullying, grief, family conflict) appears only with design intent, in-fiction support, and accurate guardian-facing content notes.
- 6.12 Villain interiority scales: B1 villains are silly or scared themselves; B2-B3 defeasible and motivated; B4+ may be genuinely disturbing but never sadistically detailed.

---

## 7. Re-readability and the second playthrough

- 7.1 Divergence value bar: [bar: choosing differently at the first major fork yields at least 50% new prose at B3+, at least 30% at B2]; B1 is exempt (repetition is the point; variation is a garnish).
- 7.2 Structural, not cosmetic, variety: [bar: B3+ books have at least two structurally distinct middle acts, not one trunk with different final paragraphs].
- 7.3 Early meaningful divergence: at least one act-one choice changes the middle act substantially.
- 7.4 Cross-path recontextualization: plant details that read differently with other-path knowledge (the locked door whose key story you now know); foreshadow one path's reveal in another path's background.
- 7.5 Knowledge transfer is a treat, not a toll: re-read knowledge should feel clever to apply and must never be required for a good first read.
- 7.6 Completionist scaffolding at B3+: visible endings count, spoiler-safe endings gallery, post-completion path map, optional collectibles; none of it nags.
- 7.7 Memorable forks: decision points are written to be findable from memory ("the cellar door choice"), supporting deliberate retry.
- 7.8 B1 re-read design: refrains and a choice ritual invite repetition; alternate branches carry small delights so the co-reading adult also survives read number twelve.
- 7.9 Catalogue-level re-readability: the next book must not be the same skeleton in a costume; track structural and lexical similarity across the catalogue [bar: flag any new book above a set similarity threshold to any existing one].

---

## 8. Coherence at reconvergence (merges)

- 8.1 State classes that must survive merges: inventory, injuries/conditions, knowledge/secrets, relationships and trust, NPC status (met/alive/angry), promises made, elapsed time, location, emotional tone.
- 8.2 Merge validity rule: every merge node must read true from EVERY inbound path (facts and tone), or the graph must branch on state instead of merging. [bar: 100% of merges human-checked from each inbound edge; this is linear-cost, see 14.3].
- 8.3 Merge ban list: references to unexperienced events ("as the wizard told you"), unobtained items, unmet characters greeted as friends, unsustained injuries, second meetings framed as first.
- 8.4 Tone bridging: check each merge from its worst-tone parent (one reader arrives triumphant, another shaken); the merge must work for both or be split.
- 8.5 No recap sludge: merges must not open with generic summary ("after everything that had happened..."); they continue action valid for all parents.
- 8.6 Time and geography compatibility: elapsed time, time of day, weather, and location must be reconcilable from all parents or normalized explicitly in-fiction.
- 8.7 Chekhov accounting: setups planted before a branch pay off on all paths or are gracefully released; payoffs after merges must not assume branch-only setups.
- 8.8 Reader-memory support: when a merge consequence depends on a choice made long ago, the text carries a light in-fiction cue; children should not need note-taking below B4.
- 8.9 Merge in-degree budget: [bar: typical merges have at most 3-4 parents; high-in-degree funnels need explicit state-conditional text or redesign].

---

## 9. Character, voice, and theme

- 9.1 The "you" contract: second person is the default; "you" stays band-appropriate in age, competence, and permissions; "you" is under-specified in gender/body unless deliberately designed; other characters must not gender the reader in address ("good girl") unless customization exists.
- 9.2 Consistent "you" across branches: skills, knowledge, and temperament of "you" do not mutate between paths without cause.
- 9.3 Cast size fits working memory: [bar: named characters B1 2-3, B2 3-4, B3 5-7, B4+ as needed]; every named character has a want, a voice tell, and an entry in the book bible.
- 9.4 Book bible discipline: characters, items, places, rules of magic/tech recorded once and enforced across all branches (the continuity editor's source of truth).
- 9.5 Voice distinctiveness: each book declares a narratorial stance (wry, warm, breathless) in the intent doc; raters check the book against its own stance and against house-monotone drift.
- 9.6 Dialogue differentiation: characters are tellable apart by speech alone; children do not sound like small HR adults.
- 9.7 Theme: one articulable theme per book ("courage is asking for help"); choices instantiate it; endings refract it from different angles; the narrator never sermonizes it.
- 9.8 Failure shows, never scolds: the theme's negative case is dramatized, not lectured.
- 9.9 Emotional literacy by band: B1-B2 name and normalize feelings in-scene; interiority deepens with band.
- 9.10 Antagonists have reasons at B3+; pure sadism is out below B5 and suspect even there.
- 9.11 Growth arcs exist per path: even in branching form, "you" and key companions end somewhere different from where they started on every substantial path.

---

## 10. Language and readability

- 10.1 Per-node reading-level consistency: [bar: node-level readability variance within one grade band across the whole graph; automated per-node screen, human confirmation on flagged nodes]; rare branches must not read harder than the trunk.
- 10.2 B1-B2 constraints: decodability/phonics-stage alignment where the product claims it; sentence length caps; pronoun-antecedent clarity (young readers lose referents fast); proper-noun load caps.
- 10.3 Stretch vocabulary is welcome with in-context support; [bar: a handful of stretch words per path, each scaffolded by context or picture].
- 10.4 Read-aloud QA at B1 (and B2 where narrated): an adult reads it cold aloud; stumbles, tongue-twisters, unpronounceable names, and broken scansion are defects.
- 10.5 Tense and person locked per book; present-tense second person is conventional; any deviation is a design decision, not drift.
- 10.6 Idiom hygiene at B1-B3: figurative idioms either avoided or made literal-safe (ESL readers and literal-minded children).
- 10.7 Option text obeys the band floor (see 2.6) and is never the hardest sentence on the screen.
- 10.8 Evergreen language: avoid datable slang and tech references below B4, or accept scheduled refresh cost (see 14.6.8).

---

## 11. Inclusivity and representation

- 11.1 Catalogue-level targets, book-level authenticity: representation (race/ethnicity, disability, gender, family structures, culture, class, religion, body types) is measured across the catalogue with leads, not sidekick quotas; within a book, identity is rendered with specificity, not costume.
- 11.2 Anti-stereotype checklist applied per book: villain coding (accents, disfigurement, dark-equals-evil), gendered agency patterns (who rescues, who cries, who leads), disability as villainy/tragedy/inspiration-object, poverty tropes, model-minority framing.
- 11.3 Default-demographic audit: characters left unspecified by the prompt must not silently converge on one demographic across the catalogue (see defect 15.6.4).
- 11.4 Names, foods, festivals, dress, and language snippets are accurate to the depicted culture; sacred elements are not props.
- 11.5 Sensitivity-read trigger: content centering a lived experience outside the team's competence (specific cultures, disability, adoption, grief, religion) gets a qualified sensitivity read before publication; findings are addressed or the divergence documented.
- 11.6 Helped communities have agency; no savior framing.
- 11.7 Socioeconomic texture: not every child in the catalogue has a detached house, a yard, and two devices.
- 11.8 The reader-avatar question is decided, not defaulted: "you" is either unillustrated, varied across art, or customizable; prose keeps "you" inclusive.
- 11.9 Accessibility as inclusion: dyslexia-friendly type option, screen-reader-quality alt text (see 12.8), no meaning carried by color alone in choice UI.
- 11.10 Own-voices readers in testing pools: children from represented groups notice misrenderings adult editors miss (see 14.5).
- 11.11 Localization awareness: units, school customs, and cultural references either neutral or flagged for adaptation.

---

## 12. Illustration, audio, and format hooks

- 12.1 Illustration density: B1 every node; B2 every 1-2 nodes; B3 per scene or decision hub; B4-B5 chapter art and set pieces; covers always.
- 12.2 Branch-state consistency in art: character model sheets locked; items, injuries, time of day, weather in each image must match the node's state on every inbound path; art briefs are generated from node state and checked against text.
- 12.3 Decision-page dramaturgy: the illustration at a choice depicts the dilemma without spoiling either outcome.
- 12.4 Choice UI grammar: options visually parallel, consistent placement, order randomized or neutral so position does not imply "correct"; B1 options carry pictures; tap targets meet motor-skill norms for the band.
- 12.5 A consistent visual signal marks decision moments so children recognize agency (border, panel, color).
- 12.6 Back-to-fork and map affordances are designed features: retry must feel like play, not remediation.
- 12.7 Cover honesty: cover and blurb promise the actual genre, tone, and band, and remain legible at thumbnail size.
- 12.8 Alt text is authored prose: every image gets narrative alt text matching branch state, QA'd like body text.
- 12.9 Narrated audio (if offered): pronunciation dictionary per book (invented names!), pacing per band, no jump-scare audio at B1-B3, sound never required to understand a choice.
- 12.10 Typography per band: size, leading, and line length norms; option text set larger or equal to body, never smaller.
- 12.11 Page/screen economy: a decision and its options appear together on one screen; no choice hidden below the fold.

---

## 13. Metadata, guardian trust, and rights

- 13.1 Band label accuracy is a gating check: the label must hold on every branch (the worst branch sets the label).
- 13.2 Guardian content notes: short, factual, non-alarmist ("mild peril; a pet is briefly lost; mentions of a deceased grandparent"), accurate to ALL branches including rare ones.
- 13.3 Blurbs and promised counts (endings, "over N story paths") must match the shipped graph.
- 13.4 Originality screening: plagiarism/near-duplication scan against known children's corpora and against the publisher's own catalogue; no trademarked characters, settings, or lyrics; no serial-numbers-filed-off versions of famous IP; no "in the style of [living author]" prompting.
- 13.5 Factual claims inside fiction (animal facts, history, science asides) are fact-checked like nonfiction; children's publishers get this mail.
- 13.6 Approval record: a named human approver per book version, with the signed checklist, defect log, and rubric scores stored and auditable.

---

## 14. The QA process

### 14.1 Stage gates and review order
- 14.1.1 Gate order: (G1) intent doc approved; (G2) skeleton/graph structure approved BEFORE prose fill (structure defects are cheapest here and prose QA cannot fix a broken graph); (G3) automated lint clean; (G4) editorial passes; (G5) safety review; (G6) named final approval.
- 14.1.2 Automated lint (100% of graph, every build): reachability, sinks, loops, state-flag satisfiability, choice-count and node-length rules, per-node reading level, banned-content classifiers, ending statistics, intra-book and catalogue similarity, placeholder/artifact scan.
- 14.1.3 Two human reads minimum before approval: one relational read (graph-aware, tools open) and one cold read (an editor who has never seen the book plays it twice like a reader, no map).
- 14.1.4 Mandatory endings pass: one editor reads 100% of endings as a set, checking mix quotas, tone ladder, dedupe, and length floors. Endings concentrate risk; read them together, early.
- 14.1.5 Kill criteria exist and are used: [bar: a healthy pipeline rejects or returns 5-20% of books at first pass; sustained approval above ~98% means the gate is decorative and triggers a process audit].
- 14.1.6 Two-person rule: whoever commissioned/prompted/generated the book cannot be its safety reviewer or final approver.
- 14.1.7 The safety reviewer holds unilateral block/unpublish authority, no escalation needed to stop a book.

### 14.2 Rubrics and rater consistency
- 14.2.1 Rubric dimensions (1-5, anchored): hook/premise; choice quality and agency; fairness/legibility; pacing; prose and voice; character; emotional/scare calibration; endings quality and mix; continuity/coherence; re-readability; inclusivity/representation; band fit; theme/heart. Plus binary gates: safety, structural validity, rights/IP, metadata accuracy.
- 14.2.2 Publish rule: [bar: all binaries pass; no dimension at or below 2; band fit and fairness at least 4; overall mean at least 3.5].
- 14.2.3 Anchors are exemplars, not adjectives: each scale point cites real excerpts in a versioned anchor pack; anchors refreshed quarterly, seeded with recent escaped defects and recent triumphs.
- 14.2.4 Evidence requirement: any score of 1-2 or 5 must cite node IDs and quotes; "vibes" scores are returned.
- 14.2.5 Calibration mechanics: onboarding raters score a gold set before rating live [bar: within-1-point agreement at least 85% to qualify]; monthly whole-team calibration on a shared node set with adjudicated discussion.
- 14.2.6 Ongoing reliability: [bar: 15% of books blind double-rated; weighted kappa at least 0.6; per-rater drift dashboards; covert gold items reinserted into normal queues to detect fatigue].
- 14.2.7 Disagreements adjudicated by a senior editor with written rationale that feeds back into anchors.
- 14.2.8 Separate taste from standard: raters log personal-taste reactions in a distinct field so the rubric measures the standard.
- 14.2.9 Fatigue caps: [bar: at most 4-5 hours of rubric rating per rater per day; annotation-speed floors and ceilings monitored].
- 14.2.10 Defect severity taxonomy used in all logs: S0 safety (block, incident review), S1 breaks story or graph (block), S2 breaks scene or trust (fix pre-publish), S3 polish (fix if budget); every defect carries node IDs and a suspected pipeline stage.
- 14.2.11 Rubric validity check: rubric scores are periodically correlated with child-testing behavior and post-launch telemetry; dimensions that predict nothing get redesigned.

### 14.3 Sampling strategy for large graphs (nobody reads all paths of a 600-node book)
- 14.3.1 Organizing principle: paths are exponential; nodes, edges, and merges are linear. Guarantee linear-cost coverage exhaustively, then spend a bounded budget on full-path walks for arc-level qualities only walks can reveal (pacing, tone accumulation, fatigue).
- 14.3.2 L0 machine coverage: 100% of nodes and edges linted every build (see 14.1.2). Machines read everything; humans sample paths but not nodes.
- 14.3.3 L1 human node coverage: [bar: 100% of nodes read by a human, in adjacency units: the decision stem plus ALL its options plus each option's first child read together as one unit]. This is the native editing unit of the genre; isolated node-card reading is non-compliant.
- 14.3.4 L1 merge coverage: [bar: 100% of merge nodes read once per inbound edge, including from the worst-tone parent]; linear cost, catches most continuity defects.
- 14.3.5 L2 walk set (full playthroughs), minimum composition: the modal path (highest expected choice probabilities); every ending reached at least once via its most probable inbound route; extremal walks (longest, shortest, highest cumulative scare score, most state-laden); [bar: 3-5 persona walks: the cautious reader, the kind reader, the chaos reader, the completionist]; 2-3 random walks. [bar: union of L1+L2 covers 100% of edges].
- 14.3.6 Equal per-node rigor regardless of traffic: rare branches get the same scrutiny per node as the trunk; children exhaustively hunt rare branches, and generation quality is usually WORST there (tail-risk inversion).
- 14.3.7 L3 state audit: automated simulation of flags/items along all walks plus human spot-reads of the top state-divergent merges.
- 14.3.8 L4 cold read: see 14.1.3; the cold reader files an experience report (where bored, where confused, where delighted), not a defect list.
- 14.3.9 Endings pass: see 14.1.4, 100% of endings, always.
- 14.3.10 Dirty-subgraph re-review: any changed node re-read with parents and children; any changed choice or flag re-walks affected routes; L0 re-runs fully; safety re-gates on any change touching scare, values, or representation content.
- 14.3.11 Worked budget (600 nodes, ~118k words, ~200 words/node): L1 at ~150 wpm annotated is ~13-16 hours; merge multi-entry and walk overlap add ~40-60%; endings pass, continuity audit, copyedit, safety, cold reads on top. All-in [bar: 45-75 review minutes per 1,000 words for branching text, roughly 2-3x linear-book cost], so the largest books cost ~90-150 person-hours of QA. If unit economics cannot afford that, commission smaller graphs or lower state complexity; do not thin the floor.
- 14.3.12 Design-for-reviewability budgets at commissioning: [bar: at most 6-8 independent state flags per book; merge in-degree at most 3-4; act-local state preferred over global], keeping human verification linear and honest.

### 14.4 Editor roles and time budgets
- 14.4.1 Roles (combinable in small teams, except where independence is required): structural/commissioning editor (intent doc, skeleton gate); line editor (L1); continuity editor, the branching specialist (merges, state, timeline, book bible); copyeditor/proofreader (frozen text, last); endings editor (14.1.4, often the structural editor); sensitivity reader (triggered, external as needed); fact checker (triggered); art director (12.2-12.5); audio director (if narrated); safety reviewer (independent); final approver (named, accountable); QA analyst (telemetry, sampling design, rater reliability).
- 14.4.2 Independence: generator/prompt-owner never safety-reviews or approves own book; no same-day line-edit-and-approve by one person.
- 14.4.3 Indicative all-in budgets: B1 small book ~1 editor-day; B3 mid book (20k words, ~100 nodes) ~3-4 editor-days; B5 flagship (600 nodes, 118k words) ~12-18 person-days across roles.
- 14.4.4 Throughput hygiene: [bar: at most ~25-30k words per reviewer per day with annotation before quality collapses]; QA minutes per 1,000 words is a tracked health metric, and a falling number is an alarm, not a win.
- 14.4.5 Approval mechanics: the approver verifies the defect log is closed (not merely read), all gates passed, and signs the stored record (13.6).
- 14.4.6 Reviewer tooling is an editorial requirement: graph visualization, adjacency reading mode (stem + options + children on one screen), state simulation/trace, per-node scare and reading-level heatmaps, diff-scoped re-review queues.

### 14.5 Reader testing with real children
- 14.5.1 What it CAN tell you: choice comprehension (can the child restate the options and why they picked); outcome comprehension [bar: at least 80% correct on "why did that happen?" probes]; engagement (asks to continue, accepts the re-read offer); emotional calibration (observed affect: leaning in vs distress); appeal of premise/cover; UI usability; read-aloud rhythm (B1: does the guardian stumble; does the child pre-empt the refrain); which options children crave (2.10).
- 14.5.2 What it CANNOT tell you: rare-path defect discovery (children traverse 1-3 paths); safety certification (no distress in n=8 is not "safe"); statistical winners between close variants at small n; honest verbal negatives (children please adults: weight behavior over words); representativeness beyond your recruiting network; long-term appeal.
- 14.5.3 Protocols by band: B1 guardian-child read-aloud observation (note pointing, grabbing, pre-empting, wriggling); B2-B3 individual think-aloud with neutral prompts, choice-reason probes, retell-to-a-friend, and the behavioral re-read offer; B4-B5 silent read plus interview and a one-week diary re-read.
- 14.5.4 Ask "what would you cut?" and "what did you want to do that you couldn't?": children answer cut and desire questions more honestly than "did you like it".
- 14.5.5 Sampling: [bar: 5-8 children per band per book-class/template per quarter, plus spot tests of individual risky books]; rotate the panel to avoid training expert testers; include own-voices readers (11.10); calibrate fear findings to the sensitive quartile (6.5).
- 14.5.6 Ethics floor: guardian consent plus child assent; stop-anytime honored instantly; comfort protocol and incident log for any distress [bar: any fear-driven stop at B1-B3 is an automatic content escalation]; data minimization (no retained recordings beyond coding; children's-privacy law compliance); children are never used as the red team for safety-marginal content: fix first, then test.
- 14.5.7 Findings feed the rubric: child behavior recalibrates anchors and quotas (14.2.11); a rubric that outguesses the kids is measuring the wrong thing.

### 14.6 Post-publication complaint and revision loops
- 14.6.1 In-product signals: kid-simple and guardian flag buttons on every node; flags auto-attach node ID, book version, and path trace so triage starts with the evidence.
- 14.6.2 Telemetry as QA (aggregate, privacy-safe): choice pickup distributions (dead options, 2.14); quit-point clustering [bar: top-decile quit nodes reviewed]; back-button spikes after outcomes (3.10); ending-reach distribution vs design intent [bar: over 2x drift from intent triggers structural review]; re-read and completion rates by band; node dwell-time outliers (confusion or boredom).
- 14.6.3 Complaint taxonomy: safety; scare overshoot; values/ideology; representation harm; unfairness; quality (boring, confusing); band mislabel; technical (dead end, state bug). Each mapped to severity S0-S3.
- 14.6.4 SLAs: [bar: S0 quarantine/unpublish within hours, investigate after, notify affected guardians; S1 fix within days; S2-S3 batched into scheduled revisions].
- 14.6.5 Values complaints vs harm: differentiate "this family's values differ" (answered with accurate content notes and choice, 13.2) from harm (answered with change); do not bowdlerize the catalogue to the most easily offended complaint.
- 14.6.6 Versioning discipline: books are versioned with changelogs; a child mid-book keeps a coherent version or is migrated gracefully; any content change re-passes the safety gate and dirty-subgraph QA (14.3.10); art, audio, and alt text re-sync with text.
- 14.6.7 Learning loop: every S0/S1 escape is root-caused to a pipeline stage (skeleton, prompt, generation, validator, rubric, sampling) and produces a durable change (new lint rule, new anchor, new prompt constraint), reviewed monthly against the defect taxonomy.
- 14.6.8 Scheduled re-review: every catalogue title re-screened on policy updates and refreshed on an 18-24 month cycle (language dating, evolving norms, classifier improvements).

---

## 15. What an LLM pipeline characteristically gets wrong in this genre

Concrete defect types editors must actively hunt. Automated screens help with many; the meaning-level ones are human work.

### 15.1 Graph and structure defects
- 15.1.1 Illusory branching: options lead to near-paraphrase continuations; agency exists only in the UI.
- 15.1.2 Instant reconvergence: every branch snaps back to the trunk within one node; middles identical regardless of choices.
- 15.1.3 Choice-label mismatch: option says "sneak past the guard", next node has you fighting him.
- 15.1.4 Option-child misbinding: outcome text responds to a different option than the one picked (off-by-one wiring).
- 15.1.5 Rushed leaves: terminal nodes shrink to a sentence or two; the model runs out of steam at the graph's edges.
- 15.1.6 Depth decay: specificity, band fit, and craft degrade with graph depth and rarity; rare branches read like first drafts.
- 15.1.7 Deus ex machina funnels: forced rescues and coincidences invented to drag divergent branches back to a merge.
- 15.1.8 Loop illiteracy: cycles replay text verbatim with no acknowledgment, or create softlocks.
- 15.1.9 Difficulty inversion: cautious, well-signaled options accidentally lead to worse outcomes because moral framing was applied inconsistently across branches.
- 15.1.10 Orphaned Chekhov guns: setups (key, prophecy, wound) that pay off on no path, or payoffs firing on paths that lack the setup.
- 15.1.11 Premature climax: the big confrontation lands mid-book on some paths, leaving a long flat tail.

### 15.2 Continuity and state defects
- 15.2.1 Memory bleed: a node references items, characters, or events from a sibling branch the reader never saw ("as the wizard warned you").
- 15.2.2 State amnesia: the rope you took is gone when needed; the lantern you never took is in your hand.
- 15.2.3 Double introduction: a character introduced as a stranger twice on one path, or greeted as an old friend at first meeting.
- 15.2.4 Timeline scramble: night/day flips, "later that morning" after dusk, impossible travel times, inconsistent ages and dates.
- 15.2.5 Geography drift: rooms and exits rearrange; you leave a cellar onto a rooftop.
- 15.2.6 Condition amnesia: the sprained ankle sprints; the soaked clothes are dry mid-scene.
- 15.2.7 Resurrection bugs: a character lost on THIS path reappears without explanation.
- 15.2.8 Merge genericity: reconvergence nodes written as vague, tone-flattened recap sludge ("after everything that had happened...") to fit all parents.
- 15.2.9 Tone whiplash at merges: triumphant and traumatized inbound paths dumped into the same cheerful next scene.
- 15.2.10 Rule-of-magic drift: the amulet does whatever the local branch needs; world rules mutate across branches.

### 15.3 Prose and voice defects
- 15.3.1 Register creep: vocabulary and syntax drift above band, especially deep in the graph; per-node reading-level spikes.
- 15.3.2 Tic phrases at genre density: "you can't help but", "little did you know", "a wave of relief washes over you", "with newfound determination", "heart pounding", "suddenly" clusters. [bar: per-book tic frequency caps enforced by lint plus ear].
- 15.3.3 House monotone: every book and every character in the same rhythm; catalogue-level sameness across titles.
- 15.3.4 Name/imagery monoculture: the same names (Luna, Max, Willow...), foods, and settings recurring across the catalogue from model priors.
- 15.3.5 Recap compulsion: nodes open by summarizing the previous node because each node was generated quasi-independently.
- 15.3.6 Person and tense wobble: second person slips to third or first; present/past flips at branch seams.
- 15.3.7 Empty vividness: abstract emotion words in place of concrete sensory detail; or fake specificity lavished on irrelevancies.
- 15.3.8 Moral-of-the-story appendage: unbidden final-line sermons ("and that's why honesty matters!") at bands they patronize.
- 15.3.9 Positivity flattening: conflicts dissolve instantly, everyone apologizes, villains reform in a line; no tension survives a node boundary.
- 15.3.10 Safety-hedging leakage: characters flinch from all risk ("maybe we shouldn't; it could be dangerous!"), gutting adventure; assistant-brain caution wearing a costume.
- 15.3.11 Dialogue sameness: all ages and species speak in the same polite adult register.
- 15.3.12 Pattern commitment decay: refrains, rhyme schemes, or motifs established early silently vanish in later or rare nodes; B1 verse breaks scansion.
- 15.3.13 Format artifacts: leaked headings, node IDs, markdown, placeholder tokens, prompt echoes ("As requested..."), instruction vocabulary inside prose ("age-appropriate").
- 15.3.14 Cliché furniture: chosen-one prophecy, glowing amulet, wise old owl, dream ending, "the real treasure was friendship" as default cadence.
- 15.3.15 TTS/read-aloud traps: unpronounceable invented names, homograph ambushes, tongue-twisters in narrated bands.

### 15.4 Choice-specific defects
- 15.4.1 Strawman dilemmas: one obviously right option plus a cartoonishly bad one; agency collapses to compliance.
- 15.4.2 Pre-judged options: option text morally labels itself ("be selfish and grab it").
- 15.4.3 Blind-choice spam: "left / right / straight" with no cues anywhere, repeatedly.
- 15.4.4 Duplicate options: two options that mean the same thing in different words.
- 15.4.5 Spoiler options: option text reveals the outcome ("open the door and get captured").
- 15.4.6 Knowledge-gated options: choices hinging on facts the book never provided or on adult general knowledge.
- 15.4.7 Persona-impossible options: actions the band's protagonist could not or would not take.
- 15.4.8 Trivia decision spam: interactivity padded with stakeless micro-choices.
- 15.4.9 Slow echo: after a pick, the next node dawdles before enacting the chosen action, or quietly enacts a different one.
- 15.4.10 Option-count drift: four and five options appearing at bands specified for two.

### 15.5 Ending defects
- 15.5.1 Ending sameness: all endings restate one moral in one cadence; near-duplicate endings.
- 15.5.2 Path-blind endings: generic ending text that forgets which route led there.
- 15.5.3 Tone-quota drift: failure endings harsher (or blander) than band tone ladder; shaming language in defeat.
- 15.5.4 Abrupt stubs: one-sentence endings after long buildups (see 15.1.5).
- 15.5.5 Unearned tragedy: death or loss dropped in casually for drama at bands requiring preparation and support.

### 15.6 Safety, values, and representation defects (the subtle ones filters miss)
- 15.6.1 Tail-risk concentration: the most frightening or least appropriate content sits in low-probability branches where generation context was thinnest and review attention lowest.
- 15.6.2 Imitable hazards modeled neutrally or rewarded on at least one branch: hiding in appliances, eating found berries, approaching strays, meeting online strangers, dares.
- 15.6.3 Internal safety-logic contradiction: one branch teaches "trust the helpful stranger" while another punishes it; the book's own safety lessons disagree.
- 15.6.4 Stereotype seepage: villain accents and coded names, gendered rescue patterns, disability as obstacle or inspiration, homogeneous defaults for unspecified characters.
- 15.6.5 Scare-intensity variance: band-appropriate modal path, nightmare fuel on a rare branch (calibration failed to propagate).
- 15.6.6 Ideological freelancing: the model inserts its own didactic frames and generic virtue sermons misaligned with the book's designed theme.
- 15.6.7 Crisis content mishandled: bullying, grief, self-harm-adjacent despair introduced without design intent, in-fiction support, or accurate content notes.
- 15.6.8 Romance drift: age-inappropriate romantic or body-focused content creeping into low bands.
- 15.6.9 Age-inappropriate autonomy: children depicted doing adult things (driving, drinking coffee at midnight in a bar) as unremarkable.

### 15.7 Facts, rights, and metadata defects
- 15.7.1 Confabulated facts: wrong animal/science/history "facts" delivered in the trusted voice of a children's book.
- 15.7.2 IP contamination: trademarked characters and settings, recognizable lyrics, or filed-off famous properties; art in a branded style.
- 15.7.3 Cultural misrender: mashed languages and customs (a Spanish phrase in a Japanese-set scene), sacred items as set dressing.
- 15.7.4 Arithmetic and counting errors: three tasks announced, two delivered; ages and dates that don't add up; "all four friends" when one left two nodes ago.
- 15.7.5 Metadata drift: band label, blurb, ending counts, or content notes that don't match the shipped graph (especially its rare branches).
- 15.7.6 Alt-text divergence: image descriptions contradicting branch state or spoiling outcomes.

---

## The 10 mistakes teams most often make here

1. **Approval theater.** The human gate exists but approves ~100% of books at a review speed faster than reading speed. If there is no kill rate, no named approver, and no time floor, the policy is decorative exactly where the company promised it wasn't.
2. **Reviewing nodes as cards instead of relations.** QA reads passages in isolation and misses everything the genre actually is: stem-options-children units, merge validity from every parent, and consequence linkage. The defects live between nodes, not inside them.
3. **Modal-path myopia.** Attention gets allocated by expected traffic, so rare branches, where LLM quality is worst and children absolutely will go, ship with the least scrutiny. Per-node rigor must be uniform; tail branches need more suspicion, not less.
4. **Age-banding by vocabulary only.** Teams scale the same graph shape and stakes with simpler words. Bands need different agency types, decision cadence, ending mixes, failure tones, and scare ceilings, not a reading-level slider.
5. **Interactivity metric inflation.** Node counts, choice counts, and ending counts become the KPI, so the pipeline optimizes into fake agency, paraphrase branches, and thin endings. Measure materiality (differentiated consequence), not volume.
6. **Safety review crowding out quality review.** Everything is screened for harm, nothing for delight, and the catalogue converges on safe, flat, forgettable books. A children's publisher's real bar is "would a child beg to re-read this", and it needs its own gate.
7. **Rubric rot.** Unanchored 1-5 scales, no double-rating, no drift monitoring; within months every book is a polite 4 and the rubric stops discriminating. Anchored exemplars, blind duplicates, kappa targets, and evidence-cited scores are not optional.
8. **Misusing child testing.** Either skipping children entirely (adults guessing what is fun or scary), or treating eight kids' smiles as statistical validation and safety certification. Small-n child testing is a discovery lens for comprehension, desire, and calibration, never a gate by itself, and children are never the red team.
9. **Whack-a-mole defect fixing.** Editors hand-patch each instance of memory bleed or register creep and never root-cause to the pipeline stage, so the same defect returns in every book forever. Every escaped S0/S1 must end as a validator rule, prompt constraint, or anchor update.
10. **Publish-and-forget.** No telemetry-to-editorial loop, no complaint taxonomy with SLAs, no versioned re-approval on revision, no catalogue-level monitoring of sameness and representation. The catalogue silently rots, and the team never learns which of its rubric scores actually predicted real children's behavior.
