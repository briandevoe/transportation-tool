"""
Layer 1 (Geography): standardize every downloaded TIGER/Line file (from
01_download_tiger.py and 02_download_congressional_dist.py) into one common
schema: GEOID, geometry, geography_type, vintage, state_fips, name,
land_area_m2, water_area_m2. RUCA is deliberately NOT part of this schema --
that's Layer 5's job to join in by GEOID, not Layer 1's to carry.

Source field names are NOT consistent across geography types or vintages --
verified directly by reading real shapefiles, not assumed:
  - 2020 tract/bg/county/school districts/tribal_area use bare field names
    (GEOID, STATEFP, ALAND, AWATER, NAME or NAMELSAD)
  - 2020 block/zcta/urban_area/cd118 use "20"-suffixed field names instead
    (GEOID20, STATEFP20, ALAND20, ...)
  - Every 2010 file uses a "10" suffix (GEOID10, STATEFP10, ...), including
    types that get no suffix at all in 2020
  - cd113 (a 2013-vintage file, not a 2010-vintage one) uses bare field
    names, like 2020's non-suffixed group
So FIELD_MAP/CD_FIELD_MAP below is an explicit per-(geography_type, vintage)
table, not a derived suffix rule.

state_fips is null for zcta/urban_area/tribal_area -- none of the three is
guaranteed to sit inside one state (a ZCTA or urban area can straddle a
state line; TIGER's AIANNH tribal areas can too), so there's no single
correct state per row. name is null for zcta -- there's no descriptive name
field at all, only the code that's already the GEOID.

block is handled differently from every other geography type: at roughly
8 million features nationally (vs. tens/hundreds of thousands for
everything else here), concatenating all 56 states into one file risks the
same memory problem already hit and solved for the OSM road network in
Layer 2. Block output is one Parquet file PER STATE instead of one combined
national file; every other geography type is combined into a single
national Parquet per vintage (or per congress, for congressional districts).

Usage:
    python 04_standardize_geographies.py                        # every geography type, every downloaded vintage
    python 04_standardize_geographies.py --geography tract       # just tracts, both vintages
    python 04_standardize_geographies.py --geography tract --vintage 2020
    python 04_standardize_geographies.py --geography cd           # congressional districts, both congresses
    python 04_standardize_geographies.py --geography cd --congress 118
"""
import argparse
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.tiger_download import STATE_FIPS

REPO_ROOT = Path(__file__).parent.parent.parent
RAW_DIR = REPO_ROOT / "data" / "layer1_geography" / "raw"
OUT_DIR = REPO_ROOT / "data" / "layer1_geography" / "processed"

# geography_type -> vintage -> source column names (state_fips/name are None
# where that attribute doesn't exist/doesn't apply -- see module docstring)
FIELD_MAP = {
    "tract": {
        "2020": {"geoid": "GEOID",   "state_fips": "STATEFP",   "name": "NAMELSAD",   "aland": "ALAND",   "awater": "AWATER"},
        "2010": {"geoid": "GEOID10", "state_fips": "STATEFP10", "name": "NAMELSAD10", "aland": "ALAND10", "awater": "AWATER10"},
    },
    "bg": {
        "2020": {"geoid": "GEOID",   "state_fips": "STATEFP",   "name": "NAMELSAD",   "aland": "ALAND",   "awater": "AWATER"},
        "2010": {"geoid": "GEOID10", "state_fips": "STATEFP10", "name": "NAMELSAD10", "aland": "ALAND10", "awater": "AWATER10"},
    },
    "block": {
        "2020": {"geoid": "GEOID20", "state_fips": "STATEFP20", "name": "NAME20",   "aland": "ALAND20", "awater": "AWATER20"},
        "2010": {"geoid": "GEOID10", "state_fips": "STATEFP10", "name": "NAME10",   "aland": "ALAND10", "awater": "AWATER10"},
    },
    "zcta": {
        "2020": {"geoid": "GEOID20", "state_fips": None, "name": None, "aland": "ALAND20", "awater": "AWATER20"},
        "2010": {"geoid": "GEOID10", "state_fips": None, "name": None, "aland": "ALAND10", "awater": "AWATER10"},
    },
    "county": {
        "2020": {"geoid": "GEOID",   "state_fips": "STATEFP",   "name": "NAMELSAD",   "aland": "ALAND",   "awater": "AWATER"},
        "2010": {"geoid": "GEOID10", "state_fips": "STATEFP10", "name": "NAMELSAD10", "aland": "ALAND10", "awater": "AWATER10"},
    },
    "school_unified": {
        "2020": {"geoid": "GEOID",   "state_fips": "STATEFP",   "name": "NAME",   "aland": "ALAND",   "awater": "AWATER"},
        "2010": {"geoid": "GEOID10", "state_fips": "STATEFP10", "name": "NAME10", "aland": "ALAND10", "awater": "AWATER10"},
    },
    "school_elementary": {
        "2020": {"geoid": "GEOID",   "state_fips": "STATEFP",   "name": "NAME",   "aland": "ALAND",   "awater": "AWATER"},
        "2010": {"geoid": "GEOID10", "state_fips": "STATEFP10", "name": "NAME10", "aland": "ALAND10", "awater": "AWATER10"},
    },
    "school_secondary": {
        "2020": {"geoid": "GEOID",   "state_fips": "STATEFP",   "name": "NAME",   "aland": "ALAND",   "awater": "AWATER"},
        "2010": {"geoid": "GEOID10", "state_fips": "STATEFP10", "name": "NAME10", "aland": "ALAND10", "awater": "AWATER10"},
    },
    "urban_area": {
        "2020": {"geoid": "GEOID20", "state_fips": None, "name": "NAMELSAD20", "aland": "ALAND20", "awater": "AWATER20"},
        "2010": {"geoid": "GEOID10", "state_fips": None, "name": "NAMELSAD10", "aland": "ALAND10", "awater": "AWATER10"},
    },
    "tribal_area": {
        "2020": {"geoid": "GEOID",   "state_fips": None, "name": "NAMELSAD",   "aland": "ALAND",   "awater": "AWATER"},
        "2010": {"geoid": "GEOID10", "state_fips": None, "name": "NAMELSAD10", "aland": "ALAND10", "awater": "AWATER10"},
    },
}

