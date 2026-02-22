(** Graph theory module for MST and eigenvector centrality. *)

open Types

(* Union-Find data structure for Kruskal's algorithm *)
module UnionFind = struct
  type t = {
    parent : int array;
    rank : int array;
  }

  let create n = {
    parent = Array.init n (fun i -> i);
    rank = Array.make n 0;
  }

  let rec find uf x =
    if uf.parent.(x) <> x then
      uf.parent.(x) <- find uf uf.parent.(x);
    uf.parent.(x)

  let union uf x y =
    let px = find uf x in
    let py = find uf y in
    if px = py then false
    else begin
      if uf.rank.(px) < uf.rank.(py) then
        uf.parent.(px) <- py
      else if uf.rank.(px) > uf.rank.(py) then
        uf.parent.(py) <- px
      else begin
        uf.parent.(py) <- px;
        uf.rank.(px) <- uf.rank.(px) + 1
      end;
      true
    end
end

let edges_from_distances (dist : float array array) : edge list =
  let n = Array.length dist in
  let edges = ref [] in
  for i = 0 to n - 1 do
    for j = i + 1 to n - 1 do
      edges := { from_idx = i; to_idx = j; weight = dist.(i).(j) } :: !edges
    done
  done;
  !edges

let kruskal_mst (edges : edge list) (n_vertices : int) : mst =
  (* Sort edges by weight *)
  let sorted_edges = List.sort (fun e1 e2 -> compare e1.weight e2.weight) edges in

  let uf = UnionFind.create n_vertices in
  let mst_edges = ref [] in
  let total_weight = ref 0.0 in

  List.iter (fun edge ->
    if List.length !mst_edges < n_vertices - 1 then
      if UnionFind.union uf edge.from_idx edge.to_idx then begin
        mst_edges := edge :: !mst_edges;
        total_weight := !total_weight +. edge.weight
      end
  ) sorted_edges;

  { edges = !mst_edges; n_vertices; total_weight = !total_weight }

let mst_to_adjacency (mst : mst) : float array array =
  let n = mst.n_vertices in
  let adj = Array.make_matrix n n 0.0 in

  List.iter (fun edge ->
    (* Use 1/weight as edge strength (inverse of distance) *)
    let strength = if edge.weight > 1e-10 then 1.0 /. edge.weight else 1.0 in
    adj.(edge.from_idx).(edge.to_idx) <- strength;
    adj.(edge.to_idx).(edge.from_idx) <- strength
  ) mst.edges;

  adj

(** Power iteration to find principal eigenvector *)
let power_iteration_vec (adj : float array array) (max_iter : int) (tol : float) : float array =
  let n = Array.length adj in
  let vec = Array.make n (1.0 /. sqrt (float_of_int n)) in
  let new_vec = Array.make n 0.0 in

  for _ = 1 to max_iter do
    (* Multiply: new_vec = adj * vec *)
    for i = 0 to n - 1 do
      new_vec.(i) <- 0.0;
      for j = 0 to n - 1 do
        new_vec.(i) <- new_vec.(i) +. adj.(i).(j) *. vec.(j)
      done
    done;

    (* Normalize *)
    let norm = sqrt (Array.fold_left (fun acc x -> acc +. x *. x) 0.0 new_vec) in
    if norm > tol then
      for i = 0 to n - 1 do
        new_vec.(i) <- new_vec.(i) /. norm
      done;

    (* Check convergence *)
    let diff = ref 0.0 in
    for i = 0 to n - 1 do
      diff := !diff +. (new_vec.(i) -. vec.(i)) ** 2.0
    done;

    (* Update vec *)
    for i = 0 to n - 1 do
      vec.(i) <- new_vec.(i)
    done;

    if sqrt !diff < tol then ()
  done;

  (* Ensure non-negative (eigenvector centrality should be positive) *)
  Array.map abs_float vec

let eigenvector_centrality (adj : float array array) : centrality_result =
  let centralities = power_iteration_vec adj 100 1e-8 in
  let n = Array.length centralities in

  (* Compute mean *)
  let mean_centrality =
    Array.fold_left ( +. ) 0.0 centralities /. float_of_int n
  in

  (* Compute standard deviation *)
  let sum_sq = Array.fold_left (fun acc x ->
    acc +. (x -. mean_centrality) ** 2.0
  ) 0.0 centralities in
  let std_centrality =
    if n > 1 then sqrt (sum_sq /. float_of_int (n - 1))
    else 0.0
  in

  { centralities; mean_centrality; std_centrality }

let compute_graph_metrics (dist : float array array) : mst * centrality_result =
  let n = Array.length dist in
  let edges = edges_from_distances dist in
  let mst = kruskal_mst edges n in
  let adj = mst_to_adjacency mst in
  let centrality = eigenvector_centrality adj in
  (mst, centrality)
