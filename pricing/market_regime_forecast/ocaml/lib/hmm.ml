(** Hidden Markov Model for Regime Detection

    3-state HMM with Gaussian emissions:
    - State 0: Bull (positive mean return)
    - State 1: Bear (negative mean return)
    - State 2: Sideways (near-zero mean return)

    Estimation via Baum-Welch (EM) algorithm
    Decoding via Viterbi algorithm *)

open Types

(** Small constant for numerical stability *)
let eps = 1e-300
let log_eps = -690.7755  (* log(1e-300) *)

(** Standard normal PDF *)
let norm_pdf ~mu ~sigma x =
  let z = (x -. mu) /. sigma in
  exp (-0.5 *. z *. z) /. (sigma *. sqrt (2.0 *. Float.pi))

(** Log of normal PDF (more stable) *)
let log_norm_pdf ~mu ~sigma x =
  let z = (x -. mu) /. sigma in
  -0.5 *. z *. z -. log sigma -. 0.5 *. log (2.0 *. Float.pi)

(** Initialize HMM parameters with reasonable defaults for market regimes *)
let init_params ~returns ~n_states =
  let n = Array.length returns in

  (* Estimate sample statistics *)
  let mean =
    Array.fold_left (+.) 0.0 returns /. float_of_int n
  in
  let var =
    Array.fold_left (fun acc r ->
      let d = r -. mean in acc +. d *. d
    ) 0.0 returns /. float_of_int n
  in
  let std = sqrt var in

  (* Initialize emission parameters *)
  let emission_means = Array.make n_states 0.0 in
  let emission_vars = Array.make n_states var in

  if n_states = 3 then begin
    (* Bull: positive returns *)
    emission_means.(0) <- mean +. std;
    emission_vars.(0) <- var *. 0.8;
    (* Bear: negative returns *)
    emission_means.(1) <- mean -. std;
    emission_vars.(1) <- var *. 1.5;  (* Higher vol in bear *)
    (* Sideways: near mean *)
    emission_means.(2) <- mean;
    emission_vars.(2) <- var *. 0.5;  (* Lower vol sideways *)
  end else begin
    (* Generic initialization for other n_states *)
    for i = 0 to n_states - 1 do
      let offset = float_of_int (i - n_states / 2) *. std in
      emission_means.(i) <- mean +. offset;
      emission_vars.(i) <- var
    done
  end;

  (* Initialize transition matrix with high persistence *)
  let transition_matrix = Array.make_matrix n_states n_states 0.0 in
  for i = 0 to n_states - 1 do
    for j = 0 to n_states - 1 do
      if i = j then
        transition_matrix.(i).(j) <- 0.90  (* Stay in same state *)
      else
        transition_matrix.(i).(j) <- 0.10 /. float_of_int (n_states - 1)
    done
  done;

  (* Uniform initial distribution *)
  let initial_probs = Array.make n_states (1.0 /. float_of_int n_states) in

  { n_states; transition_matrix; emission_means; emission_vars; initial_probs }

(** Forward algorithm - compute P(observations, state_t = i)
    Returns (alpha, scaling_factors) where alpha is scaled *)
let forward ~params ~returns =
  let n = Array.length returns in
  let k = params.n_states in

  let alpha = Array.make_matrix n k 0.0 in
  let scale = Array.make n 0.0 in

  (* Initialize t=0 *)
  for i = 0 to k - 1 do
    let sigma = sqrt params.emission_vars.(i) in
    alpha.(0).(i) <- params.initial_probs.(i) *.
      norm_pdf ~mu:params.emission_means.(i) ~sigma returns.(0)
  done;

  (* Scale to prevent underflow *)
  scale.(0) <- Array.fold_left (+.) 0.0 alpha.(0);
  if scale.(0) > eps then
    for i = 0 to k - 1 do
      alpha.(0).(i) <- alpha.(0).(i) /. scale.(0)
    done;

  (* Forward recursion *)
  for t = 1 to n - 1 do
    for j = 0 to k - 1 do
      let sum = ref 0.0 in
      for i = 0 to k - 1 do
        sum := !sum +. alpha.(t - 1).(i) *. params.transition_matrix.(i).(j)
      done;
      let sigma = sqrt params.emission_vars.(j) in
      alpha.(t).(j) <- !sum *.
        norm_pdf ~mu:params.emission_means.(j) ~sigma returns.(t)
    done;

    (* Scale *)
    scale.(t) <- Array.fold_left (+.) 0.0 alpha.(t);
    if scale.(t) > eps then
      for i = 0 to k - 1 do
        alpha.(t).(i) <- alpha.(t).(i) /. scale.(t)
      done
  done;

  (alpha, scale)

