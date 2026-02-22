#!/bin/bash
# regenerate_showcase.sh - Regenerate all showcase SVGs referenced in the main README
#
# Runs the full fetch → analyze → visualize pipeline for every module
# that has showcase plots embedded in README.md.
#
# Usage:
#   ./regenerate_showcase.sh                  Run all modules (parallel)
#   ./regenerate_showcase.sh --module <name>  Run a single module
#   ./regenerate_showcase.sh --jobs 4         Limit to 4 parallel modules
#   ./regenerate_showcase.sh --sequential     Run modules one at a time
#   ./regenerate_showcase.sh --list           List available modules
#   ./regenerate_showcase.sh --dry-run        Show what would run without executing

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

DRY_RUN=false
TARGET_MODULE=""
SKIP_FETCH=false
MAX_JOBS=0  # 0 = auto (nproc - 2)
FAILED_MODULES=()
SUCCEEDED_MODULES=()

usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --module <name>   Run only the specified module"
    echo "  --list            List all available modules"
    echo "  --dry-run         Show what would run without executing"
    echo "  --skip-fetch      Skip data fetching (use existing data)"
    echo "  --jobs N          Max parallel modules (default: nproc - 2)"
    echo "  --sequential      Force sequential execution (same as --jobs 1)"
    echo "  -h, --help        Show this help"
    echo ""
    echo "Modules are run inside Docker. Ensure the container is running:"
    echo "  docker compose up -d"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --module) TARGET_MODULE="$2"; shift 2 ;;
        --list) LIST_MODE=true; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        --skip-fetch) SKIP_FETCH=true; shift ;;
        --jobs) MAX_JOBS="$2"; shift 2 ;;
        --sequential) MAX_JOBS=1; shift ;;
        -h|--help) usage ;;
        *) echo "Unknown option: $1"; usage ;;
    esac
done

# ─── Helpers ──────────────────────────────────────────────────────────────────

header() {
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}$1${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════${NC}"
}

step() {
    echo -e "  ${CYAN}→${NC} $1"
}

ok() {
    echo -e "  ${GREEN}✓${NC} $1"
}

fail() {
    echo -e "  ${RED}✗${NC} $1"
}

# ─── Execution mode detection ────────────────────────────────────────────────
# Detect whether to use Docker or native commands. Docker is preferred; native
# is the fallback if the container isn't running. If native tools are missing,
# we fail with an install message.

USE_DOCKER=false

