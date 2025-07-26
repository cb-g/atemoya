val read_adjusted_closes : string -> Lacaml.D.mat

val compute_log_returns : Lacaml.D.mat -> Lacaml.D.mat

val mean_return_vector : Lacaml.D.mat -> Lacaml.D.vec

val covariance_matrix : Lacaml.D.mat -> Lacaml.D.mat

val efficient_frontier :
  Lacaml.D.vec -> Lacaml.D.mat -> int -> (float * float * Lacaml.D.vec) list

val write_frontier_to_csv :
  string -> (float * float * Lacaml.D.vec) list -> unit

val write_example_portfolios_to_csv :
  string -> string list -> (string * float * float * Lacaml.D.vec) list -> unit
