"""
Shared TIGER/Line download helpers -- used by every layer1_geography script
that pulls bulk shapefiles from https://www2.census.gov/geo/tiger/TIGER<year>/.
Factored out once a second script (02_download_congressional_dist.py) needed
the same download-with-validation logic as 01_download_tiger.py.
"""
import time
import urllib.error
import urllib.request

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


def download_one(url, dest_path, max_retries=5):
    if dest_path.exists():
        return "skipped"
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    # 429 means "you're going too fast," not "this file doesn't exist" --
    # hit this live requesting ~170 files back-to-back with no delay (a
    # school-district run silently mis-reported real states as missing
    # because their 429 looked identical to a genuine 404 for a state that
    # doesn't use that district type). Retry with backoff specifically for
    # 429; anything else (404, connection error) is a real failure.
    delay = 2
    for attempt in range(max_retries + 1):
        try:
            urllib.request.urlretrieve(url, dest_path)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries:
                print(f"    rate limited, retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2
                continue
            print(f"    FAILED: {e}")
            return "failed"
        except Exception as e:
            print(f"    FAILED: {e}")
            return "failed"

    # A 200 response isn't proof of a real file -- a corporate proxy/firewall
    # can return an HTML block page with a 200 status instead of the zip,
    # which urlretrieve happily saves with no exception raised (hit this
    # live: two states silently got a Cloudflare/WAF rejection page saved as
    # a 600-byte ".zip"). Real zips always start with a "PK" signature.
    with open(dest_path, "rb") as f:
        header = f.read(2)
    if header != b"PK":
        with open(dest_path, "rb") as f:
            snippet = f.read(200).decode("utf-8", errors="replace").strip()
        dest_path.unlink()
        print(f"    FAILED: response wasn't a zip file -- got: {snippet[:120]!r}")
        return "failed"

    mb = dest_path.stat().st_size / 1e6
    print(f"    {dest_path.name}  ({mb:.0f} MB, {fmt_elapsed(time.time() - t0)})")
    return "downloaded"
