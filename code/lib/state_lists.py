"""Shared state-FIPS lists for scripts that process "all states" in one run.

STATE_FIPS_49 was originally defined only in
analysis/01_compute_distance_metrics.py; factored out here once layer4's OSM
destination-prep scripts (grocery, hospitals) needed the same default batch
scope, to avoid a third copy of the list.
"""

# 49 states + DC -- layer1's "conus_ak_hi" scope (its STATE_FIPS list minus
# 5 territory codes), further minus Alaska (02). Excluded by user decision
# (made for the distance-metrics analysis, applied here too for consistency
# building the destination data that feeds it): distances there are both
# genuinely extreme (checked real cases -- rural Alaska Native census areas
# with 8,000-10,000 residents and a nearest school 50-120+ miles away) and a
# poor fit for straight-line distance specifically, since many of those
# communities aren't road-connected at all -- "nearest by air distance"
# understates real travel difficulty rather than overstating it, unlike
# everywhere else this metric is used.
STATE_FIPS_49 = [
    "01", "04", "05", "06", "08", "09", "10", "11", "12", "13", "15",
    "16", "17", "18", "19", "20", "21", "22", "23", "24", "25", "26", "27",
    "28", "29", "30", "31", "32", "33", "34", "35", "36", "37", "38", "39",
    "40", "41", "42", "44", "45", "46", "47", "48", "49", "50", "51", "53",
    "54", "55", "56",
]
