---
schema_type: planning
title: "Research Notes: Choice Agency, Pacing, Reading Rates, and Fail States by Age"
description: "Committed, citable academic research base for the ADR-011 constants: choice design and
  perceived agency, children's interactive e-book evidence, reading-rate norms by age, failure and
  persistence by age, and branching-structure/replay research. Rebuilt 2026-08-02 to replace the
  never-committed docs/planning/research/ originals."
tags:
  - planning
  - research
  - storybook
status: active
owner: core-maintainer
authors:
  - name: "Claude (research rebuild, branch claude/story-structure-diversity-ba8swy)"
purpose: "Give ADR-011's pacing, choice-count, fail-state, and reading-speed constants a re-examinable
  evidence base with graded sources, and record explicitly where the literature is silent so unanchored
  constants are labeled as designer priors rather than research."
component: Strategy
source: "External literature pass, 2026-08-02: Consensus, Scholar Gateway, and Tavily/web searches.
  Every claim carries its source; evidence graded STRONG (meta-analysis / replicated / preregistered),
  MODERATE (well-cited or convergent studies), WEAK (single small study, theory piece, gray literature)."
---

# Research Notes: Choice Agency, Pacing, Reading Rates, and Fail States by Age

Companion note: [cyoa-structure-measurements.md](cyoa-structure-measurements.md) covers the structural
side (the Ashwell taxonomy and published CYOA/gamebook measurements). This note covers the human side.
See the README in this directory for provenance and the relationship to ADR-011's original citations.

## 1. Choice design and agency

### 1.1 The choice poetics framework (WEAK to MODERATE: theory plus small generator experiments)

