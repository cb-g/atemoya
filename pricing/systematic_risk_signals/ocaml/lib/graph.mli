(** Graph theory module for MST and eigenvector centrality.

    Implements:
    - Minimum Spanning Tree construction (Kruskal's algorithm)
    - Eigenvector centrality calculation
    - Adjacency matrix operations

    The MST represents the minimal connectivity structure capturing
    the most significant relationships between securities.
*)

open Types

(** Build list of edges from distance matrix *)
val edges_from_distances : float array array -> edge list

(** Construct MST using Kruskal's algorithm *)
val kruskal_mst : edge list -> int -> mst

(** Build adjacency matrix from MST *)
val mst_to_adjacency : mst -> float array array

(** Compute eigenvector centrality from adjacency matrix *)
val eigenvector_centrality : float array array -> centrality_result

(** Full pipeline: distance matrix -> MST -> centrality *)
val compute_graph_metrics : float array array -> mst * centrality_result
