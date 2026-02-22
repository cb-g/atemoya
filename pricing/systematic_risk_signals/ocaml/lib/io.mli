(** I/O operations for systematic risk signals module. *)

open Types

(** Read returns data from JSON file *)
val read_returns_data : string -> asset_returns array

(** Write analysis result to JSON *)
val write_result_json : string -> analysis_result -> unit

(** Print formatted analysis to console *)
val print_analysis : analysis_result -> unit

(** Print signal dashboard *)
val print_dashboard : risk_signals -> risk_regime -> float -> unit
