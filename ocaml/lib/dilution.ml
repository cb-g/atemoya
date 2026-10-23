open Boundary_t

let ratio (fin : financials) = match fin.dilution with Some d -> d.ratio | None -> 0.

let shares fin ~market_cap ~price = market_cap /. price *. (1. +. ratio fin)
