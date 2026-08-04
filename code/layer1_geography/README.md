# Layer 1: Geography

Census boundary files -- tracts, block groups, blocks, ZCTAs, counties,
school districts, congressional districts, urban areas, tribal areas.
Everything else in this repo joins to these by GEOID, so this layer runs
first.

No API key or manual downloads needed -- everything here pulls directly
from the public Census TIGER/Line server.

## Scripts, in order

1. **`01_download_tiger.py`** -- downloads tract/block group/block/ZCTA/
   county/school-district boundary files.
2. **`02_download_congressional_dist.py`** -- downloads congressional
   district boundaries (a separate script because these are vintaged by
   congress number, not census year).
3. **`04_standardize_geographies.py`** -- standardizes whatever's been
   downloaded into one common schema (GEOID, geometry, geography_type,
   vintage, state_fips, name, land/water area). Always scans every state;
   automatically skips any state that hasn't been downloaded, so running
   this after an MA-only download just produces MA output.

(There is no `03` script in this layer -- not a gap, just how the numbering
landed historically.)

## Quick start (Massachusetts, the default)

```
python 01_download_tiger.py
python 02_download_congressional_dist.py
python 04_standardize_geographies.py
```

Every script defaults to Massachusetts (`--state-fips 25`) if run with no
flags. To pull more states at once, pass `--region all` (56 states/
territories) or `--region conus_ak_hi` (50 states + DC, no territories), or
`--state-fips 25 36` for a specific list.

## Convenience runners

`01_run_download_tiger.py` and `02_run_download_congressional_dist.py` are
config-at-the-top versions of the same two scripts -- edit the values and
hit Run instead of typing flags. Both already default to Massachusetts-only
for a quick test; change `STATE_FIPS` (or set `REGION`) to run more states.

## Output

`data/layer1_geography/raw/<year or cd<congress>>/...` (untouched downloads)
and `data/layer1_geography/processed/<vintage>/<geography_type>.parquet`
(standardized output layers 2-5 actually consume).
