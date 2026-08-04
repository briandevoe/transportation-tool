# Function suite design

Design notes for turning this repo's layer scripts into a real, reusable
library -- one prep function per layer plus a core accessibility-computation
engine, replacing the archived one-off `analysis/` scripts (see
`archive/transportation-tool-analysis-visualization-scripts/` next to this
repo). **Status: design only.** The package lives at `code/engine/` (see
"Where this lives" below) as a scaffold -- folder structure, function
signatures, and docstrings all match the design below, but only
`analysis_schema.py` and `reference_data.py` are real, working code.
Every function in `prep.py`, `network.py`, `compute.py`, and `scoring.py`
raises `NotImplementedError` -- the design is settled, the implementation
isn't started. See `docs/accessibility_models.md` for the to-do list this
unblocks.

## Why now

The archived analysis scripts duplicate real logic in multiple places --
`02_compute_travel_time_metrics.py` and `05_build_simple_model.py` each
independently rebuild an igraph graph and a cKDTree for snapping origins to
nodes. Every new accessibility model (gravity, 2SFCA, PWD -- see
`accessibility_models.md`) would otherwise mean another script repeating
that same setup. A shared function suite fixes that once.

## Where this lives

`code/engine/` -- not `code/lib/` (that's shared *prep* infrastructure:
download clients, weighting math, the schemas layer1-4's own scripts
validate against) and not a separate top-level package (yet -- see
"Packaging" below). `engine/` is the *consumption*-side counterpart to
`lib/`'s prep side: it reads already-standardized layer output and computes
accessibility from it. The name matches the README's own title
("Transportation Accessibility Engine"). Layout:

```
code/engine/
  __init__.py          # public API surface
  prep.py              # get_geography(), get_population(), get_network(), get_destinations()
  network.py           # the Network class
  compute.py           # compute_matrix()
  scoring.py           # score()
  analysis_schema.py   # moved from lib/ -- the metrics-output schema
  reference_data.py    # moved from lib/ -- Layer 5 discovery/join
```

`analysis_schema.py` and `reference_data.py` moved here from `code/lib/`
for the same reason: they define the engine's output contract and the
post-hoc reference join, not something layer1-4's prep scripts touch.

## The four prep functions (`engine/prep.py`)

Each loads and validates already-processed layer output -- no downloading,
no building. That stays the job of the existing CLI scripts in
`code/layer1_geography/` through `code/layer4_destination/` (see their
`README.md`s); these functions are the fast, in-memory "assemble already-
prepared layers" step that sits on top.

```
get_geography(state_fips="25", geography_type="tract", vintage="2020") -> GeoDataFrame
get_population(state_fips="25", race_scheme="coi_5", characteristics=["N/A"]) -> DataFrame
get_network(state_fips="25", source="osm") -> Network
get_destinations(dest_type="hospital", state_fips="25") -> DataFrame
```

Column shapes for these are already locked by layer1's standardize output,
`code/lib/population_schema.py`, and `code/lib/destination_schema.py`
respectively -- these functions don't invent new schemas, they just load
what's already standardized.

## The `Network` class (`engine/network.py`)

The fix for the duplicated graph-build/snap logic:

```
class Network:
    def snap(self, lats, lons) -> node_indices           # cKDTree snap, done once
    def matrix(self, origin_nodes, dest_nodes) -> ndarray  # batched multi-source Dijkstra
```

Built once per `get_network()` call, reused for every routing call against
it, instead of every script rebuilding both from scratch.

## Routing vs. scoring: two composable stages, not one function (`engine/compute.py`, `engine/scoring.py`)

`docs/overview.md` already calls this out as a real distinction. Splitting
it means a new accessibility model only ever needs a new `score()` function,
never new routing code:

```
compute_matrix(origins, destinations, network=None, algorithm="dijkstra") -> long DataFrame
    # origin_id, dest_id, value, unit
    # algorithm="euclidean" ignores `network` entirely
    # algorithm="dijkstra" requires it
    # a future algorithm="transit" would need GTFS data on top of a Network

score(matrix, population, metric="cumulative_opportunity", **params) -> metrics DataFrame
    # metric="nearest" | "k_nearest" | "within_threshold" | "gravity" | "2sfca" | "pwd"
    # e.g. score(matrix, population, metric="gravity", decay="exp", beta=0.1)
```

`algorithm=` is a dispatcher, not a strict drop-in interface -- different
algorithms genuinely need different required inputs (notes.md already flags
this).

## Schema decisions (the part that's actually done)

Three different levels of rigidity, on purpose:

1. **Layers 1-4 stay strictly schema'd.** They're engine inputs -- the
   routing/snapping/scoring logic reads specific columns from them
   (`lat`/`lon` to snap, `length_m`/`speed_kph` for travel time,
   `population` to weight a centroid) to actually compute something. Their
   schemas (`network_schema.py`, `population_schema.py`,
   `destination_schema.py`) are unchanged by this design.

2. **The metrics output (`code/engine/analysis_schema.py`) is now a small
   fixed spine plus flexible columns.** Required: `GEOID`,
   `geography_level`, `state_fips`, `race_ethnicity`, `characteristic`,
   `dest_type`, `algorithm` -- the identity/join keys every downstream
   comparison needs. NOT fixed: the metric value column(s) themselves
   (`nearest_time_min`, `gravity_value`, `n_within_5mi`, ...) -- name them
   descriptively with the unit baked into the name (a single row can carry
   several differently-unitted metrics side by side), and adding a new
   metric never requires editing the schema file. `population` is expected
   to almost always be present but isn't enforced -- it's an attribute, not
   an identity key.

   One shape doesn't fit this at all: **Population-Weighted Distance is a
   single number per geography** (e.g. one number for all of
   Massachusetts), not one row per origin like the others. It's a
   reduction over the per-origin table, not a row that belongs in the same
   metrics table.

3. **Layer 5 reference data (`code/engine/reference_data.py`) is fully
   discovery-driven, not schema'd at all.** It's never touched by the
   engine -- purely a post-hoc GEOID join for grouping/comparison, so there's
   no engine-side reason to lock its shape down. `attach_reference_attributes()`
   now globs `data/layer5_reference/*/processed/*.parquet`, left-joins
   whatever it finds by `GEOID`, and requires nothing else. Adding a new
   reference source (crash data, transit frequency) is zero code changes --
   just land a GEOID-keyed parquet in the right folder. The only convention
   worth keeping: prefix ambiguous column names with the source's own name
   (`coi_vintage`, not `vintage`) so two sources never collide when joined
   back to back.

## Open questions -- not decided yet

- **Packaging.** Does "library" mean a real installable package
  (`pyproject.toml`, a proper import name, eventually `pip install`-able for
  outside researchers) or does `code/engine/` stay internal-only, imported
  the way this repo's own scripts import from `code/lib/` today? Not
  urgent -- promoting `code/engine/` to a repo-root package later is a
  mechanical move, not a redesign, so this doesn't block building it out
  as internal modules now.
- **2SFCA's destination-side catchment computation** is the one metric that
  needs a genuinely new kind of input (population reachable *from* each
  destination, not just origins reachable *to* destinations) -- not just a
  new `score()` function like gravity/PWD are.
