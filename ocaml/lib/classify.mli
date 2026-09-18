(** Statement signatures as a consistency check against the declared entity
    class. The signatures never classify: the class is a human declaration.

    [signature] reads the latest fiscal period. The statements indicate [`Bank]
    iff [net_interest_income / total_revenue >= threshold] (a materiality ratio;
    the vendor reports a net interest income row for every company, so a sign
    test is wrong), else [`Insurer] iff [premiums_earned > 0], else nothing.
    [check] compares that with the declaration: no declaration is fatal; a
    signature that contradicts a declared [`OperatingCompany] is fatal, because
    it would have let an inadmissible model run; any other mismatch is recorded
    and the record proceeds to the admissibility decision. The
    [Boundary_t.class_check] is the evidence, always populated. *)

type signature = {
  indicated : Boundary_t.entity_class option;
  fiscal_period_end : string option;
  total_revenue : float option;
  net_interest_income : float option;
  nii_ratio : float option;
  threshold : Boundary_t.parameter;
  premiums_earned : float option;
  premiums_earned_row : string option;
}

val signature :
  threshold:Boundary_t.parameter -> Boundary_t.financials -> signature

type verdict =
  | Proceed of Boundary_t.class_check
  | Refuse of string * Boundary_t.class_check  (** the reason, and the evidence *)

val check :
  declared:Boundary_t.entity_class option -> signature -> verdict
