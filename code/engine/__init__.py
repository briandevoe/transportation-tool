"""Transportation Accessibility Engine -- the function suite that turns
Layers 1-4 into accessibility metrics, replacing the archived one-off
analysis scripts (archive/transportation-tool-analysis-visualization-
scripts/). Full design writeup: docs/function_design.md.

Status: a first real, working vertical slice exists -- get_geography,
get_population, get_network, get_destinations, Network, compute_matrix
(algorithm="dijkstra" only), and score (metric="nearest" only), enough to
run tests/test_smoke_ma_hospitals.py end-to-end. Other geography types,
race schemes, destination types, algorithms, and metrics raise
NotImplementedError until someone actually needs them -- see each module's
docstring for exactly what's covered.

Layout:
  prep.py             get_geography(), get_population(), get_network(),
                       get_destinations() -- load already-processed layer
                       output into memory
  network.py          the Network class -- one built graph + snapping,
                       shared across every routing call against it
  compute.py           compute_matrix() -- the routing stage
  scoring.py           score() -- the scoring stage (metric dispatch)
  analysis_schema.py   the metrics-output schema (small fixed spine,
                       flexible metric columns)
  reference_data.py    attach_reference_attributes() -- discovers and
                       joins whatever Layer 5 reference sources exist
"""

from .analysis_schema import validate_metrics
from .compute import compute_matrix
from .network import Network
from .prep import get_destinations, get_geography, get_network, get_population
from .reference_data import attach_reference_attributes
from .scoring import score

__all__ = [
    "get_geography", "get_population", "get_network", "get_destinations",
    "Network", "compute_matrix", "score",
    "validate_metrics", "attach_reference_attributes",
]
