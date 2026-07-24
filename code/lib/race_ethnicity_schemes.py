"""Swappable race/ethnicity category schemes for layer3_population.

Every scheme maps a category label -> the ACS race-iterated table letter
suffix(es) to sum (B01001<letter>, B18101<letter>, ... -- ACS uses the same
A-I letter convention across every race-iterated detailed table, so one
mapping drives every characteristic pull in acs_characteristics.py).

Letters: A=White alone, B=Black alone, C=AIAN alone, D=Asian alone,
E=NHPI alone, F=Some Other Race alone, G=Two or More Races,
H=White alone Not Hispanic, I=Hispanic or Latino (any race).

Caveat (not solved here, just disclosed): ACS only publishes a true "alone,
not Hispanic" iteration for White (H). Black/Asian/AIAN/NHPI/Other have no
NH-specific version in the age (B01001) or disability (B18101) table
families, so black_nh/asian_nh/other_nh below include a small Hispanic
overlap for those characteristics. Fixing this exactly would require ACS
PUMS microdata, which only exists at the much coarser PUMA level.

Adding a new scheme = adding another dict below and pointing ACTIVE_SCHEME
at it; nothing else in the pipeline changes.
"""

SIMPLIFIED_5 = {
    "white_nh": ["H"],
    "black_nh": ["B"],
    "hispanic": ["I"],
    "asian_nh": ["D"],
    "other_nh": ["C", "E", "F", "G"],
}

SCHEMES = {
    "simplified_5": SIMPLIFIED_5,
}

ACTIVE_SCHEME_NAME = "simplified_5"


def get_scheme(name=ACTIVE_SCHEME_NAME):
    if name not in SCHEMES:
        raise ValueError(f"Unknown race/ethnicity scheme '{name}'. Options: {list(SCHEMES)}")
    return SCHEMES[name]


# B03002 (Hispanic Origin by Race) variable codes, for general-population
# weighting only -- verified live against the Census API. Unlike the
# B01001/B18101 letter tables (which only publish at tract or coarser, per
# lib/acs_client.py's docstring), B03002 publishes at block group AND gives
# true "not Hispanic" figures for every category, not just White -- so it's
# strictly better for weighting even though, like the letter tables at block
# group, it can't provide age/disability breakdowns.
SIMPLIFIED_5_WEIGHTS_B03002 = {
    "total":     ["B03002_001E"],  # general-population fallback for race_ethnicity="total" when a
                                    # characteristic's table isn't bg_available (e.g. disability)
    "white_nh": ["B03002_003E"],
    "black_nh": ["B03002_004E"],
    "hispanic": ["B03002_012E"],
    "asian_nh": ["B03002_006E"],
    "other_nh": ["B03002_005E", "B03002_007E", "B03002_008E", "B03002_009E"],
}

WEIGHT_SCHEMES = {
    "simplified_5": SIMPLIFIED_5_WEIGHTS_B03002,
}


def get_weight_scheme(name=ACTIVE_SCHEME_NAME):
    if name not in WEIGHT_SCHEMES:
        raise ValueError(f"Unknown weight scheme '{name}'. Options: {list(WEIGHT_SCHEMES)}")
    return WEIGHT_SCHEMES[name]


# 2020 Decennial PL 94-171 table P2 (Hispanic or Latino Origin by Race)
# variable codes, for 03_build_centroids_block.py -- verified live. Cleaner
# than B03002/P1: P2 already has a single pre-aggregated "two or more races"
# bucket (P2_011N), no need to sum the dozens of specific-combination
# variables P1 would require for the same "other" category.
SIMPLIFIED_5_WEIGHTS_PL94171 = {
    "total":     ["P2_001N"],
    "white_nh":  ["P2_005N"],
    "black_nh":  ["P2_006N"],
    "hispanic":  ["P2_002N"],
    "asian_nh":  ["P2_008N"],
    "other_nh":  ["P2_007N", "P2_009N", "P2_010N", "P2_011N"],
}

DECENNIAL_WEIGHT_SCHEMES = {
    "simplified_5": SIMPLIFIED_5_WEIGHTS_PL94171,
}


def get_decennial_weight_scheme(name=ACTIVE_SCHEME_NAME):
    if name not in DECENNIAL_WEIGHT_SCHEMES:
        raise ValueError(f"Unknown decennial weight scheme '{name}'. Options: {list(DECENNIAL_WEIGHT_SCHEMES)}")
    return DECENNIAL_WEIGHT_SCHEMES[name]
