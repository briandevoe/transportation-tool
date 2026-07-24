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

- [x] Download 2020 TIGER/Line tract, block group, block, ZCTA, and county
      boundaries for all states (`code/layer1_geography/01_download_tiger.py`)
- [x] Download 2010 vintage too, same script (`--year 2010`) -- URL/filename
      patterns differ (nested `/2010/` subdirectory, `10`-suffixed filenames
      like `tract10`/`bg10`/`tabblock10`/`zcta510`/`county10`), verified
      against the live TIGER2010 server
- [x] `download_one()` (now shared in `code/lib/tiger_download.py`) validates
      the response is actually a zip (`PK` file signature) before counting it
      downloaded -- caught a real case where a corporate/CDN WAF block page
      came back with a 200 status and got silently saved as a `.zip`, and
      retries with backoff specifically on HTTP 429 (rate limited) rather
      than misreporting a real file as missing -- caught live requesting
      school district files back-to-back with no delay
- [x] Add school districts -- three geography types since not every state
      uses unified districts (`school_unified`/`school_elementary`/
      `school_secondary` = TIGER's `UNSD`/`ELSD`/`SCSD`), same per-state,
      per-vintage pattern as county/tract. Downloaded and verified for both
      vintages; per-state 404s for whichever type(s) a state doesn't use are
      expected, not a bug (counts match the live server's file listings
      exactly: 2020 elsd 26/56, scsd 20/56; 2010 elsd 24/56, scsd 19/56)
- [x] Add Urban Areas (`urban_area` = TIGER's `UAC`) and tribal areas
      (`tribal_area` = TIGER's `AIANNH`, American Indian/Alaska Native/Native
      Hawaiian areas) -- both single national files per vintage, downloaded
      and verified. Urban Areas get redefined each census like RUCA does; the
      2020 TIGER folder hosts the old 2010-criteria file, the new
      2020-criteria file, AND a "_corrected" version of the 2020 file --
      used the corrected one since it supersedes the original release
- [x] Add congressional districts, as a **separate script**
      (`code/layer1_geography/02_download_congressional_dist.py`) --
      TIGER vintages these by **congress number**, not census year, and
      verified there's no formula from congress number to hosting TIGER
      year (congress 116 and 118 both live under `TIGER2020/CD/`, while the
      current 119th lives under `TIGER2024/CD/`), so it can't share
      01's year-keyed config. Defaults to the first congress based on each
      of the 2010 and 2020 censuses: congress 113 (seated 2013, one national
      file) and congress 118 (seated 2023, per-state). Output folder is
      `data/layer1_geography/raw/cd<congress>/`, deliberately not a bare number,
      so it can never be confused with a census-year vintage folder
- [x] Verify completeness/integrity of downloads across all states and
      geography types -- 602 zip files across 22 folders, every one checked
      for a real `PK` zip signature (0 invalid) and every per-state geography
      type's FIPS codes cross-checked against the canonical 56-state list
      (0 duplicates, 0 unknown codes; missing codes for school_elementary/
      school_secondary are the genuine "state doesn't use that district
      type" case, confirmed against the live server's own file counts)
- [x] Standardize into the common schema (GEOID, geometry, geography_type,
      vintage, state_fips, name, land_area_m2, water_area_m2) --
      `code/layer1_geography/04_standardize_geographies.py`. RUCA is
      deliberately NOT part of this schema, it's Layer 5's job to join it in
      by GEOID, not Layer 1's to carry. Congressional districts' `vintage`
      value is the congress number (e.g. `"118"`), not a year -- fine since
      `geography_type` scopes what `vintage` means per row. state_fips/name
      are null for zcta/urban_area/tribal_area since none of the three sits
      inside a single state. Source field names are NOT consistent across
      geography type or vintage (verified by reading real shapefiles, not
      assumed) -- e.g. 2020 tract uses bare `GEOID`/`ALAND` while 2020 block
      uses `GEOID20`/`ALAND20`, and every 2010 file uses a `10` suffix
      regardless of what 2020 does for that same type -- so the script uses
      an explicit per-(type, vintage) field map rather than a suffix rule.
      `block` is standardized to one Parquet file per state instead of one
      combined national file (~8M rows nationally vs. tens/hundreds of
      thousands for every other type) -- the same memory lesson already
      learned building the Layer 2 road network
- [ ] Make geography vintage a first-class, switchable parameter, not
      hard-coded -- bit the previous version once already (2010 vs. 2020 tract
      mismatch against COI data). The download/standardize scripts already
      take `--year`/`--vintage` flags; this item is about the eventual
      `get_geography(vintage=...)` library API, not the scripts themselves

## Layer 5: Reference data

Not part of the core four layers -- external tract-level datasets the
engine's GEOID-keyed output joins to, rather than something the engine
computes. Lives in `code/layer5_reference/` / `data/layer5_reference/`.

- [x] COI (Child Opportunity Index) -- direct GEOID join
      (`01_prepare_coi.py`)
- [x] RUCA -- direct GEOID join at the tract level
      (`02_prepare_ruca.py`); still needs wiring into Layer 1 itself, see above
- [x] Redlining (HOLC grades) -- spatial overlay, not a GEOID join, processed
      per-state (`03_prepare_redlining.py`)
- [ ] Opportunity Atlas -- not started

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
