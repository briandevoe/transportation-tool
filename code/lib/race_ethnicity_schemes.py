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

detailed_7 splits simplified_5's "other_nh" bucket (C+E+F+G) into its
constituent groups -- the general 7-group standard used broadly in
child-equity research. Initially guessed this was also COI's own breakdown;
confirmed against COI 3.0's actual technical documentation (docs/COI 3.0
Technical Documentation 20250724.pdf) that it is NOT -- COI explicitly uses
5 groups (p.46: "We compute Ij separately for Asian, Black, Hispanic,
American Indian/Alaska Native and non-Hispanic White children"), matching
the child-population-counts file already cached in this repo. coi_5 below
is that actual COI definition: it merges Asian with Native Hawaiian/Pacific
Islander (D+E) into one "asian" group, keeps AIAN (C) as its own group, and
-- unlike simplified_5/detailed_7 -- doesn't fold "Some Other Race" (F) or
"Two or More Races" (G) into any group at all; COI simply excludes them from
its race-specific breakdown rather than bucketing them as "other." Only
"white_nh" is genuinely NH-exclusive by construction (ACS's H letter); COI's
own black/asian/aian labels aren't NH-specific either (its data dictionary
describes them as "alone," not "alone, not Hispanic"), so they carry the
same small Hispanic-overlap caveat above.
"""

SIMPLIFIED_5 = {
    "white_nh": ["H"],
    "black_nh": ["B"],
    "hispanic": ["I"],
    "asian_nh": ["D"],
    "other_nh": ["C", "E", "F", "G"],
}

DETAILED_7 = {
    "white_nh": ["H"],
    "black_nh": ["B"],
    "hispanic": ["I"],
    "asian_nh": ["D"],
    "aian_nh": ["C"],
    "nhpi_nh": ["E"],
    "other_multiracial_nh": ["F", "G"],
}

COI_5 = {
    "white_nh": ["H"],
    "black": ["B"],
    "hispanic": ["I"],
    "asian": ["D", "E"],
    "aian": ["C"],
}

SCHEMES = {
    "simplified_5": SIMPLIFIED_5,
    "detailed_7": DETAILED_7,
    "coi_5": COI_5,
}

ACTIVE_SCHEME_NAME = "coi_5"  # COI is expected to be this project's most-used reference layer


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

DETAILED_7_WEIGHTS_B03002 = {
    "total":                ["B03002_001E"],
    "white_nh":             ["B03002_003E"],
    "black_nh":             ["B03002_004E"],
    "hispanic":             ["B03002_012E"],
    "asian_nh":             ["B03002_006E"],
    "aian_nh":              ["B03002_005E"],
    "nhpi_nh":              ["B03002_007E"],
    "other_multiracial_nh": ["B03002_008E", "B03002_009E"],
}

# B03002's race breakdown (003-009) is already Hispanic-origin-cross-tabulated
# (it splits Hispanic vs. not-Hispanic first, then race within not-Hispanic),
# so black/asian/aian here genuinely ARE NH-exclusive -- unlike the same
# labels in COI_5 above, which come from the B01001/B18101 letter tables and
# do carry the Hispanic-overlap caveat. Both share the same key names
# because the merge logic requires it, not because the underlying precision
# matches.
COI_5_WEIGHTS_B03002 = {
    "total":     ["B03002_001E"],
    "white_nh":  ["B03002_003E"],
    "black":     ["B03002_004E"],
    "hispanic":  ["B03002_012E"],
    "asian":     ["B03002_006E", "B03002_007E"],
    "aian":      ["B03002_005E"],
}

WEIGHT_SCHEMES = {
    "simplified_5": SIMPLIFIED_5_WEIGHTS_B03002,
    "detailed_7": DETAILED_7_WEIGHTS_B03002,
    "coi_5": COI_5_WEIGHTS_B03002,
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

DETAILED_7_WEIGHTS_PL94171 = {
    "total":                ["P2_001N"],
    "white_nh":             ["P2_005N"],
    "black_nh":             ["P2_006N"],
    "hispanic":             ["P2_002N"],
    "asian_nh":             ["P2_008N"],
    "aian_nh":              ["P2_007N"],
    "nhpi_nh":              ["P2_009N"],
    "other_multiracial_nh": ["P2_010N", "P2_011N"],
}

# P2's race breakdown (005-011) is NH-exclusive by construction, same
# reasoning as COI_5_WEIGHTS_B03002 above.
COI_5_WEIGHTS_PL94171 = {
    "total":     ["P2_001N"],
    "white_nh":  ["P2_005N"],
    "black":     ["P2_006N"],
    "hispanic":  ["P2_002N"],
    "asian":     ["P2_008N", "P2_009N"],
    "aian":      ["P2_007N"],
}

DECENNIAL_WEIGHT_SCHEMES = {
    "simplified_5": SIMPLIFIED_5_WEIGHTS_PL94171,
    "detailed_7": DETAILED_7_WEIGHTS_PL94171,
    "coi_5": COI_5_WEIGHTS_PL94171,
}


def get_decennial_weight_scheme(name=ACTIVE_SCHEME_NAME):
    if name not in DECENNIAL_WEIGHT_SCHEMES:
        raise ValueError(f"Unknown decennial weight scheme '{name}'. Options: {list(DECENNIAL_WEIGHT_SCHEMES)}")
    return DECENNIAL_WEIGHT_SCHEMES[name]
