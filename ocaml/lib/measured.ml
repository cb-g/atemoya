(* What each readout block was measured against and what came of it (decided 2026-10-18,
   docs/run.md, the readouts and what was measured about them): a readout describes the
   statements, the tape or the filings and need not predict, and the record says beside each
   one what the description was measured against on docs/studies.md and what was found, or
   that it has not been. Dated, so a reader knows which panel; the figures that are the
   finding and not the decimals, so a rebuilt panel does not stale the sentence. One sentence
   per block, the last of its limits. A study that measures a readout owes its block the
   sentence in the same commit, as a Failed string owes the flow chart. *)

let quality =
  "measured 2026-10-04 on the broad panel and on the point-in-time baseline: the nine-signal score sorted nothing before 2022 and was close to monotone from it, in the smaller two thirds by size and not the largest; one signal at a time the levels sorted, no more shares about five points ahead in ten years of eleven, profitable five and cash-generating nine, and the five year-on-year comparisons ran level or slightly the wrong way; the accruals ratio ran the wrong way from 2022; survivors only, sixteen formations (docs/studies.md, What the quality score is made of)"

let growth_shadow =
  "measured 2026-10-03 on the point-in-time panel: the shadow's margin of safety ranked names as the headline's did, a rank correlation of 0.97 within the date, and sorted the returns that followed no better, so it stays a shadow (docs/studies.md, The naive baseline)"

let four_quarter_shadow =
  "measured 2026-10-18 on the rule panel and the point-in-time panel: the shadow's margin ranks with the headline's at 0.92 to 0.93 within the date, sorts the returns that followed no better, the cheapest fifth less the dearest within a few points of the headline's and both negative from 2022, and is nearer the next June's headline than the headline itself on two thirds of name-years, a quarter closer in log distance; a fresher base and not a better sort (docs/studies.md, The owed measurements on the rule panel)"

let base_rate =
  "not measured against what followed: the share is a frequency from the reference class's own history, and no study on docs/studies.md reads it"

let stretch =
  "measured descriptively through time: episodes of a side's count reaching three, walked over every name's closes, against the return at 20, 60 and 120 trading days less the market's, with what insiders had done in the ninety days before; counts, medians and quartiles kept as a sample, no finding promoted to a result and no threshold moved (docs/studies.md, Stretch and insiders through time)"

let insiders =
  "measured descriptively through time beside stretch: what insiders had done in the ninety days before an episode, an open-market buyer, net selling by two or more, or neither, and unknown where the window cannot be read in full; a sample and not a result, and nothing here is read as a call (docs/studies.md, Stretch and insiders through time)"

let earnings =
  "not measured against what followed on docs/studies.md: the implied move is read against the name's own realised median on this block; the surprise history's persistence, a sixth of the last surprise and a small drift for two quarters, is the consensus tool's finding (docs/studies.md, What the surprise history preceded)"

let build_out =
  "not measured against what followed: a map of what the build-out must return for the price, read by a person, and no study on docs/studies.md reads it"

let runway =
  "not measured against what followed: cash against the burn as this tool reads it, and no study on docs/studies.md reads it"

let capital_intensity =
  "measured 2026-10-18 on the rule panel: fifths of capex over depreciation did not sort the twelve-month excess, the heaviest fifth less the lightest within a point pooled, three points behind before 2022 and five ahead from it, names at twice their depreciation or more ran about three points behind the rest on two hundred rows, and the margin at maintenance capex sorted the returns that followed worse than the headline's; the figures describe the spending and say nothing about what it will earn, which stays the universe entry's judgment (docs/studies.md, The owed measurements on the rule panel)"

let goodwill =
  "measured 2026-10-18 on the rule panel: the fundamental growth estimate on the return without goodwill forecast realised revenue and operating income growth no better than the headline's and slightly worse at three and five years, both with a negative R-squared as they stand and none fitted, on about thirteen hundred rows; the return without goodwill reads higher by half a point at the median and the headline keeps the one with it (docs/studies.md, The owed measurements on the rule panel)"

let all =
  [ ("quality", quality); ("growth_shadow", growth_shadow); ("four_quarter_shadow", four_quarter_shadow);
    ("base_rate", base_rate); ("stretch", stretch); ("insiders", insiders); ("earnings", earnings);
    ("build_out", build_out); ("runway", runway); ("capital_intensity", capital_intensity); ("goodwill", goodwill) ]

(* The heading a sentence points at, "(docs/studies.md, <heading>)", or None where it says
   no study reads the block. *)
let heading sentence =
  let marker = "(docs/studies.md, " in
  let rec find i =
    if i + String.length marker > String.length sentence then None
    else if String.sub sentence i (String.length marker) = marker then Some (i + String.length marker)
    else find (i + 1)
  in
  match find 0 with
  | None -> None
  | Some start -> (
      match String.index_from_opt sentence start ')' with
      | None -> None
      | Some stop -> Some (String.sub sentence start (stop - start)))
