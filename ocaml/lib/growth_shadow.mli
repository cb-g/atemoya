(** The growth shadow: the generic DCF's value if the starting growth were the higher of its
    two estimates, beside the headline and never replacing it.

    The headline's rule ([Growth.select]) is a switch at zero net reinvestment: with
    positive after-tax operating profit and positive net reinvestment it takes the
    fundamental estimate, return on capital times the reinvestment rate, and otherwise the
    historical revenue growth, held to the return on capital. So a name reinvesting slightly
    more than nothing takes a growth near zero and one reinvesting slightly less takes its
    whole revenue history. The shadow takes the higher of the two estimates wherever both
    exist, the historical one still held to the return on capital, and the one that exists
    where only one does; the clamp, the path, the cash flow and the discount rate are the
    headline's own. A company that grows through spending the accounts do not count as
    reinvestment has a low measured reinvestment rate that says little about its growth,
    which is the case for reading the higher one; the cap keeps the headline's safeguard.

    Contract. [of_inputs] takes a completed generic DCF's inputs and fair value and returns
    the block. The block is always there on such a record, and equals the headline where
    the rule picks the same estimate. The record's fair value, margin of safety and signal
    are never moved by it. *)

val higher : Boundary_t.inputs -> (float * Boundary_t.growth_source) option
(** The higher of the fundamental estimate (where after-tax operating profit and net
    reinvestment are both positive) and the historical one held to the return on capital;
    [None] when neither exists. Before the clamp. *)

val scope_limits : string list

val of_inputs : Boundary_t.inputs -> fair_value:float -> Boundary_t.growth_shadow
