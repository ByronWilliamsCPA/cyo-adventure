# Authoring instructions

You are authoring one branching storybook for readers aged 10-13. You have exactly two input
files, given to you by path: `kernel.json` (the narrative contract) and `shell.json` (the
story graph to fill). Read only these two files. Do not read any other file and do not list
any directory. Write exactly two output files, at the paths given to you.

## Step 1: read the contract and the graph

`kernel.json` carries, per node: `function` (what the scene is for), `tier`, `entry_state`
(every fact a reader is guaranteed to know arriving at this node, on every path into it),
`establishes` (facts this node must make true), `forbids` (facts this node must not make true
or reveal), and for some nodes an `invention` entry (formal device picks). Top level:
`facts` (the fact vocabulary), `world_recipe` (device categories to draw from), and
`safety_envelope` (hard content constraints). Honor every field that is present. If a field
is absent, it is absent; do not infer constraints that are not stated.

`shell.json` is the story graph: nodes, choices with labels and targets, ending markers, and
a `<<FILL role=... words=N ...>>` directive in each body. The shell's choice labels are
authoritative for the world: derive your setting, characters, and proper nouns consistently
from them, and invent the rest yourself, keeping every invention consistent everywhere it
appears.

## Step 2: write the decisional stratum

Write `decisional.json`:

```json
{
  "stratum": "decisional",
  "premise": {
    "engine": "a-short-kebab-case-name-for-your-story-engine",
    "dramatic_question": "one sentence",
    "resolution_space": ["one sentence", "one sentence", "one sentence"]
  },
  "nodes": {
    "<node_id>": {
      "beat_hint": "one or two sentences: what happens in this scene",
      "affect": {"target": "the feeling this beat aims for", "forbid": ["feelings to avoid"]},
      "choice_semantics": {"<choice_id>": "one sentence: what choosing this option means"}
    }
  }
}
```

Every node in the shell gets an entry. `choice_semantics` appears only on nodes that have
choices, with one entry per choice id. Where a node's `invention` entry requires picks, choose
from the listed category kinds, respect `unique_within_story`, stay consistent with the
shell's labels, and use your picks consistently in every later scene.

The stratum must honor the contract: a beat may only assume facts in its node's
`entry_state`, must deliver its `establishes`, and must not make a `forbids` fact true or
reveal it.

## Step 3: fill the shell

Write `filled.json`: the complete shell JSON with exactly these changes and no others.

- Replace every `<<FILL ...>>` body with prose. Aim within twenty percent of the directive's
  `words=N`.
- Replace the book `title` with your own.
- On ending nodes, set `ending.title` following the kernel's `title_contract` for that node
  when one is present; otherwise choose a short, evocative title of your own.
- Change nothing else: ids, choice labels, targets, `start_node`, `variables`, `metadata`,
  ending kinds and valences all stay byte-identical.

Prose rules: second person, present tense. Readers are 10-13: Flesch-Kincaid grade roughly
5 to 7, sentences averaging 14 to 18 words, concrete and clear. Each scene delivers its
`beat_hint` and lands its obligations. The first sentence after a choice acknowledges what
the reader just chose. Never use the em-dash character in any output. Output must be valid
JSON, UTF-8, no trailing commentary.

## Step 4: write the outputs

Write `decisional.json` and `filled.json` to the two output paths you were given. Do not
write any other file. Then reply with a single line: the book title you chose and the total
word count of your filled bodies.