# geography_type -> vintage -> (raw filename template, per_state)
RAW_FILES = {
    "tract":             {"2020": ("tl_2020_{state}_tract.zip", True),       "2010": ("tl_2010_{state}_tract10.zip", True)},
    "bg":                {"2020": ("tl_2020_{state}_bg.zip", True),          "2010": ("tl_2010_{state}_bg10.zip", True)},
    "block":             {"2020": ("tl_2020_{state}_tabblock20.zip", True),  "2010": ("tl_2010_{state}_tabblock10.zip", True)},
    "zcta":              {"2020": ("tl_2020_us_zcta520.zip", False),        "2010": ("tl_2010_us_zcta510.zip", False)},
    "county":            {"2020": ("tl_2020_us_county.zip", False),         "2010": ("tl_2010_us_county10.zip", False)},
    "school_unified":    {"2020": ("tl_2020_{state}_unsd.zip", True),        "2010": ("tl_2010_{state}_unsd10.zip", True)},
    "school_elementary": {"2020": ("tl_2020_{state}_elsd.zip", True),        "2010": ("tl_2010_{state}_elsd10.zip", True)},
    "school_secondary":  {"2020": ("tl_2020_{state}_scsd.zip", True),        "2010": ("tl_2010_{state}_scsd10.zip", True)},
    "urban_area":        {"2020": ("tl_2020_us_uac20_corrected.zip", False),"2010": ("tl_2010_us_uac10.zip", False)},
    "tribal_area":       {"2020": ("tl_2020_us_aiannh.zip", False),         "2010": ("tl_2010_us_aiannh10.zip", False)},
}

CD_FIELD_MAP = {
    113: {"geoid": "GEOID",   "state_fips": "STATEFP",   "name": "NAMELSAD",   "aland": "ALAND",   "awater": "AWATER"},
    118: {"geoid": "GEOID20", "state_fips": "STATEFP20", "name": "NAMELSAD20", "aland": "ALAND20", "awater": "AWATER20"},
}
CD_RAW_FILES = {
    113: ("tl_2013_us_cd113.zip", False),
    118: ("tl_2020_{state}_cd118.zip", True),
}

LARGE_TYPES = {"block"}  # written per-state instead of one combined national file -- see module docstring


def _null_string_column(length):
    return pd.array([None] * length, dtype="string")


