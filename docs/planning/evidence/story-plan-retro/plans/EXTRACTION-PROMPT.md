# WP-1.4 blind extraction prompt

This is the exact instruction text given to every WP-1.4 extracting agent, committed before any extraction ran so the
blindness claim can be audited (`docs/planning/story-plan-implementation-plan.md`, WP-1.4). Each agent received this
text followed by one assignment line naming its input file(s) and output id(s). The mapping from input ids to source
books and revisions is recorded in `manifest.json`, written after extraction; the agents never saw it.

**Isolation.** Agents ran in a separate git worktree from which `docs/planning/` (including this directory and the
answer key), `tests/`, `.claude/skills/cyo-author/reference/`, every `out/*.plan.json`, and the current versions of the
four revised books had been deleted from the working tree. Inputs were staged as `tmp_cleanup/blind/x<N>.book.json`
under neutral ids. Agents did not commit; the orchestrator committed their outputs.

---

You are writing a Story Plan for an existing choose-your-own-adventure book, by reading the book. Work only in the
directory `/workspace/cyo-adventure/.worktrees/wp14-blind`. Use `uv run python` for any script.

## What you may read (nothing else)

- Your assigned input book(s): `tmp_cleanup/blind/x<N>.book.json`.
- `src/cyo_adventure/storyplan/models.py` (the Story Plan schema; its module docstring defines every field).
- `schema/storyplan.schema.json` (the same schema as JSON Schema).
- `src/cyo_adventure/storybook/models.py` and `src/cyo_adventure/player/engine.py` (the book format and the engine:
  `StoryEngine` with `start`, `visible_choices`, `choose`), so you can walk the book's routes and variable states.
- A format example: `tmp_cleanup/blind/example.plan.json`, a plan for a different book,
  `tmp_cleanup/blind/example.book.json`. Use it for shape and level of detail only.

Do not open, list, grep or search any other file or directory in the repository. Do not run `git log`, `git show`,
`git diff`, `git blame` or any other command that reads history. Do not run `scripts/check_story_plan.py`, any
`scripts/check_*` or `run_*gate*` script, or any validator. Do not read other agents' outputs. Do not use the web.
If you find yourself needing something outside this list, stop and say so in your report instead.

## What to produce, per assigned book

1. **A plan**: `docs/planning/evidence/story-plan-retro/plans/<id>.plan.json`, valid under `StoryPlan` in
   `models.py`, `plan_version` `"0.1"`. Bind it with `provenance.book_sha256` (hex SHA-256 of the input file's bytes)
   and `provenance.book_file` (the input path); set `provenance.producer` to `"wp-1.4 blind extraction"`,
   `provenance.method` to `"read-book"`, `provenance.authored` to today's date, and `provenance.authoring_minutes` to
   your honest estimate of the time spent. Write `request.band` from the book's `metadata.age_band`. Every node id and
   every choice id in the book must appear in `nodes` and `choices`, verbatim; every ending node in `endings`; every
   variable that a choice sets as a `thread` with its planting choices and payoff sites.
2. **An assertion map**: `docs/planning/evidence/story-plan-retro/assertions/<id>.json`, a JSON object whose keys are
   every node id in the book and whose values are lists of plan fact ids: **the facts that node's prose (body and its
   choice labels) asserts or presupposes as true**, whether or not the reader could know them by then. Record what the
   text says, not what it should say. An empty list is valid.

## How to write the plan

- Read the whole book first: every node body and every choice label, conditions and effects. Walk its routes and
  reachable variable states with `StoryEngine` so you know which nodes are reached from where and in which states.
- **`truth`**: the story's one canonical answer as the book presents it, and the ledger facts that make it up.
- **`facts`**: one entry per distinct thing the reader can come to know (a person, an object, a past event, a place, a
  name, a rule of the world, a possession or state). Keep them small and concrete; a partial reveal is its own fact.
  Mark genuinely incompatible facts with `contradicts`.
- **`nodes`**: for each node, `function`, a one-line `event`, `establishes` (the facts this passage makes known to a
  reader who did not know them) and `requires` (the facts this passage's prose **presupposes the reader already knows
  on entry**: names used without introduction, objects referred to as already seen or held, events referred to as
  already happened). Write `requires` from what the prose presupposes, not from what you believe every route has
  shown. Do not adjust `requires` or `establishes` to make routes consistent; that is not your job, and the plan is
  only useful if it records the text faithfully.
- **`choices`**: `intent` and `cost` for every choice (one short phrase each; `"none"` is allowed), `plants` where the
  choice sets a variable, and `requires` / `establishes` where the label presupposes or establishes a fact.
- **`threads`**, **`endings`** (`gift` required for each ending, plus `valence` and `kind` from the book), **`pitch`**,
  **`cast`**: as the schema describes, read off the book.
- Keep plan strings single-line, printable, without braces, `<<` or `>>`, and without the em-dash character (U+2014).
  Slot-like strings (pitch, cast, choice intent and cost, ending gift, payoff `shows`) at most 120 characters; fact
  texts and node events at most 240; `truth.statement` at most 600.

## Validation you may run

Schema validation only:

```bash
uv run python -c "import sys; from cyo_adventure.storyplan.models import StoryPlan; StoryPlan.model_validate_json(open(sys.argv[1]).read()); print('ok')" <plan path>
```

and a script you write yourself that checks every book node id is a key of the assertion map and of `nodes`, every
choice id is a key of `choices`, and every assertion value is a declared fact id. Write JSON with `indent=2`,
`ensure_ascii=True` and a trailing newline. Put any scratch scripts under `tmp_cleanup/blind/work-<id>/`.

## Report

For each assigned book: the output paths, node / choice / fact / thread counts, the time you spent, anything in the
book you found ambiguous and how you resolved it, and confirmation that you read nothing outside the allowed list.
Do not commit.
