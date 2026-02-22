(** Liquidity scoring computations *)

open Types

let array_mean arr =
  let n = Array.length arr in
  if n = 0 then 0.0
  else Array.fold_left ( +. ) 0.0 arr /. float_of_int n

let array_std arr =
  let n = Array.length arr in
  if n < 2 then 0.0
  else
    let mean = array_mean arr in
    let sum_sq = Array.fold_left (fun acc x -> acc +. (x -. mean) ** 2.0) 0.0 arr in
    sqrt (sum_sq /. float_of_int (n - 1))

let array_tail arr n =
  let len = Array.length arr in
  if n >= len then arr
  else Array.sub arr (len - n) n

let array_diff arr =
  let n = Array.length arr in
  if n < 2 then [||]
  else Array.init (n - 1) (fun i -> arr.(i + 1) -. arr.(i))

let returns close =
  let n = Array.length close in
  if n < 2 then [||]
  else Array.init (n - 1) (fun i ->
    if close.(i) = 0.0 then 0.0
    else (close.(i + 1) -. close.(i)) /. close.(i))

(** Amihud Illiquidity Ratio: avg(|return| / dollar_volume) * 1e6 *)
let amihud_ratio close volume ~window =
  let rets = returns close in
  let n = Array.length rets in
  if n < window then Float.infinity
  else
    let start = n - window in
    let sum = ref 0.0 in
    let count = ref 0 in
    for i = start to n - 1 do
      let dollar_vol = close.(i + 1) *. volume.(i + 1) in
      if dollar_vol > 0.0 then begin
        sum := !sum +. (abs_float rets.(i) /. dollar_vol);
        incr count
      end
    done;
    if !count = 0 then Float.infinity
    else (!sum /. float_of_int !count) *. 1e6

(** Turnover Ratio: avg_daily_volume / shares_outstanding *)
let turnover_ratio volume shares_outstanding ~window =
  if shares_outstanding <= 0.0 then 0.0
  else
    let recent = array_tail volume window in
    array_mean recent /. shares_outstanding

(** Relative Volume: latest / avg(previous window) *)
let relative_volume volume ~window =
  let n = Array.length volume in
  if n < window + 1 then 0.0
  else
    let prev = Array.sub volume (n - window - 1) window in
    let avg = array_mean prev in
    if avg <= 0.0 then 0.0
    else volume.(n - 1) /. avg

(** Volume Volatility: std(volume) / mean(volume) *)
let volume_volatility volume ~window =
  let recent = array_tail volume window in
  let mean = array_mean recent in
  if mean <= 0.0 then Float.infinity
  else array_std recent /. mean

(** Spread Proxy: avg((high - low) / close) as percentage *)
let spread_proxy high low close ~window =
  let n = Array.length close in
  if n < window then 0.0
  else
    let start = n - window in
    let sum = ref 0.0 in
    for i = start to n - 1 do
      if close.(i) > 0.0 then
        sum := !sum +. ((high.(i) -. low.(i)) /. close.(i))
    done;
    (!sum /. float_of_int window) *. 100.0

(** Calculate composite liquidity score (0-100) *)
let liquidity_score ~amihud ~turnover ~vol_vol ~spread =
  let score = ref 50.0 in

  (* Amihud: lower is better *)
  if amihud < 0.01 then score := !score +. 15.0
  else if amihud < 0.1 then score := !score +. 10.0
  else if amihud < 1.0 then score := !score +. 5.0
  else if amihud > 10.0 then score := !score -. 15.0
  else if amihud > 5.0 then score := !score -. 10.0;

  (* Turnover: higher is better *)
  if turnover > 0.05 then score := !score +. 15.0
  else if turnover > 0.02 then score := !score +. 10.0
  else if turnover > 0.01 then score := !score +. 5.0
  else if turnover < 0.001 then score := !score -. 10.0;

  (* Volume volatility: lower is better *)
  if vol_vol < 0.3 then score := !score +. 10.0
  else if vol_vol < 0.5 then score := !score +. 5.0
  else if vol_vol > 1.0 then score := !score -. 10.0;

  (* Spread: lower is better *)
  if spread < 0.5 then score := !score +. 10.0
  else if spread < 1.0 then score := !score +. 5.0
  else if spread > 3.0 then score := !score -. 10.0;

  max 0.0 (min 100.0 !score)

let liquidity_tier score =
  if score >= 80.0 then "Excellent"
  else if score >= 65.0 then "Good"
  else if score >= 50.0 then "Fair"
  else if score >= 35.0 then "Poor"
  else "Very Poor"

(** Compute all liquidity metrics *)
let compute_metrics (data : ticker_data) ~window : liquidity_metrics =
  let ohlcv = data.ohlcv in
  let amihud = amihud_ratio ohlcv.close ohlcv.volume ~window in
  let turnover = turnover_ratio ohlcv.volume data.shares_outstanding ~window in
  let rel_vol = relative_volume ohlcv.volume ~window in
  let vol_vol = volume_volatility ohlcv.volume ~window in
  let spread = spread_proxy ohlcv.high ohlcv.low ohlcv.close ~window in
  let score = liquidity_score ~amihud ~turnover ~vol_vol ~spread in
  let tier = liquidity_tier score in
  {
    amihud_ratio = amihud;
    turnover_ratio = turnover;
    relative_volume = rel_vol;
    volume_volatility = vol_vol;
    spread_proxy = spread;
    liquidity_score = score;
    liquidity_tier = tier;
  }
