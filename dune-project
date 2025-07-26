(lang dune 3.19)

(name atemoya)

(generate_opam_files true)

(source
 (github cb-g/atemoya))

(license MIT)

(package
 (name atemoya)
 (synopsis "active investing")
 (description "")
 (depends
  (ocaml (>= 4.14.0))
  dune
  core
  odoc
  alcotest)
 (tags
  ("portfolio optimization" "option pricing" "quantitative finance" "risk management" "value investing" "efficient frontier" "intrinsiv value" "volatility surface" "active investing")))
