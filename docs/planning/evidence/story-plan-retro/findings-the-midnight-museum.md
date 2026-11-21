# Continuity findings: The Midnight Museum (WP-0.4)

Second-reader continuity pass over `out/the-midnight-museum.filled.json` (revised edition, 108 nodes, 22 endings,
variables `read_back`, `has_chalk`, `has_token`, `has_glasses`) against its plan `out/the-midnight-museum.plan.json`.
The reader did not write the plan. This is one of the seven family-test books, and a revised book, so every finding
below is fixed (the WP-0.4 Controls rule does not apply).

**Method.** Every route was played with `StoryEngine` (`start`, `visible_choices`, `choose`) by exhaustive depth-first
search: 37,704 complete routes, 102,668 (node, route) visits, **584 distinct reachable (node, variable state)
configurations**, every node reached, no dead ends. For each node the walk recorded the known-on-entry set per route
(the union of `establishes` of nodes visited before it plus the plant fact of each planting choice taken), its inbound
nodes and its reachable states. Every passage and choice label was read against what is guaranteed on entry on every
route and in every state, against the plan's `truth`, and for plain contradictions. The read was then repeated the way
the reader sees it: 80 flowed screens (single-choice chains joined, as the 10-13 band flows them), each tagged with
its inbound nodes and states. Before the fix the plan's own `requires` lists held on every route (no SP-2 miss), so
every finding below is a fact the prose asserts that the plan did not list, or a contradiction the plan recorded as
written.

Routes are choice ids from the start; `...` elides a prefix any route can supply. States: `B` = `read_back`,
`C` = `has_chalk`, `T` = `has_token`, `G` = `has_glasses`. `B` and `C` are mutually exclusive (one plant at `n_desk`).

## Pre-fix findings

### Blocker

**F2. The floor opens "for one minute", yet on that route the stair stays open for hours.** Class
`state_contradiction`.

- Nodes: `ro_records_guard` (the rule) against `v_share`, `v_share_curator`, `v_reveal2`, `e_set_dawn`, `e_set_caught`,
  `v_grab_run` (the open stair afterwards).
- Route: `... c_dome_rotunda > c_rot_records > c_records_guard > c_guard_vault > c_vault_share > c_share_curator`, any
  state (all 1,080 routes through `ro_records_guard` are affected).
- Quoted: "my clockwork brings the rings home by itself and the floor opens for one minute." Then: "Nadia climbed
  back up the stair with the sealed letter in her hand, and the marble stood open behind her." and, at eight, "and at
  the open floor beside the globe."
- Why: on this route Nadia goes down a stair that by the book's own rule shut a minute later, which would trap her
  below; yet every following node has her climb out of an open floor, and the curator sees it open hours later. The
  plan recorded both facts (`floor_opens_one_minute`, `floor_left_open`, marked as contradicting).
- Fix: the founder's rule now reads "my clockwork brings the rings home by itself and opens the floor." The slab stays
  open until someone pushes it shut by hand (see F5). Plan: `floor_opens_one_minute` renamed
  `floor_opens_by_clockwork` with that meaning; `floor_left_open` removed.

### Should-fix

**F1. The founder's code is two different ciphers on different routes.** Class `two_backstories`.

- Nodes: `k_stairs_up`, `k_stairs_base` (three-place shift) against `k_cabinet`, `k_display_careful` (shuffled
  table). In the plan only, `e_set_broken_case` was also tagged with the shuffled table.
- Routes: `... c_corridor_key > c_key_stairs > c_stairs_up` (shift) versus `... c_corridor_key > c_key_display >
  c_display_open > c_open_cabinet` (table), any state. No single route crosses both; a child who rereads meets both.
- Quoted: "The inner ring turned under her hand until A met D and B met E. ... Every letter had stepped three places
  on." versus "down the other ran the alphabet again, shuffled" and "the alphabet and a shuffled alphabet".
- Why: the same note on the same key must decode the same way on every route, and a shuffled substitution and a shift
  are different codes. The tools may differ by design (Ellery: "Behind each one I left a way to read that note"); the
  code cannot.
