"""
Layer 1 (Geography): download Census TIGER/Line boundary files.

TIGER/Line isn't a queryable REST API -- it's bulk shapefiles (one .zip per
state for tract/block group/block, one national .zip for ZCTAs) at a
predictable URL under https://www2.census.gov/geo/tiger/TIGER<year>/. URL
patterns below were verified against the live server, not guessed, for both
vintages currently supported:

    2020 vintage:
        TRACT/tl_<year>_<state_fips>_tract.zip
        BG/tl_<year>_<state_fips>_bg.zip
        TABBLOCK20/tl_<year>_<state_fips>_tabblock20.zip
        ZCTA520/tl_<year>_us_zcta520.zip           (one file, national, no state loop)
        COUNTY/tl_<year>_us_county.zip              (one file, national, no state loop)
        UNSD/tl_<year>_<state_fips>_unsd.zip        (unified school districts)
        ELSD/tl_<year>_<state_fips>_elsd.zip        (elementary school districts)
        SCSD/tl_<year>_<state_fips>_scsd.zip        (secondary school districts)
        UAC/tl_<year>_us_uac20_corrected.zip        (urban areas, one file, national;
                                                      the 2020-criteria definition -- the
                                                      same folder also still hosts the old
                                                      2010-criteria uac10 file and an
                                                      uncorrected uac20, since Urban Areas
                                                      get redefined each census the same way
                                                      RUCA does; "_corrected" supersedes the
                                                      original 2020 release, verified same
                                                      order of magnitude in size, not a
                                                      small patch)
        AIANNH/tl_<year>_us_aiannh.zip               (tribal areas -- American Indian/Alaska
                                                      Native/Native Hawaiian, one file, national)

    2010 vintage -- nested one directory level deeper than 2020, and
    filenames carry a "10" geography suffix instead of a bare/"20" one:
        TRACT/2010/tl_<year>_<state_fips>_tract10.zip
        BG/2010/tl_<year>_<state_fips>_bg10.zip
        TABBLOCK/2010/tl_<year>_<state_fips>_tabblock10.zip
        ZCTA5/2010/tl_<year>_us_zcta510.zip        (one file, national, no state loop)
        COUNTY/2010/tl_<year>_us_county10.zip       (one file, national, no state loop;
                                                      per-state county10 files also exist
                                                      but the national file is simpler and
                                                      matches the 2020 county pattern)
        UNSD/2010/tl_<year>_<state_fips>_unsd10.zip
        ELSD/2010/tl_<year>_<state_fips>_elsd10.zip
        SCSD/2010/tl_<year>_<state_fips>_scsd10.zip
        UA/2010/tl_<year>_us_uac10.zip               (urban areas, one file, national;
                                                       per-territory uac10 files also exist
                                                       but the national file matches the
                                                       2020 pattern)
        AIANNH/2010/tl_<year>_us_aiannh10.zip         (tribal areas, one file, national;
                                                       per-state aiannh10 files also exist
                                                       but the national file matches the
                                                       2020 pattern)

School districts: not every state has all three types -- most states use
either unified districts OR a split of elementary+secondary, not both. Only
~26 states have a UNSD file and ~20-24 have ELSD/SCSD (verified counts against
the live server), so requesting all three for all 56 states/territories is
expected to produce a lot of per-state 404s ("failed") for whichever type(s)
a given state doesn't use -- that's normal, not a bug, and downstream code
should union whichever type(s) exist per state rather than expect one.

Congressional districts are NOT here -- they're vintaged by congress number,
not census year, and don't fit this year-keyed config (see
02_download_congressional_dist.py).

Each vintage gets its own subfolder under data/layer1_geography/raw/<year>/
so multiple vintages (2010, 2020, and eventually post-2030) can sit
alongside each other without conflict or overwrite. Raw downloads live
under raw/ to keep them clearly separate from processed/ (see
04_standardize_geographies.py).

No unzipping needed to use these -- geopandas reads directly from a zip:
    gpd.read_file("zip://data/layer1_geography/raw/2020/tract/tl_2020_25_tract.zip")

Usage:
    python 01_download_tiger.py                                       # all geography types, all 56 states/territories, 2020
    python 01_download_tiger.py --year 2010                           # same, but 2010 vintage
    python 01_download_tiger.py --geography tract                     # just tracts
    python 01_download_tiger.py --geography tract bg                  # tracts and block groups
    python 01_download_tiger.py --geography tract --region conus_ak_hi  # tracts, 50 states + DC, no territories
    python 01_download_tiger.py --state-fips 25                       # just Massachusetts (ignored for zcta/county -- one national file)
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.tiger_download import BASE_URL, REGION_PRESETS, download_one

REPO_ROOT = Path(__file__).parent.parent.parent

# Verified against https://www2.census.gov/geo/tiger/TIGER<year>/<DIR>/ directly,
# per vintage -- 2010's directory structure and filenames differ enough from
# 2020's (and every other year hasn't been checked) that vintages are looked
# up explicitly rather than guessed from a year range.
# (tiger_dir, filename template, per_state)
GEOGRAPHY_CONFIG_BY_VINTAGE = {
    2020: {
        "tract":              ("TRACT",      "tl_{year}_{state}_tract.zip",      True),
        "bg":                 ("BG",         "tl_{year}_{state}_bg.zip",         True),
        "block":              ("TABBLOCK20", "tl_{year}_{state}_tabblock20.zip", True),
        "zcta":               ("ZCTA520",    "tl_{year}_us_zcta520.zip",         False),
        "county":             ("COUNTY",     "tl_{year}_us_county.zip",          False),
        "school_unified":     ("UNSD",       "tl_{year}_{state}_unsd.zip",       True),
        "school_elementary":  ("ELSD",       "tl_{year}_{state}_elsd.zip",       True),
        "school_secondary":   ("SCSD",       "tl_{year}_{state}_scsd.zip",       True),
        "urban_area":         ("UAC",        "tl_{year}_us_uac20_corrected.zip", False),
        "tribal_area":        ("AIANNH",     "tl_{year}_us_aiannh.zip",          False),
    },
    2010: {
        "tract":              ("TRACT/2010",    "tl_{year}_{state}_tract10.zip",      True),
        "bg":                 ("BG/2010",       "tl_{year}_{state}_bg10.zip",         True),
        "block":              ("TABBLOCK/2010", "tl_{year}_{state}_tabblock10.zip",   True),
        "zcta":               ("ZCTA5/2010",    "tl_{year}_us_zcta510.zip",           False),
        "county":             ("COUNTY/2010",   "tl_{year}_us_county10.zip",          False),
        "school_unified":     ("UNSD/2010",     "tl_{year}_{state}_unsd10.zip",       True),
        "school_elementary":  ("ELSD/2010",     "tl_{year}_{state}_elsd10.zip",       True),
        "school_secondary":   ("SCSD/2010",     "tl_{year}_{state}_scsd10.zip",       True),
        "urban_area":         ("UA/2010",       "tl_{year}_us_uac10.zip",             False),
        "tribal_area":        ("AIANNH/2010",   "tl_{year}_us_aiannh10.zip",          False),
    },
}


def download_geography(geography, year, data_dir, states):
    if year not in GEOGRAPHY_CONFIG_BY_VINTAGE:
        supported = ", ".join(str(y) for y in sorted(GEOGRAPHY_CONFIG_BY_VINTAGE))
        raise SystemExit(f"No verified URL pattern for vintage {year} yet -- supported: {supported}")
    tiger_dir, name_template, per_state = GEOGRAPHY_CONFIG_BY_VINTAGE[year][geography]
    out_dir = data_dir / str(year) / geography
    print(f"\n[{geography}] -> {out_dir}")

    counts = {"downloaded": 0, "skipped": 0, "failed": 0}
    targets = states if per_state else ["us"]
    for state in targets:
        filename = name_template.format(year=year, state=state)
        url = f"{BASE_URL.format(year=year)}/{tiger_dir}/{filename}"
        result = download_one(url, out_dir / filename)
        counts[result] += 1
        if result != "skipped":
            time.sleep(0.3)  # avoid tripping the server's rate limit on back-to-back requests

    print(f"  {geography}: {counts['downloaded']} downloaded, "
          f"{counts['skipped']} already present, {counts['failed']} failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    geography_types = list(GEOGRAPHY_CONFIG_BY_VINTAGE[2020])
    parser.add_argument("--geography", nargs="+", choices=geography_types, default=geography_types,
                         help="Geography type(s) to download (default: all)")
    parser.add_argument("--year", type=int, default=2020,
                         help=f"TIGER/Line vintage year (default: 2020; supported: {sorted(GEOGRAPHY_CONFIG_BY_VINTAGE)})")
    parser.add_argument("--region", choices=list(REGION_PRESETS), default=None,
                         help="'all' = 56 states/territories, 'conus_ak_hi' = 50 states + DC, no territories -- "
                              "use this instead of --state-fips to run many states in one invocation")
    parser.add_argument("--state-fips", nargs="+", default=["25"],
                         help="Specific state FIPS code(s) (default: 25, Massachusetts) -- overridden by --region if given")
    args = parser.parse_args()

    data_dir = REPO_ROOT / "data" / "layer1_geography" / "raw"
    states = REGION_PRESETS[args.region] if args.region else args.state_fips

    for geography in args.geography:
        download_geography(geography, args.year, data_dir, states)

    print("\nDone.")


if __name__ == "__main__":
    main()
