---
title: "Story personalization: closed-vocabularies proposal (ADR-023 rows 4a/5/6/7)"
schema_type: planning
status: draft
owner: core-maintainer
purpose: "Proposed value lists for the four empty CLOSED_VOCABULARIES enums, for owner
  accept/edit/reject review."
tags:
  - planning
  - privacy
component: Strategy
source: "ADR-023 rows 4a/5/6/7; src/cyo_adventure/storybook/personalization_values.py;
  docs/planning/story-personalization-execution-plan.md open question 3"
---

## Goal

`CLOSED_VOCABULARIES` (`src/cyo_adventure/storybook/personalization_values.py:105-119`) ships
four enum slots with empty vocabularies by design: `pet_species`, `kinship_label`, `favorite`,
and `home_type` (plus a fifth key, `dedication`, which shares `kinship_label`'s shape; see the
dependency note below). Every `value_enum` candidate for these slots is currently rejected
(fail-closed), because ADR-023's taxonomy table names categories and a few illustrative examples
but never an exhaustive, shippable list (module docstring,
`personalization_values.py:57-73`). This document proposes those lists for owner review. It does
not decide; each list below ends with an explicit decision line.

## How acceptance lands

The owner marks each decision below (or in PR review comments on this file). A follow-up code
change then edits `CLOSED_VOCABULARIES` to the accepted values, citing this document. The dict's
own `#VERIFY` marker (`personalization_values.py:102-104`) requires exactly that: "do not
hand-add values here without a design-plan update or an ADR-023 amendment recording the
vocabulary." Once accepted, this document is that update.

One dependency worth flagging up front: `CLOSED_VOCABULARIES` actually has a fifth key,
`dedication` (`personalization_values.py:118`, added by Stage C Task C0e after AL-068 found it
missing). ADR-023 row 8 stores a kinship label there in the same closed shape as `kinship_label`
(row 5), kept as a separate key because the "from" kinship on a dedication can legitimately
differ from the in-story trusted-adult kinship. **This proposal seeds `dedication` with the same
21-value list as `kinship_label`**; accepting `kinship_label` below therefore covers both keys
unless the owner asks for a distinct dedication list. Until then the "love {KINSHIP}" half of
the dedication template stays unreachable: `frontend/src/reader/DedicationOverlay.tsx:41-54`
renders the name-only fallback today for exactly this reason and will pick up the kinship clause
once the vocabulary lands.

## Verified facts this proposal depends on

- **The dict location and its fail-closed contract**: `CLOSED_VOCABULARIES` at
  `personalization_values.py:105`, with the four target entries as empty `frozenset()` literals
  at lines 106-109. Every candidate takes the "not a member of its closed vocabulary" rejection
  branch (`personalization_values.py:268-287`) until real values are seeded.
- **`favorite` is a flat, single-value slot, not three sub-fields**. Confirmed in three places:
  `theme_contract.py:63-79` (`PERSONALIZATION_FIELDS` lists `"favorite"` once, not
  `favorite_color`/`favorite_food`/`favorite_hobby`), `api/schemas.py:2189-2199`
  (`_PersonalizationSlotType` Literal lists `"favorite"` once), and
  `personalization_values.py` itself, where every slot type takes one `value_enum` regardless of
  category. There is exactly one `CLOSED_VOCABULARIES["favorite"]` set, so a candidate value must
  encode color, food, or hobby membership in a single flat vocabulary, not three parallel ones.
- **ADR-023 rows 4a/5/6/7** (`docs/planning/adr/adr-023-story-personalization-slots.md:354-358`):
  row 4a (pet species) names no example at all; row 5 (kinship label) gives four illustrative
  examples ("Grandma", "Abuela", "Auntie", "Grandpa") without stating they are exhaustive, and
  excludes "a real adult's personal name... a third party who never consented"; row 6 (favorite)
  names categories (color, food, hobby) not values, with the decision text reading "closed
  vocabulary lists only, never free text" (singular "lists" is ambiguous between one merged list
  and three; see Judgment call 1 below); row 7 (home type) trails off with "house, apartment,
  farm, ...".
- **No collision with the band-mandatory safety denylist**. The bundles are `lethal`, `weapon`,
  `toxic`, `capture`, `graphic`, `despair` (`src/cyo_adventure/validator/slots.py:43-160`), unioned
  per band by `band_mandatory_bundles` (`validator/slots.py:192-203`). I checked every proposed
  value below against all six bundles' stems (`_LETHAL`, `_WEAPON`, `_TOXIC`, `_CAPTURE`,
  `_GRAPHIC`, `_DESPAIR`, `validator/slots.py:43-151`): none of the proposed pet species, kinship
  labels, favorites, or home types share a word-boundary stem with any denylisted term. This is a
  point-in-time claim; re-run the check if either list changes before acceptance.

## Proposed vocabularies

### `pet_species` (16 values, lowercase common nouns)

```text
dog, cat, rabbit, hamster, fish, bird, guinea pig, turtle, lizard, snake, frog,
hermit crab, chicken, ferret, goat, horse
```

Common kid-household and small-farm pets, ordered roughly by prevalence, all kid-appropriate and
none exotic or unsafe to keep. `dog, cat, rabbit, hamster` open the list and `horse` closes it,
matching the fixed convention in the task spec.

Decision requested: accept, edit, or reject.

