(** Cross-sectional factor-rank types.

    A [panel_row] is one ticker's RAW, trading-basis fundamentals as written by the
    Python fetcher (already FX-converted; sign-normalized so "good" magnitudes are
    positive). Fields are kept as a sparse assoc list so missing inputs are simply
    absent — the ranking treats absent factors as missing rather than zero. *)

type panel_row = {
  ticker : string;
  sector : string;
  fields : (string * float) list;  (* present numeric fields only, trading basis *)
}

(** A ranked result. Percentiles are [Some 0..100] or [None] when the pillar had
    fewer than half its sector-allowed factors present (never imputed). *)
type ranked = {
  ticker : string;
  sector : string;
  value_pct : float option;
  quality_pct : float option;
  combined_pct : float option;
  n_value_used : int;
  n_value_allowed : int;
  n_quality_used : int;
  n_quality_allowed : int;
  signal : string;
}
