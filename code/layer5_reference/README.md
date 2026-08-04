# Layer 5: Reference data

External, tract-level datasets that the tool's accessibility output gets
*joined to* by GEOID -- not something this tool computes itself. COI, RUCA,
and redlining all need a manually-downloaded source file already sitting in
`data/layer5_reference/`; vehicle availability is the one script here that
pulls its own data automatically.

**Since `data/` isn't in git, none of the manual source files below exist
on a fresh clone.** Ask Brian for copies, or re-download from each
project's own site.

## Scripts

- **`01_prepare_coi.py`** -- Child Opportunity Index (COI 3.0-2021).
  **Manual prerequisite:** `data/layer5_reference/coi/2020 census tracts,
  overall index and domains (COI 3.0-2021).zip` must already exist.
  National output, direct GEOID join, no state flag needed.
- **`02_prepare_ruca.py`** -- Rural-Urban Commuting Area codes.
  **Manual prerequisite:** `data/layer5_reference/ruca/
  RUCA-codes-2020-tract.csv` must already exist. National output, no state
  flag needed.
- **`03_prepare_redlining.py`** -- historical HOLC redlining grades (spatial
  overlay, not a GEOID join -- most tracts nationally have no HOLC data at
  all, which is expected). **Manual prerequisite:**
  `data/layer5_reference/redlining/mappinginequality.json` (Mapping
  Inequality project) must already exist. Defaults to Massachusetts.
- **`04_prepare_vehicle_availability.py`** -- household vehicle availability
  from ACS table B25044. The one script in this layer that needs no manual
  file -- **but does need the same free Census API key as Layer 3**
  (`CENSUS_API_KEY` env var or `--api-key`). Defaults to Massachusetts.

## Quick start (Massachusetts, the default)

```
python 04_prepare_vehicle_availability.py
```

That one works out of the box. For COI/RUCA/redlining, get the manual
source file in place first (see above), then:

```
python 01_prepare_coi.py
python 02_prepare_ruca.py
python 03_prepare_redlining.py
```

## Output

`data/layer5_reference/<coi|ruca|redlining|vehicle_availability>/
processed/...` -- all GEOID-keyed lookup tables, meant to be joined onto
Layer 1-4 output via `code/engine/reference_data.py`, not consumed directly.
