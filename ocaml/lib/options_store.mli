(** The options store (36, 37): [dir/<date>/<TICKER>.json], one end-of-day chain per name
    and snapshot date, written by python/fetch_options.py and never tracked.

    [lookup] is the no-lookahead rule: a name's chain is the one on the latest snapshot
    date at or before [today] and, given [max_age_days], no more than that many calendar
    days before it (the point-in-time panel passes 7). [Error "no options data"] when the
    store holds no chain for the name (on any date at or before [today] without a window;
    on any date at all with one); [Error "no options snapshot within N days before <today>"]
    when it holds one but none inside the window, which is what every panel date before
    the archive begins says; an unreadable file is an error naming it. *)

val snapshot_dates : dir:string -> today:string -> ?max_age_days:int -> unit -> string list
(** The store's snapshot dates at or before [today] (and within the window), newest first. *)

val lookup :
  dir:string -> today:string -> ?max_age_days:int -> string -> (Boundary_t.option_chain, string) result