detect_exec_mode() {
    if docker compose ps --status running 2>/dev/null | grep -q atemoya; then
        USE_DOCKER=true
        echo -e "${GREEN}Using Docker container${NC}"
    else
        USE_DOCKER=false
        echo -e "${YELLOW}Docker container not running — falling back to native${NC}"
        local missing=()
        if ! command -v opam &>/dev/null; then missing+=("opam"); fi
        if ! command -v dune &>/dev/null && ! opam exec -- dune --version &>/dev/null 2>&1; then missing+=("dune"); fi
        if ! command -v uv &>/dev/null; then missing+=("uv"); fi
        if [[ ${#missing[@]} -gt 0 ]]; then
            echo -e "${RED}Error: Missing native tools: ${missing[*]}${NC}"
            echo -e "${RED}Install them first, or start the Docker container with: docker compose up -d${NC}"
            exit 1
        fi
    fi
}

# Run an OCaml/dune command
dock() {
    if $DRY_RUN; then
        if $USE_DOCKER; then
            echo -e "  ${YELLOW}[dry-run]${NC} docker compose exec -w /app atemoya /bin/bash -c \"eval \\\$(opam env) && $*\""
        else
            echo -e "  ${YELLOW}[dry-run]${NC} eval \$(opam env) && $*"
        fi
        return 0
    fi
    if $USE_DOCKER; then
        docker compose exec -T -w /app atemoya /bin/bash -c "eval \$(opam env) && $*"
    else
        # Subshell prevents cd from leaking to subsequent modules
        (eval "$(opam env)" && eval "$*")
    fi
}

# Run a Python command
dockpy() {
    if $DRY_RUN; then
        if $USE_DOCKER; then
            echo -e "  ${YELLOW}[dry-run]${NC} docker compose exec -w /app atemoya /bin/bash -c \"uv run $*\""
        else
            echo -e "  ${YELLOW}[dry-run]${NC} uv run $*"
        fi
        return 0
    fi
    if $USE_DOCKER; then
        docker compose exec -T -w /app atemoya /bin/bash -c "PYTHONPATH=/app uv run $*"
    else
        (PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}." uv run $*)
    fi
}

run_module() {
    local name="$1"
    shift
    if [[ -n "$TARGET_MODULE" && "$TARGET_MODULE" != "$name" ]]; then
        return 0
    fi
    header "$name"
    if "$@"; then
        ok "Done"
        SUCCEEDED_MODULES+=("$name")
    else
        fail "Failed"
        FAILED_MODULES+=("$name")
    fi
}

# ─── Module definitions ──────────────────────────────────────────────────────
# Each function runs the full pipeline for one module's showcase plots.
# Showcase SVGs: see the !-prefixed entries in .gitignore

# --- Valuation modules ---

mod_dcf_deterministic() {
    local tickers="AMZN,ALL,CBOE,COP,CVX,GS,IBKR,JPM,LLY,MET,PGR,SFM,TAC,XOM"

    if ! $SKIP_FETCH; then
        step "Fetching + running DCF valuation for $tickers..."
        IFS=',' read -ra arr <<< "$tickers"
        for t in "${arr[@]}"; do
            dock "dune exec dcf_deterministic -- \
                -ticker $t \
                -data-dir valuation/dcf_deterministic/data \
                -log-dir valuation/dcf_deterministic/log \
                -python valuation/dcf_deterministic/python/fetch_financials.py \
                -fetch-sec-reserves"
        done
    fi

    step "Running sensitivity analyses..."
    mkdir -p valuation/dcf_deterministic/output/sensitivity/data
    local sens_tickers="TAC,JPM,CVX"
    IFS=',' read -ra sarr <<< "$sens_tickers"
    for t in "${sarr[@]}"; do
        dock "dune exec dcf_sensitivity -- -ticker $t"
    done

    step "Generating valuation plots..."
    dockpy "valuation/dcf_deterministic/python/viz/plot_results.py \
        --viz-dir valuation/dcf_deterministic/output \
        --valuation-only"

    step "Generating sensitivity plots..."
    dockpy "valuation/dcf_deterministic/python/viz/plot_results.py \
        --csv-dir valuation/dcf_deterministic/output/sensitivity/data \
        --viz-dir valuation/dcf_deterministic/output \
        --sensitivity-only"
}

mod_dcf_probabilistic() {
    local tickers="AMZN,ALL,CBOE,COP,CVX,GS,IBKR,JPM,LLY,MET,PGR,SFM,TAC,XOM"

    if ! $SKIP_FETCH; then
        step "Fetching + running probabilistic DCF..."
        IFS=',' read -ra arr <<< "$tickers"
        for t in "${arr[@]}"; do
            dock "dune exec valuation/dcf_probabilistic/ocaml/bin/main.exe -- \
                -ticker $t \
                -data-dir valuation/dcf_probabilistic/data \
                -output-dir valuation/dcf_probabilistic/output \
                -python valuation/dcf_probabilistic/python/fetch/fetch_financials_ts.py"
        done
    fi

    step "Generating KDE plots..."
    dockpy "valuation/dcf_probabilistic/python/viz/plot_results.py"

    step "Generating efficient frontier..."
    dockpy "valuation/dcf_probabilistic/python/viz/plot_frontier.py"
}

mod_dcf_reit() {
    local tickers="PLD O EQIX STWD"

    if ! $SKIP_FETCH; then
        step "Fetching REIT data..."
        dockpy "valuation/dcf_reit/python/fetch/fetch_reit_data.py \
            -t $tickers -o valuation/dcf_reit/data"
    fi

    step "Running REIT valuation..."
    dock "dune exec valuation/dcf_reit/ocaml/bin/main.exe -- \
        -d valuation/dcf_reit/data -o valuation/dcf_reit/output/data"

    step "Generating REIT plots..."
    dock "for f in valuation/dcf_reit/output/data/*_valuation.json; do \
        uv run valuation/dcf_reit/python/viz/plot_reit_valuation.py \
            -i \"\$f\" -o valuation/dcf_reit/output/plots; done"
}

mod_crypto_treasury() {
    if ! $SKIP_FETCH; then
        step "Running crypto treasury valuation..."
        dockpy "valuation/crypto_treasury/python/crypto_valuation.py"
    fi

    step "Generating crypto treasury plot..."
    dockpy "valuation/crypto_treasury/python/plot_crypto.py"
}

mod_garp_peg() {
    local tickers="META,SFM,AAPL,PLTR,COST"

    if ! $SKIP_FETCH; then
        step "Fetching GARP data..."
        IFS=',' read -ra arr <<< "$tickers"
        for t in "${arr[@]}"; do
            dockpy "valuation/garp_peg/python/fetch/fetch_garp_data.py \
                --ticker $t --output valuation/garp_peg/data"
        done
    fi

    step "Running GARP comparison..."
    dock "dune exec garp_peg -- --tickers $tickers --compare \
        --data valuation/garp_peg/data --output valuation/garp_peg/output"

    step "Generating individual GARP plots..."
    IFS=',' read -ra arr <<< "$tickers"
    for t in "${arr[@]}"; do
        dockpy "valuation/garp_peg/python/viz/plot_garp.py \
            --result valuation/garp_peg/output/garp_result_${t}.json"
    done

    step "Generating GARP comparison plot..."
    dockpy "valuation/garp_peg/python/viz/plot_garp.py \
        --comparison valuation/garp_peg/output/garp_comparison.json"
}

mod_growth_analysis() {
    local tickers="NVDA,CRWD,SFM,JNJ,PLTR"

    if ! $SKIP_FETCH; then
        step "Fetching growth data..."
        IFS=',' read -ra arr <<< "$tickers"
        for t in "${arr[@]}"; do
            dockpy "valuation/growth_analysis/python/fetch/fetch_growth_data.py \
                --ticker $t --output valuation/growth_analysis/data"
        done
    fi

    step "Running growth comparison..."
    dock "dune exec growth_analysis -- --tickers $tickers --compare \
        --data valuation/growth_analysis/data --output valuation/growth_analysis/output"

    step "Generating growth analysis plots..."
    IFS=',' read -ra arr <<< "$tickers"
    for t in "${arr[@]}"; do
        dockpy "valuation/growth_analysis/python/viz/plot_growth.py \
            --input valuation/growth_analysis/output/growth_result_${t}.json"
    done

    step "Generating growth comparison plot..."
    dockpy "valuation/growth_analysis/python/viz/plot_growth.py \
        --comparison valuation/growth_analysis/output/growth_comparison.json"
}

mod_normalized_multiples() {
    local tickers="CAT,DE,GE,HON"

    step "Running normalized multiples comparison..."
    dock "dune exec normalized_multiples -- --mode compare --tickers $tickers \
        --python 'uv run' --json"

    step "Running individual ticker analyses..."
    IFS=',' read -ra arr <<< "$tickers"
    for t in "${arr[@]}"; do
        dock "dune exec normalized_multiples -- --tickers $t --json"
    done

    step "Generating multiples plots..."
    for t in "${arr[@]}"; do
        dockpy "valuation/normalized_multiples/python/viz/plot_multiples.py \
            --input valuation/normalized_multiples/output/multiples_result_${t}.json \
            --output-dir valuation/normalized_multiples/output/plots"
    done
    dockpy "valuation/normalized_multiples/python/viz/plot_multiples.py \
        --input valuation/normalized_multiples/output/multiples_comparison.json \
        --comparison --output-dir valuation/normalized_multiples/output/plots"
}

mod_relative_valuation() {
    local targets_and_peers=(
        "TAC:AES,VST,NRG,CEG,CWEN,BEP"
    )

    for entry in "${targets_and_peers[@]}"; do
        local target="${entry%%:*}"
        local peers="${entry##*:}"

        if ! $SKIP_FETCH; then
            step "Fetching peer data for $target..."
            dockpy "valuation/relative_valuation/python/fetch/fetch_peer_data.py \
                --target $target --peers $peers --output valuation/relative_valuation/data"
        fi

        step "Running relative valuation for $target..."
        dock "dune exec relative_valuation -- \
            --target $target --peers $peers \
            --data valuation/relative_valuation/data \
            --output valuation/relative_valuation/output"
    done

    step "Generating relative valuation plots..."
    for entry in "${targets_and_peers[@]}"; do
        local target="${entry%%:*}"
        dockpy "valuation/relative_valuation/python/viz/plot_relative.py \
            --input valuation/relative_valuation/output/relative_result_${target}.json"
    done
}

mod_dividend_income() {
    local tickers="JNJ,KO,PEP,PG,VZ,MO"

    if ! $SKIP_FETCH; then
        step "Fetching dividend data..."
        IFS=',' read -ra arr <<< "$tickers"
        for t in "${arr[@]}"; do
            dockpy "valuation/dividend_income/python/fetch/fetch_dividend_data.py \
                --ticker $t --output valuation/dividend_income/data"
        done
    fi

    step "Running dividend analysis..."
    IFS=',' read -ra arr <<< "$tickers"
    for t in "${arr[@]}"; do
        dock "dune exec valuation/dividend_income/ocaml/bin/main.exe -- \
            --ticker $t --data valuation/dividend_income/data \
            --output valuation/dividend_income/output"
    done

    step "Generating dividend plots..."
    for t in "${arr[@]}"; do
        dockpy "valuation/dividend_income/python/viz/plot_dividend.py \
            --input valuation/dividend_income/output/dividend_result_${t}.json"
    done
}

mod_analyst_upside() {
    local tickers="NVDA,MSFT,GOOGL,META,AMD,AVGO,PLTR,ARM,MRVL,CRWD,XOM,CVX,COP,SLB,EOG,MPC,OXY,DVN,HAL,FANG"

    step "Fetching analyst targets..."
    dockpy "valuation/analyst_upside/python/fetch_targets.py \
        --tickers $tickers --output valuation/analyst_upside/output/analyst_targets.json"

    step "Generating analyst upside plot..."
    dockpy "valuation/analyst_upside/python/viz/plot_upside.py \
        --input valuation/analyst_upside/output/analyst_targets.json \
        --output-dir valuation/analyst_upside/output"
}

mod_etf_analysis() {
    local tickers="SPY,QQQ,JEPI,SCHD"

    if ! $SKIP_FETCH; then
        step "Fetching ETF data..."
        IFS=',' read -ra arr <<< "$tickers"
        for t in "${arr[@]}"; do
            dockpy "valuation/etf_analysis/python/fetch/fetch_etf_data.py $t"
        done
    fi

    step "Running ETF analysis..."
    IFS=',' read -ra arr <<< "$tickers"
    for t in "${arr[@]}"; do
        dock "dune exec valuation/etf_analysis/ocaml/bin/main.exe -- \
            --holdings 10 valuation/etf_analysis/data/etf_data_${t}.json"
    done

    step "Generating ETF plots..."
    for t in "${arr[@]}"; do
        dockpy "valuation/etf_analysis/python/viz/plot_etf.py \
            --input valuation/etf_analysis/output/etf_result_${t}.json"
    done
}

# --- Pricing modules ---

mod_regime_downside() {
    local tickers="AMZN,CBOE,CVX,IBKR,JPM,LLY,TAC"

    if ! $SKIP_FETCH; then
        step "Fetching benchmark + asset data..."
        dockpy "pricing/regime_downside/python/fetch/fetch_benchmark.py"
        dockpy "pricing/regime_downside/python/fetch/fetch_assets.py $tickers"
    fi

    step "Running regime downside optimization..."
    # Use -start 2000 to evaluate only the most recent ~500 days
    # (full dataset is ~2500 days from 2015). Keeps runtime under 5 min.
    dock "dune exec regime_downside -- \
        -tickers $tickers -lookback 63 -start 2000 -init equal_20"

    step "Generating plots..."
    dockpy "pricing/regime_downside/python/viz/plot_results.py"
}

mod_pairs_trading() {
    local pairs="GLD:GDX CCJ:URA"

    step "Running cointegration analysis..."
    dock "dune exec pairs_trading"

    for pair in $pairs; do
        local t1="${pair%%:*}"
        local t2="${pair##*:}"

        if ! $SKIP_FETCH; then
            step "Fetching pair data ($t1/$t2)..."
            dockpy "pricing/pairs_trading/python/fetch/fetch_pairs.py \
                --ticker1 $t1 --ticker2 $t2 --days 252"
        fi

        step "Generating pairs plot ($t1/$t2)..."
        dockpy "pricing/pairs_trading/python/viz/plot_pairs.py \
            --ticker1 $t1 --ticker2 $t2"
    done
}

mod_liquidity() {
    if ! $SKIP_FETCH; then
        step "Fetching liquidity data..."
        dockpy "pricing/liquidity/python/fetch/fetch_liquidity_data.py"
    fi

    step "Running liquidity analysis..."
    dock "dune exec liquidity_exe -- \
        --data pricing/liquidity/data/market_data.json \
        --output pricing/liquidity/output/liquidity_results.json"

    step "Generating liquidity dashboard..."
    dockpy "pricing/liquidity/python/viz/plot_liquidity.py"
}

mod_dispersion_trading() {
    if ! $SKIP_FETCH; then
        step "Fetching dispersion data..."
        dockpy "pricing/dispersion_trading/python/fetch/fetch_options.py \
            --index SPY --constituents AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,JPM,V,UNH --days 30"
    fi

    step "Running dispersion analysis..."
    dock "dune exec dispersion_trading"

    step "Generating dispersion plot..."
    dockpy "pricing/dispersion_trading/python/viz/plot_dispersion.py"
}

mod_gamma_scalping() {
    if ! $SKIP_FETCH; then
        step "Fetching intraday data for SPY..."
        dockpy "pricing/gamma_scalping/python/fetch/fetch_intraday.py --ticker SPY --days 5"
    fi

    step "Running gamma scalping simulation..."
    dock "dune exec gamma_scalping -- \
        -ticker SPY -position straddle -strike 0 -expiry 30 -iv 0.20 \
        -strategy threshold -threshold 0.10"

    step "Generating gamma scalping plots..."
    dockpy "pricing/gamma_scalping/python/viz/plot_pnl.py --ticker SPY"
}

mod_volatility_arbitrage() {
    local ticker="TSLA"

    if ! $SKIP_FETCH; then
        step "Fetching OHLC data for $ticker..."
        dockpy "pricing/volatility_arbitrage/python/fetch/fetch_historical.py --ticker $ticker"
    fi

    step "Running vol arb analysis..."
    dock "dune exec volatility_arbitrage -- -ticker $ticker -operation all"

    step "Generating vol arb plot..."
    dockpy "pricing/volatility_arbitrage/python/viz/plot_iv_vs_rv.py --ticker $ticker"
}

mod_variance_swaps() {
    local ticker="SPY"

    if ! $SKIP_FETCH; then
        step "Fetching variance swap data for $ticker..."
        dockpy "pricing/variance_swaps/python/fetch_data.py \
            --ticker $ticker --lookback 365 --output pricing/variance_swaps/data"
    fi

    step "Running variance swap operations..."
    dock "dune exec variance_swaps -- \
        -ticker $ticker -op price -horizon 30"
    dock "dune exec variance_swaps -- \
        -ticker $ticker -op vrp -horizon 30 -estimator cc -forecast historical"
    dock "dune exec variance_swaps -- \
        -ticker $ticker -op signal -horizon 30 -estimator cc -forecast historical"
    dock "dune exec variance_swaps -- \
        -ticker $ticker -op backtest -horizon 30 -estimator cc -forecast historical"
    dock "dune exec variance_swaps -- \
        -ticker $ticker -op vrp -horizon 30 -estimator yz -forecast garch"
    dock "dune exec variance_swaps -- \
        -ticker $ticker -op signal -horizon 30 -estimator yz -forecast garch"
    dock "dune exec variance_swaps -- \
        -ticker $ticker -op backtest -horizon 30 -estimator yz -forecast garch"

    step "Generating VRP plots..."
    dockpy "pricing/variance_swaps/python/viz_vrp.py \
        --vrp pricing/variance_swaps/output/${ticker}_vrp_cc_historical.csv \
        --signals pricing/variance_swaps/output/${ticker}_signal_cc_historical.csv \
        --output-dir pricing/variance_swaps/output \
        --estimator cc --forecast historical"
    dockpy "pricing/variance_swaps/python/viz_vrp.py \
        --vrp pricing/variance_swaps/output/${ticker}_vrp_yz_garch.csv \
        --signals pricing/variance_swaps/output/${ticker}_signal_yz_garch.csv \
        --output-dir pricing/variance_swaps/output \
        --estimator yz --forecast garch"
}

mod_skew_trading() {
    local ticker="TSLA"

    if ! $SKIP_FETCH; then
        step "Fetching skew data for $ticker..."
        dockpy "pricing/skew_trading/python/fetch/fetch_underlying.py \
            --ticker $ticker --output-dir pricing/skew_trading/data"
        dockpy "pricing/skew_trading/python/fetch/fetch_options.py \
            --ticker $ticker --output-dir pricing/skew_trading/data"
        dockpy "pricing/skew_trading/python/fetch/compute_skew_timeseries.py \
            --ticker $ticker --data-dir pricing/skew_trading/data --expiry 30"
    fi

    step "Running skew analysis..."
    dock "dune exec skew_trading -- -ticker $ticker -op measure -expiry 30"
    dock "dune exec skew_trading -- -ticker $ticker -op signal"
    dock "dune exec skew_trading -- -ticker $ticker -op backtest"

    step "Generating skew plots..."
    dockpy "pricing/skew_trading/python/viz/plot_smile.py \
        --ticker $ticker --data-dir pricing/skew_trading/data --output-dir pricing/skew_trading/output"
    dockpy "pricing/skew_trading/python/viz/plot_skew_ts.py \
        --ticker $ticker --data-dir pricing/skew_trading/data --output-dir pricing/skew_trading/output"
    dockpy "pricing/skew_trading/python/viz/plot_pnl.py \
        --ticker $ticker --data-dir pricing/skew_trading/output --output-dir pricing/skew_trading/output"
}

mod_skew_verticals() {
    local tickers="AAPL,PYPL"

    IFS=',' read -ra arr <<< "$tickers"
    for ticker in "${arr[@]}"; do
        if ! $SKIP_FETCH; then
            step "Fetching options chain for $ticker..."
            dockpy "pricing/skew_verticals/python/fetch/fetch_options_chain.py --ticker $ticker"
            dockpy "pricing/skew_verticals/python/fetch/fetch_prices.py --ticker $ticker"
        fi

        step "Running skew verticals scanner for $ticker..."
        dock "dune exec skew_verticals -- $ticker"

        step "Generating spread analysis plot for $ticker..."
        dockpy "pricing/skew_verticals/python/viz/plot_spread.py \
            -t $ticker -d pricing/skew_verticals/data \
            -s pricing/skew_verticals/output -o pricing/skew_verticals/output/plots"
    done
}

mod_market_regime_forecast() {
    local ticker="SPY"

    if ! $SKIP_FETCH; then
        step "Fetching regime forecast data..."
        dockpy "pricing/market_regime_forecast/python/fetch/fetch_prices.py \
            --ticker $ticker --output pricing/market_regime_forecast/data/prices_${ticker}.json"
    fi

    step "Running regime forecast (all models)..."
    for model in basic ms-garch bocpd gp; do
        dock "dune exec market_regime_forecast -- \
            pricing/market_regime_forecast/data/prices_${ticker}.json \
            --model $model \
            --output pricing/market_regime_forecast/output/forecast_${ticker}_${model}.json"
    done

    step "Generating regime analysis plot..."
    dockpy "pricing/market_regime_forecast/python/viz/plot_regime.py --ticker $ticker \
        --basic pricing/market_regime_forecast/output/forecast_${ticker}_basic.json \
        --ms-garch pricing/market_regime_forecast/output/forecast_${ticker}_ms-garch.json \
        --bocpd pricing/market_regime_forecast/output/forecast_${ticker}_bocpd.json \
        --gp pricing/market_regime_forecast/output/forecast_${ticker}_gp.json \
        --output-dir pricing/market_regime_forecast/output"
}

mod_options_hedging() {
    local ticker="BMNR"

    if ! $SKIP_FETCH; then
        step "Fetching underlying + option chain..."
        dockpy "pricing/options_hedging/python/fetch/fetch_underlying.py --ticker $ticker"
        dockpy "pricing/options_hedging/python/fetch/fetch_options.py --ticker $ticker"

        step "Calibrating vol surfaces (SVI + SABR)..."
        dockpy "pricing/options_hedging/python/calibrate_vol_surface.py --ticker $ticker --model both"
    fi

    step "Running hedge analysis..."
    dock "dune exec options_hedging -- -ticker $ticker -position 100 -expiry 90"

    step "Generating options hedging plots..."
    dockpy "pricing/options_hedging/python/viz/plot_payoffs.py --ticker $ticker"
    dockpy "pricing/options_hedging/python/viz/plot_frontier.py --ticker $ticker"
    dockpy "pricing/options_hedging/python/viz/plot_greeks.py --ticker $ticker"
    dockpy "pricing/options_hedging/python/viz/plot_vol_surface.py --ticker $ticker"
}

mod_fx_hedging() {
    local contracts="M6S ETH"

    # Seed sample portfolio: CHF investor with USD equities + ETH
    step "Creating sample portfolio..."
    mkdir -p pricing/fx_hedging/data
    cat > pricing/fx_hedging/data/portfolio.csv << 'CSVEOF'
ticker,quantity
AMZN,310
NVDA,245
META,34
MSFT,50
COST,9
AAPL,13
GOOGL,8
JPM,9
ETH-USD,21
CSVEOF

    if ! $SKIP_FETCH || [[ ! -f pricing/fx_hedging/data/met_spot.csv ]]; then
        step "Enriching portfolio (home currency: CHF)..."
        dockpy "pricing/fx_hedging/python/fetch/enrich_portfolio.py \
            pricing/fx_hedging/data/portfolio.csv --home-currency CHF"

        step "Fetching FX data for $contracts..."
        for c in $contracts; do
            dockpy "pricing/fx_hedging/python/fetch/fetch_fx_data.py $c"
        done
    fi

    step "Running FX exposure analysis..."
    dock "dune exec fx_hedging -- -operation exposure"

    step "Running hedge backtests..."
    for c in $contracts; do
        dock "dune exec fx_hedging -- -operation backtest -contract $c"
    done

    step "Generating hedge performance plots..."
    for c in $contracts; do
        dockpy "pricing/fx_hedging/python/viz/plot_hedge_performance.py $c \
            --output pricing/fx_hedging/output/${c}_hedge_performance.png"
    done

    step "Generating exposure analysis plot..."
    dockpy "pricing/fx_hedging/python/viz/plot_exposure_analysis.py \
        --output pricing/fx_hedging/output/exposure_analysis.png \
        --home-currency CHF"
}

mod_earnings_vol() {
    local tickers="NVDA AVGO"

    for ticker in $tickers; do
        if ! $SKIP_FETCH; then
            step "Fetching earnings data for $ticker..."
            dockpy "pricing/earnings_vol/python/fetch/fetch_earnings.py --ticker $ticker"
            dockpy "pricing/earnings_vol/python/fetch/fetch_iv_term.py --ticker $ticker"
        fi

        step "Running earnings vol scanner for $ticker..."
        dock "dune exec earnings_vol -- \
            -ticker $ticker -account 10000 -kelly 0.10 -structure calendar"

        step "Generating earnings vol plot for $ticker..."
        dockpy "pricing/earnings_vol/python/viz/plot_earnings_vol.py \
            --ticker $ticker --data-dir pricing/earnings_vol/data \
            --output-dir pricing/earnings_vol/output/plots"
    done
}

mod_forward_factor() {
    local ticker="AAPL"

    if ! $SKIP_FETCH; then
        step "Fetching options chain data..."
        dockpy "pricing/forward_factor/python/fetch_chains.py"
    fi

    step "Running forward factor scanner..."
    dock "dune exec forward_factor"

    step "Generating forward factor plot..."
    dockpy "pricing/forward_factor/python/viz/plot_forward_factor.py \
        --ticker $ticker --output-dir pricing/forward_factor/output/plots"
}

mod_pre_earnings_straddle() {
    local tickers="NVDA AVGO"

    if ! $SKIP_FETCH; then
        step "Training ML model..."
        dockpy "pricing/pre_earnings_straddle/python/train/train_model.py"
    fi

    for ticker in $tickers; do
        if ! $SKIP_FETCH; then
            step "Fetching earnings history for $ticker..."
            dockpy "pricing/pre_earnings_straddle/python/fetch/fetch_earnings_data.py \
                --ticker $ticker --output-dir pricing/pre_earnings_straddle/data"

            step "Fetching straddle data for $ticker..."
            dockpy "pricing/pre_earnings_straddle/python/fetch/fetch_straddle_data.py --ticker $ticker"
        fi

        step "Running pre-earnings scanner for $ticker..."
        dock "dune exec pre_earnings_straddle -- $ticker"

        step "Generating straddle analysis plot for $ticker..."
        dockpy "pricing/pre_earnings_straddle/python/viz/plot_straddle.py \
            -t $ticker -d pricing/pre_earnings_straddle/data \
            -o pricing/pre_earnings_straddle/output/plots"
    done
}

mod_perpetual_futures() {
    local symbol="BTCUSDT"

    if ! $SKIP_FETCH; then
        step "Fetching perpetual futures data..."
        dockpy "pricing/perpetual_futures/python/fetch/fetch_perp_data.py \
            --symbol $symbol --exchange binance"
    fi

    step "Running perpetual futures pricing..."
    dock "dune exec perpetual_futures -- \
        --data pricing/perpetual_futures/data/market_data.json \
        --type linear --kappa 1.095 --r_a 0.05 --r_b 0.0 \
        --output pricing/perpetual_futures/output/analysis.json"

    step "Generating perpetual futures plot..."
    dockpy "pricing/perpetual_futures/python/viz/plot_perpetual.py \
        --input pricing/perpetual_futures/output/analysis.json"
}

mod_tail_risk_forecast() {
    local tickers="SPY,SOXL"

    IFS=',' read -ra arr <<< "$tickers"
    for ticker in "${arr[@]}"; do
        if ! $SKIP_FETCH; then
            step "Fetching intraday data for $ticker..."
            dockpy "pricing/tail_risk_forecast/python/fetch/fetch_intraday.py --ticker $ticker --days 120"
        fi

        step "Running tail risk forecast for $ticker..."
        dock "dune exec tail_risk_forecast -- --ticker $ticker --json"

        step "Generating tail risk plot for $ticker..."
        dockpy "pricing/tail_risk_forecast/python/viz/plot_forecast.py \
            --input pricing/tail_risk_forecast/output/forecast_${ticker}.json"
    done
}

# --- Alternative modules ---

mod_macro_dashboard() {
    # Macro dashboard requires a FRED API key
    local has_key=false
    if [[ -n "${FRED_API_KEY:-}" ]]; then
        has_key=true
    elif [[ -f .env ]] && grep -q '^FRED_API_KEY=.\+' .env 2>/dev/null; then
        has_key=true
    fi
    if ! $has_key; then
        step "Skipping — no FRED_API_KEY found in environment or .env"
        step "Get a free key at: https://fred.stlouisfed.org/docs/api/api_key.html"
        return 0
    fi

    if ! $SKIP_FETCH; then
        step "Fetching macro data..."
        dockpy "alternative/macro_dashboard/python/fetch/fetch_macro.py"
    fi

    step "Classifying macro environment..."
    dock "dune exec macro_dashboard -- alternative/macro_dashboard/data/macro_data.json \
        --output alternative/macro_dashboard/output/environment.json"

    step "Generating macro dashboard..."
    dockpy "alternative/macro_dashboard/python/viz/plot_dashboard.py"
}

mod_watchlist() {
    # Always rebuild sample portfolio for showcase
    step "Creating sample watchlist portfolio..."
    rm -f monitoring/watchlist/data/portfolio.json
    mkdir -p monitoring/watchlist/data

    # Core longs — big winners with targets
    dockpy "monitoring/watchlist/python/manage.py add NVDA --type long --shares 100 --cost 125 --sell-target 250 --stop-loss 160"
    dockpy "monitoring/watchlist/python/manage.py add AVGO --type long --shares 40 --cost 180 --sell-target 500 --stop-loss 280"
    dockpy "monitoring/watchlist/python/manage.py add PLTR --type long --shares 200 --cost 25 --sell-target 200 --stop-loss 100"
    dockpy "monitoring/watchlist/python/manage.py add META --type long --shares 30 --cost 320 --sell-target 900 --stop-loss 550"

    # Value / income longs
    dockpy "monitoring/watchlist/python/manage.py add COST --type long --shares 15 --cost 800 --sell-target 1100 --stop-loss 900"
    dockpy "monitoring/watchlist/python/manage.py add XOM --type long --shares 80 --cost 95 --sell-target 130 --stop-loss 90"

    # Short positions — bearish bets
    dockpy "monitoring/watchlist/python/manage.py add SMCI --type short --shares 50 --cost 35 --buy-target 20 --stop-loss 55"
    dockpy "monitoring/watchlist/python/manage.py add INTC --type short --shares 100 --cost 50 --buy-target 30 --stop-loss 55"

    # Watching — waiting for entry
    dockpy "monitoring/watchlist/python/manage.py add AMD --type watching --buy-target 160 --sell-target 300"
    dockpy "monitoring/watchlist/python/manage.py add CRWD --type watching --buy-target 300 --sell-target 600"

    # Add thesis arguments
    dockpy "monitoring/watchlist/python/manage.py thesis NVDA --bull 'Data center demand accelerating' --weight 9"
    dockpy "monitoring/watchlist/python/manage.py thesis NVDA --bear 'Valuation stretched at 60x PE' --weight 6"
    dockpy "monitoring/watchlist/python/manage.py thesis PLTR --bull 'Government AI contracts expanding' --weight 8"
    dockpy "monitoring/watchlist/python/manage.py thesis PLTR --bear 'Stock-based compensation dilution' --weight 5"
    dockpy "monitoring/watchlist/python/manage.py thesis SMCI --bear 'Accounting concerns and audit risk' --weight 8"
    dockpy "monitoring/watchlist/python/manage.py thesis SMCI --bull 'AI server demand tailwind' --weight 4"
    dockpy "monitoring/watchlist/python/manage.py thesis META --bull 'AI monetization via ads' --weight 8"
    dockpy "monitoring/watchlist/python/manage.py thesis META --bear 'Metaverse capex drag' --weight 5"
    dockpy "monitoring/watchlist/python/manage.py thesis INTC --bear 'Foundry losses mounting' --weight 9"
    dockpy "monitoring/watchlist/python/manage.py thesis INTC --bull 'CHIPS Act subsidies' --weight 4"

    if ! $SKIP_FETCH || [[ ! -f monitoring/watchlist/data/prices.json ]]; then
        step "Fetching market prices..."
        dockpy "monitoring/watchlist/python/fetch/fetch_prices.py"
    fi

    step "Running watchlist analysis..."
    dock "dune exec watchlist -- \
        --portfolio monitoring/watchlist/data/portfolio.json \
        --prices monitoring/watchlist/data/prices.json \
        --output monitoring/watchlist/output/analysis.json"

    step "Generating watchlist dashboard..."
    dockpy "monitoring/watchlist/python/viz/plot_watchlist.py \
        --input monitoring/watchlist/output/analysis.json"
}

mod_earnings_calendar() {
    local tickers="AMZN,AVGO,CRM,CVX,HD,JPM,LLY,META,MSFT,NVDA"

    if ! $SKIP_FETCH; then
        step "Fetching earnings calendar..."
        dockpy "monitoring/earnings_calendar/python/fetch/fetch_earnings_calendar.py \
            --tickers $tickers --days-ahead 30"
    fi

    step "Generating earnings calendar dashboard..."
    dockpy "monitoring/earnings_calendar/python/viz/plot_earnings_calendar.py \
        --input monitoring/earnings_calendar/data/earnings_calendar.json"
}

mod_systematic_risk_signals() {
    local tickers="SPY,QQQ,IWM,EFA,AGG,GLD"

    if ! $SKIP_FETCH; then
        step "Fetching returns data..."
        dockpy "pricing/systematic_risk_signals/python/fetch/fetch_returns.py \
            --tickers $tickers --lookback 504"
    fi

    step "Running risk signals analysis..."
    dock "dune exec systematic_risk_signals -- \
        --data pricing/systematic_risk_signals/data/returns.json \
        --output pricing/systematic_risk_signals/output \
        --json"

    step "Generating risk signals dashboard..."
    dockpy "pricing/systematic_risk_signals/python/viz/plot_risk_signals.py \
        --input pricing/systematic_risk_signals/output/risk_signals.json"
}

mod_alt_data() {
    local tickers="AAPL NVDA TSLA MSFT META AMZN GOOGL"

    if ! $SKIP_FETCH; then
        step "Fetching insider trading data..."
        dockpy "alternative/insider_trading/python/fetch_form4.py $tickers"

        step "Fetching options flow data..."
        dockpy "alternative/options_flow/python/fetch_flow.py $tickers"

        step "Fetching short interest data..."
        dockpy "alternative/short_interest/python/fetch_short_interest.py $tickers"

        step "Fetching Google Trends data..."
        dockpy "alternative/google_trends/python/fetch_trends.py $tickers"

        step "Fetching SEC filings..."
        dockpy "alternative/sec_filings/python/fetch_filings.py $tickers"
    fi

    step "Analyzing insider trading..."
    dockpy "alternative/insider_trading/python/analyze_insider.py --quiet"

    step "Analyzing options flow..."
    dockpy "alternative/options_flow/python/analyze_flow.py --quiet"

    step "Analyzing short interest..."
    dockpy "alternative/short_interest/python/analyze_shorts.py --quiet"

    step "Analyzing Google Trends..."
    dockpy "alternative/google_trends/python/analyze_trends.py --quiet"

    step "Analyzing SEC filings..."
    dockpy "alternative/sec_filings/python/analyze_filings.py --quiet"

    step "Running NLP sentiment pipeline (SEC filings)..."
    dockpy "alternative/nlp_sentiment/python/pipeline.py $tickers \
        --skip-transcripts --quarters 4"

    step "Importing Discord data..."
    dockpy "alternative/nlp_sentiment/python/fetch/import_discord_export.py \
        --dir alternative/nlp_sentiment/data/discord_exports \
        --output alternative/nlp_sentiment/data/discord"

    step "Analyzing Discord sentiment..."
    dockpy "alternative/nlp_sentiment/python/analyze_discord.py"

    step "Plotting Discord sentiment..."
    dockpy "alternative/nlp_sentiment/python/viz/plot_discord.py"

    step "Generating alt data dashboard..."
    dockpy "alternative/python/viz/plot_alt_data.py \
        --output alternative/output/alt_data_dashboard.png"
}

# ─── Module registry ──────────────────────────────────────────────────────────

ALL_MODULES=(
    # Valuation
    "dcf_deterministic"
    "dcf_probabilistic"
    "dcf_reit"
    "crypto_treasury"
    "garp_peg"
    "growth_analysis"
    "normalized_multiples"
    "relative_valuation"
    "dividend_income"
    "analyst_upside"
    "etf_analysis"
    # Pricing
    "regime_downside"
    "pairs_trading"
    "liquidity"
    "dispersion_trading"
    "gamma_scalping"
    "volatility_arbitrage"
    "variance_swaps"
    "skew_trading"
    "skew_verticals"
    "market_regime_forecast"
    "options_hedging"
    "fx_hedging"
    "earnings_vol"
    "forward_factor"
    "pre_earnings_straddle"
    "perpetual_futures"
    "tail_risk_forecast"
    "systematic_risk_signals"
    # Alternative
    "macro_dashboard"
    "alt_data"
    # Monitoring
    "watchlist"
    "earnings_calendar"
)

if [[ "$LIST_MODE" == true ]]; then
    echo "Available modules:"
    for m in "${ALL_MODULES[@]}"; do
        echo "  $m"
    done
    exit 0
fi

# ─── Execution modes ─────────────────────────────────────────────────────────

run_sequential() {
    for mod in "${ALL_MODULES[@]}"; do
        run_module "$mod" "mod_${mod}"
    done
}

run_parallel() {
    local tmpdir
    tmpdir=$(mktemp -d)

    # Determine job count
    local jobs=$MAX_JOBS
    if (( jobs == 0 )); then
        jobs=$(( $(nproc 2>/dev/null || echo 4) - 2 ))
        (( jobs < 1 )) && jobs=1
    fi

    echo -e "${BOLD}Running with ${jobs} parallel job(s)${NC}"
    echo ""

    local -a pids=()
    local -A pid_mod=()
    local running=0
    local total=0
    local completed=0

    # Count eligible modules
    for mod in "${ALL_MODULES[@]}"; do
        [[ -n "$TARGET_MODULE" && "$TARGET_MODULE" != "$mod" ]] && continue
        total=$((total + 1))
    done

    # Drain finished jobs, print their status, update counters
    drain_finished() {
        local -a still_running=()
        for pid in "${pids[@]}"; do
            if kill -0 "$pid" 2>/dev/null; then
                still_running+=("$pid")
            else
                wait "$pid" 2>/dev/null
                local ec=$?
                local mod_name="${pid_mod[$pid]}"
                completed=$((completed + 1))
                if [[ $ec -eq 0 ]]; then
                    echo -e "  ${GREEN}✓${NC} ${mod_name} ${CYAN}[${completed}/${total}]${NC}"
                else
                    echo -e "  ${RED}✗${NC} ${mod_name} ${CYAN}[${completed}/${total}]${NC}"
                fi
            fi
        done
        pids=("${still_running[@]}")
        running=${#pids[@]}
    }

    for mod in "${ALL_MODULES[@]}"; do
        [[ -n "$TARGET_MODULE" && "$TARGET_MODULE" != "$mod" ]] && continue

        # Wait for a slot
        while (( running >= jobs )); do
            wait -n "${pids[@]}" 2>/dev/null || true
            drain_finished
        done

        # Launch module in background subshell
        (
            if "mod_${mod}" > "$tmpdir/${mod}.log" 2>&1; then
                echo "ok" > "$tmpdir/${mod}.status"
            else
                echo "fail" > "$tmpdir/${mod}.status"
            fi
        ) &
        local pid=$!
        pids+=("$pid")
        pid_mod[$pid]="$mod"
        running=$((running + 1))
        echo -e "  ${CYAN}⟳${NC} Started: ${BOLD}${mod}${NC}"
    done

    # Wait for all remaining jobs
    for pid in "${pids[@]}"; do
        wait "$pid" 2>/dev/null
        local ec=$?
        local mod_name="${pid_mod[$pid]}"
        completed=$((completed + 1))
        if [[ $ec -eq 0 ]]; then
            echo -e "  ${GREEN}✓${NC} ${mod_name} ${CYAN}[${completed}/${total}]${NC}"
        else
            echo -e "  ${RED}✗${NC} ${mod_name} ${CYAN}[${completed}/${total}]${NC}"
        fi
    done
    pids=()

    # Collect results
    for mod in "${ALL_MODULES[@]}"; do
        [[ -n "$TARGET_MODULE" && "$TARGET_MODULE" != "$mod" ]] && continue
        local status
        status=$(cat "$tmpdir/${mod}.status" 2>/dev/null || echo "fail")
        if [[ "$status" == "ok" ]]; then
            SUCCEEDED_MODULES+=("$mod")
        else
            FAILED_MODULES+=("$mod")
        fi
    done

    # Dump failed module logs
    if [[ ${#FAILED_MODULES[@]} -gt 0 ]]; then
        echo ""
        echo -e "${RED}─── Failed module logs ───${NC}"
        for mod in "${FAILED_MODULES[@]}"; do
            echo -e "\n${RED}=== ${mod} ===${NC}"
            cat "$tmpdir/${mod}.log" 2>/dev/null || echo "(no log)"
        done
    fi

    rm -rf "$tmpdir"
}

# ─── Main ─────────────────────────────────────────────────────────────────────

echo -e "${BOLD}Regenerating showcase plots for README.md${NC}"
if $DRY_RUN; then
    echo -e "${YELLOW}[DRY RUN MODE — no commands will be executed]${NC}"
fi
if $SKIP_FETCH; then
    echo -e "${YELLOW}[SKIP FETCH — using existing data]${NC}"
fi
echo ""

# Detect execution mode (Docker or native fallback)
if ! $DRY_RUN; then
    detect_exec_mode
fi

if (( MAX_JOBS == 1 )); then
    run_sequential
else
    run_parallel
fi

# ─── Summary ──────────────────────────────────────────────────────────────────

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════${NC}"
echo -e "${BOLD}Summary${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════${NC}"

if [[ ${#SUCCEEDED_MODULES[@]} -gt 0 ]]; then
    echo -e "${GREEN}Succeeded (${#SUCCEEDED_MODULES[@]}):${NC} ${SUCCEEDED_MODULES[*]}"
fi
if [[ ${#FAILED_MODULES[@]} -gt 0 ]]; then
    echo -e "${RED}Failed (${#FAILED_MODULES[@]}):${NC} ${FAILED_MODULES[*]}"
fi

if [[ ${#FAILED_MODULES[@]} -eq 0 ]]; then
    echo ""
    echo -e "${GREEN}All showcase plots regenerated successfully.${NC}"
else
    echo ""
    echo -e "${YELLOW}Some modules failed. Check logs above for details.${NC}"
    exit 1
fi
