(** Simple threshold-based variance jump detection *)

open Types

let default_threshold = 2.5  (* 2.5 std devs *)

let detect_jump ?(threshold = default_threshold) ?(window = 60) (rv_series : daily_rv array) (idx : int) : jump_indicator =
  let n = Array.length rv_series in
  if n = 0 || idx >= n then
    { date = ""; is_jump = false; rv = 0.0; threshold = 0.0; z_score = 0.0 }
  else
    let date = rv_series.(idx).date in
    let rv = rv_series.(idx).rv in

    (* Compute rolling mean and std up to (but not including) current day *)
    let start_idx = max 0 (idx - window) in
    let end_idx = idx - 1 in

    if end_idx < start_idx then
      (* Not enough history *)
      { date; is_jump = false; rv; threshold = rv *. 2.0; z_score = 0.0 }
    else
      let count = end_idx - start_idx + 1 in

      (* Mean *)
      let sum = ref 0.0 in
      for i = start_idx to end_idx do
        sum := !sum +. rv_series.(i).rv
      done;
      let mean = !sum /. float_of_int count in

      (* Std *)
      let sq_sum = ref 0.0 in
      for i = start_idx to end_idx do
        let diff = rv_series.(i).rv -. mean in
        sq_sum := !sq_sum +. diff *. diff
      done;
      let std = sqrt (!sq_sum /. float_of_int count) in

      let jump_threshold = mean +. threshold *. std in
      let z_score = if std > 1e-10 then (rv -. mean) /. std else 0.0 in
      let is_jump = rv > jump_threshold in

      { date; is_jump; rv; threshold = jump_threshold; z_score }

let detect_all_jumps ?(threshold = default_threshold) ?(window = 60) (rv_series : daily_rv array) : jump_indicator array =
  Array.mapi (fun i _ -> detect_jump ~threshold ~window rv_series i) rv_series

let count_recent_jumps (jumps : jump_indicator array) (n : int) : int =
  let len = Array.length jumps in
  if len = 0 then 0
  else
    let start = max 0 (len - n) in
    let count = ref 0 in
    for i = start to len - 1 do
      if jumps.(i).is_jump then incr count
    done;
    !count

let jump_intensity (jumps : jump_indicator array) : float =
  let n = Array.length jumps in
  if n = 0 then 0.0
  else
    let count = Array.fold_left (fun acc j -> if j.is_jump then acc + 1 else acc) 0 jumps in
    float_of_int count /. float_of_int n

let jump_days (jumps : jump_indicator array) : int array =
  let indices = ref [] in
  Array.iteri (fun i j -> if j.is_jump then indices := i :: !indices) jumps;
  Array.of_list (List.rev !indices)
