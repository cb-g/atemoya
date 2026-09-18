open Boundary_t

type signature = {
  indicated : entity_class option;
  fiscal_period_end : string option;
  total_revenue : float option;
  net_interest_income : float option;
  nii_ratio : float option;
  threshold : parameter;
  premiums_earned : float option;
  premiums_earned_row : string option;
}

type verdict = Proceed of class_check | Refuse of string * class_check

let signature ~(threshold : parameter) (fin : financials) =
  let period = Period.latest fin in
  let field f = Option.bind period f in
  let total_revenue = field (fun p -> p.total_revenue) in
  let net_interest_income = field (fun p -> p.net_interest_income) in
  let premiums_earned = field (fun p -> p.premiums_earned) in
  let premiums_earned_row = field (fun p -> p.premiums_earned_row) in
  let nii_ratio =
    match (net_interest_income, total_revenue) with
    | Some nii, Some revenue when revenue > 0. -> Some (nii /. revenue)
    | _ -> None
  in
  let bank = match nii_ratio with Some r -> r >= threshold.value | None -> false in
  let insurer = match premiums_earned with Some p -> p > 0. | None -> false in
  let indicated =
    if bank then Some `Bank else if insurer then Some `Insurer else None
  in
  {
    indicated;
    fiscal_period_end = Option.map (fun (p : fiscal_period) -> p.period_end) period;
    total_revenue;
    net_interest_income;
    nii_ratio;
    threshold;
    premiums_earned;
    premiums_earned_row;
  }

(* How the statements made their case, for the reason text. *)
let describe s =
  match (s.indicated, s.nii_ratio, s.premiums_earned, s.premiums_earned_row) with
  | Some `Bank, Some r, _, _ -> Printf.sprintf "NII/revenue %.2f" r
  | Some `Insurer, _, Some p, Some row -> Printf.sprintf "%s %g" row p
  | _ -> "signature"

let evidence ~declared s outcome : class_check =
  {
    declared;
    indicated = s.indicated;
    outcome;
    fiscal_period_end = s.fiscal_period_end;
    total_revenue = s.total_revenue;
    net_interest_income = s.net_interest_income;
    nii_ratio = s.nii_ratio;
    bank_nii_ratio_threshold = s.threshold;
    premiums_earned = s.premiums_earned;
    premiums_earned_row = s.premiums_earned_row;
  }

let check ~declared s =
  let name = Admissibility.class_name in
  match (declared, s.indicated) with
  | None, None -> Refuse ("entity_class not declared", evidence ~declared s `Undeclared)
  | None, Some c ->
      Refuse
        ( Printf.sprintf "entity_class not declared; statements indicate %s (%s)"
            (name c) (describe s),
          evidence ~declared s `Undeclared )
  | Some `OperatingCompany, Some c ->
      Refuse
        ( Printf.sprintf
            "class disagreement: declared OperatingCompany, statements indicate %s (%s)"
            (name c) (describe s),
          evidence ~declared s `Disagreement )
  | Some d, Some c when c = d -> Proceed (evidence ~declared s `Consistent)
  | Some _, Some _ -> Proceed (evidence ~declared s `Signature_differs)
  | Some (`Bank | `Insurer), None -> Proceed (evidence ~declared s `Signature_absent)
  | Some _, None -> Proceed (evidence ~declared s `Consistent)
