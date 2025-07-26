# atemoya

## theory

[typeset/atemoya.pdf](typeset/atemoya.pdf)

## implementation

```zsh
opam install . --deps-only
eval $(opam env)
```

```zsh
uv sync
```

```zsh
dune clean && dune build
```

define ticker selection here: [data/tickers.yml](data/tickers.yml)

### valuation

deterministic computation of selected stocks' intrinsic value per share through discounted free cash flow to equity and to firm - displaying margins of safety, projected and implied growth rates, and including interpretation of the result as can be seen [here](log/val/dcf_deterministic/IVPS_2025-07-26_17-02-52_GOOGL_SIE.DE_ROG.SW_ASML_TCS.NS_GRAB_CEG.log)
```zsh
uv run -m prep.val.dcf_deterministic
dune exec dcf_deterministic
```

probabilistic computation of selected stocks' intrinsic value per share ([here](log/val/dcf_probabilistic/IVPS_2025-07-26_17-03-38_GOOGL_SIE.DE_ROG.SW_ASML_TCS.NS_GRAB_CEG.log))

single-asset value-surplus distributions (FCFE)

<div>
  <img src="fig/val/dcf_probabilistic/single_asset/CEG_fcfe_2025-07-26_17-03-55.svg" alt="single-asset value-surplus distribution" style="display:inline-block; width:35%;"/>
  <img src="fig/val/dcf_probabilistic/single_asset/CEG_fcfe_pct_2025-07-26_17-03-55.svg" alt="single-asset value-surplus percentage distribution" style="display:inline-block; width:35%;"/>
</div>

single-asset value-surplus distributions (FCFF)

<div>
  <img src="fig/val/dcf_probabilistic/single_asset/CEG_fcff_2025-07-26_17-03-55.svg" alt="single-asset value-surplus distribution" style="display:inline-block; width:35%;"/>
  <img src="fig/val/dcf_probabilistic/single_asset/CEG_fcff_pct_2025-07-26_17-03-55.svg" alt="single-asset value-surplus percentage distribution" style="display:inline-block; width:35%;"/>
</div>

multi-asset value-surplus frontier (based on FCFE)

<div>
  <img src="fig/val/dcf_probabilistic/multi_asset/efficient_frontier_stddev_fcfe_2025-07-26_17-03-58.svg" alt="fcfe-based multi-asset value-surplus percentage distribution std" style="display:inline-block; width:49%;"/>
  <img src="fig/val/dcf_probabilistic/multi_asset/efficient_frontier_probability_fcfe_2025-07-26_17-03-58.svg" alt="fcfe-based multi-asset value-surplus percentage distribution prob" style="display:inline-block; width:49%;"/>
</div>

multi-asset value-surplus frontier (based on FCFF)

<div>
  <img src="fig/val/dcf_probabilistic/multi_asset/efficient_frontier_stddev_fcff_2025-07-26_17-04-00.svg" alt="fcff-based multi-asset value-surplus percentage distribution std" style="display:inline-block; width:49%;"/>
  <img src="fig/val/dcf_probabilistic/multi_asset/efficient_frontier_probability_fcff_2025-07-26_17-04-00.svg" alt="fcff-based multi-asset value-surplus percentage distribution prob" style="display:inline-block; width:49%;"/>
</div>

```zsh
uv run -m prep.val.dcf_probabilistic
dune exec dcf_probabilistic
uv run -m viz.val.dcf_probabilistic
```

### pricing

mpt: portfolio weights on efficient frontier in the mean-variance optimization framework
<div>
  <img src="fig/pri/mpt/frontier_with_allocations.svg" alt="efficient frontier" style="display:inline-block; width:37%;"/>
</div>

```zsh
uv run -m prep.pri.mpt
dune exec mpt
uv run -m viz.pri.mpt
```
