# Skeleton design report: The Blackwood Sanatorium

- **Slug / file**: `skeletons/16+/the-blackwood-sanatorium.json`
- **id**: `sk_blackwood_sanatorium`
- **Cell**: age_band `16+`, length `medium`, narrative_style `prose`
- **Topology**: `open_map`
- **Tier**: 1 (stateless; no variables, no conditions, no effects)
- **Nodes**: 151 (siblings: the-last-train-north 143, the-third-shift 151,
  the-quiet-harbor-protocol 153)
- **Endings**: 24

## Why this skeleton exists

The `(16+, medium, prose)` cell held `branch_and_bottleneck`,
`branch_and_bottleneck` (tier 2), and `sorting_hat`, but no `open_map`. This
adds the missing open_map so the cell samples the full topology trio, and it is
a **tier-1** open_map, adding tier diversity alongside the existing tier-2
`the-quiet-harbor-protocol`.

## Premise

Wren Colefax cuts the padlock on the condemned Blackwood Sanatorium the night
before the wrecking crews arrive. Her late aunt Miriam died a patient here, and
the sealed ledgers that could clear Miriam's name are somewhere inside. A
demolition watchman walks the building once an hour; a storm is coming; the
floors, fumes, and cold are all failing. Wren has until dawn to explore the
wings in any order and carry out proof, if any survives. Mature, lethal,
resource-of-time-based fail states are used per the 16+ policy.

## Structure: cyclic hub-and-spoke (open_map)

- **Start**: `n_arrival` (single choice) leads into the hub.
- **Hub**: `n_hub`, the central rotunda. It offers a lane into each of the nine
  wings plus an "abandon the site" ending, and is re-offered on every return.
- **Lanes (9 wings)**: each wing is a chain of "room" nodes. Every room offers
  two choices: **press deeper** (to the next room, or to the wing terminus at
  the end of the chain) and **withdraw to the rotunda** (back-edge to `n_hub`).
  These withdraw edges are what make the graph **cyclic**, which is the defining
  primitive of open_map (hub -> room -> hub loops). The classifier
  (`validator/topology.py`) returns `{loop_and_grow, open_map}` for any cyclic
  graph, so open_map is admissible (PL-18).
- **Wing terminus**: a decision node offering the wing's endings plus a
  withdraw-to-hub edge (so terminus stays in the hub SCC and L1-5 is satisfied:
  the SCC always reaches an ending).
- **Endings**: terminal leaves hanging off the termini, plus the one hub-level
  "abandon" ending.

Wing room counts: flooded stairwell 16, hydrotherapy 13, cold rooms 13, chapel
12, boiler house 12, superintendent's wing 16, dormitories 11, dispensary 12,
attic 11.

## Tier justification

Tier 1 (stateless) is clean and sufficient here: the open map is a set of
locations the reader visits in any order, and no location needs to remember
another. The "you can leave anytime" hub ending, the per-wing fail states, and
the two deep win routes are all reachable through pure edges, so no variables,
conditions, or effects are required. This satisfies the brief's tier-1
preference and the tier-1 open_map invariant (a clean cyclic hub-and-spoke that
re-offers all lanes on return).

## Endings (24): kinds and valences

- kinds: completion 1, success 1, discovery 8, capture 5, death 5, setback 4
- valences: positive 2, neutral 8, negative 14

The two **satisfying** endings (kind success/completion, the only kinds PL-20
gates on) are placed at the ends of the two deepest 16-room wings:

- `e_stair_1` **The Ledger Carried Down** (completion, positive), shortest path
  20 nodes.
- `e_office_1` **The Signed Hand** (success, positive), shortest path 20 nodes.

Both are >= the `(16+, medium, prose)` fastest-finish floor of 18 nodes, so
PL-20 passes. All other "good-feeling" outcomes are typed `discovery` (neutral,
e.g. the attic cache found but rain-ruined), which do not trip the arc floor and
can sit shallower in the map. The remaining endings are the mature fail states
the 16+ band allows: entrapment (`capture`), lethal accidents and gas
(`death`), and non-lethal retreats (`setback`).

## Validator invariants checked

- **Cyclic graph** (`is_directed_acyclic_graph` is False), so open_map is in the
  admissible set (PL-18) and L1-7 branch-depth is skipped for the cyclic
  subgraph.
- **L1-3/L1-4**: every node reachable from `n_arrival`; every non-ending node
  has >= 1 choice and a path to an ending.
- **L1-5**: the hub SCC reaches endings via each wing terminus.
- **PL-17 floors** (breadth-scaled, prose): min_endings ceil(151*0.15)=23 (have
  24), min_decisions ceil(151*0.08)=13 (have 126 decision nodes).
- **PL-19**: FILL word targets (rooms/termini/hub 155-170, endings 140, arrival
  185) are all under the 16+ prose per-node max 385; story mean is inside the
  125-230 advisory band.
- **Node envelope**: 151 within the cell's 135-215.
- No em-dash (U+2014) anywhere in the file.

## check_skeleton result

Command:

```
uv run python scripts/check_skeleton.py skeletons/16+/the-blackwood-sanatorium.json \
    --band 16+ --length medium --style prose --topology open_map --tier 1
```

Final output (exit 0):

```
stats: nodes=151 endings=24 fill_nodes=151 cell=(16+, medium, prose) topology=open_map tier=1
ok: skeleton passes gate and brief checks
```
