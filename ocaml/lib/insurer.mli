(** The insurer model: residual income on AOCI-adjusted book, from filed
    statements.

    Contract: [value] returns [Ok (inputs, fair_value)] or [Error reason]. It
    runs [Residual_income.value] with book read as reported stockholders'
    equity less accumulated other comprehensive income, per period, so the
    unrealised gains and losses on the bond portfolio do not distort the base.
    A record whose provider supplied no filed statements, or whose periods
    carry no AOCI and premiums, is an [Error] that names what would fix it;
    the model never runs on vendor rows that lack those fields. The
    underwriting checks (combined-ratio proxy, reserves over premiums, AOCI
    over reported book) are recorded for the reader and gate nothing.
    Solvency is null with its basis stated; it is never fabricated. No
    cash-flow model and no earnings multiple appear anywhere. *)

val requires_filed : Boundary_t.financials -> string option
(** [Some reason] when the record cannot feed the model: the provider had no
    statements (its own explanation is appended) or no period carries AOCI and
    premiums earned. *)

val value :
  Dcf.assumptions ->
  terminal_spread:Boundary_t.parameter ->
  country:string ->
  Boundary_t.financials ->
  (Boundary_t.insurer_inputs * float, string) result
