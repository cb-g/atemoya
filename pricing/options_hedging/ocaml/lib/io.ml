(* I/O Operations - CSV and JSON *)

open Types

(* Parse option type from string *)
let parse_option_type s =
  match String.lowercase_ascii (String.trim s) with
  | "call" -> Call
  | "put" -> Put
  | _ -> failwith (Printf.sprintf "Invalid option type: %s" s)

(* Parse exercise style from string *)
let parse_exercise_style s =
  match String.lowercase_ascii (String.trim s) with
  | "european" -> European
  | "american" -> American
  | _ -> failwith (Printf.sprintf "Invalid exercise style: %s" s)

(* Read option chain CSV
   Expected columns: ticker, option_type, strike, expiry, bid, ask, implied_volatility
*)
let read_option_chain ~filename =
  let csv = Csv.load filename in

  (* Skip header row *)
  let data_rows = match csv with
    | [] -> []
    | _ :: rows -> rows
  in

  let points = List.filter_map (fun row ->
    try
      match row with
      | _ticker :: _option_type_str :: strike_str :: expiry_str :: bid_str :: ask_str :: iv_str :: _ ->
          let strike = float_of_string strike_str in
          let expiry = float_of_string expiry_str in
          let implied_vol = float_of_string iv_str in

          (* Parse optional bid/ask *)
          let bid = try Some (float_of_string bid_str) with Failure _ -> None in
          let ask = try Some (float_of_string ask_str) with Failure _ -> None in

          (* Calculate market price as midpoint if available *)
          let market_price = match (bid, ask) with
            | (Some b, Some a) -> Some ((b +. a) /. 2.0)
            | _ -> None
          in

          Some {
            strike;
            expiry;
            implied_vol;
            bid;
            ask;
            market_price;
          }
      | _ -> None
    with Failure _ -> None
  ) data_rows in

  Array.of_list points

(* Read underlying data CSV
   Expected columns: ticker, spot_price, dividend_yield
*)
let read_underlying_data ~filename =
  let csv = Csv.load filename in

  match csv with
  | _ :: [ticker :: spot_str :: div_str :: _] ->
      {
        ticker;
        spot_price = float_of_string spot_str;
        dividend_yield = float_of_string div_str;
      }
  | _ -> failwith "Invalid underlying data CSV format"

(* Read volatility surface from JSON *)
let read_vol_surface ~filename =
  let json = Yojson.Safe.from_file filename in

  let open Yojson.Safe.Util in

  let surface_type = json |> member "type" |> to_string in

  match surface_type with
  | "SVI" ->
      let params_json = json |> member "params" |> to_list in
      let params = List.map (fun p ->
        {
          expiry = p |> member "expiry" |> to_float;
          a = p |> member "a" |> to_float;
          b = p |> member "b" |> to_float;
          rho = p |> member "rho" |> to_float;
          m = p |> member "m" |> to_float;
          sigma = p |> member "sigma" |> to_float;
        }
      ) params_json in
      SVI (Array.of_list params)

  | "SABR" ->
      let params_json = json |> member "params" |> to_list in
      let params = List.map (fun p ->
        {
          expiry = p |> member "expiry" |> to_float;
          alpha = p |> member "alpha" |> to_float;
          beta = p |> member "beta" |> to_float;
          rho = p |> member "rho" |> to_float;
          nu = p |> member "nu" |> to_float;
        }
      ) params_json in
      SABR (Array.of_list params)

  | _ -> failwith (Printf.sprintf "Unknown surface type: %s" surface_type)

