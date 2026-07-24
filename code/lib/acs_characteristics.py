"""Swappable "characteristic" definitions for layer3_population -- which ACS
table (and which rows within it) to pull for each demographic slice.

Verified live against the Census API, not guessed:
  - B01001<letter> (Sex by Age) row numbers differ between the combined
    "all races" table and the race-iterated tables, because the
    race-iterated tables have fewer age bins -- confirmed against
    https://api.census.gov/data/2022/acs/acs5/groups/B01001A.json.
  - B18101<letter> (Sex by Age by Disability Status) has no sex split, just
    Under 18 / 18-64 / 65+, each split into "with disability" / "no
    disability" -- confirmed against
    https://api.census.gov/data/2022/acs/acs5/groups/B18101A.json.
    "disability" here sums the three with-disability cells across every age.
  - B18101's universe is the civilian noninstitutionalized population, not
    total population like B01001 -- that's why the unfiltered "N/A" entry
    uses B01001, not B18101 (using B18101 there would silently undercount).

"N/A" is the unfiltered/no-characteristic-filter entry (population by
race/ethnicity only, no age or disability slice) -- the default so that
race_ethnicity="total" doesn't also read "characteristic=total", which reads
as a confusing double-total. Still a real ACS pull (B01001's grand-total
row), not a placeholder -- just labeled to mean "no filter applied" rather
than implying a specific filter called "total".

Adding a new characteristic = adding one CHARACTERISTICS entry pointing at
whatever ACS table publishes it; nothing else in the pipeline changes.
"""

AGE_ROWS = {
    "all_races": {
        "under_18": {"male": range(3, 7), "female": range(27, 31)},   # <5, 5-9, 10-14, 15-17
        "65_plus":  {"male": range(20, 26), "female": range(44, 50)},  # 65-66 through 85+
    },
    "race_specific": {                          # structure shared by B01001A through B01001I
        "under_18": {"male": range(3, 7), "female": range(18, 22)},
        "65_plus":  {"male": range(14, 17), "female": range(29, 32)},
    },
}

DISABILITY_WITH_DISABILITY_ROWS = [3, 6, 9]  # <letter>_003E, _006E, _009E: under-18/18-64/65+ "with a disability"

# bg_available: whether this table publishes at block-group geography at
# all -- verified live, not assumed identical across table families. B01001
# (age) does, even its plain non-race-iterated grand-total row. B18101
# (disability) does not, confirmed at every level: race-iterated, plain
# total, even the single overall B18101_001E cell -- 0 of 5,116 Massachusetts
# block groups returned a non-null value, vs. 57/57 tracts working fine.
# lib/layer3_population/02_build_centroids_block_group.py uses this to decide
# whether a race_ethnicity="total" row can get characteristic-specific
# block-group weighting or must fall back to general-population weighting
# (same as every non-total race_ethnicity always must, since the
# race-iterated tables never publish below tract regardless of table family).
CHARACTERISTICS = {
    "N/A":        {"table": "B01001", "rows": None, "bg_available": True},
    "under_18":   {"table": "B01001", "rows": "AGE_ROWS", "bg_available": True},
    "65_plus":    {"table": "B01001", "rows": "AGE_ROWS", "bg_available": True},
    "disability": {"table": "B18101", "rows": "DISABILITY_WITH_DISABILITY_ROWS", "bg_available": False},
}


def variable_codes(characteristic, letter=None):
    """ACS variable codes to sum for one characteristic and race letter
    ('H' for White NH, etc). letter=None means the combined all-races table."""
    if characteristic not in CHARACTERISTICS:
        raise ValueError(f"Unknown characteristic '{characteristic}'. Options: {list(CHARACTERISTICS)}")
    spec = CHARACTERISTICS[characteristic]
    prefix = f"{spec['table']}{letter}" if letter else spec["table"]

    if spec["rows"] is None:
        return [f"{prefix}_001E"]

    if spec["rows"] == "AGE_ROWS":
        bucket = "race_specific" if letter else "all_races"
        rows = AGE_ROWS[bucket][characteristic]
        return [f"{prefix}_{i:03d}E" for i in rows["male"]] + [f"{prefix}_{i:03d}E" for i in rows["female"]]

    if spec["rows"] == "DISABILITY_WITH_DISABILITY_ROWS":
        return [f"{prefix}_{i:03d}E" for i in DISABILITY_WITH_DISABILITY_ROWS]

    raise ValueError(f"Unhandled rows spec for characteristic '{characteristic}'")
