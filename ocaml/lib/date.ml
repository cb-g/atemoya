let ( let* ) = Result.bind

(* Days since 1970-01-01 (Hinnant's civil-to-days algorithm). *)
let days_from_civil y m d =
  let y = if m <= 2 then y - 1 else y in
  let era = (if y >= 0 then y else y - 399) / 400 in
  let yoe = y - (era * 400) in
  let mp = (m + 9) mod 12 in
  let doy = ((153 * mp) + 2) / 5 + d - 1 in
  let doe = (yoe * 365) + (yoe / 4) - (yoe / 100) + doy in
  (era * 146097) + doe - 719468

let parse s =
  match Scanf.sscanf s "%4d-%2d-%2d%!" (fun y m d -> (y, m, d)) with
  | (_, m, d) as date when m >= 1 && m <= 12 && d >= 1 && d <= 31 -> Ok date
  | _ -> Error (Printf.sprintf "%S is not a calendar date" s)
  | exception (Scanf.Scan_failure _ | End_of_file | Failure _) ->
      Error (Printf.sprintf "%S is not an ISO 8601 date (YYYY-MM-DD)" s)

let days_between ~from ~until =
  let* y1, m1, d1 = parse from in
  let* y2, m2, d2 = parse until in
  Ok (days_from_civil y2 m2 d2 - days_from_civil y1 m1 d1)
