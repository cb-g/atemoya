(lang dune 3.17)
(name atemoya)
(version 0.1.0)

(generate_opam_files true)

(package
 (name atemoya)
 (synopsis "Quantitative finance models for investment analysis")
 (description "A collection of pricing and valuation models implemented in OCaml, covering portfolio optimization, regime detection, and fundamental valuation.")
 (license MIT)
 (maintainers "cb-g")
 (authors "cb-g")
 (homepage "https://github.com/cb-g/atemoya")
 (bug_reports "https://github.com/cb-g/atemoya/issues")
 (depends
  (ocaml (>= 5.0))
  dune
  (owl (>= 1.1))
  (yojson (>= 2.0))
  (csv (>= 2.4))
  (ppx_deriving (>= 5.2))
  (alcotest :with-test)))