(** Backward algorithm - compute P(observations_{t+1:T} | state_t = i) *)
let backward ~params ~returns ~scale =
  let n = Array.length returns in
  let k = params.n_states in

  let beta = Array.make_matrix n k 0.0 in

  (* Initialize t=T-1 *)
  for i = 0 to k - 1 do
    beta.(n - 1).(i) <- 1.0
  done;

  (* Backward recursion *)
  for t = n - 2 downto 0 do
    for i = 0 to k - 1 do
      let sum = ref 0.0 in
      for j = 0 to k - 1 do
        let sigma = sqrt params.emission_vars.(j) in
        let emit = norm_pdf ~mu:params.emission_means.(j) ~sigma returns.(t + 1) in
        sum := !sum +. params.transition_matrix.(i).(j) *. emit *. beta.(t + 1).(j)
      done;
      beta.(t).(i) <- !sum
    done;

    (* Scale with same factor as forward *)
    if scale.(t + 1) > eps then
      for i = 0 to k - 1 do
        beta.(t).(i) <- beta.(t).(i) /. scale.(t + 1)
      done
  done;

  beta

(** Compute gamma (state probabilities) and xi (transition probabilities) *)
let compute_gamma_xi ~params ~returns ~alpha ~beta ~scale:_ =
  let n = Array.length returns in
  let k = params.n_states in

  (* gamma(t,i) = P(state_t = i | observations) *)
  let gamma = Array.make_matrix n k 0.0 in
  for t = 0 to n - 1 do
    let sum = ref 0.0 in
    for i = 0 to k - 1 do
      gamma.(t).(i) <- alpha.(t).(i) *. beta.(t).(i);
      sum := !sum +. gamma.(t).(i)
    done;
    if !sum > eps then
      for i = 0 to k - 1 do
        gamma.(t).(i) <- gamma.(t).(i) /. !sum
      done
  done;

  (* xi(t,i,j) = P(state_t = i, state_{t+1} = j | observations) *)
  let xi = Array.init (n - 1) (fun _ -> Array.make_matrix k k 0.0) in
  for t = 0 to n - 2 do
    let sum = ref 0.0 in
    for i = 0 to k - 1 do
      for j = 0 to k - 1 do
        let sigma = sqrt params.emission_vars.(j) in
        let emit = norm_pdf ~mu:params.emission_means.(j) ~sigma returns.(t + 1) in
        xi.(t).(i).(j) <- alpha.(t).(i) *. params.transition_matrix.(i).(j) *.
          emit *. beta.(t + 1).(j);
        sum := !sum +. xi.(t).(i).(j)
      done
    done;
    if !sum > eps then
      for i = 0 to k - 1 do
        for j = 0 to k - 1 do
          xi.(t).(i).(j) <- xi.(t).(i).(j) /. !sum
        done
      done
  done;

  (gamma, xi)

