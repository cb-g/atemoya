(** factor_rank ranker: read a universe panel JSON -> ranked CSV + terminal report.

    The panel JSON (array of trading-basis ticker records) is produced by
    python/fetch/fetch_panel.py. This same binary is invoked by the backtest, once
    per rebalance, so live and backtest rank through identical code. *)

open Factor_rank
open Types

let rec take n = function [] -> [] | _ when n <= 0 -> [] | x :: xs -> x :: take (n - 1) xs

let () =
  let panel = ref "" in
  let data_dir = ref "valuation/factor_rank/data" in
  let output_dir = ref "valuation/factor_rank/output" in
  let top = ref 15 in
  let spec =
    [ ("--panel", Arg.Set_string panel, "Panel JSON file (default: latest in --data)");
      ("--data", Arg.Set_string data_dir, "Data directory");
      ("--output", Arg.Set_string output_dir, "Output directory");
      ("--top", Arg.Set_int top, "Rows to print per ranking (default 15)") ]
  in
  Arg.parse spec (fun _ -> ()) "factor_rank: panel JSON -> ranked value/quality CSV";
  let panel_file =
    if !panel <> "" then !panel
    else
      let entries = try Sys.readdir !data_dir with _ -> [||] in
      let cands =
        Array.to_list entries
        |> List.filter (fun f ->
               String.length f > 13
               && String.sub f 0 13 = "factor_panel_"
               && Filename.check_suffix f ".json")
        |> List.sort (fun a b -> compare b a)
      in
      match cands with
      | f :: _ -> Filename.concat !data_dir f
      | [] -> prerr_endline "No panel file found (run fetch_panel.py first)"; exit 1
  in
  let rows = Io.read_panel panel_file in
  Printf.printf "panel: %s  (%d names)\n" panel_file (List.length rows);
  let ranked = Rank_engine.rank rows in
  (try Unix.mkdir !output_dir 0o755 with _ -> ());
  let t = Unix.localtime (Unix.time ()) in
  let date =
    Printf.sprintf "%04d-%02d-%02d" (t.Unix.tm_year + 1900) (t.Unix.tm_mon + 1) t.Unix.tm_mday
  in
  let out = Filename.concat !output_dir (Printf.sprintf "factor_ranks_%s.csv" date) in
  Io.write_csv out ranked;
  Printf.printf "wrote %s\n\n" out;
  let by f =
    List.sort
      (fun a b ->
        match f a, f b with
        | Some x, Some y -> compare y x
        | Some _, None -> -1
        | None, Some _ -> 1
        | None, None -> 0)
      ranked
  in
  let show title f =
    Printf.printf "=== %s ===\n" title;
    List.iter
      (fun r ->
        let sec = if String.length r.sector > 20 then String.sub r.sector 0 20 else r.sector in
        Printf.printf "  %-7s %-20s val=%6s qual=%6s comb=%6s  %s\n" r.ticker sec
          (Io.fo r.value_pct) (Io.fo r.quality_pct) (Io.fo r.combined_pct) r.signal)
      (take !top (by f));
    print_newline ()
  in
  show "Top by VALUE+QUALITY (combined)" (fun r -> r.combined_pct);
  show "Top by VALUE" (fun r -> r.value_pct);
  show "Top by QUALITY" (fun r -> r.quality_pct)
