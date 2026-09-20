(* Every expiry's smile on one stored chain (38), for python/hedge.py:

     atemoya-smile <chain.json> --rf RATE

   prints Boundary_t.chain_smiles as JSON: per expiry the forward by put-call parity and the
   constrained SVI fit of brief 36, or the reason it has none. Nothing here prices a leg; the
   hedging tool prices from quotes and uses the smile only for Greeks at quoted strikes, the
   stale-quote flag and the risk-neutral floor probability. *)

open Atemoya

let () =
  match Array.to_list Sys.argv with
  | [ _; path; "--rf"; rf ] -> (
      match (float_of_string_opt rf, Atdgen_runtime.Util.Json.from_file Boundary_j.read_option_chain path) with
      | Some rf, chain -> print_string (Boundary_j.string_of_chain_smiles (Market_implied.smiles chain ~rf) ^ "\n")
      | None, _ ->
          prerr_endline "--rf takes a decimal rate";
          exit 2
      | exception (Yojson.Json_error msg | Atdgen_runtime.Oj_run.Error msg | Sys_error msg) ->
          Printf.eprintf "%s: cannot read the chain: %s\n%!" path msg;
          exit 2)
  | _ ->
      prerr_endline "usage: atemoya-smile <chain.json> --rf RATE";
      exit 2
