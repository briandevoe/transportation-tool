# Development notes

Running engineering log: decisions, bugs found and fixed, and the reasoning
behind each layer's design. Renamed from `plan.md` -- content unchanged,
just no longer the first thing a new reader sees.

## Motivation (recorded 2026-07-24)

COI measures whether a neighborhood has resources; it deliberately does not
measure whether a specific person can actually reach them (COI's own
reasoning for staying out of this, applied to race rather than access, is in
`docs/COI 3.0 Technical Documentation 20250724.pdf` p.22). COI leadership has
named transportation (along with crime and remote sensing) as a category
missing from COI's current indicator set. This project's goal is a
transportation equity measure/index -- population-weighted, demographic-
sliced, routed accessibility -- built using this repo's existing five-layer
architecture as-is.

Explicit decisions, so they don't get re-litigated by accident later:
- **No restructuring the five-layer architecture** to fit any single
  downstream consumer's shape, including COI's own indicator-construction
  pipeline (block-level, z-scored, nationally/state/metro-normed). COI
  consumes this tool's output as Layer 5 reference data (a GEOID join),
  the same relationship RUCA/redlining already have -- it does not shape
  how Layers 1-4 or the core engine work.
- **Greenspace/NatureScore-replacement work is explicitly out of scope for
  now.** Only the transportation measure is active work.
- The Conveyal Analysis / tool-landscape comparison (item below) matters
  more than it did before, not less: if this measure is meant to be used in
  actual COI-adjacent research rather than stay a personal exploration, "we
  built this ourselves" needs a defensible answer to "why not R5."
- Per-layer status snapshot as of this date: Layer 1 (geography) is the most
  complete and verified; Layer 2 (network) and Layer 3 (population) have
  real depth but only Massachusetts is built end-to-end; Layer 4
  (destinations) has schools/grocery/hospitals; the core engine (routing +
  scoring) exists only as code embedded in `code/analysis/*` scripts, not a
  reusable API, and has only ever been run against Massachusetts. No
  accessibility number produced by this pipeline has yet been used to
  answer a real research question end-to-end.

## Known constraints worth remembering

- **ACS (race/age/disability) bottoms out at block group** -- the Census
  Bureau does not publish those breakdowns at the block level, full stop.
  Block-level analysis will be total-population-only.
