(** Portfolio Analysis Functions *)

open Types

(** Calculate thesis score from bull and bear arguments *)
let calculate_thesis_score (bull : thesis_arg list) (bear : thesis_arg list) : thesis_score =
  let bull_score = List.fold_left (fun acc a -> acc + a.weight) 0 bull in
  let bear_score = List.fold_left (fun acc a -> acc + a.weight) 0 bear in
  let net = bull_score - bear_score in
  let conviction =
    if net > 10 then "strong bull"
    else if net > 5 then "moderately bullish"
    else if net > 0 then "slightly bullish"
    else if net = 0 then "neutral"
    else if net > -5 then "slightly bearish"
    else if net > -10 then "moderately bearish"
    else "strong bear"
  in
  { bull_score; bear_score; net_score = net; conviction }

(** Check price alerts for a position *)
let check_price_alerts (pos : portfolio_position) (market : market_data option) : triggered_alert list =
  match market with
  | None -> []
  | Some m ->
    let alerts = ref [] in
    let price = m.current_price in
    let cost = pos.position.avg_cost in
    let is_short = pos.position.pos_type = Short in

    (* Stop loss: for longs, price drops below stop; for shorts, price rises above stop *)
    (match pos.levels.stop_loss with
     | Some stop when (not is_short && price <= stop) || (is_short && price >= stop) ->
       alerts := {
         ticker = pos.ticker;
         alert = HitStopLoss (price, stop);
         priority = Urgent;
         message = Io.alert_to_string (HitStopLoss (price, stop));
       } :: !alerts
     | Some stop when (not is_short && price <= stop *. 1.05) || (is_short && price >= stop *. 0.95) ->
       alerts := {
         ticker = pos.ticker;
         alert = NearStopLoss (price, stop);
         priority = High;
         message = Io.alert_to_string (NearStopLoss (price, stop));
       } :: !alerts
     | _ -> ());

    (* Buy target: for longs/watching, price drops to buy level *)
    (if not is_short then
       match pos.levels.buy_target with
       | Some target when price <= target ->
         alerts := {
           ticker = pos.ticker;
           alert = HitBuyTarget (price, target);
           priority = High;
           message = Io.alert_to_string (HitBuyTarget (price, target));
         } :: !alerts
       | Some target when price <= target *. 1.05 ->
         alerts := {
           ticker = pos.ticker;
           alert = NearBuyTarget (price, target);
           priority = Normal;
           message = Io.alert_to_string (NearBuyTarget (price, target));
         } :: !alerts
       | _ -> ());

    (* Sell target: for longs, price rises above target; for shorts, price drops below target (cover) *)
    (match pos.levels.sell_target with
     | Some target when (not is_short && price >= target) || (is_short && price <= target) ->
       alerts := {
         ticker = pos.ticker;
         alert = HitSellTarget (price, target);
         priority = High;
         message = Io.alert_to_string (HitSellTarget (price, target));
       } :: !alerts
     | _ -> ());

    (* PnL alerts for actual positions *)
    (match pos.position.pos_type with
     | Long when cost > 0.0 ->
       let pnl_pct = (price -. cost) /. cost *. 100.0 in
       if pnl_pct >= 20.0 then
         alerts := {
           ticker = pos.ticker;
           alert = AboveCostBasis (price, cost, pnl_pct);
           priority = Info;
           message = Io.alert_to_string (AboveCostBasis (price, cost, pnl_pct));
         } :: !alerts
       else if pnl_pct <= -10.0 then
         alerts := {
           ticker = pos.ticker;
           alert = BelowCostBasis (price, cost, pnl_pct);
           priority = Normal;
           message = Io.alert_to_string (BelowCostBasis (price, cost, pnl_pct));
         } :: !alerts
     | Short when cost > 0.0 ->
       let pnl_pct = (cost -. price) /. cost *. 100.0 in
       if pnl_pct >= 20.0 then
         alerts := {
           ticker = pos.ticker;
           alert = AboveCostBasis (price, cost, pnl_pct);
           priority = Info;
           message = Io.alert_to_string (AboveCostBasis (price, cost, pnl_pct));
         } :: !alerts
       else if pnl_pct <= -10.0 then
         alerts := {
           ticker = pos.ticker;
           alert = BelowCostBasis (price, cost, pnl_pct);
           priority = Normal;
           message = Io.alert_to_string (BelowCostBasis (price, cost, pnl_pct));
         } :: !alerts
     | _ -> ());

    List.rev !alerts

(** Analyze a single position *)
let analyze_position (pos : portfolio_position) (market_data : (string * market_data) list) : position_analysis =
  let market = List.assoc_opt pos.ticker market_data in
  let thesis = calculate_thesis_score pos.bull pos.bear in
  let pnl_pct = match market, pos.position.pos_type with
    | Some m, Long when pos.position.avg_cost > 0.0 ->
      Some ((m.current_price -. pos.position.avg_cost) /. pos.position.avg_cost *. 100.0)
    | Some m, Short when pos.position.avg_cost > 0.0 ->
      Some ((pos.position.avg_cost -. m.current_price) /. pos.position.avg_cost *. 100.0)
    | _ -> None
  in
  let pnl_abs = match market, pos.position.pos_type with
    | Some m, Long ->
      Some ((m.current_price -. pos.position.avg_cost) *. pos.position.shares)
    | Some m, Short ->
      Some ((pos.position.avg_cost -. m.current_price) *. pos.position.shares)
    | _ -> None
  in
  let alerts = check_price_alerts pos market in
  { position = pos; market; thesis; pnl_pct; pnl_abs; alerts }

(** Run full portfolio analysis *)
let run_analysis (positions : portfolio_position list) (market_data : (string * market_data) list) : portfolio_analysis =
  let now = Unix.gettimeofday () |> Unix.gmtime in
  let run_time = Printf.sprintf "%04d-%02d-%02d %02d:%02d:%02d UTC"
      (now.Unix.tm_year + 1900) (now.Unix.tm_mon + 1) now.Unix.tm_mday
      now.Unix.tm_hour now.Unix.tm_min now.Unix.tm_sec
  in

  let analyses = List.map (fun p -> analyze_position p market_data) positions in
  let all_alerts = List.concat_map (fun a -> a.alerts) analyses in

  (* Calculate totals for held positions *)
  let held = List.filter (fun a ->
      match a.position.position.pos_type with Long | Short -> true | Watching -> false
    ) analyses in
  let total_cost = List.fold_left (fun acc a ->
      acc +. (a.position.position.avg_cost *. a.position.position.shares)
    ) 0.0 held in
  let total_value = List.fold_left (fun acc a ->
      match a.market with
      | Some m -> acc +. (m.current_price *. a.position.position.shares)
      | None -> acc
    ) 0.0 held in
  let total_pnl_pct =
    if total_cost > 0.0 then Some ((total_value -. total_cost) /. total_cost *. 100.0)
    else None
  in

  {
    run_time;
    positions = analyses;
    total_value = if total_value > 0.0 then Some total_value else None;
    total_cost = if total_cost > 0.0 then Some total_cost else None;
    total_pnl_pct;
    all_alerts;
  }
