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

Shared code (schemas, download clients, the routing/accessibility helpers
every layer uses) lives in `code/lib/`.

## How to run something

Every prep script takes command-line flags (state, year, race scheme, etc.)
-- run any script with `--help` to see its options:

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

## Folder structure

```
code/
  layer1_geography/    layer2_network/    layer3_population/
  layer4_destination/  layer5_reference/  lib/

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
  accessibility_models.md   # to-do list of accessibility models to build
  emilie_tasks.txt          # current week's task list
  COI 3.0 Technical Documentation 20250724.pdf
```

## Current status

Layers 1-4 have real, working code -- see `docs/notes.md` for the detailed,
per-layer status and `docs/accessibility_models.md` for what's built vs.
what's next. The next major step is designing a shared function suite that
brings all four layers together into one reusable accessibility-computation
engine (`docs/accessibility_models.md`'s first to-do item) -- not started
yet, a design discussion before any code gets written.
