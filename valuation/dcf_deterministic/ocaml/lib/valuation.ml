(** Present value calculations and terminal value *)

let calculate_terminal_value ~final_cash_flow ~terminal_growth_rate ~discount_rate =
  (* TV = CF_h × (1 + TGR) / (discount_rate - TGR) *)
  if discount_rate <= terminal_growth_rate then
    None  (* Invalid: would create infinite or negative terminal value *)
  else
    let numerator = final_cash_flow *. (1.0 +. terminal_growth_rate) in
    let denominator = discount_rate -. terminal_growth_rate in
    Some (numerator /. denominator)

let calculate_present_value ~cash_flows ~discount_rate ~terminal_growth_rate =
  let h = Array.length cash_flows in
  if h = 0 then
    Some 0.0  (* No cash flows to discount *)
  else
    (* Calculate present value of explicit forecast period *)
    let pv_explicit =
      Array.fold_left (fun (acc, t) cf ->
        let discount_factor = (1.0 +. discount_rate) ** (float_of_int t) in
        (acc +. (cf /. discount_factor), t + 1)
      ) (0.0, 1) cash_flows
      |> fst
    in

    (* Calculate terminal value and its present value *)
    let final_cf = cash_flows.(h - 1) in
    match calculate_terminal_value ~final_cash_flow:final_cf ~terminal_growth_rate ~discount_rate with
    | None -> None  (* Terminal value calculation failed *)
    | Some tv ->
        let discount_factor_terminal = (1.0 +. discount_rate) ** (float_of_int h) in
        let pv_terminal = tv /. discount_factor_terminal in
        Some (pv_explicit +. pv_terminal)

let calculate_pve ~projection ~cost_of_equity ~terminal_growth_rate =
  let open Types in
  calculate_present_value
    ~cash_flows:projection.fcfe
    ~discount_rate:cost_of_equity
    ~terminal_growth_rate

let calculate_pvf ~projection ~wacc ~terminal_growth_rate =
  let open Types in
  calculate_present_value
    ~cash_flows:projection.fcff
    ~discount_rate:wacc
    ~terminal_growth_rate
