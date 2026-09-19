(** The cross-currency recipe: statement totals times one FX rate, divided by
    effective shares. Never a per-share field.

    [rate] gives the trading currency per unit of the financial currency,
    through USD, with both legs' provenance and the older leg's age; a currency
    with no rate is an [Error] naming the pair; a stale leg is an [Error] naming
    it; a table never fetched is an [Error] naming the refresher (29). [convert] multiplies every money total of every period by the rate and
    sets the record's currency to the trading currency, so the models run on it
    unchanged; price and market cap are already in the trading currency and are
    untouched. [country_of] names the country whose curve and terminal growth a
    trading currency uses. *)

type legs = {
  fx_rate : float;
  usd_per_financial : float;
  usd_per_trading : float;
  source : string;
  as_of : string;
  age_days : int;
}

val rate :
  Reference_t.fx_sources ->
  Reference_t.fx_rates option ->
  today:string ->
  financial:string ->
  trading:string ->
  (legs, string) result

val country_of : Reference_t.fx_sources -> string -> (string, string) result

val convert : rate:float -> Boundary_t.financials -> Boundary_t.financials
