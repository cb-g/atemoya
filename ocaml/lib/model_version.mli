(** The other half of provenance (21): which code produced a record. [stamp ~head
    ~porcelain] is the short hash of HEAD, with "-dirty" appended when [git status
    --porcelain] printed anything (uncommitted edits: the hash alone would name code
    that did not produce the run), or "unversioned" when there is no HEAD (outside a
    git checkout). Pure; the batch supplies the two command outputs. *)

val stamp : head:string option -> porcelain:string -> string