(* Write volatility surface to JSON *)
let write_vol_surface vol_surface ~filename =
  let open Yojson.Safe in

  let json = match vol_surface with
  | SVI params ->
      `Assoc [
        ("type", `String "SVI");
        ("params", `List (
          Array.to_list (Array.map (fun (p : svi_params) ->
            `Assoc [
              ("expiry", `Float p.expiry);
              ("a", `Float p.a);
              ("b", `Float p.b);
              ("rho", `Float p.rho);
              ("m", `Float p.m);
              ("sigma", `Float p.sigma);
            ]
          ) params)
        ))
      ]
  | SABR params ->
      `Assoc [
        ("type", `String "SABR");
        ("params", `List (
          Array.to_list (Array.map (fun (p : sabr_params) ->
            `Assoc [
              ("expiry", `Float p.expiry);
              ("alpha", `Float p.alpha);
              ("beta", `Float p.beta);
              ("rho", `Float p.rho);
              ("nu", `Float p.nu);
            ]
          ) params)
        ))
      ]
  in

  to_file filename json

(* Helper: strategy type to string *)
let strategy_type_to_string = function
  | ProtectivePut { put_strike } ->
      Printf.sprintf "ProtectivePut(K=%.2f)" put_strike
  | Collar { put_strike; call_strike } ->
      Printf.sprintf "Collar(Put=%.2f,Call=%.2f)" put_strike call_strike
  | VerticalSpread { long_strike; short_strike } ->
      Printf.sprintf "VerticalSpread(Long=%.2f,Short=%.2f)" long_strike short_strike
  | CoveredCall { call_strike } ->
      Printf.sprintf "CoveredCall(K=%.2f)" call_strike

(* Write Pareto frontier to CSV *)
let write_pareto_csv ~filename ~frontier =
  let header = ["strategy"; "expiry"; "contracts"; "cost"; "protection_level"; "delta"; "gamma"; "vega"; "theta"; "rho"] in

  let rows = Array.to_list (Array.map (fun point ->
    let s = point.strategy in
    [
      strategy_type_to_string s.strategy_type;
      Printf.sprintf "%.4f" s.expiry;
      string_of_int s.contracts;
      Printf.sprintf "%.2f" s.cost;
      Printf.sprintf "%.2f" s.protection_level;
      Printf.sprintf "%.6f" s.greeks.delta;
      Printf.sprintf "%.6f" s.greeks.gamma;
      Printf.sprintf "%.6f" s.greeks.vega;
      Printf.sprintf "%.6f" s.greeks.theta;
      Printf.sprintf "%.6f" s.greeks.rho;
    ]
  ) frontier) in

  Csv.save filename (header :: rows)

(* Write single strategy to CSV *)
let write_strategy_csv ~filename ~strategy =
  let header = ["field"; "value"] in

  let rows = [
    ["strategy_type"; strategy_type_to_string strategy.strategy_type];
    ["expiry"; Printf.sprintf "%.4f" strategy.expiry];
    ["contracts"; string_of_int strategy.contracts];
    ["cost"; Printf.sprintf "%.2f" strategy.cost];
    ["protection_level"; Printf.sprintf "%.2f" strategy.protection_level];
    ["delta"; Printf.sprintf "%.6f" strategy.greeks.delta];
    ["gamma"; Printf.sprintf "%.6f" strategy.greeks.gamma];
    ["vega"; Printf.sprintf "%.6f" strategy.greeks.vega];
    ["theta"; Printf.sprintf "%.6f" strategy.greeks.theta];
    ["rho"; Printf.sprintf "%.6f" strategy.greeks.rho];
  ] in

  Csv.save filename (header :: rows)

(* Write Greeks summary for multiple strategies *)
let write_greeks_csv ~filename ~strategies =
  let header = ["strategy"; "delta"; "gamma"; "vega"; "theta"; "rho"] in

  let rows = List.map (fun strategy ->
    [
      strategy_type_to_string strategy.strategy_type;
      Printf.sprintf "%.6f" strategy.greeks.delta;
      Printf.sprintf "%.6f" strategy.greeks.gamma;
      Printf.sprintf "%.6f" strategy.greeks.vega;
      Printf.sprintf "%.6f" strategy.greeks.theta;
      Printf.sprintf "%.6f" strategy.greeks.rho;
    ]
  ) strategies in

  Csv.save filename (header :: rows)

(* Write optimization result to JSON *)
let write_optimization_result ~filename ~result =
  let open Yojson.Safe in

  (* Convert pareto frontier *)
  let frontier_json = `List (
    Array.to_list (Array.map (fun point ->
      let s = point.strategy in
      `Assoc [
        ("cost", `Float point.cost);
        ("protection_level", `Float point.protection_level);
        ("strategy", `Assoc [
          ("type", `String (strategy_type_to_string s.strategy_type));
          ("expiry", `Float s.expiry);
          ("contracts", `Int s.contracts);
          ("cost", `Float s.cost);
          ("protection_level", `Float s.protection_level);
          ("greeks", `Assoc [
            ("delta", `Float s.greeks.delta);
            ("gamma", `Float s.greeks.gamma);
            ("vega", `Float s.greeks.vega);
            ("theta", `Float s.greeks.theta);
            ("rho", `Float s.greeks.rho);
          ])
        ])
      ]
    ) result.pareto_frontier)
  ) in

  (* Convert recommended strategy *)
  let recommended_json = match result.recommended_strategy with
    | None -> `Null
    | Some s ->
        `Assoc [
          ("type", `String (strategy_type_to_string s.strategy_type));
          ("expiry", `Float s.expiry);
          ("contracts", `Int s.contracts);
          ("cost", `Float s.cost);
          ("protection_level", `Float s.protection_level);
          ("greeks", `Assoc [
            ("delta", `Float s.greeks.delta);
            ("gamma", `Float s.greeks.gamma);
            ("vega", `Float s.greeks.vega);
            ("theta", `Float s.greeks.theta);
            ("rho", `Float s.greeks.rho);
          ])
        ]
  in

  let json = `Assoc [
    ("pareto_frontier", frontier_json);
    ("recommended_strategy", recommended_json);
  ] in

  to_file filename json
