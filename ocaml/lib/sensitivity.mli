(** The sensitivity block (23): where the anchor's uncertainty bites, deterministically.
    For each held input that has a declared step, fair value at the input stepped down
    and up with everything else at its recorded value, the swing [|up - down| /
    fair_value], and the inputs ranked by swing; a step that crosses a guard (a
    discount rate reaching terminal growth, a non-positive base or lambda) records null
    with the reason on that side. No probabilities, no distributions, no sampling; the
    steps are readability steps from [reference/params.json], not standard deviations.
    The headline never depends on this module. *)

val note : string

val of_inputs :
  Reference_t.sensitivity_steps -> Boundary_t.model_inputs -> fair_value:float -> Boundary_t.sensitivity
