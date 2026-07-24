"""Shared Geofabrik .osm.pbf download/cache logic. Originally lived only in
layer2_network/01_download_osm_roads.py; factored out here once layer4's OSM
POI scripts (02_prepare_grocery_osm.py, 03_prepare_hospitals_osm.py) needed
the exact same "get me this state's cached/downloaded PBF" capability rather
than duplicating the STATE_FIPS_TO_PLACE/GEOFABRIK_NAMES dicts a second time.
"""
import time
import urllib.request
from pathlib import Path

STATE_FIPS_TO_PLACE = {
    "01": "Alabama, USA",        "02": "Alaska, USA",          "04": "Arizona, USA",
    "05": "Arkansas, USA",       "06": "California, USA",      "08": "Colorado, USA",
    "09": "Connecticut, USA",    "10": "Delaware, USA",        "11": "District of Columbia, USA",
    "12": "Florida, USA",        "13": "Georgia, USA",         "15": "Hawaii, USA",
    "16": "Idaho, USA",          "17": "Illinois, USA",        "18": "Indiana, USA",
    "19": "Iowa, USA",           "20": "Kansas, USA",          "21": "Kentucky, USA",
    "22": "Louisiana, USA",      "23": "Maine, USA",           "24": "Maryland, USA",
    "25": "Massachusetts, USA",  "26": "Michigan, USA",        "27": "Minnesota, USA",
    "28": "Mississippi, USA",    "29": "Missouri, USA",        "30": "Montana, USA",
    "31": "Nebraska, USA",       "32": "Nevada, USA",          "33": "New Hampshire, USA",
    "34": "New Jersey, USA",     "35": "New Mexico, USA",      "36": "New York, USA",
    "37": "North Carolina, USA", "38": "North Dakota, USA",    "39": "Ohio, USA",
    "40": "Oklahoma, USA",       "41": "Oregon, USA",          "42": "Pennsylvania, USA",
    "44": "Rhode Island, USA",   "45": "South Carolina, USA",  "46": "South Dakota, USA",
    "47": "Tennessee, USA",      "48": "Texas, USA",           "49": "Utah, USA",
    "50": "Vermont, USA",        "51": "Virginia, USA",        "53": "Washington, USA",
    "54": "West Virginia, USA",  "55": "Wisconsin, USA",       "56": "Wyoming, USA",
    "72": "Puerto Rico",
}

# Geofabrik's north-america/us extract names, by state FIPS. No Hawaii entry
# -- Geofabrik doesn't publish a standalone Hawaii extract -- carried over
# from ../transportation2 as a known, unaddressed gap.
GEOFABRIK_NAMES = {
    "01": "alabama", "02": "alaska", "04": "arizona", "05": "arkansas",
    "06": "california", "08": "colorado", "09": "connecticut", "10": "delaware",
    "11": "district-of-columbia", "12": "florida", "13": "georgia", "16": "idaho",
    "17": "illinois", "18": "indiana", "19": "iowa", "20": "kansas",
    "21": "kentucky", "22": "louisiana", "23": "maine", "24": "maryland",
    "25": "massachusetts", "26": "michigan", "27": "minnesota", "28": "mississippi",
    "29": "missouri", "30": "montana", "31": "nebraska", "32": "nevada",
    "33": "new-hampshire", "34": "new-jersey", "35": "new-mexico", "36": "new-york",
    "37": "north-carolina", "38": "north-dakota", "39": "ohio", "40": "oklahoma",
    "41": "oregon", "42": "pennsylvania", "44": "rhode-island", "45": "south-carolina",
    "46": "south-dakota", "47": "tennessee", "48": "texas", "49": "utah",
    "50": "vermont", "51": "virginia", "53": "washington", "54": "west-virginia",
    "55": "wisconsin", "56": "wyoming",
}


def fmt_elapsed(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def download_pbf(geofabrik_name, raw_dir):
    raw_dir.mkdir(parents=True, exist_ok=True)
    pbf_path = raw_dir / f"{geofabrik_name}-latest.osm.pbf"
    if pbf_path.exists():
        print(f"  {pbf_path.name} already present, skipping download.")
        return pbf_path
    url = f"https://download.geofabrik.de/north-america/us/{geofabrik_name}-latest.osm.pbf"
    print(f"  Downloading PBF from Geofabrik: {geofabrik_name}...")
    t0 = time.time()
    urllib.request.urlretrieve(url, pbf_path)
    print(f"  Downloaded ({fmt_elapsed(time.time() - t0)}, {pbf_path.stat().st_size / 1e6:.0f} MB)")
    return pbf_path


def get_pbf_path(state_fips, raw_dir):
    """Resolve a state FIPS code to its cached (or freshly downloaded)
    Geofabrik PBF path. Raises SystemExit if there's no extract mapping."""
    place = STATE_FIPS_TO_PLACE.get(state_fips, f"state FIPS {state_fips}")
    geofabrik_name = GEOFABRIK_NAMES.get(state_fips)
    if geofabrik_name is None:
        raise SystemExit(f"No Geofabrik extract mapping for state FIPS {state_fips} ({place})")
    return download_pbf(geofabrik_name, Path(raw_dir))
