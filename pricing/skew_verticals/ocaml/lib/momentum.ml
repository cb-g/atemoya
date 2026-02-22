(** Momentum Indicators Calculator *)

open Types

(** Calculate time series momentum returns *)
let calculate_returns ~(prices : (string * float) array) : (float * float * float) =
  let n = Array.length prices in
  if n < 63 then (0.0, 0.0, 0.0) (* Need ~3 months of data *)
  else
    let current = snd prices.(n - 1) in
    let week_ago = if n >= 5 then snd prices.(n - 5) else current in
    let month_ago = if n >= 21 then snd prices.(n - 21) else current in
    let three_months_ago = if n >= 63 then snd prices.(n - 63) else current in

    let return_1w = (current -. week_ago) /. week_ago in
    let return_1m = (current -. month_ago) /. month_ago in
    let return_3m = (current -. three_months_ago) /. three_months_ago in

    (return_1w, return_1m, return_3m)

(** Calculate proximity to 52-week high *)
let pct_from_52w_high ~(prices : (string * float) array) : float =
  let n = Array.length prices in
  if n = 0 then 0.0
  else
    let current = snd prices.(n - 1) in
    let lookback = min n 252 in  (* ~52 weeks *)

    let high_52w = Array.fold_left (fun acc (_, price) -> max acc price)
      (snd prices.(n - 1))
      (Array.sub prices (n - lookback) lookback)
    in

    if high_52w > 0.0 then
      ((current -. high_52w) /. high_52w) *. 100.0
    else 0.0

(** Calculate simple beta vs market *)
let calculate_beta ~(stock_prices : (string * float) array) ~(market_prices : (string * float) array) : float =
  let n = min (Array.length stock_prices) (Array.length market_prices) in
  if n < 21 then 1.0  (* Default to 1.0 if insufficient data *)
  else
    (* Calculate returns *)
    let stock_returns = Array.init (n - 1) (fun i ->
      let p0 = snd stock_prices.(i) in
      let p1 = snd stock_prices.(i + 1) in
      (p1 -. p0) /. p0
    ) in

    let market_returns = Array.init (n - 1) (fun i ->
      let p0 = snd market_prices.(i) in
      let p1 = snd market_prices.(i + 1) in
      (p1 -. p0) /. p0
    ) in

    (* Calculate covariance and variance *)
    let stock_mean = Array.fold_left (+.) 0.0 stock_returns /. float_of_int (n - 1) in
    let market_mean = Array.fold_left (+.) 0.0 market_returns /. float_of_int (n - 1) in

    let covariance =
      let sum = ref 0.0 in
      for i = 0 to Array.length stock_returns - 1 do
        sum := !sum +. ((stock_returns.(i) -. stock_mean) *. (market_returns.(i) -. market_mean))
      done;
      !sum /. float_of_int (n - 2)
    in

    let market_variance = Array.fold_left (fun acc mr ->
      let dev = mr -. market_mean in
      acc +. (dev *. dev)
    ) 0.0 market_returns /. float_of_int (n - 2) in

    if market_variance > 0.0 then
      covariance /. market_variance
    else 1.0

(** Calculate alpha (excess return vs market) *)
let calculate_alpha ~(stock_return : float) ~(market_return : float) ~(beta : float) : float =
  stock_return -. (beta *. market_return)

(** Calculate momentum score from components *)
let calculate_momentum_score
    ~(return_1m : float)
    ~(return_3m : float)
    ~(pct_from_high : float)
    ~(alpha : float)
    : float =

  (* Weight the components *)
  let score =
    0.3 *. (if return_1m > 0.0 then 1.0 else -1.0) *. (min (abs_float return_1m) 0.2 /. 0.2) +.
    0.3 *. (if return_3m > 0.0 then 1.0 else -1.0) *. (min (abs_float return_3m) 0.5 /. 0.5) +.
    0.2 *. (max (-1.0) (min 1.0 (pct_from_high /. 20.0))) +.
    0.2 *. (if alpha > 0.0 then 1.0 else -1.0) *. (min (abs_float alpha) 0.1 /. 0.1)
  in

  (* Clamp to [-1, 1] *)
  max (-1.0) (min 1.0 score)

(** Compute momentum metrics *)
let compute_momentum
    ~(ticker : string)
    ~(stock_prices : (string * float) array)
    ~(market_prices : (string * float) array)
    ~(rank_1m : int)
    ~(rank_3m : int)
    ~(percentile : float)
    : momentum =

  (* Calculate returns *)
  let (return_1w, return_1m, return_3m) = calculate_returns ~prices:stock_prices in

  (* Calculate beta and alpha *)
  let beta = calculate_beta ~stock_prices ~market_prices in
  let market_1m = if Array.length market_prices >= 21 then
    let current = snd market_prices.(Array.length market_prices - 1) in
    let month_ago = snd market_prices.(Array.length market_prices - 21) in
    (current -. month_ago) /. month_ago
  else 0.0
  in
  let alpha_1m = calculate_alpha ~stock_return:return_1m ~market_return:market_1m ~beta in

  (* Calculate 52-week high proximity *)
  let pct_from_52w_high = pct_from_52w_high ~prices:stock_prices in

  (* Calculate momentum score *)
  let momentum_score = calculate_momentum_score
    ~return_1m
    ~return_3m
    ~pct_from_high:pct_from_52w_high
    ~alpha:alpha_1m
  in

  {
    ticker;
    return_1w;
    return_1m;
    return_3m;
    rank_1m;
    rank_3m;
    percentile;
    beta;
    alpha_1m;
    pct_from_52w_high;
    momentum_score;
  }

(** Print momentum metrics *)
let print_momentum (mom : momentum) : unit =
  Printf.printf "\n=== Momentum: %s ===\n" mom.ticker;
  Printf.printf "Returns: 1W=%.2f%% | 1M=%.2f%% | 3M=%.2f%%\n"
    (mom.return_1w *. 100.0) (mom.return_1m *. 100.0) (mom.return_3m *. 100.0);
  Printf.printf "Beta: %.2f | Alpha (1M): %.2f%%\n" mom.beta (mom.alpha_1m *. 100.0);
  Printf.printf "From 52W High: %.2f%%\n" mom.pct_from_52w_high;
  Printf.printf "Momentum Score: %.2f\n" mom.momentum_score;

  if mom.momentum_score > 0.5 then
    Printf.printf "✓ STRONG POSITIVE MOMENTUM - Consider bull spreads\n"
  else if mom.momentum_score < -0.5 then
    Printf.printf "✓ STRONG NEGATIVE MOMENTUM - Consider bear spreads\n"
