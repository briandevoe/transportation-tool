# Layer 3: Population

ACS and Decennial population, by race/ethnicity and by characteristic (age
bracket, disability status), turned into population-weighted centroids --
the actual origin points every accessibility metric routes *from*.

**Requires a free Census API key** before running anything in this layer:
sign up at https://api.census.gov/data/key_signup.html, then either set the
`CENSUS_API_KEY` environment variable or pass `--api-key` to any script
below.

## Scripts, in order

1. **`01_download_acs_population.py`** -- tract-level population counts by
   race/ethnicity (and optionally by characteristic). Useful standalone if
   you just need population counts with no location.
2. **`02_build_centroids_block_group.py`** -- the main origin-table builder:
   pulls block-group-level population for weighting, and produces
   population-weighted centroids per tract.
3. **`03_build_centroids_block.py`** -- same idea, but block-level (Decennial
   data, the finest resolution the Census publishes race at).

`build_ct_geoid_crosswalk.py` is a one-time historical script (fixes a
Connecticut-specific GEOID mismatch) -- not part of the regular pipeline,
skip it.

## Quick start (Massachusetts, the default)

```
python 01_download_acs_population.py
python 02_build_centroids_block_group.py
python 03_build_centroids_block.py
```

All three default to Massachusetts, 2022 ACS 5-year, and COI's own 5-group
race/ethnicity scheme (`coi_5`). Useful flags:

- `--characteristics under_18 65_plus disability` -- add age/disability
  slices (default is total population by race/ethnicity only)
- `--race-scheme <name>` -- swap race/ethnicity grouping
- `--k <n>` (centroid scripts only) -- split each tract into `k`
  population-weighted centroids instead of one; default `k=1` is fine to
  start with

## Output

`data/layer3_population/acs/processed/<state_fips>/` (raw population counts)
and `data/layer3_population/block_group_weighted/processed/<state_fips>/
origins_<year>.parquet` (the origin table -- population-weighted centroids
by race/ethnicity/characteristic, ready to route from).
