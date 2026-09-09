(lang dune 3.17)
(name atemoya)
(version 0.1.0)

(generate_opam_files true)

(package
 (name atemoya)
 (synopsis "Quantitative finance models for investment analysis")
 (description
  "Fundamentals-based fair-value anchoring for equities, with OCaml valuation engines fed by Python data collection.")
 (license MIT)
 (maintainers "cb-g")
 (authors "cb-g")
 (homepage "https://github.com/cb-g/atemoya")
 (bug_reports "https://github.com/cb-g/atemoya/issues")
 (depends
  (ocaml (>= 5.3))
  dune
  (atdgen (and (>= 4.2) :build))
  (atdgen-runtime (>= 4.2))
  (atdpy (and (>= 4.2) :build))
  (yojson (>= 2.0))
  (alcotest :with-test)))
