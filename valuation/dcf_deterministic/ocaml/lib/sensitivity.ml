(** Sensitivity analysis for DCF valuation parameters *)

type sensitivity_point = {
  param_value : float;
  fcfe_ivps : float;
  fcff_ivps : float;
}

type sensitivity_results = {
  growth_rate : sensitivity_point list;
  discount_rate : sensitivity_point list;
  terminal_growth : sensitivity_point list;
}

(** Run growth rate sensitivity analysis *)
let analyze_growth_rate
    ~market_data
    ~financial_data
    ~config
    ~cost_of_capital
    ~tax_rate
  =
  (* Sweep growth rate from -2% to +6% in 0.5% steps *)
  let growth_range = List.init 17 (fun i -> -0.02 +. (float_of_int i) *. 0.005) in

  List.filter_map (fun growth ->
    (* For growth sensitivity, we manually construct cash flow projections
       with the specified growth rate, keeping everything else constant *)

    (* Get base year cash flows *)
    let fcfe_0 = Cash_flow.calculate_fcfe ~financial_data ~market_data in
    let fcff_0 = Cash_flow.calculate_fcff ~financial_data ~tax_rate in

    (* Project cash flows manually with the specified growth rate *)
    let projection_years = config.Types.params.projection_years in
    let fcfe_array = Array.init projection_years (fun i ->
      fcfe_0 *. ((1.0 +. growth) ** (float_of_int (i + 1)))
    ) in
    let fcff_array = Array.init projection_years (fun i ->
      fcff_0 *. ((1.0 +. growth) ** (float_of_int (i + 1)))
    ) in

    let manual_projection = Types.{
      fcfe = fcfe_array;
      fcff = fcff_array;
      growth_rate_fcfe = growth;
      growth_rate_fcff = growth;
      growth_clamped_fcfe = false;
      growth_clamped_fcff = false;
    } in

    (* Calculate PV with this projection *)
    let terminal_growth = config.Types.params.terminal_growth_rate in
    let pve_opt = Valuation.calculate_pve
      ~projection:manual_projection
      ~cost_of_equity:cost_of_capital.Types.ce
      ~terminal_growth_rate:terminal_growth
    in

    let pvf_opt = Valuation.calculate_pvf
      ~projection:manual_projection
      ~wacc:cost_of_capital.wacc
      ~terminal_growth_rate:terminal_growth
    in

    match pve_opt, pvf_opt with
    | Some pve, Some pvf ->
        let fcfe_ivps = pve /. market_data.Types.shares_outstanding in
        let pvf_minus_debt = pvf -. market_data.mvb in
        let fcff_ivps = pvf_minus_debt /. market_data.shares_outstanding in
        Some { param_value = growth *. 100.0; fcfe_ivps; fcff_ivps }
    | _ -> None
  ) growth_range

