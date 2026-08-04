# Layer 4: Destinations

Where people are traveling to -- schools, hospitals, grocery stores. Each
script standardizes one destination type into the same schema (location,
category, source, plus optional quality attributes).

## Scripts

- **`01_prepare_schools.py`** -- **needs manually-downloaded raw files
  first** (see below). Not state-specific -- produces one national file,
  filtered later by whichever state you're analyzing.
- **`02_prepare_grocery_osm.py`** -- grocery/supermarket locations from OSM.
  Defaults to Massachusetts, downloads what it needs automatically (reuses
  the same Geofabrik `.pbf` Layer 2 uses).
- **`03_prepare_hospitals_osm.py`** -- hospitals from OSM. Same pattern,
  also defaults to Massachusetts.

## Quick start (Massachusetts, the default)

```
python 02_prepare_grocery_osm.py
python 03_prepare_hospitals_osm.py
```

Both of those "just work" with no setup. Schools need one manual step
first:

### Schools -- manual prerequisite

`01_prepare_schools.py` reads two NCES files that must already exist in
`data/layer4_destination/schools/` -- it does not download them itself.
Both come from NCES's Common Core of Data (CCD) ecosystem, but from two
different pages -- get both before running the script. **Since `data/`
isn't in git, a fresh clone of this repo has neither one**; ask Brian for
copies of what he already has if that's easier than redownloading.

**1. School locations (geocodes) -- file: `EDGE_GEOCODE_PUBLICSCH_<year>.zip`**
- Go to https://nces.ed.gov/programs/edge/Geographic/SchoolLocations
- Download the public school geocode file for the school year you want
  (e.g. 2024-25) -- these are generated from CCD data but published under
  NCES's EDGE (geographic) program specifically, not the CCD file tool
  below.
- Save it, unrenamed, to `data/layer4_destination/schools/`.

**2. School characteristics (directory) -- file: `ccd_sch_029_<year>_*.zip`**
- Go to https://nces.ed.gov/ccd/files.asp and open the **CCD Data File
  Tool** (the "Table Generator" on the same page is an easier way to pick a
  year/component if the raw file tool is confusing).
- Download the **Public Elementary/Secondary School Universe Survey**
  file (the school "directory" file, `sch_029`) for the same school year
  as the geocode file above -- type/charter status, grade span, and
  operational status all come from this file.
- Save it, unrenamed, to the same folder: `data/layer4_destination/schools/`.

Both files must be the **same school year** (`01_prepare_schools.py` joins
them on `NCESSCH`, the school ID -- see its `--year` flag for which vintage
codes, e.g. `2425`, it currently expects). Once both are in place:

```
python 01_prepare_schools.py
```

## Output

`data/layer4_destination/<schools|grocery|hospitals>/processed/...` --
schools is one national parquet per grade band; grocery/hospitals are one
parquet per state.
