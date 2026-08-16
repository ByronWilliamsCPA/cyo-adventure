# W7 run 4: what a second complete run settles

> Run: `out/w7-run4/`, 2026-08-16, 43 arms x 2 judges = 86 scorings, $2.5855.
> Panel: `judge-gpt-5.6`, `judge-grok-4.6`. `gemini-3.1` excluded (`AL-403`, `AL-408`).
> Compared against run 1 (`out/w7/verdicts.json`, 3 judges, 129 scorings, 2026-08-14).
> This is the first W7 run to complete in this environment after three consecutive kills.

## Verdicts, re-derived without `gemini-3.1`

| criterion | verdict | detected | median delta | noise floor |
| --- | --- | --- | --- | --- |
| `age_fit` | KEEP | 6/6 | -2.00 | 0.82 |
| `imagery` | KEEP | 6/6 | -2.00 | 0.24 |
| `voice` | UNTESTED | no arm exercises it | - | 0.35 |
| `dialogue` | **RETIRE** | 1/2 | -0.75 | 0.00 |
| `choice_quality` | KEEP | 5/5 | -1.50 | 0.24 |
| `ending_quality` | KEEP | 6/6 | -1.50 | 0.47 |
| `engagement` | KEEP | 5/6 | -0.50 | 0.12 |

`dialogue` moves from under-powered to RETIRE, but on n=2 books, because
`dialogue_flat` only lands on the two books that contain dialogue at all. A
1-of-2 miss and a 1-of-6 miss are not the same evidence, and this verdict
should be read as "still not supported" rather than as a firm retirement.

## `UW-C258`: per-criterion run-to-run spread

The previous estimate compared two runs at *leg mean* granularity and reported a
single figure, 0.217. That figure is an average across criteria whose stability
differs fourfold, so it describes no criterion in particular.

Measured per criterion over 84 matched `(judge, arm)` pairs:

| criterion | mean abs delta | share >= 0.5 margin |
| --- | --- | --- |
| `imagery` | 0.071 | 7.1% |
| `dialogue` | 0.119 | 11.9% |
| `ending_quality` | 0.119 | 11.9% |
| `voice` | 0.179 | 17.9% |
| `engagement` | 0.179 | 17.9% |
| `age_fit` | 0.214 | 21.4% |
| `choice_quality` | 0.286 | 28.6% |

The median is 0.000 for every criterion: most scorings reproduce exactly, and
the mean is carried by a minority that move a full scale point.

## `UW-C255`: the false-positive column, restated against controls

W7's `x-arm` column counted a criterion moving on another criterion's defect
arm. The arms are not single-defect documents, so most of that movement is real
collateral change and the column penalised criteria for working.

On **control arms**, where the book is unmodified and any movement is
unambiguously noise:

| criterion | mean abs delta | share >= 0.5 margin |
| --- | --- | --- |
| `imagery` | 0.000 | 0.0% |
| `dialogue` | 0.000 | 0.0% |
| `engagement` | 0.000 | 0.0% |
| `voice` | 0.167 | 16.7% |
| `ending_quality` | 0.250 | 25.0% |
| `age_fit` | 0.333 | 33.3% |
| `choice_quality` | 0.333 | 33.3% |

Three criteria did not move at all on an unchanged book across two runs. That is
the number the `x-arm` column should have been reporting, and it splits the
panel into two populations the old column could not distinguish.

## Do the KEEP verdicts survive their own noise

| criterion | effect | control run-to-run | ratio |
| --- | --- | --- | --- |
| `age_fit` | 2.00 | 0.333 | 6.0x |
| `imagery` | 2.00 | 0.000 | never moved |
| `choice_quality` | 1.50 | 0.333 | 4.5x |
| `ending_quality` | 1.50 | 0.250 | 6.0x |
| `engagement` | **0.50** | 0.000 | never moved |

All five clear their own noise, so no KEEP is withdrawn. The one to watch is
**`engagement`**, whose effect of 0.50 sits exactly *on* the 0.5 detection
margin while detecting on 5 of 6 books. Its control-arm movement of 0.000 is
what carries it; one book moving one scale point would take it below the margin.
Treat it as the weakest KEEP on the panel rather than as an equal of `imagery`.

## Panel stability after dropping `gemini-3.1`

Pooled across criteria, the two surviving judges are now comparably stable:

| judge | n | mean abs delta | share >= margin |
| --- | --- | --- | --- |
| `judge-gpt-5.6` | 287 | 0.164 | 16.4% |
| `judge-grok-4.6` | 301 | 0.169 | 16.9% |

Against run 1, where `gemini-3.1` averaged 0.323 absolute movement to
`gpt-5.6`'s 0.120 and owned every movement past a full scale point. Removing it
removed the asymmetry rather than merely lowering an average.

## Agreement, two judges, per criterion

Quadratic-weighted kappa against the project's 0.60 floor:

| criterion | rho (within-book deltas) | qwk (raw) |
| --- | --- | --- |
| `imagery` | +0.70 | +0.77 |
| `dialogue` | +0.65 | +0.65 |
| `choice_quality` | +0.61 | +0.61 |
| `ending_quality` | +0.39 | +0.58 |
| `engagement` | +0.34 | +0.56 |
| `voice` | +0.31 | +0.40 |
| `age_fit` | +0.19 | +0.39 |

`age_fit` is the standout: a KEEP with the largest effect on the panel (-2.00)
and the *worst* inter-judge agreement (+0.19 / +0.39). Both judges detect the
seeded defect every time and disagree about the level. That is consistent, and
it means `age_fit` is usable for "did this get worse" and not for "how good is
this", which is the distinction a ranking would erase.

## Reproducing

```
uv run python scripts/seed_defects.py out/w7/corpus/*.filled.json --out out/w7/arms
uv run python scripts/w7_battery.py --arms out/w7/arms --harden-dir out/w7/harden \
    --reblend --prepare out/w7/corpus/*.filled.json
uv run python scripts/w7_battery.py --arms out/w7/arms --out out/w7-run4 --env-file .env
uv run python scripts/w7_run_to_run.py --first out/w7/verdicts.json \
    --second out/w7-run4/verdicts.json
uv run python scripts/w7_agreement.py --verdicts out/w7-run4/verdicts.json
```

The first two steps call no provider: `out/w7/corpus/` and `out/w7/harden/` are
tracked, and only the judging pass costs money.
