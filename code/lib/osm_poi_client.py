"""Shared OSM point-of-interest extraction for layer4_destination scripts
(currently grocery stores and hospitals). Verified live against the cached
Massachusetts PBF before writing any of this:

  - OSM.get_pois(custom_filter=...) is a genuine inclusion filter -- unlike
    get_network() (see layer2_network/01_download_osm_roads.py), it has no
    filter_type parameter at all, and a live pull returned exactly the
    expected matches, not their inverse.
  - Many matches are polygon geometries (about half, in MA -- mostly
    building footprints), and pyrosm's raw lat/lon columns are only
    populated for Point rows. geometry.centroid is used here instead,
    uniformly, since centroid-of-a-point is just the point itself.
  - The filter can loosely admit a few rows that don't actually match any
    requested tag value (confirmed live: ~3 of 851) -- match_fn re-checks
    explicitly rather than trusting the filter alone.
"""
from datetime import date

import pandas as pd
from pyrosm import OSM

SOURCE_LABEL = "OSM (Geofabrik)"


def _combine_address(row):
    number = row.get("addr:housenumber")
    street = row.get("addr:street")
    if pd.notna(number) and pd.notna(street):
        return f"{number} {street}"
    return street if pd.notna(street) else (number if pd.notna(number) else None)


def extract_pois(pbf_path, tag_filter, match_fn, category_fn, dest_type, state_fips):
    """Returns a long-format DataFrame (dest_id, dest_type, name, lat, lon,
    category, address, city, state_fips, source, year) -- not yet run
    through lib.destination_schema.validate_destinations(), left to the
    calling script same as lib/acs_client.py's fetch functions."""
    osm = OSM(str(pbf_path))
    pois = osm.get_pois(custom_filter=tag_filter)
    if pois is None or len(pois) == 0:
        return pd.DataFrame()

    pois = pois[pois.apply(match_fn, axis=1)]
    before = len(pois)
    pois = pois[pois["name"].notna()]
    print(f"  {len(pois)} matched with a name (dropped {before - len(pois)} unnamed)")
    if pois.empty:
        return pd.DataFrame()

    centroids = pois.geometry.centroid

    out = pd.DataFrame({
        "dest_id": "osm_" + pois["id"].astype(str),
        "dest_type": dest_type,
        "name": pois["name"],
        "lat": centroids.y.values,
        "lon": centroids.x.values,
        "category": pois.apply(category_fn, axis=1),
        "address": pois.apply(_combine_address, axis=1),
        "city": pois["addr:city"] if "addr:city" in pois.columns else None,
        "state_fips": state_fips,
        "source": SOURCE_LABEL,
        "year": date.today().isoformat(),
    })
    return out.reset_index(drop=True)
