# Transportation Accessibility Engine

A general-purpose tool for computing **population access to opportunity**
across the United States — built for equity and policy research, not general
navigation.

    population (by geography, by demographic group)
        --travels via--> a network (roads, transit, sidewalks, bike lanes...)
        --to reach--> destinations (schools, hospitals, grocery stores...)
        = accessibility metrics, joinable by GEOID to any other tract-level
          dataset (COI, Opportunity Atlas, redlining maps, flood risk, ...)

This is a fresh repo. An earlier single-purpose version (tracts only, driving
only, three destination types) lives at `../transportation2` — working,
validated code and the source of real lessons (an igraph-based routing engine,
a pyrosm-based road network builder, ACS download logic) that this rewrite
carries forward deliberately rather than starting from zero knowledge. See
`docs/reference.md` for the fuller design discussion this repo grew out of,
including a longer list of routing algorithms, candidate libraries, and
possible destination types.

## The four layers

Every analysis this tool runs is a combination of four independently
swappable inputs. The core engine (routing + accessibility scoring) doesn't
change based on which layer choices feed it — it only ever needs a
standardized origin schema, a standardized network graph, and a standardized
destination schema. Making each layer conform to that standard, one prep
script per data source, is the whole job of this rewrite.

| Layer | Examples | Status |
|---|---|---|
| **Geography** | Census tracts, block groups, blocks, ZCTAs, congressional districts | Starting now — see `code/layer1_geography/` |
| **Travel network** | Roads, sidewalks, bike lanes, buses, trails | Not started here (roads exist in `../transportation2`) |
| **Population** | Total, age groups, disability status, race/ethnicity | Not started here (partial version in `../transportation2`) |
| **Destinations** | Schools, hospitals, grocery, pharmacies, and more | Not started here (pattern proven in `../transportation2`) |

## Why this isn't Conveyal Analysis

The closest existing tool (Conveyal Analysis, built on R5) is a general
"population access to jobs/opportunity" platform. This one is narrower on
purpose: built for equity and policy analysis specifically (e.g. "do disabled
Black residents have less transportation access to flood-risk areas in New
Orleans"), with a demographic-subgroup-first population layer and output
always keyed by GEOID so it drops straight into a join with COI, the
Opportunity Atlas, redlining maps, or any other tract-level dataset a
researcher is already using — this tool doesn't need to contain those
datasets, just produce output that joins to them trivially. (A thorough check
of the current tool landscape is still pending before leaning on this as a
funding pitch.)

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

## Folder structure

```
code/
  layer1_geography/     # tract/block/block group/ZCTA/congressional district prep
  layer2_network/        # road/sidewalk/bike/transit network builders
  layer3_population/     # ACS pulls by demographic group
  layer4_destination/    # per-destination-type prep scripts
  (a shared lib/ for the standardized schemas + the routing/accessibility
   engine will land once there's more than one layer script to share it)

data/
  layer1_geography/
    2020/                # vintage-specific subfolder -- one per Census vintage
  layer2_network/
  layer3_population/
  layer4_destination/

outputs/
  (travel times, accessibility metrics, comparisons -- populated once the
   pipeline actually runs)

docs/
  reference.md           # routing algorithms, candidate libraries, destination ideas
```

## Current focus

Layer 1 (Geography), 2020 vintage only: pull tract, block group, block, and
ZCTA boundaries from the Census Bureau's TIGER/Line data for all states, into
`data/layer1_geography/2020/`. See `docs/plan.md` for the full development
plan and todo list, broken down by layer.
