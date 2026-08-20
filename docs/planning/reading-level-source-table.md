# Reading level: what each source says

> **RESOLVED 2026-08-18.** `validator/band_profile.py`'s `_READING_LEVEL_TARGET` is now the single
> source of record; `brief.py`, the injected prompt guide, and the frontend derive from it, and
> `tests/unit/test_reading_level_sources.py` parses the two non-Python surfaces and compares them, so
> they cannot drift again. The whole-book gate reads each book's own band. The
> `reading_level_cap` ceiling now clamps rather than substitutes, on both stacks. The tables below
> are kept as the record of what disagreed.

Built 2026-08-18 in response to the owner's request during the `AL-458` audit sweep, which found
that four sites state per-band Flesch-Kincaid targets and they do not agree. Every number below was
read out of the named source, not transcribed from another table. Cited by `UW-C281`.

## 1. The one table that actually governs a book

RL-13 measures each node against **the story's own declared `metadata.reading_level.target`**, plus
or minus its declared `tolerance`. Nothing in the validator consults a per-band table. So the
operative numbers are whatever the catalog declares, and every other table below is upstream advice
about what to declare.

| Age band | Declared target(s) in the committed catalog | Declared tolerance | Effective window |
|---|---|---|---|
| 3-5 | 1.0 | 1.0 | up to 2.0 (upper bound only) |
| 5-8 | 2.5 | 1.0, 1.5 | up to 3.5-4.0 (upper bound only) |
| 8-11 | 4.5 | 1.5 | 3.0 to 6.0 |
| 10-13 | 5.5 | 1.5 | 4.0 to 7.0 |
| 13-16 | 7.0 | 1.5, 2.0 | 5.0-5.5 to 8.5-9.0 |
| 16+ | 8.0, 8.5, 9.0 | 1.5, 2.0 | 6.0-6.5 to 10.5-11.0 |

3-5 and 5-8 are upper-bound only (`reading_level._UPPER_BOUND_ONLY_BANDS`): prose too easy for a
young reader is not a defect.

## 2. Every source, side by side

| Age band | A. `brief.py` `_BAND_FK_TARGET` | B. frontend `intakeApi.ts` `BAND_DEFAULTS.fkTarget` | C. **injected** `generation/templates/drafting_guide.md` | D. `docs/planning/drafting-guide.md` | E. Declared in catalog (governs) | F. `scripts/check_reading_level.py` (**the only gate**) | G. Measured FK of committed books (min / median / max) |
|---|---|---|---|---|---|---|---|
| 3-5 | 1.0 | 1 | 1.0 (0.0-2.0) | 0.0-1.5 | 1.0 | 5.5, max 7.0 | -0.42 / 0.76 / 1.47 |
| 5-8 | 2.0 | 2 | 2.0 (1.0-3.0) | 1.5-3.0 | 2.5 | 5.5, max 7.0 | 1.71 / 2.30 / 2.69 |
| 8-11 | 4.0 | 4 | 4.0 (3.0-5.0) | 3.0-4.5 | 4.5 | 5.5, max 7.0 | 4.45 / 4.50 / 4.63 |
| 10-13 | 6.0 | 6 | 6.0 (5.0-7.0) | 5.0-7.0 | 5.5 | 5.5, max 7.0 | 4.74 / 4.99 / 5.54 |
| 13-16 | 8.0 | 8 | 8.0 (7.0-9.0) | 7.0-9.5 | 7.0 | 5.5, max 7.0 | 6.59 / 6.72 / 7.40 |
| 16+ | 10.0 | 10 | 10.0 (9.0-11.0) | 9.5-12.0 | 8.0-9.0 | 5.5, max 7.0 | 6.57 / 8.36 / 9.33 |

Sources, exactly:

- **A** `src/cyo_adventure/story_requests/brief.py`, `_BAND_FK_TARGET`. Sets the brief's
  `reading_level_target`, and only when the child's `reading_level_cap` is the unset 99 sentinel.
