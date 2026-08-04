"""Smoke test / worked example: exercises the real (non-stub) slice of
code/engine -- get_population, get_network, get_destinations,
compute_matrix, score, attach_reference_attributes -- end-to-end against
genuine Massachusetts data already on disk, and produces two concrete
artifacts as proof it actually works, not just that it imports:

  outputs/smoke_test/ma_hospital_access_stats.csv   nearest-hospital travel
                                                     time by race/ethnicity
  outputs/smoke_test/ma_hospital_access_map.png     tract choropleth of the
                                                     same metric

Run directly for the full exercise + artifacts:
    python tests/test_smoke_ma_hospitals.py
Or via pytest for just the sanity assertions (no plotting dependency):
    pytest tests/test_smoke_ma_hospitals.py

This is the first test in the repo. Map uses a single-hue sequential
colormap (viridis) since travel time is a magnitude measure, not identity --
per the dataviz skill's color-by-job rule.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "code"))
from engine import (
    attach_reference_attributes, compute_matrix, get_destinations,
    get_geography, get_network, get_population, score,
)

REPO_ROOT = Path(__file__).parent.parent
OUT_DIR = REPO_ROOT / "outputs" / "smoke_test"


def test_smoke_ma_hospitals():
    """Real exercise of the engine's vertical slice: nearest-hospital travel
    time for Massachusetts, by race/ethnicity. Returns the metrics table so
    __main__ below can reuse it for stats/plotting without recomputing."""
    population = get_population(state_fips="25")
    network = get_network(state_fips="25")
    hospitals = get_destinations(dest_type="hospital", state_fips="25")

    assert len(population) > 0, "no MA population rows loaded"
    assert len(hospitals) > 0, "no MA hospitals loaded"

    matrix = compute_matrix(population, hospitals, network=network, algorithm="dijkstra")
    metrics = score(matrix, population, dest_type="hospital", algorithm="dijkstra", metric="nearest")
    metrics = attach_reference_attributes(metrics)

    assert "nearest_time_min" in metrics.columns
    assert metrics["nearest_time_min"].notna().any(), "every origin unreachable -- routing is broken"
    assert (metrics["nearest_time_min"].dropna() >= 0).all(), "negative travel time -- routing is broken"

    return metrics


if __name__ == "__main__":
    metrics = test_smoke_ma_hospitals()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # --- Stats ---
    stats = metrics.groupby("race_ethnicity")["nearest_time_min"].agg(["mean", "median", "count"]).round(2)
    print("\nNearest hospital travel time (minutes) by race/ethnicity:")
    print(stats)
    stats.to_csv(OUT_DIR / "ma_hospital_access_stats.csv")
    print(f"Wrote {OUT_DIR / 'ma_hospital_access_stats.csv'}")

    coi_rows = metrics.dropna(subset=["coi_level_nat"])
    if len(coi_rows):
        print("\nMean nearest hospital time by COI level:")
        print(coi_rows.groupby("coi_level_nat")["nearest_time_min"].mean().round(2))

    # --- Map ---
    import geopandas as gpd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    tracts = get_geography(state_fips="25", geography_type="tract")
    hospitals = get_destinations(dest_type="hospital", state_fips="25")
    tract_avg = (
        metrics[metrics["race_ethnicity"] == "total"]
        .groupby("GEOID")["nearest_time_min"].mean()
    )
    tracts = tracts.merge(tract_avg.rename("nearest_time_min"), on="GEOID", how="left")

    fig, ax = plt.subplots(figsize=(8, 8))
    tracts.plot(
        column="nearest_time_min", cmap="viridis", legend=True, ax=ax,
        missing_kwds={"color": "lightgrey", "label": "No data"},
        legend_kwds={"label": "Nearest hospital, minutes (network travel time)"},
    )
    ax.scatter(hospitals["lon"], hospitals["lat"], c="red", s=10, marker="+", label="Hospitals")
    ax.set_title("Massachusetts: Nearest Hospital Travel Time by Tract")
    ax.set_axis_off()
    ax.legend(loc="lower right")
    fig.tight_layout()
    map_path = OUT_DIR / "ma_hospital_access_map.png"
    fig.savefig(map_path, dpi=150)
    print(f"Wrote {map_path}")
