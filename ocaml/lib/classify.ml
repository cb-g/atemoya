open Boundary_t

type outcome = Classified of model | Unresolved of string

let model_name = function
  | `Generic -> "Generic"
  | `Bank -> "Bank"
  | `Insurer -> "Insurer"

let contains haystack needle =
  let n = String.length needle and h = String.length haystack in
  let rec go i = i + n <= h && (String.sub haystack i n = needle || go (i + 1)) in
  go 0

let hint_of_industry = function
  | None -> None
  | Some industry ->
      let s = String.lowercase_ascii industry in
      if contains s "bank" then Some `Bank
      else if contains s "insurance" then Some `Insurer
      else None

let classify ~(threshold : parameter) (fin : financials) =
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
  let bank =
    match nii_ratio with Some r -> r >= threshold.value | None -> false
  in
  let insurer =
    match premiums_earned with Some p -> p > 0. | None -> false
  in
  let info_hint =
    if bank || insurer then None else hint_of_industry fin.industry
  in
  let outcome =
    if bank then Classified `Bank
    else if insurer then Classified `Insurer
    else
      match info_hint with
      | Some hinted ->
          Unresolved
            (Printf.sprintf
               "classification unresolved: .info suggests %s, no statement \
                signature"
               (model_name hinted))
      | None -> Classified `Generic
  in
  ( outcome,
    {
      fiscal_period_end = Option.map (fun (p : fiscal_period) -> p.period_end) period;
      total_revenue;
      net_interest_income;
      nii_ratio;
      bank_nii_ratio_threshold = threshold;
      premiums_earned;
      premiums_earned_row;
      info_hint;
    } )
