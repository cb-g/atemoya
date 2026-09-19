open Boundary_t

let note =
  "this anchor moves by the swing for the declared step, everything else held; the steps are readability steps, \
   not standard deviations, and nothing here is a probability"

let side ~guard f x = match guard x with Some reason -> { value = None; reason = Some reason } | None -> { value = Some (f x); reason = None }

(* One entry: the input at recorded - step and recorded + step under [guard]. *)
let entry ~input ~recorded ~step ~step_kind ~guard ~fair_value f =
  let delta = match step_kind with "relative" -> Float.abs recorded *. step | _ -> step in
  let down = side ~guard f (recorded -. delta) and up = side ~guard f (recorded +. delta) in
  let swing =
    match (down.value, up.value) with
    | Some d, Some u when fair_value <> 0. -> Some (Float.abs (u -. d) /. Float.abs fair_value)
    | _ -> None
  in
  { input; recorded; step; step_kind; down; up; swing }

let positive name x = if x <= 0. then Some (Printf.sprintf "%s %.4g is not positive" name x) else None
let above_terminal name ~terminal rate =
  if rate <= terminal then Some (Printf.sprintf "%s %.4f does not exceed terminal growth %.4f" name rate terminal) else None
let terminal_below name ~rate terminal =
  if terminal >= rate then Some (Printf.sprintf "terminal growth %.4f reaches %s %.4f" terminal name rate) else None

let dcf_entries (s : Reference_t.sensitivity_steps) (i : inputs) ~base_name ~fair_value =
  let lambda = i.mean_reversion_lambda.value and terminal = i.terminal_growth_rate.value in
  let e = entry ~fair_value in
  [
    e ~input:"g0" ~recorded:i.g0 ~step:s.growth ~step_kind:"absolute" ~guard:(fun _ -> None)
      (fun g0 -> Implied.dcf_fair_value i ~g0 ~lambda);
    e ~input:"mean_reversion_lambda" ~recorded:lambda ~step:s.lambda ~step_kind:"absolute" ~guard:(positive "lambda")
      (fun lambda -> Implied.dcf_fair_value i ~g0:i.g0 ~lambda);
    e ~input:"terminal_growth_rate" ~recorded:terminal ~step:s.terminal_growth ~step_kind:"absolute"
      ~guard:(terminal_below "wacc" ~rate:i.wacc)
      (fun terminal_growth_rate -> Implied.dcf_fair_value i ~terminal_growth_rate ~g0:i.g0 ~lambda);
    e ~input:"wacc" ~recorded:i.wacc ~step:s.discount_rate ~step_kind:"absolute" ~guard:(above_terminal "wacc" ~terminal)
      (fun wacc -> Implied.dcf_fair_value i ~wacc ~g0:i.g0 ~lambda);
    e ~input:base_name ~recorded:i.fcff ~step:s.base_fraction ~step_kind:"relative" ~guard:(positive base_name)
      (fun fcff -> Implied.dcf_fair_value i ~fcff ~g0:i.g0 ~lambda);
  ]

let residual_income_entries (s : Reference_t.sensitivity_steps) (i : residual_income_inputs) ~fair_value =
  let lambda = i.mean_reversion_lambda.value in
  let e = entry ~fair_value in
  [
    e ~input:"roe_0" ~recorded:i.roe_0 ~step:s.growth ~step_kind:"absolute" ~guard:(fun _ -> None)
      (fun roe_0 -> Implied.residual_income_fair_value i ~roe_0 ~lambda);
    e ~input:"mean_reversion_lambda" ~recorded:lambda ~step:s.lambda ~step_kind:"absolute" ~guard:(positive "lambda")
      (fun lambda -> Implied.residual_income_fair_value i ~roe_0:i.roe_0 ~lambda);
    e ~input:"cost_of_equity" ~recorded:i.cost_of_equity ~step:s.discount_rate ~step_kind:"absolute"
      ~guard:(positive "cost of equity")
      (fun cost_of_equity -> Implied.residual_income_fair_value i ~cost_of_equity ~roe_0:i.roe_0 ~lambda);
    e ~input:"book_equity" ~recorded:i.book_equity ~step:s.base_fraction ~step_kind:"relative" ~guard:(positive "book equity")
      (fun book_equity -> Implied.residual_income_fair_value i ~book_equity ~roe_0:i.roe_0 ~lambda);
  ]

let reit_entries (s : Reference_t.sensitivity_steps) (i : reit_inputs) ~fair_value =
  let lambda = i.mean_reversion_lambda.value and terminal = i.terminal_growth_rate.value in
  let e = entry ~fair_value in
  [
    e ~input:"g0" ~recorded:i.g0 ~step:s.growth ~step_kind:"absolute" ~guard:(fun _ -> None)
      (fun g0 -> Implied.reit_fair_value i ~g0 ~lambda);
    e ~input:"mean_reversion_lambda" ~recorded:lambda ~step:s.lambda ~step_kind:"absolute" ~guard:(positive "lambda")
      (fun lambda -> Implied.reit_fair_value i ~g0:i.g0 ~lambda);
    e ~input:"terminal_growth_rate" ~recorded:terminal ~step:s.terminal_growth ~step_kind:"absolute"
      ~guard:(terminal_below "cost of equity" ~rate:i.cost_of_equity)
      (fun terminal_growth_rate -> Implied.reit_fair_value i ~terminal_growth_rate ~g0:i.g0 ~lambda);
    e ~input:"cost_of_equity" ~recorded:i.cost_of_equity ~step:s.discount_rate ~step_kind:"absolute"
      ~guard:(above_terminal "cost of equity" ~terminal)
      (fun cost_of_equity -> Implied.reit_fair_value i ~cost_of_equity ~g0:i.g0 ~lambda);
    e ~input:"dividend_per_share" ~recorded:i.dividend_per_share ~step:s.base_fraction ~step_kind:"relative"
      ~guard:(positive "dividend per share")
      (fun dividend_per_share -> Implied.reit_fair_value i ~dividend_per_share ~g0:i.g0 ~lambda);
  ]

let of_inputs (s : Reference_t.sensitivity_steps) (m : model_inputs) ~fair_value =
  let entries =
    match m with
    | `Dcf i -> dcf_entries s i ~base_name:"fcff" ~fair_value
    | `Dcf_midcycle mc -> dcf_entries s mc.dcf ~base_name:"fcff_mid" ~fair_value
    | `Residual_income i | `Residual_income_insurer { core = i; _ } -> residual_income_entries s i ~fair_value
    | `Reit_ffo_dividend i -> reit_entries s i ~fair_value
  in
  let ranked =
    List.filter_map (fun (e : sensitivity_entry) -> Option.map (fun w -> (e.input, w)) e.swing) entries
    |> List.stable_sort (fun (_, a) (_, b) -> compare b a)
    |> List.map fst
  in
  {
    fair_value;
    steps_source = s.source;
    steps_as_of = s.as_of;
    entries;
    ranking = ranked;
    binding_input = (match ranked with x :: _ -> Some x | [] -> None);
    note;
  }
