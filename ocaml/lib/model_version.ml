let stamp ~head ~porcelain =
  match Option.map String.trim head with
  | None | Some "" -> "unversioned"
  | Some hash -> if String.trim porcelain = "" then hash else hash ^ "-dirty"
