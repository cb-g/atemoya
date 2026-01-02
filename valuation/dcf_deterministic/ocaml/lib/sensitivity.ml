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

    (* For FCFF, we need to adjust WACC proportionally
       If CE changes from base to 'discount', scale WACC by same factor *)
    let wacc_scale = discount /. cost_of_capital.Types.ce in
    let modified_wacc = cost_of_capital.wacc *. wacc_scale in

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
