# Layer 2: Travel network

Roads (and eventually sidewalks/bike lanes/transit) as a routable network.
Depends on Layer 1 only for context (join keys, tract boundaries for
visualization) -- the network itself is built independently.

No API key needed -- OSM/Geofabrik and TIGER are both public downloads.

## Scripts

- **`01_download_osm_roads.py`** -- the primary, routable road network.
  Downloads a state's Geofabrik `.osm.pbf` extract and builds a road graph
  from it. Defaults to Massachusetts (`--state-fips 25`). Can take a while
  for large/dense states -- it's parsing and simplifying a full state's OSM
  road data, not a quick download.
- **`02_download_tiger_roads.py`** -- downloads raw TIGER ROADS county
  files. Used both as the input to `03` below and as the source for bike
  path geometry (MTFCC `S1820`). Also defaults to Massachusetts.
- **`03_build_routable_tiger_network.py`** -- builds a routable network from
  TIGER roads instead of OSM. Faster than `01` (pure local geometry
  processing, no network parsing) but less accurate: no real speed limits
  (flat defaults per road class) and no oneway data. Use this as a fallback
  for a state where `01` hasn't finished yet, not as the default choice.

## Quick start (Massachusetts, the default)

```
python 01_download_osm_roads.py
```

That alone gives you a routable MA network. Add `02_download_tiger_roads.py`
if you also want bike path data or the TIGER-based fallback network.

## Convenience runners

`01_run_download_osm_roads.py` and `02_run_download_tiger_roads.py` are
multi-state batch runners with hardcoded state lists at the top (Massachusetts
is already included in `01`'s list) -- meant for building many states in one
background run, not a quick single-state test. For Massachusetts alone, just
run `01_download_osm_roads.py` directly.

## Output

`data/layer2_network/roads/osm/processed/<state_fips>/{edges,nodes}.parquet`
(routable graph) and `data/layer2_network/roads/tiger/raw/<year>/` (raw TIGER
county files, also the bike-path source).
