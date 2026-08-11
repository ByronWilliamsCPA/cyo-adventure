# Q-3c: is the premise mode a property of one model, or of the family?

`AL-239` found six mutually isolated authors producing five coastal
lighthouse-or-lantern stories. That run used one model, so the mode could have been
that model's. This probe holds the task and the prompt constant and varies the model:
two instances each at two other tiers, each asked only for a title, a one-line premise
and an opening passage, each forbidden from reading anything in the repository.

## Result

| model | title | beacon object | elder or keeper |
| --- | --- | --- | --- |
| tier A, run 1 | The Last Star Forest | no | no |
| tier A, run 2 | The Lighthouse Keeper's Secret | **lighthouse** | **grandmother, keeper** |
| tier B, run 1 | **The Lantern Under Marrow Hill** | **lantern** | no |
| tier B, run 2 | **The Lantern Beneath Marrow Hill** | **lantern, Beacon** | no |

**Two independent instances at tier B, sharing no context, invented the same place name
and the same object, and produced titles differing by a single preposition:** *The Lantern
Under Marrow Hill* against *The Lantern Beneath Marrow Hill*. Four of five words identical.
Neither could see the other; neither read any file.

Pooled with the six-book run, **8 of 10 independent generations across three model tiers
put a light-or-signal beacon at the centre of the story**, most of them coastal or
fog-bound, several with an elder keeper. The two outliers are a kite race and a forest
threatened by a shopping mall.

## What this does and does not establish

**Does:** the premise mode is not an artifact of one model or one capability tier. It
survives changing the model, holding the prompt fixed. Any architecture whose diversity
argument rests on "generate independently" is answering a question the data has already
closed.

**Does not:** all three tiers belong to one model family. This is silent on whether the
mode is training-distribution-level across vendors. Testing that needs authors from
genuinely different families, which this run could not reach, and it remains the open
version of the question.

The practical consequence is unchanged either way: premise must be allocated from a
curated enumerated space, because the failure lives in the generator's own distribution
and withholding does not touch it.
