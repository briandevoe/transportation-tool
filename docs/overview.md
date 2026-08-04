# Technical overview

Background research the current architecture grew out of: data sources per
layer, routing-algorithm options, and libraries considered. Renamed from
`reference.md` -- content unchanged. Kept for context and to revisit as
new layers or algorithms get built.

## Layer notes

**Geography**: Tracts, block groups, blocks, ZCTAs, counties, congressional
districts, and school districts are all published as TIGER/Line shapefiles by
the Census Bureau — see the Layer 1 section of the main README for what's
being built first. Congressional districts redraw every redistricting cycle
(~10 years, sometimes off-cycle via litigation) and are vintaged by **congress
number**, not census year, unlike every other geography type here — need an
explicit vintage field from day one, and it can't reuse the same
year-keyed config the rest of Layer 1 uses.

**Travel network**: the hardest layer, no Census-equivalent single source.

| Network type | Data source | Notes |
|---|---|---|
| Roads (driving) | OpenStreetMap, via Geofabrik `.pbf` + pyrosm | Built in `../transportation2` |
| Sidewalks (walking) | OpenStreetMap | Sparse/inconsistent nationally; most walkability research assumes sidewalks parallel roads because true sidewalk-specific data mostly doesn't exist |
| Bike lanes | OpenStreetMap | Better-tagged than sidewalks in most cities, still uneven |
| Buses / transit | GTFS feeds, via Transitland or the Mobility Database (MobilityData) | No single national source; schedule-based, not a static-weight graph |
| School buses | No known public national dataset | Most districts don't publish routes at all; may not be solvable at national scale |
| Trails | OpenStreetMap (informal tagging) or Rails-to-Trails Conservancy TrailLink | Lower priority |

Lessons already learned building the road network in `../transportation2`,
worth not re-learning the hard way:
- `osmnx.graph_from_xml()` cannot read `.osm.pbf` (it wants XML). Use `pyrosm`
  to parse `.pbf` files directly.
- Public Overpass API mirrors rate-limit/block IPs sending many heavy queries
  in a row — not viable for bulk automated state-by-state network building.
  Local `.pbf` parsing avoids depending on Overpass entirely.
