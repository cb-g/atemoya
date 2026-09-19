(** Declared required returns on equity (34), beside CAPM. An entry is exactly three
    fields: [premium_over_rf] (percentage points over the country's risk-free rate at the
    model's tenor), [why], [as_of]. The loaders are strict; nothing here derives a
    premium from anything. Resolution per name: an entry in a further file given as
    --required-returns, else the tracked names section, else the class default, else
    CAPM ([None]). *)

val load_classes_string : string -> (Reference_t.required_returns, string) result
val load_classes : string -> (Reference_t.required_returns, string) result
val load_names_string : string -> (Reference_t.name_required_returns, string) result
val load_names : string -> (Reference_t.name_required_returns, string) result

val resolve :
  Reference_t.required_returns ->
  ?names:Reference_t.name_required_returns ->
  ticker:string ->
  entity_class:string ->
  unit ->
  Dcf.declared_return option
(** The premium as a decimal fraction with its source text ("declared: name" or
    "declared: class <name>") and version stamp. *)

val version : Reference_t.required_return -> source_kind:string -> string
(** [as_of-<7 hex of the three fields>-<class|name>]: changes when any field changes. *)
