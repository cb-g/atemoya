(* Dispersion trading signals and position construction *)

open Types

(** Dispersion metrics **)

(* Calculate weighted average implied volatility *)
let weighted_avg_iv ~constituent_vols ~weights =
  let n = Array.length constituent_vols in
  let weighted_sum = ref 0.0 in
  for i = 0 to n - 1 do
    weighted_sum := !weighted_sum +. weights.(i) *. constituent_vols.(i)
  done;
  !weighted_sum

(* Calculate dispersion level (weighted avg IV - index IV) *)
let dispersion_level ~index_iv ~constituent_vols ~weights =
  let avg_iv = weighted_avg_iv ~constituent_vols ~weights in
  avg_iv -. index_iv

(* Calculate z-score of dispersion level *)
let dispersion_zscore ~current_dispersion ~historical_dispersion =
  let mean = Correlation.mean historical_dispersion in
  let std = Correlation.std historical_dispersion in
  if std > 0.0 then
    (current_dispersion -. mean) /. std
  else
    0.0

(* Calculate dispersion metrics *)
let calculate_dispersion_metrics ~index_iv ~constituent_vols ~weights ~historical_dispersion ~implied_corr =
  let avg_iv = weighted_avg_iv ~constituent_vols ~weights in
  let disp_level = dispersion_level ~index_iv ~constituent_vols ~weights in
  let zscore = dispersion_zscore ~current_dispersion:disp_level ~historical_dispersion in

  (* Generate signal based on z-score *)
  let signal =
    if zscore > 1.5 then "LONG"       (* High dispersion -> buy dispersion *)
    else if zscore < -1.5 then "SHORT" (* Low dispersion -> sell dispersion *)
    else "NEUTRAL"
  in

  {
    index_iv;
    weighted_avg_iv = avg_iv;
    dispersion_level = disp_level;
    dispersion_zscore = zscore;
    implied_corr;
    signal;
  }

(** Position construction **)

(* Build index position *)
let build_index_position ~ticker ~spot ~option ~notional =
  {
    ticker;
    spot;
    option;
    notional;
  }

(* Build single-name position *)
let build_single_name ~ticker ~weight ~spot ~option ~notional =
  {
    ticker;
    weight;
    spot;
    option;
    notional;
  }

(* Build dispersion position

   Long dispersion:  Buy single-name options, sell index options
   Short dispersion: Sell single-name options, buy index options
*)
let build_dispersion_position ~position_type ~index ~single_names ~entry_date ~expiry_date =
  {
    position_type;
    index;
    single_names;
    entry_date;
    expiry_date;
  }

(** Position Greeks **)

(* Calculate position delta *)
let position_delta (position : dispersion_position) =
  let index_delta = position.index.option.delta *. position.index.notional in
  let single_delta = Array.fold_left (fun acc (sn : single_name) ->
    acc +. sn.option.delta *. sn.notional
  ) 0.0 position.single_names in

  match position.position_type with
  | LongDispersion -> single_delta -. index_delta  (* Long stocks, short index *)
  | ShortDispersion -> index_delta -. single_delta (* Short stocks, long index *)

(* Calculate position gamma *)
let position_gamma (position : dispersion_position) =
  let index_gamma = position.index.option.gamma *. position.index.notional in
  let single_gamma = Array.fold_left (fun acc (sn : single_name) ->
    acc +. sn.option.gamma *. sn.notional
  ) 0.0 position.single_names in

  match position.position_type with
  | LongDispersion -> single_gamma -. index_gamma
  | ShortDispersion -> index_gamma -. single_gamma

(* Calculate position vega *)
let position_vega (position : dispersion_position) =
  let index_vega = position.index.option.vega *. position.index.notional in
  let single_vega = Array.fold_left (fun acc (sn : single_name) ->
    acc +. sn.option.vega *. sn.notional
  ) 0.0 position.single_names in

  match position.position_type with
  | LongDispersion -> single_vega -. index_vega
  | ShortDispersion -> index_vega -. single_vega

(* Calculate position theta *)
let position_theta (position : dispersion_position) =
  let index_theta = position.index.option.theta *. position.index.notional in
  let single_theta = Array.fold_left (fun acc (sn : single_name) ->
    acc +. sn.option.theta *. sn.notional
  ) 0.0 position.single_names in

  match position.position_type with
  | LongDispersion -> single_theta -. index_theta
  | ShortDispersion -> index_theta -. single_theta

(** Position valuation **)

(* Calculate position P&L *)
let position_pnl ~position ~new_index_price ~new_single_prices ~new_index_iv:_ ~new_single_ivs:_ =
  (* Index P&L *)
  let index_price_change = new_index_price -. position.index.option.price in
  let index_pnl = index_price_change *. position.index.notional in

  (* Single-name P&L *)
  let single_pnl = ref 0.0 in
  for i = 0 to Array.length position.single_names - 1 do
    let sn = position.single_names.(i) in
    let new_price = new_single_prices.(i) in
    let price_change = new_price -. sn.option.price in
    single_pnl := !single_pnl +. price_change *. sn.notional
  done;

  match position.position_type with
  | LongDispersion -> !single_pnl -. index_pnl  (* Profit when stocks outperform index *)
  | ShortDispersion -> index_pnl -. !single_pnl (* Profit when index outperforms stocks *)
