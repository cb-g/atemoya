(** Quality from filed statements: Piotroski's nine signals (Journal of Accounting Research,
    2000), the accruals ratio (Sloan, 1996) and gross profitability (Novy-Marx, 2013).
    Independent of every model here: it reads two fiscal years of statements and nothing
    else, so it is the same on a valued record and a refused one, and nothing reads it.

    Contract. [of_financials] returns the block, or the reason there is none: no filed
    lines for the name, fewer than two fiscal periods, or two periods that are not
    consecutive years. A signal whose lines are not all filed is null, never guessed, and
    [f_score] is null unless all nine are available; [signals_passed] counts what is there.

    The signals, on the latest year t against the year before, assets at each year's end:
    return on assets positive (net income over total assets); operating cash flow positive;
    return on assets higher than the year before; operating cash flow above net income;
    debt over assets lower (the record's financial debt, where Piotroski reads long-term
    debt; both years with no debt passes); current ratio higher; no more shares (the
    weighted count not above the year before; a rise beyond a quarter is null, since a
    split and an issue cannot be told apart from the counts alone); gross margin higher
    (gross profit as filed, else revenue less cost of revenue); asset turnover higher. *)

val scope_limits : string list

val of_financials : Boundary_t.financials -> Boundary_t.quality option * string option
(** Exactly one side is [Some]. Read from the statements in their own currency; every
    figure in the block is a ratio. *)
