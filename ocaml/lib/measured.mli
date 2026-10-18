(** What each readout block was measured against and what came of it, one dated sentence per
    block, the last of its limits (decided 2026-10-18). A readout describes and need not
    predict; the record says beside each what the description was measured against on
    docs/studies.md and what was found, or that no study reads it. A study that measures a
    readout owes its block the sentence in the same commit; a test holds every sentence that
    names a heading to a heading that exists. *)

val quality : string
val growth_shadow : string
val four_quarter_shadow : string
val base_rate : string
val stretch : string
val insiders : string
val earnings : string
val build_out : string
val runway : string

val all : (string * string) list
(** Every block's sentence, by the record field it rides on. *)

val heading : string -> string option
(** The docs/studies.md heading a sentence points at, or [None] where it says no study reads
    the block. *)
