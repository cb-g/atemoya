#!/bin/zsh

set -euo pipefail

# get current directory name as package name
base_name=${PWD:t}
pkg_name="ocaml_${base_name}"
opam_file="${pkg_name}.opam"

# abort if file already exists
if [[ -f "$opam_file" ]]; then
  echo "⚠️  $opam_file already exists. aborting."
  exit 1
fi

# write a minimal opam file
cat > "$opam_file" <<EOF
opam-version: "2.0"
name: "$pkg_name"
version: "0.1.0"
synopsis: "active investing"

maintainer: "cb-g"
authors: ["cb-g"]
license: "MIT"

depends: [
  "ocaml" {>= "4.14.0"}
  "dune"  {>= "3.16.0"}
]

build: [
  ["dune" "build" "-p" name "-j" jobs]
]
EOF

echo "created $opam_file"