- Fix: the cabinet ledger's table is now the alphabet against the alphabet "started at D. Every letter sat three
  places on from its partner" (`k_cabinet`) and "the alphabet again, starting three letters on"
  (`k_display_careful`). The shared decoding node `n_cipher` now states the rule for every reader: "Each letter
  stepped three places back, so every D became an A." The portrait wheel, the notebook's worked line and
  `e_set_broken_case`'s "two columns of letters" were already compatible and are unchanged. Plan:
  `cipher_substitution_table` removed; `k_cabinet`, `k_display_careful` and `n_cipher` establish `cipher_shift_three`;
  `e_set_broken_case` establishes `cipher_tool`.

**F3. Times that are false on the clockwork route.** Class `unestablished_fact_on_route`.

- Nodes: `v_map`, `v_share`.
- Route: `... c_rot_records > c_records_guard > c_guard_vault > c_vault_map` (and `> c_vault_share`), any state.
- Quoted: "Her phone said five in the morning." (`v_map`); "Gray light was creeping into the rotunda." (`v_share`).
- Why: on this route the rounds-book clock read "sixteen minutes to four" a moment before she went down, and `v_map`
  and `v_share` follow `n_vault` with nothing in between. Other routes fix no hour at all.
- Fix: `v_map` now says "Up above, the long night was wearing thin."; in `v_share` the gray-light sentence is replaced
  by "into the hush of the rotunda." Both are true on every route.

**F4. Nadia leaves a locked museum by a way that does not exist.** Class `unestablished_fact_on_route`.

- Nodes: `e_win_donate`, `e_neutral_evidence`, `e_win_quiet_keeper`, `v_share_secret`.
- Routes: `... c_vault_share > c_share_museum > c_museum_end`; `... c_vault_map > c_map_photo > c_photo_end`;
  `... c_vault_letter > c_letter_keep > c_keep_end`; `... c_vault_share > c_share_secret`; any state.
- Quoted: "Nadia was out through the garden gate before the first keys rattled in the staff door." / "Nadia headed out
  through the garden gate into the gray dawn" / "Nadia slipped out at dawn" / "She let herself out by the garden gate".
- Why: `n_open` establishes that the doors are locked, and the whole book depends on it; only the founder's garden
  door (`v_map_back`, read-back route) gives a way out. `e_win_donate` even has her out before anyone unlocks a door.
  `e_set_dawn` already had it right: she leaves when "the first keys of the morning" open the staff door.
- Fix: each exit now waits for the first keys of the morning to open the staff door, then uses the garden gate,
  matching `e_set_dawn`. Plan: new fact `staff_door_morning`, established by those four nodes and `e_set_dawn`.

**F5. The slab is open, closed, or closes by itself depending on the route, and one ending needs it shut.** Class
`state_contradiction`.

