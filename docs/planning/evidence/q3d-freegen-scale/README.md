# Q-3d: does constraint-stated generation hold at production scale?

Two graphs at 100 to 115 nodes, the same stated constraint set as Q-3b scaled to the
band, mutually isolated authors, nothing in this repository read. This is the pivot test:
both candidate architecture rankings turned on whether skeleton-free generation survives
past the 30-node pilot.

| | s1 | s2 |
| --- | --- | --- |
| nodes / endings / forks | 103 / 20 / 30 | 101 / 20 / 24 |
| structural failures | **0** | **0** |
| all 13 stated constraints | pass | pass |
| Flesch-Kincaid | **5.12** | **8.35** |
| nodes inside band | **84%** | **11%** |
| reading-level gate | **pass** | **FAIL** |
| one pass? | **no** | **no** |
| approximate tokens / tool calls | 210k / 60 | 337k / 269 |

## Structure holds. Nothing else came free.

**Structural validity survives the scale jump: 2 of 2, zero failures, every budget met.**
That answers the question both reviews' rankings depended on, and it answers it favourably
for generation-without-reuse.

**Neither author managed it in one pass.** s1 built a scripted build-validate-patch loop;
s2's first draft produced a longest path of 43 against a ceiling of 24 and needed
structural trimming and repadding. The one-pass yield that held at 30 nodes is gone by 100.
What replaced it is iteration against a checker, which is the architecture's actual
requirement rather than an implementation detail.

**Reading level split 1 of 2, and the split has a cause.** s1's author explicitly added
sentence-splitting for readability to its loop and landed at 5.12 with 84 percent of nodes
in band, the first book in this programme to pass reading level at production scale
against a prior 101-node attempt that reached 8.1 to 8.4. s2's author built a loop for
depth and word count and not for reading level, and landed at 8.35 with 11 percent in
band. Same prompt, same explicit target, opposite outcomes, decided by whether the author
chose to instrument the one constraint it cannot estimate by inspection.

The conclusion is narrow and firm: **the repair loop belongs in the harness, not the
prompt.** Leaving it to the author's initiative is a coin flip, and this run flipped it
once each way.

## Cost

Roughly 2.5 to 4 times the tokens of a 30-node graph for 3.4 times the nodes, with tool
call counts of 60 and 269 against 3. Generation cost is not linear in nodes and is
dominated by the repair loop, which is the first hard evidence available for pricing any
of the candidate architectures and the reason cost instrumentation should precede the
bake-off.

## The premise mode is unchanged at scale, and collided again

- s1: *The Lighthouse of Windgate Bay*
- s2: *The Lantern Keeper's Apprentice*

s2 independently reproduced, word for word, the title of one of the 30-node graphs from
Q-3b. That is the third collision in this round, after the near-identical *Marrow Hill*
pair. Pooled across Q-3b, Q-3c and this run, **10 of 12 independent generations across
three model tiers and two scales centre on a light-or-signal beacon.**

s1 against s2 sits at **5.18 shared four-grams per 1000**, over the 4.0 budget, which is
again a same-archetype pair breaching through content rather than wording.
