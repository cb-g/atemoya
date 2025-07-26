type input = {
  short_name : string;
  currency : string;
  rfr : float;
  beta_u : float;
  erp : float;
  ebit : float;
  ni : float;
  capx : float;
  d : float;
  ca : float;
  cl : float;
  prev_ca : float;
  prev_cl : float;
  tgr : float;
  h : int;
  ctr : float;
  ic : float;
  dp : float;
  so : float;
  mve : float;
  mvb : float;
  tdr : float;
  time_series : (string * float list) list;
  growth_clamp_upper : float;
  growth_clamp_lower : float;
}

val load_inputs : string -> (string * input) list

val simulate_fcfe : input -> float list
val simulate_fcff : input -> float list

val run_monte_carlo :
  input ->
  n:int ->
  fcfe:bool ->
  float list  (* list of valuations *)
