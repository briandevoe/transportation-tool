# Transportation Accessibility Engine

A general-purpose tool for computing **population access to opportunity**
across the United States — built for equity and policy research, not general
navigation.

    population (by geography, by demographic group)
        --travels via--> a network (roads, transit, sidewalks, bike lanes...)
        --to reach--> destinations (schools, hospitals, grocery stores...)
        = accessibility metrics, joinable by GEOID to Layer 5 reference data
          (COI, Opportunity Atlas, redlining maps, flood risk, ...)

This is a fresh repo. An earlier single-purpose version (tracts only, driving
only, three destination types) lives at `../transportation2` — working,
validated code and the source of real lessons (an igraph-based routing engine,
a pyrosm-based road network builder, ACS download logic) that this rewrite
carries forward deliberately rather than starting from zero knowledge. See
`docs/reference.md` for the fuller design discussion this repo grew out of,
including a longer list of routing algorithms, candidate libraries, and
possible destination types.

## Why this exists

The Child Opportunity Index (COI) measures whether a neighborhood *has*
resources — good schools nearby, clean air, jobs, safe housing. It doesn't
measure whether a specific person, of a specific demographic group, starting
from a specific address, can actually *reach* those resources in a reasonable
amount of time by a real mode of travel. That's a different, complementary
question, and COI's own methodology deliberately stays out of it (see
`docs/COI 3.0 Technical Documentation 20250724.pdf`, "Should race/ethnicity be
included as a component indicator?", p.22, for the same reasoning applied to
race — COI measures structural features directly rather than access to them).
This tool exists to answer the access/travel-time side of that question:
population-weighted, demographic-sliced, routed accessibility to real
destinations — output that's meant to sit *alongside* COI (and other
tract-level research datasets), not inside it.

## The five layers

Every analysis this tool runs is a combination of five independently
swappable inputs. The core engine (routing + accessibility scoring) doesn't
change based on which of the first four layers' choices feed it — it only
ever needs a standardized origin schema, a standardized network graph, and a
standardized destination schema. Making each layer conform to that standard,
one prep script per data source, is the whole job of this rewrite. Layer 5 is
different in kind from the other four: it's not computed by this tool at
all, just joined to the tool's output by GEOID.