(** Baum-Welch (EM) algorithm for parameter estimation *)
let baum_welch ~returns ~n_states ~max_iter ~tolerance =
  let n = Array.length returns in
  let params = ref (init_params ~returns ~n_states) in

  let prev_ll = ref neg_infinity in
  let converged = ref false in
  let iter = ref 0 in

  while !iter < max_iter && not !converged do
    incr iter;

    (* E-step: compute forward/backward and sufficient statistics *)
    let (alpha, scale) = forward ~params:!params ~returns in
    let beta = backward ~params:!params ~returns ~scale in
    let (gamma, xi) = compute_gamma_xi ~params:!params ~returns ~alpha ~beta ~scale in

    (* Compute log-likelihood *)
    let log_likelihood =
      Array.fold_left (fun acc s ->
        if s > eps then acc +. log s else acc
      ) 0.0 scale
    in

    (* Check convergence *)
    if log_likelihood -. !prev_ll < tolerance then
      converged := true
    else begin
      prev_ll := log_likelihood;

      (* M-step: update parameters *)
      let k = !params.n_states in

      (* Update initial probabilities *)
      let new_initial = Array.init k (fun i -> gamma.(0).(i)) in

      (* Update transition matrix *)
      let new_trans = Array.make_matrix k k 0.0 in
      for i = 0 to k - 1 do
        let denom = ref 0.0 in
        for t = 0 to n - 2 do
          denom := !denom +. gamma.(t).(i)
        done;
        for j = 0 to k - 1 do
          let numer = ref 0.0 in
          for t = 0 to n - 2 do
            numer := !numer +. xi.(t).(i).(j)
          done;
          new_trans.(i).(j) <-
            if !denom > eps then !numer /. !denom else 1.0 /. float_of_int k
        done
      done;

      (* Update emission means *)
      let new_means = Array.make k 0.0 in
      for i = 0 to k - 1 do
        let numer = ref 0.0 in
        let denom = ref 0.0 in
        for t = 0 to n - 1 do
          numer := !numer +. gamma.(t).(i) *. returns.(t);
          denom := !denom +. gamma.(t).(i)
        done;
        new_means.(i) <- if !denom > eps then !numer /. !denom else 0.0
      done;

      (* Update emission variances *)
      let new_vars = Array.make k 0.0 in
      for i = 0 to k - 1 do
        let numer = ref 0.0 in
        let denom = ref 0.0 in
        for t = 0 to n - 1 do
          let d = returns.(t) -. new_means.(i) in
          numer := !numer +. gamma.(t).(i) *. d *. d;
          denom := !denom +. gamma.(t).(i)
        done;
        (* Minimum variance to prevent degenerate solutions *)
        new_vars.(i) <- max 1e-8 (if !denom > eps then !numer /. !denom else 1e-4)
      done;

      params := {
        n_states = k;
        transition_matrix = new_trans;
        emission_means = new_means;
        emission_vars = new_vars;
        initial_probs = new_initial;
      }
    end
  done;

  (* Final log-likelihood *)
  let (_, scale) = forward ~params:!params ~returns in
  let log_likelihood =
    Array.fold_left (fun acc s ->
      if s > eps then acc +. log s else acc
    ) 0.0 scale
  in

  { params = !params; log_likelihood; n_iterations = !iter; converged = !converged }

(** Relabel HMM states so that:
    - State 0 (Bull): highest mean return
    - State 1 (Bear): lowest mean return
    - State 2 (Sideways): middle mean return *)
let relabel_states params =
  let k = params.n_states in
  if k <> 3 then params  (* Only relabel 3-state models *)
  else
    (* Create index-mean pairs and sort by mean *)
    let indexed_means = Array.mapi (fun i m -> (i, m)) params.emission_means in
    Array.sort (fun (_, m1) (_, m2) -> compare m2 m1) indexed_means;  (* Descending *)

    (* indexed_means.(0) = highest mean (Bull)
       indexed_means.(1) = middle mean (Sideways)
       indexed_means.(2) = lowest mean (Bear) *)
    let old_to_new = Array.make k 0 in
    old_to_new.(fst indexed_means.(0)) <- 0;  (* Highest -> Bull *)
    old_to_new.(fst indexed_means.(2)) <- 1;  (* Lowest -> Bear *)
    old_to_new.(fst indexed_means.(1)) <- 2;  (* Middle -> Sideways *)

    (* Reorder emission parameters *)
    let new_means = Array.make k 0.0 in
    let new_vars = Array.make k 0.0 in
    let new_initial = Array.make k 0.0 in
    for old_i = 0 to k - 1 do
      let new_i = old_to_new.(old_i) in
      new_means.(new_i) <- params.emission_means.(old_i);
      new_vars.(new_i) <- params.emission_vars.(old_i);
      new_initial.(new_i) <- params.initial_probs.(old_i)
    done;

    (* Reorder transition matrix *)
    let new_trans = Array.make_matrix k k 0.0 in
    for old_i = 0 to k - 1 do
      for old_j = 0 to k - 1 do
        let new_i = old_to_new.(old_i) in
        let new_j = old_to_new.(old_j) in
        new_trans.(new_i).(new_j) <- params.transition_matrix.(old_i).(old_j)
      done
    done;

    {
      n_states = k;
      transition_matrix = new_trans;
      emission_means = new_means;
      emission_vars = new_vars;
      initial_probs = new_initial;
    }

