(** Which models may run on which declared entity class, from
    [reference/admissibility.json], the only place lens text and admissibility
    live. A model never runs on a class the table does not list it for. *)

val all_classes : Boundary_t.entity_class list
(** Every constructor of the closed variant, for checking the table covers
    them all. Kept in step with the variant by [class_name]'s exhaustive match. *)

val class_name : Boundary_t.entity_class -> string

val class_of_string : string -> Boundary_t.entity_class option
(** ["Bank"] -> [Some `Bank]; anything that is not a constructor -> [None]. *)

val model_name : Boundary_t.model -> string

val model_of_string : string -> Boundary_t.model option
(** ["dcf"] -> [Some `Dcf]; a name that is not a model -> [None]. *)

val routed : Reference_t.class_rule -> Boundary_t.model option
(** The first model in the row's [admissible_models] that exists. *)

val rule :
  Reference_t.admissibility ->
  Boundary_t.entity_class ->
  (Reference_t.class_rule, string) result
(** The class's row, or an error naming the class. *)

val admits : Reference_t.class_rule -> Boundary_t.model -> bool