- **B** `frontend/src/guardian/intakeApi.ts`, `BAND_DEFAULTS`. The guardian intake UI's proposed
  default. Its own comment calls these "proposed defaults ... anchored to the repo's 8-11
  precedent" and says "revisit when validator policy grows per-band reading-level values".
- **C** `src/cyo_adventure/generation/templates/drafting_guide.md`. **Spliced into every structure,
  prose, and fill prompt.** Calls itself "the FK-target source of record".
- **D** `docs/planning/drafting-guide.md`. Human-facing authoring guide. States ranges, plus
  words/sentence and syllables/word, plus a reference book per band.
- **E** `metadata.reading_level` across the committed skeletons. What RL-13 measures against.
- **F** `scripts/check_reading_level.py`, `_TARGET=5.5`, `_TOLERANCE=1.5`, `_MAX_GRADE=7.0`. The
  whole-book check in the guard battery, listed there as "is the whole book too hard for its band",
  gating yes. It never reads the band.
- **G** `measure_book` over the 31 committed `out/*.filled.json`, each against its own declared
  target.

## 3. Where they disagree, and how much it matters

| Disagreement | Size | Consequence |
|---|---|---|
| **C (injected into every prompt) vs E (what the validator measures)** | 1.0 grade at 13-16, 1.0-2.0 at 16+ | The generator is told to write to 8.0 while RL-13 grades against 7.0. The prompt's stated range at 13-16 (7.0-9.0) is partly outside the declared window; at 16+ (9.0-11.0) it is almost entirely outside. This is the sharpest conflict: it is the only one that steers the model on every single generation. |
| **F vs every other column** | up to 5.0 grades | The only gating whole-book check grades all six bands against a 10-13 target. All five books it marks OVER are inside their own declared windows; a 16+ book a full grade below its window passes. A 3-5 book has 5.0 grades of headroom before it fires. |
| **A/B/C vs E at 8-11 and 10-13** | 0.5 grade each way | 8-11 is told 4.0 and declares 4.5; 10-13 is told 6.0 and declares 5.5. Small, but the two bands disagree in opposite directions, so no single offset reconciles them. |
| **D vs C** | 0.0-1.5 depending on band | Two drafting guides with the same name in different directories state different numbers. D's 16+ floor (9.5) is above C's centre (10.0) minus tolerance, and D's 3-5 range starts at 0.0 where C's centre is 1.0. |
| **G vs C** | 1.3-3.4 grades | What was actually written sits well below what the injected guide asks for at the top bands: 13-16 measures a 6.72 median against a stated 8.0, 16+ measures 8.36 against 10.0. Four of five 13-16 books are below the injected guide's own floor. |
| **G vs E** | mostly inside | Against their own declared targets the corpus is broadly in band. The books are consistent with what the validator asks; they are not consistent with what the prompt asks. |

## 4. The reading_level_cap conflation, separately

`story_requests/brief.py` feeds `profile.reading_level_cap` into `reading_level_target` when a
guardian has set one. `api/schemas.py` documents the cap as a ceiling that "can only ever tighten".
RL-13 then uses the value as the **centre** of a plus-or-minus window, so a guardian-set cap of 2.0
admits prose at FK 3.00, a full grade above the maximum that guardian asked for. This is a
ceiling-used-as-a-centre error and is independent of which table above wins.

## 5. What has to be decided

1. **One source of record.** Four tables claim the role; C says so in its own text. Whichever wins,
   the other three should derive from it or be deleted, not restate it.
2. **Whether the declared-per-story target survives at all.** Today E governs and is authored per
   skeleton, which is why the catalog is self-consistent and disagrees with every upstream table. A
   per-band table that the skeleton inherits would collapse E into whichever of A-D wins.
3. **What the whole-book gate should check.** F is the only gating row and currently checks a
   different thing than it advertises. It needs to read the band, or its guard-battery description
   needs to stop claiming it does.
4. **Cap versus target.** A ceiling and a window centre are different quantities and one field is
   being used as both.

None of these is a code-sized question; each is a decision about which number is true.
