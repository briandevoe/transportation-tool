"""score(): the scoring stage of the accessibility pipeline -- turns a
travel-time/distance matrix (from compute.py's compute_matrix()) into an
accessibility metric. See docs/accessibility_models.md for which metrics
are already proven (as archived one-off scripts) vs. still to-do.

See docs/function_design.md. Only metric="nearest" is implemented so far;
the rest raise NotImplementedError until ported/built.
"""
from .analysis_schema import validate_metrics


def score(matrix, population, dest_type, algorithm, metric="nearest", **params):
    """metric options (see docs/accessibility_models.md for the full
    writeup of each):
      - "nearest": nearest destination's value per origin. Implemented.
      - "k_nearest" / "within_threshold" / "gravity" / "2sfca" / "pwd":
        not implemented yet.

    `population` must be the same origins DataFrame passed to
    compute_matrix() (its index is what matrix's origin_id refers to).
    Returns a metrics DataFrame validated against
    engine/analysis_schema.py's spine, plus one metric-value column named
    for its unit (e.g. nearest_time_min).
    """
    if metric != "nearest":
        raise NotImplementedError(f"metric={metric!r} not implemented yet -- see docs/accessibility_models.md")

    unit = matrix["unit"].iloc[0] if len(matrix) else "value"
    unit_word = {"min": "time_min", "mi": "distance_mi"}.get(unit, unit)
    col_name = f"nearest_{unit_word}"

    nearest = matrix.groupby("origin_id")["value"].min()
    out = population.copy()
    out[col_name] = out.index.map(nearest)
    out["dest_type"] = dest_type
    out["algorithm"] = algorithm
    return validate_metrics(out)
