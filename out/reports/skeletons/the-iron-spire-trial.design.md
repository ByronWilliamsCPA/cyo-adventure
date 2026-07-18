# Design report: the-iron-spire-trial

- **Cell**: 13-16 / medium / gamebook (brief #23, Wave 5) — the normal 13-16 Medium gamebook gauntlet (paired with #24 the-smugglers-cut b&b; not a dagger cell)
- **Topology / tier**: gauntlet / 2 (the first TIER-2 gauntlet of the run; wins differentiated by accumulated state)
- **Designer model**: opus (gamebook batch; zero checker-fail cycles)
- **Reviewer model**: opus (independent; full uncapped config walk driving the real engine, enumerated every win config, de-duped all 64 dread/consequence beats)
- **Disposition**: APPROVED for the fill stage (2 non-blocking wording fixes; the skeleton-level one applied by the supervisor)

## Scripted validation (post-fix)

```text
stats: nodes=277 endings=79 fill_nodes=277 cell=(13-16, medium, gamebook) topology=gauntlet tier=2
ok: skeleton passes gate and brief checks
```

Reviewer confirmed: acyclic (zero cycles), longest path 53 edges (under the
60 cap), 3,405 reachable configs uncapped, zero choiceless states, 79 unique
untruncated titles, no em-dash, words mean 62.3 (13-16 gamebook envelope).

## State machine (three axes; first tier-2 gauntlet)

- `standing` 0-2 (conduct; monotone +1 at the two conduct checkpoints;
  differentiates the honour win).
- `grip` 0-3 (physical; monotone -1 at the three climb gamble-slips, never
  restored; gates the honest clean-line resolution of the Sheer Pitch).
- `token` bool (access; set at the Warden's Post; gates the High Gate and,
  with standing, the best win).

## Review verdict (7 categories): all PASS, OVERALL SHIP

- **Exact-partition + no choiceless state**: zero choiceless states across
  all 3,405 configs; the true resolve nodes (sheer_resolve on grip,
  summit_gate on standing, summit_honor_check on token) each show exactly one
  enabled choice per reachable state.
- **Best-win exactness**: win_honor ("Named to the Crown") reachable at
  exactly (standing==2, token==true), zero leaks; the two lesser wins occupy
  distinct standing/token regions.
- **Prose-variety guard: strong.** All 64 dread beats and all 64 consequence
  beats distinct (64/64), each naming its checkpoint hazard; 11 timing gates
  carry a delay-is-death beat.
- **Ratios**: 79/277 = 28.5% terminals (64 death + 12 capture + 3 wins);
  deaths grave, terse, gore-free.

## Fixes

1. **Applied (skeleton):** softened the `grip` variable description. The
   reviewer found the standard gamble-slip bypasses the grip check (as at
   every checkpoint), so grip gates the honest clean climb line, not survival
   absolutely, and does not differentiate the wins. The description now says
   so. Gate re-validated clean.
2. **Recorded (report):** the designer's self-report ending split (65 death /
   11 capture) was off by one each; the actual node-level split is 64 death /
   12 capture / 3 wins (reviewer-verified, matches metadata.ending_count=79).
3. **Fill-stage note (optional, not applied):** three positional "Stop/Shelter"
   hesitation fatals (portcullis/murderholes/beacon) lack an explicit
   delay-is-death beat; each is a legible positional death and each of those
   checkpoints has a separate literal "Wait" fatal that does carry the beat,
   so this is left as a fill-stage consistency note.

## Notes for the future fill stage

Pin the summit naming logic (standing==2 + token = named to the Crown;
standing==1 or no token = a true ascent; standing==0 = the unnamed summit).
Grip is a survival-flavor axis on the clean line only; write the Sheer Pitch
gamble as the nerve-over-strength bypass it is.
