(* Realized volatility estimators implementation *)

open Types

let trading_days_per_year = 252.0
let sqrt_trading_days = sqrt trading_days_per_year

(* Helper: compute log returns *)
let log_returns prices =
  let n = Array.length prices in
  if n < 2 then [||]
  else
    Array.init (n - 1) (fun i ->
      log (prices.(i + 1) /. prices.(i))
    )

(* Helper: extract close prices from OHLC bars *)
let extract_closes bars =
  Array.map (fun bar -> bar.close) bars

(* Convert annualized vol to daily vol *)
let annualized_to_daily vol =
  vol /. sqrt_trading_days

(* Convert daily vol to annualized vol *)
let daily_to_annualized vol =
  vol *. sqrt_trading_days

(* Close-to-close estimator *)
let close_to_close bars ~window_days =
  let n = Array.length bars in
  if n < window_days + 1 then [||]
  else begin
    let closes = extract_closes bars in
    let returns = log_returns closes in

    (* Rolling window variance *)
    let num_estimates = n - window_days in
    Array.init num_estimates (fun i ->
      let window_returns = Array.sub returns i window_days in

      (* Sample variance *)
      let mean = Array.fold_left (+.) 0.0 window_returns /. float_of_int window_days in
      let variance = Array.fold_left (fun acc r ->
        let dev = r -. mean in
        acc +. dev *. dev
      ) 0.0 window_returns /. float_of_int (window_days - 1) in

      let daily_vol = sqrt variance in
      let annualized_vol = daily_to_annualized daily_vol in

      {
        timestamp = bars.(i + window_days).timestamp;
        estimator = CloseToClose;
        volatility = annualized_vol;
        window_days;
      }
    )
  end

(* Parkinson high-low estimator *)
let parkinson bars ~window_days =
  let n = Array.length bars in
  if n < window_days then [||]
  else begin
    let num_estimates = n - window_days + 1 in

    Array.init num_estimates (fun i ->
      let sum_hl_sq = ref 0.0 in

      for j = i to i + window_days - 1 do
        let bar = bars.(j) in
        let hl_ratio = log (bar.high /. bar.low) in
        sum_hl_sq := !sum_hl_sq +. hl_ratio *. hl_ratio
      done;

      (* Parkinson formula: σ² = (1/(4n·ln(2))) × Σ[log(H/L)]² *)
      let variance = !sum_hl_sq /. (4.0 *. float_of_int window_days *. log 2.0) in
      let daily_vol = sqrt variance in
      let annualized_vol = daily_to_annualized daily_vol in

      {
        timestamp = bars.(i + window_days - 1).timestamp;
        estimator = Parkinson;
        volatility = annualized_vol;
        window_days;
      }
    )
  end

(* Garman-Klass OHLC estimator *)
let garman_klass bars ~window_days =
  let n = Array.length bars in
  if n < window_days then [||]
  else begin
    let num_estimates = n - window_days + 1 in

    Array.init num_estimates (fun i ->
      let sum_variance = ref 0.0 in

      for j = i to i + window_days - 1 do
        let bar = bars.(j) in
        let hl = log (bar.high /. bar.low) in
        let co = log (bar.close /. bar.open_) in

        (* GK formula: 0.5·(log(H/L))² - (2·ln(2)-1)·(log(C/O))² *)
        let term1 = 0.5 *. hl *. hl in
        let term2 = (2.0 *. log 2.0 -. 1.0) *. co *. co in
        sum_variance := !sum_variance +. term1 -. term2
      done;

      let variance = !sum_variance /. float_of_int window_days in
      let daily_vol = sqrt variance in
      let annualized_vol = daily_to_annualized daily_vol in

      {
        timestamp = bars.(i + window_days - 1).timestamp;
        estimator = GarmanKlass;
        volatility = annualized_vol;
        window_days;
      }
    )
  end

(* Rogers-Satchell drift-independent estimator *)
let rogers_satchell bars ~window_days =
  let n = Array.length bars in
  if n < window_days then [||]
  else begin
    let num_estimates = n - window_days + 1 in

    Array.init num_estimates (fun i ->
      let sum_variance = ref 0.0 in

      for j = i to i + window_days - 1 do
        let bar = bars.(j) in
        let hc = log (bar.high /. bar.close) in
        let ho = log (bar.high /. bar.open_) in
        let lc = log (bar.low /. bar.close) in
        let lo = log (bar.low /. bar.open_) in

        (* RS formula: sqrt[log(H/C)·log(H/O) + log(L/C)·log(L/O)] *)
        sum_variance := !sum_variance +. (hc *. ho) +. (lc *. lo)
      done;

      let variance = !sum_variance /. float_of_int window_days in
      let daily_vol = sqrt variance in
      let annualized_vol = daily_to_annualized daily_vol in

      {
        timestamp = bars.(i + window_days - 1).timestamp;
        estimator = RogersSatchell;
        volatility = annualized_vol;
        window_days;
      }
    )
  end

