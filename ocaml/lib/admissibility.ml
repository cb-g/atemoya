(* [class_name] is an exhaustive match: adding a constructor to the variant fails to
   compile here until it is named, which is the reminder to extend [all_classes] and the
   table. *)
let class_name : Boundary_t.entity_class -> string = function
  | `OperatingCompany -> "OperatingCompany"
  | `Bank -> "Bank"
  | `Insurer -> "Insurer"
  | `RegulatedUtility -> "RegulatedUtility"
  | `MerchantPower -> "MerchantPower"
  | `Reit -> "Reit"
  | `Miner -> "Miner"
  | `Royalty -> "Royalty"
  | `HighGrowthSoftware -> "HighGrowthSoftware"
  | `PreProfit -> "PreProfit"
  | `Wrapper -> "Wrapper"
  | `ConstructionStage -> "ConstructionStage"
  | `UnderBid -> "UnderBid"
  | `Ballast -> "Ballast"

let all_classes : Boundary_t.entity_class list =
  [
    `OperatingCompany;
    `Bank;
    `Insurer;
    `RegulatedUtility;
    `MerchantPower;
    `Reit;
    `Miner;
    `Royalty;
    `HighGrowthSoftware;
    `PreProfit;
    `Wrapper;
    `ConstructionStage;
    `UnderBid;
    `Ballast;
  ]

let class_of_string s =
  match Boundary_j.entity_class_of_string (Yojson.Safe.to_string (`String s)) with
  | c -> Some c
  | exception (Yojson.Json_error _ | Atdgen_runtime.Oj_run.Error _ | Failure _) -> None

let model_name : Boundary_t.model -> string = function
  | `Dcf -> "dcf"
  | `Residual_income -> "residual_income"
  | `Residual_income_insurer -> "residual_income_insurer"
  | `Reit_ffo_dividend -> "reit_ffo_dividend"

let model_of_string s =
  match Boundary_j.model_of_string (Yojson.Safe.to_string (`String s)) with
  | m -> Some m
  | exception (Yojson.Json_error _ | Atdgen_runtime.Oj_run.Error _ | Failure _) -> None

let routed (r : Reference_t.class_rule) =
  List.find_map model_of_string r.admissible_models

let rule (table : Reference_t.admissibility) cls =
  match List.assoc_opt (class_name cls) table.classes with
  | Some r -> Ok r
  | None ->
      Error
        (Printf.sprintf "no admissibility row for entity class %s in the reference table"
           (class_name cls))

let admits (r : Reference_t.class_rule) model =
  List.mem (model_name model) r.admissible_models
