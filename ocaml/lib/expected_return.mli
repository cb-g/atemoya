(** The options-implied expected return (Martin and Wagner, "What is the expected return
    on a stock?", Journal of Finance 2019): a required return read from option prices alone,
    beside CAPM and the declared one and never replacing either. No model here, no beta, no
    history: three risk-neutral variances.

    Contract. [annotate] runs after the batch, under --options only. Every record of a name
    that is not a fund gets the block, or the reason there is none; no other field of any
    record moves. The block is the same whatever the record's status, since nothing in it
    reads the valuation.

    Method. For one expiry with fitted smile and forward F, SVIX squared is the risk-neutral
    variance of the return over the horizon, [2 / F^2] times the integral over strikes of the
    out-of-the-money option price (puts below the forward, calls above, undiscounted), taken
    on the fitted smile by Simpson's rule between the lowest and the highest strike the fit
    read (nothing is taken from the extrapolated wings, so the figure understates), and annualised by
    dividing by the horizon in years. The expiry is the one the market-implied readout uses:
    the longest at least 365 days out with eight quoted strikes on each side. Then, annualised,

    [expected excess return = (1 + rf) * (market + (stock - average) / 2)]

    where [market] is the benchmark fund's SVIX squared, [stock] the name's, and [average]
    the market-capitalisation-weighted mean of [stock] over the names in the run with a
    usable chain on the benchmark's snapshot date. The paper's average runs over every index
    member; here it runs over the names the options store holds, which the block counts and
    its scope limits say. Fewer than [min_names] is a reason, not an average. *)

val min_names : int
val benchmark : string

val svix2 : ?lower:float -> ?upper:float -> Market_implied.svi -> forward:float -> float
(** Over the expiry's horizon, not annualised: [2 / F^2 * integral of OTM price dK] over
    log-moneyness [lower, upper], by default [-3, 3]. On a flat smile of total variance [w]
    over a wide range this is [exp w - 1]. *)

val scope_limits : string list

val annotate :
  lookup:(string -> (Boundary_t.option_chain, string) result) ->
  rf:(float, string) result ->
  caps:(string * float) list ->
  Boundary_t.valuation list ->
  Boundary_t.valuation list
(** [caps] are the market capitalisations of the run's names, in one currency; a name
    without one is left out of the average and told so. [rf] is the risk-free rate of the
    benchmark's currency, or why it could not be resolved. *)
