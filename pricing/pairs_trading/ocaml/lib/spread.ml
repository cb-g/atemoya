(* Spread modeling and signal generation *)

open Types

(** Spread statistics **)

(* Calculate z-score of current spread value *)
let zscore ~spread ~mean ~std =
  if std > 0.0 then (spread -. mean) /. std
  else 0.0

(* Calculate half-life of mean reversion
   Using AR(1) model: S_t = ρ·S_{t-1} + ε
   Mean reversion requires |ρ| < 1

   Regression on differences: ΔS_t = α + φ·S_{t-1} + ε
   where φ = ρ - 1 (so φ < 0 for mean reversion)

   AR(1) coefficient: ρ = 1 + φ
   Discrete half-life: t_{1/2} = -ln(2) / ln(ρ) = -ln(2) / ln(1 + φ)

   Note: The continuous approximation -ln(2)/φ is only accurate for small |φ|.
   We use the exact discrete formula for better accuracy.
*)
let calculate_half_life spread_series =
  let n = Array.length spread_series in
  if n < 10 then None  (* Not enough data for reliable estimate *)
  else
    (* Calculate changes *)
    let delta_s = Array.init (n - 1) (fun i ->
      spread_series.(i + 1) -. spread_series.(i)
    ) in
    let s_lagged = Array.sub spread_series 0 (n - 1) in

    (* Regression: ΔS ~ S_{t-1} gives coefficient φ = ρ - 1 *)
    let (_, phi, _) = Cointegration.ols_regression ~x:s_lagged ~y:delta_s in

    (* Mean reversion requires φ < 0 (equivalently, ρ < 1) *)
    if phi >= 0.0 then
      None  (* No mean reversion - spread is non-stationary or explosive *)
    else if phi <= -1.0 then
      None  (* ρ ≤ 0: oscillatory/explosive, not mean-reverting *)
    else
      (* ρ = 1 + φ, where -1 < φ < 0 means 0 < ρ < 1 *)
      let rho = 1.0 +. phi in
      (* Half-life = -ln(2) / ln(ρ) *)
      let log_rho = log rho in
      if abs_float log_rho < 1e-10 then
        None  (* ρ ≈ 1: essentially random walk *)
      else
        let half_life = -. (log 2.0) /. log_rho in
        (* Validate: half-life should be positive and reasonable *)
        if half_life > 0.5 && half_life < 252.0 then
          Some half_life
        else
          None  (* Outside reasonable range for trading *)

(* Calculate comprehensive spread statistics *)
let calculate_spread_stats spread_series =
  let mean = Cointegration.mean spread_series in
  let std = Cointegration.std spread_series in
  let half_life_opt = calculate_half_life spread_series in
  (* Use default of 5.0 if half-life cannot be estimated *)
  let half_life = match half_life_opt with
    | Some hl -> hl
    | None -> 5.0
  in
  let current_spread = spread_series.(Array.length spread_series - 1) in
  let current_zscore = zscore ~spread:current_spread ~mean ~std in

  {
    mean;
    std;
    half_life;
    current_zscore;
  }

(** Signal generation **)

(* Generate trading signal based on z-score thresholds
   - Z > entry_threshold: SHORT spread (sell Y, buy X)
   - Z < -entry_threshold: LONG spread (buy Y, sell X)
   - |Z| < exit_threshold: EXIT
*)
let generate_signal ~zscore ~entry_threshold ~exit_threshold ~current_position =
  match current_position with
  | None ->
      (* No position - check entry *)
      if zscore > entry_threshold then Short
      else if zscore < -.entry_threshold then Long
      else Neutral
  | Some pos ->
      (* Have position - check exit *)
      (match pos.position_type with
       | Long ->
           (* Long position: exit if spread reverts (z-score near zero or crosses) *)
           if zscore > exit_threshold then Exit
           else Neutral
       | Short ->
           (* Short position: exit if spread reverts *)
           if zscore < -.exit_threshold then Exit
           else Neutral
       | _ -> Neutral)

(* Generate signals for entire series *)
let generate_signals ~spread_series ~entry_threshold ~exit_threshold:_ =
  let n = Array.length spread_series in
  let mean = Cointegration.mean spread_series in
  let std = Cointegration.std spread_series in

  Array.init n (fun i ->
    let z = zscore ~spread:spread_series.(i) ~mean ~std in
    let signal =
      if z > entry_threshold then Short
      else if z < -.entry_threshold then Long
      else Neutral
    in
    {
      timestamp = float_of_int i;
      signal;
      zscore = z;
      spread_value = spread_series.(i);
    }
  )

(** Position management **)

(* Calculate position sizes based on hedge ratio and capital *)
let position_sizes ~hedge_ratio ~capital ~price1 ~price2 =
  (* For a $1 position in Y, need $β in X
     Allocate capital: shares_y * price_y + shares_x * price_x = capital
     Constraint: shares_x = -β * shares_y (short X when long Y)
  *)
  let shares_y = capital /. (price2 +. hedge_ratio *. price1) in
  let shares_x = -.hedge_ratio *. shares_y in
  (shares_y, shares_x)

(* Create position *)
let create_position ~entry_time ~entry_zscore ~entry_spread ~position_type ~hedge_ratio ~capital ~price1 ~price2 =
  let (shares_y, shares_x) =
    match position_type with
    | Long ->
        (* Long spread: buy Y, sell X *)
        position_sizes ~hedge_ratio ~capital ~price1 ~price2
    | Short ->
        (* Short spread: sell Y, buy X *)
        let (sy, sx) = position_sizes ~hedge_ratio ~capital ~price1 ~price2 in
        (-.sy, -.sx)
    | _ -> (0.0, 0.0)
  in

  {
    entry_time;
    entry_zscore;
    entry_spread;
    position_type;
    shares_y;
    shares_x;
  }

(* Calculate position P&L *)
let position_pnl ~position ~current_price1 ~current_price2 ~entry_price1 ~entry_price2 =
  let pnl_y = position.shares_y *. (current_price2 -. entry_price2) in
  let pnl_x = position.shares_x *. (current_price1 -. entry_price1) in
  pnl_y +. pnl_x

(** Dynamic half-life monitoring **)

(* Compute half-life over a rolling window
   Returns one value per observation from index `window` to end *)
let rolling_half_life ~spread_series ~window =
  let n = Array.length spread_series in
  if n < window || window < 10 then [||]
  else
    let num_windows = n - window + 1 in
    Array.init num_windows (fun i ->
      let sub = Array.sub spread_series i window in
      calculate_half_life sub
    )

(* Compare current rolling half-life to baseline (full-sample)
   ratio > 2.0 means mean reversion is weakening *)
let monitor_half_life ~spread_series ~window =
  match calculate_half_life spread_series with
  | None -> None
  | Some baseline ->
    let rolling = rolling_half_life ~spread_series ~window in
    let len = Array.length rolling in
    if len = 0 then None
    else
      match rolling.(len - 1) with
      | None -> None
      | Some current ->
        let ratio = current /. baseline in
        Some {
          baseline_half_life = baseline;
          current_half_life = current;
          ratio;
          is_expanding = ratio > 2.0;
        }
