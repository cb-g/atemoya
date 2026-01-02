(** Multi-year cash flow projection *)

let project_fcfe ~fcfe_0 ~growth_rate ~years =
  (* Project FCFE_t = FCFE_0 × (1 + g)^t for t = 1..years *)
  Array.init years (fun i ->
    let t = float_of_int (i + 1) in
    fcfe_0 *. ((1.0 +. growth_rate) ** t)
  )

let project_fcff ~fcff_0 ~growth_rate ~years =
  (* Project FCFF_t = FCFF_0 × (1 + g)^t for t = 1..years *)
  Array.init years (fun i ->
    let t = float_of_int (i + 1) in
    fcff_0 *. ((1.0 +. growth_rate) ** t)
  )

let create_projection ~financial_data ~market_data ~tax_rate ~params =
  let open Types in

  (* Calculate current year cash flows (year 0) *)
  let fcfe_0 = Cash_flow.calculate_fcfe ~financial_data ~market_data in
  let fcff_0 = Cash_flow.calculate_fcff ~financial_data ~tax_rate in

  (* Calculate growth rates with clamping *)
  let growth_rate_fcfe, growth_clamped_fcfe =
    Growth.calculate_fcfe_growth_rate ~financial_data ~fcfe:fcfe_0 ~params
  in

  let growth_rate_fcff, growth_clamped_fcff =
    Growth.calculate_fcff_growth_rate ~financial_data ~tax_rate ~params
  in

  (* Project cash flows over h years *)
  let fcfe = project_fcfe
    ~fcfe_0
    ~growth_rate:growth_rate_fcfe
    ~years:params.projection_years
  in

  let fcff = project_fcff
    ~fcff_0
    ~growth_rate:growth_rate_fcff
    ~years:params.projection_years
  in

  {
    fcfe;
    fcff;
    growth_rate_fcfe;
    growth_rate_fcff;
    growth_clamped_fcfe;
    growth_clamped_fcff;
  }
