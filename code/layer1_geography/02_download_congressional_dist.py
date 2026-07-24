"""
Layer 1 (Geography): download Census TIGER/Line congressional district
boundaries.

Deliberately a separate script from 01_download_tiger.py: every other
geography type there is vintaged by census year (2010/2020) and hosted at a
URL predictable from that year. Congressional districts are vintaged by
**congress number** instead, and -- verified directly against the live
server, not assumed -- there's no formula mapping a congress number to the
TIGER<year> folder that hosts it:

    Congress 113 (2013-2015) -> TIGER2013/CD/tl_2013_us_cd113.zip
                                 (one file, national, no state loop)
    Congress 118 (2023-2025) -> TIGER2020/CD/CD118/tl_2020_<state>_cd118.zip
                                 (per state -- note it's still hosted under
                                 TIGER2020, three years after that vintage)
    Congress 116 also lives directly under TIGER2020/CD/, alongside the
    CD118/ subfolder -- Census keeps appending newer congresses' files into
    whichever TIGER<year> folder was current when they published them,
    rather than creating a new TIGER<year> folder per congress. So each
    congress's hosting location must be looked up and verified by hand
    (below) rather than computed.

Which congress matches which census: redistricting based on a decennial
census first takes effect for elections held two years after the census, so:
    2010 Census -> first used starting with the 113th Congress (seated 2013)
    2020 Census -> first used starting with the 118th Congress (seated 2023)
These are the two vintages this script defaults to.

Output goes to data/layer1_geography/raw/cd<congress>/ -- a "cd"-prefixed
folder name (not a bare number) so it's never visually confusable with a
census-year vintage folder like data/layer1_geography/raw/2020/.

Usage:
    python 02_download_congressional_dist.py                     # both 113 (2010 census) and 118 (2020 census)
    python 02_download_congressional_dist.py --congress 118       # just the 2020-census-based map
    python 02_download_congressional_dist.py --congress 118 --state-fips 25  # just Massachusetts
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from lib.tiger_download import BASE_URL, REGION_PRESETS, download_one

REPO_ROOT = Path(__file__).parent.parent.parent

# Verified against https://www2.census.gov/geo/tiger/TIGER<tiger_year>/CD/
# directly -- each entry is a hand-confirmed (tiger_year, tiger_dir,
# filename template, per_state), not a computed pattern (see module
# docstring for why one can't be computed).
CONGRESS_CONFIG = {
    113: (2013, "CD",      "tl_{tiger_year}_us_cd113.zip",      False),
    118: (2020, "CD/CD118", "tl_{tiger_year}_{state}_cd118.zip", True),
}

DEFAULT_CONGRESSES = [113, 118]


def download_congress(congress, data_dir, states):
    tiger_year, tiger_dir, name_template, per_state = CONGRESS_CONFIG[congress]
    out_dir = data_dir / f"cd{congress}"
    print(f"\n[cd{congress}] -> {out_dir}")

    counts = {"downloaded": 0, "skipped": 0, "failed": 0}
    targets = states if per_state else ["us"]
    for state in targets:
        filename = name_template.format(tiger_year=tiger_year, state=state)
        url = f"{BASE_URL.format(year=tiger_year)}/{tiger_dir}/{filename}"
        result = download_one(url, out_dir / filename)
        counts[result] += 1
        if result != "skipped":
            time.sleep(0.3)  # avoid tripping the server's rate limit on back-to-back requests

    print(f"  cd{congress}: {counts['downloaded']} downloaded, "
          f"{counts['skipped']} already present, {counts['failed']} failed")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--congress", nargs="+", type=int, choices=list(CONGRESS_CONFIG), default=DEFAULT_CONGRESSES,
                         help=f"Congress number(s) to download (default: {DEFAULT_CONGRESSES}, "
                              "the first congress based on each of the 2010 and 2020 censuses)")
    parser.add_argument("--region", choices=list(REGION_PRESETS), default="all",
                         help="'all' = 56 states/territories, 'conus_ak_hi' = 50 states + DC, no territories (default: all)")
    parser.add_argument("--state-fips", nargs="+", default=None,
                         help="Specific state FIPS code(s) -- overrides --region if given (ignored for congress 113 -- one national file)")
    args = parser.parse_args()

    data_dir = REPO_ROOT / "data" / "layer1_geography" / "raw"
    states = args.state_fips or REGION_PRESETS[args.region]

    for congress in args.congress:
        download_congress(congress, data_dir, states)

    print("\nDone.")


if __name__ == "__main__":
    main()
