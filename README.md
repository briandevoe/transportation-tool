# Transportation Accessibility Engine

A tool for measuring how easily different populations can reach important
places -- schools, hospitals, grocery stores -- across the United States.
Built for equity and policy research, not for turn-by-turn navigation.

    population (by geography, by demographic group)
        --travels via--> a network (roads, transit, sidewalks, bike lanes...)
        --to reach--> destinations (schools, hospitals, grocery stores...)
        = accessibility metrics, joinable by GEOID to reference data
          (COI, Opportunity Atlas, redlining maps, ...)

## Why this exists

The Child Opportunity Index (COI) measures whether a neighborhood *has*
resources nearby. It doesn't measure whether a specific person can actually
*reach* those resources. This tool answers that second question:
population-weighted, demographic-sliced, routed accessibility to real
destinations -- meant to sit alongside COI and similar datasets, not inside
them.

## The five layers

Every analysis this tool runs combines five independently swappable inputs.
Layers 1-4 feed the engine; Layer 5 is external data the engine's output
gets joined to afterward, not something the engine computes.

| Layer | What it covers | Code |
|---|---|---|
| **1. Geography** | Census tracts, block groups, blocks, ZCTAs, counties, congressional districts, school districts | `code/layer1_geography/` |
| **2. Travel network** | Roads, sidewalks, bike lanes, buses | `code/layer2_network/` |
| **3. Population** | Total population, age groups, disability status, race/ethnicity, population-weighted centroids | `code/layer3_population/` |
| **4. Destinations** | Schools, hospitals, grocery stores | `code/layer4_destination/` |
| **5. Reference data** | COI, RUCA, redlining -- external, joined by GEOID | `code/layer5_reference/` |

Shared prep infrastructure (schemas, download clients, weighting math that
layer1-4's own scripts use to produce their output) lives in `code/lib/`.

The function suite that actually *consumes* Layers 1-4 to compute
accessibility -- turning all of this into a reusable library instead of
one-off scripts -- lives in `code/engine/`. Design only right now, not yet
implemented: see [`docs/function_design.md`](docs/function_design.md).

## How to run something

Every layer folder has its own `README.md` with that layer's scripts, run
order, and any prerequisites -- start there:
[`code/layer1_geography/README.md`](code/layer1_geography/README.md) ·
[`code/layer2_network/README.md`](code/layer2_network/README.md) ·
[`code/layer3_population/README.md`](code/layer3_population/README.md) ·
[`code/layer4_destination/README.md`](code/layer4_destination/README.md) ·
[`code/layer5_reference/README.md`](code/layer5_reference/README.md)

Every prep script takes command-line flags (state, year, race scheme, etc.)
-- run any script with `--help` to see its options, and **every script
defaults to Massachusetts** if you don't pass `--state-fips`:

```
python code/layer1_geography/01_download_tiger.py --help
```

Some scripts also have a paired `01_run_*.py` "convenience runner" sitting
next to them -- open that file, edit the config values at the top (state
list, year, etc.), and just hit Run instead of typing flags into a
terminal. Both versions call the same underlying code, so use whichever is
easier.

Scripts are numbered in the order you'd normally run them within a layer
(e.g. `01_download_tiger.py` before `04_standardize_geographies.py`) --
later layers depend on earlier ones (Layer 3's population centroids need
Layer 1's geography, for example).

## Getting Massachusetts data end-to-end

Two things to line up before running anything:
- A free Census API key (Layer 3 and one Layer 5 script need it) --
  https://api.census.gov/data/key_signup.html, then set `CENSUS_API_KEY`.
- A few Layer 4/5 scripts (schools, COI, RUCA, redlining) read a raw source
  file that has to already exist locally -- `data/` isn't in git, so a
  fresh clone has none of them. See each layer's README for exactly which
  file and where it goes; ask Brian for copies rather than re-downloading
  if you're not sure you have the current version.

With those in place, running every layer for Massachusetts (the default
everywhere) looks like:

```
# Layer 1: geography
python code/layer1_geography/01_download_tiger.py
python code/layer1_geography/02_download_congressional_dist.py
python code/layer1_geography/04_standardize_geographies.py

# Layer 2: network
python code/layer2_network/01_download_osm_roads.py

# Layer 3: population (needs CENSUS_API_KEY)
python code/layer3_population/01_download_acs_population.py
python code/layer3_population/02_build_centroids_block_group.py
python code/layer3_population/03_build_centroids_block.py

# Layer 4: destinations (schools needs its manual files in place first)
python code/layer4_destination/02_prepare_grocery_osm.py
python code/layer4_destination/03_prepare_hospitals_osm.py

# Layer 5: reference data (COI/RUCA/redlining need their manual files first)
python code/layer5_reference/04_prepare_vehicle_availability.py
```

## Folder structure

```
code/
  layer1_geography/    layer2_network/    layer3_population/
  layer4_destination/  layer5_reference/  lib/
  engine/               # the accessibility function suite -- design-only
                        # stubs today, see docs/function_design.md

data/
  layer1_geography/raw/        # untouched downloads, by vintage
  layer1_geography/processed/  # standardized output (GEOID, geometry, ...)
  layer2_network/  layer3_population/  layer4_destination/  layer5_reference/

outputs/     # accessibility results, once the pipeline runs end-to-end

docs/
  overview.md               # background research: data sources, routing
                             # algorithms, and libraries considered per layer
  notes.md                  # engineering log -- decisions, bugs found and
                             # fixed, and the reasoning behind each layer
  function_design.md        # design (not yet implemented) for the shared
                             # accessibility function suite/library
  accessibility_models.md   # to-do list of accessibility models to build
  emilie_tasks.txt          # current week's task list
  COI 3.0 Technical Documentation 20250724.pdf
```

## Planned usage (not runnable yet)

`code/engine/` is a scaffold right now -- every function below raises
`NotImplementedError`. This is the interface it's being built to, so you
can see where the project is headed; keep this block in sync as `engine/`
actually gets implemented (see `docs/function_design.md`).

```python
from engine import get_population, get_network, get_destinations, compute_matrix, score, attach_reference_attributes

# 1. Load already-prepared layers for a state (fast -- just reads parquet)
population = get_population(state_fips="25")                          # layer 3
network    = get_network(state_fips="25")                              # layer 2
hospitals  = get_destinations(dest_type="hospital", state_fips="25")   # layer 4

# 2. Route (layers 2+3+4 combine here)
matrix = compute_matrix(population, hospitals, network=network, algorithm="dijkstra")

# 3. Score (turn the matrix into a metric)
metrics = score(matrix, population, metric="nearest")   # one row per GEOID x race_ethnicity x characteristic

# 4. Attach Layer 5 -- a join, not part of the computation
metrics = attach_reference_attributes(metrics)           # adds coi_level_nat, ruca_code, redlining_grade, ...

# 5. The actual research question -- plain pandas, not part of the engine at all
metrics.groupby("race_ethnicity")["nearest_time_min"].mean()
```

Steps 1-3 are what the engine standardizes across every use of this tool;
step 5 is disposable, question-specific analysis that changes every time.

## Current status

Layers 1-4 have real, working code -- see `docs/notes.md` for the detailed,
per-layer status and `docs/accessibility_models.md` for what's built vs.
what's next. `code/engine/` now exists as a scaffold (folder + function
signatures + docstrings, matching `docs/function_design.md`), but every
function in it still just raises `NotImplementedError` -- the design is
settled, the implementation isn't started.
