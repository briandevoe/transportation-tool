"""Shared 2020 Decennial Census (PL 94-171) fetch logic for
03_build_centroids_block.py. Separate from lib/acs_client.py because it's a
different API family (/dec/pl, not /acs/acs5) with a different geography
hierarchy -- block-level PL 94-171 confirmed live to work with both county
and tract wildcarded in one call (state-wide in a single request, ~107K rows
for Massachusetts), no per-county looping needed.

Requires the same free Census API key as lib/acs_client.py
(https://api.census.gov/data/key_signup.html, CENSUS_API_KEY env var).
"""
import pandas as pd
import requests

GEOGRAPHY = {
    "block": {"for": "block:*", "in": "state:{fips} county:* tract:*", "geoid_cols": ["state", "county", "tract", "block"]},
}


def fetch_block_race_totals(state_fips, year, weight_scheme, api_key):
    """Long-format DataFrame: GEOID (15-digit block), race_ethnicity,
    population. No characteristic dimension -- PL 94-171 has no age/
    disability breakdown, only race/ethnicity headcounts."""
    geo = GEOGRAPHY["block"]
    all_vars = sorted({v for vs in weight_scheme.values() for v in vs})

    resp = requests.get(
        f"https://api.census.gov/data/{year}/dec/pl",
        params={"get": ",".join(all_vars), "for": geo["for"], "in": geo["in"].format(fips=state_fips), "key": api_key},
        timeout=120,
    )
    resp.raise_for_status()
    rows = resp.json()
    df = pd.DataFrame(rows[1:], columns=rows[0])
    for v in all_vars:
        df[v] = pd.to_numeric(df[v], errors="coerce")
    df["GEOID"] = df[geo["geoid_cols"]].agg("".join, axis=1)

    long_rows = [
        {"GEOID": geoid, "race_ethnicity": race_ethnicity, "population": pop}
        for race_ethnicity, var_list in weight_scheme.items()
        for geoid, pop in zip(df["GEOID"], df[var_list].sum(axis=1))
    ]
    return pd.DataFrame(long_rows)
