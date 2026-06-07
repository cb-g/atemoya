(** Cross-sectional value/quality ranking over a universe panel.

    Per factor: winsorize globally (near-no-op for ranks, since rank is monotone —
    it just protects the composite mean from a pathological tail), then percentile-
    rank WITHIN sector (pandas "average" method); sectors with fewer than
    [thin_sector_threshold] names (with that factor) are ranked against the global
    pool instead. A pillar's composite = mean of its sector-allowed, present factor
    percentiles, required >= half present, else None (never imputed). value_pct and
    quality_pct are emitted SEPARATELY; combined is their mean. *)

open Types

let mean = function
  | [] -> None
  | xs -> Some (List.fold_left ( +. ) 0. xs /. float_of_int (List.length xs))

(* percentile of v within peers (which includes v), pandas rank(pct=True, average). *)
let pct_among peers v =
  let n = List.length peers in
  if n = 0 then None
  else
    let less = List.fold_left (fun a x -> if x < v then a + 1 else a) 0 peers in
    let equal = List.fold_left (fun a x -> if x = v then a + 1 else a) 0 peers in
    let rank = float_of_int less +. (float_of_int (equal + 1)) /. 2. in
    Some (rank /. float_of_int n)

let winsor_bounds vals =
  let arr = Array.of_list (List.sort compare vals) in
  let n = Array.length arr in
  if n = 0 then (neg_infinity, infinity)
  else
    let idx f = max 0 (min (n - 1) (int_of_float (f *. float_of_int (n - 1)))) in
    (arr.(idx 0.01), arr.(idx 0.99))

(* sector-relative signal: HIGH value_pct = cheap (value factors are yields). *)
let signal_of_value = function
  | None -> "N/A"
  | Some p ->
    if p >= 75. then "DeepValue"
    else if p >= 60. then "Undervalued"
    else if p >= 40. then "FairValue"
    else if p >= 25. then "Overvalued"
    else "Expensive"

let rank (rows : panel_row list) : ranked list =
  (* per row: (row, allowed-and-present value factors, quality factors, allowed lists) *)
  let per_row =
    List.map
      (fun (r : panel_row) ->
        let av = Sector_policy.value_factors_for r.sector in
        let aq = Sector_policy.quality_factors_for r.sector in
        let keep allowed fs = List.filter (fun (n, _) -> List.mem n allowed) fs in
        let vf = keep av (Factors.value_factors r) in
        let qf = keep aq (Factors.quality_factors r) in
        (r, vf, qf, av, aq))
      rows
  in
  let pct_table : (string * string, float) Hashtbl.t = Hashtbl.create 4096 in
  let all_factors = Sector_policy.all_value @ Sector_policy.all_quality in
  List.iter
    (fun fac ->
      let entries =
        List.filter_map
          (fun ((r : panel_row), vf, qf, _, _) ->
            match List.assoc_opt fac (vf @ qf) with
            | Some v -> Some (r.ticker, r.sector, v)
            | None -> None)
          per_row
      in
      if entries <> [] then begin
        let lo, hi = winsor_bounds (List.map (fun (_, _, v) -> v) entries) in
        let clip v = Float.max lo (Float.min hi v) in
        let entries = List.map (fun (t, s, v) -> (t, s, clip v)) entries in
        let sector_count s =
          List.length (List.filter (fun (_, s2, _) -> s2 = s) entries)
        in
        List.iter
          (fun (t, s, v) ->
            let peers =
              if sector_count s >= Sector_policy.thin_sector_threshold then
                List.filter_map (fun (_, s2, v2) -> if s2 = s then Some v2 else None) entries
              else List.map (fun (_, _, v2) -> v2) entries
            in
            match pct_among peers v with
            | Some p -> Hashtbl.replace pct_table (t, fac) p
            | None -> ())
          entries
      end)
    all_factors;
  List.map
    (fun ((r : panel_row), _, _, av, aq) ->
      let pcts allowed =
        List.filter_map (fun fac -> Hashtbl.find_opt pct_table (r.ticker, fac)) allowed
      in
      let vp = pcts av and qp = pcts aq in
      let need allowed = (List.length allowed + 1) / 2 in
      let comp present allowed =
        if allowed <> [] && List.length present >= need allowed then
          Option.map (fun m -> m *. 100.) (mean present)
        else None
      in
      let value_pct = comp vp av and quality_pct = comp qp aq in
      let combined_pct =
        match value_pct, quality_pct with
        | Some a, Some b -> Some ((a +. b) /. 2.)
        | _ -> None
      in
      { ticker = r.ticker;
        sector = r.sector;
        value_pct;
        quality_pct;
        combined_pct;
        n_value_used = List.length vp;
        n_value_allowed = List.length av;
        n_quality_used = List.length qp;
        n_quality_allowed = List.length aq;
        signal = signal_of_value value_pct })
    per_row