### `kinship_label` (21 values, Title Case address terms)

```text
Mom, Dad, Grandma, Grandpa, Nana, Papa, Gran, Pop, Abuela, Abuelo, Oma, Opa,
Auntie, Aunt, Uncle, Mama, Mommy, Daddy, Nonna, Nonno, Grown-up
```

These are vocative address terms, used mid-sentence in "love {KINSHIP}" (dedication) and in
story prose referring to a trusted adult (ADR-023 row 5), never a real adult's personal name. The
list covers common English terms (`Mom`, `Dad`, `Grandma`, `Grandpa`, `Auntie`, `Aunt`, `Uncle`,
informal variants `Mama`/`Mommy`/`Daddy`) plus widely used, culturally specific grandparent terms
(`Nana`/`Papa`/`Gran`/`Pop` English-informal, `Abuela`/`Abuelo` Spanish, `Oma`/`Opa` German/Dutch,
`Nonna`/`Nonno` Italian), and ends with `Grown-up` as the generic fallback for a family whose term
is not on the list. `Mom, Dad, Grandma, Auntie, Grandpa` and the trailing `Grown-up` match the
fixed convention in the task spec.

Decision requested: accept, edit, or reject.

### `favorite` (Option A, recommended: 16 flat values spanning color/food/hobby)

```text
red, blue, green, purple, pizza, tacos, ice cream, pancakes, soccer, dancing,
drawing, swimming, dinosaurs, space, robots, reading
```

One flat vocabulary because the schema is flat (see "Verified facts" above): four colors, four
foods, four hobbies-as-activities, and four hobbies-as-interests, all safe to drop into a single
sentence template regardless of which sub-category the guardian picked.

Decision requested: accept, edit, or reject.

#### Option B (alternative, not recommended): split into three slot types

A 36-value split, 12 each, across three separate slot types:

```text
favorite_color (12):  red, blue, green, purple, yellow, orange, pink, black,
                       white, teal, silver, gold
favorite_food (12):   pizza, tacos, ice cream, pancakes, spaghetti, burgers,
                       waffles, sushi, mac and cheese, strawberries, cookies, soup
favorite_hobby (12):  soccer, dancing, drawing, swimming, dinosaurs, space,
                       robots, reading, gymnastics, building blocks, biking, singing
```

**This is a bigger change than a value list edit.** It requires: a `ChildProfilePersonalization`
migration or CHECK-constraint update to accept three new `slot_type` values instead of one, three
new entries in `PERSONALIZATION_FIELDS` (`theme_contract.py:67-79`) and
`_PersonalizationSlotType` (`api/schemas.py:2189-2199`), and matching skeleton/theme-contract
slot declarations wherever `favorite` is bound today. Flag this to the owner explicitly: choosing
Option B is choosing a schema migration, not a vocabulary edit.

**Recommendation: Option A.** It fits the existing flat schema with zero migration, and the
combined list still reads naturally in a single sentence template ("your favorite is {FAVORITE}").

### `home_type` (12 values, lowercase)

```text
house, apartment, farm, cabin, houseboat, trailer, cottage, condo, duplex,
ranch, bungalow, tent
```

`house, apartment, farm, cabin` open the list per ADR-023 row 7's own trailing example, and `tent`
closes it (a home type valid for a family that camps or lives seasonally in one, and the fixed
convention in the task spec).

Decision requested: accept, edit, or reject.

## Three judgment calls worth recording

**1. `favorite` stays flat (Option A), not split (Option B).** Splitting into three slot types
touches the database `CHECK` constraint, the ORM slot-type surface, and the API `Literal` type;
none of that is required to ship a useful vocabulary. Recommend Option A unless the owner has a
specific reason to want color/food/hobby resolved independently at read time.

**2. Case convention is split, and deliberately not normalized in this module.** `pet_species`,
`favorite`, and `home_type` are lowercase because they are common nouns interpolated mid-sentence
("a pet {PET_SPECIES}"). `kinship_label` is Title Case because its values are vocative address
terms ("love {KINSHIP}"), matching ADR-023's own examples ("Grandma", "Abuela"). Recommend
normalizing case at the API boundary (the write-time route, before the value reaches
`validate_personalization_value`) rather than inside `personalization_values.py`: that module is
documented as pure and total (`personalization_values.py:207-209`), and case-folding is an input
transform, not a validation rule.

**3. No explicit "none" or "no pet" sentinel member in any list.** Leaving a slot unset is
already the existing contract for absence: an unset slot is simply omitted from the render
payload and the story falls back to its generic default
(`personalization_value_for_payload`, `personalization_values.py:299-368`). Adding a sentinel
value like `"none"` to `pet_species` would invent product policy ADR-023 never stated (does "no
pet" mean the story omits the pet entirely, or renders a generic unnamed pet?), so this proposal
leaves that decision to the owner rather than encoding an assumption into the vocabulary.

## Decision summary

| Slot | Count | Decision |
| --- | --- | --- |
| `pet_species` | 16 | accept / edit / reject |
| `kinship_label` | 21 | accept / edit / reject |
| `dedication` (same 21 values as `kinship_label` unless a distinct list is requested) | 21 | accept / edit / reject |
| `favorite` (Option A, recommended) | 16 | accept / edit / reject |
| `favorite` (Option B, alternative) | 36 | accept / edit / reject |
| `home_type` | 12 | accept / edit / reject |
