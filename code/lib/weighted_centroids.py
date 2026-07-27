"""Shared population-weighted centroid logic for layer3_population, used by
both 02_build_centroids_block_group.py and 03_build_centroids_block.py
(previously two near-identical copies of the same weighted-average math).

Supports k > 1: instead of collapsing a tract's sub-tract population (block
group or block, whichever the caller passes in) into one weighted-average
point, split it into k population-weighted clusters via a small weighted
k-means, so a tract with two separated population concentrations doesn't
get flattened into a single point that may sit on top of nobody. k=1
(default) skips clustering entirely and reduces to exactly the original
single-centroid math -- verified to produce identical output to the
pre-k-parameter implementation.

Also computes a dispersion metric per centroid: the population-weighted RMS
distance (meters) from each sub-unit to its assigned centroid -- a cheap
diagnostic for how much a given centroid is actually representative of
where its population lives, independent of whether k=1 or k>1 was used.

Distances use a local equirectangular (planar) approximation, not haversine
-- accurate to a few meters at within-tract scale (a few km across at most),
not valid at larger scales. Same category of pragmatic approximation already
used elsewhere in this repo (e.g. layer2_network's EPSG:4269-vs-4326 note).
"""
import numpy as np
import pandas as pd

METERS_PER_DEGREE_LAT = 111_320.0
METERS_PER_DEGREE_LON_AT_EQUATOR = 111_320.0


def _project_to_meters(lat, lon, lat0):
    lat0_rad = np.radians(lat0)
    x_m = lon * METERS_PER_DEGREE_LON_AT_EQUATOR * np.cos(lat0_rad)
    y_m = lat * METERS_PER_DEGREE_LAT
    return x_m, y_m


def _weighted_kmeans(xy, weights, k, seed, n_iter=20):
    """Weighted Lloyd's algorithm. xy: (n,2) planar coords. weights: (n,)
    population. Returns integer cluster labels (n,) in [0,k) -- fewer than k
    distinct labels can come back if a cluster never gets assigned a point
    (caller must not assume exactly k labels present)."""
    n = len(xy)
    if n <= k:
        return np.arange(n)  # not enough distinct points to support k clusters

    rng = np.random.default_rng(seed)
    probs = weights / weights.sum()
    init_idx = rng.choice(n, size=k, replace=False, p=probs)
    centroids = xy[init_idx].copy()
    labels = np.full(n, -1)

    for _ in range(n_iter):
        dists = ((xy[:, None, :] - centroids[None, :, :]) ** 2).sum(axis=2)
        new_labels = dists.argmin(axis=1)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for c in range(k):
            mask = labels == c
            if not mask.any():
                continue  # empty cluster this iteration -- leave its centroid where it was
            w = weights[mask]
            centroids[c] = (xy[mask] * w[:, None]).sum(axis=0) / w.sum()

    return labels


def weighted_centroid_clusters(sub_population, sub_points, group_keys, k=1, seed=0):
    """sub_population: DataFrame with GEOID (sub-tract unit -- block group or
    block), group_keys columns, and population. sub_points: DataFrame with
    GEOID, lat, lon. group_keys: grouping columns beyond the tract itself,
    e.g. ["race_ethnicity"] or ["race_ethnicity", "characteristic"].

    Returns one row per (tract, *group_keys, centroid_index):
        GEOID, *group_keys, centroid_index, centroid_k, population, lat, lon, dispersion_m

    "population" is the sum of the input sub_population values assigned to
    that centroid's cluster -- callers with a more authoritative total (e.g.
    tract-level ACS, which can differ slightly from a block-group aggregate)
    should treat this as a share/proportion and rescale, not use it as the
    final population figure directly. Callers with no better source (e.g.
    decennial block totals) can use it as-is.
    """
    df = sub_population.merge(sub_points, on="GEOID", how="inner")
    df["GEOID_tract"] = df["GEOID"].str[:11]

    all_keys = ["GEOID_tract"] + group_keys
    rows = []
    for group_vals, g in df.groupby(all_keys, sort=False):
        group_vals = group_vals if isinstance(group_vals, tuple) else (group_vals,)
        base = dict(zip(all_keys, group_vals))

        total_pop = g["population"].sum()
        if total_pop == 0:
            rows.append({**base, "centroid_index": 0, "centroid_k": k,
                         "population": 0.0, "lat": None, "lon": None, "dispersion_m": None})
            continue

        # Zero-population sub-units can't meaningfully belong to any cluster
        # and break weighted-sampling initialization if they leave fewer
        # than k *populated* points to seed clusters from (even when the
        # raw row count is >= k) -- drop them before clustering.
        nonzero = g["population"].to_numpy() > 0
        lon_v = g["lon"].to_numpy()[nonzero]
        lat_v = g["lat"].to_numpy()[nonzero]
        weights = g["population"].to_numpy()[nonzero]
        n_points = len(weights)

        lat0 = lat_v.mean()
        x_m, y_m = _project_to_meters(lat_v, lon_v, lat0)

        effective_k = min(k, n_points)
        if effective_k <= 1:
            labels = np.zeros(n_points, dtype=int)
        else:
            labels = _weighted_kmeans(np.column_stack([x_m, y_m]), weights, effective_k, seed=seed)

        for label in sorted(set(labels)):
            mask = labels == label
            w = weights[mask]
            w_sum = w.sum()
            if w_sum == 0:
                continue
            c_lon = float((lon_v[mask] * w).sum() / w_sum)
            c_lat = float((lat_v[mask] * w).sum() / w_sum)
            cx_m = (x_m[mask] * w).sum() / w_sum
            cy_m = (y_m[mask] * w).sum() / w_sum
            dist2 = (x_m[mask] - cx_m) ** 2 + (y_m[mask] - cy_m) ** 2
            dispersion_m = float(np.sqrt((w * dist2).sum() / w_sum))
            rows.append({**base, "centroid_index": int(label), "centroid_k": k,
                         "population": float(w_sum), "lat": c_lat, "lon": c_lon, "dispersion_m": dispersion_m})

    out = pd.DataFrame(rows).rename(columns={"GEOID_tract": "GEOID"})
    return out
