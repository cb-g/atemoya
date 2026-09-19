(** The universe file, loaded strictly (brief 20): each entry is exactly a ticker, a
    declared class, a why and optionally scope_limits and a declared cik (22); any other field, a missing or
    empty required one, or an unknown class is an [Error] naming the entry and the
    problem, so nothing that remembers an outcome or a finding can creep back in. *)

val allowed_fields : string list

val load_string : string -> (Reference_t.universe, string) result
val load : string -> (Reference_t.universe, string) result
(** [load path] reads the file; [load_string] the JSON text. *)