- Nodes: `v_share` ("the marble stood open behind her"), `v_letter_keep` ("at the top the marble slid shut behind
  her"), `v_share_secret` > `e_win_secret_kept`, `v_share_museum`.
- Route: `... c_set_vault > c_vault_share > c_share_secret > c_secret_end`, any state.
- Quoted: "and the marble stood open behind her." then, weeks later, "Tess kept watch for the guard while Nadia set
  the rings, and for one minute the two of them stood on the top step of the hidden stair".
- Why: on the secret route she leaves the floor standing open in a museum that opens in the morning, yet the room is
  still undiscovered on the next school visit. In `v_letter_keep` the marble shuts by itself when she climbs out, while
  in `v_share` and `e_set_caught` it stays open after she climbs out, so a rereader meets a mechanism that behaves two
  ways.
- Fix: `v_share` no longer says where the slab is. Nadia pushes it back into place herself where the scene needs it
  shut: `v_letter_keep`, `v_share_secret`, and `v_share_museum` (whose note tells the museum to set the rings and go
  down). `v_share_curator` keeps the open floor, which is now true because nothing closed it. Plan: new fact
  `slab_closed_by_hand` on those three nodes.

**F6. The guard's humming is presupposed on routes that never heard it.** Class `unestablished_fact_on_route`.

- Nodes: `n_rotunda`, `ro_pym`.
- Route: `c_open > c_desk_chalk > c_desk_chalk_go > c_start_gems > c_gems_case > c_gems_vitrine > c_vitrine_go >
  c_corridor_key > c_key_founder > c_founder_desk > c_desk_study > c_study_cipher > c_cipher_stars > c_stars_dome >
  c_dome_rotunda > c_rot_records > c_records_note > c_note_desk`, state C, G, T.
- Quoted: "Nobody was humming." (`n_rotunda`); "he was older than his humming" (`ro_pym`).
- Why: Nadia hears the guard hum only in `a_gems_alarm` or `k_display`. Every route that skips both (most archive,
  Egypt, study and back-stair routes) has never heard him.
- Fix: `n_rotunda` now ends "The room seemed empty."; `ro_pym` says "he was older than Nadia had pictured".

**F7. "The big arch" is named as known on routes that never saw it.** Class `unestablished_fact_on_route`.

- Node: `e_win_lost_wing` (flowed after `v_map_follow`).
- Route: `... c_set_vault > c_vault_map > c_map_follow > c_follow_end`, any state, on every route that skipped
  `b_egypt_wedge` (only the read-back Egypt route shows arch 29; `e_set_locked_gallery` is an ending).
- Quoted: "Then the bricks came out of the big arch,".
- Fix: "Then the bricks came out of an old arch in a roped-off gallery,". Plan: new fact `east_wing_paintings`, the
  wing's paintings that `v_map_follow` and `e_win_founders_door` assert, so the plan carries what those passages say.

**F16. A lamp and table appear from nowhere, and the plan credits the node with a fact its text never states.** Class
`unestablished_fact_on_route`.

- Node: `k_display_careful` (it flows straight to `n_cipher` and skips `k_study`).
- Route: `... c_corridor_key > c_key_display > c_display_force > c_force_careful`, any state.
- Quoted: "She carried it to the small table by the landing window, pulled the chain of the green lamp, and untied
  the note from her key."
- Why: "the small table" and "the green lamp" are definite on a route that never introduced them (`k_display` and
  `k_display_force` mention no table or lamp). The plan credited this node with `reading_lamp_bulb` (someone keeps
  changing the bulb), the fact the glasses payoff `v_letter_ps` leans on, but the text never said the lamp lit. (The
  payoff is not reachable from this route, because the glasses and the cabinet sit behind different locks, so the
  defect is the unintroduced objects and the plan claim.)
- Fix: "She carried it to a small reading table by the landing window and pulled the chain of its green-shaded lamp.
  Green light fell across the table, so someone had been changing the bulb. She untied the note from her key."

### Minor

| Id | Node | Route and state | Quoted | Why | Fix |
| --- | --- | --- | --- | --- | --- |
| F8 | `e_set_caught` | `... c_vault_grab > c_grab_run > c_run_end`; T false | "with the owl chiming away in her coat pocket" | `v_grab_run` puts the bells under the shelf; the owl only ticks | "with the owl ticking away in her coat pocket" |
| F9 | `n_vault` (`v_share`, `v_share_curator` lean on it) | `... c_vault_share > c_share_curator`; any | "a letter addressed to the finder" while still sealed | the address appeared only inside the letter ("To the finder," it began) | `n_vault`: "A sealed letter marked \"To the finder\" leaned on the nearest shelf" |
| F10 | `v_letter` | `... c_vault_letter`; any | "One record remains, friend, so key in forty" | records 39 (workshop) and 40 both remain unheard on every vault route | "My last record is waiting, friend, so key in forty" |
| F11 | `n_open` | start; any | "A pencil had ringed a wing that no longer stood" | contradicts `truth` and `v_map` ("bricked up but never pulled down") | "a wing she had never seen on any plan of the museum" |
| F12 | `n_key` | `... c_corridor_key`, then `c_key_stairs`; any | "all in my rooms at the top of the house: ... my back stair" | `k_stairs` puts the back stair door downstairs, behind the cloakroom | "and all of them lead to my rooms at the top of the house" |
| F13 | `ci_clock_pendulum` | `... c_cipher_clock > c_clock_pendulum`; any | "swung right across the only doorway out of the corridor" | `ci_clock` shows a second door (the gear room) and the way she came in | "swung right across the doorway at that end of the corridor" |
| F14 | `c_archive_chalk` | `c_open > c_desk_chalk > c_desk_chalk_go > c_start_archive > c_arch_dark > c_dark_chalk`; C | "The white letter on the next shelf end was Q." | she is in true dark after one second of phone light | "In the same second of light she read the white letter on the next shelf end. It was Q." |
| F15 | `a_gems_hide` | `... c_gems_alarm > c_alarm_hide`; any | "as if he had come in that way" | the corridor behind that door is a dead end (`a_gems_corridor`) | "as if he had just looked in there on his rounds" |
| F17 | `c_archive1` | `... c_start_archive`; any | "\"Stop thirty-one,\" said the handset" | every other stop is keyed in by Nadia; here the handset speaks unprompted | "Nadia keyed in the number painted by the door." added before it |
| F18 | `v_share_curator` | `... c_vault_share > c_share_curator`; any | "and at the open floor beside the globe" | the two of them are standing at the staff door | "Then she followed Nadia to the rotunda and looked for a long time at the open floor beside the globe." |
| F19 | `v_share_museum` | `... c_vault_share > c_share_museum`; any | "She carried both halves of the map to the guard's desk" | `v_share` has her come up with only the letter; the shelf half is still below | "She went back down for the shelf's half of the map and laid both halves on the guard's desk" |

## Checked and left unchanged (not defects)

- **The token and the key are each found in three places on three routes.** Same object, never twice on one route,
  and the book's stated design ("I was never a man for one door"). Unlike F1, nothing about the object itself changes
  between routes.
- **The cipher tools differ by route** (notebook, wheel, ledger table, dial, chart). That is by design; after F1 every
  tool fits the one three-place shift.
- **"The phone was the only light" (the editor's warning).** `n_vault` says "lit only by the glow of her phone".
  Checked on every route: the power-cut torch dies and is set down in `b_egypt_torch`; the archive lantern is hung at
  the row end in `c_archive_lantern`; Pym's torch appears only in endings or before the vault. No lit prop reaches
  `n_vault`.
- **Nodes the editor said were not reread after late reading-level patches.** `v_map_follow`, every `v_share_*`,
  `v_letter_keep` and their endings were read flowed with their predecessors in every state; what turned up there is
  F3, F4, F5, F7, F9, F18 and F19.
- `e_neutral_call_home`'s "the brass key on his desk": she set it down while she waited. Implied, not a contradiction.
- `a_gems_corridor` and `b_egypt_hall` share a sentence about the silent handset; they are on exclusive routes.
- Plan SP-4 note: `e_set_locked_gallery` establishes `map_back_warning` on the unplanted route. That ending is the
  reveal (its `gift`), so this is intended.
- An agency observation outside this read's definition: `c_letter_ps` (the glasses payoff) leads to the same node as
  `c_letter_reveal`, so the postscript pays off only within its own scene. Recorded, not changed.

## After the fix

- Bodies changed in 25 nodes. No label, id, choice, target, condition, effect, variable, node or ending changed
  (checked by comparing the two files with every body and label stripped).
- The full configuration walk was re-run on the fixed book (584 configurations, same routes), and all 80 flowed
  screens were re-read in every state: **zero open findings**. One wording slip introduced by the fix (`n_rotunda`
  said "inside" twice) was corrected in the same pass.
- The plan was updated to match: contradicting facts removed, three facts added (`staff_door_morning`,
  `slab_closed_by_hand`, `east_wing_paintings`), `establishes` and `requires` updated, and provenance records the
  revision and the new book hash. Every referenced fact is defined, every defined fact is used, no fact still carries
  `contradicts`, and every node's `requires` is guaranteed on entry on every route.
