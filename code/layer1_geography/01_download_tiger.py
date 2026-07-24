"""
Layer 1 (Geography): download Census TIGER/Line boundary files.

TIGER/Line isn't a queryable REST API -- it's bulk shapefiles (one .zip per
state for tract/block group/block, one national .zip for ZCTAs) at a
predictable URL under https://www2.census.gov/geo/tiger/TIGER<year>/. URL
patterns below were verified against the live server, not guessed:

    TRACT/tl_<year>_<state_fips>_tract.zip
    BG/tl_<year>_<state_fips>_bg.zip
    TABBLOCK20/tl_<year>_<state_fips>_tabblock20.zip
    ZCTA520/tl_<year>_us_zcta520.zip           (one file, national, no state loop)

2020 vintage only for now. Each vintage gets its own subfolder under
data/layer1_geography/<year>/ so a later vintage (2010, or post-2030) can sit
alongside without conflict or overwrite.

No unzipping needed to use these -- geopandas reads directly from a zip:
    gpd.read_file("zip://data/layer1_geography/2020/tract/tl_2020_25_tract.zip")

Usage:
    python 01_download_tiger.py                                       # all 4 geography types, all 56 states/territories, 2020
    python 01_download_tiger.py --geography tract                     # just tracts
    python 01_download_tiger.py --geography tract bg                  # tracts and block groups
    python 01_download_tiger.py --geography tract --region conus_ak_hi  # tracts, 50 states + DC, no territories
    python 01_download_tiger.py --state-fips 25                       # just Massachusetts (ignored for zcta -- one national file)
"""
import argparse
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

# Verified against https://www2.census.gov/geo/tiger/TIGER2020/<DIR>/ directly.
# (tiger_dir, filename template, per_state)
GEOGRAPHY_CONFIG = {
    "tract": ("TRACT",      "tl_{year}_{state}_tract.zip",      True),
    "bg":    ("BG",         "tl_{year}_{state}_bg.zip",         True),
    "block": ("TABBLOCK20", "tl_{year}_{state}_tabblock20.zip", True),
    "zcta":  ("ZCTA520",    "tl_{year}_us_zcta520.zip",         False),
}

# The 56 state/territory FIPS codes Census actually publishes TIGER/Line
# files for (50 states + DC + AS/GU/MP/PR/VI), pulled from the live TRACT
# directory listing rather than hand-typed.
STATE_FIPS = [
    "01", "02", "04", "05", "06", "08", "09", "10", "11", "12", "13", "15",
    "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27",
    "28", "29", "30", "31", "32", "33", "34", "35", "36", "37", "38", "39",
    "40", "41", "42", "44", "45", "46", "47", "48", "49", "50", "51", "53",
    "54", "55", "56", "60", "66", "69", "72", "78",
]

# American Samoa, Guam, Northern Mariana Islands, Puerto Rico, US Virgin Islands
TERRITORY_FIPS = ["60", "66", "69", "72", "78"]

REGION_PRESETS = {
    "all":         STATE_FIPS,
    "conus_ak_hi": [f for f in STATE_FIPS if f not in TERRITORY_FIPS],  # 50 states + DC, no territories
}

BASE_URL = "https://www2.census.gov/geo/tiger/TIGER{year}"


def fmt_elapsed(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def download_one(url, dest_path):
    if dest_path.exists():
        return "skipped"
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    try:
        urllib.request.urlretrieve(url, dest_path)
    except Exception as e:
        print(f"    FAILED: {e}")
        return "failed"
    mb = dest_path.stat().st_size / 1e6
    print(f"    {dest_path.name}  ({mb:.0f} MB, {fmt_elapsed(time.time() - t0)})")
    return "downloaded"


def download_geography(geography, year, data_dir, states):
    tiger_dir, name_template, per_state = GEOGRAPHY_CONFIG[geography]
    out_dir = data_dir / str(year) / geography
    print(f"\n[{geography}] -> {out_dir}")

    counts = {"downloaded": 0, "skipped": 0, "failed": 0}
    targets = states if per_state else ["us"]
    for state in targets:
        filename = name_template.format(year=year, state=state)
        url = f"{BASE_URL.format(year=year)}/{tiger_dir}/{filename}"
        result = download_one(url, out_dir / filename)
        counts[result] += 1

    print(f"  {geography}: {counts['downloaded']} downloaded, "
          f"{counts['skipped']} already present, {counts['failed']} failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--geography", nargs="+", choices=list(GEOGRAPHY_CONFIG), default=list(GEOGRAPHY_CONFIG),
                         help="Geography type(s) to download (default: all four)")
    parser.add_argument("--year", type=int, default=2020, help="TIGER/Line vintage year (default: 2020)")
    parser.add_argument("--region", choices=list(REGION_PRESETS), default="all",
                         help="'all' = 56 states/territories, 'conus_ak_hi' = 50 states + DC, no territories (default: all)")
    parser.add_argument("--state-fips", nargs="+", default=None,
                         help="Specific state FIPS code(s) -- overrides --region if given")
    args = parser.parse_args()

    data_dir = REPO_ROOT / "data" / "layer1_geography"
    states = args.state_fips or REGION_PRESETS[args.region]

    for geography in args.geography:
        download_geography(geography, args.year, data_dir, states)

    print("\nDone.")


if __name__ == "__main__":
    main()
