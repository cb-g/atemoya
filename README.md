# atemoya

```zsh
uv venv .venv
source .venv/bin/activate
uv install
```

```zsh
echo "alias py3='python3'" >> ~/.zshrc && source ~/.zshrc
```

```zsh
opam switch create . ocaml-base-compiler.4.14.0
chmod +x create_opam.zsh; ./create_opam.zsh
opam install . --deps-only
eval $(opam env)
```

## valuation

[typeset/atemoya.pdf](typeset/atemoya.pdf)

```zsh
py3 src/atemoya.py valuation
dune build; dune install; ocaml_atemoya valuation
```