- Parsing a whole large state's PBF into memory at once can exceed available
  RAM (hit this on California). Fix: split the state into geographic chunks
  (recursive median split on point lon/lat, not a uniform grid, so dense
  metro areas don't end up in one oversized chunk) and parse each chunk with
  `pyrosm`'s `bounding_box` filter.
- `pyrosm`'s default "driving" filter is far more permissive than it looks —
  produced a graph ~15x bigger than the equivalent osmnx/Overpass network for
  the same state. Restrict to the standard drivable-highway-tag set and run
  `osmnx.simplify_graph()` afterward.
- **Still unresolved**: even chunked and filtered, `pyrosm`'s `get_network()`
  linearly scans the *entire* PBF file per chunk (no persistent spatial index
  across calls) — an 8-chunk state means 8 full scans of a multi-GB file.
  Worth solving properly (a one-time spatial pre-index, or building the whole
  state's graph once and cutting sub-graphs from it in memory) before this
  gets ported over.
- Network-chunk size should be driven by what a chunk's *parse* can handle in
  memory, not by how many origins are being routed against it — the old code
  conflated the two. Decoupling them is what makes moving from tracts to
  block groups (or beyond) tractable: chunk the network for memory limits
  once, then route as many batches of origins against each built chunk as
  needed (routing itself, via igraph, is fast; the network build is what's
  expensive).

**Population**: ACS pulls already support total/age/race stratification in
`../transportation2`. Extending to disability status is the same pattern — a
different ACS table, same download/reshape logic.

**Destinations**: already a proven pattern in `../transportation2` — one prep
script per data source, output standardized to one schema, routing/summary
code never changes.

## Computing travel times and distances

Several genuinely different approaches exist — which is appropriate depends
on the destination type, not just the network type.

**Not a network at all — straight-line distance**
- **Haversine / great-circle distance**: real distance between two lat/lons on
  a sphere. Right choice when *proximity itself* is the thing being measured
  (e.g. exposure to a pollution site or flood zone) rather than travel time —
  nobody "commutes to" a hazard.
- **Circuity-adjusted straight-line distance**: haversine x a fudge factor
  (~1.2-1.4) as a cheap stand-in for real road distance.
- "No network, just distance" is a valid network-layer configuration, not a
  separate system — a destination type (e.g. hazard sites) can simply be
  configured to use it instead of a routed network.

**Static-weight network shortest path** — what the road layer uses today
- **Dijkstra's algorithm**: the standard shortest-path algorithm for graphs
  with non-negative weights. What `networkx`, `igraph`, and
  `scipy.sparse.csgraph` all run underneath.
- **A\* (A-star)**: Dijkstra + a heuristic (usually straight-line distance to
  the target). Good for single origin -> single destination; less useful for
  "one origin, many candidate destinations."
- **Bidirectional search**: expand from both ends, meet in the middle.
- **Contraction Hierarchies (CH)**: what OSRM uses — expensive one-time
  preprocessing, then near-instant repeated queries (even many-to-many). The
  right tool for this pipeline's shape; blocked previously by no Docker
  available for OSRM. Worth revisiting if that changes.
- **Multi-Level Dijkstra (MLD)**: OSRM's other preprocessing option.
- **ALT (A\* + Landmarks + Triangle inequality)**: precomputed landmark
  distances bound/guide A* search — a middle ground.

**Many-to-many / batch matrix computation** — the actual shape of this problem
- **OSRM's `/table` service**: one call, full N x M matrix, CH-preprocessed.
- **Batched multi-source Dijkstra** (igraph's `distances()`, scipy's
  `csgraph.dijkstra`): what the current road layer uses — compiled code,
  multiple sources per call, no separate preprocessing step.
- **R5 / `r5py`**: purpose-built for population-to-opportunity accessibility
  research specifically, handles many-to-many natively, properly accounts for
  GTFS schedules. Probably the most relevant engine to evaluate as this
  matures.

**Schedule-based routing** — specifically for transit
- **RAPTOR**: the modern standard for transit routing, handles schedules and
  transfers correctly. What R5 runs internally.
- **Time-expanded graphs**: represent every scheduled departure as its own
  graph node, run ordinary Dijkstra. Simple but the graph gets huge.
- **Frequency-based approximation**: constant average headway + expected wait
  penalty at boarding, routed on the same static graph as roads. Less
  accurate for infrequent service, fits the existing engine — likely v1
  approach for transit.

**Isochrones**: compute the whole area reachable within N minutes (same
shortest-path machinery, different output) instead of time to a specific
destination. Not needed now, useful for visualization later.

**Routing vs. accessibility scoring are separate pipeline stages.** Everything
above computes raw travel times. Turning those into a metric (gravity-weighted
access, count-within-15-minutes, nearest-time) is a separate downstream step.

## R and Python libraries worth evaluating

Not a commitment to use any of these — assembled while thinking through the
layers. Starred (⭐) entries are unusually well-matched to this project.

**Geospatial data handling**: `geopandas`, `shapely`, `pyproj` (Python, in
use) · `pyogrio` (Python, fast vector I/O) · `rasterio` (Python, gridded
hazard data) · `sf` (R, vector data) · `terra` (R, raster data)

**Census / ACS access**: ⭐ `tigris` (R — downloads TIGER/Line shapefiles for
every geography type here, by year; well ahead of Python's equivalents for
this specific need) · ⭐ `tidycensus` (R — Census/ACS data into tidy/`sf`
format with clean vintage selection) · `pygris` (Python port of `tigris`) ·
`census` / `cenpy` (Python, Census API wrappers)

**Networks / routing**: `osmnx`, `pyrosm` (Python, in use) · `igraph`
(Python/R, in use) · `networkx` (Python, pure-Python fallback) ·
`scipy.sparse.csgraph` (Python, compiled Dijkstra) · ⭐ `pandana` (Python —
built specifically for fast urban accessibility calculations, from the
UrbanSim/Urban Data Science Toolkit group) · ⭐ `r5py` (Python) / ⭐ `r5r` (R)
— R5 engine wrappers, purpose-built for accessibility research, proper GTFS
handling · `dodgr` (R, street network routing) · `stplanr` (R, transport
planning) · `networkit` (Python, parallelized C++) · `graph-tool` (Python,
very fast, notoriously hard to install on Windows)

**Transit / GTFS**: `gtfs-kit`, `partridge` (Python) · `gtfsrouter`,
`tidytransit` (R)

**Accessibility scoring**: ⭐ `accessibility` (R, same Ipea group as `r5r` —
computes accessibility metrics directly from a travel-time matrix, doing
functionally what this repo's engine does; worth a direct comparison)

**Spatial statistics**: `pysal` (Python) · `spdep`, `sfdep` (R)

## Potential destination types

Beyond schools/hospitals/grocery. Not a commitment to build all of these.

- **Health**: pharmacies, urgent care, Federally Qualified Health Centers
  (HRSA data — specifically serve underserved populations), dialysis centers
  (frequent-visit health-equity research), mental health/behavioral health,
  substance use treatment, dental clinics, WIC clinics
- **Food access**: farmers markets, food banks/pantries, SNAP-authorized
  retailers specifically (USDA retailer locator — narrower than "grocery")
- **Education & childcare**: public libraries (digital-divide research),
  childcare/daycare ("childcare desert" is an active research subfield), Head
  Start, public pre-K, community colleges, adult education/GED
- **Civic & government**: polling places (directly relevant given the
  congressional-district geography layer), DMV offices, Social Security
  offices, social services offices, legal aid/courts, post offices
- **Economic**: banks/credit unions ("banking desert" research), check-
  cashing/payday lending (predatory-exposure angle), job/workforce centers
- **Transportation as a destination**: transit stops/stations (access *to*
  transit as an outcome, distinct from using transit as a network), EV
  charging stations
- **Housing & safety net**: homeless shelters, domestic violence shelters,
  public housing
- **Public safety**: police, fire/EMS stations
- **Environmental hazards** (negative destinations — the straight-line-
  distance use case above): EPA Toxic Release Inventory sites, Superfund
  sites, landfills/waste facilities, power plants, major highways (proximity
  itself is the studied exposure)
