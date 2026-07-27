"""Shared Census ACS 5-year fetch logic for layer3_population.

Generalizes ../transportation2/v2_archive/code/01_download_acs.py's
fetch()/build_vars() (same requests-based approach, same CENSUS_API_KEY env
var convention) to loop over a whole race/ethnicity scheme x characteristic
list in one call instead of one race/one population type, and to support
"block group" geography (needed for centroid weighting) as well as "tract".

Requires a free Census API key: https://api.census.gov/data/key_signup.html
Set via the CENSUS_API_KEY env var. Confirmed live that ACS data queries
(unlike the groups/variables metadata endpoints) return an HTTP 200 "Missing
Key" error page without one -- so a bad/missing key fails as a parse error,
not an HTTP error; get_api_key() below fails fast instead.
"""
import os

import pandas as pd
import requests

from lib.acs_characteristics import variable_codes
from lib.ct_geoid_crosswalk import fix_ct_geoids

CENSUS_MAX_VARS_PER_REQUEST = 50  # Census API hard limit on variables per request

GEOGRAPHY = {
    "tract":       {"for": "tract:*",       "in": "state:{fips} county:*",             "geoid_cols": ["state", "county", "tract"]},
    "block group": {"for": "block group:*", "in": "state:{fips} county:* tract:*",      "geoid_cols": ["state", "county", "tract", "block group"]},
}


def get_api_key(cli_value=None):
    key = cli_value or os.environ.get("CENSUS_API_KEY")
    if not key:
        raise SystemExit(
            "No Census API key. Set CENSUS_API_KEY or pass --api-key. "
            "Get one at https://api.census.gov/data/key_signup.html"
        )
    return key


def _chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def _fetch_chunk(year, geo, state_fips, variables, api_key):
    resp = requests.get(
        f"https://api.census.gov/data/{year}/acs/acs5",
        params={"get": ",".join(variables), "for": geo["for"], "in": geo["in"].format(fips=state_fips), "key": api_key},
        timeout=60,
    )
    resp.raise_for_status()
    rows = resp.json()
    return pd.DataFrame(rows[1:], columns=rows[0])


def fetch_population(state_fips, year, geography, race_scheme, characteristics, api_key):
    """Long-format DataFrame: GEOID, race_ethnicity, characteristic, population.

    race_scheme: dict like race_ethnicity_schemes.SIMPLIFIED_5 (category -> ACS
    letter suffixes). "total" (all races combined, via the plain table with no
    letter suffix) is always included in addition to the scheme's categories.
    """
    geo = GEOGRAPHY[geography]
    categories = {"total": [None], **race_scheme}

    # (race_ethnicity, characteristic) -> the ACS variable codes to sum for it.
    # A category with multiple letters (e.g. other_nh = C+E+F+G) sums across
    # all of them, not just within one letter's own age/sex rows.
    target_vars = {
        (race_ethnicity, characteristic): [v for letter in letters for v in variable_codes(characteristic, letter)]
        for race_ethnicity, letters in categories.items()
        for characteristic in characteristics
    }
    all_vars = sorted({v for vs in target_vars.values() for v in vs})

    frames = [_fetch_chunk(year, geo, state_fips, chunk, api_key) for chunk in _chunked(all_vars, CENSUS_MAX_VARS_PER_REQUEST)]
    df = frames[0]
    for frame in frames[1:]:
        df = df.merge(frame, on=geo["geoid_cols"])
    for v in all_vars:
        df[v] = pd.to_numeric(df[v], errors="coerce")
    df["GEOID"] = df[geo["geoid_cols"]].agg("".join, axis=1)
    df = fix_ct_geoids(df)  # ACS 2022+ uses CT's new planning-region county codes; Layer 1 geometry doesn't

    long_rows = [
        {"GEOID": geoid, "race_ethnicity": race_ethnicity, "characteristic": characteristic, "population": pop}
        for (race_ethnicity, characteristic), var_list in target_vars.items()
        for geoid, pop in zip(df["GEOID"], df[var_list].sum(axis=1))
    ]
    return pd.DataFrame(long_rows)


def fetch_race_totals(state_fips, year, geography, weight_scheme, api_key):
    """Long-format DataFrame: GEOID, race_ethnicity, population -- general
    (all-ages, no disability filter) race/ethnicity population, e.g. via
    B03002. No characteristic dimension: unlike fetch_population(), this is
    for sources that only publish plain race totals (no age/disability
    breakdown) -- see race_ethnicity_schemes.SIMPLIFIED_5_WEIGHTS_B03002 for
    why that's needed at block-group geography specifically.
    """
    geo = GEOGRAPHY[geography]
    all_vars = sorted({v for vs in weight_scheme.values() for v in vs})

    frames = [_fetch_chunk(year, geo, state_fips, chunk, api_key) for chunk in _chunked(all_vars, CENSUS_MAX_VARS_PER_REQUEST)]
    df = frames[0]
    for frame in frames[1:]:
        df = df.merge(frame, on=geo["geoid_cols"])
    for v in all_vars:
        df[v] = pd.to_numeric(df[v], errors="coerce")
    df["GEOID"] = df[geo["geoid_cols"]].agg("".join, axis=1)
    df = fix_ct_geoids(df)  # ACS 2022+ uses CT's new planning-region county codes; Layer 1 geometry doesn't

    long_rows = [
        {"GEOID": geoid, "race_ethnicity": race_ethnicity, "population": pop}
        for race_ethnicity, var_list in weight_scheme.items()
        for geoid, pop in zip(df["GEOID"], df[var_list].sum(axis=1))
    ]
    return pd.DataFrame(long_rows)
