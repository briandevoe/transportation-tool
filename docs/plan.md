# Development plan

## Architecture decisions (settle these before/alongside layer work)

- [ ] Lock the standardized schema each layer must output (geography, population,
      network, destinations), keyed by GEOID with an explicit vintage field --
      this is the one decision that's expensive to redo later
- [ ] Design the library's public API: one prep function per layer
      (`get_geography()`, `get_population()`, `get_network()`, `get_destinations()`)
      returning standardized objects, plus one core function
      (`compute_accessibility(geography, network, population, destinations,
      algorithm=...)`) that runs routing + scoring against already-prepared
      inputs. Keeps expensive one-time prep (esp. network building) separate
      from cheap repeated computation.
- [ ] Design the algorithm dispatch layer -- Dijkstra, Euclidean, and future
      RAPTOR/transit routing all need different inputs, so `algorithm=` is a
      dispatcher, not a literal drop-in swap
- [ ] Pick a license for the repo, especially given eventual outside-researcher
      use; confirm r5r's license before depending on it; note OSM data itself
      is ODbL (share-alike on redistributed derived datasets, not just code)
- [ ] Write up the tool landscape comparison (Conveyal Analysis, Urban
      Institute's Spatial Equity Data Tool, Spatial Access of America) --
      promised as a follow-up in the COI proposal thread

## Layer 1: Geography

- [x] Download 2020 TIGER/Line tract, block group, block, and ZCTA boundaries
      for all states (`code/layer1_geography/01_download_tiger.py`)
- [ ] Verify completeness/integrity of downloads across all states and
      geography types
- [ ] Standardize into the common schema (GEOID, geometry, vintage)
- [ ] Join in RUCA codes as a filterable reference field (2020 tract and ZIP
      data already in `data/reference/ruca/`) so users can subset to
      urban-only, rural-only, or any RUCA class
- [ ] Make geography vintage a first-class, switchable parameter, not
      hard-coded -- bit the previous version once already (2010 vs. 2020 tract
      mismatch against COI data)
- [ ] Add congressional districts (needs an explicit redistricting-cycle
      vintage field)
- [ ] Treat COI, RUCA, redlining maps, and the Opportunity Atlas as a
      candidate fifth "reference data" layer, joinable by GEOID

## Layer 2: Travel network

- [ ] Port the pyrosm/igraph driving-network builder from `../transportation2`
- [ ] Carry forward known fixes: restrict to the standard drivable-highway tag
      set, run `osmnx.simplify_graph()`, chunk large states by recursive
      median split (not a uniform grid)
- [ ] Decouple network-chunk size (memory-driven) from origin-batch routing
      size, so moving from tracts to finer geographies stays tractable
- [ ] Add sidewalks and bike lanes as network types (OpenStreetMap-based)
- [ ] Add straight-line (Euclidean, optionally circuity-adjusted) as a
      no-network option for destination types where proximity itself is the
      exposure (hazard sites, etc.)
- [ ] Prototype r5py for future transit routing (proper GTFS schedule
      handling, RAPTOR-based)
- [ ] Revisit OSRM/Contraction Hierarchies if Docker becomes available
- [ ] Still-open problem: `pyrosm`'s `get_network()` rescans the entire PBF
      per chunk -- worth a one-time spatial pre-index before this scales up

## Layer 3: Population

- [ ] Port ACS download/reshape logic from `../transportation2`
      (total/age/race)
- [ ] Add disability status stratification (new ACS table, same pattern)
- [ ] Pull decennial block-level race/ethnicity counts -- the finest
      resolution Census publishes race at, and what makes within-tract
      demographic weighting possible (ACS itself bottoms out at block group)
- [ ] Compute population-weighted centroids: tract geographic center by
      default, plus race/ethnicity-specific centroids using block-level
      weighting
- [ ] Add ACS vehicle-availability-by-household data (block-group level), to
      support car-access-by-demographic-group analysis

## Layer 4: Destinations

- [ ] Establish the standard destination schema: location, category, source,
      plus optional quality attributes
- [ ] Build the first prep script: schools, including quality attributes
      (e.g. percent experienced teachers) -- check what COI already collects
      before sourcing from scratch
- [ ] Build additional prep scripts as prioritized: hospitals, grocery stores
      (with a healthy-food attribute), pharmacies, polling places
- [ ] Add hazard/negative-destination support (flood risk, TRI sites, etc.)
      using the straight-line-distance network option

## Core engine (routing + accessibility scoring)

- [ ] Define the common interface every algorithm must implement (inputs:
      network/points; output: a travel-time matrix)
- [ ] Implement Dijkstra/igraph-based routing (already proven)
- [ ] Implement the Euclidean/straight-line distance option
- [ ] Implement r5py-based routing (for transit)
- [ ] Keep routing and accessibility scoring as separate pipeline stages
      (contour, gravity-weighted, nearest-time, etc.)
- [ ] Implement the main library function(s) described in the architecture
      section above

## Outputs

- [ ] GEOID-joinable output format for joining to COI, Opportunity Atlas,
      redlining maps, and other tract-level datasets
- [ ] Optional RUCA/urban-rural filtering on output
- [ ] Documentation aimed at outside-researcher use, not just internal use
