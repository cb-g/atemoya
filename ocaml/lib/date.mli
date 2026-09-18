(** ISO 8601 calendar dates (YYYY-MM-DD), proleptic Gregorian. *)

val days_between : from:string -> until:string -> (int, string) result
(** Calendar days from [from] to [until]; negative when [until] is earlier.
    The error names the string that is not a date. *)