Mawhorter, Mateas, Wardrip-Fruin and Jhala formalize a choice as framing + options + outcomes evaluated
against player goals ([Towards a Theory of Choice Poetics, FDG 2014](http://www.fdg2014.org/papers/fdg2014_paper_19.pdf)),
operationalized in the Dunyazad generator ([ICCC 2015](https://computationalcreativity.net/iccc2015/proceedings/13_4Mateas.pdf))
and matured in [Choice Poetics by Example](https://eis.ucsc.edu/papers/ChoicePoeticsByExample.pdf)
(Arts 7(3):47, 2018, DOI 10.3390/arts7030047). Named idioms: obvious choice, relaxed choice, dilemma,
flavor choice, dead-end option, false choice, unchoice. Key claim: flavor choices are legitimate when
the reader can tell expression is the point; they poison trust only when dressed up as consequential.
Not child-tested; no age-differentiated version exists.

### 1.2 Agency is perceived, not mechanical (MODERATE: convergent across ~6 independent studies)

- [Agency Reconsidered](https://eis.ucsc.edu/papers/nwf-C7-digra09-agency.pdf) (Wardrip-Fruin, Mateas,
  Dow and Sali, DiGRA 2009, DOI 10.26503/dl.v2009i1.369): agency arises when the actions players desire
  are among those they can take; it is a designed alignment, not raw freedom or branch count.
- [Achieving the Illusion of Agency](https://link.springer.com/chapter/10.1007/978-3-642-34851-8_11)
  (Fendt et al., ICIDS 2012, DOI 10.1007/978-3-642-34851-8_11): a non-branching story whose choices
  were followed only by explicit textual acknowledgment sustained perceived agency comparable to real
  branching. Acknowledgment feedback, not structural divergence, carries much of perceived agency.
- Cardona-Rivera et al., Foreseeing Meaningful Choices (AIIDE 2014, n=88): players report higher agency
  when options are foreseen to lead to situationally different states; options differing only in
  non-situational flavor produced lower agency. The boundary condition on Fendt: anticipated difference
  at the moment of choosing matters even if the eventual difference is modest.
- Iten, Steinemann and Opwis (CHI 2018): choices feel meaningful when moral, social, and consequential;
  meaningful choices increased appreciation and narrative engagement more than raw enjoyment.
- [Kway and Mitchell](https://link.springer.com/chapter/10.1007/978-3-030-04028-4_23) (ICIDS 2018,
  qualitative): perceived agency from expressing the character within constraints plus the system
  visibly recognizing that expression, even with no lasting consequences.
- [Green and Jenkins](https://onlinelibrary.wiley.com/ai/10.1111/jcom.12093) (J. Communication 2014,
  DOI 10.1111/jcom.12093): interactive narratives reliably produce stronger felt responsibility for
  outcomes than linear ones; each decision point spawns counterfactual thinking that amplifies emotion,
  especially after negative outcomes.
- Failure mode: players lose interest when choices are exposed as cosmetic (Cao 2025 survey; the
  Bandersnatch case study, H. Zhang 2023; Kuo, Hiler and Lutz 2016, DOI 10.1002/cb.1620). WEAK
  individually, convergent as a set.

### 1.3 Rewind and backtracking (MODERATE)

Kleinman's line ([ICIDS 2016](https://link.springer.com/chapter/10.1007/978-3-319-48279-8_32);
[FDG 2018, DOI 10.1145/3235765.3235773](https://dl.acm.org/doi/10.1145/3235765.3235773);
Entertainment Computing 2020, ScienceDirect PII S1875952117301167; cited text-only because Elsevier
rejects non-browser link checks)
taxonomizes rewind (Restricted / Unrestricted / External) and finds rewind-as-mechanic can support
rather than destroy narrative experience; empirical data remain thin. Companion:
[Mitchell, ICIDS 2020](https://link.springer.com/chapter/10.1007/978-3-030-62516-0_15) on repeat
experience and resistance to closure. The app's one-step Go back and the A13b ending-screen affordance
are both inside the well-precedented Restricted Rewind class.

### 1.4 Choice frequency and density: the literature is nearly SILENT

The only direct experiment found:
[Moser and Fang](https://www.tandfonline.com/doi/abs/10.1080/10447318.2014.986639) (IJHCI 2015,
DOI 10.1080/10447318.2014.986639): branching structure and more salient decision points each improved
enjoyment and engagement. Adults, single game, viewing-based. No academic source prescribes choices
per minute, per N words, or tap pacing for any age group, and none exists for child readers.
Anything the app codifies here is an engineering judgment anchored on proxies and must be tagged so.

## 2. Interactive and enhanced e-books for children (ages ~2-8)

### 2.1 Meta-analytic core (STRONG)

- Takacs, Swart and Bus (Review of Educational Research 2015, DOI 10.3102/0034654314566989; 43 studies,
  n=2,147): story-congruent multimedia helps comprehension (g+ 0.17) and vocabulary (g+ 0.20);
  interactive elements (hotspots, games, dictionaries) distract, and are detrimental for disadvantaged
  children.
- Furenes, Kucirkova and Bus (RER 2021, DOI 10.3102/0034654321998074; 39 studies, n=1,812, ages 1-8):
  digitization alone lowers comprehension vs paper; with story-congruent enhancements digital wins;
  adult mediation of print beats unmediated enhanced digital.
- Bus et al. (Early Education and Development 2025; 20 articles, n=1,978, ages 2-8): interactive
  features' average comprehension effect near zero; mini-games negative; reader-performed actions
  mirroring the protagonist's actions positive; hotspots and inserted questions ineffective, "likely
  because both introduce pauses that disrupt the natural flow of story processing."
- Savva, Higgins and Beckmann (JCAL 2021; n=2,317, ages 3-8): e-books vs print g 0.25 for
  language/literacy overall, vocabulary 0.40, no significant difference for story comprehension.

Nuance (MODERATE): Yeari, Hadad and Korat 2023 (n=72 kindergarteners) varied interruption frequency of
story-relevant interactions and found no impairment; the poison is irrelevance, not interruption per
se. Walker et al. 2017: meaning-highlighting interactions produced large benefits for dual-language
learners.

### 2.2 Silence

No study manipulates narrative branching choices as the interactive feature in children's e-books.
Whether a plot choice behaves like a distracting hotspot or a story-congruent action for a 4- or
6-year-old is empirically open. Safest reading: a choice that mirrors the protagonist's dilemma sits on
the beneficial side of the Bus 2025 split; decorative tappables do not.

## 3. Reading-rate norms vs the per-band WPM constants

Anchors (STRONG):

- Oral reading fluency, grades 1-6: Hasbrouck and Tindal 2017
  ([ERIC ED594994](https://files.eric.ed.gov/fulltext/ED594994.pdf)); 50th-percentile spring WCPM:
  G1 60, G2 100, G3 112, G4 133, G5 146, G6 146.
- Adult silent reading: Brysbaert 2019 meta-analysis (JML, DOI 10.1016/j.jml.2019.104047; 190 studies,
  n=18,573): 238 wpm non-fiction, 260 fiction (normal range roughly 175-320); adult oral 183 wpm.
- Children's silent reading: Taylor 1965 norms (G1 80 ... G4 158 ... G12 250), with
  [Spichtig et al. 2016](https://ila.onlinelibrary.wiley.com/doi/full/10.1002/rrq.137)
  (RRQ, DOI 10.1002/rrq.137) showing today's growth curve is shallower with a grade 6-8 plateau, so
  Taylor's upper-grade numbers overestimate the modern median child.

Audit of `_READING_PACE_WPM` (`validator/band_profile.py`):

| Band | App wpm | Anchor | Verdict |
| --- | --- | --- | --- |
| 3-5 (read-aloud) | 100 | adult oral 183 wpm; no norm for picture-book read-aloud with dwell | Plausible, unanchored; label as assumption |
| 5-8 | 90 | ORF G1-2 60-100; Taylor G2 115 | Well placed, conservative |
| 8-11 | 120 | ORF G3-5 112-146; Taylor G3-4 138-158 | Slightly conservative; headroom to ~130-135 |
| 10-13 | 150 | ORF G6 146; Taylor G5-7 discounted per Spichtig | Reasonable |
| 13-16 | 190 | Taylor G8-10 204-224 minus plateau | Reasonable |
| 16+ | 220 | adult fiction 260, range 200-320 | Conservative by 10-15%, sensible margin |

Caveat: all norms are for continuous passages. None includes decision-point dwell time; per-node time
estimates should treat choice deliberation as a separate additive term (no literature quantifies child
choice-dwell time).

## 4. Fail states, frustration, and persistence by age

- Smiley and Dweck 1994 (Child Development): even 4-5-year-olds show helpless responses to failure;
  learning-goal orientation protects persistence. Foundational, replicated tradition.
- Leonard et al. 2021 (Developmental Psychology; 3 preregistered experiments, n=319, ages 4-6, STRONG):
  children persist when they perceive performance improving; flat/no-progress feedback demotivates.
  Design translation: visible progress across retries buys retry tolerance in young children.
- Chase 2001 (n=289, ages 8-14): high-self-efficacy children attribute failure to effort and persist;
  low-self-efficacy children attribute to ability and disengage.
- Fear-content curve (Weems and Costa 2005, JAACAP,
  [PMID 15968234](https://pubmed.ncbi.nlm.nih.gov/15968234/)): separation fears dominate ~6-9, death
  and danger fears peak ~10-13, social-evaluation and failure fears dominate 14-17. Preschoolers are
  frightened by perceptually scary imagery even when narratively benign (Cantor's fright-reaction
  program).
- Games scholarship: failure engages when framed as the player's responsibility and recoverable (Juul,
  [Fear of Failing](https://jesperjuul.net/text/fearoffailing/)); low-stakes multiple-chance settings
  reduce frustration (Shokeen et al., CHI PLAY 2020). WEAK to MODERATE.

Silence: no study measures retry tolerance or fail-ending acceptance in branching stories for
children, at any age. There is no empirical basis for a specific "no death endings under age X" line;
the per-band `forbidden_ending_kinds` policy is directionally supported (preschool helplessness
vulnerability; death salience peaking 10-13) but cannot be fine-tuned from literature.

## 5. Branching structure, replay, and choice counts

- Moser and Fang 2015 (above) is the lone controlled structure experiment: branching plus more salient
  decisions improved engagement (adults).
- Gamito et al. 2021 (n=64): showing post-ending feedback about unchosen paths increased replay intent
  via curiosity without remorse. Convergent with Detroit: Become Human's post-chapter flowcharts
  (Lagrange, DiGRA 2023; Nash et al. 2025, RRQ, DOI 10.1002/rrq.70079). The best-evidenced replay
  lever found; candidate for 8-11+ (for 3-8, meta-UI layers have no support, per section 2).
- Choice overload by age: preschoolers overload when cognitive resources are low (Schupak et al. 2019;
  fourth graders were more satisfied with MORE options); large arrays dilute preference in preschoolers
  (Miller et al. 2017); adult meta-analyses find overload only under moderators (Scheibehenne et al.
  2010; Chernev et al. 2015). Net: 2-3 options for 3-5/5-8/8-11; 3-4 permissible from 10-13 up.
- No academic study quantifies ending count, branching factor, or graph shape vs engagement or replay,
  and none involves children. The `min_endings` floors and endings-fraction heuristics (~15% prose,
  ~25% gamebook) are designer priors and should be labeled as such.

## 6. Implications for ADR-011 constants (consolidated)

| Constant | Verdict from evidence |
| --- | --- |
| Per-band wpm (100/90/120/150/190/220) | Keep. Defensible against Hasbrouck-Tindal 2017, Taylor 1965, Spichtig 2016, Brysbaert 2019. Label 3-5's 100 as an untested read-aloud assumption. Add a choice-dwell term to time estimates. |
| Choices per decision (2-3; 3-4 teen) | Design recommendation consistent with the evidence, not a measured threshold: the specific 2-3 / 3-4 numbers and the 10-13 switchover are designer priors. Direction supported: fewer options for young bands (overload + flow disruption), more tolerated and preferred from ~4th grade. Each added option must read as situationally distinct (Cardona-Rivera). |
| Choice cadence per band | No direct evidence anywhere. ADR-011 section 10 cadence is a designer prior. Adult evidence mildly favors more salient decisions for 10-13+; child e-book evidence favors fewer, story-integral stops at 3-8. |
| Flavor/consequential mix | Flavor-heavy is acceptable IF every choice is acknowledged in the very next text and looks situationally distinct when offered; the emotionally loaded choices should be moral/social/consequential; never frame flavor with high stakes (false-choice trust poisoning). |
| Fail-state policy per band | Directionally supported: 3-5/5-8 setbacks-only with visible retry progress and learning-goal framing; 8-11 recoverable failure, short distance back to the last choice; 10-13+ death/danger developmentally salient rather than harmful; 13-16/16+ full gamebook economics. Numbers are priors, not findings. |
| Endings floors / fractions | No literature anchor. Designer priors; direction (more endings with age, gamebook density for teens) is consistent with the rest of the evidence. |

## 7. Master gap list (silences, kept as deliverables)

1. No research on choice cadence or tap pacing for any population; none for children.
2. No research on children's tolerance for flavor vs consequential choices at any age.
3. No screen-length or words-per-node norms by age for interactive readers.
4. No study of branching choices as an e-book feature (meta-analyses cover hotspots/games/dictionaries).
5. No quantification of ending count, branching factor, or graph shape vs engagement or replay.
6. No empirical basis for age-gating death/fail endings in stories (only adjacent literatures).
7. No measurement of decision-dwell time in child readers.

These gaps mean the app's own reading telemetry (deferred behind the privacy review, see the
unscheduled-work register) is the only realistic path to calibrating cadence and dwell constants.

## Full source list

Locator policy (tightened after PR review, per the README standing rule): every entry carries a DOI,
a stable URL, or an aggregator link recorded during the research pass; entries whose aggregator link
did not survive verification are explicitly flagged rather than guessed. DOIs resolve via
`https://doi.org/<doi>`. Aggregator links below are Consensus paper pages captured 2026-08-02.

Choice/agency: Mawhorter et al. FDG 2014
(<http://www.fdg2014.org/papers/fdg2014_paper_19.pdf>), ICCC 2015
(<https://computationalcreativity.net/iccc2015/proceedings/13_4Mateas.pdf>), Arts 2018
(DOI 10.3390/arts7030047); Wardrip-Fruin et al. DiGRA 2009 (DOI 10.26503/dl.v2009i1.369,
<https://eis.ucsc.edu/papers/nwf-C7-digra09-agency.pdf>); Fendt et al. ICIDS 2012
(DOI 10.1007/978-3-642-34851-8_11); Cardona-Rivera et al. AIIDE 2014
(<https://consensus.app/papers/details/5ded2c308cf352a1b28492494a748dd3/>); Iten et al. CHI 2018
(<https://consensus.app/papers/details/116cb26e5aae5940ae5e75eed6ef3d91/>); Kway and Mitchell ICIDS
2018 (DOI 10.1007/978-3-030-04028-4_23); Carstensdottir et al. CHI 2021
(<https://consensus.app/papers/details/2022b2aea82f5812ad36413d77838dd7/>); Green and Jenkins 2014
(DOI 10.1111/jcom.12093); Kuo et al. 2016 (DOI 10.1002/cb.1620); Cao 2025
(<https://consensus.app/papers/details/41b0a509bfd65a2a9e84c03dc681a963/>); H. Zhang 2023
(<https://consensus.app/papers/details/8eaf417ef9bf5c16bc6a1afa059b1935/>); Kleinman et al. 2016
(DOI 10.1007/978-3-319-48279-8_32), 2018 (DOI 10.1145/3235765.3235773), 2020 (Entertainment
Computing, ScienceDirect PII S1875952117301167, text-only per the link-gate note in section 1.3);
Mitchell ICIDS 2020 (DOI 10.1007/978-3-030-62516-0_15); Moser and Fang 2015
(DOI 10.1080/10447318.2014.986639); Hwang et al. 2025
(<https://consensus.app/papers/details/44d9249b2ab65478badebc8e8b95a329/>).

Children's e-books: Takacs, Swart and Bus 2015 (DOI 10.3102/0034654314566989); Furenes, Kucirkova and
Bus 2021 (DOI 10.3102/0034654321998074); Bus et al. 2025
(<https://consensus.app/papers/details/9e26ba2de6e65e8fbb6862bc84f3fda9/>); Bus, Takacs and Kegel
2015 (DOI 10.1016/j.dr.2014.12.004); Savva et al. 2021 (JCAL; the pass's aggregator id did not
survive verification, flagged per the locator policy); Yeari et al. 2023
(<https://consensus.app/papers/details/e8cae4d0ed165be79dd5d82928fac116/>); Walker et al. 2017
(<https://consensus.app/papers/details/2f9a70ac67ef5a5c8350988635940dfb/>); Korat et al. 2021
(<https://consensus.app/papers/details/eb892acaa882588698a9084876c2189d/>).

Reading rates: Hasbrouck and Tindal 2017 (ERIC ED594994,
<https://files.eric.ed.gov/fulltext/ED594994.pdf>); Brysbaert 2019 (DOI 10.1016/j.jml.2019.104047);
Spichtig et al. 2016 (DOI 10.1002/rrq.137); Taylor 1965 norms via Hiebert, Samuels and Rasinski
(<https://textproject.org/wp-content/uploads/2022/07/Hiebert-samuels-rasinski_Comprehension-based-silent-reading-rates.pdf>);
Ciuffo et al. 2017 (<https://consensus.app/papers/details/7ed13f9856645c11a5bbeade4d26af20/>);
Chen et al. 2025 (<https://consensus.app/papers/details/45d2dfcaece05cb78a2c6b63a60bb34f/>).

Failure/persistence: Smiley and Dweck 1994
(<https://consensus.app/papers/details/4004ab65bf1f5c72a9e110b1c261dcda/>); Leonard et al. 2021
(<https://consensus.app/papers/details/79ab55da2a2d544481764e05ecc16ece/>); Chase 2001
(<https://consensus.app/papers/details/7161d518ec6f530ea0b5bd862ca7a4d8/>); Bennett 2018
(<https://consensus.app/papers/details/6bd631d07d9c5bfb80ad3bcf8adeacac/>); Huang et al. 2017
(<https://consensus.app/papers/details/2d4c8bbb8a435c33bc1085e4f75f0ee7/>); Gilmore et al. 2003
(<https://consensus.app/papers/details/67dd89caa2d1528a80df99915bebb99c/>); Wang et al. 2026
(<https://consensus.app/papers/details/8f6f00e530385e71bf9e332ed5fcb9a0/>); Yavorska-Vietrova 2021
(<https://consensus.app/papers/details/f74a80791d215c0d8fbb26e97a9bf1b4/>); Weems and Costa 2005
(PMID 15968234, <https://pubmed.ncbi.nlm.nih.gov/15968234/>); Sayfan and Lagattuta 2008
(DOI 10.1111/j.1467-8624.2008.01161.x); Cantor via Ed Week 1996
(<https://www.edweek.org/education/what-scares-children/1996/04>); Juul, Fear of Failing
(<https://jesperjuul.net/text/fearoffailing/>); Shokeen et al. 2020 (CHI PLAY,
DOI 10.1145/3383668.3419901).

Branching/replay/choice count: Gamito et al. 2021
(<https://consensus.app/papers/details/37d80537fce358b19456c5c8759660ec/>); Lagrange DiGRA 2023
(<https://consensus.app/papers/details/379ce2cb32dc5a24b253a71b2d598f72/>); Nash et al. 2025
(DOI 10.1002/rrq.70079); Yong et al. 2023
(<https://consensus.app/papers/details/5463ca5240ed5014a5d250a76b8459d7/>); Carstensdottir et al.
FDG 2019 (<https://consensus.app/papers/details/a45fd572375f50a6a99cbe38dd1ec11f/>); Breien and
Wasson 2020 (DOI 10.1111/bjet.13004); Mishra et al. 2025 (WhatIF; the pass's aggregator id did not
survive verification, flagged per the locator policy); Ashwell 2015 (gray literature, see the
structure note); Schupak et al. 2019
(<https://consensus.app/papers/details/c683bb9e48875a3eade8e43918b99902/>); Castelo et al. 2023
(<https://consensus.app/papers/details/759bf175f6465c93950c3fca51bff2bb/>); Miller et al. 2017
(<https://consensus.app/papers/details/e968316b88b25983900de321715b327c/>); Tiger et al. 2006
(<https://consensus.app/papers/details/e2ba74a5d7505ec482266cf0065a33f5/>); Scheibehenne et al. 2010
(<https://consensus.app/papers/details/2930f189fab95d3495ebbfedb94f142b/>); Chernev et al. 2015
(<https://consensus.app/papers/details/c7be5e074f57554893b5ee8df581e539/>).
