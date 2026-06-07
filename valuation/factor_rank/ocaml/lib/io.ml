(** Read the panel JSON (array of ticker records) and write ranked CSV. *)

open Types

let to_number = function
  | `Float f -> Some f
  | `Int i -> Some (float_of_int i)
  | _ -> None

(* A panel file is a JSON array; each element is an object with "ticker",
   "sector", and numeric fundamental fields (already trading-basis). Any numeric
   member other than the two strings is captured as a factor input. *)
let read_panel filename : panel_row list =
  let json = Yojson.Basic.from_file filename in
  let objs = Yojson.Basic.Util.to_list json in
  List.filter_map
    (fun obj ->
      match obj with
      | `Assoc kvs ->
        let ticker =
          match List.assoc_opt "ticker" kvs with Some (`String s) -> s | _ -> ""
        in
        let sector =
          match List.assoc_opt "sector" kvs with
          | Some (`String s) when String.trim s <> "" -> s
          | _ -> "Unknown"
        in
        if ticker = "" then None
        else
          let fields =
            List.filter_map
              (fun (k, v) ->
                if k = "ticker" || k = "sector" then None
                else
                  match to_number v with
                  | Some f when Float.is_finite f -> Some (k, f)
                  | _ -> None)
              kvs
          in
          Some { ticker; sector; fields }
      | _ -> None)
    objs

let fo = function Some x -> Printf.sprintf "%.2f" x | None -> ""

let write_csv filename (rows : ranked list) =
  let oc = open_out filename in
  output_string oc
    "ticker,sector,value_pct,quality_pct,combined_pct,signal,n_value_used,n_value_allowed,n_quality_used,n_quality_allowed\n";
  List.iter
    (fun r ->
      Printf.fprintf oc "%s,%s,%s,%s,%s,%s,%d,%d,%d,%d\n" r.ticker
        (String.map (fun c -> if c = ',' then ';' else c) r.sector)
        (fo r.value_pct) (fo r.quality_pct) (fo r.combined_pct) r.signal
        r.n_value_used r.n_value_allowed r.n_quality_used r.n_quality_allowed)
    rows;
  close_out oc