| Layer | Examples | Status |
|---|---|---|
| **1. Geography** | Census tracts, block groups, blocks, ZCTAs, counties, congressional districts, school districts, urban areas, tribal areas | Standardized schema built and verified — see `code/layer1_geography/` |
| **2. Travel network** | Roads, sidewalks, bike lanes, buses, trails | OSM (routable) and TIGER (reference) roads built and standardized; only Massachusetts fully processed so far, rest of the states queued — see `code/layer2_network/` |
| **3. Population** | Total, age groups, disability status, race/ethnicity | ACS- and Decennial-based population-weighted centroids built, with a tunable number of centroids per tract (`--k`) and swappable race/ethnicity schemes (COI's own 5-group breakdown is the default) — see `code/layer3_population/` |
| **4. Destinations** | Schools, hospitals, grocery, pharmacies, and more | Schools, grocery, and hospitals prepped from OSM/other sources — see `code/layer4_destination/` |
| **5. Reference data** | COI, RUCA, redlining maps, Opportunity Atlas | Not computed by this tool — external, GEOID-joined context for the accessibility numbers Layers 1-4 produce. COI, RUCA, and redlining already prepped — see `code/layer5_reference/` |

## Why this isn't Conveyal Analysis (or SEDT, or Spatial Access of America)

No existing tool combines real network routing, demographic-subgroup slicing
as a first-class dimension, flexible destination types, and GEOID-native
output — checked directly against the three closest candidates (2026-07-26,
see `docs/plan.md` for the full writeup):

- **Conveyal Analysis / R5 / r5py** routes well (GTFS-based transit included)
  and supports flexible destination types, but has no native demographic-
  subgroup accessibility model — Conveyal's product requires uploading one
  population layer per demographic category and running a separate job each
  time, and r5py (the Python routing engine this tool could someday sit on)
  has no accessibility function at all, just travel-time matrices. Its
  internal spatial unit is also a Web Mercator grid, not census geography —
  not GEOID-native by default. r5py is free, self-hostable, and more
  battle-tested for transit routing than a hand-rolled router — a real
  candidate for a future Layer 2 swap-in once transit enters scope, without
  touching Layers 1/3/4 or the GEOID-keyed output contract. For now this
  tool keeps its own network layer.
- **Urban Institute's Spatial Equity Data Tool** doesn't route at all — its
  core methodology is a siting/representativeness disparity score (does
  where a resource sits match the population's demographic composition),
  structurally closer to COI than to a travel-time tool. Its new
  routing-based "access measure" pilot is limited to Maryland/Virginia/DC.
- **Spatial Access of America** (Purdue, 2025) is the closest methodological
  peer — real routing, demographic-sliced job/POI access — but is a static
  published dataset covering the 50 largest urban areas, with no transit and
  no path to extend it.

## Known constraints worth remembering

- **ACS (race/age/disability) bottoms out at block group** — the Census
  Bureau does not publish those breakdowns at the block level, full stop.
  Block-level analysis will be total-population-only.
- **Geography vintages need to be switchable by year as a first-class
  parameter**, not hard-coded — this bit the previous version (a 2010-vs-2020
  tract mismatch against COI data) and matters even more once congressional
  districts (redistricting cycles) are in scope.
- **ZCTAs are not zip codes** — they're the Census Bureau's polygon
  approximation of USPS zip codes, built from block geometry.
- **School bus route data**: no known public national source. Not an
  architecture problem (any network type slots in the same way) — a
  data-availability problem to keep chasing separately.
- **Connecticut's 2022 planning-region switch** breaks any naive GEOID join
  between ACS 2022+ data and 2020-vintage TIGER geometry — the Census Bureau
  replaced CT's 8 legacy counties with 9 new county-equivalent planning
  regions, changing every CT GEOID's county segment even though tract/
  block-group boundaries never moved. Fixed via a tract-code crosswalk
  (`code/lib/ct_geoid_crosswalk.py`, applied automatically in
  `lib/acs_client.py`) — same approach the Child Opportunity Index team used
  for the same problem (see `docs/COI 3.0 Technical Documentation
  20250724.pdf`, Appendix 6).

## Folder structure

```
code/
  layer1_geography/     # tract/block/block group/ZCTA/congressional district prep
  layer2_network/        # road/sidewalk/bike/transit network builders
  layer3_population/     # ACS pulls by demographic group
  layer4_destination/    # per-destination-type prep scripts
  layer5_reference/       # COI/RUCA/redlining/Opportunity Atlas -- external
                          # datasets the engine's output joins to, not
                          # something the engine computes itself
  lib/                    # shared schemas + the routing/accessibility engine

data/
  layer1_geography/
    raw/                  # untouched TIGER/Line downloads
      2020/                # vintage-specific subfolder -- one per Census vintage
      cd118/                # congressional districts are vintaged by congress
                            # number instead, in their own cd<congress>/ folder
    processed/            # standardized output (GEOID, geometry, geography_type,
                          # vintage, state_fips, name, land/water area)
  layer2_network/
  layer3_population/
  layer4_destination/
  layer5_reference/

outputs/
  (travel times, accessibility metrics, comparisons -- populated once the
   pipeline actually runs)

docs/
  reference.md           # routing algorithms, candidate libraries, destination ideas
  plan.md                 # detailed development plan and todo list, by layer
  COI 3.0 Technical Documentation 20250724.pdf  # the Child Opportunity Index's
                          # own methodology -- our most-used Layer 5 reference,
                          # and the source for several Layer 1/3 design decisions
  Transportation Accessibility Engine Overview.pptx  # quick non-technical
                          # overview slides -- architecture/motivation/novelty,
                          # no results (see docs/plan.md for actual findings)
```

## Current focus

Building toward a first real transportation-equity accessibility measure
(demographic-sliced, routed, destination-flexible) using Layers 1-4 as they
stand today -- no restructuring of the five-layer architecture to fit any
single downstream consumer's shape, COI included. COI's role stays Layer 5:
something the tool's output joins to, not something it's built to feed.

Layers 1-3 all have substantial work in place -- see `docs/plan.md` for the
full, current, per-layer status (this README stays intentionally high-level).
Layer 1 (Geography): pull tract, block group, block, ZCTA, county, and school
district boundaries from the Census Bureau's TIGER/Line data for all states,
for both the 2010 and 2020 vintages, into `data/layer1_geography/raw/<year>/`
(`01_download_tiger.py`) -- plus congressional districts, which are vintaged
by congress number instead of census year and so get their own script
(`02_download_congressional_dist.py`) and `cd<congress>/` output folders. See
`docs/plan.md` for the full development plan and todo list, broken down by
layer.