(* Yang-Zhang estimator (combines multiple components) *)
let yang_zhang bars ~window_days =
  let n = Array.length bars in
  if n < window_days + 1 then [||]
  else begin
    let num_estimates = n - window_days in

    Array.init num_estimates (fun i ->
      (* Component 1: Overnight variance (close to open) *)
      let overnight_returns = Array.init window_days (fun j ->
        let bar_prev = bars.(i + j) in
        let bar_curr = bars.(i + j + 1) in
        log (bar_curr.open_ /. bar_prev.close)
      ) in

      let mean_o = Array.fold_left (+.) 0.0 overnight_returns /. float_of_int window_days in
      let var_o = Array.fold_left (fun acc r ->
        let dev = r -. mean_o in
        acc +. dev *. dev
      ) 0.0 overnight_returns /. float_of_int (window_days - 1) in

      (* Component 2: Open-to-close variance *)
      let oc_returns = Array.init window_days (fun j ->
        let bar = bars.(i + j + 1) in
        log (bar.close /. bar.open_)
      ) in

      let mean_c = Array.fold_left (+.) 0.0 oc_returns /. float_of_int window_days in
      let var_c = Array.fold_left (fun acc r ->
        let dev = r -. mean_c in
        acc +. dev *. dev
      ) 0.0 oc_returns /. float_of_int (window_days - 1) in

      (* Component 3: Rogers-Satchell variance *)
      let rs_bars = Array.sub bars (i + 1) window_days in
      let rs_var =
        let sum = ref 0.0 in
        for j = 0 to window_days - 1 do
          let bar = rs_bars.(j) in
          let hc = log (bar.high /. bar.close) in
          let ho = log (bar.high /. bar.open_) in
          let lc = log (bar.low /. bar.close) in
          let lo = log (bar.low /. bar.open_) in
          sum := !sum +. (hc *. ho) +. (lc *. lo)
        done;
        !sum /. float_of_int window_days
      in

      (* Yang-Zhang combination: σ² = σ_o² + k·σ_c² + (1-k)·σ_rs² *)
      (* k = 0.34 / (1.34 + (n+1)/(n-1)) *)
      let n_f = float_of_int window_days in
      let k = 0.34 /. (1.34 +. (n_f +. 1.0) /. (n_f -. 1.0)) in

      let variance = var_o +. k *. var_c +. (1.0 -. k) *. rs_var in
      let daily_vol = sqrt variance in
      let annualized_vol = daily_to_annualized daily_vol in

      {
        timestamp = bars.(i + window_days).timestamp;
        estimator = YangZhang;
        volatility = annualized_vol;
        window_days;
      }
    )
  end

(* Intraday realized volatility from high-frequency prices *)
let intraday_realized_vol ~prices ~timestamps ~window_hours =
  let n = Array.length prices in
  if n < 2 then 0.0
  else begin
    let window_seconds = float_of_int window_hours *. 3600.0 in
    let cutoff_time = timestamps.(n - 1) -. window_seconds in

    (* Find start index within window *)
    let start_idx = ref 0 in
    while !start_idx < n && timestamps.(!start_idx) < cutoff_time do
      incr start_idx
    done;

    if !start_idx >= n - 1 then 0.0
    else begin
      (* Compute realized variance as sum of squared log returns *)
      let sum_sq_returns = ref 0.0 in
      for i = !start_idx to n - 2 do
        let ret = log (prices.(i + 1) /. prices.(i)) in
        sum_sq_returns := !sum_sq_returns +. ret *. ret
      done;

      (* Annualize assuming 252 trading days, 6.5 hours per day *)
      let hours_per_year = 252.0 *. 6.5 in
      let annualization_factor = hours_per_year /. float_of_int window_hours in

      sqrt (!sum_sq_returns *. annualization_factor)
    end
  end

(* Compare all estimators *)
let compare_estimators bars ~window_days =
  let cc = close_to_close bars ~window_days in
  let pk = parkinson bars ~window_days in
  let gk = garman_klass bars ~window_days in
  let rs = rogers_satchell bars ~window_days in
  let yz = yang_zhang bars ~window_days in

  (* Get latest estimate from each *)
  let get_latest arr =
    if Array.length arr = 0 then 0.0
    else arr.(Array.length arr - 1).volatility
  in

  [|
    (CloseToClose, get_latest cc);
    (Parkinson, get_latest pk);
    (GarmanKlass, get_latest gk);
    (RogersSatchell, get_latest rs);
    (YangZhang, get_latest yz);
  |]

(* Get latest RV estimate *)
let get_latest_rv rv_array =
  if Array.length rv_array = 0 then None
  else Some rv_array.(Array.length rv_array - 1)