(** Run discount rate sensitivity analysis *)
let analyze_discount_rate
    ~market_data
    ~financial_data
    ~config
    ~cost_of_capital
    ~tax_rate
  =
  (* Sweep discount rate from 6% to 12% in 0.5% steps *)
  let discount_range = List.init 13 (fun i -> 0.06 +. (float_of_int i) *. 0.005) in

  (* Use base projection (doesn't change with discount rate) *)
  let base_projection = Projection.create_projection
    ~financial_data
    ~market_data
    ~tax_rate
    ~params:config.Types.params
  in

  let terminal_growth = config.Types.params.terminal_growth_rate in

  List.filter_map (fun discount ->
    (* For discount rate sensitivity, we vary cost of equity (for FCFE)
       and WACC (for FCFF) while keeping everything else constant *)

    (* Calculate FCFE with modified cost of equity *)
    let pve_opt = Valuation.calculate_pve
      ~projection:base_projection
      ~cost_of_equity:discount
      ~terminal_growth_rate:terminal_growth
    in

    (* For FCFF, we need to properly adjust WACC when CE changes.
       WACC = E_weight * CE + D_weight * CB * (1-T)
       When varying CE, only the equity component should change:
       new_WACC = old_WACC + E_weight * (new_CE - old_CE)
       where E_weight = MVE / (MVE + MVB) *)
    let total_value = market_data.Types.mve +. market_data.mvb in
    let equity_weight =
      if total_value > 0.0 then market_data.mve /. total_value
      else 1.0 (* Default to all equity if no data *)
    in
    let ce_delta = discount -. cost_of_capital.Types.ce in
    let modified_wacc = cost_of_capital.wacc +. (equity_weight *. ce_delta) in

    let pvf_opt = Valuation.calculate_pvf
      ~projection:base_projection
      ~wacc:modified_wacc
      ~terminal_growth_rate:terminal_growth
    in

    match pve_opt, pvf_opt with
    | Some pve, Some pvf ->
        let fcfe_ivps = pve /. market_data.Types.shares_outstanding in
        let pvf_minus_debt = pvf -. market_data.mvb in
        let fcff_ivps = pvf_minus_debt /. market_data.shares_outstanding in
        Some { param_value = discount *. 100.0; fcfe_ivps; fcff_ivps }
    | _ -> None
  ) discount_range

(** Run terminal growth sensitivity analysis *)
let analyze_terminal_growth
    ~market_data
    ~financial_data
    ~config
    ~cost_of_capital
    ~tax_rate
  =
  (* Sweep terminal growth from 1% to 4% in 0.25% steps *)
  let terminal_range = List.init 13 (fun i -> 0.01 +. (float_of_int i) *. 0.0025) in

  (* Use base projection *)
  let base_projection = Projection.create_projection
    ~financial_data
    ~market_data
    ~tax_rate
    ~params:config.Types.params
  in

  List.filter_map (fun terminal_g ->
    (* Vary terminal growth rate only *)
    let pve_opt = Valuation.calculate_pve
      ~projection:base_projection
      ~cost_of_equity:cost_of_capital.Types.ce
      ~terminal_growth_rate:terminal_g
    in

    let pvf_opt = Valuation.calculate_pvf
      ~projection:base_projection
      ~wacc:cost_of_capital.wacc
      ~terminal_growth_rate:terminal_g
    in

    match pve_opt, pvf_opt with
    | Some pve, Some pvf ->
        let fcfe_ivps = pve /. market_data.Types.shares_outstanding in
        let pvf_minus_debt = pvf -. market_data.mvb in
        let fcff_ivps = pvf_minus_debt /. market_data.shares_outstanding in
        Some { param_value = terminal_g *. 100.0; fcfe_ivps; fcff_ivps }
    | _ -> None
  ) terminal_range

let run_sensitivity_analysis
    ~market_data
    ~financial_data
    ~config
    ~cost_of_capital
    ~tax_rate
  =
  Printf.printf "Running growth rate sensitivity...\n";
  let growth_rate = analyze_growth_rate
    ~market_data ~financial_data ~config ~cost_of_capital ~tax_rate
  in

  Printf.printf "Running discount rate sensitivity...\n";
  let discount_rate = analyze_discount_rate
    ~market_data ~financial_data ~config ~cost_of_capital ~tax_rate
  in

  Printf.printf "Running terminal growth sensitivity...\n";
  let terminal_growth = analyze_terminal_growth
    ~market_data ~financial_data ~config ~cost_of_capital ~tax_rate
  in

  { growth_rate; discount_rate; terminal_growth }

let write_sensitivity_csv
    ~output_dir
    ~ticker
    ~results
    ~market_price
  =
  (* Ensure output directory structure exists *)
  let sensitivity_dir = Filename.concat output_dir "sensitivity" in
  let data_dir = Filename.concat sensitivity_dir "data" in

  (try Unix.mkdir sensitivity_dir 0o755 with Unix.Unix_error (Unix.EEXIST, _, _) -> ());
  (try Unix.mkdir data_dir 0o755 with Unix.Unix_error (Unix.EEXIST, _, _) -> ());

  (* Write growth rate sensitivity *)
  let growth_file = Filename.concat data_dir (Printf.sprintf "sensitivity_growth_%s.csv" ticker) in
  let oc_growth = open_out growth_file in
  Printf.fprintf oc_growth "growth_rate_pct,fcfe_ivps,fcff_ivps,market_price\n";
  List.iter (fun pt ->
    Printf.fprintf oc_growth "%.2f,%.2f,%.2f,%.2f\n"
      pt.param_value pt.fcfe_ivps pt.fcff_ivps market_price
  ) results.growth_rate;
  close_out oc_growth;
  Printf.printf "Growth sensitivity written to: %s\n" growth_file;

  (* Write discount rate sensitivity *)
  let discount_file = Filename.concat data_dir (Printf.sprintf "sensitivity_discount_%s.csv" ticker) in
  let oc_discount = open_out discount_file in
  Printf.fprintf oc_discount "discount_rate_pct,fcfe_ivps,fcff_ivps,market_price\n";
  List.iter (fun pt ->
    Printf.fprintf oc_discount "%.2f,%.2f,%.2f,%.2f\n"
      pt.param_value pt.fcfe_ivps pt.fcff_ivps market_price
  ) results.discount_rate;
  close_out oc_discount;
  Printf.printf "Discount sensitivity written to: %s\n" discount_file;

  (* Write terminal growth sensitivity *)
  let terminal_file = Filename.concat data_dir (Printf.sprintf "sensitivity_terminal_%s.csv" ticker) in
  let oc_terminal = open_out terminal_file in
  Printf.fprintf oc_terminal "terminal_growth_pct,fcfe_ivps,fcff_ivps,market_price\n";
  List.iter (fun pt ->
    Printf.fprintf oc_terminal "%.2f,%.2f,%.2f,%.2f\n"
      pt.param_value pt.fcfe_ivps pt.fcff_ivps market_price
  ) results.terminal_growth;
  close_out oc_terminal;
  Printf.printf "Terminal growth sensitivity written to: %s\n" terminal_file

(* ============================================================
   Specialized sensitivity analyses for bank/insurance/oil_gas
   ============================================================ *)

type specialized_point = {
  param_value : float;
  fair_value : float;
}

type bank_sensitivity_results = {
  roe : specialized_point list;
  cost_of_equity : specialized_point list;
  growth : specialized_point list;
}

type insurance_sensitivity_results = {
  combined_ratio : specialized_point list;
  investment_yield : specialized_point list;
  ins_cost_of_equity : specialized_point list;
}

type oil_gas_sensitivity_results = {
  oil_price : specialized_point list;
  lifting_cost : specialized_point list;
  og_discount_rate : specialized_point list;
}

(* --- Bank sensitivity --- *)

let run_bank_sensitivity ~(financial : Types.financial_data)
    ~(market : Types.market_data) ~risk_free_rate ~equity_risk_premium
    ~terminal_growth_rate ~projection_years =

  let shares = market.shares_outstanding in
  let book_value = financial.book_value_equity in
  let base_coe = Bank.calculate_bank_cost_of_equity
    ~risk_free_rate ~equity_risk_premium ~market in

  (* 1. ROE sensitivity: 5% to 25% in 1% steps *)
  Printf.printf "Running bank ROE sensitivity...\n";
  let roe = List.init 21 (fun i ->
    let roe_val = 0.05 +. (float_of_int i) *. 0.01 in
    let excess_pv = Bank.calculate_excess_return_value
      ~roe:roe_val ~cost_of_equity:base_coe ~book_value
      ~growth_rate:0.03 ~projection_years ~terminal_growth:terminal_growth_rate in
    let fv = (book_value +. excess_pv) /. shares in
    { param_value = roe_val *. 100.0; fair_value = fv }
  ) in

  (* 2. Cost of equity sensitivity: 6% to 12% in 0.5% steps *)
  Printf.printf "Running bank cost of equity sensitivity...\n";
  let metrics = Bank.calculate_bank_metrics ~financial ~market in
  let cost_of_equity = List.init 13 (fun i ->
    let coe_val = 0.06 +. (float_of_int i) *. 0.005 in
    let excess_pv = Bank.calculate_excess_return_value
      ~roe:metrics.roe ~cost_of_equity:coe_val ~book_value
      ~growth_rate:0.03 ~projection_years ~terminal_growth:terminal_growth_rate in
    let fv = (book_value +. excess_pv) /. shares in
    { param_value = coe_val *. 100.0; fair_value = fv }
  ) in

  (* 3. Sustainable growth sensitivity: 0% to 6% in 0.5% steps *)
  Printf.printf "Running bank growth sensitivity...\n";
  let growth = List.init 13 (fun i ->
    let g = (float_of_int i) *. 0.005 in
    let excess_pv = Bank.calculate_excess_return_value
      ~roe:metrics.roe ~cost_of_equity:base_coe ~book_value
      ~growth_rate:g ~projection_years ~terminal_growth:terminal_growth_rate in
    let fv = (book_value +. excess_pv) /. shares in
    { param_value = g *. 100.0; fair_value = fv }
  ) in

  { roe; cost_of_equity; growth }

let write_bank_sensitivity_csv ~output_dir ~ticker ~results ~market_price =
  let sensitivity_dir = Filename.concat output_dir "sensitivity" in
  let data_dir = Filename.concat sensitivity_dir "data" in
  (try Unix.mkdir sensitivity_dir 0o755 with Unix.Unix_error (Unix.EEXIST, _, _) -> ());
  (try Unix.mkdir data_dir 0o755 with Unix.Unix_error (Unix.EEXIST, _, _) -> ());

  let write_csv filename header points =
    let filepath = Filename.concat data_dir (Printf.sprintf "%s_%s.csv" filename ticker) in
    let oc = open_out filepath in
    Printf.fprintf oc "%s,fair_value,market_price\n" header;
    List.iter (fun pt ->
      Printf.fprintf oc "%.2f,%.2f,%.2f\n" pt.param_value pt.fair_value market_price
    ) points;
    close_out oc;
    Printf.printf "Written: %s\n" filepath
  in

  write_csv "sensitivity_bank_roe" "roe_pct" results.roe;
  write_csv "sensitivity_bank_coe" "cost_of_equity_pct" results.cost_of_equity;
  write_csv "sensitivity_bank_growth" "growth_rate_pct" results.growth

(* --- Insurance sensitivity --- *)

let run_insurance_sensitivity ~(financial : Types.financial_data)
    ~(market : Types.market_data) ~risk_free_rate ~equity_risk_premium
    ~terminal_growth_rate ~projection_years =

  let shares = market.shares_outstanding in
  let book_value = financial.book_value_equity in
  let base_coe = Insurance.calculate_insurance_cost_of_equity
    ~risk_free_rate ~equity_risk_premium ~market in
  let metrics = Insurance.calculate_insurance_metrics ~financial ~market in

  (* 1. Combined ratio sensitivity: 85% to 110% in 1% steps *)
  Printf.printf "Running insurance combined ratio sensitivity...\n";
  let combined_ratio = List.init 26 (fun i ->
    let cr = 0.85 +. (float_of_int i) *. 0.01 in
    let uw_value = Insurance.calculate_underwriting_value
      ~premiums:financial.premiums_earned ~combined_ratio:cr
      ~cost_of_equity:base_coe ~growth_rate:0.03
      ~projection_years ~terminal_growth:terminal_growth_rate in
    let float_value = Insurance.calculate_float_value
      ~float_amount:financial.float_amount
      ~investment_yield:metrics.investment_yield ~combined_ratio:cr
      ~cost_of_equity:base_coe ~projection_years
      ~terminal_growth:terminal_growth_rate in
    let fv = (book_value +. uw_value +. float_value) /. shares in
    { param_value = cr *. 100.0; fair_value = fv }
  ) in

  (* 2. Investment yield sensitivity: 1% to 6% in 0.25% steps *)
  Printf.printf "Running insurance investment yield sensitivity...\n";
  let investment_yield = List.init 21 (fun i ->
    let yield_val = 0.01 +. (float_of_int i) *. 0.0025 in
    let uw_value = Insurance.calculate_underwriting_value
      ~premiums:financial.premiums_earned ~combined_ratio:metrics.combined_ratio
      ~cost_of_equity:base_coe ~growth_rate:0.03
      ~projection_years ~terminal_growth:terminal_growth_rate in
    let float_value = Insurance.calculate_float_value
      ~float_amount:financial.float_amount
      ~investment_yield:yield_val ~combined_ratio:metrics.combined_ratio
      ~cost_of_equity:base_coe ~projection_years
      ~terminal_growth:terminal_growth_rate in
    let fv = (book_value +. uw_value +. float_value) /. shares in
    { param_value = yield_val *. 100.0; fair_value = fv }
  ) in

  (* 3. Cost of equity sensitivity: 6% to 12% in 0.5% steps *)
  Printf.printf "Running insurance cost of equity sensitivity...\n";
  let ins_cost_of_equity = List.init 13 (fun i ->
    let coe_val = 0.06 +. (float_of_int i) *. 0.005 in
    let uw_value = Insurance.calculate_underwriting_value
      ~premiums:financial.premiums_earned ~combined_ratio:metrics.combined_ratio
      ~cost_of_equity:coe_val ~growth_rate:0.03
      ~projection_years ~terminal_growth:terminal_growth_rate in
    let float_value = Insurance.calculate_float_value
      ~float_amount:financial.float_amount
      ~investment_yield:metrics.investment_yield ~combined_ratio:metrics.combined_ratio
      ~cost_of_equity:coe_val ~projection_years
      ~terminal_growth:terminal_growth_rate in
    let fv = (book_value +. uw_value +. float_value) /. shares in
    { param_value = coe_val *. 100.0; fair_value = fv }
  ) in

  { combined_ratio; investment_yield; ins_cost_of_equity }

let write_insurance_sensitivity_csv ~output_dir ~ticker ~results ~market_price =
  let sensitivity_dir = Filename.concat output_dir "sensitivity" in
  let data_dir = Filename.concat sensitivity_dir "data" in
  (try Unix.mkdir sensitivity_dir 0o755 with Unix.Unix_error (Unix.EEXIST, _, _) -> ());
  (try Unix.mkdir data_dir 0o755 with Unix.Unix_error (Unix.EEXIST, _, _) -> ());

  let write_csv filename header points =
    let filepath = Filename.concat data_dir (Printf.sprintf "%s_%s.csv" filename ticker) in
    let oc = open_out filepath in
    Printf.fprintf oc "%s,fair_value,market_price\n" header;
    List.iter (fun pt ->
      Printf.fprintf oc "%.2f,%.2f,%.2f\n" pt.param_value pt.fair_value market_price
    ) points;
    close_out oc;
    Printf.printf "Written: %s\n" filepath
  in

  write_csv "sensitivity_insurance_cr" "combined_ratio_pct" results.combined_ratio;
  write_csv "sensitivity_insurance_yield" "investment_yield_pct" results.investment_yield;
  write_csv "sensitivity_insurance_coe" "cost_of_equity_pct" results.ins_cost_of_equity

(* --- Oil & Gas sensitivity --- *)

let run_oil_gas_sensitivity ~(financial : Types.financial_data)
    ~(market : Types.market_data) ~risk_free_rate ~equity_risk_premium
    ~tax_rate ~oil_price ~gas_price =

  let shares = market.shares_outstanding in
  let debt = market.mvb in

  (* Helper: calculate blended fair value = (NAV + PV10) / 2 *)
  let calc_fv ~op ~gp ~discount =
    let reserve_val = Oil_gas.calculate_reserve_value
      ~proven_reserves:financial.proven_reserves
      ~production_boe_day:financial.production_boe_day
      ~oil_pct:financial.oil_pct ~lifting_cost:financial.lifting_cost
      ~oil_price:op ~gas_price:gp ~discount_rate:discount ~tax_rate in
    let pv10 = Oil_gas.calculate_pv10
      ~proven_reserves:financial.proven_reserves
      ~production_boe_day:financial.production_boe_day
      ~oil_pct:financial.oil_pct ~lifting_cost:financial.lifting_cost
      ~oil_price:op ~gas_price:gp ~tax_rate in
    let nav_ps = (reserve_val -. debt) /. shares in
    let pv10_ps = (pv10 -. debt) /. shares in
    (nav_ps +. pv10_ps) /. 2.0
  in

  let base_discount = Oil_gas.calculate_oil_gas_cost_of_capital
    ~risk_free_rate ~equity_risk_premium ~market ~oil_price in

  (* 1. Oil price sensitivity: $40 to $120 in $5 steps *)
  Printf.printf "Running oil price sensitivity...\n";
  let oil_price_pts = List.init 17 (fun i ->
    let op = 40.0 +. (float_of_int i) *. 5.0 in
    let fv = calc_fv ~op ~gp:gas_price ~discount:base_discount in
    { param_value = op; fair_value = fv }
  ) in

  (* 2. Lifting cost sensitivity: $5 to $25 in $1 steps *)
  Printf.printf "Running lifting cost sensitivity...\n";
  let lifting_cost_pts = List.init 21 (fun i ->
    let lc = 5.0 +. (float_of_int i) *. 1.0 in
    (* Temporarily override lifting cost *)
    let reserve_val = Oil_gas.calculate_reserve_value
      ~proven_reserves:financial.proven_reserves
      ~production_boe_day:financial.production_boe_day
      ~oil_pct:financial.oil_pct ~lifting_cost:lc
      ~oil_price ~gas_price ~discount_rate:base_discount ~tax_rate in
    let pv10 = Oil_gas.calculate_pv10
      ~proven_reserves:financial.proven_reserves
      ~production_boe_day:financial.production_boe_day
      ~oil_pct:financial.oil_pct ~lifting_cost:lc
      ~oil_price ~gas_price ~tax_rate in
    let nav_ps = (reserve_val -. debt) /. shares in
    let pv10_ps = (pv10 -. debt) /. shares in
    let fv = (nav_ps +. pv10_ps) /. 2.0 in
    { param_value = lc; fair_value = fv }
  ) in

  (* 3. Discount rate sensitivity: 6% to 14% in 0.5% steps *)
  Printf.printf "Running O&G discount rate sensitivity...\n";
  let og_discount_rate = List.init 17 (fun i ->
    let dr = 0.06 +. (float_of_int i) *. 0.005 in
    let fv = calc_fv ~op:oil_price ~gp:gas_price ~discount:dr in
    { param_value = dr *. 100.0; fair_value = fv }
  ) in

  { oil_price = oil_price_pts; lifting_cost = lifting_cost_pts; og_discount_rate }

let write_oil_gas_sensitivity_csv ~output_dir ~ticker ~results ~market_price =
  let sensitivity_dir = Filename.concat output_dir "sensitivity" in
  let data_dir = Filename.concat sensitivity_dir "data" in
  (try Unix.mkdir sensitivity_dir 0o755 with Unix.Unix_error (Unix.EEXIST, _, _) -> ());
  (try Unix.mkdir data_dir 0o755 with Unix.Unix_error (Unix.EEXIST, _, _) -> ());

  let write_csv filename header points =
    let filepath = Filename.concat data_dir (Printf.sprintf "%s_%s.csv" filename ticker) in
    let oc = open_out filepath in
    Printf.fprintf oc "%s,fair_value,market_price\n" header;
    List.iter (fun pt ->
      Printf.fprintf oc "%.2f,%.2f,%.2f\n" pt.param_value pt.fair_value market_price
    ) points;
    close_out oc;
    Printf.printf "Written: %s\n" filepath
  in

  write_csv "sensitivity_oilgas_price" "oil_price_usd" results.oil_price;
  write_csv "sensitivity_oilgas_lifting" "lifting_cost_usd" results.lifting_cost;
  write_csv "sensitivity_oilgas_discount" "discount_rate_pct" results.og_discount_rate
