"""compute_matrix(): the routing stage of the accessibility pipeline --
turns origins + destinations (+ a Network, for network-based algorithms)
into a travel-time/distance matrix. Deliberately separate from
scoring.py's score() so a new accessibility model (see
docs/accessibility_models.md) never needs new routing code, only a new
scoring function.

See docs/function_design.md. Only algorithm="dijkstra" is implemented
(ported from the archived 02_compute_travel_time_metrics.py); euclidean
raises NotImplementedError until someone needs it.
"""
import numpy as np
import pandas as pd


def compute_matrix(origins, destinations, network=None, algorithm="dijkstra"):
    """Returns a long DataFrame: origin_id, dest_id, value, unit.
    origin_id is origins' row position (its DataFrame index after
    reset_index); dest_id is destinations['dest_id'].

    `algorithm` is a dispatcher, not a strict drop-in interface:
      - "dijkstra": network-routed travel time (minutes), requires `network`.
      - "euclidean": straight-line/haversine distance, would ignore
        `network` entirely -- not implemented yet.
    """
    if algorithm == "dijkstra":
        if network is None:
            raise ValueError("algorithm='dijkstra' requires a network")
        origin_nodes = network.snap(origins["lat"].values, origins["lon"].values)
        dest_nodes = network.snap(destinations["lat"].values, destinations["lon"].values)
        dist = network.matrix(origin_nodes, dest_nodes)  # (n_origins, n_dests), minutes

        n_o, n_d = dist.shape
        return pd.DataFrame({
            "origin_id": np.repeat(origins.index.values, n_d),
            "dest_id": np.tile(destinations["dest_id"].values, n_o),
            "value": dist.flatten(),
            "unit": "min",
        })
    elif algorithm == "euclidean":
        raise NotImplementedError("euclidean/haversine routing not ported yet -- see archived 01_compute_distance_metrics.py")
    else:
        raise ValueError(f"Unknown algorithm: {algorithm!r}")