(** Fit HMM to returns *)
let fit ~returns ~config =
  let n = Array.length returns in
  if n < 100 then failwith "Need at least 100 observations for HMM";

  (* Use only recent data for fitting to capture current regime *)
  let lookback = min n config.Types.hmm_lookback_days in
  let recent_returns = Array.sub returns (n - lookback) lookback in

  let result = baum_welch
    ~returns:recent_returns
    ~n_states:3
    ~max_iter:config.hmm_max_iter
    ~tolerance:config.hmm_tolerance
  in

  (* Relabel states so Bull=highest mean, Bear=lowest, Sideways=middle *)
  let relabeled_params = relabel_states result.params in
  { result with params = relabeled_params }

(** Viterbi algorithm - find most likely state sequence *)
let viterbi ~params ~returns =
  let n = Array.length returns in
  let k = params.n_states in

  (* Log probabilities for numerical stability *)
  let log_delta = Array.make_matrix n k neg_infinity in
  let psi = Array.make_matrix n k 0 in

  (* Initialize *)
  for i = 0 to k - 1 do
    let sigma = sqrt params.emission_vars.(i) in
    let log_emit = log_norm_pdf ~mu:params.emission_means.(i) ~sigma returns.(0) in
    let log_init =
      if params.initial_probs.(i) > eps then log params.initial_probs.(i)
      else log_eps
    in
    log_delta.(0).(i) <- log_init +. log_emit
  done;

  (* Recursion *)
  for t = 1 to n - 1 do
    for j = 0 to k - 1 do
      let sigma = sqrt params.emission_vars.(j) in
      let log_emit = log_norm_pdf ~mu:params.emission_means.(j) ~sigma returns.(t) in

      let best_i = ref 0 in
      let best_val = ref neg_infinity in
      for i = 0 to k - 1 do
        let log_trans =
          if params.transition_matrix.(i).(j) > eps
          then log params.transition_matrix.(i).(j)
          else log_eps
        in
        let val_i = log_delta.(t - 1).(i) +. log_trans in
        if val_i > !best_val then begin
          best_val := val_i;
          best_i := i
        end
      done;

      log_delta.(t).(j) <- !best_val +. log_emit;
      psi.(t).(j) <- !best_i
    done
  done;

  (* Backtrack *)
  let states = Array.make n 0 in

  (* Find best final state *)
  let best_final = ref 0 in
  for i = 1 to k - 1 do
    if log_delta.(n - 1).(i) > log_delta.(n - 1).(!best_final) then
      best_final := i
  done;
  states.(n - 1) <- !best_final;

  (* Backtrack *)
  for t = n - 2 downto 0 do
    states.(t) <- psi.(t + 1).(states.(t + 1))
  done;

  states

(** Get current state probabilities using forward algorithm *)
let current_state_probs ~params ~returns =
  let (alpha, _) = forward ~params ~returns in
  let n = Array.length returns in
  let k = params.n_states in

  let probs = Array.copy alpha.(n - 1) in
  let sum = Array.fold_left (+.) 0.0 probs in
  if sum > eps then
    for i = 0 to k - 1 do
      probs.(i) <- probs.(i) /. sum
    done;

  probs

(** Predict next state probabilities *)
let next_state_probs ~params ~current_probs =
  let k = params.n_states in
  let next = Array.make k 0.0 in

  for j = 0 to k - 1 do
    for i = 0 to k - 1 do
      next.(j) <- next.(j) +. current_probs.(i) *. params.transition_matrix.(i).(j)
    done
  done;

  next

(** Calculate regime persistence (expected days in current regime) *)
let regime_persistence ~params ~state =
  let p_stay = params.transition_matrix.(state).(state) in
  if p_stay < 1.0 then
    1.0 /. (1.0 -. p_stay)
  else
    infinity

(** Count consecutive days in current regime *)
let regime_age ~states =
  let n = Array.length states in
  if n = 0 then 0
  else
    let current = states.(n - 1) in
    let age = ref 1 in
    for t = n - 2 downto 0 do
      if states.(t) = current then incr age
      else age := n  (* Break *)
    done;
    min !age n
