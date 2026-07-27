"""Fixes Connecticut GEOIDs from ACS 2022+ (new planning-region county
codes) back to the old-county-based GEOIDs Layer 1's TIGER 2020 geometry
uses. Connecticut's 8 legacy counties were replaced by 9 new state-defined
planning regions as county-equivalents starting with the 2022 ACS release,
changing every Connecticut GEOID's county segment even though tract/
block-group boundaries themselves never moved. Without this, every
Connecticut row silently fails to join to Layer 1 geometry (confirmed live:
100% null lat/lon for state 09, vs. the normal 3-18% sparse-population rate
everywhere else).

Same underlying problem the COI 3.0 team hit and solved (see docs/COI 3.0
Technical Documentation 20250724.pdf, Appendix 6, "Connecticut planning
regions") -- this crosswalk follows their approach: match the trailing
6-digit tract code between the old (county-based) and new (region-based)
GEOID, since that code alone uniquely identifies 879 of 883 Connecticut
tracts. The crosswalk itself (data/layer3_population/ct_geoid_crosswalk.csv,
built once by code/layer3_population/_build_ct_crosswalk.py, not part of
the regular pipeline) was built directly from this repo's own Layer 1 tract
list plus one live ACS query, not copied from COI -- but the 4 remaining
ambiguous tracts (reused placeholder tract codes "990000"/"990100", used
for institutional or water-covered tracts) can't be resolved by code-
matching alone. 3 of those 4 are hardcoded below using COI's own published
resolution (obtained by them via spatial analysis); the 4th -- a tract
fully covered by water that split into two in 2022 -- is dropped entirely,
matching COI's choice not to invent an arbitrary counterpart for it.

Does NOT apply to Decennial Census data (lib/decennial_client.py) --
confirmed live that 2020 Decennial PL 94-171 still uses the old county
codes for Connecticut (it predates the 2022 switch), so 03_build_centroids_block.py
never had this bug.
"""
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).parent.parent.parent
CROSSWALK_PATH = REPO_ROOT / "data" / "layer3_population" / "ct_geoid_crosswalk.csv"

_crosswalk = None


def _load_crosswalk():
    global _crosswalk
    if _crosswalk is None:
        df = pd.read_csv(CROSSWALK_PATH, dtype=str)
        _crosswalk = dict(zip(df["geoid_new"], df["geoid_old"]))
    return _crosswalk


def fix_ct_geoids(df, geoid_col="GEOID"):
    """Rewrites any Connecticut (state prefix '09') GEOID using the new
    planning-region county codes back to its old-county equivalent. Safe to
    call unconditionally on any GEOID column -- non-Connecticut GEOIDs and
    already-old-vintage Connecticut GEOIDs pass through untouched (the
    crosswalk is keyed only by new-vintage GEOIDs, so anything else is a
    lookup miss, not a mistaken rewrite). Works for both tract-level
    (11-digit) and block-group-level (12-digit) GEOIDs -- block groups
    nest inside tracts and never moved either, so the crosswalk (built at
    the tract level) is applied to the leading 11 digits and any trailing
    block-group digit is carried through as-is. A Connecticut GEOID with no
    crosswalk entry (the one dropped tract, or anything unexpected) is left
    as-is -- it simply won't join to Layer 1 geometry downstream, which is
    correct behavior for genuinely unmappable data rather than a silent
    guess.
    """
    crosswalk = _load_crosswalk()

    def _fix(geoid):
        if not isinstance(geoid, str) or not geoid.startswith("09") or len(geoid) < 11:
            return geoid
        tract_part, suffix = geoid[:11], geoid[11:]
        return crosswalk.get(tract_part, tract_part) + suffix

    df = df.copy()
    df[geoid_col] = df[geoid_col].apply(_fix)
    return df