- **ZCTAs are not zip codes** -- they're the Census Bureau's polygon
  approximation of USPS zip codes, built from block geometry.

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
- [x] Write up the tool landscape comparison (Conveyal Analysis, Urban
      Institute's Spatial Equity Data Tool, Spatial Access of America) --
      promised as a follow-up in the COI proposal thread. Findings (recorded
      2026-07-26):
  - **Conveyal Analysis / R5 / r5py**: no native demographic-subgroup
    accessibility engine anywhere in this stack. Conveyal's hosted product
    supports equity analysis only by having the user upload one population
    layer per demographic category and run a separate job per layer -- not a
    built-in race x age x disability model. r5py (the Python routing wrapper,
    MIT/GPL, actively maintained by Univ. of Helsinki's Digital Geography
    Lab) has no accessibility function at all, only travel-time
    matrices/isochrones/itineraries -- any accessibility or demographic
    logic is 100% custom code on top, same burden this repo already carries.
    Conveyal's internal spatial unit is also a Web Mercator grid, not census
    geography -- polygon data gets areally dispersed into grid cells, not
    GEOID-native by default. Real, defensible future option though: R5/r5py
    is free, self-hostable, and far more battle-tested for GTFS-based
    transit routing (modified RAPTOR) than a hand-rolled router would be --
    a plausible Layer 2 swap-in once transit enters scope, without touching
    Layers 1/3/4 or the GEOID-keyed output contract. Decided 2026-07-26:
    continue with the custom network layer for now; revisit r5py
    specifically for Layer 2 in a more mature version of the tool.
  - **Urban Institute's Spatial Equity Data Tool (SEDT)**: does not route at
    all. Core methodology (v1 2020, v2 2021, public API ~2024, GPLv3, still
    active) is a siting/representativeness disparity score -- does the
    demographic composition of uploaded point locations match the
    population's demographic composition -- structurally closer to COI than
    to a travel-time tool. A new pilot "access measure" (r5r-based
    walk/drive sheds) is architecturally similar to this project's approach
    but is limited to a Maryland/Virginia/DC pilot with no confirmed
    national timeline.
  - **Spatial Access of America** (Purdue, *Scientific Data* July 2025,
    unaffiliated with Urban Institute): the closest methodological peer --
    real OSRM routing, multiple accessibility metrics (E2SFCA, gravity,
    cumulative-opportunity), demographic-sliced job/POI access. But it's a
    static published dataset + viz tool, not an interactive/extensible
    platform, covers only the 50 largest urban areas, and has no transit.
  - **Net**: no existing tool combines real network routing + first-class
    demographic-subgroup slicing + flexible destination types + GEOID-native
    output. Conveyal has routing + flexible destinations but not
    demographic/GEOID-native output; SEDT has demographic/GEOID but no
    routing; Spatial Access of America has routing + demographic slicing but
    is static, non-transit, and limited to 50 metros. This is the
    defensible answer to "why not just use an existing tool."

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
- [x] RUCA -- direct GEOID join at the tract level (`02_prepare_ruca.py`).
      Deliberately kept Layer-5-only, not wired into Layer 1's own schema
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

- [x] Port ACS download/reshape logic from `../transportation2`
      (`01_download_acs_population.py`, `lib/acs_client.py`) -- built for
      total/age/race, swappable race scheme (`lib/race_ethnicity_schemes.py`)
- [x] Add a second race/ethnicity scheme, `detailed_7` -- the general
      7-group standard used broadly in child-equity research, splitting
      `simplified_5`'s "other_nh" bucket into aian_nh/nhpi_nh/
      other_multiracial_nh. Initially assumed (incorrectly, see below) to be
      COI's own breakdown; kept anyway since it's a real, separately-used
      standard -- specifically, this is the breakdown NCES's Common Core of
      Data (CCD) uses for school-level race/ethnicity reporting, relevant to
      the education-domain / school-level work this project may draw on in
      Layer 4. Selectable via the existing `--race-scheme` flag on all three
      layer3_population scripts, no script logic changes needed -- schemes
      are just dicts. Along the way, fixed a real gap: none of the three
      scripts' output filenames included the race scheme, so a `detailed_7`
      run for a state that already had `simplified_5` output would have
      silently skipped or overwritten it -- same fix pattern as the `--k`
      filename suffix, default scheme keeps the original filename
- [x] Add a third scheme, `coi_5`, matching COI's *actual* race/ethnicity
      breakdown -- confirmed directly from `docs/COI 3.0 Technical
      Documentation 20250724.pdf` (p.46: "We compute Ij separately for
      Asian, Black, Hispanic, American Indian/Alaska Native and non-Hispanic
      White children") that the neighborhood-level COI index uses 5 groups.
      `coi_5` merges Asian with Native Hawaiian/Pacific Islander into one
      "asian" group, keeps AIAN as its own group, and -- unlike
      `simplified_5`/`detailed_7` -- doesn't fold "Some Other Race"/"Two or
      More Races" into an "other" bucket at all; COI simply excludes them
      from its race-specific breakdown. **`coi_5` is now the default**
      (`ACTIVE_SCHEME_NAME` and every script's `--race-scheme` default) since
      COI is expected to be this project's most-used reference layer --
      existing `simplified_5` output (51 states across `acs` and
      `block_group_weighted`, 1 state for `block_weighted`) was renamed with
      an explicit `_simplified_5` suffix rather than deleted, freeing the
      bare filename for the new `coi_5` default; both coexist under distinct
      filenames going forward
- [x] **Connecticut GEOID-mismatch bug -- fixed**, the same way COI fixed it
      (Appendix 6, p.87): tract/block-group boundaries never changed in the
      2022 planning-region switch, only the county-FIPS segment of the
      GEOID did, so matching the trailing 6-digit tract code alone
      (ignoring the county prefix) uniquely crosswalks 879 of 883
      Connecticut tracts. Built the crosswalk ourselves
      (`code/layer3_population/build_ct_geoid_crosswalk.py`, a one-time
      script, not part of the regular pipeline) directly from this repo's
      own Layer 1 tract list plus one live ACS query -- landed on the exact
      same 4 ambiguous tracts (reused "990000"/"990100" placeholder codes)
      COI found; reused COI's own published resolution (Table A6.2, needed
      spatial analysis to resolve, not just code-matching) for 3 of them,
      and dropped the 4th exactly like COI did (a tract fully covered by
      water that split into two in 2022, so there's no single valid
      counterpart). Fix lives in `code/lib/ct_geoid_crosswalk.py`, applied
      unconditionally inside `lib/acs_client.py`'s two fetch functions --
      safe to call on any state/vintage since it only rewrites GEOIDs that
      actually match a new-vintage Connecticut entry, everything else
      passes through untouched. Does NOT apply to
      `03_build_centroids_block.py` -- confirmed live that 2020 Decennial
      PL 94-171 still uses the old county codes for Connecticut (it
      predates the 2022 switch), so that script never had this bug.
      Verified: Connecticut's null-lat/lon rate dropped from 100% to 17.1%,
      right in the normal 3-18% sparse-population range every other state
      shows; the 2 remaining unmapped GEOIDs are exactly the expected split
      fragments of the dropped water tract, not a new problem. Only
      Connecticut (09) has been rebuilt with the fix so far -- the other 50
      states' `coi_5`-default output still needs to be (re)built whenever a
      full batch run happens, though the fix is a no-op for all of them
- [ ] **Ideas surfaced by the same document, not started**: (1) nationally/
      state/metro-normed scoring -- COI publishes the same metric normalized
      three ways depending on the comparison being made, directly
      transportable to an "accessibility percentile"; (2) an "equity
      validity" style metric -- COI deliberately excludes race from its
      composite index (to avoid confusing race as cause vs. symptom of
      structural inequity) but measures race-based concentration in a
      *separate* downstream analysis, which is exactly how this project is
      already architected (population joins after computing accessibility,
      not baked into it); (3) computing accessibility at the block level as
      the base unit and aggregating up, mirroring COI's own approach, rather
      than tract-first; (4) population-sized adaptive-radius density
      measures (COI's point-to-block convex-hull aggregation, Appendix 4) as
      an alternative/complement to pure travel-time accessibility
- [x] Add disability status stratification (`lib/acs_characteristics.py`'s
      `CHARACTERISTICS` dict -- adding a new one is one entry, nothing else
      in the pipeline changes)
- [x] Pull decennial block-level race/ethnicity counts
      (`lib/decennial_client.py`, `03_build_centroids_block.py`) -- the
      finest resolution Census publishes race at
- [x] Compute population-weighted centroids -- `02_build_centroids_block_group.py`
      (ACS, block-group weighted) and `03_build_centroids_block.py`
      (Decennial, block weighted). **Schema locked in** with a tunable `--k`
      (`lib/weighted_centroids.py`, shared by both scripts): instead of
      always collapsing a tract's sub-tract population into one weighted-
      average point, k > 1 splits it into k population-weighted clusters via
      weighted k-means, so a tract with separated population concentrations
      doesn't flatten into a centroid that sits on nobody. Default k=1
      reproduces the original single-centroid math exactly -- verified
      byte-for-byte (population exact match, lat/lon match to float noise)
      against pre-k-parameter output before this was trusted. Every centroid
      also gets a `dispersion_m` (population-weighted RMS distance from the
      centroid, meters) as a standing diagnostic independent of k, so a
      consumer can spot a shaky single-centroid tract without needing k>1.
      Schema: `GEOID, geography_level, state_fips, race_ethnicity,
      characteristic, population, population_source, population_vintage,
      centroid_source, centroid_vintage, centroid_index, centroid_k, lat,
      lon, dispersion_m` (`lib/population_schema.py`). k=1 output keeps the
      original filename (`origins_<year>.parquet`); k>1 writes to
      `origins_<year>_k<k>.parquet` instead of colliding with it. Consuming
      k>1 output correctly (grouping by centroid_index, weighting sub-
      origins) is NOT yet done in the analysis layer -- default k=1 is safe
      for existing code, k>1 needs `code/analysis/*` updated before use
- [ ] Add ACS vehicle-availability-by-household data (block-group level), to
      support car-access-by-demographic-group analysis
- [ ] Coverage: `acs` and `block_group_weighted` built for 51/56 states
      (missing the 5 island territories); `block_weighted` (decennial) only
      built for Massachusetts so far -- same "one state proven, rest not run
      yet" state Layer 2 started in
- [ ] **Known bug, root-caused, not yet fixed**: Connecticut (state 09) --
      100% of origins have null lat/lon (vs. 3-18% elsewhere, the normal
      sparse-population rate). Cause: Connecticut replaced its 8 legacy
      counties with 9 new state-defined planning regions as county-
      equivalents starting with 2022-vintage Census data. ACS 2022 5-year
      already uses the new region codes (`09110`-`09190`); Layer 1's TIGER
      geography is 2020-vintage and still uses the old county codes
      (`09001`-`09015`) -- every Connecticut GEOID's county segment
      mismatches between population data and geometry, so the block-group
      weighting join finds zero matches. Same bug *class* the "2010 vs 2020
      tract mismatch" note above already warns about, new instance. Real fix
      needs either an old-county<->new-region crosswalk or 2022+-vintage
      TIGER geometry for Connecticut specifically (its tract boundaries were
      partly redrawn along with the region change, so a crosswalk alone may
      not be sufficient)
- [ ] **Known limitation, confirmed larger than documented**: the "small
      Hispanic overlap" in `black_nh`/`asian_nh`/`other_nh`
      (`lib/race_ethnicity_schemes.py`'s own caveat -- ACS only publishes a
      true alone-not-Hispanic table for White, so the other "alone" race
      counts include their Hispanic members too, double-counted against the
      separate `hispanic` category) is NOT small in practice. Measured
      directly: summing the 5 race categories vs. the independent `total`
      column across Massachusetts tracts averages ~9% inflation but reaches
      86% in the highest-Hispanic-population tracts (Lawrence/Lynn area) --
      the overlap size tracks almost exactly with that tract's Hispanic
      population, meaning nearly the entire Hispanic community there gets
      double-counted into a non-white "alone" category. Worse specifically
      in the diverse, heavily-Hispanic communities this tool's equity
      mission cares most about. Real fix needs ACS PUMS microdata (person-
      level, correct race x Hispanic-origin cross-tabulation), a genuinely
      bigger lift than the tract/block-group table approach used today

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
