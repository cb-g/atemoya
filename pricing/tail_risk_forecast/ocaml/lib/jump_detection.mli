(** Simple threshold-based variance jump detection

    A jump is detected when RV_t exceeds k standard deviations above
    the rolling mean. This is simpler than the paper's SARJ model but
    captures most of the signal.
*)

open Types

(** Default threshold multiplier (number of std devs) *)
val default_threshold : float

(** Detect if a single day has a variance jump.
    Uses rolling window to compute mean and std. *)
val detect_jump : ?threshold:float -> ?window:int -> daily_rv array -> int -> jump_indicator

(** Detect jumps across entire series *)
val detect_all_jumps : ?threshold:float -> ?window:int -> daily_rv array -> jump_indicator array

(** Count recent jumps in last n days *)
val count_recent_jumps : jump_indicator array -> int -> int

(** Compute jump intensity (fraction of days with jumps) *)
val jump_intensity : jump_indicator array -> float

(** Get indices of jump days *)
val jump_days : jump_indicator array -> int array