def _standardize(gdf, fmap, geography_type, vintage):
    return gpd.GeoDataFrame({
        "GEOID": gdf[fmap["geoid"]].astype("string"),
        "geometry": gdf.geometry,
        "geography_type": geography_type,
        "vintage": str(vintage),
        "state_fips": gdf[fmap["state_fips"]].astype("string") if fmap["state_fips"] else _null_string_column(len(gdf)),
        "name": gdf[fmap["name"]].astype("string") if fmap["name"] else _null_string_column(len(gdf)),
        "land_area_m2": pd.to_numeric(gdf[fmap["aland"]], errors="coerce"),
        "water_area_m2": pd.to_numeric(gdf[fmap["awater"]], errors="coerce"),
    }, geometry="geometry", crs=gdf.crs)


def _read_and_standardize(src, fmap, geography_type, vintage, label):
    if not src.exists():
        print(f"  {label}: MISSING, skipped")
        return None
    gdf = gpd.read_file(f"zip://{src}")
    std = _standardize(gdf, fmap, geography_type, vintage)
    print(f"  {label}: {len(std):,} rows")
    return std


def standardize_geography(geography_type, vintage, states):
    fmap = FIELD_MAP[geography_type][vintage]
    filename_template, per_state = RAW_FILES[geography_type][vintage]
    raw_dir = RAW_DIR / vintage / geography_type
    out_dir = OUT_DIR / vintage
    out_dir.mkdir(parents=True, exist_ok=True)

    if geography_type in LARGE_TYPES:
        print(f"\n[{geography_type} {vintage}] -- one output file per state (large geography type)")
        for state in states:
            out_path = out_dir / f"{geography_type}_{state}.parquet"
            if out_path.exists():
                print(f"  {state}: already standardized, skipped")
                continue
            std = _read_and_standardize(raw_dir / filename_template.format(state=state), fmap, geography_type, vintage, state)
            if std is not None:
                std.to_parquet(out_path)
        return

    out_path = out_dir / f"{geography_type}.parquet"
    if out_path.exists():
        print(f"\n[{geography_type} {vintage}] already standardized -> {out_path.name}, skipped")
        return

    print(f"\n[{geography_type} {vintage}]")
    targets = states if per_state else [None]
    pieces = []
    for state in targets:
        filename = filename_template.format(state=state) if per_state else filename_template
        std = _read_and_standardize(raw_dir / filename, fmap, geography_type, vintage, state or "us")
        if std is not None:
            pieces.append(std)

    if not pieces:
        print("  No source files found -- nothing written.")
        return

    combined = gpd.GeoDataFrame(pd.concat(pieces, ignore_index=True), crs=pieces[0].crs)
    combined.to_parquet(out_path)
    print(f"  Total: {len(combined):,} rows -> {out_path}")


def standardize_cd(congress, states):
    fmap = CD_FIELD_MAP[congress]
    filename_template, per_state = CD_RAW_FILES[congress]
    raw_dir = RAW_DIR / f"cd{congress}"
    out_dir = OUT_DIR / f"cd{congress}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "cd.parquet"
    if out_path.exists():
        print(f"\n[cd{congress}] already standardized -> {out_path.name}, skipped")
        return

    print(f"\n[cd{congress}]")
    targets = states if per_state else [None]
    pieces = []
    for state in targets:
        filename = filename_template.format(state=state) if per_state else filename_template
        std = _read_and_standardize(raw_dir / filename, fmap, "congressional_district", congress, state or "us")
        if std is not None:
            pieces.append(std)

    if not pieces:
        print("  No source files found -- nothing written.")
        return

    combined = gpd.GeoDataFrame(pd.concat(pieces, ignore_index=True), crs=pieces[0].crs)
    combined.to_parquet(out_path)
    print(f"  Total: {len(combined):,} rows -> {out_path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    all_types = list(FIELD_MAP) + ["cd"]
    parser.add_argument("--geography", nargs="+", choices=all_types, default=all_types,
                         help="Geography type(s) to standardize (default: all, including congressional districts as 'cd')")
    parser.add_argument("--vintage", nargs="+", choices=["2010", "2020"], default=["2010", "2020"],
                         help="Census vintage(s) to standardize (default: both; ignored for 'cd')")
    parser.add_argument("--congress", nargs="+", type=int, choices=list(CD_FIELD_MAP), default=list(CD_FIELD_MAP),
                         help="Congress number(s) to standardize for 'cd' (default: both 113 and 118)")
    args = parser.parse_args()

    for geography_type in args.geography:
        if geography_type == "cd":
            for congress in args.congress:
                standardize_cd(congress, STATE_FIPS)
        else:
            for vintage in args.vintage:
                standardize_geography(geography_type, vintage, STATE_FIPS)

    print("\nDone.")


if __name__ == "__main__":
    main()
