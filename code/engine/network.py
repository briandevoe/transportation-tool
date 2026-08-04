"""The Network class: wraps a routable graph (igraph) plus fast lat/lon ->
node snapping (cKDTree), so every accessibility computation shares one built
graph instead of each script rebuilding its own -- the duplication this
whole engine package exists to fix (the archived
02_compute_travel_time_metrics.py and 05_build_simple_model.py each
independently rebuilt both; this is that same proven logic, generalized).

See docs/function_design.md.
"""
import numpy as np
import igraph as ig
from scipy.spatial import cKDTree


class Network:
    """Wraps one state/source's edges + nodes tables (the schema in
    lib/network_schema.py) into a routable directed graph, built once in
    __init__ and reused for every snap()/matrix() call against it. Returned
    by engine.prep.get_network(), not constructed directly in normal use."""

    def __init__(self, edges, nodes):
        self.nodes = nodes.reset_index(drop=True)
        node_index = {nid: i for i, nid in enumerate(self.nodes["node_id"])}
        u_idx = edges["from_node"].map(node_index)
        v_idx = edges["to_node"].map(node_index)
        valid = u_idx.notna() & v_idx.notna()
        edges = edges[valid]
        u_idx, v_idx = u_idx[valid].astype(int), v_idx[valid].astype(int)
        travel_time_min = (edges["length_m"].astype(float) / 1000) / edges["speed_kph"].astype(float) * 60

        self.graph = ig.Graph(n=len(self.nodes), edges=list(zip(u_idx, v_idx)), directed=True)
        self.graph.es["weight"] = travel_time_min.values

        # Equirectangular-approximate scaling for snapping, same approach the
        # archived analysis scripts used -- fine at state scale, not meant for
        # anything near the poles.
        self._lon_scale = np.cos(np.radians(self.nodes["lat"].mean()))
        self._tree = cKDTree(np.column_stack([
            self.nodes["lon"].values * self._lon_scale, self.nodes["lat"].values,
        ]))

    def snap(self, lats, lons):
        """Snap lat/lon points to their nearest network node. Returns graph
        vertex indices (same length as lats/lons)."""
        _, idx = self._tree.query(
            np.column_stack([np.asarray(lons) * self._lon_scale, np.asarray(lats)]), k=1,
        )
        return np.atleast_1d(idx)

    def matrix(self, origin_nodes, dest_nodes):
        """Multi-source Dijkstra travel time (minutes) between every given
        origin node and every given destination node. Returns an
        (len(origin_nodes), len(dest_nodes)) ndarray; unreachable pairs are
        NaN, not inf. Does not deduplicate repeated node indices -- fine at
        the scale this has been tested at (a few thousand origins, a few
        hundred destinations); revisit if that stops being true."""
        dist_rows = self.graph.distances(
            source=list(origin_nodes), target=list(dest_nodes), weights="weight",
        )
        dist_matrix = np.array(dist_rows, dtype=float)
        dist_matrix[np.isinf(dist_matrix)] = np.nan
        return dist_matrix
