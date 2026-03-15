#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m' # No Color

# Helper functions
print_header() {
    echo -e "\n${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Prompt for a ticker symbol, retrying until non-empty (or using default).
# Usage: read_ticker ["prompt text"] [default_ticker]
# Sets the variable $ticker.
read_ticker() {
    local default_ticker="${2:-}"
    local prompt
    if [[ -n "$default_ticker" ]]; then
        prompt="${1:-Enter ticker symbol (default: ${default_ticker}):}"
    else
        prompt="${1:-Enter ticker symbol (e.g., AAPL):}"
    fi
    while true; do
        echo -ne "${YELLOW}${prompt}${NC} "
        read -r ticker
        if [[ -z "$ticker" && -n "$default_ticker" ]]; then
            ticker="$default_ticker"
            return 0
        fi
        if [[ -n "$ticker" ]]; then
            ticker=$(echo "$ticker" | tr '[:lower:]' '[:upper:]')
            return 0
        fi
        print_error "Ticker cannot be empty, please try again"
    done
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Prompt for ticker source: manual entry, all_liquid, or a price-segment file.
# Sets the variable $ticker_arg to pass to --tickers.
# Usage: pick_ticker_source "default_ticker"
pick_ticker_source() {
    local default_ticker="${1:-TSLA}"
    local segment_dir="pricing/liquidity/data"

    echo -e "\n${YELLOW}Ticker source:${NC}"
    echo -e "  ${GREEN}1)${NC} Enter ticker(s) manually (default: $default_ticker)"
    echo -e "  ${GREEN}2)${NC} All liquid optionables (liquid_options.txt)"

    # List available segment files (prefer liquid_options segments, fall back to liquid_tickers)
    local segments=()
    if compgen -G "$segment_dir/liquid_options_*_USD.txt" > /dev/null 2>&1; then
        while IFS= read -r f; do
            segments+=("$f")
        done < <(ls "$segment_dir"/liquid_options_*_USD.txt 2>/dev/null | sort -V)
    elif compgen -G "$segment_dir/liquid_tickers_*_USD.txt" > /dev/null 2>&1; then
        while IFS= read -r f; do
            segments+=("$f")
        done < <(ls "$segment_dir"/liquid_tickers_*_USD.txt 2>/dev/null | sort -V)
    fi

    if [[ ${#segments[@]} -gt 0 ]]; then
        echo -e "  ${GREEN}3)${NC} Price segment (pick from available segments)"
    fi

    echo ""
    echo -e "${YELLOW}Enter choice (default: 1):${NC} "
    read -r source_choice

    case ${source_choice:-1} in
        1)
            echo -e "${YELLOW}Enter ticker(s), comma-separated (default: $default_ticker):${NC} "
            read -r ticker_arg
            ticker_arg=${ticker_arg:-$default_ticker}
            ;;
        2)
            ticker_arg="all_liquid"
            local count=0
            if [[ -f "$segment_dir/liquid_options.txt" ]]; then
                count=$(wc -l < "$segment_dir/liquid_options.txt" | tr -d ' ')
            fi
            print_info "Using all $count liquid optionables"
            ;;
        3)
            if [[ ${#segments[@]} -eq 0 ]]; then
                print_error "No segment files found. Run 'Subset Liquid Tickers by Price' first."
                ticker_arg=""
                return 1
            fi
            echo ""
            for i in "${!segments[@]}"; do
                local fname
                fname=$(basename "${segments[$i]}" .txt)
                local count
                count=$(wc -l < "${segments[$i]}" | tr -d ' ')
                # Pretty-print: liquid_tickers_1_to_10_USD -> $1-$10
                local label
                label=$(echo "$fname" | sed 's/liquid_options_//;s/liquid_tickers_//;s/_USD//;s/\([0-9]*\)_to_\([0-9]*\)/$\1-$\2/;s/^above_/above $/')
                echo -e "  ${GREEN}$((i+1)))${NC} $label ($count tickers)"
            done
            echo ""
            echo -e "${YELLOW}Pick a segment:${NC} "
            read -r seg_choice
            seg_choice=${seg_choice:-1}
            local idx=$((seg_choice - 1))
            if [[ $idx -ge 0 && $idx -lt ${#segments[@]} ]]; then
                ticker_arg="${segments[$idx]}"
                local count
                count=$(wc -l < "$ticker_arg" | tr -d ' ')
                print_info "Using segment: $(basename "$ticker_arg") ($count tickers)"
            else
                print_error "Invalid choice"
                ticker_arg=""
                return 1
            fi
            ;;
        *)
            print_error "Invalid choice"
            ticker_arg=""
            return 1
            ;;
    esac
}

# Check if we're in the project root
check_project_root() {
    if [[ ! -f "dune-project" ]] || [[ ! -f "pyproject.toml" ]]; then
        print_error "Please run this script from the atemoya project root directory"
        exit 1
    fi
}

# Check dependencies
check_opam() {
    if command -v opam &> /dev/null; then
        print_success "opam is installed"
        return 0
    else
        print_error "opam is not installed"
        print_info "Install from: https://opam.ocaml.org/doc/Install.html"
        return 1
    fi
}

check_uv() {
    if command -v uv &> /dev/null; then
        print_success "uv is installed"
        return 0
    else
        print_error "uv is not installed"
        print_info "Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
        return 1
    fi
}

check_python() {
    if command -v python3 &> /dev/null; then
        print_success "python3 is installed"
        return 0
    else
        print_error "python3 is not installed"
        return 1
    fi
}

# Installation functions
install_ocaml_deps() {
    print_header "Installing OCaml Dependencies"

    if ! check_opam; then
        return 1
    fi

    # macOS-specific: Install dependencies via Homebrew and set up environment
    if [[ "$OSTYPE" == "darwin"* ]]; then
        print_info "Detected macOS - checking for required packages..."
        if ! command -v brew &> /dev/null; then
            print_warning "Homebrew not found. Please install from: https://brew.sh"
            print_warning "Or install pkg-config and openblas manually before continuing"
        else
            # Install pkg-config if missing
            if ! command -v pkg-config &> /dev/null; then
                print_info "Installing pkg-config via Homebrew..."
                brew install pkg-config
                print_success "pkg-config installed"
            else
                print_success "pkg-config already installed"
            fi

            # Install openblas if missing
            if ! brew list openblas &> /dev/null; then
                print_info "Installing openblas via Homebrew (required for owl)..."
                brew install openblas
                print_success "openblas installed"
            else
                print_success "openblas already installed"
            fi

            # Set PKG_CONFIG_PATH so opam can find openblas
            OPENBLAS_PREFIX=$(brew --prefix openblas)
            export PKG_CONFIG_PATH="${OPENBLAS_PREFIX}/lib/pkgconfig:${PKG_CONFIG_PATH}"
            print_info "PKG_CONFIG_PATH set to: ${OPENBLAS_PREFIX}/lib/pkgconfig"
        fi
    fi

    # Disable exit-on-error temporarily for opam switch detection
    set +e

    # Check if Docker named switch exists (from Dockerfile)
    if opam switch list --short 2>/dev/null | grep -q "^atemoya-build$"; then
        print_info "Using existing Docker opam switch: atemoya-build"
        current_switch=$(opam switch show 2>/dev/null)
        if [[ "$current_switch" != "atemoya-build" ]]; then
            print_info "Activating atemoya-build switch..."
            eval $(opam env --switch=atemoya-build --set-switch)
            print_success "Switch activated: atemoya-build"
        fi
        set -e
    else
        # Check if a local switch exists for this directory
        local_switch_path=$(pwd)
        current_switch=$(opam switch show 2>/dev/null)
        switch_show_result=$?

        # Check if we already have a local switch for this directory activated
        if [[ $switch_show_result -eq 0 ]] && [[ "$current_switch" == "$local_switch_path" ]]; then
            print_info "Using existing local opam switch: $current_switch"
            set -e
        else
            # Check if a local switch exists but isn't activated
            if opam switch list --short 2>/dev/null | grep -q "^${local_switch_path}$"; then
                print_info "Activating existing local switch: $local_switch_path"
                set -e
                eval $(opam env --switch="$local_switch_path" --set-switch)
                print_success "Switch activated: $local_switch_path"
            else
                # No local switch for this directory - create one
                print_warning "No local opam switch found for this project. Creating one..."

                # Use OCaml 5.2.1 as required by the project
                OCAML_VERSION="5.2.1"
                print_info "Creating local opam switch with OCaml ${OCAML_VERSION}..."
                print_info "This may take several minutes..."

                set -e  # Re-enable exit-on-error for the critical operation

                opam switch create . ${OCAML_VERSION} --yes

                if [[ $? -ne 0 ]]; then
                    print_error "Failed to create opam switch"
                    set -e  # Ensure it's re-enabled before returning
                    return 1
                fi

                print_success "Local opam switch created successfully"
                eval $(opam env)

                # On macOS, configure the switch to use PKG_CONFIG_PATH
                if [[ "$OSTYPE" == "darwin"* ]] && [[ -n "${PKG_CONFIG_PATH}" ]]; then
                    print_info "Configuring opam switch to use PKG_CONFIG_PATH..."
                    opam option setenv+="PKG_CONFIG_PATH=${PKG_CONFIG_PATH}"
                    print_success "PKG_CONFIG_PATH configured in opam switch"
                fi
            fi
        fi
    fi

    # On macOS, ensure PKG_CONFIG_PATH is configured in the switch
    if [[ "$OSTYPE" == "darwin"* ]] && [[ -n "${PKG_CONFIG_PATH}" ]]; then
        # Check if we need to set it (might already be set from switch creation)
        current_setenv=$(opam option setenv --safe 2>/dev/null || echo "")
        if [[ ! "$current_setenv" =~ "PKG_CONFIG_PATH" ]]; then
            print_info "Configuring PKG_CONFIG_PATH in opam switch..."
            opam option setenv+="PKG_CONFIG_PATH=${PKG_CONFIG_PATH}"
            print_success "PKG_CONFIG_PATH configured"
        fi
    fi

    print_info "Installing OCaml packages: owl, yojson, csv, ppx_deriving, alcotest..."
    opam install alcotest --yes
    opam install . --deps-only --with-test --yes

    print_success "OCaml dependencies installed"
    print_info "Setting up OCaml environment..."
    eval $(opam env)
    print_success "OCaml environment loaded"
}

install_python_deps() {
    print_header "Installing Python Dependencies"

    if ! check_uv; then
        return 1
    fi

    print_info "Installing Python packages: yfinance, pandas, numpy, matplotlib, seaborn, cvxpy, scipy..."

    # Remove broken .venv if it exists
    if [ -d ".venv" ]; then
        # Try to query the existing Python
        if ! .venv/bin/python3 -c "import sys" &>/dev/null; then
            print_info "Removing broken virtual environment..."
            rm -rf .venv
        fi
    fi

    # Use copy mode to avoid hardlink warnings (especially in Docker)
    export UV_LINK_MODE=copy

    # Use system Python to avoid compatibility issues
    uv sync --python $(which python3)

    print_success "Python dependencies installed"
}

# Build functions
build_project() {
    print_header "Building OCaml Project"

    print_info "Running: opam exec -- dune build"
    opam exec -- dune build

    local build_success=true

    if [[ -f "_build/default/pricing/regime_downside/ocaml/bin/main.exe" ]]; then
        print_success "Pricing model built: regime_downside"
    else
        print_error "Failed to build: pricing/regime_downside"
        build_success=false
    fi

    if [[ -f "_build/default/valuation/dcf_deterministic/ocaml/bin/main.exe" ]]; then
        print_success "Valuation model built: dcf_deterministic"
    else
        print_error "Failed to build: valuation/dcf_deterministic"
        build_success=false
    fi

    if [[ -f "_build/default/valuation/dcf_probabilistic/ocaml/bin/main.exe" ]]; then
        print_success "Valuation model built: dcf_probabilistic"
    else
        print_error "Failed to build: valuation/dcf_probabilistic"
        build_success=false
    fi

    if [[ -f "_build/default/valuation/normalized_multiples/ocaml/bin/main.exe" ]]; then
        print_success "Valuation model built: normalized_multiples"
    else
        print_error "Failed to build: valuation/normalized_multiples"
        build_success=false
    fi

    if [[ -f "_build/default/pricing/tail_risk_forecast/ocaml/bin/main.exe" ]]; then
        print_success "Pricing model built: tail_risk_forecast"
    else
        print_error "Failed to build: pricing/tail_risk_forecast"
        build_success=false
    fi

    if [[ "$build_success" == "false" ]]; then
        return 1
    fi
}

run_tests() {
    print_header "Running Tests"

    print_info "Running: opam exec -- dune test"
    opam exec -- dune test

    print_success "Tests completed"
}

# Data fetching
fetch_benchmark_data() {
    print_header "Fetching S&P 500 Benchmark Data"

    if [[ ! -f ".venv/bin/python3" ]]; then
        print_error "Python virtual environment not found. Run 'Install Python Dependencies' first."
        return 1
    fi

    print_info "Fetching S&P 500 data..."
    .venv/bin/python3 pricing/regime_downside/python/fetch/fetch_benchmark.py

    if [[ -f "pricing/regime_downside/data/sp500_returns.csv" ]]; then
        print_success "Benchmark data saved to: pricing/regime_downside/data/sp500_returns.csv"
    else
        print_error "Failed to fetch benchmark data"
        return 1
    fi
}

fetch_asset_data() {
    print_header "Fetching Asset Data"

    if [[ ! -f ".venv/bin/python3" ]]; then
        print_error "Python virtual environment not found. Run 'Install Python Dependencies' first."
        return 1
    fi

    local default_tickers="AMZN,CBOE,CVX,IBKR,JPM,LLY,TAC"

    echo -e "\n${YELLOW}Enter ticker symbols (comma-separated):${NC}"
    echo -e "${BLUE}Press Enter for default (7 assets): $default_tickers${NC}"
    read -r tickers

    if [[ -z "$tickers" ]]; then
        tickers="$default_tickers"
        print_info "Using default: 7 assets"
    fi

    print_info "Fetching data for: $tickers"
    .venv/bin/python3 pricing/regime_downside/python/fetch/fetch_assets.py "$tickers"

    # Save tickers for future use
    echo "$tickers" > pricing/regime_downside/data/.last_tickers

    print_success "Asset data saved to: pricing/regime_downside/data/"
}

# Helper to detect minimum data length
get_min_data_length() {
    local tickers=$1
    local min_length=999999

    IFS=',' read -ra TICKER_ARRAY <<< "$tickers"
    for ticker in "${TICKER_ARRAY[@]}"; do
        ticker=$(echo "$ticker" | xargs) # trim whitespace
        local file="pricing/regime_downside/data/${ticker}_returns.csv"
        if [[ -f "$file" ]]; then
            local length=$(wc -l < "$file")
            length=$((length - 1)) # subtract header
            if [[ $length -lt $min_length ]]; then
                min_length=$length
            fi
        else
            print_warning "Data file not found: $file"
            return 1
        fi
    done

    echo "$min_length"
}

# Optimization
run_optimization() {
    print_header "Running Portfolio Optimization"

    # Check if we have last fetched tickers
    local default_tickers="AMZN,CBOE,CVX,IBKR,JPM,LLY,TAC"
    if [[ -f "pricing/regime_downside/data/.last_tickers" ]]; then
        default_tickers=$(cat pricing/regime_downside/data/.last_tickers)
        local ticker_count=$(echo "$default_tickers" | tr ',' '\n' | wc -l)
        echo -e "\n${YELLOW}Enter ticker symbols (comma-separated):${NC}"
        echo -e "${BLUE}Press Enter for last fetched ($ticker_count assets): $default_tickers${NC}"
    else
        echo -e "\n${YELLOW}Enter ticker symbols (comma-separated):${NC}"
        echo -e "${BLUE}Press Enter for default (7 assets): $default_tickers${NC}"
    fi

    read -r tickers
    if [[ -z "$tickers" ]]; then
        tickers="$default_tickers"
        local ticker_count=$(echo "$tickers" | tr ',' '\n' | wc -l)
        print_info "Using: $ticker_count assets"
    fi

    # Detect available data
    print_info "Checking available data..."
    local min_days=$(get_min_data_length "$tickers")
    if [[ $? -ne 0 ]] || [[ -z "$min_days" ]]; then
        print_error "Failed to detect data availability. Make sure data is fetched first."
        return 1
    fi

    print_info "Minimum available data: $min_days days"
    echo ""

    # Show abstract timeline to explain the concept
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}Understanding the Timeline:${NC}"
    echo ""
    echo -e "  Your $min_days days of data will be split into three parts:"
    echo ""
    echo -e "  ${BLUE}[────── Warmup ──────${NC}${YELLOW}═ Lookback ═${NC}${GREEN}████ Backtest ████${NC}${BLUE}]${NC}"
    echo ""
    echo -e "  ${BLUE}Warmup (Start Index):${NC}"
    echo -e "    Initial period to reserve for training (days to skip at the start)."
    echo -e "    Larger warmup = shorter backtest, but more recent testing data."
    echo ""
    echo -e "  ${YELLOW}Lookback (Training Window):${NC}"
    echo -e "    Rolling window of historical data used for each optimization step."
    echo -e "    Standard choices: 252 days (1yr), 126 days (6mo), 63 days (3mo)."
    echo ""
    echo -e "  ${GREEN}Backtest (Test Period):${NC}"
    echo -e "    Out-of-sample period where portfolio is evaluated day-by-day."
    echo -e "    ${YELLOW}⚠ Longer backtest = more computationally intensive!${NC}"
    echo -e "    Each day in backtest requires a full portfolio optimization."
    echo ""
    echo -e "  ${BLUE}Formula: Backtest Days = Total Days - Warmup - Lookback${NC}"
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo ""

    # Get initial allocation strategy
    echo -e "${YELLOW}Initial portfolio allocation:${NC}"
    echo -e "${BLUE}  1) 100% cash (let optimizer build position from scratch)${NC}"
    echo -e "${BLUE}  2) Equal weights + 20% cash (balanced starting point)${NC}"
    echo -e "${BLUE}  3) Equal weights + 0% cash (fully invested from start)${NC}"
    echo -e "${BLUE}Press Enter for default (1):${NC}"
    read -r init_choice
    if [[ -z "$init_choice" ]]; then
        init_choice="1"
    fi

    case $init_choice in
        1)
            init_mode="cash"
            print_info "Starting with 100% cash"
            ;;
        2)
            init_mode="equal_20"
            print_info "Starting with equal weights + 20% cash"
            ;;
        3)
            init_mode="equal_0"
            print_info "Starting with equal weights + 0% cash"
            ;;
        *)
            print_error "Invalid choice, using default (100% cash)"
            init_mode="cash"
            ;;
    esac
    echo ""

    # Get lookback window
    echo -e "${YELLOW}Lookback window (rolling training window in days):${NC}"
    echo -e "${BLUE}  How many days of historical data to use for each optimization step.${NC}"
    echo ""
    echo -e "${BLUE}  Common configurations:${NC}"
    echo -e "    252 days (1 year)   - Standard for annual market cycles"
    echo -e "    126 days (6 months) - More responsive to recent trends"
    echo -e "    63 days (3 months)  - Highly adaptive to market changes"
    echo ""
    echo -e "${BLUE}  Press Enter for default: 252 days${NC}"
    read -r lookback
    if [[ -z "$lookback" ]]; then
        lookback="252"
        print_info "Using default: $lookback days (1 year)"
    fi

    # Calculate valid range for start index
    local max_start=$((min_days - lookback - 1))
    if [[ $max_start -lt 0 ]]; then
        print_error "Not enough data! Need at least $((lookback + 1)) days, have $min_days days."
        return 1
    fi

    echo ""
    echo -e "${YELLOW}Start index (warmup period - days to skip at the beginning):${NC}"
    echo -e "${BLUE}  This determines when your backtest evaluation period begins.${NC}"
    echo -e "${BLUE}  Higher start index = shorter backtest (faster) but tests on more recent data.${NC}"
    echo ""
    echo -e "${BLUE}  Valid range: 0 to $max_start days${NC}"
    echo ""
    echo -e "${BLUE}  Recommended configurations:${NC}"

    # Calculate different scenarios
    local quick_start=$(( max_start * 2 / 3 ))
    local quick_backtest=$((min_days - quick_start - lookback))
    local medium_start=$(( max_start / 2 ))
    local medium_backtest=$((min_days - medium_start - lookback))
    local long_start=$(( lookback + 100 ))
    local long_backtest=$((min_days - long_start - lookback))

    echo ""
    echo -e "    ${GREEN}Quick test (recent data):${NC}     Start=$quick_start  → ${quick_backtest} day backtest"
    echo -e "    ${YELLOW}Medium test (balanced):${NC}       Start=$medium_start  → ${medium_backtest} day backtest"
    echo -e "    ${RED}Thorough test (max period):${NC}  Start=$long_start → ${long_backtest} day backtest ${YELLOW}⚠ SLOW${NC}"
    echo ""
    echo -e "${BLUE}  Example: Start=500 with lookback=$lookback means:${NC}"
    echo -e "${BLUE}    • First optimization uses days 0-$((500+lookback-1))${NC}"
    echo -e "${BLUE}    • First portfolio evaluation happens on day $((500+lookback))${NC}"
    echo -e "${BLUE}    • Backtest continues until day $min_days${NC}"
    echo ""
    echo -e "${YELLOW}Enter start index (0 to $max_start):${NC}"
    read -r start

    # Validate start index
    if [[ -z "$start" ]]; then
        print_error "Start index is required (enter a value between 0 and $max_start)"
        return 1
    fi
    if [[ $start -gt $max_start ]]; then
        print_error "Start index too large! Maximum allowed: $max_start (have $min_days days, need $lookback for lookback)"
        return 1
    fi

    # Calculate backtest period
    local backtest_period=$((min_days - start - lookback))
    local first_eval=$((start + lookback))

    # Create visual timeline
    echo ""
    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}Timeline Visualization (${min_days} days total):${NC}"
    echo ""

    # Calculate bar widths (total width = 56 characters)
    local bar_width=56
    local warmup_width=$((start * bar_width / min_days))
    local lookback_width=$((lookback * bar_width / min_days))
    local backtest_width=$((bar_width - warmup_width - lookback_width))

    # Ensure at least 1 character for each section if it exists
    if [[ $warmup_width -gt 0 && $warmup_width -lt 1 ]]; then warmup_width=1; fi
    if [[ $lookback_width -gt 0 && $lookback_width -lt 1 ]]; then lookback_width=1; fi
    if [[ $backtest_width -gt 0 && $backtest_width -lt 1 ]]; then backtest_width=1; fi

    # Build the bars
    local warmup_bar=$(printf '%*s' "$warmup_width" '' | tr ' ' '─')
    local lookback_bar=$(printf '%*s' "$lookback_width" '' | tr ' ' '═')
    local backtest_bar=$(printf '%*s' "$backtest_width" '' | tr ' ' '█')

    # Print the timeline
    echo -e "  ${BLUE}[${warmup_bar}${NC}${YELLOW}${lookback_bar}${NC}${GREEN}${backtest_bar}${NC}${BLUE}]${NC}"
    echo ""
    echo -e "  ${BLUE}├─ Warmup: $start days (skipped for training)${NC}"
    echo -e "  ${YELLOW}├─ Lookback: $lookback days (rolling training window)${NC}"
    echo -e "  ${GREEN}└─ Backtest: $backtest_period days (${backtest_period} optimization steps)${NC}"
    echo ""
    echo -e "  Day 0 ${BLUE}────────────────────${NC} Day $start ${YELLOW}────${NC} Day $first_eval ${GREEN}──────${NC} Day $min_days"
    echo ""
    echo -e "  ${YELLOW}First optimization:${NC} Uses days 0-$((first_eval-1)) to optimize portfolio for day $first_eval"
    echo -e "  ${YELLOW}Each day:${NC} Window rolls forward, re-optimizes with latest $lookback days"
    echo ""

    # Estimate runtime
    local ticker_count=$(echo "$tickers" | tr ',' '\n' | wc -l)
    local est_seconds_per_step=$((ticker_count / 2 + 1))  # Rough estimate: ~0.5s per asset per step
    local total_est_seconds=$((backtest_period * est_seconds_per_step))
    local est_minutes=$((total_est_seconds / 60))

    if [[ $est_minutes -lt 1 ]]; then
        echo -e "  ${GREEN}Estimated runtime: <1 minute${NC}"
    elif [[ $est_minutes -lt 5 ]]; then
        echo -e "  ${GREEN}Estimated runtime: ~$est_minutes minutes${NC}"
    elif [[ $est_minutes -lt 15 ]]; then
        echo -e "  ${YELLOW}Estimated runtime: ~$est_minutes minutes${NC}"
    else
        echo -e "  ${RED}Estimated runtime: ~$est_minutes minutes (long backtest)${NC}"
    fi

    echo -e "${BLUE}════════════════════════════════════════════════════════════${NC}"
    echo ""

    print_info "Running optimization with:"
    print_info "  Tickers: $tickers"
    print_info "  Available data: $min_days days"
    print_info "  Initial allocation: $init_mode"
    print_info "  Lookback window: $lookback days"
    print_info "  Start index: $start"
    print_info "  Backtest period: $((min_days - start - lookback)) days"

    opam exec -- dune exec regime_downside -- \
        -tickers "$tickers" \
        -start "$start" \
        -lookback "$lookback" \
        -init "$init_mode"

    if [[ -f "pricing/regime_downside/output/optimization_results.csv" ]]; then
        print_success "Results saved to: pricing/regime_downside/output/optimization_results.csv"
    else
        print_error "Optimization failed - no results file"
        return 1
    fi
}

# Visualization
generate_plots() {
    print_header "Generating Plots"

    if [[ ! -f "pricing/regime_downside/output/optimization_results.csv" ]]; then
        print_error "No optimization results found. Run optimization first."
        return 1
    fi

    if [[ ! -f ".venv/bin/python3" ]]; then
        print_error "Python virtual environment not found."
        return 1
    fi

    print_info "Generating plots..."
    .venv/bin/python3 pricing/regime_downside/python/viz/plot_results.py

    if [[ -f "pricing/regime_downside/output/portfolio_weights.png" ]]; then
        print_success "Plots saved to: pricing/regime_downside/output/"
        print_info "  - portfolio_weights.png (constrained vs frictionless)"
        print_info "  - risk_metrics.png (constrained vs frictionless)"
        print_info "  - gap_analysis.png (convergence tracking)"
    else
        print_error "Failed to generate plots"
        return 1
    fi
}

# DCF Valuation
run_dcf_valuation() {
    print_header "Running DCF Valuation"

    local default_tickers="AMZN,ALL,CBOE,COP,CVX,GS,IBKR,JPM,LLY,MET,PGR,SFM,TAC,XOM"

    echo -e "\n${YELLOW}Enter ticker symbols for valuation (comma-separated):${NC}"
    echo -e "${BLUE}Press Enter for default (14 stocks): $default_tickers${NC}"
    read -r tickers

    if [[ -z "$tickers" ]]; then
        tickers="$default_tickers"
        print_info "Using default: 14 stocks"
    fi

    # Convert to array
    IFS=',' read -ra TICKER_ARRAY <<< "$tickers"

    # Build executable first to avoid Dune warnings in parallel execution
    print_info "Building DCF executable..."
    if ! opam exec -- dune build valuation/dcf_deterministic/ocaml/bin/main.exe > /dev/null 2>&1; then
        print_error "Failed to build DCF executable"
        return 1
    fi
    local dcf_exe="_build/default/valuation/dcf_deterministic/ocaml/bin/main.exe"

    print_info "Running DCF valuation for ${#TICKER_ARRAY[@]} ticker(s) in parallel..."
    echo ""

    # Run valuations in parallel (up to 8 at a time)
    local max_parallel=8
    local running=0
    local pids=()
    local ticker_names=()

    for ticker in "${TICKER_ARRAY[@]}"; do
        ticker=$(echo "$ticker" | xargs)  # trim whitespace

        # Start background process
        (
            "$dcf_exe" \
                -ticker "$ticker" \
                -data-dir valuation/dcf_deterministic/data \
                -log-dir valuation/dcf_deterministic/log \
                -python valuation/dcf_deterministic/python/fetch_financials.py \
                -fetch-sec-reserves
        ) &

        local pid=$!
        pids+=($pid)
        ticker_names[$pid]=$ticker
        running=$((running + 1))

        # Wait if we've hit the parallel limit
        if [[ $running -ge $max_parallel ]]; then
            wait -n
            running=$((running - 1))
        fi
    done

    # Wait for all remaining processes
    echo "Waiting for all valuations to complete..."
    wait

    echo ""

    # Check for log files
    local log_count=$(ls -1 valuation/dcf_deterministic/log/dcf_*.log 2>/dev/null | wc -l)
    if [[ $log_count -gt 0 ]]; then
        print_success "Valuation logs saved to: valuation/dcf_deterministic/log/"
        print_info "  Found $log_count log file(s)"
    else
        print_error "No valuation logs generated"
        return 1
    fi
}

# Full workflow
run_full_workflow() {
    print_header "Running Full Workflow"

    print_info "This will run:"
    print_info "  1. Install OCaml dependencies"
    print_info "  2. Install Python dependencies"
    print_info "  3. Build project"
    print_info "  4. Fetch benchmark data"
    print_info "  5. Fetch asset data"
    print_info "  6. Run optimization"
    print_info "  7. Generate plots"

    echo -e "\n${YELLOW}Continue? (y/n):${NC}"
    read -r confirm
    if [[ "$confirm" != "y" ]]; then
        print_warning "Workflow cancelled"
        return 0
    fi

    install_ocaml_deps || return 1
    install_python_deps || return 1
    build_project || return 1
    fetch_benchmark_data || return 1
    fetch_asset_data || return 1
    run_optimization || return 1
    generate_plots || return 1

    print_success "Full workflow completed successfully!"
}

# Status check
check_status() {
    print_header "System Status Check"

    # Check dependencies
    print_info "Checking system dependencies..."
    check_opam
    check_uv
    check_python

    echo ""

    # Check OCaml packages
    print_info "Checking OCaml packages..."

    # Disable exit-on-error for opam checks
    set +e

    # Check if local switch or Docker named switch is active
    local_switch_path=$(pwd)
    current_switch=$(opam switch show 2>/dev/null)
    switch_show_result=$?

    if [[ $switch_show_result -eq 0 ]] && [[ "$current_switch" == "$local_switch_path" || "$current_switch" == "atemoya-build" ]]; then
        # Correct switch is active, check if packages are installed
        if opam list csv owl yojson ppx_deriving alcotest 2>&1 | grep -q "installed"; then
            print_success "OCaml packages installed"
        else
            print_warning "Some OCaml packages may be missing"
        fi
    elif [[ $switch_show_result -eq 0 ]]; then
        # Some other switch is active (not our local one)
        print_warning "Different opam switch active. Run 'Install OCaml Dependencies' to set up local switch"
    else
        # No switch is active
        print_warning "No opam switch currently active (run 'Install OCaml Dependencies' to set up)"
    fi

    # Re-enable exit-on-error
    set -e

    # Check Python venv
    if [[ -d ".venv" ]]; then
        print_success "Python virtual environment exists"
        if .venv/bin/python3 -c "import cvxpy, numpy, scipy, yfinance" 2>/dev/null; then
            print_success "Python packages installed"
        else
            print_warning "Some Python packages may be missing"
        fi
    else
        print_warning "Python virtual environment not found"
    fi

    # Check builds (scan all modules dynamically)
    print_info "Checking builds..."
    local built=0 unbuilt=0
    for category in pricing valuation monitoring alternative; do
        for exe in _build/default/${category}/*/ocaml/bin/main.exe; do
            [[ -f "$exe" ]] || continue
            local mod_name=$(echo "$exe" | sed "s|_build/default/${category}/\([^/]*\)/.*|\1|")
            built=$((built + 1))
        done
    done
    # Count unbuilt modules (have ocaml/bin/main.ml but no built exe)
    for category in pricing valuation monitoring alternative; do
        for src in ${category}/*/ocaml/bin/main.ml; do
            [[ -f "$src" ]] || continue
            local mod_name=$(echo "$src" | sed "s|${category}/\([^/]*\)/.*|\1|")
            if [[ ! -f "_build/default/${category}/${mod_name}/ocaml/bin/main.exe" ]]; then
                unbuilt=$((unbuilt + 1))
            fi
        done
    done
    if [[ $built -gt 0 ]]; then
        print_success "$built OCaml module(s) built"
    fi
    if [[ $unbuilt -gt 0 ]]; then
        print_warning "$unbuilt OCaml module(s) not built yet"
    fi
    if [[ $built -eq 0 && $unbuilt -eq 0 ]]; then
        print_warning "No OCaml modules found"
    fi

    # Check data (only count files that are actually fetched, not config/tracked)
    print_info "Checking data..."
    local data_dirs=0
    for category in pricing valuation monitoring alternative; do
        for d in ${category}/*/data; do
            [[ -d "$d" ]] || continue
            local fetched=0
            while IFS= read -r f; do
                [[ -z "$f" ]] && continue
                # Skip snapshots
                [[ "$f" == */snapshots/* ]] && continue
                # Skip git-tracked files
                git ls-files --error-unmatch "$f" &>/dev/null && continue
                # Skip config files
                local bn=$(basename "$f")
                case "$bn" in
                    params.json|params_*.json|config.json|config_*.json) continue ;;
                    tickers.json|holdings.json|targets.json) continue ;;
                    bayesian_priors.json|og_reserves.json) continue ;;
                    .last_tickers) continue ;;
                    DATA_SOURCES.md|*.md) continue ;;
                esac
                fetched=1
                break
            done < <(find "$d" -type f 2>/dev/null)
            if [[ $fetched -gt 0 ]]; then
                data_dirs=$((data_dirs + 1))
            fi
        done
    done
    if [[ $data_dirs -gt 0 ]]; then
        print_success "$data_dirs module(s) have fetched data"
    else
        print_warning "No data fetched yet"
    fi

    # Check results
    print_info "Checking results..."
    local output_dirs=0 log_dirs=0
    for category in pricing valuation monitoring alternative; do
        for d in ${category}/*/output; do
            [[ -d "$d" ]] || continue
            local file_count=$(find "$d" -type f 2>/dev/null | wc -l)
            if [[ $file_count -gt 0 ]]; then
                output_dirs=$((output_dirs + 1))
            fi
        done
        for d in ${category}/*/log; do
            [[ -d "$d" ]] || continue
            local file_count=$(find "$d" -type f 2>/dev/null | wc -l)
            if [[ $file_count -gt 0 ]]; then
                log_dirs=$((log_dirs + 1))
            fi
        done
    done
    if [[ $output_dirs -gt 0 ]]; then
        print_success "$output_dirs module(s) have output"
    else
        print_warning "No output generated yet"
    fi
    if [[ $log_dirs -gt 0 ]]; then
        print_success "$log_dirs module(s) have logs"
    fi
}

# View results
view_results() {
    print_header "View Results"

    if [[ -f "pricing/regime_downside/output/optimization_results.csv" ]]; then
        print_info "Latest results:"
        echo ""
        head -20 pricing/regime_downside/output/optimization_results.csv
        echo ""
        print_info "Full results: pricing/regime_downside/output/optimization_results.csv"
    else
        print_error "No results found. Run optimization first."
    fi
}

# View DCF results
view_dcf_results() {
    print_header "View DCF Valuation Results"

    local log_files=(valuation/dcf_deterministic/log/dcf_*.log)

    if [[ ! -f "${log_files[0]}" ]]; then
        print_error "No DCF valuation results found. Run valuation first."
        return 1
    fi

    local log_count=${#log_files[@]}
    print_info "Found $log_count valuation log(s)"
    echo ""

    # List available logs with investment signals
    echo -e "${YELLOW}Available valuations:${NC}"
    printf "%-4s %-40s %-20s\n" "No." "File" "Signal"
    echo "$(printf '─%.0s' {1..70})"

    local i=1
    for log in "${log_files[@]}"; do
        local basename=$(basename "$log")

        # Extract investment signal from log
        local signal=$(grep "Investment Signal:" "$log" | head -1 | sed 's/.*Investment Signal: //' | sed 's/\x1b\[[0-9;]*m//g' | awk '{print $1, $2}')

        # Color code the signal
        local signal_color=""
        case "$signal" in
            "Strong Buy")
                signal_color="${GREEN}$signal${NC}"
                ;;
            "Moderate Buy"|"Weak Buy")
                signal_color="${BLUE}$signal${NC}"
                ;;
            "Avoid/Sell"|"Moderate Sell"|"Weak Sell")
                signal_color="${RED}$signal${NC}"
                ;;
            *)
                signal_color="${YELLOW}$signal${NC}"
                ;;
        esac

        printf "%-4s %-40s %b\n" "$i)" "$basename" "$signal_color"
        ((i++))
    done
    echo ""

    echo -e "${YELLOW}Enter number to view (or press Enter for strongest buy signal):${NC}"
    read -r choice

    local selected_log
    if [[ -z "$choice" ]]; then
        # Find log with strongest buy signal
        # Signal ranking: Strong Buy=3, Moderate Buy=2, Weak Buy=1, Neutral/Hold=0,
        #                 Weak Sell=-1, Moderate Sell=-2, Avoid/Sell=-3
        # Tiebreaker: Highest average margin of safety (FCFE + FCFF) / 2

        local best_score=-999
        local best_log=""
        local best_mos=0

        for log in "${log_files[@]}"; do
            # Extract signal (remove ANSI color codes)
            local signal=$(grep "Investment Signal:" "$log" | sed 's/.*Investment Signal: //; s/\x1b\[[0-9;]*m//g')

            # Map signal to score
            local score=0
            case "$signal" in
                "Strong Buy") score=3 ;;
                "Moderate Buy") score=2 ;;
                "Weak Buy") score=1 ;;
                "Neutral/Hold") score=0 ;;
                "Weak Sell") score=-1 ;;
                "Moderate Sell") score=-2 ;;
                "Avoid/Sell") score=-3 ;;
            esac

            # Extract margin of safety values (FCFE and FCFF)
            local mos_values=$(grep "Margin of Safety:" "$log" | sed 's/.*Margin of Safety: //; s/%//')
            local fcfe_mos=$(echo "$mos_values" | head -1 | awk '{print $1}')
            local fcff_mos=$(echo "$mos_values" | tail -1 | awk '{print $1}')

            # Calculate average MOS (handle empty values)
            local avg_mos=0
            if [[ -n "$fcfe_mos" && -n "$fcff_mos" ]]; then
                avg_mos=$(echo "scale=2; ($fcfe_mos + $fcff_mos) / 2" | bc)
            fi

            # Update best if this score is higher, or same score but higher MOS
            if [[ $score -gt $best_score ]] || [[ $score -eq $best_score && $(echo "$avg_mos > $best_mos" | bc) -eq 1 ]]; then
                best_score=$score
                best_log="$log"
                best_mos=$avg_mos
            fi
        done

        selected_log="$best_log"
        print_info "Showing strongest buy signal (highest margin of safety)"
    else
        if [[ $choice -ge 1 && $choice -le $log_count ]]; then
            selected_log="${log_files[$((choice-1))]}"
        else
            print_error "Invalid choice"
            return 1
        fi
    fi

    echo ""
    print_info "Displaying: $(basename "$selected_log")"
    echo ""
    cat "$selected_log"
}

# Probabilistic DCF Valuation
run_dcf_probabilistic() {
    print_header "Running Probabilistic DCF Valuation"

    local default_tickers="AMZN,ALL,CBOE,COP,CVX,GS,IBKR,JPM,LLY,MET,PGR,SFM,TAC,XOM"

    echo -e "\n${YELLOW}Enter ticker symbols for valuation (comma-separated):${NC}"
    echo -e "${BLUE}Press Enter for default (7 stocks): $default_tickers${NC}"
    read -r tickers

    if [[ -z "$tickers" ]]; then
        tickers="$default_tickers"
        print_info "Using default: 7 stocks"
    fi

    # Simulation count selection
    echo ""
    echo -e "${YELLOW}Choose simulation count:${NC}"
    echo "  1) 100   (fast, ~0.2s/stock, rough estimates)"
    echo "  2) 1000  (balanced, ~1-2s/stock, good accuracy) [DEFAULT]"
    echo "  3) 5000  (smooth, ~5-10s/stock, high accuracy)"
    echo "  4) 10000 (publication, ~10-20s/stock, very smooth)"
    echo "  5) Custom"
    echo -e "${YELLOW}Enter choice (1-5, or press Enter for default):${NC}"
    read -r sim_choice

    local num_sims=1000
    case "$sim_choice" in
        1) num_sims=100 ;;
        2|"") num_sims=1000 ;;
        3) num_sims=5000 ;;
        4) num_sims=10000 ;;
        5)
            echo -e "${YELLOW}Enter custom simulation count:${NC}"
            read -r custom_sims
            if [[ "$custom_sims" =~ ^[0-9]+$ ]] && [[ "$custom_sims" -gt 0 ]]; then
                num_sims=$custom_sims
            else
                print_error "Invalid number. Using default: 1000"
                num_sims=1000
            fi
            ;;
        *)
            print_warning "Invalid choice. Using default: 1000"
            num_sims=1000
            ;;
    esac

    # Update params file temporarily
    local params_file="valuation/dcf_probabilistic/data/params_probabilistic.json"
    local params_backup="$params_file.backup"
    cp "$params_file" "$params_backup"

    # Use jq if available, otherwise use sed
    if command -v jq &> /dev/null; then
        jq ".num_simulations = $num_sims" "$params_backup" > "$params_file"
    else
        sed -i.tmp "s/\"num_simulations\": [0-9]*/\"num_simulations\": $num_sims/" "$params_file"
        rm -f "$params_file.tmp"
    fi

    # Convert to array
    IFS=',' read -ra TICKER_ARRAY <<< "$tickers"

    # Check for stale simulation data
    local fcfe_file="valuation/dcf_probabilistic/output/simulations_fcfe.csv"
    if [[ -f "$fcfe_file" ]]; then
        echo ""
        print_info "Checking existing simulation data for conflicts..."

        local stale_check=$(cd valuation/dcf_probabilistic/python/viz && uv run python << PYEOF
import pandas as pd
import sys

try:
    sims = pd.read_csv('../../output/simulations_fcfe.csv')

    # Get ticker counts
    ticker_counts = {}
    for ticker in sims.columns:
        valid_count = sims[ticker].notna().sum()
        ticker_counts[ticker] = valid_count

    # Check if all aligned
    counts = list(ticker_counts.values())
    all_aligned = (len(set(counts)) == 1)

    if all_aligned:
        print(f"ALIGNED:{all_aligned}:{counts[0]}")
    else:
        min_count = min(counts)
        max_count = max(counts)
        print(f"MISALIGNED:{min_count}:{max_count}")

        # Show tickers with different counts
        for ticker, count in sorted(ticker_counts.items(), key=lambda x: x[1]):
            if count != max_count:
                print(f"LOW:{ticker}:{count}")

    # Total tickers
    print(f"TOTAL:{len(sims.columns)}")

except FileNotFoundError:
    print("NOFILE")
except Exception as e:
    print(f"ERROR:{e}", file=sys.stderr)
    sys.exit(1)
PYEOF
)

        if [[ $? -eq 0 ]]; then
            local aligned=$(echo "$stale_check" | grep "^ALIGNED:" | cut -d':' -f2)
            local existing_count=$(echo "$stale_check" | grep "^ALIGNED:" | cut -d':' -f3)
            local total_existing=$(echo "$stale_check" | grep "^TOTAL:" | cut -d':' -f2)

            if [[ "$aligned" == "True" ]]; then
                if [[ "$existing_count" != "$num_sims" ]]; then
                    echo ""
                    print_warning "Existing simulation data detected!"
                    echo ""
                    echo -e "${YELLOW}Current state:${NC}"
                    echo "  Existing tickers: $total_existing tickers with $existing_count simulations each"
                    echo "  New run: ${#TICKER_ARRAY[@]} ticker(s) with $num_sims simulations"
                    echo ""
                    echo -e "${RED}This will create MISALIGNED data!${NC}"
                    echo ""
                    echo -e "${YELLOW}Options:${NC}"
                    echo "  1) Clear old data and start fresh (RECOMMENDED)"
                    echo "  2) Continue anyway (will create misalignment)"
                    echo "  3) Cancel"
                    echo ""
                    echo -e "${YELLOW}Enter choice (1-3):${NC}"
                    read -r stale_choice

                    case "$stale_choice" in
                        1)
                            print_info "Clearing old simulation data..."
                            rm -f valuation/dcf_probabilistic/output/simulations_*.csv
                            rm -f valuation/dcf_probabilistic/output/market_prices.csv
                            print_success "Old data cleared"
                            ;;
                        2)
                            print_warning "Continuing with misaligned data..."
                            echo -e "${YELLOW}Note: Portfolio frontier will use only common valid simulations${NC}"
                            ;;
                        3)
                            print_info "Cancelled"
                            mv "$params_backup" "$params_file"
                            return 0
                            ;;
                        *)
                            print_warning "Invalid choice. Clearing data (safe option)..."
                            rm -f valuation/dcf_probabilistic/output/simulations_*.csv
                            rm -f valuation/dcf_probabilistic/output/market_prices.csv
                            ;;
                    esac
                fi
            else
                # Already misaligned
                local min_sims=$(echo "$stale_check" | grep "^MISALIGNED:" | cut -d':' -f2)
                local max_sims=$(echo "$stale_check" | grep "^MISALIGNED:" | cut -d':' -f3)

                echo ""
                print_warning "Existing simulation data is ALREADY MISALIGNED!"
                echo ""
                echo -e "${YELLOW}Current state:${NC}"
                echo "  $total_existing tickers with varying simulation counts ($min_sims to $max_sims)"
                echo "  New run: ${#TICKER_ARRAY[@]} ticker(s) with $num_sims simulations"
                echo ""

                # Show low-count tickers
                local low_tickers=$(echo "$stale_check" | grep "^LOW:" | head -5)
                if [[ -n "$low_tickers" ]]; then
                    echo -e "${YELLOW}Tickers with low simulation counts:${NC}"
                    echo "$low_tickers" | while IFS=':' read -r _ ticker count; do
                        echo "  - $ticker: $count simulations"
                    done
                    local more=$(echo "$stale_check" | grep "^LOW:" | wc -l)
                    if [[ $more -gt 5 ]]; then
                        echo "  ... and $((more - 5)) more"
                    fi
                    echo ""
                fi

                echo -e "${YELLOW}Recommendation: Clear old data for best results${NC}"
                echo ""
                echo -e "${YELLOW}Options:${NC}"
                echo "  1) Clear ALL old data and start fresh (RECOMMENDED)"
                echo "  2) Continue anyway (will add to misalignment)"
                echo "  3) Cancel"
                echo ""
                echo -e "${YELLOW}Enter choice (1-3):${NC}"
                read -r stale_choice

                case "$stale_choice" in
                    1)
                        print_info "Clearing old simulation data..."
                        rm -f valuation/dcf_probabilistic/output/simulations_*.csv
                        rm -f valuation/dcf_probabilistic/output/market_prices.csv
                        print_success "Old data cleared - starting fresh"
                        ;;
                    2)
                        print_warning "Continuing with misaligned data..."
                        echo -e "${YELLOW}Note: This will make alignment worse${NC}"
                        ;;
                    3)
                        print_info "Cancelled"
                        mv "$params_backup" "$params_file"
                        return 0
                        ;;
                    *)
                        print_warning "Invalid choice. Clearing data (safe option)..."
                        rm -f valuation/dcf_probabilistic/output/simulations_*.csv
                        rm -f valuation/dcf_probabilistic/output/market_prices.csv
                        ;;
                esac
            fi
        fi
        echo ""
    fi

    # Build executable first
    print_info "Building probabilistic DCF executable..."
    if ! opam exec -- dune build valuation/dcf_probabilistic/ocaml/bin/main.exe > /dev/null 2>&1; then
        print_error "Failed to build probabilistic DCF executable"
        return 1
    fi
    local dcf_prob_exe="_build/default/valuation/dcf_probabilistic/ocaml/bin/main.exe"

    print_info "Running probabilistic DCF for ${#TICKER_ARRAY[@]} ticker(s) with $num_sims simulations..."
    echo ""

    # Run valuation for each ticker
    for ticker in "${TICKER_ARRAY[@]}"; do
        ticker=$(echo "$ticker" | xargs)  # trim whitespace

        print_info "Valuing: $ticker ($num_sims simulations)"

        "$dcf_prob_exe" \
            -ticker "$ticker" \
            -data-dir valuation/dcf_probabilistic/data \
            -log-dir valuation/dcf_probabilistic/log \
            -output-dir valuation/dcf_probabilistic/output \
            -python valuation/dcf_probabilistic/python/fetch/fetch_financials_ts.py

        if [[ $? -eq 0 ]]; then
            print_success "$ticker probabilistic valuation complete"
        else
            print_error "$ticker probabilistic valuation failed"
        fi
        echo ""
    done

    # Restore params file
    mv "$params_backup" "$params_file"

    # Check for log files
    local log_count=$(ls -1 valuation/dcf_probabilistic/log/dcf_prob_*.log 2>/dev/null | wc -l)
    if [[ $log_count -gt 0 ]]; then
        print_success "Valuation complete. $log_count log file(s) created"
        echo ""
        echo -e "${BLUE}Next steps:${NC}"
        echo "  - View results: Option 15"
        echo "  - Generate visualizations: Option 16"
    else
        print_warning "No log files found"
    fi
}

view_dcf_probabilistic_results() {
    print_header "View Probabilistic DCF Results"

    local log_files=(valuation/dcf_probabilistic/log/dcf_prob_*.log)

    if [[ ! -f "${log_files[0]}" ]]; then
        print_error "No probabilistic DCF results found. Run valuation first."
        return 1
    fi

    local log_count=${#log_files[@]}
    print_info "Found $log_count probabilistic valuation log(s)"
    echo ""

    # List available logs with investment signals
    echo -e "${YELLOW}Available valuations:${NC}"
    printf "%-4s %-40s %-20s\n" "No." "File" "Signal"
    echo "$(printf '─%.0s' {1..70})"

    local i=1
    for log in "${log_files[@]}"; do
        local basename=$(basename "$log")

        # Extract investment signal from log
        local signal=$(grep "Investment Signal:" "$log" | head -1 | sed 's/.*Investment Signal: //' | sed 's/\x1b\[[0-9;]*m//g' | awk '{print $1, $2}')

        # Color code the signal
        local signal_color=""
        case "$signal" in
            "Strong Buy")
                signal_color="${GREEN}$signal${NC}"
                ;;
            "Moderate Buy"|"Weak Buy")
                signal_color="${BLUE}$signal${NC}"
                ;;
            "Avoid/Sell"|"Moderate Sell"|"Weak Sell")
                signal_color="${RED}$signal${NC}"
                ;;
            *)
                signal_color="${YELLOW}$signal${NC}"
                ;;
        esac

        printf "%-4s %-40s %b\n" "$i)" "$basename" "$signal_color"
        ((i++))
    done
    echo ""

    echo -e "${YELLOW}Enter number to view (or press Enter for strongest buy signal):${NC}"
    read -r choice

    local selected_log
    if [[ -z "$choice" ]]; then
        # Find log with strongest buy signal
        # Signal ranking: Strong Buy=3, Moderate Buy=2, Weak Buy=1, Neutral/Hold=0,
        #                 Weak Sell=-1, Moderate Sell=-2, Avoid/Sell=-3
        # Tiebreaker: Highest average margin of safety (FCFE + FCFF) / 2

        local best_score=-999
        local best_log=""
        local best_mos=0

        for log in "${log_files[@]}"; do
            # Extract signal (remove ANSI color codes)
            local signal=$(grep "Investment Signal:" "$log" | sed 's/.*Investment Signal: //; s/\x1b\[[0-9;]*m//g')

            # Map signal to score
            local score=0
            case "$signal" in
                "Strong Buy") score=3 ;;
                "Moderate Buy") score=2 ;;
                "Weak Buy") score=1 ;;
                "Neutral/Hold") score=0 ;;
                "Weak Sell") score=-1 ;;
                "Moderate Sell") score=-2 ;;
                "Avoid/Sell") score=-3 ;;
            esac

            # Extract margin of safety values (FCFE and FCFF)
            local mos_values=$(grep "Margin of Safety:" "$log" | sed 's/.*Margin of Safety: //; s/%//')
            local fcfe_mos=$(echo "$mos_values" | head -1 | awk '{print $1}')
            local fcff_mos=$(echo "$mos_values" | tail -1 | awk '{print $1}')

            # Calculate average MOS (handle empty values)
            local avg_mos=0
            if [[ -n "$fcfe_mos" && -n "$fcff_mos" ]]; then
                avg_mos=$(echo "scale=2; ($fcfe_mos + $fcff_mos) / 2" | bc)
            fi

            # Update best if this score is higher, or same score but higher MOS
            if [[ $score -gt $best_score ]] || [[ $score -eq $best_score && $(echo "$avg_mos > $best_mos" | bc) -eq 1 ]]; then
                best_score=$score
                best_log="$log"
                best_mos=$avg_mos
            fi
        done

        selected_log="$best_log"
        print_info "Showing strongest buy signal (highest margin of safety)"
    else
        if [[ "$choice" =~ ^[0-9]+$ ]] && [[ "$choice" -ge 1 ]] && [[ "$choice" -le ${#log_files[@]} ]]; then
            selected_log="${log_files[$((choice-1))]}"
        else
            print_error "Invalid selection"
            return 1
        fi
    fi

    echo ""
    print_info "Displaying: $(basename "$selected_log")"
    echo ""
    cat "$selected_log"

    # Show CSV summary
    local summary_file="valuation/dcf_probabilistic/output/probabilistic_summary.csv"
    if [[ -f "$summary_file" ]]; then
        echo ""
        echo -e "${YELLOW}CSV Summary (first 5 lines):${NC}"
        head -5 "$summary_file"
    fi
}

generate_dcf_visualizations() {
    print_header "Generate Probabilistic DCF Visualizations"

    # Check if simulation outputs exist
    local fcfe_file="valuation/dcf_probabilistic/output/data/simulations_fcfe.csv"
    if [[ ! -f "$fcfe_file" ]]; then
        print_error "No simulation data found. Run probabilistic valuation first."
        return 1
    fi

    print_info "Generating KDE and surplus distribution plots..."
    echo ""

    if uv run valuation/dcf_probabilistic/python/viz/plot_results.py; then
        local png_count=$(ls -1 valuation/dcf_probabilistic/output/single_asset/*.png 2>/dev/null | wc -l)
        print_success "Visualizations complete. $png_count plot(s) generated"
        echo ""
        echo -e "${BLUE}Plots saved to:${NC} valuation/dcf_probabilistic/output/single_asset/"
        ls -1 valuation/dcf_probabilistic/output/single_asset/*.png 2>/dev/null | while read -r file; do
            echo "  - $(basename "$file")"
        done
    else
        print_error "Visualization generation failed"
    fi
}

generate_portfolio_frontier() {
    print_header "Generate Portfolio Efficient Frontier"

    # Check if simulation outputs exist
    local fcfe_file="valuation/dcf_probabilistic/output/data/simulations_fcfe.csv"
    if [[ ! -f "$fcfe_file" ]]; then
        print_error "No simulation data found. Run probabilistic valuation first."
        return 1
    fi

    # Count number of tickers
    local n_tickers=$(head -1 "$fcfe_file" | tr ',' '\n' | wc -l)
    if [[ $n_tickers -lt 2 ]]; then
        print_error "Need at least 2 tickers for portfolio analysis. Found: $n_tickers"
        echo ""
        echo -e "${YELLOW}Run probabilistic valuation with multiple tickers first:${NC}"
        echo "  Example: AMZN,CBOE,CVX,IBKR,JPM,LLY,TAC"
        return 1
    fi

    print_info "Found $n_tickers tickers in simulation data"
    echo ""

    # Check simulation alignment
    print_info "Checking simulation alignment across tickers..."
    echo ""

    local alignment_check=$(cd valuation/dcf_probabilistic/python/viz && uv run python << 'PYEOF'
import pandas as pd
import sys

try:
    sims = pd.read_csv('../../output/data/simulations_fcfe.csv')

    # Get total rows and valid counts per ticker
    total_rows = len(sims)
    ticker_stats = {}
    for ticker in sims.columns:
        valid_count = sims[ticker].notna().sum()
        ticker_stats[ticker] = (total_rows, valid_count)

    # Check if all tickers have same total rows (structure alignment)
    all_same_rows = len(set([total_rows] * len(sims.columns))) == 1

    # Find common valid range (all tickers have data)
    all_valid_mask = sims.notna().all(axis=1)
    common_count = all_valid_mask.sum()

    # Get valid count range
    valid_counts = [stats[1] for stats in ticker_stats.values()]
    min_valid = min(valid_counts)
    max_valid = max(valid_counts)

    # Print results
    print(f"TOTAL_ROWS:{total_rows}")
    print(f"STRUCTURE_ALIGNED:{all_same_rows}")
    print(f"MIN_VALID:{min_valid}")
    print(f"MAX_VALID:{max_valid}")
    print(f"COMMON_VALID:{common_count}")

    # Print per-ticker stats (sorted by valid count)
    for ticker, (total, valid) in sorted(ticker_stats.items(), key=lambda x: x[1][1]):
        print(f"TICKER:{ticker}:{total}:{valid}")

except Exception as e:
    print(f"ERROR:{e}", file=sys.stderr)
    sys.exit(1)
PYEOF
)

    if [[ $? -ne 0 ]]; then
        print_error "Failed to check simulation alignment"
        return 1
    fi

    # Parse alignment results
    local total_rows=$(echo "$alignment_check" | grep "^TOTAL_ROWS:" | cut -d':' -f2)
    local structure_aligned=$(echo "$alignment_check" | grep "^STRUCTURE_ALIGNED:" | cut -d':' -f2)
    local min_valid=$(echo "$alignment_check" | grep "^MIN_VALID:" | cut -d':' -f2)
    local max_valid=$(echo "$alignment_check" | grep "^MAX_VALID:" | cut -d':' -f2)
    local common_valid=$(echo "$alignment_check" | grep "^COMMON_VALID:" | cut -d':' -f2)

    echo -e "${BLUE}Per-ticker data quality (total rows: $total_rows):${NC}"
    echo "$alignment_check" | grep "^TICKER:" | while IFS=':' read -r _ ticker total valid; do
        local pct=$((valid * 100 / total))
        if [[ "$pct" -ge 90 ]]; then
            echo -e "  ${GREEN}$ticker: $valid/$total valid ($pct%)${NC}"
        elif [[ "$pct" -ge 70 ]]; then
            echo -e "  ${YELLOW}$ticker: $valid/$total valid ($pct%)${NC}"
        else
            echo -e "  ${RED}$ticker: $valid/$total valid ($pct%)${NC}"
        fi
    done
    echo ""

    if [[ "$structure_aligned" == "True" ]]; then
        print_success "✓ CSV structure aligned: all tickers have $total_rows rows"

        # Check data quality
        local common_pct=$((common_valid * 100 / total_rows))
        echo ""
        echo -e "${BLUE}Data Quality Summary:${NC}"
        echo "  Total rows (structure): $total_rows"
        echo "  Valid data range: $min_valid - $max_valid (per ticker)"
        echo "  Common valid rows: $common_valid ($common_pct% of total)"
        echo ""

        if [[ "$common_pct" -lt 50 ]]; then
            print_warning "Low data quality: only $common_pct% of rows have valid data for ALL tickers"
            echo ""
            echo -e "${YELLOW}This may be due to:${NC}"
            echo "  - Monte Carlo simulations producing NaN for some parameter combinations"
            echo "  - Data quality issues in fetched financial data"
            echo "  - Extreme parameter values causing numerical errors"
            echo ""
            echo -e "${YELLOW}Impact on portfolio analysis:${NC}"
            echo "  - Portfolio frontiers will use only $common_valid simulations"
            echo "  - This may still be sufficient if > 1000"
            echo ""
        fi
    else
        print_error "CSV structure is MISALIGNED (different row counts)!"
        echo ""
        echo -e "${RED}This should not happen with the current implementation.${NC}"
        echo -e "${YELLOW}Recommendation:${NC} Clear old data and re-run all tickers in one batch"
        echo ""
        return 1
    fi

    # Ask for number of portfolios
    echo ""
    echo -e "${YELLOW}Number of random portfolios to generate:${NC}"
    echo "  1) 1,000  (fast, rough frontier)"
    echo "  2) 5,000  (balanced, smooth frontier) [DEFAULT]"
    echo "  3) 10,000 (slow, very smooth frontier)"
    echo "  4) Custom"
    echo -e "${YELLOW}Enter choice (1-4, or press Enter for 5,000):${NC}"
    read -r n_choice

    local n_portfolios=5000
    case "$n_choice" in
        1) n_portfolios=1000 ;;
        2|"") n_portfolios=5000 ;;
        3) n_portfolios=10000 ;;
        4)
            echo -e "${YELLOW}Enter custom number:${NC}"
            read -r custom_n
            if [[ "$custom_n" =~ ^[0-9]+$ ]] && [[ "$custom_n" -gt 0 ]]; then
                n_portfolios=$custom_n
            else
                print_error "Invalid number. Using default: 5,000"
                n_portfolios=5000
            fi
            ;;
        *)
            print_warning "Invalid choice. Using default: 5,000"
            n_portfolios=5000
            ;;
    esac

    # Generate combined frontiers (FCFF and FCFE in one plot with aligned axes)
    print_info "Generating $n_portfolios random portfolios with combined FCFF/FCFE plots..."
    echo ""

    if ! uv run valuation/dcf_probabilistic/python/viz/plot_frontier.py \
        --n-portfolios "$n_portfolios" \
        --method combined; then
        print_error "Frontier generation failed"
        return 1
    fi
    echo ""

    print_success "Portfolio frontier generation complete"
    echo ""
    echo -e "${BLUE}Combined plots saved to:${NC} valuation/dcf_probabilistic/output/multi_asset/"
    echo -e "${BLUE}(Each plot shows FCFF (top) and FCFE (bottom) with aligned x-axes)${NC}"
    echo ""
    ls -1 valuation/dcf_probabilistic/output/multi_asset/*.png 2>/dev/null | while read -r file; do
        echo "  - $(basename "$file")"
    done
}

# Clean build artifacts
clean_build_artifacts() {
    print_header "Cleaning Build Artifacts"

    echo -e "\n${YELLOW}This will remove OCaml build artifacts (_build/). Continue? (y/n):${NC}"
    read -r confirm
    if [[ "$confirm" != "y" ]]; then
        print_warning "Clean cancelled"
        return 0
    fi

    print_info "Cleaning build artifacts..."
    opam exec -- dune clean

    print_success "Build artifacts cleaned"
}




# Detect if running in Docker container
is_docker() {
    # Check multiple Docker indicators
    if [ -f /.dockerenv ]; then
        return 0
    elif [ -f /proc/1/cgroup ] && grep -q docker /proc/1/cgroup 2>/dev/null; then
        return 0
    elif [ -f /proc/self/cgroup ] && grep -q docker /proc/self/cgroup 2>/dev/null; then
        return 0
    else
        return 1
    fi
}

# Main menu
show_main_menu() {
    clear

    # Detect environment
    local env_label=""
    if is_docker; then
        env_label="Docker Container"
    else
        env_label="Native Install"
    fi

    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════╗"
    echo "║                                              ║"
    echo "║                   ATEMOYA                    ║"
    echo "║                                              ║"
    echo "║          github.com/cb-g/atemoya             ║"
    echo "║                                              ║"
    printf "║%46s║\n" "[$env_label]"
    echo "╚══════════════════════════════════════════════╝"
    echo -e "${NC}"

    echo -e "${GREEN}1)${NC} Installation"
    echo -e "${GREEN}2)${NC} Maintenance"
    echo -e "${GREEN}3)${NC} Run"
    echo ""
    echo -e "${GREEN}0)${NC} Quit"
    echo ""
}

# Complete installation workflow
install_all() {
    print_header "Complete Installation"

    echo -e "\n${YELLOW}This will run all installation steps in sequence:${NC}"
    echo "  1. Check System Status"
    echo "  2. Install OCaml Dependencies"
    echo "  3. Install Python Dependencies"
    echo "  4. Build Project"
    echo "  5. Run Tests"
    echo ""
    echo -e "${YELLOW}Continue? (y/n):${NC}"
    read -r confirm
    if [[ "$confirm" != "y" ]]; then
        print_warning "Installation cancelled"
        return 0
    fi

    echo ""
    check_status
    echo ""

    install_ocaml_deps
    if [[ $? -ne 0 ]]; then
        print_error "OCaml installation failed. Stopping."
        return 1
    fi
    echo ""

    install_python_deps
    if [[ $? -ne 0 ]]; then
        print_error "Python installation failed. Stopping."
        return 1
    fi
    echo ""

    build_project
    if [[ $? -ne 0 ]]; then
        print_error "Build failed. Stopping."
        return 1
    fi
    echo ""

    run_tests

    echo ""
    print_success "Complete installation finished!"
}

# Installation submenu
show_installation_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Installation ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Check System Status"
        echo -e "${GREEN}2)${NC} Install OCaml Dependencies"
        echo -e "${GREEN}3)${NC} Install Python Dependencies"
        echo -e "${GREEN}4)${NC} Build Project"
        echo -e "${GREEN}5)${NC} Run Tests"
        echo -e "${GREEN}6)${NC} Do Everything"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Main Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) check_status ;;
            2) install_ocaml_deps ;;
            3) install_python_deps ;;
            4) build_project ;;
            5) run_tests ;;
            6|"") install_all ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

# Clear output files (keep README showcase SVGs)
# Delete output, logs (interactive options for showcase preservation and log keeping)
clear_output_interactive() {
    print_header "Delete Output"
    echo -e "  Deletes plots, CSVs, and analysis results from all output/ directories."
    echo -e "  ${DIM}Config files, snapshots, and fetched data are never touched.${NC}\n"
    echo -ne "${GREEN}Keep README showcase SVGs? (Y/n):${NC} "
    read -r keep_showcase
    echo -ne "${GREEN}Keep log files? (Y/n):${NC} "
    read -r keep_logs
    local flags="--yes"
    if [[ "$keep_showcase" == "n" || "$keep_showcase" == "N" ]]; then
        flags="$flags --all"
    else
        flags="$flags --keep-showcase"
    fi
    if [[ "$keep_logs" == "n" || "$keep_logs" == "N" ]]; then
        : # logs will be deleted (default behavior without --keep-logs)
    else
        flags="$flags --keep-logs"
    fi
    bash clean_output.sh --dry-run $flags
    echo ""
    echo -ne "${RED}${BOLD}Proceed with deletion? (type YES):${NC} "
    read -r confirm
    if [[ "$confirm" != "YES" ]]; then
        print_warning "Cancelled"
        return 0
    fi
    bash clean_output.sh $flags
}

# Delete output + fetched data (keeps config, snapshots, git-tracked)
clear_output_with_data() {
    print_header "Delete Output + Fetched Data"
    echo -e "  Deletes output, logs, AND re-fetchable API data (market prices, benchmarks, etc.)."
    echo -e "  ${GREEN}Always preserved:${NC} config files, option chain snapshots, git-tracked reference data.\n"
    bash clean_output.sh --dry-run --all --clean-data
    echo ""
    echo -ne "${RED}${BOLD}Proceed with deletion? (type YES):${NC} "
    read -r confirm
    if [[ "$confirm" != "YES" ]]; then
        print_warning "Cancelled"
        return 0
    fi
    bash clean_output.sh --all --yes --clean-data
}

# Nuclear: build artifacts + output + data + temp files
clean_nuclear() {
    print_header "Nuclear Clean"
    echo -e "  ${RED}Removes everything regeneratable:${NC}"
    echo -e "    - Build artifacts (_build/)"
    echo -e "    - All output and log files"
    echo -e "    - All re-fetchable API data"
    echo -e "    - Temporary files in /tmp"
    echo -e ""
    echo -e "  ${GREEN}Always preserved:${NC} config files, option chain snapshots, git-tracked reference data."
    echo -e "  ${GREEN}Also preserved:${NC} _opam/ (OCaml packages), .venv/ (Python packages)\n"
    bash clean_output.sh --dry-run --all --clean-data
    echo ""
    echo -ne "${RED}${BOLD}Proceed with nuclear clean? (type YES):${NC} "
    read -r confirm
    if [[ "$confirm" != "YES" ]]; then
        print_warning "Cancelled"
        return 0
    fi
    print_info "Cleaning build artifacts..."
    opam exec -- dune clean 2>/dev/null || true
    bash clean_output.sh --all --yes --clean-data
    print_info "Removing temporary files..."
    rm -f /tmp/lp_problem.json /tmp/lp_solution.json
    rm -f /tmp/dcf_market_data_*.json /tmp/dcf_financial_data_*.json
    print_success "Nuclear clean complete"
}

# Regenerate all showcase SVGs
regenerate_showcase_all() {
    print_header "Regenerate All Showcase SVGs"
    echo -e "${YELLOW}This runs the full fetch → analyze → visualize pipeline for every module.${NC}"
    echo -e "${DIM}Requires Docker container to be running. May take 30+ minutes.${NC}\n"
    echo -e "${GREEN}Include data fetching? (y/n, default: y):${NC} "
    read -r fetch_choice
    local flags=""
    if [[ "$fetch_choice" == "n" || "$fetch_choice" == "N" ]]; then
        flags="--skip-fetch"
    fi
    bash regenerate_showcase.sh $flags
}

# Regenerate showcase for a single module
regenerate_showcase_single() {
    print_header "Regenerate Single Module Showcase"
    echo -e "${DIM}Available modules:${NC}\n"
    bash regenerate_showcase.sh --list
    echo ""
    echo -e "${GREEN}Enter module name:${NC} "
    read -r module_name
    if [[ -z "$module_name" ]]; then
        print_warning "No module specified"
        return 0
    fi
    echo -e "${GREEN}Include data fetching? (y/n, default: y):${NC} "
    read -r fetch_choice
    local flags="--module $module_name"
    if [[ "$fetch_choice" == "n" || "$fetch_choice" == "N" ]]; then
        flags="$flags --skip-fetch"
    fi
    bash regenerate_showcase.sh $flags
}

# Regenerate showcase dry run
regenerate_showcase_dry_run() {
    print_header "Regenerate Showcase (Dry Run)"
    echo -e "${DIM}Showing what would run without executing:${NC}\n"
    bash regenerate_showcase.sh --dry-run
}

# Maintenance submenu
show_maintenance_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Maintenance ═══${NC}\n"
        echo -e "${YELLOW}── Delete ──${NC}"
        echo -e "${GREEN}1)${NC} Output only           ${DIM}plots, CSVs, analysis results${NC}"
        echo -e "${GREEN}2)${NC} Output + fetched data  ${DIM}also removes API-fetched data (keeps config & snapshots)${NC}"
        echo -e "${GREEN}3)${NC} Build artifacts        ${DIM}_build/ directory (dune clean)${NC}"
        echo -e "${GREEN}4)${NC} Nuclear                ${DIM}all of the above + temp files${NC}"
        echo ""
        echo -e "${YELLOW}── Regenerate ──${NC}"
        echo -e "${GREEN}5)${NC} All showcase SVGs      ${DIM}full pipeline for every module${NC}"
        echo -e "${GREEN}6)${NC} Single module showcase  ${DIM}pick one module to regenerate${NC}"
        echo -e "${GREEN}7)${NC} Preview (dry run)      ${DIM}show what would be regenerated${NC}"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Main Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) clear_output_interactive ;;
            2) clear_output_with_data ;;
            3) clean_build_artifacts ;;
            4) clean_nuclear ;;
            5) regenerate_showcase_all ;;
            6) regenerate_showcase_single ;;
            7) regenerate_showcase_dry_run ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

# Run submenu (paradigm selection)
show_run_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Run ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Pricing"
        echo -e "${GREEN}2)${NC} Valuation"
        echo -e "${GREEN}3)${NC} Monitoring & Alternative Data"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Main Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) show_pricing_menu ;;
            2) show_valuation_menu ;;
            3) show_monitoring_menu ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

# Pricing submenu
show_pricing_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Pricing ═══${NC}"
        echo -e "${DIM}[IBKR+] = Benefits from IBKR real-time options data${NC}\n"
        echo -e "${GREEN}1)${NC} ${BOLD}Regime-Aware Downside Optimization${NC}"
        echo -e "${DIM}   Constructs portfolios that adapt to market regimes (normal/stress/crisis)"
        echo -e "   using exponentially-weighted moving average beta estimation and conditional"
        echo -e "   value-at-risk (CVaR) optimization to minimize downside risk${NC}"
        echo ""
        echo -e "${GREEN}2)${NC} ${BOLD}Options Hedging${NC} ${CYAN}[IBKR+]${NC}"
        echo -e "${DIM}   Portfolio protection using options strategies (protective put, collar,"
        echo -e "   vertical spread, covered call). Multi-objective optimization generates"
        echo -e "   Pareto frontier showing cost vs protection trade-offs.${NC}"
        echo ""
        echo -e "${GREEN}3)${NC} ${BOLD}Volatility Arbitrage${NC} ${CYAN}[IBKR+]${NC}"
        echo -e "${DIM}   Exploit mispricing between implied and realized volatility. Computes RV"
        echo -e "   using multiple estimators, forecasts vol (GARCH/EWMA/HAR), detects arbitrage"
        echo -e "   opportunities, and generates trading signals for vol strategies.${NC}"
        echo ""
        echo -e "${GREEN}4)${NC} ${BOLD}Variance Swaps & VRP Trading${NC} ${CYAN}[IBKR+]${NC}"
        echo -e "${DIM}   Harvest variance risk premium (VRP) systematically. Price variance swaps"
        echo -e "   using Carr-Madan formula, compute VRP (IV² - RV²), generate trading signals"
        echo -e "   to short variance, and build option replication portfolios.${NC}"
        echo ""
        echo -e "${GREEN}5)${NC} ${BOLD}Skew Trading${NC} ${CYAN}[IBKR+]${NC}"
        echo -e "${DIM}   Trade volatility skew (smile) using risk reversals and butterflies."
        echo -e "   Measures RR25 (put skew), BF25 (smile curvature), generates mean"
        echo -e "   reversion signals, and builds multi-leg skew positions.${NC}"
        echo ""
        echo -e "${GREEN}6)${NC} ${BOLD}Gamma Scalping${NC} ${CYAN}[IBKR+]${NC}"
        echo -e "${DIM}   Delta-hedged options positions profiting from realized volatility."
        echo -e "   Simulates intraday gamma scalping with straddle/strangle positions,"
        echo -e "   4 hedging strategies, and complete P&L attribution (gamma/theta/vega).${NC}"
        echo ""
        echo -e "${GREEN}7)${NC} ${BOLD}FX & Crypto Hedging with Futures${NC}"
        echo -e "${DIM}   Capital-efficient hedging using currency and crypto futures."
        echo -e "   Supports FX (EUR, JPY, GBP, CHF) and crypto (BTC, ETH)."
        echo -e "   Backtests hedge ratios, margin usage, and options pricing.${NC}"
        echo ""
        echo -e "${GREEN}8)${NC} ${BOLD}Dispersion Trading${NC} ${CYAN}[IBKR+]${NC}"
        echo -e "${DIM}   Trade correlation: buy single-name options, sell index options."
        echo -e "   Profits when stocks move independently (low realized correlation)."
        echo -e "   Analyzes implied vs realized correlation, generates signals.${NC}"
        echo ""
        echo -e "${GREEN}9)${NC} ${BOLD}Pairs Trading (Statistical Arbitrage)${NC}"
        echo -e "${DIM}   Trade mean-reverting spread between two cointegrated assets."
        echo -e "   Tests cointegration (Engle-Granger), calculates hedge ratio,"
        echo -e "   generates signals based on z-score thresholds.${NC}"
        echo ""
        echo -e "${GREEN}10)${NC} ${BOLD}Earnings Volatility (IV Crush Scanner)${NC} ${CYAN}[IBKR+]${NC}"
        echo -e "${DIM}    Sell IV around earnings when it's overpriced relative to realized."
        echo -e "    Filters for backwardation, high volume, elevated IV/RV ratio."
        echo -e "    Uses Kelly sizing for calendar spreads or short straddles.${NC}"
        echo ""
        echo -e "${GREEN}11)${NC} ${BOLD}Skew Verticals (Directional Spreads)${NC} ${CYAN}[IBKR+]${NC}"
        echo -e "${DIM}    Directional vertical spreads using momentum and volatility skew."
        echo -e "    Recommends bull call spreads (bullish) or bear put spreads (bearish)"
        echo -e "    based on momentum, with strike selection optimized for skew mispricing.${NC}"
        echo ""
        echo -e "${GREEN}12)${NC} ${BOLD}Pre-Earnings Straddle (ML-Based)${NC} ${CYAN}[IBKR+]${NC}"
        echo -e "${DIM}    Predict earnings moves using machine learning on historical data."
        echo -e "    Trains regression model on implied vs realized move ratios, generates"
        echo -e "    trade signals for buying/selling straddles before earnings announcements.${NC}"
        echo ""
        echo -e "${GREEN}13)${NC} ${BOLD}Forward Factor (Term Structure Arbitrage)${NC} ${CYAN}[IBKR+]${NC}"
        echo -e "${DIM}    Exploit volatility term structure anomalies using calendar spreads."
        echo -e "    Detects backwardation (sell front, buy back) or contango (buy front,"
        echo -e "    sell back) opportunities, computes expected P&L from term structure decay.${NC}"
        echo ""
        echo -e "${GREEN}14)${NC} ${BOLD}Liquidity Analysis${NC}"
        echo -e "${DIM}    Score stocks by tradability and generate volume-based predictive signals."
        echo -e "    Computes Amihud ratio, turnover, OBV divergence, volume surge detection,"
        echo -e "    smart money flow, and composite bullish/bearish signals.${NC}"
        echo ""
        echo -e "${GREEN}15)${NC} ${BOLD}Perpetual Futures Pricing${NC}"
        echo -e "${DIM}    No-arbitrage pricing of perpetual futures (crypto derivatives)."
        echo -e "    Linear, inverse, and quanto contracts. Funding rate analysis,"
        echo -e "    basis computation, and everlasting options pricing (Black-Scholes).${NC}"
        echo ""
        echo -e "${GREEN}16)${NC} ${BOLD}Market Regime Forecast${NC}"
        echo -e "${DIM}    Detect market regimes (trend/volatility) using multiple models:"
        echo -e "    Basic (GARCH+HMM), MS-GARCH, BOCPD (Bayesian changepoint), and GP."
        echo -e "    Generates covered call suitability scores for income ETF timing.${NC}"
        echo ""
        echo -e "${GREEN}17)${NC} ${BOLD}Tail Risk Forecast${NC}"
        echo -e "${DIM}    VaR/ES forecasting using HAR-RV model with jump detection. Uses intraday"
        echo -e "    realized variance to forecast next-day tail risk (5%/1% loss thresholds).${NC}"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Run Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) show_regime_downside_menu ;;
            2) show_options_hedging_menu ;;
            3) show_volatility_arbitrage_menu ;;
            4) show_variance_swaps_menu ;;
            5) show_skew_trading_menu ;;
            6) show_gamma_scalping_menu ;;
            7) show_fx_hedging_menu ;;
            8) show_dispersion_trading_menu ;;
            9) show_pairs_trading_menu ;;
            10) show_earnings_vol_menu ;;
            11) show_skew_verticals_menu ;;
            12) show_pre_earnings_straddle_menu ;;
            13) show_forward_factor_menu ;;
            14) show_liquidity_menu ;;
            15) show_perpetual_futures_menu ;;
            16) show_market_regime_forecast_menu ;;
            17) show_tail_risk_menu ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

# Market Regime Forecast operations
show_market_regime_forecast_menu() {
    local providers
    providers=$(detect_data_provider)
    while true; do
        clear
        echo -e "${BLUE}═══ Market Regime Forecast ═══${NC}\n"
        echo "Detect market regimes using multiple statistical models"
        if echo "$providers" | grep -q "ibkr"; then
            echo -e "  ${GREEN}Data: IBKR${NC} (yfinance fallback)"
        else
            echo -e "  ${YELLOW}Data: yfinance${NC} (IBKR not detected)"
        fi
        echo ""
        echo -e "${GREEN}1)${NC} Fetch Price Data"
        echo -e "${GREEN}2)${NC} Run Basic Model (GARCH+HMM)"
        echo -e "${GREEN}3)${NC} Run MS-GARCH Model"
        echo -e "${GREEN}4)${NC} Run BOCPD Model (Bayesian Changepoint)"
        echo -e "${GREEN}5)${NC} Run GP Model (Gaussian Process)"
        echo -e "${GREEN}6)${NC} Run All Models (Compare)"
        echo -e "${GREEN}7)${NC} Visualize Results"
        echo -e "${GREEN}8)${NC} Run Full Workflow"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Pricing Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_regime_prices ; echo ""; read -rp "Press Enter to continue..." ;;
            2) run_regime_basic ; echo ""; read -rp "Press Enter to continue..." ;;
            3) run_regime_ms_garch ; echo ""; read -rp "Press Enter to continue..." ;;
            4) run_regime_bocpd ; echo ""; read -rp "Press Enter to continue..." ;;
            5) run_regime_gp ; echo ""; read -rp "Press Enter to continue..." ;;
            6) run_regime_all ; echo ""; read -rp "Press Enter to continue..." ;;
            7) visualize_regime_results ; echo ""; read -rp "Press Enter to continue..." ;;
            8|"") run_regime_workflow ; echo ""; read -rp "Press Enter to continue..." ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_regime_prices() {
    print_header "Fetch Price Data for Regime Detection"

    read -p "Enter ticker (default: SPY): " ticker
    ticker=${ticker:-SPY}

    print_info "Fetching price data for $ticker..."

    uv run pricing/market_regime_forecast/python/fetch/fetch_prices.py --ticker "$ticker"

    if [[ -f "pricing/market_regime_forecast/data/${ticker,,}_prices.json" ]]; then
        print_success "Price data saved to pricing/market_regime_forecast/data/"
    else
        print_error "Failed to fetch price data"
    fi
}

run_regime_model() {
    # Helper: run a single regime model
    # Usage: run_regime_model <ticker> <model> <display_name>
    local ticker="$1"
    local model="$2"
    local display_name="$3"

    local datafile="pricing/market_regime_forecast/data/${ticker,,}_prices.json"
    if [[ ! -f "$datafile" ]]; then
        print_error "Data file not found: $datafile"
        print_info "Run 'Fetch Price Data' first"
        return 1
    fi

    mkdir -p pricing/market_regime_forecast/output

    print_info "Running $display_name model for $ticker..."

    opam exec -- dune exec --root pricing/market_regime_forecast/ocaml market_regime_forecast -- \
        "$datafile" --model "$model" \
        --output "pricing/market_regime_forecast/output/${ticker}_${model}.json"

    print_success "$display_name model analysis complete!"
}

run_regime_basic() {
    print_header "Run Basic Model (GARCH+HMM)"
    read -p "Enter ticker (default: SPY): " ticker
    ticker=${ticker:-SPY}
    run_regime_model "$ticker" basic "Basic (GARCH+HMM)"
}

run_regime_ms_garch() {
    print_header "Run MS-GARCH Model"
    read -p "Enter ticker (default: SPY): " ticker
    ticker=${ticker:-SPY}
    run_regime_model "$ticker" ms-garch "MS-GARCH"
}

run_regime_bocpd() {
    print_header "Run BOCPD Model (Bayesian Changepoint)"
    read -p "Enter ticker (default: SPY): " ticker
    ticker=${ticker:-SPY}
    run_regime_model "$ticker" bocpd "BOCPD"
}

run_regime_gp() {
    print_header "Run GP Model (Gaussian Process)"
    read -p "Enter ticker (default: SPY): " ticker
    ticker=${ticker:-SPY}
    run_regime_model "$ticker" gp "GP"
}

run_regime_all() {
    print_header "Run All Regime Models (Compare)"

    read -p "Enter ticker (default: SPY): " ticker
    ticker=${ticker:-SPY}

    local datafile="pricing/market_regime_forecast/data/${ticker,,}_prices.json"
    if [[ ! -f "$datafile" ]]; then
        print_error "Data file not found: $datafile"
        print_info "Run 'Fetch Price Data' first"
        return
    fi

    print_info "Running all 4 models for $ticker..."
    echo ""

    echo -e "${CYAN}=== Basic (GARCH+HMM) ===${NC}"
    run_regime_model "$ticker" basic "Basic (GARCH+HMM)"
    echo ""

    echo -e "${CYAN}=== MS-GARCH ===${NC}"
    run_regime_model "$ticker" ms-garch "MS-GARCH"
    echo ""

    echo -e "${CYAN}=== BOCPD (Bayesian Changepoint) ===${NC}"
    run_regime_model "$ticker" bocpd "BOCPD"
    echo ""

    echo -e "${CYAN}=== GP (Gaussian Process) ===${NC}"
    run_regime_model "$ticker" gp "GP"

    print_success "All models complete!"
}

visualize_regime_results() {
    print_header "Visualize Regime Forecast Results"

    read -p "Enter ticker (default: SPY): " ticker
    ticker=${ticker:-SPY}

    local output_dir="pricing/market_regime_forecast/output"
    local args=""

    # Build args from available output files
    [[ -f "$output_dir/${ticker}_basic.json" ]] && args="$args --basic $output_dir/${ticker}_basic.json"
    [[ -f "$output_dir/${ticker}_ms-garch.json" ]] && args="$args --ms-garch $output_dir/${ticker}_ms-garch.json"
    [[ -f "$output_dir/${ticker}_bocpd.json" ]] && args="$args --bocpd $output_dir/${ticker}_bocpd.json"
    [[ -f "$output_dir/${ticker}_gp.json" ]] && args="$args --gp $output_dir/${ticker}_gp.json"

    if [[ -z "$args" ]]; then
        print_error "No model output files found for $ticker"
        print_info "Run models first to generate output"
        return
    fi

    print_info "Generating regime analysis plot..."

    uv run pricing/market_regime_forecast/python/viz/plot_regime.py \
        --ticker "$ticker" $args

    print_success "Visualization complete!"
}

run_regime_workflow() {
    print_header "Run Full Regime Forecast Workflow"

    read -p "Enter ticker (default: SPY): " ticker
    ticker=${ticker:-SPY}

    # Step 1: Fetch price data
    print_info "Step 1/3: Fetching price data..."
    uv run pricing/market_regime_forecast/python/fetch/fetch_prices.py --ticker "$ticker"

    # Step 2: Run all models
    print_info "Step 2/3: Running all regime models..."
    local datafile="pricing/market_regime_forecast/data/${ticker,,}_prices.json"
    if [[ ! -f "$datafile" ]]; then
        print_error "Data file not found after fetch: $datafile"
        return
    fi

    mkdir -p pricing/market_regime_forecast/output

    for model in basic ms-garch bocpd gp; do
        echo -e "\n${CYAN}=== $model ===${NC}"
        opam exec -- dune exec --root pricing/market_regime_forecast/ocaml market_regime_forecast -- \
            "$datafile" --model "$model" \
            --output "pricing/market_regime_forecast/output/${ticker}_${model}.json"
    done

    # Step 3: Visualize
    print_info "Step 3/3: Generating visualization..."
    local viz_args="--ticker $ticker"
    for model in basic ms-garch bocpd gp; do
        local jf="pricing/market_regime_forecast/output/${ticker}_${model}.json"
        [[ -f "$jf" ]] && viz_args="$viz_args --$model $jf"
    done

    uv run pricing/market_regime_forecast/python/viz/plot_regime.py $viz_args

    print_success "Full regime forecast workflow complete!"
}

# Perpetual Futures Pricing operations
show_perpetual_futures_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Perpetual Futures Pricing ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Fetch Market Data (from exchange)"
        echo -e "${GREEN}2)${NC} Price Linear Perpetual"
        echo -e "${GREEN}3)${NC} Price Inverse Perpetual"
        echo -e "${GREEN}4)${NC} Price Everlasting Call Option"
        echo -e "${GREEN}5)${NC} Price Everlasting Put Option"
        echo -e "${GREEN}6)${NC} Generate Option Price Grid"
        echo -e "${GREEN}7)${NC} Run Full Analysis"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Pricing Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) run_perp_fetch_data ;;
            2) run_perp_linear ;;
            3) run_perp_inverse ;;
            4) run_perp_call_option ;;
            5) run_perp_put_option ;;
            6) run_perp_option_grid ;;
            7|"") run_perp_full_analysis ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

run_perp_fetch_data() {
    echo ""
    echo -e "${YELLOW}Enter symbol (default: BTCUSDT):${NC} "
    read -r symbol
    symbol="${symbol:-BTCUSDT}"

    echo -e "${YELLOW}Enter exchange (binance/deribit/bybit, default: binance):${NC} "
    read -r exchange
    exchange="${exchange:-binance}"

    echo ""
    echo -e "${GREEN}Fetching perpetual futures data...${NC}"
    uv run pricing/perpetual_futures/python/fetch/fetch_perp_data.py \
        --symbol "$symbol" --exchange "$exchange"
}

run_perp_linear() {
    echo ""
    echo -e "${YELLOW}Enter spot price (e.g., 50000):${NC} "
    read -r spot

    echo -e "${YELLOW}Enter kappa (premium rate, e.g., 1.0):${NC} "
    read -r kappa

    echo -e "${YELLOW}Enter r_a (quote currency rate, e.g., 0.05):${NC} "
    read -r r_a

    echo -e "${YELLOW}Enter r_b (base currency rate, e.g., 0.0):${NC} "
    read -r r_b

    echo ""
    echo -e "${GREEN}Pricing linear perpetual futures...${NC}"
    eval $(opam env)
    dune exec pricing/perpetual_futures/ocaml/bin/main.exe -- \
        --type linear --spot "$spot" --kappa "$kappa" --r_a "$r_a" --r_b "$r_b"
}

run_perp_inverse() {
    echo ""
    echo -e "${YELLOW}Enter spot price (e.g., 50000):${NC} "
    read -r spot

    echo -e "${YELLOW}Enter kappa (premium rate, e.g., 1.0):${NC} "
    read -r kappa

    echo -e "${YELLOW}Enter r_a (quote currency rate, e.g., 0.05):${NC} "
    read -r r_a

    echo -e "${YELLOW}Enter r_b (base currency rate, e.g., 0.0):${NC} "
    read -r r_b

    echo ""
    echo -e "${GREEN}Pricing inverse perpetual futures...${NC}"
    eval $(opam env)
    dune exec pricing/perpetual_futures/ocaml/bin/main.exe -- \
        --type inverse --spot "$spot" --kappa "$kappa" --r_a "$r_a" --r_b "$r_b"
}

run_perp_call_option() {
    echo ""
    echo -e "${YELLOW}Enter spot price (e.g., 50000):${NC} "
    read -r spot

    echo -e "${YELLOW}Enter strike price (e.g., 50000):${NC} "
    read -r strike

    echo -e "${YELLOW}Enter kappa (premium rate, e.g., 1.0):${NC} "
    read -r kappa

    echo -e "${YELLOW}Enter sigma (volatility, e.g., 0.8):${NC} "
    read -r sigma

    echo ""
    echo -e "${GREEN}Pricing everlasting call option...${NC}"
    eval $(opam env)
    dune exec pricing/perpetual_futures/ocaml/bin/main.exe -- \
        --option call --spot "$spot" --strike "$strike" --kappa "$kappa" \
        --sigma "$sigma" --r_a 0.0 --r_b 0.0
}

run_perp_put_option() {
    echo ""
    echo -e "${YELLOW}Enter spot price (e.g., 50000):${NC} "
    read -r spot

    echo -e "${YELLOW}Enter strike price (e.g., 50000):${NC} "
    read -r strike

    echo -e "${YELLOW}Enter kappa (premium rate, e.g., 1.0):${NC} "
    read -r kappa

    echo -e "${YELLOW}Enter sigma (volatility, e.g., 0.8):${NC} "
    read -r sigma

    echo ""
    echo -e "${GREEN}Pricing everlasting put option...${NC}"
    eval $(opam env)
    dune exec pricing/perpetual_futures/ocaml/bin/main.exe -- \
        --option put --spot "$spot" --strike "$strike" --kappa "$kappa" \
        --sigma "$sigma" --r_a 0.0 --r_b 0.0
}

run_perp_option_grid() {
    echo ""
    echo -e "${YELLOW}Enter strike price (e.g., 50000):${NC} "
    read -r strike

    echo -e "${YELLOW}Enter spot min (e.g., 30000):${NC} "
    read -r spot_min

    echo -e "${YELLOW}Enter spot max (e.g., 70000):${NC} "
    read -r spot_max

    echo -e "${YELLOW}Enter kappa (premium rate, e.g., 1.0):${NC} "
    read -r kappa

    echo -e "${YELLOW}Enter sigma (volatility, e.g., 0.8):${NC} "
    read -r sigma

    echo ""
    echo -e "${GREEN}Generating option price grid...${NC}"
    eval $(opam env)
    dune exec pricing/perpetual_futures/ocaml/bin/main.exe -- \
        --grid --strike "$strike" --spot-min "$spot_min" --spot-max "$spot_max" \
        --kappa "$kappa" --sigma "$sigma" --r_a 0.0 --r_b 0.0

    echo ""
    echo -e "${GREEN}Grid saved to pricing/perpetual_futures/output/option_grid.csv${NC}"
}

run_perp_full_analysis() {
    echo ""
    echo -e "${YELLOW}Enter symbol (default: BTCUSDT):${NC} "
    read -r symbol
    symbol="${symbol:-BTCUSDT}"

    echo ""
    echo -e "${GREEN}Step 1/3: Fetching market data...${NC}"
    uv run pricing/perpetual_futures/python/fetch/fetch_perp_data.py \
        --symbol "$symbol" --exchange binance

    echo ""
    echo -e "${GREEN}Step 2/3: Pricing with theoretical model...${NC}"
    eval $(opam env)
    dune exec perpetual_futures -- \
        --data pricing/perpetual_futures/data/market_data.json \
        --type linear --kappa 1.095 --r_a 0.05 --r_b 0.0 \
        --output pricing/perpetual_futures/output/analysis.json

    echo ""
    echo -e "${GREEN}Step 3/3: Generating visualization...${NC}"
    uv run python pricing/perpetual_futures/python/viz/plot_perpetual.py \
        --input pricing/perpetual_futures/output/analysis.json

    if [[ -d "pricing/perpetual_futures/output/plots" ]]; then
        print_success "Analysis complete! Plot saved to: pricing/perpetual_futures/output/plots/"
    else
        echo -e "${GREEN}Analysis complete!${NC}"
    fi
}

# Liquidity Analysis operations
show_liquidity_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Liquidity Analysis ═══${NC}\n"
        echo -e "${DIM}Feeds into: Skew Trading, Variance Swaps, Pre-Earnings Straddle collectors${NC}"
        echo -e "${DIM}Gate 1 (stock liquidity) → Gate 2 (option chain coverage) → price segments${NC}"
        echo ""
        echo -e "${GREEN}1)${NC} Fetch Market Data"
        echo -e "${GREEN}2)${NC} Run Liquidity Analysis"
        echo -e "${GREEN}3)${NC} Generate Dashboard"
        echo -e "${GREEN}4)${NC} Generate Single Ticker Detail"
        echo -e "${GREEN}5)${NC} Run Full Workflow"
        echo ""
        echo -e "${CYAN}--- Optionable Screening ---${NC}"
        echo -e "${GREEN}6)${NC} Fetch Optionable Tickers (CBOE)"
        echo -e "${GREEN}7)${NC} Screen Optionables for Liquidity"
        echo -e "${GREEN}8)${NC} Screen Options Chain Depth"
        echo -e "${GREEN}9)${NC} Subset Liquid Tickers by Price"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Pricing Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_liquidity_data ;;
            2) run_liquidity_analysis ;;
            3) plot_liquidity_dashboard ;;
            4) plot_liquidity_single ;;
            5|"") run_liquidity_full_workflow ;;
            6) fetch_optionable_tickers ;;
            7) screen_optionables_for_liquidity ;;
            8) screen_options_chain_depth ;;
            9) subset_liquid_by_price ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_liquidity_data() {
    print_header "Fetch Liquidity Market Data"

    echo -e "${YELLOW}Enter tickers (comma-separated, or press Enter for defaults):${NC}"
    read -r tickers

    if [[ -z "$tickers" ]]; then
        .venv/bin/python3 pricing/liquidity/python/fetch_liquidity_data.py
    else
        .venv/bin/python3 pricing/liquidity/python/fetch_liquidity_data.py --tickers "$tickers"
    fi

    if [[ -f "pricing/liquidity/data/market_data.json" ]]; then
        print_success "Market data saved to: pricing/liquidity/data/market_data.json"
    else
        print_error "Failed to fetch market data"
    fi
}

run_liquidity_analysis() {
    print_header "Run Liquidity Analysis (OCaml)"

    if [[ ! -f "pricing/liquidity/data/market_data.json" ]]; then
        print_error "No market data found. Run 'Fetch Market Data' first."
        return 1
    fi

    dune exec pricing/liquidity/ocaml/bin/main.exe -- \
        --data pricing/liquidity/data/market_data.json \
        --output pricing/liquidity/output/liquidity_results.json

    if [[ -f "pricing/liquidity/output/liquidity_results.json" ]]; then
        print_success "Results saved to: pricing/liquidity/output/liquidity_results.json"
    else
        print_error "Analysis failed"
    fi
}

plot_liquidity_dashboard() {
    print_header "Generate Liquidity Dashboard"

    if [[ ! -f "pricing/liquidity/output/liquidity_results.json" ]]; then
        print_error "No results found. Run 'Run Liquidity Analysis' first."
        return 1
    fi

    .venv/bin/python3 pricing/liquidity/python/plot_liquidity.py

    if [[ -f "pricing/liquidity/output/liquidity_dashboard.png" ]]; then
        print_success "Dashboard saved to: pricing/liquidity/output/liquidity_dashboard.png"
    else
        print_error "Failed to generate dashboard"
    fi
}

plot_liquidity_single() {
    print_header "Generate Single Ticker Detail"

    echo -e "${YELLOW}Enter ticker symbol:${NC}"
    read -r ticker

    if [[ -z "$ticker" ]]; then
        print_error "Ticker required"
        return 1
    fi

    .venv/bin/python3 pricing/liquidity/python/plot_liquidity.py --ticker "$ticker"

    local output_file="pricing/liquidity/output/${ticker}_liquidity_detail.png"
    if [[ -f "$output_file" ]]; then
        print_success "Detail chart saved to: $output_file"
    else
        print_error "Failed to generate detail chart"
    fi
}

run_liquidity_full_workflow() {
    print_header "Liquidity Analysis - Full Workflow"

    echo -e "${YELLOW}Enter tickers (comma-separated, or press Enter for defaults):${NC}"
    read -r tickers

    # Step 1: Fetch data
    print_info "Step 1/3: Fetching market data..."
    if [[ -z "$tickers" ]]; then
        .venv/bin/python3 pricing/liquidity/python/fetch_liquidity_data.py
    else
        .venv/bin/python3 pricing/liquidity/python/fetch_liquidity_data.py --tickers "$tickers"
    fi

    if [[ ! -f "pricing/liquidity/data/market_data.json" ]]; then
        print_error "Failed to fetch market data"
        return 1
    fi
    print_success "Market data fetched"

    # Step 2: Run OCaml analysis
    print_info "Step 2/3: Running liquidity analysis..."
    dune exec pricing/liquidity/ocaml/bin/main.exe -- \
        --data pricing/liquidity/data/market_data.json \
        --output pricing/liquidity/output/liquidity_results.json

    if [[ ! -f "pricing/liquidity/output/liquidity_results.json" ]]; then
        print_error "Analysis failed"
        return 1
    fi
    print_success "Analysis complete"

    # Step 3: Generate dashboard
    print_info "Step 3/3: Generating dashboard..."
    .venv/bin/python3 pricing/liquidity/python/plot_liquidity.py

    if [[ -f "pricing/liquidity/output/liquidity_dashboard.png" ]]; then
        print_success "Dashboard saved to: pricing/liquidity/output/liquidity_dashboard.png"
    fi

    print_success "Full workflow complete!"
}

fetch_optionable_tickers() {
    print_header "Fetch Optionable Tickers from CBOE"

    uv run pricing/liquidity/python/fetch/fetch_optionable_tickers.py

    if [[ -f "pricing/liquidity/data/optionable_tickers.csv" ]]; then
        local count
        count=$(tail -n +2 pricing/liquidity/data/optionable_tickers.csv | wc -l)
        print_success "Saved $count optionable tickers to pricing/liquidity/data/optionable_tickers.csv"
    else
        print_error "Failed to fetch optionable tickers"
    fi
}

screen_optionables_for_liquidity() {
    print_header "Screen Optionables for Liquidity"

    if [[ ! -f "pricing/liquidity/data/optionable_tickers.csv" ]]; then
        print_error "No optionable tickers found. Run 'Fetch Optionable Tickers' first."
        return 1
    fi

    local count
    count=$(tail -n +2 pricing/liquidity/data/optionable_tickers.csv | wc -l)
    print_info "Screening $count optionable tickers (score >= 75)"
    print_info "This is a long-running process (~17h for full run). Resumable if interrupted."

    echo -e "${YELLOW}Batch size (Enter=100):${NC}"
    read -r batch_size
    batch_size=${batch_size:-20}

    echo -e "${YELLOW}Delay between tickers in seconds (Enter=10):${NC}"
    read -r delay
    delay=${delay:-10}

    echo -e "${YELLOW}Start fresh? Ignore previous progress? (y/N):${NC}"
    read -r fresh
    local resume_flag=""
    if [[ "$fresh" == "y" || "$fresh" == "Y" ]]; then
        resume_flag="--no-resume"
    fi

    uv run pricing/liquidity/python/fetch/filter_liquid_tickers.py \
        --batch-size "$batch_size" \
        --delay "$delay" \
        $resume_flag

    if [[ -f "pricing/liquidity/data/liquid_tickers.txt" ]]; then
        local liquid_count
        liquid_count=$(wc -l < pricing/liquidity/data/liquid_tickers.txt)
        print_success "$liquid_count liquid tickers written to pricing/liquidity/data/liquid_tickers.txt"
    fi
}

screen_options_chain_depth() {
    print_header "Screen Options Chain Depth (Gate 2)"

    if [[ ! -f "pricing/liquidity/data/liquid_tickers.txt" ]]; then
        print_error "No liquid tickers found. Run 'Screen Optionables for Liquidity' first."
        return 1
    fi

    local ticker_count
    ticker_count=$(wc -l < pricing/liquidity/data/liquid_tickers.txt | tr -d ' ')
    print_info "Input: $ticker_count liquid tickers from gate 1"
    print_info "Checks each ticker for >= 3 valid expiries and >= 5 OTM strikes (SVI requirements)"

    echo -e "${YELLOW}Batch size (default: 20):${NC} "
    read -r batch_size
    batch_size=${batch_size:-20}

    echo -e "${YELLOW}Delay between tickers in seconds (default: 2):${NC} "
    read -r delay
    delay=${delay:-2}

    uv run pricing/liquidity/python/fetch/filter_liquid_options.py \
        --batch-size "$batch_size" \
        --delay "$delay"

    if [ $? -eq 0 ]; then
        if [[ -f "pricing/liquidity/data/liquid_options.txt" ]]; then
            local pass_count
            pass_count=$(wc -l < pricing/liquidity/data/liquid_options.txt | tr -d ' ')
            print_success "Gate 2 complete: $pass_count tickers with deep options chains"
            print_info "Output: pricing/liquidity/data/liquid_options.txt"
        fi
    else
        print_error "Options chain screening failed"
    fi

    echo ""
    echo -e "${YELLOW}Jump to:${NC}  ${GREEN}s)${NC} Skew Trading  ${GREEN}v)${NC} Variance Swaps  ${GREEN}e)${NC} Pre-Earnings  ${GREEN}p)${NC} Subset by Price  ${GREEN}Enter)${NC} Stay"
    read -r jump
    case $jump in
        s) show_skew_trading_menu ;;
        v) show_variance_swaps_menu ;;
        e) show_pre_earnings_straddle_menu ;;
        p) subset_liquid_by_price ;;
    esac
}

subset_liquid_by_price() {
    print_header "Subset Liquid Tickers by Price"

    if [[ ! -f "pricing/liquidity/data/liquid_tickers.txt" ]]; then
        print_error "No liquid tickers found. Run 'Screen Optionables for Liquidity' first."
        return 1
    fi

    echo -e "${YELLOW}Enter max price in USD, or 'segments' for all \$10 segments up to \$200 (e.g., 50):${NC}"
    read -r choice

    if [[ -z "$choice" ]]; then
        print_error "Input required"
        return 1
    fi

    if [[ "$choice" == "segments" ]]; then
        print_info "Generating all price segments..."
        uv run pricing/liquidity/python/fetch/subset_by_price.py --segments
    else
        print_info "Fetching prices and filtering below \$$choice..."
        uv run pricing/liquidity/python/fetch/subset_by_price.py --max-price "$choice"
    fi
}

# Regime-aware downside optimization operations
show_regime_downside_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Regime-Aware Downside Optimization ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Fetch Benchmark Data (S&P 500)"
        echo -e "${GREEN}2)${NC} Fetch Asset Data"
        echo -e "${GREEN}3)${NC} Run Portfolio Optimization"
        echo -e "${GREEN}4)${NC} Generate Plots"
        echo -e "${GREEN}5)${NC} Run Full Workflow"
        echo -e "${GREEN}6)${NC} Quick Demo (shortest runtime)"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Pricing"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_benchmark_data ;;
            2) fetch_asset_data ;;
            3) run_optimization ;;
            4) generate_plots ;;
            5|"") run_full_workflow ;;
            6) run_quick_demo ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

# Quick demo with shortest runtime (auto-calculated parameters)
run_quick_demo() {
    print_header "Quick Demo - Shortest Runtime"

    # Use default or last-fetched tickers
    local tickers="AMZN,CBOE,CVX,IBKR,JPM,LLY,TAC"
    if [[ -f "pricing/regime_downside/data/.last_tickers" ]]; then
        tickers=$(cat pricing/regime_downside/data/.last_tickers)
    fi
    local ticker_count=$(echo "$tickers" | tr ',' '\n' | wc -l)

    # Step 1: Fetch benchmark if needed
    if [[ ! -f "pricing/regime_downside/data/benchmark_returns.csv" ]]; then
        print_info "Fetching benchmark data..."
        fetch_benchmark_data
    else
        print_info "Benchmark data exists, skipping fetch"
    fi

    # Step 2: Fetch asset data if needed (check first ticker)
    local first_ticker=$(echo "$tickers" | cut -d',' -f1 | xargs)
    if [[ ! -f "pricing/regime_downside/data/${first_ticker}_returns.csv" ]]; then
        print_info "Fetching asset data for: $tickers"
        # Use the fetch script directly with defaults
        .venv/bin/python3 pricing/regime_downside/python/fetch/fetch_assets.py \
            --tickers "$tickers" \
            --output-dir pricing/regime_downside/data \
            --years 3
        echo "$tickers" > pricing/regime_downside/data/.last_tickers
    else
        print_info "Asset data exists for $first_ticker, skipping fetch"
    fi

    # Step 3: Detect available data
    print_info "Checking available data..."
    local min_days=$(get_min_data_length "$tickers")
    if [[ $? -ne 0 ]] || [[ -z "$min_days" ]]; then
        print_error "Failed to detect data availability."
        return 1
    fi
    print_info "Available data: $min_days days"

    # Step 4: Calculate shortest viable runtime parameters
    # Use 63-day lookback (3 months - minimum viable)
    local lookback=63

    # Target ~60 backtest days for quick demo
    local target_backtest=60

    # Constraint: start + lookback <= min_days
    # Backtest period = min_days - start
    # So: start = min_days - target_backtest
    # But also: start <= min_days - lookback (max valid start)
    local max_start=$((min_days - lookback))
    local start=$((min_days - target_backtest))

    # Ensure we don't exceed the OCaml constraint
    if [[ $start -gt $max_start ]]; then
        start=$max_start
    fi

    # Recalculate actual backtest period
    local backtest_period=$((min_days - start))

    # Validate we have enough data
    if [[ $backtest_period -lt 10 ]]; then
        print_error "Not enough data for quick demo. Need at least $((lookback + 10)) days, have $min_days."
        return 1
    fi

    print_info "Quick demo parameters (auto-calculated):"
    print_info "  Tickers: $tickers ($ticker_count assets)"
    print_info "  Lookback: $lookback days (3 months)"
    print_info "  Start index: $start"
    print_info "  Backtest: $backtest_period days"
    print_info "  Initial: 100% cash"
    echo ""

    # Step 5: Run optimization
    print_info "Running optimization..."
    opam exec -- dune exec regime_downside -- \
        -tickers "$tickers" \
        -start "$start" \
        -lookback "$lookback" \
        -init "cash"

    if [[ ! -f "pricing/regime_downside/output/optimization_results.csv" ]]; then
        print_error "Optimization failed"
        return 1
    fi

    # Step 6: Generate plots
    print_info "Generating plots..."
    .venv/bin/python3 pricing/regime_downside/python/viz/plot_results.py

    if [[ -f "pricing/regime_downside/output/portfolio_weights.png" ]]; then
        print_success "Quick demo complete!"
        print_info "Output: pricing/regime_downside/output/"
    else
        print_error "Failed to generate plots"
        return 1
    fi
}

# Valuation submenu
show_valuation_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Valuation ═══${NC}\n"
        echo -e "${GREEN}1)${NC} ${BOLD}DCF Deterministic${NC}"
        echo -e "${DIM}   Point estimates of intrinsic value using free cash flow (FCFE/FCFF) with"
        echo -e "   sensitivity analysis across growth rates, discount rates, and terminal growth${NC}"
        echo ""
        echo -e "${GREEN}2)${NC} ${BOLD}DCF Probabilistic (Monte Carlo)${NC}"
        echo -e "${DIM}   Probabilistic valuation with uncertainty quantification via Monte Carlo simulation,"
        echo -e "   generating distributions of intrinsic value and portfolio efficient frontiers${NC}"
        echo ""
        echo -e "${GREEN}3)${NC} ${BOLD}Crypto Treasury Valuation${NC}"
        echo -e "${DIM}   Value companies by BTC/ETH holdings using mNAV (multiple of Net Asset Value)."
        echo -e "   Compares market cap to crypto holdings value, identifies discount/premium.${NC}"
        echo ""
        echo -e "${GREEN}4)${NC} ${BOLD}DCF REIT Valuation${NC}"
        echo -e "${DIM}   Value REITs using NAV, FFO/AFFO multiples, and dividend discount models."
        echo -e "   Accounts for property-type risk premiums and interest rate sensitivity.${NC}"
        echo ""
        echo -e "${GREEN}5)${NC} ${BOLD}Dividend Income Analysis${NC}"
        echo -e "${DIM}   Analyze dividend stocks using DDM valuation, safety scores, and income metrics."
        echo -e "   Calculates yield, growth rates, payout ratios, and generates buy/hold signals.${NC}"
        echo ""
        echo -e "${GREEN}6)${NC} ${BOLD}ETF Analysis${NC}"
        echo -e "${DIM}   Comprehensive ETF analysis: expense ratios, tracking error, premium/discount."
        echo -e "   Auto-detects ETF types (covered call, buffer, leveraged, volatility).${NC}"
        echo ""
        echo -e "${GREEN}7)${NC} ${BOLD}GARP/PEG Analysis${NC}"
        echo -e "${DIM}   Growth at Reasonable Price scoring using PEG/PEGY ratios, quality metrics,"
        echo -e "   and composite scores (growth + quality + balance sheet + ROE).${NC}"
        echo ""
        echo -e "${GREEN}8)${NC} ${BOLD}Growth Analysis${NC}"
        echo -e "${DIM}   Analyze growth stocks: revenue growth, Rule of 40, margins, and efficiency."
        echo -e "   Scores companies on growth sustainability and profitability balance.${NC}"
        echo ""
        echo -e "${GREEN}9)${NC} ${BOLD}Relative Valuation${NC}"
        echo -e "${DIM}   Peer comparison analysis using valuation multiples (P/E, P/B, EV/EBITDA)."
        echo -e "   Positions target company vs peer group with percentile rankings.${NC}"
        echo ""
        echo -e "${GREEN}10)${NC} ${BOLD}Normalized Multiples${NC}"
        echo -e "${DIM}    All common multiples with explicit time windows (TTM/NTM). Quality-adjusted"
        echo -e "    percentile scoring vs sector benchmarks. Single-ticker and comparative modes.${NC}"
        echo ""
        echo -e "${GREEN}11)${NC} ${BOLD}Analyst Upside${NC}"
        echo -e "${DIM}    Scan analyst price targets to find biggest upside opportunities."
        echo -e "    Ranks by upside %, filters by analyst coverage, maps conviction vs dispersion.${NC}"
        echo ""
        echo -e "${GREEN}12)${NC} ${BOLD}Panel (Multi-Model View)${NC}"
        echo -e "${DIM}    Run multiple valuation models per ticker. Each model's verdict presented"
        echo -e "    as-is — a panel of experts, each speaking for itself.${NC}"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Run Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) show_dcf_deterministic_menu ;;
            2) show_dcf_probabilistic_menu ;;
            3) show_crypto_treasury_menu ;;
            4) show_dcf_reit_menu ;;
            5) show_dividend_income_menu ;;
            6) show_etf_analysis_menu ;;
            7) show_garp_peg_menu ;;
            8) show_growth_analysis_menu ;;
            9) show_relative_valuation_menu ;;
            10) show_normalized_multiples_menu ;;
            11) show_analyst_upside_menu ;;
            12) show_panel_menu ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

# ═══════════════════════════════════════════════════════════════════════════════
# Analyst Upside
# ═══════════════════════════════════════════════════════════════════════════════

show_analyst_upside_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Analyst Upside ═══${NC}\n"
        echo -e "${BOLD}  Custom${NC}"
        echo -e "${GREEN}1)${NC}  Custom Tickers"
        echo ""
        echo -e "${BOLD}  Index-Based${NC}"
        echo -e "${GREEN}2)${NC}  S&P 500 Top 50"
        echo -e "${GREEN}3)${NC}  NASDAQ Top 30"
        echo -e "${GREEN}4)${NC}  Dow 30"
        echo ""
        echo -e "${BOLD}  Sector-Based${NC}"
        echo -e "${GREEN}5)${NC}  Technology (20 stocks)"
        echo -e "${GREEN}6)${NC}  Healthcare (20 stocks)"
        echo -e "${GREEN}7)${NC}  Industrials (20 stocks)"
        echo -e "${GREEN}8)${NC}  Consumer (20 stocks)"
        echo -e "${GREEN}9)${NC}  Financials (20 stocks)"
        echo -e "${GREEN}10)${NC} Energy (20 stocks)"
        echo ""
        echo -e "${BOLD}  Thematic${NC}"
        echo -e "${GREEN}11)${NC} AI / Machine Learning"
        echo -e "${GREEN}12)${NC} Clean Energy / EV"
        echo -e "${GREEN}13)${NC} Dividend Aristocrats"
        echo ""
        echo -e "${BOLD}  Market-Cap Tiers${NC}"
        echo -e "${GREEN}14)${NC} Mid-Cap Picks"
        echo -e "${GREEN}15)${NC} Small-Cap Picks"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Valuation Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) run_analyst_upside_custom ;;
            2) run_analyst_upside_universe sp50 ;;
            3) run_analyst_upside_universe nasdaq30 ;;
            4) run_analyst_upside_universe dow30 ;;
            5) run_analyst_upside_universe tech ;;
            6) run_analyst_upside_universe healthcare ;;
            7) run_analyst_upside_universe industrials ;;
            8) run_analyst_upside_universe consumer ;;
            9) run_analyst_upside_universe financials ;;
            10) run_analyst_upside_universe energy ;;
            11) run_analyst_upside_universe ai ;;
            12) run_analyst_upside_universe clean_energy ;;
            13) run_analyst_upside_universe div_aristocrats ;;
            14) run_analyst_upside_universe midcap ;;
            15) run_analyst_upside_universe smallcap ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

run_analyst_upside_custom() {
    print_header "Analyst Upside - Custom Tickers"

    local default_tickers="CAT,DE,GE,HON,MMM,EMR,ITW,ETN"

    echo -e "${YELLOW}Enter ticker symbols (comma-separated):${NC}"
    echo -e "${BLUE}Press Enter for default: $default_tickers${NC}"
    read -r tickers

    if [[ -z "$tickers" ]]; then
        tickers="$default_tickers"
        print_info "Using default tickers"
    fi

    tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]')
    print_info "Scanning $tickers..."

    uv run python valuation/analyst_upside/python/fetch_targets.py \
        -t "$tickers" \
        -o valuation/analyst_upside/output/targets.json

    if [[ -f "valuation/analyst_upside/output/targets.json" ]]; then
        print_info "Generating plots..."
        uv run python valuation/analyst_upside/python/viz/plot_upside.py \
            -i valuation/analyst_upside/output/targets.json
    fi

    print_success "Analyst upside scan complete"
}

run_analyst_upside_universe() {
    local universe="$1"
    print_header "Analyst Upside - ${universe^^}"

    print_info "Scanning $universe universe..."

    uv run python valuation/analyst_upside/python/fetch_targets.py \
        -u "$universe" \
        -o valuation/analyst_upside/output/targets.json

    if [[ -f "valuation/analyst_upside/output/targets.json" ]]; then
        print_info "Generating plots..."
        uv run python valuation/analyst_upside/python/viz/plot_upside.py \
            -i valuation/analyst_upside/output/targets.json
    fi

    print_success "Analyst upside scan complete"
}

# Tail Risk Forecast menu
show_tail_risk_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Tail Risk Forecast ═══${NC}\n"
        echo -e "${GREEN}1)${NC} ${BOLD}Run Tail Risk Forecast${NC}"
        echo -e "${DIM}   Fetch intraday data and forecast VaR/ES for a ticker${NC}"
        echo ""
        echo -e "${GREEN}2)${NC} ${BOLD}Run Multiple Tickers${NC}"
        echo -e "${DIM}   Forecast tail risk for multiple tickers${NC}"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Valuation Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) run_tail_risk_single ;;
            2) run_tail_risk_multiple ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

run_tail_risk_single() {
    print_header "Tail Risk Forecast"

    echo -e "${YELLOW}Enter ticker symbol (default: SPY):${NC}"
    read -r ticker
    ticker="${ticker:-SPY}"

    ticker=$(echo "$ticker" | tr '[:lower:]' '[:upper:]')
    print_info "Step 1/3: Fetching intraday data for $ticker..."

    # Fetch intraday data
    if ! uv run python pricing/tail_risk_forecast/python/fetch/fetch_intraday.py --ticker "$ticker"; then
        print_error "Failed to fetch intraday data"
        return 1
    fi

    print_info "Step 2/3: Running tail risk forecast..."
    eval $(opam env)
    dune exec tail_risk_forecast -- --ticker "$ticker" --json

    print_info "Step 3/3: Generating visualization..."
    uv run python pricing/tail_risk_forecast/python/viz/plot_forecast.py \
        --input "pricing/tail_risk_forecast/output/forecast_${ticker}.json"

    if [[ -f "pricing/tail_risk_forecast/output/plots/${ticker}_tail_risk.png" ]]; then
        print_success "Plot saved to: pricing/tail_risk_forecast/output/plots/${ticker}_tail_risk.png"
    fi

    echo ""
    echo -e "${GREEN}Tail risk forecast complete.${NC}"
    read -p "Press Enter to continue..."
}

run_tail_risk_multiple() {
    print_header "Tail Risk Forecast - Multiple Tickers"

    echo -e "${YELLOW}Enter tickers (comma-separated, default: SPY,SOXL):${NC}"
    read -r tickers
    tickers="${tickers:-SPY,SOXL}"

    eval $(opam env)

    IFS=',' read -ra ticker_array <<< "$tickers"
    for ticker in "${ticker_array[@]}"; do
        ticker=$(echo "$ticker" | tr '[:lower:]' '[:upper:]' | xargs)
        print_info "Processing $ticker..."

        # Fetch intraday data
        if uv run python pricing/tail_risk_forecast/python/fetch/fetch_intraday.py --ticker "$ticker" > /dev/null 2>&1; then
            dune exec tail_risk_forecast -- --ticker "$ticker" --json

            # Generate visualization
            uv run python pricing/tail_risk_forecast/python/viz/plot_forecast.py \
                --input "pricing/tail_risk_forecast/output/forecast_${ticker}.json"
        else
            print_warning "Failed to fetch data for $ticker"
        fi
        echo ""
    done

    echo -e "${GREEN}Tail risk forecast complete for all tickers.${NC}"
    read -p "Press Enter to continue..."
}

# Normalized Multiples menu
show_normalized_multiples_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Normalized Multiples ═══${NC}\n"
        echo -e "${GREEN}1)${NC} ${BOLD}Single Ticker Analysis${NC}"
        echo -e "${DIM}   Deep-dive into one stock: all multiples with time windows (TTM/NTM),"
        echo -e "   percentile ranks vs sector, quality adjustments, implied prices"
        echo -e "   (Not suited for banks, insurance, or oil & gas — use DCF Deterministic)${NC}"
        echo ""
        echo -e "${GREEN}2)${NC} ${BOLD}Comparative Analysis${NC}"
        echo -e "${DIM}   Compare multiple tickers head-to-head: rankings by P/E, EV/EBITDA, PEG."
        echo -e "   Identifies best value and quality-adjusted picks${NC}"
        echo ""
        echo -e "${GREEN}3)${NC} ${BOLD}Refresh Sector Benchmarks${NC}"
        echo -e "${DIM}   Update sector median/P25/P75 stats by sampling S&P 500 constituents${NC}"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Valuation Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) run_normalized_multiples_single ;;
            2) run_normalized_multiples_compare ;;
            3) refresh_sector_benchmarks ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

run_normalized_multiples_single() {
    print_header "Normalized Multiples - Single Ticker"

    local default_tickers="CAT DE GE HON"

    echo -e "${YELLOW}Enter ticker symbols (space-separated):${NC}"
    echo -e "${BLUE}Press Enter for default: $default_tickers${NC}"
    read -r tickers

    if [[ -z "$tickers" ]]; then
        tickers="$default_tickers"
        print_info "Using default tickers"
    fi

    tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]')

    # Build first
    eval $(opam env)
    if ! dune build valuation/normalized_multiples/ocaml/bin/main.exe > /dev/null 2>&1; then
        print_error "Failed to build normalized_multiples"
        return 1
    fi

    for ticker in $tickers; do
        print_info "Running analysis for $ticker..."
        dune exec normalized_multiples -- \
            --tickers "$ticker" \
            --json \
            --python 'uv run python'

        # Generate plots
        local result_file="valuation/normalized_multiples/output/multiples_result_${ticker}.json"
        if [[ -f "$result_file" ]]; then
            uv run python valuation/normalized_multiples/python/viz/plot_multiples.py \
                -i "$result_file"
        fi
    done

    echo ""
    print_success "Analysis complete"
}

run_normalized_multiples_compare() {
    print_header "Normalized Multiples - Comparative Analysis"

    local default_tickers="CAT,DE,GE,HON"

    echo -e "${YELLOW}Enter ticker symbols (comma-separated):${NC}"
    echo -e "${BLUE}Press Enter for default: $default_tickers${NC}"
    read -r tickers

    if [[ -z "$tickers" ]]; then
        tickers="$default_tickers"
        print_info "Using default tickers"
    fi

    tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]')
    print_info "Running comparative analysis..."

    eval $(opam env)
    if ! dune build valuation/normalized_multiples/ocaml/bin/main.exe > /dev/null 2>&1; then
        print_error "Failed to build normalized_multiples"
        return 1
    fi

    dune exec normalized_multiples -- \
        --tickers "$tickers" \
        --mode compare \
        --python 'uv run python'

    print_info "Generating comparison plot..."
    uv run python valuation/normalized_multiples/python/viz/plot_multiples.py \
        -i valuation/normalized_multiples/output/multiples_comparison.json \
        --comparison

    echo ""
    print_success "Comparative analysis complete"
}

refresh_sector_benchmarks() {
    print_header "Refresh Sector Benchmarks"

    print_info "Fetching benchmark data from S&P 500 constituents..."
    print_info "This will sample ~10 companies per sector to calculate medians"
    echo ""

    uv run python valuation/normalized_multiples/python/fetch/fetch_sector_benchmarks.py

    if [[ $? -eq 0 ]]; then
        print_success "Sector benchmarks updated"
        ls -la valuation/normalized_multiples/data/sector_benchmarks/
    else
        print_error "Failed to fetch sector benchmarks"
    fi
}

# Options Hedging operations
show_options_hedging_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Options Hedging ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Fetch Underlying Data (Stock Price, Dividend, Volatility)"
        echo -e "${GREEN}2)${NC} Fetch Option Chain"
        echo -e "${GREEN}3)${NC} Calibrate Volatility Surfaces (SVI + SABR)"
        echo -e "${GREEN}4)${NC} Run Hedge Analysis"
        echo -e "${GREEN}5)${NC} Generate Visualizations"
        echo -e "${GREEN}6)${NC} Do Everything (Full Workflow)"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Pricing Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_underlying_data_options ;;
            2) fetch_option_chain ;;
            3) calibrate_vol_surface ;;
            4) run_options_hedge_analysis ;;
            5) generate_options_visualizations ;;
            6|"") run_options_full_workflow ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

# Volatility Arbitrage menu
show_volatility_arbitrage_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Volatility Arbitrage ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Fetch Historical OHLC Data"
        echo -e "${GREEN}2)${NC} Compute Realized Volatility"
        echo -e "${GREEN}3)${NC} Forecast Volatility (GARCH/EWMA/HAR)"
        echo -e "${GREEN}4)${NC} Detect Arbitrage Opportunities"
        echo -e "${GREEN}5)${NC} Generate Visualizations"
        echo -e "${GREEN}6)${NC} Do Everything (Full Workflow)"
        echo ""
        echo "DAILY PIPELINE:"
        echo -e "${GREEN}7)${NC} Collect Daily Snapshot"
        echo -e "${GREEN}8)${NC} Scan Signals (z-score watchlist)"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Pricing Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_historical_ohlc ;;
            2) compute_realized_vol ;;
            3) forecast_volatility ;;
            4) detect_volatility_arbitrage ;;
            5) generate_vol_arb_visualizations ;;
            6|"") run_vol_arb_full_workflow ;;
            7) collect_vol_arb_snapshot ;;
            8) scan_vol_arb_signals ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

# Fetch historical OHLC data
fetch_historical_ohlc() {
    print_header "Fetch Historical OHLC Data"

    read_ticker "Enter ticker symbol (default: TSLA):" "TSLA"

    echo -e "${YELLOW}Lookback days (default: 252 = 1 year):${NC} "
    read -r lookback
    lookback=${lookback:-252}

    print_info "Fetching OHLC data for $ticker (${lookback} days)..."
    uv run pricing/volatility_arbitrage/python/fetch/fetch_historical.py \
        --ticker "$ticker" \
        --lookback-days "$lookback"

    if [[ -f "pricing/volatility_arbitrage/data/${ticker}_ohlc.csv" ]]; then
        print_success "OHLC data saved to: pricing/volatility_arbitrage/data/${ticker}_ohlc.csv"
        print_success "Underlying data saved to: pricing/volatility_arbitrage/data/${ticker}_underlying.csv"
    else
        print_error "Failed to fetch OHLC data"
        return 1
    fi
}

# Compute realized volatility
compute_realized_vol() {
    print_header "Compute Realized Volatility"

    read_ticker "Enter ticker symbol (default: TSLA):" "TSLA"

    echo -e "${YELLOW}RV window (days, default: 21):${NC} "
    read -r window
    window=${window:-21}

    echo -e "${YELLOW}Estimator (yang_zhang, garman_klass, parkinson, close_to_close, rogers_satchell):${NC} "
    read -r estimator
    estimator=${estimator:-yang_zhang}

    print_info "Computing realized volatility for $ticker..."
    opam exec -- dune exec volatility_arbitrage -- \
        -ticker "$ticker" \
        -operation realized_vol \
        -estimator "$estimator" \
        -rv-window "$window"

    if [[ -f "pricing/volatility_arbitrage/output/${ticker}_realized_vol.csv" ]]; then
        print_success "Realized volatility saved to: pricing/volatility_arbitrage/output/${ticker}_realized_vol.csv"
    else
        print_error "Failed to compute realized volatility"
        return 1
    fi
}

# Forecast volatility
forecast_volatility() {
    print_header "Forecast Volatility"

    read_ticker "Enter ticker symbol (default: TSLA):" "TSLA"

    echo -e "${YELLOW}Forecast method (garch, ewma, har, historical):${NC} "
    read -r method
    method=${method:-garch}

    echo -e "${YELLOW}Forecast horizon (days, default: 30):${NC} "
    read -r horizon
    horizon=${horizon:-30}

    print_info "Forecasting volatility for $ticker using ${method}..."
    opam exec -- dune exec volatility_arbitrage -- \
        -ticker "$ticker" \
        -operation forecast_vol \
        -forecast-method "$method" \
        -forecast-horizon "$horizon"

    if [[ -f "pricing/volatility_arbitrage/output/${ticker}_vol_forecast.json" ]]; then
        print_success "Forecast saved to: pricing/volatility_arbitrage/output/${ticker}_vol_forecast.json"
    else
        print_error "Failed to generate forecast"
        return 1
    fi
}

# Detect arbitrage opportunities
detect_volatility_arbitrage() {
    print_header "Detect Arbitrage Opportunities"

    read_ticker "Enter ticker symbol (default: TSLA):" "TSLA"

    print_info "Scanning for arbitrage opportunities in $ticker..."
    print_warning "Requires vol surface from options_hedging model"

    opam exec -- dune exec volatility_arbitrage -- \
        -ticker "$ticker" \
        -operation detect_arbitrage \
        -data-dir pricing/options_hedging/data

    if [[ -f "pricing/volatility_arbitrage/output/${ticker}_arbitrage_signals.csv" ]]; then
        print_success "Arbitrage signals saved to: pricing/volatility_arbitrage/output/${ticker}_arbitrage_signals.csv"
    else
        print_warning "No arbitrage opportunities detected or vol surface not available"
    fi
}

# Generate visualizations
generate_vol_arb_visualizations() {
    print_header "Generate Visualizations"

    read_ticker "Enter ticker symbol (default: TSLA):" "TSLA"

    print_info "Generating IV vs RV plot for $ticker..."
    uv run pricing/volatility_arbitrage/python/viz/plot_iv_vs_rv.py --ticker "$ticker"

    if [[ -f "pricing/volatility_arbitrage/output/plots/${ticker}_rv_analysis.png" ]]; then
        print_success "Plot saved to: pricing/volatility_arbitrage/output/plots/${ticker}_rv_analysis.png"
    else
        print_error "Failed to generate plots"
        return 1
    fi
}

# Full workflow
run_vol_arb_full_workflow() {
    print_header "Volatility Arbitrage - Full Workflow"

    read_ticker "Enter ticker symbol (default: TSLA):" "TSLA"

    print_info "Step 1/5: Fetching historical OHLC data..."
    uv run pricing/volatility_arbitrage/python/fetch/fetch_historical.py --ticker "$ticker"

    print_info "Step 2/5: Computing realized volatility..."
    opam exec -- dune exec volatility_arbitrage -- \
        -ticker "$ticker" \
        -operation realized_vol

    print_info "Step 3/5: Forecasting volatility (GARCH)..."
    opam exec -- dune exec volatility_arbitrage -- \
        -ticker "$ticker" \
        -operation forecast_vol \
        -forecast-method garch

    print_info "Step 4/5: Detecting arbitrage opportunities..."
    opam exec -- dune exec volatility_arbitrage -- \
        -ticker "$ticker" \
        -operation detect_arbitrage \
        -data-dir pricing/options_hedging/data || true

    print_info "Step 5/5: Generating visualizations..."
    uv run pricing/volatility_arbitrage/python/viz/plot_iv_vs_rv.py --ticker "$ticker"

    print_success "Full workflow complete for $ticker"
    print_info "Results in: pricing/volatility_arbitrage/output/"
}

collect_vol_arb_snapshot() {
    print_header "Collect Daily Vol Arb Snapshot"

    pick_ticker_source "TSLA" || return

    print_info "Collecting volatility arbitrage snapshot..."

    uv run pricing/volatility_arbitrage/python/fetch/collect_snapshot.py \
        --tickers "$ticker_arg" \
        --data-dir pricing/volatility_arbitrage/data

    if [ $? -eq 0 ]; then
        print_success "Snapshot collected"
        print_info "Data: pricing/volatility_arbitrage/data/"
    else
        print_error "Snapshot collection failed"
    fi
}

scan_vol_arb_signals() {
    print_header "Scan Vol Arb Signals"

    echo -e "${GREEN}1)${NC} Overall ranking (all tickers)"
    echo -e "${GREEN}2)${NC} By price segment"
    echo ""
    echo -e "${YELLOW}Enter your choice (Enter=By segment):${NC} "
    read -r scan_choice

    local scan_args="--quiet"
    case $scan_choice in
        1) ;;
        2|"") scan_args="$scan_args --segments" ;;
        *) scan_args="$scan_args --segments" ;;
    esac

    print_info "Scanning vol arb histories..."

    uv run pricing/volatility_arbitrage/python/scan_signals.py \
        $scan_args \
        --output pricing/volatility_arbitrage/output/signal_scan.csv

    if [ $? -eq 0 ]; then
        print_success "Scan complete"
        print_info "Results: pricing/volatility_arbitrage/output/signal_scan.csv"
    else
        print_error "Scan failed"
    fi
}

# Variance Swaps - prompt for estimator and forecast method
prompt_variance_swaps_settings() {
    echo ""
    echo -e "${CYAN}RV Estimator:${NC}"
    echo "  1) Yang-Zhang (14x efficiency, uses OHLC) [default]"
    echo "  2) Garman-Klass (8x efficiency, uses OHLC)"
    echo "  3) Rogers-Satchell (drift-independent, uses OHLC)"
    echo "  4) Parkinson (5x efficiency, uses High-Low)"
    echo "  5) Close-to-Close (basic)"
    read -p "  Choice [1]: " est_choice
    case ${est_choice:-1} in
        1) VS_ESTIMATOR="yz" ;;
        2) VS_ESTIMATOR="gk" ;;
        3) VS_ESTIMATOR="rs" ;;
        4) VS_ESTIMATOR="parkinson" ;;
        5) VS_ESTIMATOR="cc" ;;
        *) VS_ESTIMATOR="yz" ;;
    esac

    echo ""
    echo -e "${CYAN}Forecast Model:${NC}"
    echo "  1) EWMA (λ=0.94, responsive to recent moves) [default]"
    echo "  2) GARCH(1,1) (mean-reverting conditional variance)"
    echo "  3) Historical RV (backward-looking, no model)"
    read -p "  Choice [1]: " fc_choice
    case ${fc_choice:-1} in
        1) VS_FORECAST="ewma" ;;
        2) VS_FORECAST="garch" ;;
        3) VS_FORECAST="historical" ;;
        *) VS_FORECAST="ewma" ;;
    esac
}

# Variance Swaps & VRP Trading menu
detect_data_provider() {
    # Detect which data providers are available
    local providers
    providers=$(uv run python -c "
import sys; sys.path.insert(0, '.')
from lib.python.data_fetcher import get_available_providers
p = get_available_providers()
print(', '.join(p))
" 2>/dev/null)
    if [[ -z "$providers" ]]; then
        providers="yfinance"
    fi
    echo "$providers"
}

show_variance_swaps_menu() {
    local providers
    providers=$(detect_data_provider)
    while true; do
        clear
        echo -e "${BLUE}═══ Variance Swaps & VRP Trading ═══${NC}\n"
        echo -e "${DIM}Daily snapshots accept liquid tickers from Liquidity module (option 8)${NC}"
        echo ""
        if echo "$providers" | grep -q "ibkr"; then
            echo -e "  ${GREEN}Data: IBKR${NC} (yfinance fallback for options chain)"
        else
            echo -e "  ${YELLOW}Data: yfinance${NC} (IBKR not detected)"
        fi
        echo ""
        echo -e "${GREEN}1)${NC} Fetch Market Data"
        echo -e "${GREEN}2)${NC} Price Variance Swap"
        echo -e "${GREEN}3)${NC} Compute VRP"
        echo -e "${GREEN}4)${NC} Generate Trading Signal"
        echo -e "${GREEN}5)${NC} Build Replication Portfolio"
        echo -e "${GREEN}6)${NC} Visualize Results"
        echo -e "${GREEN}7)${NC} Run Full Workflow"
        echo -e "${GREEN}8)${NC} Collect Daily IV Snapshot"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Pricing Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_variance_swap_data ; echo ""; read -rp "Press Enter to continue..." ;;
            2) price_variance_swap ; echo ""; read -rp "Press Enter to continue..." ;;
            3) compute_vrp ; echo ""; read -rp "Press Enter to continue..." ;;
            4) generate_vrp_signal ; echo ""; read -rp "Press Enter to continue..." ;;
            5) build_variance_replication ; echo ""; read -rp "Press Enter to continue..." ;;
            6) visualize_vrp_results ; echo ""; read -rp "Press Enter to continue..." ;;
            7|"") run_variance_swaps_full_workflow ; echo ""; read -rp "Press Enter to continue..." ;;
            8) collect_variance_snapshot ; echo ""; read -rp "Press Enter to continue..." ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_variance_swap_data() {
    print_header "Fetch Market Data for Variance Swaps"

    read -p "Enter ticker (e.g., SPY, QQQ): " ticker
    ticker=${ticker:-SPY}
    read -p "Enter lookback days (default: 365): " lookback
    lookback=${lookback:-365}

    print_info "Fetching data for $ticker (${lookback} days history)..."

    uv run pricing/variance_swaps/python/fetch_data.py \
        --ticker "$ticker" \
        --lookback "$lookback" \
        --output pricing/variance_swaps/data

    if [[ -f "pricing/variance_swaps/data/${ticker}_prices.csv" ]]; then
        print_success "Price data saved to: pricing/variance_swaps/data/${ticker}_prices.csv"
        print_success "Underlying data saved to: pricing/variance_swaps/data/${ticker}_underlying.json"
        print_success "Vol surface saved to: pricing/variance_swaps/data/${ticker}_vol_surface.json"
    else
        print_error "Failed to fetch data for $ticker"
    fi
}

price_variance_swap() {
    print_header "Price Variance Swap"

    read -p "Enter ticker (e.g., SPY): " ticker
    ticker=${ticker:-SPY}
    read -p "Enter horizon days (default: 30): " horizon
    horizon=${horizon:-30}
    read -p "Enter variance notional (default: 100000): " notional
    notional=${notional:-100000}
    read -p "Enter number of strikes (default: 20): " strikes
    strikes=${strikes:-20}

    print_info "Pricing variance swap for $ticker (${horizon}d, $strikes strikes)..."

    opam exec -- dune exec --root pricing/variance_swaps/ocaml variance_swaps -- \
        -ticker "$ticker" \
        -op price \
        -horizon "$horizon" \
        -notional "$notional" \
        -strikes "$strikes"

    if [[ -f "pricing/variance_swaps/output/${ticker}_variance_swap.csv" ]]; then
        print_success "Variance swap priced: pricing/variance_swaps/output/${ticker}_variance_swap.csv"

        # Display results
        if command -v column &> /dev/null; then
            echo ""
            print_info "Variance Swap Details:"
            column -t -s',' pricing/variance_swaps/output/${ticker}_variance_swap.csv
        fi
    else
        print_error "Failed to price variance swap for $ticker"
    fi
}

compute_vrp() {
    print_header "Compute Variance Risk Premium"

    read -p "Enter ticker (e.g., SPY): " ticker
    ticker=${ticker:-SPY}
    read -p "Enter horizon days (default: 30): " horizon
    horizon=${horizon:-30}

    prompt_variance_swaps_settings

    print_info "Computing VRP for $ticker (${horizon}d, est: $VS_ESTIMATOR, fc: $VS_FORECAST)..."

    opam exec -- dune exec --root pricing/variance_swaps/ocaml variance_swaps -- \
        -ticker "$ticker" \
        -op vrp \
        -horizon "$horizon" \
        -estimator "$VS_ESTIMATOR" \
        -forecast "$VS_FORECAST"

    if [[ -f "pricing/variance_swaps/output/${ticker}_vrp_${VS_ESTIMATOR}_${VS_FORECAST}.csv" ]]; then
        print_success "VRP computed: pricing/variance_swaps/output/${ticker}_vrp_${VS_ESTIMATOR}_${VS_FORECAST}.csv"

        # Display results
        if command -v column &> /dev/null; then
            echo ""
            print_info "VRP Observation:"
            column -t -s',' "pricing/variance_swaps/output/${ticker}_vrp_${VS_ESTIMATOR}_${VS_FORECAST}.csv"
        fi
    else
        print_error "Failed to compute VRP for $ticker"
    fi
}

generate_vrp_signal() {
    print_header "Generate VRP Trading Signal"

    read -p "Enter ticker (e.g., SPY): " ticker
    ticker=${ticker:-SPY}
    read -p "Enter horizon days (default: 30): " horizon
    horizon=${horizon:-30}

    prompt_variance_swaps_settings

    print_info "Generating VRP signal for $ticker (est: $VS_ESTIMATOR, fc: $VS_FORECAST)..."

    opam exec -- dune exec --root pricing/variance_swaps/ocaml variance_swaps -- \
        -ticker "$ticker" \
        -op signal \
        -horizon "$horizon" \
        -estimator "$VS_ESTIMATOR" \
        -forecast "$VS_FORECAST"

    if [[ -f "pricing/variance_swaps/output/${ticker}_signal_${VS_ESTIMATOR}_${VS_FORECAST}.csv" ]]; then
        print_success "Signal generated: pricing/variance_swaps/output/${ticker}_signal_${VS_ESTIMATOR}_${VS_FORECAST}.csv"

        # Display results
        if command -v column &> /dev/null; then
            echo ""
            print_info "Trading Signal:"
            column -t -s',' "pricing/variance_swaps/output/${ticker}_signal_${VS_ESTIMATOR}_${VS_FORECAST}.csv"
        fi
    else
        print_error "Failed to generate signal for $ticker"
    fi
}

build_variance_replication() {
    print_header "Build Variance Swap Replication Portfolio"

    read -p "Enter ticker (e.g., SPY): " ticker
    ticker=${ticker:-SPY}
    read -p "Enter variance notional (default: 100000): " notional
    notional=${notional:-100000}
    read -p "Enter number of strikes (default: 20): " strikes
    strikes=${strikes:-20}

    print_info "Building replication portfolio for $ticker..."

    opam exec -- dune exec --root pricing/variance_swaps/ocaml variance_swaps -- \
        -ticker "$ticker" \
        -op replicate \
        -notional "$notional" \
        -strikes "$strikes"

    if [[ -f "pricing/variance_swaps/output/${ticker}_replication.csv" ]]; then
        print_success "Replication portfolio: pricing/variance_swaps/output/${ticker}_replication.csv"
        print_success "Portfolio summary: pricing/variance_swaps/output/${ticker}_replication.csv.summary"

        # Display summary
        if [[ -f "pricing/variance_swaps/output/${ticker}_replication.csv.summary" ]]; then
            echo ""
            print_info "Portfolio Summary:"
            cat pricing/variance_swaps/output/${ticker}_replication.csv.summary
        fi
    else
        print_error "Failed to build replication portfolio for $ticker"
    fi
}

visualize_vrp_results() {
    print_header "Visualize VRP Results"

    read -p "Enter ticker (e.g., SPY): " ticker
    ticker=${ticker:-SPY}

    prompt_variance_swaps_settings

    print_info "Generating visualizations for $ticker..."

    # Check which files exist
    has_vrp=false
    has_signal=false

    if [[ -f "pricing/variance_swaps/output/${ticker}_vrp_${VS_ESTIMATOR}_${VS_FORECAST}.csv" ]]; then
        has_vrp=true
    fi

    if [[ -f "pricing/variance_swaps/output/${ticker}_signal_${VS_ESTIMATOR}_${VS_FORECAST}.csv" ]]; then
        has_signal=true
    fi

    if [[ "$has_vrp" == "false" && "$has_signal" == "false" ]]; then
        print_error "No VRP or signal data found for $ticker (${VS_ESTIMATOR}_${VS_FORECAST})"
        print_info "Run 'Compute VRP' or 'Generate Signal' first"
        return 1
    fi

    # Build viz command
    cmd="uv run pricing/variance_swaps/python/viz_vrp.py --output-dir pricing/variance_swaps/output"
    cmd="$cmd --estimator $VS_ESTIMATOR --forecast $VS_FORECAST"

    if [[ "$has_vrp" == "true" ]]; then
        cmd="$cmd --vrp pricing/variance_swaps/output/${ticker}_vrp_${VS_ESTIMATOR}_${VS_FORECAST}.csv"
    fi

    if [[ "$has_signal" == "true" ]]; then
        cmd="$cmd --signals pricing/variance_swaps/output/${ticker}_signal_${VS_ESTIMATOR}_${VS_FORECAST}.csv"
    fi

    eval "$cmd"

    print_success "Visualizations saved to: pricing/variance_swaps/output/"
}

run_variance_swaps_full_workflow() {
    print_header "Variance Swaps - Full Workflow"

    read -p "Enter ticker (default: SPY): " ticker
    ticker=${ticker:-SPY}
    read -p "Enter horizon days (default: 30): " horizon
    horizon=${horizon:-30}

    prompt_variance_swaps_settings

    print_info "Running full variance swaps workflow for $ticker (est: $VS_ESTIMATOR, fc: $VS_FORECAST)..."

    # Step 1: Fetch data
    print_info "Step 1/7: Fetching market data..."
    uv run pricing/variance_swaps/python/fetch_data.py \
        --ticker "$ticker" \
        --lookback 365 \
        --output pricing/variance_swaps/data

    # Step 2: Price variance swap
    print_info "Step 2/7: Pricing variance swap..."
    opam exec -- dune exec --root pricing/variance_swaps/ocaml variance_swaps -- \
        -ticker "$ticker" \
        -op price \
        -horizon "$horizon"

    # Step 3: Compute VRP (single point)
    print_info "Step 3/7: Computing VRP..."
    opam exec -- dune exec --root pricing/variance_swaps/ocaml variance_swaps -- \
        -ticker "$ticker" \
        -op vrp \
        -horizon "$horizon" \
        -estimator "$VS_ESTIMATOR" \
        -forecast "$VS_FORECAST"

    # Step 4: Generate signal
    print_info "Step 4/7: Generating trading signal..."
    opam exec -- dune exec --root pricing/variance_swaps/ocaml variance_swaps -- \
        -ticker "$ticker" \
        -op signal \
        -horizon "$horizon" \
        -estimator "$VS_ESTIMATOR" \
        -forecast "$VS_FORECAST"

    # Step 5: Build replication portfolio
    print_info "Step 5/7: Building replication portfolio..."
    opam exec -- dune exec --root pricing/variance_swaps/ocaml variance_swaps -- \
        -ticker "$ticker" \
        -op replicate \
        -horizon "$horizon"

    # Step 6: Backtest (generates VRP time series for plotting)
    print_info "Step 6/7: Backtesting VRP strategy..."
    opam exec -- dune exec --root pricing/variance_swaps/ocaml variance_swaps -- \
        -ticker "$ticker" \
        -op backtest \
        -horizon "$horizon" \
        -estimator "$VS_ESTIMATOR" \
        -forecast "$VS_FORECAST"

    # Step 7: Visualize
    print_info "Step 7/7: Generating visualizations..."
    uv run pricing/variance_swaps/python/viz_vrp.py \
        --vrp "pricing/variance_swaps/output/${ticker}_vrp_${VS_ESTIMATOR}_${VS_FORECAST}.csv" \
        --signals "pricing/variance_swaps/output/${ticker}_signal_${VS_ESTIMATOR}_${VS_FORECAST}.csv" \
        --output-dir pricing/variance_swaps/output \
        --estimator "$VS_ESTIMATOR" \
        --forecast "$VS_FORECAST"

    print_success "Full workflow complete for $ticker"
    print_info "Results in: pricing/variance_swaps/output/"
}

collect_variance_snapshot() {
    print_header "Collect Daily IV Snapshot"

    pick_ticker_source "SPY" || return

    print_info "Collecting IV snapshot..."

    uv run pricing/variance_swaps/python/collect_snapshot.py \
        --tickers "$ticker_arg" \
        --data-dir pricing/variance_swaps/data

    if [ $? -eq 0 ]; then
        print_success "Snapshot collected"
        print_info "Data: pricing/variance_swaps/data/"
    else
        print_error "Snapshot collection failed"
    fi

    if [[ "$ticker_arg" == "all_liquid" || "$ticker_arg" == *.txt ]]; then
        echo ""
        echo -e "${YELLOW}Jump to:${NC}  ${GREEN}s)${NC} Skew Trading  ${GREEN}e)${NC} Pre-Earnings  ${GREEN}l)${NC} Liquidity  ${GREEN}Enter)${NC} Stay"
        read -r jump
        case $jump in
            s) show_skew_trading_menu ;;
            e) show_pre_earnings_straddle_menu ;;
            l) show_liquidity_menu ;;
        esac
    fi
}

# Fetch underlying data for options
fetch_underlying_data_options() {
    print_header "Fetch Underlying Data"

    read_ticker "Enter ticker symbol (default: BMNR):" "BMNR"

    print_info "Fetching underlying data for $ticker..."
    uv run pricing/options_hedging/python/fetch/fetch_underlying.py --ticker "$ticker"

    if [[ -f "pricing/options_hedging/data/${ticker}_underlying.csv" ]]; then
        print_success "Underlying data saved to: pricing/options_hedging/data/${ticker}_underlying.csv"
    else
        print_error "Failed to fetch underlying data"
    fi
}

# Fetch option chain
fetch_option_chain() {
    print_header "Fetch Option Chain"

    read_ticker "Enter ticker symbol (default: BMNR):" "BMNR"

    print_info "Fetching option chain for $ticker..."
    uv run pricing/options_hedging/python/fetch/fetch_options.py --ticker "$ticker"

    if [[ -f "pricing/options_hedging/data/${ticker}_options.csv" ]]; then
        print_success "Option chain saved to: pricing/options_hedging/data/${ticker}_options.csv"
    else
        print_error "Failed to fetch option chain"
    fi
}

# Calibrate volatility surface
calibrate_vol_surface() {
    print_header "Calibrate Volatility Surface"

    read_ticker "Enter ticker symbol (default: BMNR):" "BMNR"

    print_info "Calibrating SVI and SABR volatility surfaces for $ticker..."
    uv run pricing/options_hedging/python/calibrate_vol_surface.py --ticker "$ticker" --model both

    if [[ -f "pricing/options_hedging/data/${ticker}_vol_surface_svi.json" ]]; then
        print_success "SVI surface saved to: pricing/options_hedging/data/${ticker}_vol_surface_svi.json"
    fi
    if [[ -f "pricing/options_hedging/data/${ticker}_vol_surface_sabr.json" ]]; then
        print_success "SABR surface saved to: pricing/options_hedging/data/${ticker}_vol_surface_sabr.json"
    fi
}

# Run hedge analysis
run_options_hedge_analysis() {
    print_header "Run Hedge Analysis"

    read_ticker "Enter ticker symbol (default: BMNR):" "BMNR"

    echo -e "${YELLOW}Enter position size (shares, default: 100):${NC} "
    read -r position
    position=${position:-100}

    echo -e "${YELLOW}Enter days to expiry (default: 90):${NC} "
    read -r expiry
    expiry=${expiry:-90}

    print_info "Running hedge analysis for $ticker (position: $position shares, expiry: $expiry days)..."
    opam exec -- dune exec options_hedging -- \
        -ticker "$ticker" \
        -position "$position" \
        -expiry "$expiry"

    if [[ -f "pricing/options_hedging/output/pareto_frontier.csv" ]]; then
        print_success "Results saved to: pricing/options_hedging/output/"
        echo ""
        print_info "Recommended strategy details:"
        if [[ -f "pricing/options_hedging/output/recommended_strategy.csv" ]]; then
            head -12 pricing/options_hedging/output/recommended_strategy.csv
        fi
    else
        print_error "Failed to generate hedge analysis"
    fi
}

# Generate visualizations
generate_options_visualizations() {
    print_header "Generate Visualizations"

    read_ticker "Enter ticker symbol (default: BMNR):" "BMNR"

    print_info "Generating visualizations..."

    uv run pricing/options_hedging/python/viz/plot_payoffs.py --ticker "$ticker"
    uv run pricing/options_hedging/python/viz/plot_frontier.py
    uv run pricing/options_hedging/python/viz/plot_greeks.py
    uv run pricing/options_hedging/python/viz/plot_vol_surface.py --ticker "$ticker"

    if [[ -d "pricing/options_hedging/output/plots" ]]; then
        print_success "Plots saved to: pricing/options_hedging/output/plots/"
        ls -lh pricing/options_hedging/output/plots/*.png 2>/dev/null || true
    else
        print_error "Failed to generate visualizations"
    fi
}

# Full workflow
run_options_full_workflow() {
    print_header "Options Hedging - Full Workflow"

    read_ticker "Enter ticker symbol (default: BMNR):" "BMNR"

    echo -e "${YELLOW}Enter position size (shares, default: 100):${NC} "
    read -r position
    position=${position:-100}

    echo -e "${YELLOW}Enter days to expiry (default: 90):${NC} "
    read -r expiry
    expiry=${expiry:-90}

    print_info "Running full workflow for $ticker..."

    # Step 1: Fetch underlying
    print_info "[1/5] Fetching underlying data..."
    uv run pricing/options_hedging/python/fetch/fetch_underlying.py --ticker "$ticker"

    # Step 2: Fetch option chain
    print_info "[2/5] Fetching option chain..."
    uv run pricing/options_hedging/python/fetch/fetch_options.py --ticker "$ticker"

    # Step 3: Calibrate vol surfaces (both SVI and SABR)
    print_info "[3/5] Calibrating volatility surfaces (SVI + SABR)..."
    uv run pricing/options_hedging/python/calibrate_vol_surface.py --ticker "$ticker" --model both

    # Step 4: Run hedge analysis (uses SVI by default)
    print_info "[4/5] Running hedge analysis..."
    opam exec -- dune exec options_hedging -- \
        -ticker "$ticker" \
        -position "$position" \
        -expiry "$expiry"

    # Step 5: Generate visualizations (both SVI and SABR surfaces)
    print_info "[5/5] Generating visualizations..."
    uv run pricing/options_hedging/python/viz/plot_payoffs.py --ticker "$ticker"
    uv run pricing/options_hedging/python/viz/plot_frontier.py
    uv run pricing/options_hedging/python/viz/plot_greeks.py
    uv run pricing/options_hedging/python/viz/plot_vol_surface.py --ticker "$ticker"

    print_success "Full workflow complete!"
    echo ""
    print_info "Results:"
    print_info "  - Data: pricing/options_hedging/data/"
    print_info "  - Output: pricing/options_hedging/output/"
    print_info "  - Plots: pricing/options_hedging/output/plots/"
}

# Run DCF sensitivity analyses (parallel CSV generation)
run_dcf_sensitivity_analyses() {
    print_header "Run DCF Sensitivity Analyses"

    local log_dir="valuation/dcf_deterministic/log"
    local output_dir="valuation/dcf_deterministic/output"

    if [[ ! -d "$log_dir" ]] || [[ -z "$(ls -A $log_dir/*.log 2>/dev/null)" ]]; then
        print_error "No valuation results found. Run deterministic DCF valuation first."
        return 1
    fi

    # Extract unique tickers from log files
    local tickers=()
    for log_file in "$log_dir"/dcf_*.log; do
        if [[ -f "$log_file" ]]; then
            local ticker=$(basename "$log_file" | awk -F_ '{print $2}')
            tickers+=("$ticker")
        fi
    done

    # Remove duplicates
    local unique_tickers=($(printf '%s\n' "${tickers[@]}" | sort -u))

    # Build executable first to avoid Dune warnings in parallel execution
    print_info "Building sensitivity analysis executable..."
    if ! opam exec -- dune build valuation/dcf_deterministic/ocaml/bin/sensitivity_main.exe > /dev/null 2>&1; then
        print_error "Failed to build sensitivity analysis executable"
        return 1
    fi
    local sensitivity_exe="_build/default/valuation/dcf_deterministic/ocaml/bin/sensitivity_main.exe"

    echo "Running sensitivity analysis for ${#unique_tickers[@]} ticker(s) in parallel..."
    echo "(This performs 43 valuations per ticker: 17 growth rates + 13 discount rates + 13 terminal growth rates)"
    echo ""

    # Run sensitivity analyses in parallel (up to 8 at a time)
    local max_parallel=8
    local running=0
    local pids=()
    local ticker_map=()

    for ticker in "${unique_tickers[@]}"; do
        # Start background process
        "$sensitivity_exe" \
            -ticker "$ticker" \
            -output-dir "$output_dir" \
            -data-dir "valuation/dcf_deterministic/data" \
            -python "valuation/dcf_deterministic/python/fetch_financials.py" \
            > /dev/null 2>&1 &

        local pid=$!
        pids+=($pid)
        ticker_map[$pid]=$ticker
        running=$((running + 1))

        # Wait if we've hit the parallel limit
        if [[ $running -ge $max_parallel ]]; then
            wait -n
            running=$((running - 1))
        fi
    done

    # Wait for all remaining processes
    wait

    # Check results
    local csv_count=$(ls -1 "$output_dir"/sensitivity/data/*.csv 2>/dev/null | wc -l)
    local expected_count=$((${#unique_tickers[@]} * 3))

    if [[ $csv_count -eq $expected_count ]]; then
        print_success "All $csv_count sensitivity CSV file(s) generated"
        echo ""
        echo -e "${BLUE}CSV files saved to:${NC} $output_dir/sensitivity/data/"
    else
        print_warning "$csv_count/$expected_count CSV file(s) generated (some may have failed)"
    fi
}

# Generate DCF valuation plots (waterfall, comparison, cost of capital)
generate_dcf_valuation_plots() {
    print_header "Generate DCF Valuation Plots"

    local log_dir="valuation/dcf_deterministic/log"
    local output_dir="valuation/dcf_deterministic/output"
    local viz_dir="$output_dir/valuation"

    if [[ ! -d "$log_dir" ]] || [[ -z "$(ls -A $log_dir/*.log 2>/dev/null)" ]]; then
        print_error "No valuation results found. Run deterministic DCF valuation first."
        return 1
    fi

    # Create output directory
    mkdir -p "$output_dir"

    print_info "Generating valuation plots (light and dark modes)..."
    echo ""

    uv run valuation/dcf_deterministic/python/viz/plot_results.py \
        --log-dir "$log_dir" \
        --viz-dir "$output_dir" \
        --valuation-only

    if [[ $? -eq 0 ]]; then
        local png_count=$(ls -1 "$viz_dir"/*.png 2>/dev/null | wc -l)
        print_success "Valuation plots complete. $png_count plot(s) generated"
        echo ""
        echo -e "${BLUE}Plots saved to:${NC} $viz_dir/"
        ls -1 "$viz_dir"/*.png 2>/dev/null | while read -r file; do
            echo "  - $(basename "$file")"
        done
    else
        print_error "Valuation plot generation failed"
    fi
}

# Generate DCF sensitivity plots (4-panel sensitivity analysis)
generate_dcf_sensitivity_plots() {
    print_header "Generate DCF Sensitivity Plots"

    local log_dir="valuation/dcf_deterministic/log"
    local output_dir="valuation/dcf_deterministic/output"
    local csv_dir="$output_dir/sensitivity/data"
    local viz_dir="$output_dir/sensitivity/plots"

    if [[ ! -d "$csv_dir" ]] || [[ -z "$(ls -A $csv_dir/*.csv 2>/dev/null)" ]]; then
        print_error "No sensitivity CSV files found. Run sensitivity analyses first."
        return 1
    fi

    # Create output directory
    mkdir -p "$output_dir"

    print_info "Generating sensitivity plots (light and dark modes, 4-panel analysis for each ticker)..."
    echo ""

    uv run valuation/dcf_deterministic/python/viz/plot_results.py \
        --log-dir "$log_dir" \
        --viz-dir "$output_dir" \
        --csv-dir "$csv_dir" \
        --sensitivity-only

    if [[ $? -eq 0 ]]; then
        local png_count=$(ls -1 "$viz_dir"/*.png 2>/dev/null | wc -l)
        print_success "Sensitivity plots complete. $png_count plot(s) generated"
        echo ""
        echo -e "${BLUE}Plots saved to:${NC} $viz_dir/"
        ls -1 "$viz_dir"/*.png 2>/dev/null | while read -r file; do
            echo "  - $(basename "$file")"
        done
    else
        print_error "Sensitivity plot generation failed"
    fi
}

# Run all DCF deterministic steps
run_dcf_deterministic_all() {
    print_header "Running Complete DCF Deterministic Workflow"
    echo ""
    echo -e "${YELLOW}This will run all steps in sequence:${NC}"
    echo "  1. Run Valuation"
    echo "  2. Run Sensitivity Analyses"
    echo "  3. Generate Valuation Plots"
    echo "  4. Generate Sensitivity Plots"
    echo ""
    echo -e "${YELLOW}Do you want to continue? (y/n):${NC} "
    read -r confirm

    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        print_info "Operation cancelled"
        return 0
    fi

    echo ""

    # Step 1: Run Valuation
    print_info "Step 1/4: Running DCF valuation..."
    if ! run_dcf_valuation; then
        print_error "Valuation failed. Stopping workflow."
        return 1
    fi
    echo ""

    # Step 2: Run Sensitivity Analyses
    print_info "Step 2/4: Running sensitivity analyses..."
    if ! run_dcf_sensitivity_analyses; then
        print_error "Sensitivity analyses failed. Stopping workflow."
        return 1
    fi
    echo ""

    # Step 3: Generate Valuation Plots
    print_info "Step 3/4: Generating valuation plots..."
    if ! generate_dcf_valuation_plots; then
        print_error "Valuation plot generation failed. Stopping workflow."
        return 1
    fi
    echo ""

    # Step 4: Generate Sensitivity Plots
    print_info "Step 4/4: Generating sensitivity plots..."
    if ! generate_dcf_sensitivity_plots; then
        print_error "Sensitivity plot generation failed. Stopping workflow."
        return 1
    fi
    echo ""

    print_success "Complete DCF deterministic workflow finished successfully!"
    echo ""
}

# DCF Deterministic operations
show_dcf_deterministic_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ DCF Deterministic Valuation ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Run Valuation"
        echo -e "${GREEN}2)${NC} View Valuation Results"
        echo -e "${GREEN}3)${NC} Run Sensitivity Analyses"
        echo -e "${GREEN}4)${NC} Generate Valuation Plots"
        echo -e "${GREEN}5)${NC} Generate Sensitivity Plots"
        echo -e "${GREEN}6)${NC} Do Everything"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Valuation"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) run_dcf_valuation ;;
            2) view_dcf_results ;;
            3) run_dcf_sensitivity_analyses ;;
            4) generate_dcf_valuation_plots ;;
            5) generate_dcf_sensitivity_plots ;;
            6|"") run_dcf_deterministic_all ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

# Run all DCF probabilistic steps
run_dcf_probabilistic_all() {
    print_header "Running Complete DCF Probabilistic Workflow"
    echo ""
    echo -e "${YELLOW}This will run all steps in sequence:${NC}"
    echo "  1. Run Valuation"
    echo "  2. Generate Visualizations (KDE plots)"
    echo "  3. Generate Portfolio Efficient Frontier"
    echo ""
    echo -e "${YELLOW}Do you want to continue? (y/n):${NC} "
    read -r confirm

    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        print_info "Operation cancelled"
        return 0
    fi

    echo ""

    # Step 1: Run Valuation
    print_info "Step 1/3: Running DCF probabilistic valuation..."
    if ! run_dcf_probabilistic; then
        print_error "Valuation failed. Stopping workflow."
        return 1
    fi
    echo ""

    # Step 2: Generate Visualizations
    print_info "Step 2/3: Generating visualizations (KDE plots)..."
    if ! generate_dcf_visualizations; then
        print_error "Visualization generation failed. Stopping workflow."
        return 1
    fi
    echo ""

    # Step 3: Generate Portfolio Efficient Frontier
    print_info "Step 3/3: Generating portfolio efficient frontier..."
    if ! generate_portfolio_frontier; then
        print_error "Portfolio frontier generation failed. Stopping workflow."
        return 1
    fi
    echo ""

    print_success "Complete DCF probabilistic workflow finished successfully!"
    echo ""
}

# DCF Probabilistic operations
show_dcf_probabilistic_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ DCF Probabilistic Valuation (Monte Carlo) ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Run Valuation"
        echo -e "${GREEN}2)${NC} View Results"
        echo -e "${GREEN}3)${NC} Generate Visualizations (KDE plots)"
        echo -e "${GREEN}4)${NC} Generate Portfolio Efficient Frontier"
        echo -e "${GREEN}5)${NC} Do Everything"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Valuation"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) run_dcf_probabilistic ;;
            2) view_dcf_probabilistic_results ;;
            3) generate_dcf_visualizations ;;
            4) generate_portfolio_frontier ;;
            5|"") run_dcf_probabilistic_all ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

# Crypto Treasury Valuation operations
show_crypto_treasury_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Crypto Treasury Valuation ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Run Valuation (BTC + ETH holdings)"
        echo -e "${GREEN}2)${NC} Generate Visualization"
        echo -e "${GREEN}3)${NC} Run Full Workflow"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Valuation"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) run_crypto_treasury_valuation ;;
            2) plot_crypto_treasury ;;
            3|"") run_crypto_treasury_full_workflow ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

run_crypto_treasury_valuation() {
    print_header "Crypto Treasury Valuation"

    .venv/bin/python3 valuation/crypto_treasury/python/crypto_valuation.py

    if [[ -f "valuation/crypto_treasury/output/crypto_valuation.json" ]]; then
        print_success "Results saved to: valuation/crypto_treasury/output/crypto_valuation.json"
    fi
}

plot_crypto_treasury() {
    print_header "Generate Crypto Treasury Visualization"

    if [[ ! -f "valuation/crypto_treasury/output/crypto_valuation.json" ]]; then
        print_error "No results found. Run valuation first."
        return 1
    fi

    .venv/bin/python3 valuation/crypto_treasury/python/plot_crypto.py

    if [[ -f "valuation/crypto_treasury/output/crypto_treasury_valuation.png" ]]; then
        print_success "Plot saved to: valuation/crypto_treasury/output/crypto_treasury_valuation.png"
    fi
}

run_crypto_treasury_full_workflow() {
    print_header "Crypto Treasury - Full Workflow"

    print_info "Step 1/2: Running valuation..."
    .venv/bin/python3 valuation/crypto_treasury/python/crypto_valuation.py

    if [[ ! -f "valuation/crypto_treasury/output/crypto_valuation.json" ]]; then
        print_error "Valuation failed"
        return 1
    fi
    print_success "Valuation complete"

    print_info "Step 2/2: Generating visualization..."
    .venv/bin/python3 valuation/crypto_treasury/python/plot_crypto.py

    if [[ -f "valuation/crypto_treasury/output/crypto_treasury_valuation.png" ]]; then
        print_success "Plot saved to: valuation/crypto_treasury/output/crypto_treasury_valuation.png"
    fi

    print_success "Full workflow complete!"
}

# DCF REIT Valuation operations
show_dcf_reit_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ DCF REIT Valuation ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Fetch REIT Data"
        echo -e "${GREEN}2)${NC} Run Valuation (OCaml)"
        echo -e "${GREEN}3)${NC} Generate Visualization"
        echo -e "${GREEN}4)${NC} Run Full Workflow"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Valuation"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_reit_data ;;
            2) run_dcf_reit_valuation ;;
            3) plot_dcf_reit ;;
            4|"") run_dcf_reit_full_workflow ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_reit_data() {
    print_header "Fetch REIT Data"

    local default_tickers="PLD O EQIX STWD"
    echo -e "${YELLOW}Enter REIT tickers (space-separated, default: ${default_tickers}):${NC}"
    read -r tickers

    if [[ -z "$tickers" ]]; then
        tickers="$default_tickers"
        print_info "Using default tickers: $tickers"
    fi

    tickers=$(echo "$tickers" | tr ',' ' ' | tr '[:lower:]' '[:upper:]')
    uv run python valuation/dcf_reit/python/fetch/fetch_reit_data.py \
        -t $tickers \
        -o valuation/dcf_reit/data

    print_success "REIT data fetched"
}

run_dcf_reit_valuation() {
    print_header "Run REIT Valuation (OCaml)"

    local json_count=$(ls valuation/dcf_reit/data/*.json 2>/dev/null | wc -l)
    if [[ "$json_count" -eq 0 ]]; then
        print_error "No REIT data found. Run 'Fetch REIT Data' first."
        return 1
    fi

    eval $(opam env) && dune exec valuation/dcf_reit/ocaml/bin/main.exe -- \
        -d valuation/dcf_reit/data \
        -o valuation/dcf_reit/output/data

    print_success "Valuation complete"
}

plot_dcf_reit() {
    print_header "Generate REIT Visualization"

    local results_dir="valuation/dcf_reit/output/data"
    if [[ ! -d "$results_dir" ]] || [[ -z "$(ls ${results_dir}/*_valuation.json 2>/dev/null)" ]]; then
        print_error "No results found. Run valuation first."
        return 1
    fi

    for f in ${results_dir}/*_valuation.json; do
        uv run python valuation/dcf_reit/python/viz/plot_reit_valuation.py \
            -i "$f" \
            -o valuation/dcf_reit/output/plots
    done

    print_success "Plots generated in valuation/dcf_reit/output/plots/"
}

run_dcf_reit_full_workflow() {
    print_header "DCF REIT - Full Workflow"

    local default_tickers="PLD O EQIX STWD"
    echo -e "${YELLOW}Enter REIT tickers (space-separated, default: ${default_tickers}):${NC}"
    read -r tickers

    if [[ -z "$tickers" ]]; then
        tickers="$default_tickers"
        print_info "Using default tickers: $tickers"
    fi

    tickers=$(echo "$tickers" | tr ',' ' ' | tr '[:lower:]' '[:upper:]')

    # Step 1: Fetch data
    print_info "Step 1/3: Fetching REIT data..."
    uv run python valuation/dcf_reit/python/fetch/fetch_reit_data.py \
        -t $tickers \
        -o valuation/dcf_reit/data
    print_success "REIT data fetched"

    # Step 2: Run OCaml valuation
    print_info "Step 2/3: Running valuation..."
    eval $(opam env) && dune exec valuation/dcf_reit/ocaml/bin/main.exe -- \
        -d valuation/dcf_reit/data \
        -o valuation/dcf_reit/output/data
    print_success "Valuation complete"

    # Step 3: Generate visualization
    print_info "Step 3/3: Generating visualization..."
    for f in valuation/dcf_reit/output/data/*_valuation.json; do
        uv run python valuation/dcf_reit/python/viz/plot_reit_valuation.py \
            -i "$f" \
            -o valuation/dcf_reit/output/plots
    done

    print_success "Full workflow complete!"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Dividend Income Analysis
# ═══════════════════════════════════════════════════════════════════════════════

show_dividend_income_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Dividend Income Analysis ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Fetch Dividend Data"
        echo -e "${GREEN}2)${NC} Run DDM Valuation (OCaml)"
        echo -e "${GREEN}3)${NC} Compare Multiple Stocks"
        echo -e "${GREEN}4)${NC} Run Full Workflow"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Valuation"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_dividend_data ;;
            2) run_dividend_income_analysis ;;
            3) run_dividend_income_compare ;;
            4|"") run_dividend_income_full_workflow ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_dividend_data() {
    print_header "Fetch Dividend Data"

    echo -e "${YELLOW}Enter ticker symbol (default: JNJ):${NC}"
    read -r ticker
    ticker="${ticker:-JNJ}"

    ticker=$(echo "$ticker" | tr '[:lower:]' '[:upper:]')
    uv run python valuation/dividend_income/python/fetch/fetch_dividend_data.py \
        --ticker "$ticker" \
        --output valuation/dividend_income/data

    if [[ -f "valuation/dividend_income/data/dividend_data_${ticker}.json" ]]; then
        print_success "Data saved to: valuation/dividend_income/data/dividend_data_${ticker}.json"
    else
        print_error "Failed to fetch dividend data"
    fi
}

run_dividend_income_analysis() {
    print_header "Run Dividend Income Analysis (OCaml)"

    echo -e "${YELLOW}Enter ticker symbol:${NC}"
    read -r ticker

    if [[ -z "$ticker" ]]; then
        print_error "Ticker is required"
        return 1
    fi

    ticker=$(echo "$ticker" | tr '[:lower:]' '[:upper:]')
    if [[ ! -f "valuation/dividend_income/data/dividend_data_${ticker}.json" ]]; then
        print_error "No data found for $ticker. Run 'Fetch Dividend Data' first."
        return 1
    fi

    dune exec valuation/dividend_income/ocaml/bin/main.exe -- \
        --ticker "$ticker" \
        --data valuation/dividend_income/data \
        --output valuation/dividend_income/output

    if [[ -f "valuation/dividend_income/output/dividend_result_${ticker}.json" ]]; then
        print_success "Results saved to: valuation/dividend_income/output/dividend_result_${ticker}.json"
    else
        print_error "Analysis failed"
    fi
}

run_dividend_income_compare() {
    print_header "Compare Dividend Stocks"

    echo -e "${YELLOW}Enter tickers (comma-separated, default: JNJ,KO,PEP,PG,VZ,MO):${NC}"
    read -r tickers
    tickers="${tickers:-JNJ,KO,PEP,PG,VZ,MO}"

    tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]')
    dune exec valuation/dividend_income/ocaml/bin/main.exe -- \
        --tickers "$tickers" \
        --compare \
        --data valuation/dividend_income/data \
        --output valuation/dividend_income/output

    if [[ -f "valuation/dividend_income/output/dividend_comparison.json" ]]; then
        print_success "Comparison saved to: valuation/dividend_income/output/dividend_comparison.json"
    fi
}

run_dividend_income_full_workflow() {
    print_header "Dividend Income - Full Workflow"

    echo -e "${YELLOW}Enter tickers (comma-separated, default: JNJ,KO,PEP,PG,VZ,MO):${NC}"
    read -r tickers
    tickers="${tickers:-JNJ,KO,PEP,PG,VZ,MO}"

    tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]')

    # Step 1: Fetch data for each ticker
    IFS=',' read -ra ticker_array <<< "$tickers"
    print_info "Step 1/3: Fetching dividend data..."
    for t in "${ticker_array[@]}"; do
        t=$(echo "$t" | tr -d ' ')
        print_info "  Fetching $t..."
        uv run python valuation/dividend_income/python/fetch/fetch_dividend_data.py \
            --ticker "$t" \
            --output valuation/dividend_income/data
    done
    print_success "Data fetched"

    # Step 2: Run individual analyses + comparison
    print_info "Step 2/3: Running analysis..."
    for t in "${ticker_array[@]}"; do
        t=$(echo "$t" | tr -d ' ')
        dune exec valuation/dividend_income/ocaml/bin/main.exe -- \
            --ticker "$t" \
            --data valuation/dividend_income/data \
            --output valuation/dividend_income/output
    done

    if [[ ${#ticker_array[@]} -gt 1 ]]; then
        print_info "Running comparison..."
        dune exec valuation/dividend_income/ocaml/bin/main.exe -- \
            --tickers "$tickers" \
            --compare \
            --data valuation/dividend_income/data \
            --output valuation/dividend_income/output

        if [[ -f "valuation/dividend_income/output/dividend_comparison.json" ]]; then
            print_success "Comparison saved to: valuation/dividend_income/output/dividend_comparison.json"
        fi
    fi

    # Step 3: Generate plots
    print_info "Step 3/3: Generating plots..."
    for t in "${ticker_array[@]}"; do
        t=$(echo "$t" | tr -d ' ')
        local result_file="valuation/dividend_income/output/dividend_result_${t}.json"
        if [[ -f "$result_file" ]]; then
            uv run python valuation/dividend_income/python/viz/plot_dividend.py --input "$result_file"
        fi
    done

    print_success "Full workflow complete!"
}

# ═══════════════════════════════════════════════════════════════════════════════
# ETF Analysis
# ═══════════════════════════════════════════════════════════════════════════════

show_etf_analysis_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ ETF Analysis ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Fetch ETF Data"
        echo -e "${GREEN}2)${NC} Run ETF Analysis (OCaml)"
        echo -e "${GREEN}3)${NC} Compare Multiple ETFs"
        echo -e "${GREEN}4)${NC} Run Full Workflow"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Valuation"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_etf_data ;;
            2) run_etf_analysis ;;
            3) run_etf_compare ;;
            4|"") run_etf_full_workflow ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_etf_data() {
    print_header "Fetch ETF Data"

    local ticker=""
    while [[ -z "$ticker" ]]; do
        echo -e "${YELLOW}Enter ETF ticker symbol (default: SPY):${NC}"
        read -r ticker
        ticker="${ticker:-SPY}"
    done

    ticker=$(echo "$ticker" | tr '[:lower:]' '[:upper:]')

    echo -e "${YELLOW}Enter benchmark ticker (optional, press Enter to auto-detect):${NC}"
    read -r benchmark

    if [[ -z "$benchmark" ]]; then
        uv run python valuation/etf_analysis/python/fetch/fetch_etf_data.py "$ticker"
    else
        benchmark=$(echo "$benchmark" | tr '[:lower:]' '[:upper:]')
        uv run python valuation/etf_analysis/python/fetch/fetch_etf_data.py "$ticker" "$benchmark"
    fi

    if [[ -f "valuation/etf_analysis/data/etf_data_${ticker}.json" ]]; then
        print_success "Data saved to: valuation/etf_analysis/data/etf_data_${ticker}.json"
    else
        print_error "Failed to fetch ETF data"
    fi
}

run_etf_analysis() {
    print_header "Run ETF Analysis (OCaml)"

    local ticker=""
    local data_file=""
    while true; do
        echo -e "${YELLOW}Enter ETF ticker symbol:${NC}"
        read -r ticker
        if [[ -z "$ticker" ]]; then
            print_warning "Ticker is required. Please try again."
            continue
        fi
        ticker=$(echo "$ticker" | tr '[:lower:]' '[:upper:]')
        data_file="valuation/etf_analysis/data/etf_data_${ticker}.json"
        if [[ ! -f "$data_file" ]]; then
            print_warning "No data found for $ticker. Run 'Fetch ETF Data' first, or enter another ticker."
            continue
        fi
        break
    done

    echo -e "${YELLOW}Number of top holdings to display (default: 10):${NC}"
    read -r holdings_count
    holdings_count="${holdings_count:-10}"

    dune exec valuation/etf_analysis/ocaml/bin/main.exe -- --holdings "$holdings_count" "$data_file"

    if [[ -f "valuation/etf_analysis/output/etf_result_${ticker}.json" ]]; then
        print_success "Results saved to: valuation/etf_analysis/output/etf_result_${ticker}.json"
    else
        print_error "Analysis failed"
    fi
}

run_etf_compare() {
    print_header "Compare ETFs"

    local tickers=""
    while [[ -z "$tickers" ]]; do
        echo -e "${YELLOW}Enter ETF tickers (comma-separated, default: SPY,QQQ,JEPI,SCHD):${NC}"
        read -r tickers
        tickers="${tickers:-SPY,QQQ,JEPI,SCHD}"
    done

    tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]')

    echo -e "${YELLOW}Number of top holdings to display (default: 10):${NC}"
    read -r holdings_count
    holdings_count="${holdings_count:-10}"

    # Build file paths from tickers
    IFS=',' read -ra ticker_array <<< "$tickers"
    local files=()
    for t in "${ticker_array[@]}"; do
        t=$(echo "$t" | tr -d ' ')
        files+=("valuation/etf_analysis/data/etf_data_${t}.json")
    done

    dune exec valuation/etf_analysis/ocaml/bin/main.exe -- --holdings "$holdings_count" --compare "${files[@]}"

    if [[ -f "valuation/etf_analysis/output/etf_comparison.json" ]]; then
        print_success "Comparison saved to: valuation/etf_analysis/output/etf_comparison.json"
    fi
}

run_etf_full_workflow() {
    print_header "ETF Analysis - Full Workflow"

    local tickers=""
    while [[ -z "$tickers" ]]; do
        echo -e "${YELLOW}Enter ETF tickers (comma-separated, default: SPY,QQQ,JEPI,SCHD):${NC}"
        read -r tickers
        tickers="${tickers:-SPY,QQQ,JEPI,SCHD}"
    done

    tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]')

    echo -e "${YELLOW}Number of top holdings to display (default: 10):${NC}"
    read -r holdings_count
    holdings_count="${holdings_count:-10}"

    # Step 1: Fetch data for each ticker
    IFS=',' read -ra ticker_array <<< "$tickers"
    print_info "Step 1/3: Fetching ETF data..."
    for t in "${ticker_array[@]}"; do
        t=$(echo "$t" | tr -d ' ')
        print_info "  Fetching $t..."
        uv run python valuation/etf_analysis/python/fetch/fetch_etf_data.py "$t"
    done
    print_success "Data fetched"

    # Step 2: Run analysis
    # Build file paths from tickers
    local files=()
    for t in "${ticker_array[@]}"; do
        t=$(echo "$t" | tr -d ' ')
        files+=("valuation/etf_analysis/data/etf_data_${t}.json")
    done

    if [[ ${#ticker_array[@]} -eq 1 ]]; then
        # Single ticker - run single analysis
        print_info "Step 2/3: Running ETF analysis..."
        local single_ticker=$(echo "${ticker_array[0]}" | tr -d ' ')
        dune exec valuation/etf_analysis/ocaml/bin/main.exe -- --holdings "$holdings_count" "${files[0]}"

        if [[ -f "valuation/etf_analysis/output/etf_result_${single_ticker}.json" ]]; then
            print_success "Results saved to: valuation/etf_analysis/output/etf_result_${single_ticker}.json"
        fi

        # Step 3: Generate plots
        print_info "Step 3/3: Generating plots..."
        uv run python valuation/etf_analysis/python/viz/plot_etf.py \
            --input "valuation/etf_analysis/output/etf_result_${single_ticker}.json"
    else
        # Multiple tickers - run individual analyses + comparison
        print_info "Step 2/3: Running analysis..."
        for t in "${ticker_array[@]}"; do
            t=$(echo "$t" | tr -d ' ')
            dune exec valuation/etf_analysis/ocaml/bin/main.exe -- --holdings "$holdings_count" "valuation/etf_analysis/data/etf_data_${t}.json"
        done
        print_info "Running comparison..."
        dune exec valuation/etf_analysis/ocaml/bin/main.exe -- --holdings "$holdings_count" --compare "${files[@]}"

        if [[ -f "valuation/etf_analysis/output/etf_comparison.json" ]]; then
            print_success "Comparison saved to: valuation/etf_analysis/output/etf_comparison.json"
        fi

        # Step 3: Generate plots for each ticker
        print_info "Step 3/3: Generating plots..."
        for t in "${ticker_array[@]}"; do
            t=$(echo "$t" | tr -d ' ')
            local result_file="valuation/etf_analysis/output/etf_result_${t}.json"
            if [[ -f "$result_file" ]]; then
                uv run python valuation/etf_analysis/python/viz/plot_etf.py --input "$result_file"
            fi
        done
    fi

    print_success "Full workflow complete!"

    # Show suggestions for portfolio analysis
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}Next Steps: Analyze the underlying holdings${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "  Copy the tickers from above and use them with these models:"
    echo ""
    echo -e "  ${YELLOW}── Portfolio Risk ──${NC}"
    echo -e "  ${GREEN}Pricing > 1) Regime-Aware Downside Optimization${NC}"
    echo "     → See how holdings behave in stress/crisis regimes"
    echo "     → CVaR analysis to understand ETF's downside exposure"
    echo -e "  ${GREEN}Pricing > 17) Tail Risk Forecast${NC}"
    echo "     → VaR/ES forecasting for holdings"
    echo ""
    echo -e "  ${YELLOW}── Valuation ──${NC}"
    echo -e "  ${GREEN}Valuation > 1) DCF Deterministic${NC}"
    echo "     → Intrinsic value of holdings - is the ETF holding overvalued stocks?"
    echo -e "  ${GREEN}Valuation > 2) DCF Probabilistic (Monte Carlo)${NC}"
    echo "     → Probabilistic valuation + efficient frontier of holdings"
    echo -e "  ${GREEN}Valuation > 9) Relative Valuation${NC}"
    echo "     → Compare holdings vs their peers"
    echo -e "  ${GREEN}Valuation > 10) Normalized Multiples${NC}"
    echo "     → Which holdings are cheap/expensive vs sector?"
    echo ""
    echo -e "  ${YELLOW}── Fundamentals ──${NC}"
    echo -e "  ${GREEN}Valuation > 7) GARP/PEG Analysis${NC}"
    echo "     → Quality + growth scoring of holdings"
    echo -e "  ${GREEN}Valuation > 8) Growth Analysis${NC}"
    echo "     → Revenue growth, margins, Rule of 40"
    echo -e "  ${GREEN}Valuation > 5) Dividend Income Analysis${NC}"
    echo "     → For dividend ETFs: yield safety, payout ratios"
    echo -e "  ${GREEN}Pricing > 15) Liquidity Analysis${NC}"
    echo "     → Tradability of holdings (esp. for small-cap ETFs)"
    echo ""

    read -p "Press Enter to continue..."
}

# ═══════════════════════════════════════════════════════════════════════════════
# GARP/PEG Analysis
# ═══════════════════════════════════════════════════════════════════════════════

show_garp_peg_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ GARP/PEG Analysis ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Fetch GARP Data"
        echo -e "${GREEN}2)${NC} Run GARP Analysis (OCaml)"
        echo -e "${GREEN}3)${NC} Compare Multiple Stocks"
        echo -e "${GREEN}4)${NC} Generate Visualization"
        echo -e "${GREEN}5)${NC} Run Full Workflow"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Valuation"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_garp_data ;;
            2) run_garp_analysis ;;
            3) run_garp_compare ;;
            4) plot_garp_results ;;
            5|"") run_garp_full_workflow ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_garp_data() {
    print_header "Fetch GARP Data"

    echo -e "${YELLOW}Enter ticker symbol:${NC}"
    read -r ticker

    if [[ -z "$ticker" ]]; then
        print_error "Ticker is required"
        return 1
    fi

    ticker=$(echo "$ticker" | tr '[:lower:]' '[:upper:]')
    uv run python valuation/garp_peg/python/fetch/fetch_garp_data.py \
        --ticker "$ticker" \
        --output valuation/garp_peg/data

    if [[ -f "valuation/garp_peg/data/garp_data_${ticker}.json" ]]; then
        print_success "Data saved to: valuation/garp_peg/data/garp_data_${ticker}.json"
    else
        print_error "Failed to fetch GARP data"
    fi
}

run_garp_analysis() {
    print_header "Run GARP Analysis (OCaml)"

    echo -e "${YELLOW}Enter ticker symbol:${NC}"
    read -r ticker

    if [[ -z "$ticker" ]]; then
        print_error "Ticker is required"
        return 1
    fi

    ticker=$(echo "$ticker" | tr '[:lower:]' '[:upper:]')
    if [[ ! -f "valuation/garp_peg/data/garp_data_${ticker}.json" ]]; then
        print_error "No data found for $ticker. Run 'Fetch GARP Data' first."
        return 1
    fi

    eval $(opam env) && dune exec garp_peg -- \
        --ticker "$ticker" \
        --data valuation/garp_peg/data \
        --output valuation/garp_peg/output

    if [[ -f "valuation/garp_peg/output/garp_result_${ticker}.json" ]]; then
        print_success "Results saved to: valuation/garp_peg/output/garp_result_${ticker}.json"
    else
        print_error "Analysis failed"
    fi
}

run_garp_compare() {
    print_header "Compare GARP Stocks"

    echo -e "${YELLOW}Enter tickers (comma-separated, e.g., AAPL,VRT,NVDA):${NC}"
    read -r tickers

    if [[ -z "$tickers" ]]; then
        print_error "At least one ticker is required"
        return 1
    fi

    tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]')
    eval $(opam env) && dune exec garp_peg -- \
        --tickers "$tickers" \
        --compare \
        --data valuation/garp_peg/data \
        --output valuation/garp_peg/output

    if [[ -f "valuation/garp_peg/output/garp_comparison.json" ]]; then
        print_success "Comparison saved to: valuation/garp_peg/output/garp_comparison.json"
    fi
}

plot_garp_results() {
    print_header "Generate GARP Visualization"

    echo -e "${YELLOW}Plot single result or comparison? (1=single, 2=comparison):${NC}"
    read -r plot_type

    if [[ "$plot_type" == "1" ]]; then
        echo -e "${YELLOW}Enter ticker symbol:${NC}"
        read -r ticker
        ticker=$(echo "$ticker" | tr '[:lower:]' '[:upper:]')

        if [[ ! -f "valuation/garp_peg/output/garp_result_${ticker}.json" ]]; then
            print_error "No results found for $ticker. Run analysis first."
            return 1
        fi

        uv run python valuation/garp_peg/python/viz/plot_garp.py \
            --result "valuation/garp_peg/output/garp_result_${ticker}.json"

        if [[ -f "valuation/garp_peg/output/garp_dashboard_${ticker}.png" ]]; then
            print_success "Plot saved to: valuation/garp_peg/output/garp_dashboard_${ticker}.png"
        fi
    else
        if [[ ! -f "valuation/garp_peg/output/garp_comparison.json" ]]; then
            print_error "No comparison results found. Run comparison first."
            return 1
        fi

        uv run python valuation/garp_peg/python/viz/plot_garp.py \
            --comparison "valuation/garp_peg/output/garp_comparison.json"

        if [[ -f "valuation/garp_peg/output/garp_comparison.png" ]]; then
            print_success "Plot saved to: valuation/garp_peg/output/garp_comparison.png"
        fi
    fi
}

run_garp_full_workflow() {
    print_header "GARP Analysis - Full Workflow"

    local default_tickers="META,SFM,AAPL,PLTR,COST"
    echo -e "${YELLOW}Enter tickers (comma-separated, default: ${default_tickers}):${NC}"
    read -r tickers

    if [[ -z "$tickers" ]]; then
        tickers="$default_tickers"
        print_info "Using default tickers: $tickers"
    fi

    tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]')

    # Step 1: Fetch data for each ticker
    IFS=',' read -ra ticker_array <<< "$tickers"
    print_info "Step 1/4: Fetching GARP data..."
    for t in "${ticker_array[@]}"; do
        t=$(echo "$t" | tr -d ' ')
        print_info "  Fetching $t..."
        uv run python valuation/garp_peg/python/fetch/fetch_garp_data.py \
            --ticker "$t" \
            --output valuation/garp_peg/data
    done
    print_success "Data fetched"

    # Step 2: Run comparison analysis
    print_info "Step 2/4: Running comparison analysis..."
    eval $(opam env) && dune exec garp_peg -- \
        --tickers "$tickers" \
        --compare \
        --data valuation/garp_peg/data \
        --output valuation/garp_peg/output

    if [[ -f "valuation/garp_peg/output/garp_comparison.json" ]]; then
        print_success "Comparison saved"
    fi

    # Step 3: Generate individual visualizations
    print_info "Step 3/4: Generating individual plots..."
    for t in "${ticker_array[@]}"; do
        t=$(echo "$t" | tr -d ' ')
        if [[ -f "valuation/garp_peg/output/garp_result_${t}.json" ]]; then
            uv run python valuation/garp_peg/python/viz/plot_garp.py \
                --result "valuation/garp_peg/output/garp_result_${t}.json"
        fi
    done

    # Step 4: Generate comparison visualization
    print_info "Step 4/4: Generating comparison plot..."
    uv run python valuation/garp_peg/python/viz/plot_garp.py \
        --comparison "valuation/garp_peg/output/garp_comparison.json"

    if [[ -f "valuation/garp_peg/output/garp_comparison.png" ]]; then
        print_success "Plot saved to: valuation/garp_peg/output/garp_comparison.png"
    fi

    print_success "Full workflow complete!"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Growth Analysis
# ═══════════════════════════════════════════════════════════════════════════════

show_growth_analysis_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Growth Analysis ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Fetch Growth Data"
        echo -e "${GREEN}2)${NC} Run Growth Analysis (OCaml)"
        echo -e "${GREEN}3)${NC} Compare Multiple Stocks"
        echo -e "${GREEN}4)${NC} Run Full Workflow"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Valuation"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_growth_data ;;
            2) run_growth_analysis ;;
            3) run_growth_compare ;;
            4|"") run_growth_full_workflow ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_growth_data() {
    print_header "Fetch Growth Data"

    echo -e "${YELLOW}Enter ticker symbol:${NC}"
    read -r ticker

    if [[ -z "$ticker" ]]; then
        print_error "Ticker is required"
        return 1
    fi

    ticker=$(echo "$ticker" | tr '[:lower:]' '[:upper:]')
    .venv/bin/python3 valuation/growth_analysis/python/fetch/fetch_growth_data.py \
        --ticker "$ticker" \
        --output valuation/growth_analysis/data

    if [[ -f "valuation/growth_analysis/data/growth_data_${ticker}.json" ]]; then
        print_success "Data saved to: valuation/growth_analysis/data/growth_data_${ticker}.json"
    else
        print_error "Failed to fetch growth data"
    fi
}

run_growth_analysis() {
    print_header "Run Growth Analysis (OCaml)"

    echo -e "${YELLOW}Enter ticker symbol:${NC}"
    read -r ticker

    if [[ -z "$ticker" ]]; then
        print_error "Ticker is required"
        return 1
    fi

    ticker=$(echo "$ticker" | tr '[:lower:]' '[:upper:]')
    if [[ ! -f "valuation/growth_analysis/data/growth_data_${ticker}.json" ]]; then
        print_error "No data found for $ticker. Run 'Fetch Growth Data' first."
        return 1
    fi

    dune exec valuation/growth_analysis/ocaml/bin/main.exe -- \
        --ticker "$ticker" \
        --data valuation/growth_analysis/data \
        --output valuation/growth_analysis/output

    if [[ -f "valuation/growth_analysis/output/growth_result_${ticker}.json" ]]; then
        print_success "Results saved to: valuation/growth_analysis/output/growth_result_${ticker}.json"
    else
        print_error "Analysis failed"
    fi
}

run_growth_compare() {
    print_header "Compare Growth Stocks"

    echo -e "${YELLOW}Enter tickers (comma-separated, e.g., VRT,NVDA,CRWD):${NC}"
    read -r tickers

    if [[ -z "$tickers" ]]; then
        print_error "At least one ticker is required"
        return 1
    fi

    tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]')
    dune exec valuation/growth_analysis/ocaml/bin/main.exe -- \
        --tickers "$tickers" \
        --compare \
        --data valuation/growth_analysis/data \
        --output valuation/growth_analysis/output

    if [[ -f "valuation/growth_analysis/output/growth_comparison.json" ]]; then
        print_success "Comparison saved to: valuation/growth_analysis/output/growth_comparison.json"
        print_info "Generating comparison plot..."
        uv run valuation/growth_analysis/python/viz/plot_growth.py \
            --comparison valuation/growth_analysis/output/growth_comparison.json || true
    fi
}

run_growth_full_workflow() {
    print_header "Growth Analysis - Full Workflow"

    local default_tickers="NVDA,CRWD,SFM,JNJ,PLTR"

    echo -e "${YELLOW}Enter tickers (comma-separated, Enter=${default_tickers}):${NC}"
    read -r tickers
    tickers="${tickers:-$default_tickers}"
    tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]')

    # Step 1: Fetch data for each ticker
    IFS=',' read -ra ticker_array <<< "$tickers"
    print_info "Step 1/2: Fetching growth data..."
    for t in "${ticker_array[@]}"; do
        t=$(echo "$t" | tr -d ' ')
        print_info "  Fetching $t..."
        uv run python valuation/growth_analysis/python/fetch/fetch_growth_data.py \
            --ticker "$t" \
            --output valuation/growth_analysis/data
    done
    print_success "Data fetched"

    # Step 2: Run comparison analysis
    print_info "Step 2/2: Running comparison analysis..."
    eval $(opam env)
    dune exec growth_analysis -- \
        --tickers "$tickers" \
        --compare \
        --data valuation/growth_analysis/data \
        --output valuation/growth_analysis/output

    if [[ -f "valuation/growth_analysis/output/growth_comparison.json" ]]; then
        print_success "Comparison saved to: valuation/growth_analysis/output/growth_comparison.json"
    fi

    print_success "Full workflow complete!"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Relative Valuation
# ═══════════════════════════════════════════════════════════════════════════════

show_relative_valuation_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Relative Valuation ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Fetch Peer Data"
        echo -e "${GREEN}2)${NC} Run Relative Valuation (OCaml)"
        echo -e "${GREEN}3)${NC} Run Full Workflow"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Valuation"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_peer_data ;;
            2) run_relative_valuation ;;
            3|"") run_relative_valuation_full_workflow ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_peer_data() {
    print_header "Fetch Peer Data"

    echo -e "${YELLOW}Enter target ticker:${NC}"
    read -r target

    if [[ -z "$target" ]]; then
        print_error "Target ticker is required"
        return 1
    fi

    target=$(echo "$target" | tr '[:lower:]' '[:upper:]')

    echo -e "${YELLOW}Enter peer tickers (comma-separated, e.g., MSFT,GOOGL,META):${NC}"
    read -r peers

    if [[ -z "$peers" ]]; then
        print_error "At least one peer ticker is required"
        return 1
    fi

    peers=$(echo "$peers" | tr '[:lower:]' '[:upper:]')
    .venv/bin/python3 valuation/relative_valuation/python/fetch/fetch_peer_data.py \
        --target "$target" \
        --peers "$peers" \
        --output valuation/relative_valuation/data

    if [[ -f "valuation/relative_valuation/data/peer_data_${target}.json" ]]; then
        print_success "Data saved to: valuation/relative_valuation/data/peer_data_${target}.json"
    else
        print_error "Failed to fetch peer data"
    fi
}

run_relative_valuation() {
    print_header "Run Relative Valuation (OCaml)"

    echo -e "${YELLOW}Enter target ticker:${NC}"
    read -r target

    if [[ -z "$target" ]]; then
        print_error "Target ticker is required"
        return 1
    fi

    target=$(echo "$target" | tr '[:lower:]' '[:upper:]')
    if [[ ! -f "valuation/relative_valuation/data/peer_data_${target}.json" ]]; then
        print_error "No data found for $target. Run 'Fetch Peer Data' first."
        return 1
    fi

    echo -e "${YELLOW}Enter peer tickers (comma-separated):${NC}"
    read -r peers

    if [[ -z "$peers" ]]; then
        print_error "At least one peer ticker is required"
        return 1
    fi

    peers=$(echo "$peers" | tr '[:lower:]' '[:upper:]')
    dune exec valuation/relative_valuation/ocaml/bin/main.exe -- \
        --target "$target" \
        --peers "$peers" \
        --data valuation/relative_valuation/data \
        --output valuation/relative_valuation/output

    if [[ -f "valuation/relative_valuation/output/relative_result_${target}.json" ]]; then
        print_success "Results saved to: valuation/relative_valuation/output/relative_result_${target}.json"
    else
        print_error "Analysis failed"
    fi
}

run_relative_valuation_full_workflow() {
    print_header "Relative Valuation - Full Workflow"

    local default_target="TAC"
    local default_peers="AES,VST,NRG,CEG,CWEN,BEP"

    echo -e "${YELLOW}Enter target ticker (Enter=${default_target}):${NC}"
    read -r target
    target="${target:-$default_target}"
    target=$(echo "$target" | tr '[:lower:]' '[:upper:]')

    echo -e "${YELLOW}Enter peer tickers (comma-separated, Enter=${default_peers}):${NC}"
    read -r peers
    peers="${peers:-$default_peers}"
    peers=$(echo "$peers" | tr '[:lower:]' '[:upper:]')

    # Step 1: Fetch peer data
    print_info "Step 1/2: Fetching peer data..."
    uv run python valuation/relative_valuation/python/fetch/fetch_peer_data.py \
        --target "$target" \
        --peers "$peers" \
        --output valuation/relative_valuation/data

    if [[ ! -f "valuation/relative_valuation/data/peer_data_${target}.json" ]]; then
        print_error "Failed to fetch peer data"
        return 1
    fi
    print_success "Peer data fetched"

    # Step 2: Run relative valuation
    print_info "Step 2/2: Running relative valuation..."
    eval $(opam env)
    dune exec relative_valuation -- \
        --target "$target" \
        --peers "$peers" \
        --data valuation/relative_valuation/data \
        --output valuation/relative_valuation/output

    if [[ -f "valuation/relative_valuation/output/relative_result_${target}.json" ]]; then
        print_success "Results saved to: valuation/relative_valuation/output/relative_result_${target}.json"
    fi

    print_success "Full workflow complete!"
}

# ═══════════════════════════════════════════════════════════════════════════════
# MONITORING & ALTERNATIVE DATA SECTION
# ═══════════════════════════════════════════════════════════════════════════════

show_monitoring_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Monitoring & Alternative Data ═══${NC}"
        echo -e "${DIM}[IBKR+] = Benefits from IBKR real-time options data${NC}\n"
        echo -e "${GREEN}1)${NC} ${BOLD}Portfolio Tracker${NC}"
        echo -e "${DIM}   Track watchlist tickers with technical signals (RSI, OBV, volume surge)."
        echo -e "   Generates alerts compatible with ntfy.sh push notifications.${NC}"
        echo ""
        echo -e "${GREEN}2)${NC} ${BOLD}Google Trends${NC}"
        echo -e "${DIM}   Monitor brand/product search interest via Google Trends."
        echo -e "   Detects retail attention surges and negative sentiment spikes.${NC}"
        echo ""
        echo -e "${GREEN}3)${NC} ${BOLD}Insider Trading (Form 4)${NC}"
        echo -e "${DIM}   Track insider buying/selling via SEC Form 4 filings."
        echo -e "   Detects cluster buying, executive purchases, large transactions.${NC}"
        echo ""
        echo -e "${GREEN}4)${NC} ${BOLD}SEC Filings${NC}"
        echo -e "${DIM}   Monitor material SEC filings (8-K, 10-K, 13D, etc.)."
        echo -e "   Classifies importance and detects material events.${NC}"
        echo ""
        echo -e "${GREEN}5)${NC} ${BOLD}Options Flow${NC} ${CYAN}[IBKR+]${NC}"
        echo -e "${DIM}   Track unusual options activity and flow sentiment."
        echo -e "   Detects bullish/bearish flow, large premiums, new positions.${NC}"
        echo ""
        echo -e "${GREEN}6)${NC} ${BOLD}Short Interest${NC}"
        echo -e "${DIM}   Monitor short interest, days to cover, and squeeze potential."
        echo -e "   Identifies squeeze candidates with high SI% and low float.${NC}"
        echo ""
        echo -e "${GREEN}7)${NC} ${BOLD}NLP Sentiment (Narrative Drift)${NC}"
        echo -e "${DIM}   Detect changes in corporate narrative via NLP on MD&A and transcripts."
        echo -e "   Analyzes hedging language, commitment levels, and material changes.${NC}"
        echo ""
        echo -e "${GREEN}8)${NC} ${BOLD}Systematic Risk Signals${NC}"
        echo -e "${DIM}   Early-warning signals for systematic risk via graph theory (MST)"
        echo -e "   and covariance eigenvalue analysis. Based on Ciciretti et al. 2025.${NC}"
        echo ""
        echo -e "${GREEN}9)${NC} ${BOLD}Macro Dashboard${NC}"
        echo -e "${DIM}   Quick macro environment snapshot: rates, inflation, employment, growth."
        echo -e "   Classifies cycle phase, Fed stance, recession probability, sector tilts.${NC}"
        echo ""
        echo -e "${GREEN}10)${NC} ${BOLD}Earnings Calendar${NC}"
        echo -e "${DIM}   Track upcoming earnings with BMO/AMC timing and EPS surprise history."
        echo -e "   Alert N days before earnings. Read from portfolio or custom tickers.${NC}"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Run Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) show_watchlist_menu ;;
            2) show_google_trends_menu ;;
            3) show_insider_trading_menu ;;
            4) show_sec_filings_menu ;;
            5) show_options_flow_menu ;;
            6) show_short_interest_menu ;;
            7) show_nlp_sentiment_menu ;;
            8) show_systematic_risk_menu ;;
            9) show_macro_dashboard_menu ;;
            10) show_earnings_calendar_menu ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

# ═══════════════════════════════════════════════════════════════════════════════
# Portfolio Tracker
# ═══════════════════════════════════════════════════════════════════════════════

show_watchlist_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Portfolio Tracker ═══${NC}\n"
        echo -e "${YELLOW}─── Analysis ───${NC}"
        echo -e "${GREEN}1)${NC} ${BOLD}Full Workflow${NC}"
        echo -e "${DIM}   Fetch prices → Analyze → Detect changes → Show alerts${NC}"
        echo ""
        echo -e "${GREEN}2)${NC} View Portfolio Analysis"
        echo -e "${GREEN}3)${NC} View Alerts Only"
        echo ""
        echo -e "${YELLOW}─── Management ───${NC}"
        echo -e "${GREEN}4)${NC} List Positions"
        echo -e "${GREEN}5)${NC} Add Position"
        echo -e "${GREEN}6)${NC} Remove Position"
        echo -e "${GREEN}7)${NC} Show Position Details"
        echo -e "${GREEN}8)${NC} Edit Portfolio (JSON)"
        echo ""
        echo -e "${YELLOW}─── Notifications ───${NC}"
        echo -e "${GREEN}9)${NC} Send Alerts via ntfy.sh"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Monitoring & Alternative Data"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1|"") run_full_watchlist_workflow ;;
            2) run_portfolio_analysis ;;
            3) view_portfolio_alerts ;;
            4) list_portfolio_positions ;;
            5) add_portfolio_position ;;
            6) remove_portfolio_position ;;
            7) show_portfolio_position ;;
            8) edit_portfolio ;;
            9) send_watchlist_notifications ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

run_portfolio_analysis() {
    print_header "Portfolio Analysis"

    if [[ ! -f "monitoring/watchlist/data/portfolio.json" ]]; then
        print_error "No portfolio found at monitoring/watchlist/data/portfolio.json"
        echo "Create a portfolio.json file with your positions and thesis arguments."
        return 1
    fi

    # Check if we have prices data
    local prices_arg=""
    if [[ -f "monitoring/watchlist/data/prices.json" ]]; then
        prices_arg="--prices monitoring/watchlist/data/prices.json"
    else
        print_info "No prices data found. Run 'Update Prices' for P&L tracking."
        echo ""
    fi

    # Run portfolio analysis
    dune exec monitoring/watchlist/ocaml/bin/main.exe -- \
        --portfolio monitoring/watchlist/data/portfolio.json \
        $prices_arg \
        --output monitoring/watchlist/output/analysis.json

    echo ""
    print_success "Analysis saved to monitoring/watchlist/output/analysis.json"
}

update_portfolio_prices() {
    print_header "Updating Market Prices"

    if [[ ! -f "monitoring/watchlist/data/portfolio.json" ]]; then
        print_error "No portfolio found at monitoring/watchlist/data/portfolio.json"
        return 1
    fi

    print_info "Fetching latest prices..."
    .venv/bin/python3 monitoring/watchlist/python/fetch_prices.py \
        --portfolio monitoring/watchlist/data/portfolio.json \
        --output monitoring/watchlist/data/prices.json

    print_success "Prices updated"
}

view_portfolio_alerts() {
    print_header "Portfolio Alerts"

    if [[ ! -f "monitoring/watchlist/data/portfolio.json" ]]; then
        print_error "No portfolio found at monitoring/watchlist/data/portfolio.json"
        return 1
    fi

    local prices_arg=""
    if [[ -f "monitoring/watchlist/data/prices.json" ]]; then
        prices_arg="--prices monitoring/watchlist/data/prices.json"
    fi

    dune exec monitoring/watchlist/ocaml/bin/main.exe -- \
        --portfolio monitoring/watchlist/data/portfolio.json \
        $prices_arg \
        --quiet
}

edit_portfolio() {
    local portfolio_file="monitoring/watchlist/data/portfolio.json"

    if [[ -n "$EDITOR" ]]; then
        $EDITOR "$portfolio_file"
    elif command -v nano &> /dev/null; then
        nano "$portfolio_file"
    elif command -v vim &> /dev/null; then
        vim "$portfolio_file"
    else
        print_error "No editor found. Set EDITOR environment variable."
        echo "Portfolio file: $portfolio_file"
    fi
}

run_full_watchlist_workflow() {
    print_header "Full Watchlist Workflow"

    local portfolio_file="monitoring/watchlist/data/portfolio.json"
    local prices_file="monitoring/watchlist/data/prices.json"
    local analysis_file="monitoring/watchlist/output/analysis.json"
    local state_file="monitoring/watchlist/data/state.json"

    if [[ ! -f "$portfolio_file" ]]; then
        print_error "No portfolio found at $portfolio_file"
        echo "Add positions with: List Positions → Add Position"
        return 1
    fi

    # Step 1: Fetch prices
    print_info "Step 1/3: Fetching market prices..."
    .venv/bin/python3 monitoring/watchlist/python/fetch_prices.py \
        --portfolio "$portfolio_file" \
        --output "$prices_file"

    # Step 2: Run analysis
    print_info "Step 2/3: Running portfolio analysis..."
    dune exec monitoring/watchlist/ocaml/bin/main.exe -- \
        --portfolio "$portfolio_file" \
        --prices "$prices_file" \
        --output "$analysis_file"

    # Step 3: Detect changes
    echo ""
    print_info "Step 3/3: Detecting changes since last run..."
    .venv/bin/python3 monitoring/watchlist/python/state_diff.py \
        --current "$analysis_file" \
        --state "$state_file" \
        --update-state

    echo ""
    print_success "Workflow complete!"
    print_info "Analysis saved to: $analysis_file"
}

list_portfolio_positions() {
    print_header "Portfolio Positions"
    .venv/bin/python3 monitoring/watchlist/python/manage.py list
}

add_portfolio_position() {
    print_header "Add Position"

    echo -e "${YELLOW}Enter ticker symbol:${NC}"
    read -r ticker

    if [[ -z "$ticker" ]]; then
        print_error "Ticker is required"
        return 1
    fi

    echo -e "${YELLOW}Position type (long/short/watching) [watching]:${NC}"
    read -r pos_type
    pos_type=${pos_type:-watching}

    local args="$ticker --type $pos_type"

    if [[ "$pos_type" == "long" || "$pos_type" == "short" ]]; then
        echo -e "${YELLOW}Number of shares:${NC}"
        read -r shares
        if [[ -n "$shares" ]]; then
            args="$args --shares $shares"
        fi

        echo -e "${YELLOW}Average cost basis:${NC}"
        read -r cost
        if [[ -n "$cost" ]]; then
            args="$args --cost $cost"
        fi

        echo -e "${YELLOW}Stop loss price (optional):${NC}"
        read -r stop
        if [[ -n "$stop" ]]; then
            args="$args --stop-loss $stop"
        fi

        echo -e "${YELLOW}Sell target price (optional):${NC}"
        read -r target
        if [[ -n "$target" ]]; then
            args="$args --sell-target $target"
        fi
    else
        echo -e "${YELLOW}Buy target price (optional):${NC}"
        read -r buy_target
        if [[ -n "$buy_target" ]]; then
            args="$args --buy-target $buy_target"
        fi
    fi

    echo -e "${YELLOW}Notes (optional):${NC}"
    read -r notes
    if [[ -n "$notes" ]]; then
        args="$args --note \"$notes\""
    fi

    eval ".venv/bin/python3 monitoring/watchlist/python/manage.py add $args"
}

remove_portfolio_position() {
    print_header "Remove Position"

    echo -e "${YELLOW}Enter ticker symbol to remove:${NC}"
    read -r ticker

    if [[ -z "$ticker" ]]; then
        print_error "Ticker is required"
        return 1
    fi

    .venv/bin/python3 monitoring/watchlist/python/manage.py remove "$ticker"
}

show_portfolio_position() {
    print_header "Position Details"

    echo -e "${YELLOW}Enter ticker symbol:${NC}"
    read -r ticker

    if [[ -z "$ticker" ]]; then
        print_error "Ticker is required"
        return 1
    fi

    .venv/bin/python3 monitoring/watchlist/python/manage.py show "$ticker"
}

send_watchlist_notifications() {
    print_header "Send Notifications"

    local alerts_file="monitoring/watchlist/output/analysis.json"

    if [[ ! -f "$alerts_file" ]]; then
        print_error "No analysis found. Run 'Full Workflow' first."
        return 1
    fi

    local topic="${NTFY_TOPIC:-}"

    if [[ -z "$topic" ]]; then
        echo -e "${YELLOW}Enter ntfy.sh topic name:${NC}"
        read -r topic

        if [[ -z "$topic" ]]; then
            print_error "Topic is required. Set NTFY_TOPIC or enter one."
            return 1
        fi
    fi

    echo -e "${YELLOW}Dry run? (y/N):${NC}"
    read -r dry_run

    local dry_run_arg=""
    if [[ "$dry_run" == "y" || "$dry_run" == "Y" ]]; then
        dry_run_arg="--dry-run"
    fi

    .venv/bin/python3 monitoring/watchlist/python/notify.py \
        --alerts "$alerts_file" \
        --topic "$topic" \
        $dry_run_arg
}

# ═══════════════════════════════════════════════════════════════════════════════
# Earnings Calendar
# ═══════════════════════════════════════════════════════════════════════════════

show_earnings_calendar_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Earnings Calendar ═══${NC}\n"
        echo -e "${GREEN}1)${NC} ${BOLD}Full Scan (Portfolio)${NC}"
        echo -e "${DIM}   Fetch earnings for all tickers in watchlist portfolio.json${NC}"
        echo ""
        echo -e "${GREEN}2)${NC} ${BOLD}Quick Scan (Custom Tickers)${NC}"
        echo -e "${DIM}   Enter tickers manually for quick earnings check${NC}"
        echo ""
        echo -e "${GREEN}3)${NC} ${BOLD}View Dashboard${NC}"
        echo -e "${DIM}   Regenerate and display the earnings calendar plot${NC}"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Monitoring & Alternative Data"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Quick Scan):${NC} "
        read -r choice

        case $choice in
            1) run_earnings_calendar_full ;;
            2|"") run_earnings_calendar_quick ;;
            3) view_earnings_calendar_dashboard ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

run_earnings_calendar_full() {
    print_header "Earnings Calendar - Full Portfolio Scan"

    local portfolio_file="monitoring/watchlist/data/portfolio.json"
    if [[ ! -f "$portfolio_file" ]]; then
        print_error "No portfolio found at $portfolio_file"
        echo "Add positions via the Portfolio Tracker, or use Quick Scan with --tickers."
        return 1
    fi

    print_info "Fetching earnings calendar from portfolio..."
    .venv/bin/python3 monitoring/earnings_calendar/python/fetch/fetch_earnings_calendar.py \
        --portfolio "$portfolio_file" --days-ahead 14

    if [[ -f "monitoring/earnings_calendar/data/earnings_calendar.json" ]]; then
        print_info "Generating dashboard..."
        .venv/bin/python3 monitoring/earnings_calendar/python/viz/plot_earnings_calendar.py \
            --input monitoring/earnings_calendar/data/earnings_calendar.json
        print_success "Dashboard saved to monitoring/earnings_calendar/output/"
    fi
}

run_earnings_calendar_quick() {
    print_header "Earnings Calendar - Quick Scan"

    local default_tickers="AMZN,CBOE,CVX,IBKR,JPM,LLY,NVDA,TAC"
    echo -e "${YELLOW}Enter tickers (comma-separated, default: ${default_tickers}):${NC} "
    read -r tickers_input
    tickers_input="${tickers_input:-$default_tickers}"

    echo ""
    echo -e "${YELLOW}Alert window in days (default=14):${NC} "
    read -r days_input
    days_input="${days_input:-14}"

    .venv/bin/python3 monitoring/earnings_calendar/python/fetch/fetch_earnings_calendar.py \
        --tickers "$tickers_input" --days-ahead "$days_input"

    if [[ -f "monitoring/earnings_calendar/data/earnings_calendar.json" ]]; then
        print_info "Generating dashboard..."
        .venv/bin/python3 monitoring/earnings_calendar/python/viz/plot_earnings_calendar.py \
            --input monitoring/earnings_calendar/data/earnings_calendar.json
        print_success "Dashboard saved to monitoring/earnings_calendar/output/"
    fi
}

view_earnings_calendar_dashboard() {
    local data_file="monitoring/earnings_calendar/data/earnings_calendar.json"
    if [[ ! -f "$data_file" ]]; then
        print_error "No earnings data found. Run Full Scan or Quick Scan first."
        return 1
    fi

    .venv/bin/python3 monitoring/earnings_calendar/python/viz/plot_earnings_calendar.py \
        --input "$data_file"
    print_success "Dashboard regenerated."
}

# ═══════════════════════════════════════════════════════════════════════════════
# Google Trends
# ═══════════════════════════════════════════════════════════════════════════════

show_google_trends_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Google Trends ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Fetch Trends Data"
        echo -e "${GREEN}2)${NC} Analyze Trends"
        echo -e "${GREEN}3)${NC} Run Full Workflow"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Monitoring & Alternative Data"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_google_trends ;;
            2) analyze_google_trends ;;
            3|"") run_google_trends_workflow ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_google_trends() {
    print_header "Fetch Google Trends Data"

    echo -e "${YELLOW}Enter tickers (comma-separated) or press Enter for all in keyword_map:${NC}"
    read -r tickers

    if [[ -z "$tickers" ]]; then
        .venv/bin/python3 alternative/google_trends/python/fetch_trends.py \
            --all \
            --output-dir alternative/google_trends/data/trends_raw
    else
        tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]' | tr ',' ' ')
        .venv/bin/python3 alternative/google_trends/python/fetch_trends.py \
            $tickers \
            --output-dir alternative/google_trends/data/trends_raw
    fi

    if [[ -f "alternative/google_trends/data/trends_combined.json" ]]; then
        print_success "Data saved to: alternative/google_trends/data/"
    else
        print_error "Failed to fetch trends data"
    fi
}

analyze_google_trends() {
    print_header "Analyze Google Trends"

    if [[ ! -f "alternative/google_trends/data/trends_combined.json" ]]; then
        print_error "No data found. Run 'Fetch Trends Data' first."
        return 1
    fi

    .venv/bin/python3 alternative/google_trends/python/analyze_trends.py \
        --data alternative/google_trends/data/trends_combined.json \
        --output alternative/google_trends/output/trends_alerts.json

    if [[ -f "alternative/google_trends/output/trends_alerts.json" ]]; then
        print_success "Alerts saved to: alternative/google_trends/output/trends_alerts.json"
    fi
}

run_google_trends_workflow() {
    print_header "Google Trends - Full Workflow"

    echo -e "${YELLOW}Enter tickers (comma-separated) or press Enter for all:${NC}"
    read -r tickers

    # Step 1: Fetch data
    print_info "Step 1/2: Fetching trends data..."
    if [[ -z "$tickers" ]]; then
        .venv/bin/python3 alternative/google_trends/python/fetch_trends.py \
            --all \
            --output-dir alternative/google_trends/data/trends_raw
    else
        tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]' | tr ',' ' ')
        .venv/bin/python3 alternative/google_trends/python/fetch_trends.py \
            $tickers \
            --output-dir alternative/google_trends/data/trends_raw
    fi
    print_success "Data fetched"

    # Step 2: Analyze
    print_info "Step 2/2: Analyzing trends..."
    .venv/bin/python3 alternative/google_trends/python/analyze_trends.py \
        --data alternative/google_trends/data/trends_combined.json \
        --output alternative/google_trends/output/trends_alerts.json

    if [[ -f "alternative/google_trends/output/trends_alerts.json" ]]; then
        print_success "Alerts saved to: alternative/google_trends/output/trends_alerts.json"
    fi

    print_success "Full workflow complete!"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Insider Trading (Form 4)
# ═══════════════════════════════════════════════════════════════════════════════

show_insider_trading_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Insider Trading (Form 4) ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Fetch Form 4 Data"
        echo -e "${GREEN}2)${NC} Analyze Insider Activity"
        echo -e "${GREEN}3)${NC} Run Full Workflow"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Monitoring & Alternative Data"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_insider_data ;;
            2) analyze_insider_activity ;;
            3|"") run_insider_workflow ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_insider_data() {
    print_header "Fetch Form 4 Insider Data"

    echo -e "${YELLOW}Enter tickers (comma-separated, default: AAPL,NVDA,TSLA):${NC}"
    read -r tickers
    tickers="${tickers:-AAPL,NVDA,TSLA}"

    tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]' | tr ',' ' ')

    echo -e "${YELLOW}Days to look back (default: 90):${NC}"
    read -r days
    days=${days:-90}

    .venv/bin/python3 alternative/insider_trading/python/fetch_form4.py \
        $tickers \
        --days "$days" \
        --output alternative/insider_trading/data/insider_transactions.json

    if [[ -f "alternative/insider_trading/data/insider_transactions.json" ]]; then
        print_success "Data saved to: alternative/insider_trading/data/insider_transactions.json"
    else
        print_error "Failed to fetch insider data"
    fi
}

analyze_insider_activity() {
    print_header "Analyze Insider Activity"

    if [[ ! -f "alternative/insider_trading/data/insider_transactions.json" ]]; then
        print_error "No data found. Run 'Fetch Form 4 Data' first."
        return 1
    fi

    .venv/bin/python3 alternative/insider_trading/python/analyze_insider.py \
        --data alternative/insider_trading/data/insider_transactions.json \
        --output alternative/insider_trading/output/insider_alerts.json

    if [[ -f "alternative/insider_trading/output/insider_alerts.json" ]]; then
        print_success "Alerts saved to: alternative/insider_trading/output/insider_alerts.json"
    fi
}

run_insider_workflow() {
    print_header "Insider Trading - Full Workflow"

    echo -e "${YELLOW}Enter tickers (comma-separated, default: AAPL,NVDA,TSLA):${NC}"
    read -r tickers
    tickers="${tickers:-AAPL,NVDA,TSLA}"

    tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]' | tr ',' ' ')

    # Step 1: Fetch data
    print_info "Step 1/2: Fetching Form 4 data (last 90 days)..."
    .venv/bin/python3 alternative/insider_trading/python/fetch_form4.py \
        $tickers \
        --days 90 \
        --output alternative/insider_trading/data/insider_transactions.json

    if [[ ! -f "alternative/insider_trading/data/insider_transactions.json" ]]; then
        print_error "Failed to fetch insider data"
        return 1
    fi
    print_success "Data fetched"

    # Step 2: Analyze
    print_info "Step 2/2: Analyzing insider activity..."
    .venv/bin/python3 alternative/insider_trading/python/analyze_insider.py \
        --data alternative/insider_trading/data/insider_transactions.json \
        --output alternative/insider_trading/output/insider_alerts.json

    if [[ -f "alternative/insider_trading/output/insider_alerts.json" ]]; then
        print_success "Alerts saved to: alternative/insider_trading/output/insider_alerts.json"
    fi

    print_success "Full workflow complete!"
}

# ═══════════════════════════════════════════════════════════════════════════════
# SEC Filings
# ═══════════════════════════════════════════════════════════════════════════════

show_sec_filings_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ SEC Filings ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Fetch SEC Filings"
        echo -e "${GREEN}2)${NC} Analyze Filings"
        echo -e "${GREEN}3)${NC} Run Full Workflow"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Monitoring & Alternative Data"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_sec_filings ;;
            2) analyze_sec_filings ;;
            3|"") run_sec_filings_workflow ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_sec_filings() {
    print_header "Fetch SEC Filings"

    echo -e "${YELLOW}Enter tickers (comma-separated, default: AAPL,NVDA,TSLA):${NC}"
    read -r tickers
    tickers="${tickers:-AAPL,NVDA,TSLA}"

    tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]' | tr ',' ' ')

    echo -e "${YELLOW}Days to look back (default: 30):${NC}"
    read -r days
    days=${days:-30}

    .venv/bin/python3 alternative/sec_filings/python/fetch_filings.py \
        $tickers \
        --days "$days" \
        --output alternative/sec_filings/data/sec_filings.json

    if [[ -f "alternative/sec_filings/data/sec_filings.json" ]]; then
        print_success "Data saved to: alternative/sec_filings/data/sec_filings.json"
    else
        print_error "Failed to fetch SEC filings"
    fi
}

analyze_sec_filings() {
    print_header "Analyze SEC Filings"

    if [[ ! -f "alternative/sec_filings/data/sec_filings.json" ]]; then
        print_error "No data found. Run 'Fetch SEC Filings' first."
        return 1
    fi

    .venv/bin/python3 alternative/sec_filings/python/analyze_filings.py \
        --data alternative/sec_filings/data/sec_filings.json \
        --output alternative/sec_filings/output/filing_alerts.json

    if [[ -f "alternative/sec_filings/output/filing_alerts.json" ]]; then
        print_success "Alerts saved to: alternative/sec_filings/output/filing_alerts.json"
    fi
}

run_sec_filings_workflow() {
    print_header "SEC Filings - Full Workflow"

    echo -e "${YELLOW}Enter tickers (comma-separated, default: AAPL,NVDA,TSLA):${NC}"
    read -r tickers
    tickers="${tickers:-AAPL,NVDA,TSLA}"

    tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]' | tr ',' ' ')

    # Step 1: Fetch data
    print_info "Step 1/2: Fetching SEC filings (last 30 days)..."
    .venv/bin/python3 alternative/sec_filings/python/fetch_filings.py \
        $tickers \
        --days 30 \
        --output alternative/sec_filings/data/sec_filings.json

    if [[ ! -f "alternative/sec_filings/data/sec_filings.json" ]]; then
        print_error "Failed to fetch SEC filings"
        return 1
    fi
    print_success "Data fetched"

    # Step 2: Analyze
    print_info "Step 2/2: Analyzing filings..."
    .venv/bin/python3 alternative/sec_filings/python/analyze_filings.py \
        --data alternative/sec_filings/data/sec_filings.json \
        --output alternative/sec_filings/output/filing_alerts.json

    if [[ -f "alternative/sec_filings/output/filing_alerts.json" ]]; then
        print_success "Alerts saved to: alternative/sec_filings/output/filing_alerts.json"
    fi

    print_success "Full workflow complete!"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Options Flow
# ═══════════════════════════════════════════════════════════════════════════════

show_options_flow_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Options Flow ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Fetch Options Flow Data"
        echo -e "${GREEN}2)${NC} Analyze Flow"
        echo -e "${GREEN}3)${NC} Run Full Workflow"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Monitoring & Alternative Data"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_options_flow ;;
            2) analyze_options_flow ;;
            3|"") run_options_flow_workflow ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_options_flow() {
    print_header "Fetch Options Flow Data"

    echo -e "${YELLOW}Enter tickers (comma-separated, default: AAPL,NVDA,TSLA):${NC}"
    read -r tickers
    tickers="${tickers:-AAPL,NVDA,TSLA}"

    tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]' | tr ',' ' ')

    .venv/bin/python3 alternative/options_flow/python/fetch_flow.py \
        $tickers \
        --output alternative/options_flow/data/options_flow.json

    if [[ -f "alternative/options_flow/data/options_flow.json" ]]; then
        print_success "Data saved to: alternative/options_flow/data/options_flow.json"
    else
        print_error "Failed to fetch options flow data"
    fi
}

analyze_options_flow() {
    print_header "Analyze Options Flow"

    if [[ ! -f "alternative/options_flow/data/options_flow.json" ]]; then
        print_error "No data found. Run 'Fetch Options Flow Data' first."
        return 1
    fi

    .venv/bin/python3 alternative/options_flow/python/analyze_flow.py \
        --data alternative/options_flow/data/options_flow.json \
        --output alternative/options_flow/output/flow_alerts.json

    if [[ -f "alternative/options_flow/output/flow_alerts.json" ]]; then
        print_success "Alerts saved to: alternative/options_flow/output/flow_alerts.json"
    fi
}

run_options_flow_workflow() {
    print_header "Options Flow - Full Workflow"

    echo -e "${YELLOW}Enter tickers (comma-separated, default: AAPL,NVDA,TSLA):${NC}"
    read -r tickers
    tickers="${tickers:-AAPL,NVDA,TSLA}"

    tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]' | tr ',' ' ')

    # Step 1: Fetch data
    print_info "Step 1/2: Fetching options flow data..."
    .venv/bin/python3 alternative/options_flow/python/fetch_flow.py \
        $tickers \
        --output alternative/options_flow/data/options_flow.json

    if [[ ! -f "alternative/options_flow/data/options_flow.json" ]]; then
        print_error "Failed to fetch options flow data"
        return 1
    fi
    print_success "Data fetched"

    # Step 2: Analyze
    print_info "Step 2/2: Analyzing flow..."
    .venv/bin/python3 alternative/options_flow/python/analyze_flow.py \
        --data alternative/options_flow/data/options_flow.json \
        --output alternative/options_flow/output/flow_alerts.json

    if [[ -f "alternative/options_flow/output/flow_alerts.json" ]]; then
        print_success "Alerts saved to: alternative/options_flow/output/flow_alerts.json"
    fi

    print_success "Full workflow complete!"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Short Interest
# ═══════════════════════════════════════════════════════════════════════════════

show_short_interest_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Short Interest ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Fetch Short Interest Data"
        echo -e "${GREEN}2)${NC} Analyze Short Interest"
        echo -e "${GREEN}3)${NC} Run Full Workflow"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Monitoring & Alternative Data"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_short_interest ;;
            2) analyze_short_interest ;;
            3|"") run_short_interest_workflow ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_short_interest() {
    print_header "Fetch Short Interest Data"

    echo -e "${YELLOW}Enter tickers (comma-separated, default: AAPL,NVDA,TSLA):${NC}"
    read -r tickers
    tickers="${tickers:-AAPL,NVDA,TSLA}"

    tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]' | tr ',' ' ')

    .venv/bin/python3 alternative/short_interest/python/fetch_short_interest.py \
        $tickers \
        --output alternative/short_interest/data/short_interest.json

    if [[ -f "alternative/short_interest/data/short_interest.json" ]]; then
        print_success "Data saved to: alternative/short_interest/data/short_interest.json"
    else
        print_error "Failed to fetch short interest data"
    fi
}

analyze_short_interest() {
    print_header "Analyze Short Interest"

    if [[ ! -f "alternative/short_interest/data/short_interest.json" ]]; then
        print_error "No data found. Run 'Fetch Short Interest Data' first."
        return 1
    fi

    .venv/bin/python3 alternative/short_interest/python/analyze_shorts.py \
        --data alternative/short_interest/data/short_interest.json \
        --output alternative/short_interest/output/short_alerts.json

    if [[ -f "alternative/short_interest/output/short_alerts.json" ]]; then
        print_success "Alerts saved to: alternative/short_interest/output/short_alerts.json"
    fi
    if [[ -f "alternative/short_interest/output/squeeze_candidates.json" ]]; then
        print_success "Squeeze candidates: alternative/short_interest/output/squeeze_candidates.json"
    fi
}

run_short_interest_workflow() {
    print_header "Short Interest - Full Workflow"

    echo -e "${YELLOW}Enter tickers (comma-separated, default: AAPL,NVDA,TSLA):${NC}"
    read -r tickers
    tickers="${tickers:-AAPL,NVDA,TSLA}"

    tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]' | tr ',' ' ')

    # Step 1: Fetch data
    print_info "Step 1/2: Fetching short interest data..."
    .venv/bin/python3 alternative/short_interest/python/fetch_short_interest.py \
        $tickers \
        --output alternative/short_interest/data/short_interest.json

    if [[ ! -f "alternative/short_interest/data/short_interest.json" ]]; then
        print_error "Failed to fetch short interest data"
        return 1
    fi
    print_success "Data fetched"

    # Step 2: Analyze
    print_info "Step 2/2: Analyzing short interest..."
    .venv/bin/python3 alternative/short_interest/python/analyze_shorts.py \
        --data alternative/short_interest/data/short_interest.json \
        --output alternative/short_interest/output/short_alerts.json

    if [[ -f "alternative/short_interest/output/short_alerts.json" ]]; then
        print_success "Alerts saved to: alternative/short_interest/output/short_alerts.json"
    fi
    if [[ -f "alternative/short_interest/output/squeeze_candidates.json" ]]; then
        print_success "Squeeze candidates: alternative/short_interest/output/squeeze_candidates.json"
    fi

    print_success "Full workflow complete!"
}

# ═══════════════════════════════════════════════════════════════════════════════
# NLP Sentiment (Narrative Drift)
# ═══════════════════════════════════════════════════════════════════════════════

show_nlp_sentiment_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ NLP Sentiment (Narrative Drift) ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Run Full Pipeline"
        echo "   (Fetch MD&A + Transcripts, Embed, Detect Changes, Surface Signals)"
        echo ""
        echo -e "${YELLOW}─── Discord Integration ───${NC}"
        echo ""
        echo -e "${GREEN}2)${NC} Import Discord Export (DiscordChatExporter)"
        echo "   (Import JSON exports - no bot required)"
        echo ""
        echo -e "${GREEN}3)${NC} Run FinBERT Analysis on Discord Data"
        echo "   (Deep sentiment analysis using transformer model)"
        echo ""
        echo -e "${GREEN}4)${NC} Run Enhanced Analysis (Temporal + Aspects + Entity Linking)"
        echo "   (Track sentiment shifts, WHY bullish/bearish, company names)"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Monitoring & Alternative Data"
        echo ""
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) run_nlp_sentiment_pipeline ;;
            2) import_discord_export ;;
            3) run_finbert_analysis ;;
            4) run_enhanced_analysis ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

# Systematic Risk Signals menu
show_systematic_risk_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Systematic Risk Signals ═══${NC}\n"
        echo "Early-warning signals for systematic risk based on graph theory"
        echo "and covariance eigenvalue analysis (Ciciretti et al. 2025 QF)."
        echo ""
        echo "Four risk signals computed:"
        echo "  1. Variance explained by largest eigenvalue (λ₁)"
        echo "  2. Variance explained by eigenvalues 2-5 (λ₂₋₅)"
        echo "  3. Mean eigenvector centrality from MST"
        echo "  4. Std dev of eigenvector centrality from MST"
        echo ""
        echo -e "${GREEN}1)${NC} Run Analysis (Market ETFs: SPY, QQQ, IWM, EFA, AGG, GLD)"
        echo ""
        echo -e "${GREEN}2)${NC} Run Analysis (Custom Tickers)"
        echo ""
        echo -e "${GREEN}3)${NC} View Last Result"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Monitoring & Alternative Data"
        echo ""
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) run_systematic_risk_default ;;
            2) run_systematic_risk_custom ;;
            3) view_systematic_risk_result ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

run_systematic_risk_default() {
    print_header "Systematic Risk Signals - Default ETFs"

    local tickers="SPY,QQQ,IWM,EFA,AGG,GLD"
    print_info "Analyzing: $tickers"

    # Build if needed
    if ! opam exec -- dune build pricing/systematic_risk_signals/ocaml/bin/main.exe > /dev/null 2>&1; then
        print_error "Failed to build systematic_risk_signals"
        return 1
    fi

    # Fetch data
    print_info "Fetching historical returns..."
    .venv/bin/python3 pricing/systematic_risk_signals/python/fetch/fetch_returns.py \
        --tickers "$tickers" --lookback 252

    # Run analysis
    print_info "Computing risk signals..."
    opam exec -- dune exec pricing/systematic_risk_signals/ocaml/bin/main.exe -- \
        --data pricing/systematic_risk_signals/data/returns.json

    echo ""
    echo -e "${GREEN}Analysis complete.${NC}"
}

run_systematic_risk_custom() {
    print_header "Systematic Risk Signals - Custom Tickers"

    echo -e "${YELLOW}Enter comma-separated tickers (min 4 recommended):${NC}"
    read -r tickers

    if [[ -z "$tickers" ]]; then
        print_error "No tickers provided."
        return 1
    fi

    print_info "Analyzing: $tickers"

    # Build if needed
    if ! opam exec -- dune build pricing/systematic_risk_signals/ocaml/bin/main.exe > /dev/null 2>&1; then
        print_error "Failed to build systematic_risk_signals"
        return 1
    fi

    # Fetch data
    print_info "Fetching historical returns..."
    .venv/bin/python3 pricing/systematic_risk_signals/python/fetch/fetch_returns.py \
        --tickers "$tickers" --lookback 252

    # Run analysis
    print_info "Computing risk signals..."
    opam exec -- dune exec pricing/systematic_risk_signals/ocaml/bin/main.exe -- \
        --data pricing/systematic_risk_signals/data/returns.json

    echo ""
    echo -e "${GREEN}Analysis complete.${NC}"
}

view_systematic_risk_result() {
    local data_file="pricing/systematic_risk_signals/data/returns.json"
    if [[ ! -f "$data_file" ]]; then
        print_error "No previous analysis found. Run analysis first."
        return 1
    fi

    opam exec -- dune exec pricing/systematic_risk_signals/ocaml/bin/main.exe -- \
        --data "$data_file"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Macro Dashboard
# ═══════════════════════════════════════════════════════════════════════════════

show_macro_dashboard_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Macro Dashboard ═══${NC}\n"
        echo "Quick macro environment snapshot: rates, inflation, employment, growth."
        echo "Classifies cycle phase, Fed stance, recession probability."
        echo ""
        echo -e "${DIM}Note: Requires FRED API key for full data (free at fred.stlouisfed.org)${NC}"
        echo -e "${DIM}      Without API key, only market data (VIX, S&P, etc.) is fetched${NC}"
        echo ""
        echo -e "${GREEN}1)${NC} Fetch Macro Data"
        echo -e "${GREEN}2)${NC} View Dashboard (from cached data)"
        echo -e "${GREEN}3)${NC} Full Workflow (Fetch + Analyze)"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Monitoring & Alternative Data"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_macro_data ;;
            2) view_macro_dashboard ;;
            3|"") run_macro_workflow ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_macro_data() {
    print_header "Fetch Macro Data"

    # Check for FRED API key
    if [[ -z "$FRED_API_KEY" ]]; then
        print_warning "FRED_API_KEY not set. Will fetch market data only."
        echo "For full macro data, get a free key at: https://fred.stlouisfed.org/docs/api/api_key.html"
        echo "Then add to .env: FRED_API_KEY=your_key_here"
        echo ""
    fi

    print_info "Fetching macro data..."

    uv run alternative/macro_dashboard/python/fetch/fetch_macro.py \
        --output data/macro_data.json

    if [[ -f alternative/macro_dashboard/data/macro_data.json ]]; then
        print_success "Macro data saved to alternative/macro_dashboard/data/macro_data.json"
    else
        print_error "Failed to fetch macro data"
    fi
}

view_macro_dashboard() {
    print_header "Macro Dashboard"

    local data_file="alternative/macro_dashboard/data/macro_data.json"
    if [[ ! -f "$data_file" ]]; then
        print_error "No macro data found. Run 'Fetch Macro Data' first."
        return 1
    fi

    # Build if needed
    if ! opam exec -- dune build alternative/macro_dashboard/ocaml/bin/main.exe > /dev/null 2>&1; then
        print_error "Failed to build macro_dashboard"
        return 1
    fi

    opam exec -- dune exec alternative/macro_dashboard/ocaml/bin/main.exe -- "$data_file"
}

run_macro_workflow() {
    print_header "Full Macro Workflow"

    # Step 1: Fetch data
    print_info "Step 1/2: Fetching macro data..."
    fetch_macro_data

    # Step 2: Analyze
    print_info "Step 2/2: Analyzing environment..."
    view_macro_dashboard

    print_success "Macro workflow complete!"
}

run_finbert_analysis() {
    print_header "FinBERT Sentiment Analysis"

    local data_dir="alternative/nlp_sentiment/data/discord"

    # Check if Discord data exists
    if [[ ! -d "$data_dir/combined" ]]; then
        print_error "No Discord data found. Import Discord exports first (option 2)."
        return 1
    fi

    local messages_file="$data_dir/combined/discord_messages.json"
    if [[ ! -f "$messages_file" ]]; then
        print_error "No messages file found at: $messages_file"
        return 1
    fi

    local msg_count=$(python3 -c "import json; print(len(json.load(open('$messages_file'))))")
    print_info "Found $msg_count messages to analyze"

    echo ""
    echo -e "${YELLOW}Analysis options:${NC}"
    echo -e "${GREEN}1)${NC} Analyze combined data (all channels)"
    echo -e "${GREEN}2)${NC} Analyze specific channel"
    echo ""
    echo -e "${YELLOW}Enter choice (default: 1):${NC}"
    read -r analysis_choice
    analysis_choice=${analysis_choice:-1}

    local input_file="$messages_file"
    local output_file="$data_dir/combined/finbert_analysis.json"

    if [[ "$analysis_choice" == "2" ]]; then
        echo ""
        echo "Available channels:"
        ls -d "$data_dir"/*/ 2>/dev/null | grep -v combined | xargs -I{} basename {}
        echo ""
        echo -e "${YELLOW}Enter channel name:${NC}"
        read -r channel_name

        if [[ -z "$channel_name" ]]; then
            print_error "No channel specified"
            return 1
        fi

        input_file="$data_dir/$channel_name/discord_messages.json"
        output_file="$data_dir/$channel_name/finbert_analysis.json"

        if [[ ! -f "$input_file" ]]; then
            print_error "Channel data not found: $input_file"
            return 1
        fi
    fi

    echo ""
    echo -e "${YELLOW}Batch size for inference (default: 16):${NC}"
    read -r batch_size
    batch_size=${batch_size:-16}

    print_info "Running FinBERT analysis (this may take a few minutes on CPU)..."
    echo ""

    .venv/bin/python3 alternative/nlp_sentiment/python/fetch/finbert_analyzer.py \
        "$input_file" \
        --output "$output_file" \
        --batch-size "$batch_size"

    if [[ -f "$output_file" ]]; then
        print_success "Analysis saved to: $output_file"
    fi
}

run_enhanced_analysis() {
    print_header "Enhanced NLP Analysis"

    local data_dir="alternative/nlp_sentiment/data/discord"

    # Check if Discord data exists
    if [[ ! -d "$data_dir/combined" ]]; then
        print_error "No Discord data found. Import Discord exports first (option 2)."
        return 1
    fi

    local messages_file="$data_dir/combined/discord_messages.json"
    if [[ ! -f "$messages_file" ]]; then
        print_error "No messages file found at: $messages_file"
        return 1
    fi

    local msg_count=$(python3 -c "import json; print(len(json.load(open('$messages_file'))))")
    print_info "Found $msg_count messages to analyze"

    echo ""
    echo -e "${BLUE}Enhanced Analysis includes:${NC}"
    echo "  - Temporal Analysis: Track sentiment shifts over time"
    echo "  - Aspect Detection: WHY bullish/bearish (management, product, valuation, growth)"
    echo "  - Entity Linking: Map company names to tickers"
    echo ""

    echo -e "${YELLOW}Time window size in hours (default: 24):${NC}"
    read -r window_hours
    window_hours=${window_hours:-24}

    local output_file="$data_dir/combined/enhanced_analysis.json"

    print_info "Running enhanced analysis..."
    echo ""

    .venv/bin/python3 alternative/nlp_sentiment/python/fetch/enhanced_analysis.py \
        --input "$messages_file" \
        --output "$output_file" \
        --window-hours "$window_hours"

    if [[ -f "$output_file" ]]; then
        print_success "Enhanced analysis saved to: $output_file"
    fi
}

run_nlp_sentiment_pipeline() {
    print_header "NLP Sentiment - Full Pipeline"

    echo -e "${YELLOW}Enter tickers (comma-separated):${NC}"
    read -r tickers

    if [[ -z "$tickers" ]]; then
        print_error "At least one ticker is required"
        return 1
    fi

    tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]' | tr ',' ' ')

    echo -e "${YELLOW}Number of quarters to analyze (default: 12):${NC}"
    read -r quarters
    quarters=${quarters:-12}

    print_info "Running NLP pipeline (this may take a while)..."
    .venv/bin/python3 alternative/nlp_sentiment/python/pipeline.py \
        $tickers \
        --quarters "$quarters" \
        --output alternative/nlp_sentiment/output

    if [[ -f "alternative/nlp_sentiment/output/signals.csv" ]]; then
        print_success "Signals saved to: alternative/nlp_sentiment/output/signals.csv"
    fi
    if [[ -f "alternative/nlp_sentiment/output/summary.md" ]]; then
        print_success "Summary saved to: alternative/nlp_sentiment/output/summary.md"
    fi

    print_success "Pipeline complete!"
}

import_discord_export() {
    print_header "Import Discord Export (DiscordChatExporter)"

    echo -e "${BLUE}This imports JSON exports from DiscordChatExporter.${NC}"
    echo ""
    echo "Download DiscordChatExporter from:"
    echo "  https://github.com/Tyrrrz/DiscordChatExporter/releases"
    echo ""
    echo "Export command (CLI):"
    echo "  ./DiscordChatExporter.Cli export -t \"USER_TOKEN\" -c CHANNEL_ID -f Json"
    echo ""
    echo "To get your user token:"
    echo "  1. Open Discord in browser"
    echo "  2. Open DevTools (F12) > Network tab"
    echo "  3. Filter by 'api'"
    echo "  4. Look at request headers for 'Authorization'"
    echo ""

    local export_dir="alternative/nlp_sentiment/data/discord_exports"

    echo -e "${YELLOW}Enter path to JSON export file or directory:${NC}"
    echo -e "${BLUE}(default: $export_dir)${NC}"
    read -r input_path

    if [[ -z "$input_path" ]]; then
        input_path="$export_dir"
    fi

    if [[ ! -e "$input_path" ]]; then
        print_error "Path not found: $input_path"
        echo ""
        echo "Create the directory and add your exported JSON files:"
        echo "  mkdir -p $export_dir"
        echo "  cp your_export.json $export_dir/"
        return 1
    fi

    echo -e "${YELLOW}Filter by tickers? (comma-separated, or press Enter for all):${NC}"
    read -r tickers

    echo -e "${YELLOW}Days of history to include? (press Enter for all):${NC}"
    read -r days

    print_info "Importing Discord exports..."

    # Convert relative path to absolute for subshell
    local root_dir="$(pwd)"
    if [[ ! "$input_path" = /* ]]; then
        input_path="$root_dir/$input_path"
    fi

    local fetch_dir="alternative/nlp_sentiment/python/fetch"
    local cmd="$root_dir/.venv/bin/python3 import_discord_export.py"

    if [[ -d "$input_path" ]]; then
        cmd="$cmd --dir \"$input_path\""
    else
        cmd="$cmd \"$input_path\""
    fi

    if [[ -n "$tickers" ]]; then
        tickers=$(echo "$tickers" | tr '[:lower:]' '[:upper:]' | tr ',' ' ')
        cmd="$cmd --tickers $tickers"
    fi

    if [[ -n "$days" ]]; then
        cmd="$cmd --days $days"
    fi

    (cd "$fetch_dir" && eval "$cmd")

    if [[ -d "alternative/nlp_sentiment/data/discord" ]]; then
        print_success "Discord data imported to: alternative/nlp_sentiment/data/discord/"
        echo ""
        echo "Files created:"
        ls -la alternative/nlp_sentiment/data/discord/
    fi
}

# Load environment configuration
setup_env() {
    if [[ -f ".env" ]]; then
        set -a
        source .env
        set +a
        print_success "Loaded environment from .env"
    elif [[ -f ".env.example" ]]; then
        print_warning "No .env file found"
        echo -e "${YELLOW}Would you like to create one from .env.example? [Y/n]${NC} "
        read -r yn
        if [[ "$yn" != "n" && "$yn" != "N" ]]; then
            cp .env.example .env
            print_success "Created .env from .env.example"
            print_info "Edit .env to set your values (SEC_EDGAR_IDENTITY, FRED_API_KEY, etc.)"
            # Find available editors
            local editors=()
            for e in vim nano emacs code; do
                command -v "$e" &>/dev/null && editors+=("$e")
            done
            if [[ ${#editors[@]} -gt 0 ]]; then
                local editor_list=$(IFS=', '; echo "${editors[*]}")
                echo -e "${YELLOW}Open .env in an editor now? Available: ${editor_list} [Enter=skip]${NC} "
                read -r chosen_editor
                if [[ -n "$chosen_editor" ]] && command -v "$chosen_editor" &>/dev/null; then
                    "$chosen_editor" .env
                elif [[ -n "$chosen_editor" ]]; then
                    print_warning "$chosen_editor not found, skipping"
                fi
            fi
            set -a
            source .env
            set +a
            print_success "Loaded environment from .env"
        else
            print_info "Continuing without .env (using defaults)"
        fi
    fi
}

# Main loop
main() {
    check_project_root
    setup_env

    while true; do
        show_main_menu
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) show_installation_menu ;;
            2) show_maintenance_menu ;;
            3) show_run_menu ;;
            0)
                clear
                echo ""
                print_info "Goodbye!"
                echo ""
                exit 0
                ;;
            *)
                print_error "Invalid choice. Please enter 1-3 or 0."
                ;;
        esac
    done
}

show_skew_trading_menu() {
    while true; do
        clear
        echo -e "${BLUE}═══ Skew Trading ═══${NC}\n"
        echo -e "${DIM}Daily snapshots accept liquid tickers from Liquidity module (option 8)${NC}"
        echo ""
        echo -e "${GREEN}1)${NC} Fetch Market Data"
        echo -e "${GREEN}2)${NC} Measure Skew (RR25, BF25)"
        echo -e "${GREEN}3)${NC} Generate Trading Signal"
        echo -e "${GREEN}4)${NC} Build Skew Position"
        echo -e "${GREEN}5)${NC} Backtest Strategy"
        echo -e "${GREEN}6)${NC} Visualize Results"
        echo -e "${GREEN}7)${NC} Run Full Workflow"
        echo -e "${GREEN}8)${NC} Collect Daily Snapshot"
        echo -e "${GREEN}9)${NC} Scan Signals (z-score watchlist)"
        echo -e "${GREEN}0)${NC} Back to Pricing Menu"
        echo ""
        echo -e "${DIM}Tip: Install a daily cron job to collect vol surface snapshots automatically.${NC}"
        echo -e "${DIM}See pricing/skew_trading/README.md → Daily Collection for setup instructions.${NC}"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_skew_data ;;
            2) measure_skew ;;
            3) generate_skew_signal ;;
            4) build_skew_position ;;
            5) backtest_skew_strategy ;;
            6) visualize_skew_results ;;
            7|"") run_skew_full_workflow ;;
            8) collect_skew_snapshot ;;
            9) scan_skew_signals ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_skew_data() {
    print_header "Fetch Market Data for Skew Trading"

    read_ticker "Enter ticker symbol (default: TSLA):" "TSLA"

    read -p "Enter lookback days (default: 252): " lookback
    lookback=${lookback:-252}

    print_info "Fetching data for $ticker..."

    # Fetch underlying
    uv run pricing/skew_trading/python/fetch/fetch_underlying.py \
        --ticker "$ticker" \
        --output-dir pricing/skew_trading/data \
        --lookback "$lookback"

    # Fetch options and calibrate SVI
    uv run pricing/skew_trading/python/fetch/fetch_options.py \
        --ticker "$ticker" \
        --output-dir pricing/skew_trading/data

    # Compute skew timeseries
    uv run pricing/skew_trading/python/fetch/compute_skew_timeseries.py \
        --ticker "$ticker" \
        --data-dir pricing/skew_trading/data

    if [[ -f "pricing/skew_trading/data/${ticker}_skew_timeseries.csv" ]]; then
        print_success "Data fetched successfully:"
        print_success "  Underlying: pricing/skew_trading/data/${ticker}_underlying.json"
        print_success "  Vol surface: pricing/skew_trading/data/${ticker}_vol_surface.json"
        print_success "  Skew timeseries: pricing/skew_trading/data/${ticker}_skew_timeseries.csv"
    else
        print_error "Failed to fetch data for $ticker"
    fi
}

measure_skew() {
    print_header "Measure Volatility Skew"

    read_ticker "Enter ticker symbol (default: TSLA):" "TSLA"

    read -p "Enter expiry days (default: 30): " expiry
    expiry=${expiry:-30}

    print_info "Measuring skew for $ticker (${expiry}d expiry)..."

    opam exec -- dune exec skew_trading -- \
        -ticker "$ticker" \
        -op measure \
        -expiry "$expiry"

    if [[ -f "pricing/skew_trading/output/${ticker}_skew.csv" ]]; then
        print_success "Skew measurements: pricing/skew_trading/output/${ticker}_skew.csv"

        # Display results
        if command -v column &> /dev/null; then
            echo ""
            print_info "Skew Metrics:"
            column -t -s',' pricing/skew_trading/output/${ticker}_skew.csv
        fi
    else
        print_error "Failed to measure skew for $ticker"
    fi
}

generate_skew_signal() {
    print_header "Generate Skew Trading Signal"

    read_ticker "Enter ticker symbol (default: TSLA):" "TSLA"

    print_info "Generating mean reversion signal for $ticker..."

    opam exec -- dune exec skew_trading -- \
        -ticker "$ticker" \
        -op signal

    if [[ -f "pricing/skew_trading/output/${ticker}_signal.csv" ]]; then
        print_success "Signal generated: pricing/skew_trading/output/${ticker}_signal.csv"

        # Display results
        if command -v column &> /dev/null; then
            echo ""
            print_info "Trading Signal:"
            column -t -s',' pricing/skew_trading/output/${ticker}_signal.csv
        fi
    else
        print_error "Failed to generate signal for $ticker"
    fi
}

build_skew_position() {
    print_header "Build Skew Position"

    read_ticker "Enter ticker symbol (default: TSLA):" "TSLA"

    read -p "Enter expiry days (default: 30): " expiry
    expiry=${expiry:-30}

    read -p "Enter vega notional (default: 10000): " notional
    notional=${notional:-10000}

    print_info "Building risk reversal position for $ticker..."

    opam exec -- dune exec skew_trading -- \
        -ticker "$ticker" \
        -op position \
        -expiry "$expiry" \
        -notional "$notional"

    if [[ -f "pricing/skew_trading/output/${ticker}_position.csv" ]]; then
        print_success "Position built: pricing/skew_trading/output/${ticker}_position.csv"

        # Display results
        if command -v column &> /dev/null; then
            echo ""
            print_info "Position Details:"
            column -t -s',' pricing/skew_trading/output/${ticker}_position.csv
        fi
    else
        print_error "Failed to build position for $ticker"
    fi
}

backtest_skew_strategy() {
    print_header "Backtest Skew Mean Reversion Strategy"

    read_ticker "Enter ticker symbol (default: TSLA):" "TSLA"

    print_info "Backtesting strategy for $ticker..."

    opam exec -- dune exec skew_trading -- \
        -ticker "$ticker" \
        -op backtest

    if [[ -f "pricing/skew_trading/output/${ticker}_backtest.csv" ]]; then
        print_success "Backtest complete: pricing/skew_trading/output/${ticker}_backtest.csv"

        # Display final results
        if command -v tail &> /dev/null && command -v column &> /dev/null; then
            echo ""
            print_info "Final P&L:"
            tail -1 pricing/skew_trading/output/${ticker}_backtest.csv | column -t -s','
        fi
    else
        print_error "Failed to backtest strategy for $ticker"
    fi
}

visualize_skew_results() {
    print_header "Visualize Skew Trading Results"

    read_ticker "Enter ticker symbol (default: TSLA):" "TSLA"

    print_info "Generating visualizations for $ticker..."

    # Volatility smile
    if [[ -f "pricing/skew_trading/data/${ticker}_vol_surface.json" ]]; then
        uv run pricing/skew_trading/python/viz/plot_smile.py \
            --ticker "$ticker" \
            --data-dir pricing/skew_trading/data \
            --output-dir pricing/skew_trading/output
    fi

    # Skew timeseries
    if [[ -f "pricing/skew_trading/data/${ticker}_skew_timeseries.csv" ]]; then
        uv run pricing/skew_trading/python/viz/plot_skew_ts.py \
            --ticker "$ticker" \
            --data-dir pricing/skew_trading/data \
            --output-dir pricing/skew_trading/output
    fi

    # Backtest P&L
    if [[ -f "pricing/skew_trading/output/${ticker}_backtest.csv" ]]; then
        uv run pricing/skew_trading/python/viz/plot_pnl.py \
            --ticker "$ticker" \
            --data-dir pricing/skew_trading/output \
            --output-dir pricing/skew_trading/output
    fi

    if [[ -f "pricing/skew_trading/output/${ticker}_vol_smile.png" ]] || \
       [[ -f "pricing/skew_trading/output/${ticker}_skew_timeseries.png" ]] || \
       [[ -f "pricing/skew_trading/output/${ticker}_backtest_pnl.png" ]]; then
        print_success "Visualizations saved to: pricing/skew_trading/output/"
    else
        print_error "Failed to generate visualizations"
    fi
}

collect_skew_snapshot() {
    print_header "Collect Daily Vol Surface Snapshot"

    pick_ticker_source "TSLA" || return

    print_info "Collecting vol surface snapshot..."
    print_info "This fetches the current option chain, calibrates SVI, and archives the raw market surface."

    uv run pricing/skew_trading/python/fetch/collect_snapshot.py \
        --tickers "$ticker_arg" \
        --data-dir pricing/skew_trading/data

    if [ $? -eq 0 ]; then
        print_success "Snapshot collected"
        print_info "Snapshots: pricing/skew_trading/data/snapshots/"
    else
        print_error "Snapshot collection failed"
    fi

    if [[ "$ticker_arg" == "all_liquid" || "$ticker_arg" == *.txt ]]; then
        echo ""
        echo -e "${YELLOW}Jump to:${NC}  ${GREEN}v)${NC} Variance Swaps  ${GREEN}e)${NC} Pre-Earnings  ${GREEN}l)${NC} Liquidity  ${GREEN}Enter)${NC} Stay"
        read -r jump
        case $jump in
            v) show_variance_swaps_menu ;;
            e) show_pre_earnings_straddle_menu ;;
            l) show_liquidity_menu ;;
        esac
    fi
}

scan_skew_signals() {
    print_header "Scan Skew Signals (z-score watchlist)"

    echo -e "${GREEN}1)${NC} Overall ranking (all tickers)"
    echo -e "${GREEN}2)${NC} By price segment"
    echo ""
    echo -e "${YELLOW}Enter your choice (Enter=By segment):${NC} "
    read -r scan_choice

    local scan_args="--quiet"
    case $scan_choice in
        1) ;;
        2|"") scan_args="$scan_args --segments" ;;
        *) scan_args="$scan_args --segments" ;;
    esac

    read -p "Min days of history (default: 5): " min_days
    min_days=${min_days:-5}

    print_info "Scanning skew histories..."

    uv run pricing/skew_trading/python/scan_signals.py \
        $scan_args \
        --min-days "$min_days" \
        --output pricing/skew_trading/output/signal_scan.csv

    if [ $? -eq 0 ]; then
        print_success "Scan complete"
        print_info "Results: pricing/skew_trading/output/signal_scan.csv"

        echo ""
        echo -e "${YELLOW}Build position for a ticker? Enter ticker or press Enter to skip:${NC} "
        read -r pos_ticker
        if [[ -n "$pos_ticker" ]]; then
            # Determine direction and strategy from scan results
            local signal
            signal=$(grep "^${pos_ticker}," pricing/skew_trading/output/signal_scan.csv 2>/dev/null | cut -d',' -f3)
            local direction="long"
            local strat="rr"
            if [[ "$signal" == *"SHORT"* ]]; then
                direction="short"
            fi
            if [[ "$signal" == *"WINGS"* ]]; then
                strat="butterfly"
            fi
            print_info "Building $direction $strat for $pos_ticker (signal: $signal)..."
            opam exec -- dune exec skew_trading -- \
                -ticker "$pos_ticker" \
                -op position \
                -direction "$direction" \
                -strategy "$strat"
        fi
    else
        print_error "Scan failed"
    fi
}

run_skew_full_workflow() {
    print_header "Skew Trading - Full Workflow"

    read_ticker "Enter ticker symbol (default: TSLA):" "TSLA"

    read -p "Enter expiry days (default: 30): " expiry
    expiry=${expiry:-30}

    print_info "Running full skew trading workflow for $ticker..."

    # Step 1: Fetch data
    print_info "Step 1/6: Fetching market data..."
    uv run pricing/skew_trading/python/fetch/fetch_underlying.py \
        --ticker "$ticker" \
        --output-dir pricing/skew_trading/data

    uv run pricing/skew_trading/python/fetch/fetch_options.py \
        --ticker "$ticker" \
        --output-dir pricing/skew_trading/data

    uv run pricing/skew_trading/python/fetch/compute_skew_timeseries.py \
        --ticker "$ticker" \
        --data-dir pricing/skew_trading/data \
        --expiry "$expiry"

    # Step 2: Measure skew
    print_info "Step 2/6: Measuring skew..."
    opam exec -- dune exec skew_trading -- \
        -ticker "$ticker" \
        -op measure \
        -expiry "$expiry"

    # Step 3: Generate signal
    print_info "Step 3/6: Generating trading signal..."
    opam exec -- dune exec skew_trading -- \
        -ticker "$ticker" \
        -op signal

    # Step 4: Build position
    print_info "Step 4/6: Building skew position..."
    opam exec -- dune exec skew_trading -- \
        -ticker "$ticker" \
        -op position \
        -expiry "$expiry"

    # Step 5: Backtest
    print_info "Step 5/6: Backtesting strategy..."
    opam exec -- dune exec skew_trading -- \
        -ticker "$ticker" \
        -op backtest

    # Step 6: Visualize
    print_info "Step 6/6: Generating visualizations..."
    uv run pricing/skew_trading/python/viz/plot_smile.py \
        --ticker "$ticker" \
        --data-dir pricing/skew_trading/data \
        --output-dir pricing/skew_trading/output

    uv run pricing/skew_trading/python/viz/plot_skew_ts.py \
        --ticker "$ticker" \
        --data-dir pricing/skew_trading/data \
        --output-dir pricing/skew_trading/output

    uv run pricing/skew_trading/python/viz/plot_pnl.py \
        --ticker "$ticker" \
        --data-dir pricing/skew_trading/output \
        --output-dir pricing/skew_trading/output

    print_success "Full workflow complete for $ticker"
    print_info "Results in: pricing/skew_trading/output/"
}

# Gamma Scalping operations
show_gamma_scalping_menu() {
    while true; do
        clear
        echo -e "${BLUE}═══ Gamma Scalping ═══${NC}\n"
        echo -e "${GREEN}1)${NC} Fetch Intraday Data"
        echo -e "${GREEN}2)${NC} Run Simulation (Straddle)"
        echo -e "${GREEN}3)${NC} Run Simulation (Strangle)"
        echo -e "${GREEN}4)${NC} Visualize P&L"
        echo -e "${GREEN}5)${NC} Run Full Workflow"
        echo -e "${GREEN}0)${NC} Back to Pricing Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_gamma_intraday_data ;;
            2) run_gamma_simulation_straddle ;;
            3) run_gamma_simulation_strangle ;;
            4) visualize_gamma_pnl ;;
            5|"") run_gamma_full_workflow ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_gamma_intraday_data() {
    print_header "Fetch Intraday Data for Gamma Scalping"

    read_ticker "Enter ticker symbol (default: SPY):" "SPY"

    read -p "Enter days of history (default: 5): " days
    days=${days:-5}

    print_info "Fetching intraday data for $ticker..."

    uv run pricing/gamma_scalping/python/fetch/fetch_intraday.py \
        --ticker "$ticker" \
        --days "$days"

    if [[ -f "pricing/gamma_scalping/data/${ticker}_intraday.csv" ]]; then
        print_success "Intraday data saved to: pricing/gamma_scalping/data/${ticker}_intraday.csv"

        # Show sample
        echo ""
        print_info "Sample (first 5 rows):"
        head -6 "pricing/gamma_scalping/data/${ticker}_intraday.csv"
    else
        print_error "Failed to fetch intraday data for $ticker"
    fi
}

run_gamma_simulation_straddle() {
    print_header "Run Gamma Scalping Simulation - Straddle"

    read_ticker "Enter ticker symbol (default: SPY):" "SPY"

    read -p "Enter strike (0 = ATM, default: 0): " strike
    strike=${strike:-0}

    read -p "Enter days to expiry (default: 30): " expiry
    expiry=${expiry:-30}

    read -p "Enter entry IV (default: 0.20): " iv
    iv=${iv:-0.20}

    read -p "Enter hedging strategy (threshold|time|hybrid|vol-adaptive, default: threshold): " strategy
    strategy=${strategy:-threshold}

    read -p "Enter delta threshold for rehedging (default: 0.10): " threshold
    threshold=${threshold:-0.10}

    print_info "Running gamma scalping simulation for $ticker straddle..."

    opam exec -- dune exec gamma_scalping -- \
        -ticker "$ticker" \
        -position straddle \
        -strike "$strike" \
        -expiry "$expiry" \
        -iv "$iv" \
        -strategy "$strategy" \
        -threshold "$threshold"

    if [[ -f "pricing/gamma_scalping/output/${ticker}_simulation.csv" ]]; then
        print_success "Simulation complete: pricing/gamma_scalping/output/${ticker}_simulation.csv"
    else
        print_error "Simulation failed for $ticker"
    fi
}

run_gamma_simulation_strangle() {
    print_header "Run Gamma Scalping Simulation - Strangle"

    read_ticker "Enter ticker symbol (default: SPY):" "SPY"

    read -p "Enter call strike (0 = ATM+5%, default: 0): " call_strike
    call_strike=${call_strike:-0}

    read -p "Enter put strike (0 = ATM-5%, default: 0): " put_strike
    put_strike=${put_strike:-0}

    read -p "Enter days to expiry (default: 30): " expiry
    expiry=${expiry:-30}

    read -p "Enter entry IV (default: 0.20): " iv
    iv=${iv:-0.20}

    read -p "Enter hedging strategy (threshold|time|hybrid|vol-adaptive, default: threshold): " strategy
    strategy=${strategy:-threshold}

    print_info "Running gamma scalping simulation for $ticker strangle..."

    opam exec -- dune exec gamma_scalping -- \
        -ticker "$ticker" \
        -position strangle \
        -call-strike "$call_strike" \
        -put-strike "$put_strike" \
        -expiry "$expiry" \
        -iv "$iv" \
        -strategy "$strategy"

    if [[ -f "pricing/gamma_scalping/output/${ticker}_simulation.csv" ]]; then
        print_success "Simulation complete: pricing/gamma_scalping/output/${ticker}_simulation.csv"
    else
        print_error "Simulation failed for $ticker"
    fi
}

visualize_gamma_pnl() {
    print_header "Visualize Gamma Scalping P&L"

    read_ticker "Enter ticker symbol (default: SPY):" "SPY"

    print_info "Generating P&L visualization for $ticker..."

    uv run pricing/gamma_scalping/python/viz/plot_pnl.py \
        --ticker "$ticker"

    if [[ -f "pricing/gamma_scalping/output/plots/${ticker}_pnl_attribution.png" ]]; then
        print_success "Plots saved to: pricing/gamma_scalping/output/plots/"
        ls -lh pricing/gamma_scalping/output/plots/${ticker}_*.png 2>/dev/null || true
    else
        print_error "Failed to generate plots for $ticker"
    fi
}

run_gamma_full_workflow() {
    print_header "Run Full Gamma Scalping Workflow"

    read_ticker "Enter ticker symbol (default: SPY):" "SPY"

    # Step 1: Fetch data
    print_info "Step 1/3: Fetching intraday data..."
    uv run pricing/gamma_scalping/python/fetch/fetch_intraday.py \
        --ticker "$ticker" \
        --days 5

    # Step 2: Run simulation
    print_info "Step 2/3: Running gamma scalping simulation..."
    opam exec -- dune exec gamma_scalping -- \
        -ticker "$ticker" \
        -position straddle \
        -strike 0 \
        -expiry 30 \
        -iv 0.20 \
        -strategy threshold \
        -threshold 0.10

    # Step 3: Visualize
    print_info "Step 3/3: Generating visualizations..."
    uv run pricing/gamma_scalping/python/viz/plot_pnl.py \
        --ticker "$ticker"

    print_success "Full workflow complete for $ticker"
    print_info "Results in: pricing/gamma_scalping/output/"
}

# FX Hedging operations
show_fx_hedging_menu() {
    detect_data_provider
    while true; do
        clear
        echo -e "${BLUE}═══ FX & Crypto Hedging with Futures ═══${NC}\n"
        echo "FX:     6E EUR/USD │ 6B GBP/USD │ 6J JPY/USD │ 6S CHF/USD │ 6A AUD/USD │ 6C CAD/USD"
        echo "Micro:  M6E        │ M6B        │ M6J        │ M6S        │ M6A        │ M6C"
        echo "Crypto: BTC Bitcoin │ MBT Micro BTC │ ETH Ether │ MET Micro ETH │ SOL Solana"
        if [[ -n "$DATA_PROVIDER_DISPLAY" ]]; then
            echo -e "Data provider: ${CYAN}${DATA_PROVIDER_DISPLAY}${NC}"
        fi
        echo ""
        echo -e "${GREEN}1)${NC} Fetch Market Data"
        echo -e "${GREEN}2)${NC} Run Hedge Backtest"
        echo -e "${GREEN}3)${NC} Analyze Exposure"
        echo -e "${GREEN}4)${NC} Price Futures Options"
        echo -e "${GREEN}5)${NC} Visualize Results"
        echo -e "${GREEN}6)${NC} Run Full Workflow"
        echo -e "${GREEN}0)${NC} Back to Pricing Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_fx_data ;;
            2) run_fx_hedge_backtest ;;
            3) analyze_fx_exposure ;;
            4) price_futures_options ;;
            5) visualize_fx_results ;;
            6|"") run_fx_full_workflow ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
        read -rp "Press Enter to continue..."
    done
}

fetch_fx_data() {
    print_header "Fetch Market Data (FX or Crypto)"

    echo "FX:     6E 6B 6J 6S 6A 6C  (micro: M6E M6B M6J M6S M6A M6C)"
    echo "Crypto: BTC MBT ETH MET SOL MSOL"
    read -p "Enter contract code [default: MET]: " contract
    contract=${contract:-MET}

    read -p "Enter lookback days (default: 252): " lookback
    lookback=${lookback:-252}

    print_info "Fetching FX data for $contract..."

    uv run pricing/fx_hedging/python/fetch/fetch_fx_data.py \
        "$contract" \
        --days "$lookback"

    contract_lower=$(echo "$contract" | tr '[:upper:]' '[:lower:]')
    if [[ -f "pricing/fx_hedging/data/${contract_lower}_spot.csv" ]]; then
        print_success "FX spot data saved to: pricing/fx_hedging/data/${contract_lower}_spot.csv"
        print_success "Futures data saved to: pricing/fx_hedging/data/${contract_lower}_futures.csv"

        # Show sample
        echo ""
        print_info "Spot rates (first 5 rows):"
        head -6 "pricing/fx_hedging/data/${contract_lower}_spot.csv"
    else
        print_error "Failed to fetch FX data for $contract"
    fi
}

run_fx_hedge_backtest() {
    print_header "Run FX Hedge Backtest"

    read -p "Enter futures contract code (default: MET): " contract
    contract=${contract:-MET}

    read -p "Enter USD exposure amount (default: 30000): " exposure
    exposure=${exposure:-30000}

    read -p "Enter hedge ratio (default: -1.0 = full hedge): " hedge_ratio
    hedge_ratio=${hedge_ratio:-"-1.0"}

    print_info "Running hedge backtest for $contract with exposure \$${exposure}..."

    opam exec -- dune exec --root pricing/fx_hedging/ocaml fx_hedging -- \
        -operation backtest \
        -contract "$contract" \
        -exposure "$exposure" \
        -hedge-ratio "$hedge_ratio"

    if [[ -f "pricing/fx_hedging/output/${contract}_backtest.csv" ]]; then
        print_success "Backtest complete: pricing/fx_hedging/output/${contract}_backtest.csv"

        # Display summary
        if command -v column &> /dev/null; then
            echo ""
            print_info "Backtest Summary (last 5 periods):"
            tail -6 "pricing/fx_hedging/output/${contract}_backtest.csv" | column -t -s','
        fi
    else
        print_error "Backtest failed for $contract"
    fi
}

manage_fx_portfolio() {
    # Interactive portfolio manager — returns 0 if user wants to continue, 1 to cancel
    local portfolio_file="$1"
    mkdir -p "$(dirname "$portfolio_file")"

    # Ensure file exists with header
    if [[ ! -f "$portfolio_file" ]]; then
        echo "ticker,quantity" > "$portfolio_file"
    fi

    while true; do
        clear
        echo -e "${BLUE}═══ Portfolio Positions ═══${NC}\n"

        # Read and display positions
        local count=0
        local tickers=()
        local quantities=()
        while IFS=',' read -r ticker qty _rest; do
            [[ "$ticker" == "ticker" ]] && continue  # skip header
            [[ -z "$ticker" ]] && continue
            count=$((count + 1))
            tickers+=("$ticker")
            quantities+=("$qty")
            printf "  ${GREEN}%d)${NC} %-10s ×%s\n" "$count" "$ticker" "$qty"
        done < "$portfolio_file"

        if [[ $count -eq 0 ]]; then
            echo -e "  ${YELLOW}(empty — add positions below)${NC}"
        fi

        echo ""
        echo -e "${GREEN}a)${NC} Add position"
        if [[ $count -gt 0 ]]; then
            echo -e "${GREEN}d)${NC} Delete position (by number)"
            echo -e "${GREEN}x)${NC} Clear all"
            echo -e "${GREEN}c)${NC} Continue"
        fi
        echo -e "${GREEN}0)${NC} Cancel"
        echo ""
        read -p "Choice: " choice

        case "$choice" in
            a|A)
                echo ""
                read -p "Ticker: " new_ticker
                new_ticker=$(echo "$new_ticker" | tr '[:lower:]' '[:upper:]' | xargs)
                if [[ -z "$new_ticker" ]]; then
                    print_error "Ticker cannot be empty."
                    sleep 1
                    continue
                fi
                # Disambiguate bare crypto symbols that collide with stock tickers
                case "$new_ticker" in
                    BTC|ETH|SOL|XRP|ADA|LINK)
                        echo ""
                        echo -e "  ${YELLOW}\"${new_ticker}\" is both a crypto symbol and a stock ticker.${NC}"
                        echo -e "  ${GREEN}1)${NC} ${new_ticker}-USD  (cryptocurrency)"
                        echo -e "  ${GREEN}2)${NC} ${new_ticker}     (stock)"
                        read -p "  Which did you mean? [1]: " crypto_choice
                        crypto_choice=${crypto_choice:-1}
                        if [[ "$crypto_choice" == "1" ]]; then
                            new_ticker="${new_ticker}-USD"
                        fi
                        ;;
                esac
                read -p "Shares: " new_qty
                new_qty=${new_qty:-0}
                echo "${new_ticker},${new_qty}" >> "$portfolio_file"
                ;;
            d|D)
                if [[ $count -eq 0 ]]; then continue; fi
                read -p "Position # to delete: " del_num
                if [[ "$del_num" =~ ^[0-9]+$ ]] && [[ $del_num -ge 1 ]] && [[ $del_num -le $count ]]; then
                    local del_ticker="${tickers[$((del_num-1))]}"
                    # Rewrite file without that line
                    local tmp_file="${portfolio_file}.tmp"
                    echo "ticker,quantity" > "$tmp_file"
                    local idx=0
                    for i in "${!tickers[@]}"; do
                        if [[ $((i+1)) -ne $del_num ]]; then
                            echo "${tickers[$i]},${quantities[$i]}" >> "$tmp_file"
                        fi
                    done
                    mv "$tmp_file" "$portfolio_file"
                    print_success "Removed $del_ticker"
                    sleep 0.5
                else
                    print_error "Invalid position number."
                    sleep 1
                fi
                ;;
            x|X)
                echo "ticker,quantity" > "$portfolio_file"
                print_success "Cleared all positions."
                sleep 0.5
                ;;
            c|C)
                if [[ $count -eq 0 ]]; then
                    print_error "Add at least one position first."
                    sleep 1
                    continue
                fi
                return 0
                ;;
            0) return 1 ;;
            *) ;;
        esac
    done
}

analyze_fx_exposure() {
    print_header "Analyze FX Exposure"

    local portfolio_file="pricing/fx_hedging/data/portfolio.csv"

    read -p "Enter your home currency (USD, EUR, GBP, JPY, CHF) [USD]: " home_ccy
    home_ccy=$(echo "${home_ccy:-USD}" | tr '[:lower:]' '[:upper:]')

    manage_fx_portfolio "$portfolio_file" || return 0

    # Enrich with prices and currencies from yfinance
    print_info "Fetching current prices and currencies..."
    uv run pricing/fx_hedging/python/fetch/enrich_portfolio.py "$portfolio_file" \
        --home-currency "$home_ccy"

    # Run OCaml exposure analysis
    print_info "Analyzing portfolio FX exposure..."
    opam exec -- dune exec --root pricing/fx_hedging/ocaml fx_hedging -- \
        -operation exposure

    if [[ -f "pricing/fx_hedging/output/exposure_analysis.csv" ]]; then
        print_success "Exposure analysis complete"
        if command -v column &> /dev/null; then
            echo ""
            column -t -s',' "pricing/fx_hedging/output/exposure_analysis.csv"
        fi
    else
        print_error "Exposure analysis failed"
    fi
}

price_futures_options() {
    print_header "Price Futures Options (Black-76)"

    read -p "Enter strike price (default: 1.10): " strike
    strike=${strike:-1.10}

    read -p "Enter option type (call|put, default: call): " option_type
    option_type=${option_type:-call}

    read -p "Enter days to expiry (default: 30): " expiry
    expiry=${expiry:-30}

    read -p "Enter implied volatility (default: 0.12): " vol
    vol=${vol:-0.12}

    print_info "Pricing $option_type option (K=$strike, T=${expiry}d, vol=$vol)..."

    opam exec -- dune exec --root pricing/fx_hedging/ocaml fx_hedging -- \
        -operation price \
        -option-type "$option_type" \
        -strike "$strike" \
        -expiry-days "$expiry" \
        -volatility "$vol"
}

visualize_fx_results() {
    print_header "Visualize FX Hedging Results"

    read -p "Enter futures contract code (default: MET): " contract
    contract=${contract:-MET}

    print_info "Generating visualizations for $contract..."

    # Plot hedge performance
    if [[ -f "pricing/fx_hedging/output/${contract}_backtest.csv" ]]; then
        uv run pricing/fx_hedging/python/viz/plot_hedge_performance.py \
            "$contract" \
            --output "pricing/fx_hedging/output/${contract}_hedge_performance.png"
        print_success "Hedge performance plot saved"
    else
        print_error "No backtest data found. Run backtest first."
    fi

    # Plot exposure analysis
    if [[ -f "pricing/fx_hedging/output/exposure_analysis.csv" ]]; then
        uv run pricing/fx_hedging/python/viz/plot_exposure_analysis.py \
            --output "pricing/fx_hedging/output/exposure_analysis.png"
        print_success "Exposure analysis plot saved"
    else
        print_info "No exposure data. Run exposure analysis to generate."
    fi
}

run_fx_full_workflow() {
    local portfolio_file="pricing/fx_hedging/data/portfolio.csv"

    # Step 0: Home currency
    read -p "Enter your home currency (USD, EUR, GBP, JPY, CHF) [USD]: " home_ccy
    home_ccy=$(echo "${home_ccy:-USD}" | tr '[:lower:]' '[:upper:]')

    # Step 1: Manage portfolio
    manage_fx_portfolio "$portfolio_file" || return 0

    # Step 2: Enrich with prices and currencies from yfinance
    print_info "Step 1/4: Fetching current prices and currencies..."
    uv run pricing/fx_hedging/python/fetch/enrich_portfolio.py "$portfolio_file" \
        --home-currency "$home_ccy"

    # Check for FX-exposed positions
    local fx_currencies
    fx_currencies=$(tail -n +2 "$portfolio_file" | cut -d',' -f4 | sort -u | tr -d ' ' | grep -v "^${home_ccy}$")

    if [[ -z "$fx_currencies" ]]; then
        echo ""
        print_error "All positions are denominated in your home currency (${home_ccy})."
        print_info "FX hedging requires exposure to foreign currencies."
        print_info "Either add stocks from other countries, or change your home currency."
        return
    fi

    # Step 3: Fetch spot data for all FX currencies
    print_info "Step 2/4: Fetching FX spot rates..."

    # Build map of currency → CME contract code
    # CME FX futures are all XXX/USD. For a non-USD home investor,
    # USD exposure is hedged via the home currency's own contract
    # (e.g., CHF investor hedges USD risk with 6S = CHF/USD).
    declare -A ccy_to_code
    for ccy in $fx_currencies; do
        if [[ "$ccy" == "USD" ]]; then
            # USD exposure for non-USD investor: use home currency's contract
            case "$home_ccy" in
                EUR) ccy_to_code[$ccy]="6E" ;; GBP) ccy_to_code[$ccy]="6B" ;;
                JPY) ccy_to_code[$ccy]="6J" ;; CHF) ccy_to_code[$ccy]="6S" ;;
                AUD) ccy_to_code[$ccy]="6A" ;; CAD) ccy_to_code[$ccy]="6C" ;;
            esac
        else
            case "$ccy" in
                EUR) ccy_to_code[$ccy]="6E" ;; GBP) ccy_to_code[$ccy]="6B" ;;
                JPY) ccy_to_code[$ccy]="6J" ;; CHF) ccy_to_code[$ccy]="6S" ;;
                AUD) ccy_to_code[$ccy]="6A" ;; CAD) ccy_to_code[$ccy]="6C" ;;
                BTC) ccy_to_code[$ccy]="MBT" ;; ETH) ccy_to_code[$ccy]="MET" ;;
                SOL) ccy_to_code[$ccy]="MSOL" ;;
            esac
        fi
    done

    for ccy in "${!ccy_to_code[@]}"; do
        local code="${ccy_to_code[$ccy]}"
        echo "  Fetching $ccy ($code)..."
        uv run pricing/fx_hedging/python/fetch/fetch_fx_data.py "$code" --days 252
    done

    # Step 4: Analyze exposure
    print_info "Step 3/4: Analyzing portfolio FX exposure..."
    opam exec -- dune exec --root pricing/fx_hedging/ocaml fx_hedging -- \
        -operation exposure

    if [[ ! -f "pricing/fx_hedging/output/exposure_analysis.csv" ]]; then
        print_error "Exposure analysis failed"
        return
    fi

    echo ""
    if command -v column &> /dev/null; then
        column -t -s',' "pricing/fx_hedging/output/exposure_analysis.csv"
    fi

    # Step 5: Run backtests only for hedgeable exposures (≥ 1 contract)
    print_info "Step 4/4: Running backtests and generating plots..."

    # Read per-currency exposure from the analysis CSV
    local backtested=0
    while IFS=',' read -r ccy exposure _pct _num; do
        [[ "$ccy" == "currency" ]] && continue  # skip header
        [[ -z "$ccy" ]] && continue
        local code="${ccy_to_code[$ccy]:-}"
        if [[ -z "$code" ]]; then continue; fi

        # Use the actual exposure amount for the backtest
        local exp_int
        exp_int=$(printf "%.0f" "$exposure")

        # Auto-downgrade to micro contracts when exposure is too small for standard.
        # You need at least ~half the contract notional for rounding to give 1 contract:
        #   6E: 125k EUR ≈ $135k    6B: 62.5k GBP ≈ $80k     6J: 12.5M JPY ≈ $83k
        #   6S: 125k CHF ≈ $150k    6A: 100k AUD  ≈ $65k     6C: 100k CAD  ≈ $72k
        # Micro FX contracts are 1/10th → need ~$3k-$8k for 1 micro contract.
        local min_micro=100
        case "$code" in
            MBT|MET|MSOL) ;;  # already micro crypto, no downgrade needed
            6E|6B|6J|6S|6A|6C)
                if [[ "$exp_int" -lt 50000 ]]; then
                    local micro_code="M${code}"
                    echo "  \$${exp_int} too small for standard ${code} — using micro ${micro_code}"
                    code="$micro_code"
                fi
                ;;
        esac

        if [[ "$exp_int" -lt "$min_micro" ]]; then
            echo "  Skipping $ccy ($code): \$${exp_int} too small even for a micro contract"
            continue
        fi

        # Fetch micro contract data if we downgraded (uses same spot, just different code)
        if [[ "$code" == M6* ]]; then
            uv run pricing/fx_hedging/python/fetch/fetch_fx_data.py "$code" --days 252
        fi

        echo ""
        echo "  Backtesting $ccy ($code) with \$${exp_int} exposure..."
        opam exec -- dune exec --root pricing/fx_hedging/ocaml fx_hedging -- \
            -operation backtest \
            -contract "$code" \
            -exposure "$exp_int" \
            -hedge-ratio "-1.0"

        # Generate hedge performance plot
        if [[ -f "pricing/fx_hedging/output/${code}_backtest.csv" ]]; then
            uv run pricing/fx_hedging/python/viz/plot_hedge_performance.py \
                "$code" \
                --output "pricing/fx_hedging/output/${code}_hedge_performance.png"
            backtested=$((backtested + 1))
        fi
    done < "pricing/fx_hedging/output/exposure_analysis.csv"

    if [[ $backtested -eq 0 ]]; then
        print_info "No positions large enough for a futures backtest."
    fi

    # Generate exposure analysis / hedge recommendation plot
    echo ""
    uv run pricing/fx_hedging/python/viz/plot_exposure_analysis.py \
        --output "pricing/fx_hedging/output/exposure_analysis.png" \
        --home-currency "$home_ccy"

    echo ""
    print_success "Workflow complete"
    print_info "Plots saved to: pricing/fx_hedging/output/"
}


# Dispersion Trading operations
show_dispersion_trading_menu() {
    while true; do
        clear
        echo -e "${BLUE}═══ Dispersion Trading ═══${NC}\n"
        echo "Trade correlation between index and constituents"
        echo ""
        echo -e "${GREEN}1)${NC} Fetch Options Data"
        echo -e "${GREEN}2)${NC} Run Analysis"
        echo -e "${GREEN}3)${NC} Visualize Dispersion"
        echo -e "${GREEN}4)${NC} Run Full Workflow"
        echo ""
        echo "DAILY PIPELINE:"
        echo -e "${GREEN}5)${NC} Collect Daily Snapshot"
        echo -e "${GREEN}6)${NC} Scan Signals"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Pricing Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_dispersion_data ;;
            2) run_dispersion_analysis ;;
            3) visualize_dispersion ;;
            4|"") run_dispersion_workflow ;;
            5) collect_dispersion_snapshot ;;
            6) scan_dispersion_signals ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_dispersion_data() {
    print_header "Fetch Options Data for Dispersion"

    read -p "Enter index ticker (default: SPY): " index
    index=${index:-SPY}

    read -p "Enter constituent tickers, comma-separated (default: top 10 SPY holdings): " constituents
    constituents=${constituents:-AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,JPM,V,UNH}

    read -p "Enter lookback days (default: 30): " days
    days=${days:-30}

    print_info "Fetching options data for $index and constituents..."

    uv run pricing/dispersion_trading/python/fetch/fetch_options.py \
        --index "$index" \
        --constituents "$constituents" \
        --days "$days"

    if [[ -f "pricing/dispersion_trading/data/index_data.csv" ]]; then
        print_success "Data saved to pricing/dispersion_trading/data/"
    else
        print_error "Failed to fetch dispersion data"
    fi
}

run_dispersion_analysis() {
    print_header "Run Dispersion Analysis"

    print_info "Running OCaml dispersion analysis..."

    cd pricing/dispersion_trading/ocaml
    opam exec -- dune exec ./bin/main.exe
    cd ../../..

    print_success "Analysis complete"
}

visualize_dispersion() {
    print_header "Visualize Dispersion Metrics"

    if [[ ! -f "pricing/dispersion_trading/data/index_data.csv" ]]; then
        print_error "No data found. Please run 'Fetch Options Data' first."
        return
    fi

    print_info "Generating dispersion visualization..."

    uv run pricing/dispersion_trading/python/viz/plot_dispersion.py

    if [[ -f "pricing/dispersion_trading/output/dispersion_analysis.png" ]]; then
        print_success "Visualization saved to: pricing/dispersion_trading/output/dispersion_analysis.png"
    else
        print_error "Failed to generate visualization"
    fi
}

run_dispersion_workflow() {
    print_header "Run Full Dispersion Workflow"

    read -p "Enter index ticker (default: SPY): " index
    index=${index:-SPY}

    read -p "Enter constituent tickers (default: top 10 SPY holdings): " constituents
    constituents=${constituents:-AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,JPM,V,UNH}

    # Step 1: Fetch data
    print_info "Step 1/3: Fetching options data..."
    uv run pricing/dispersion_trading/python/fetch/fetch_options.py \
        --index "$index" \
        --constituents "$constituents" \
        --days 30

    # Step 2: Run analysis
    print_info "Step 2/3: Running dispersion analysis..."
    cd pricing/dispersion_trading/ocaml
    opam exec -- dune exec ./bin/main.exe
    cd ../../..

    # Step 3: Visualize
    print_info "Step 3/3: Generating visualization..."
    uv run pricing/dispersion_trading/python/viz/plot_dispersion.py

    print_success "Full workflow complete!"
    echo ""

    # Show results summary
    if [[ -f "pricing/dispersion_trading/data/index_data.csv" ]] && [[ -f "pricing/dispersion_trading/data/constituents_data.csv" ]]; then
        echo -e "${CYAN}═══ Results Summary ═══${NC}"
        echo ""
        echo -e "${WHITE}Index:${NC}"
        tail -n +2 pricing/dispersion_trading/data/index_data.csv | awk -F',' '{printf "  %s: Spot $%.2f, IV %.1f%%\n", $1, $2, $3*100}'
        echo ""
        echo -e "${WHITE}Constituents:${NC}"
        tail -n +2 pricing/dispersion_trading/data/constituents_data.csv | awk -F',' '{printf "  %s: Spot $%.2f, IV %.1f%%, Weight %.0f%%\n", $1, $2, $3*100, $5*100}'
        echo ""
        echo -e "${WHITE}Output:${NC} pricing/dispersion_trading/output/dispersion_analysis.png"
        echo ""
    fi

    read -p "Press Enter to continue..."
}

collect_dispersion_snapshot() {
    print_header "Collect Daily Dispersion Snapshot"

    read -p "Enter index ticker (default: SPY): " index
    index=${index:-SPY}

    read -p "Enter constituent tickers (default: top 10 SPY holdings): " constituents
    constituents=${constituents:-AAPL,MSFT,NVDA,AMZN,GOOGL,META,TSLA,JPM,V,UNH}

    print_info "Collecting dispersion snapshot for $index..."

    uv run pricing/dispersion_trading/python/fetch/collect_snapshot.py \
        --index "$index" \
        --constituents "$constituents" \
        --data-dir pricing/dispersion_trading/data

    if [ $? -eq 0 ]; then
        print_success "Snapshot collected"
        print_info "Data: pricing/dispersion_trading/data/"
    else
        print_error "Snapshot collection failed"
    fi
}

scan_dispersion_signals() {
    print_header "Scan Dispersion Signals"

    print_info "Scanning dispersion histories..."

    uv run pricing/dispersion_trading/python/scan_signals.py \
        --quiet \
        --output pricing/dispersion_trading/output/signal_scan.csv

    if [ $? -eq 0 ]; then
        print_success "Scan complete"
        print_info "Results: pricing/dispersion_trading/output/signal_scan.csv"
    else
        print_error "Scan failed"
    fi
}

# Pairs Trading operations
show_pairs_trading_menu() {
    while true; do
        clear
        echo -e "${BLUE}═══ Pairs Trading ═══${NC}\n"
        echo "Statistical arbitrage with cointegrated pairs"
        echo ""
        echo -e "${GREEN}1)${NC} Fetch Pair Data"
        echo -e "${GREEN}2)${NC} Run Cointegration Analysis"
        echo -e "${GREEN}3)${NC} Visualize Pairs"
        echo -e "${GREEN}4)${NC} Run Full Workflow"
        echo -e "${GREEN}0)${NC} Back to Pricing Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_pairs_data ;;
            2) run_pairs_analysis ;;
            3) visualize_pairs ;;
            4|"") run_pairs_workflow ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_pairs_data() {
    print_header "Fetch Pair Data"

    read_ticker "Enter first ticker (default: GLD):" "GLD"
    local ticker1="$ticker"

    read_ticker "Enter second ticker (default: GDX):" "GDX"
    local ticker2="$ticker"

    read -p "Enter lookback days (default: 252): " days
    days=${days:-252}

    print_info "Fetching pair data for $ticker1 / $ticker2..."

    uv run pricing/pairs_trading/python/fetch/fetch_pairs.py \
        --ticker1 "$ticker1" \
        --ticker2 "$ticker2" \
        --days "$days"

    if [[ -f "pricing/pairs_trading/data/pair_data.csv" ]]; then
        print_success "Data saved to pricing/pairs_trading/data/"
    else
        print_error "Failed to fetch pair data"
    fi
}

run_pairs_analysis() {
    print_header "Run Pairs Cointegration Analysis"

    print_info "Running OCaml cointegration test..."

    opam exec -- dune exec pairs_trading

    print_success "Analysis complete"
}

visualize_pairs() {
    print_header "Visualize Pairs Trading"

    if [[ ! -f "pricing/pairs_trading/data/pair_data.csv" ]]; then
        print_error "No data found. Please run 'Fetch Pair Data' first."
        return
    fi

    print_info "Generating pairs visualization..."

    uv run pricing/pairs_trading/python/viz/plot_pairs.py

    if [[ -f "pricing/pairs_trading/output/pairs_analysis.png" ]]; then
        print_success "Visualization saved to: pricing/pairs_trading/output/pairs_analysis.png"
    else
        print_error "Failed to generate visualization"
    fi
}

run_pairs_workflow() {
    print_header "Run Full Pairs Trading Workflow"

    read_ticker "Enter first ticker (default: GLD):" "GLD"
    local ticker1="$ticker"

    read_ticker "Enter second ticker (default: GDX):" "GDX"
    local ticker2="$ticker"

    read -p "Enter lookback days (default: 252): " days
    days=${days:-252}

    # Step 1: Fetch data
    print_info "Step 1/3: Fetching pair data for $ticker1 / $ticker2..."
    uv run pricing/pairs_trading/python/fetch/fetch_pairs.py \
        --ticker1 "$ticker1" \
        --ticker2 "$ticker2" \
        --days "$days"

    # Step 2: Run analysis
    print_info "Step 2/3: Running cointegration analysis..."
    opam exec -- dune exec pairs_trading

    # Step 3: Visualize
    print_info "Step 3/3: Generating visualization..."
    uv run pricing/pairs_trading/python/viz/plot_pairs.py

    print_success "Full workflow complete!"
    print_info "Results: pricing/pairs_trading/output/"
}

# Earnings Volatility operations
show_earnings_vol_menu() {
    while true; do
        clear
        echo -e "${BLUE}═══ Earnings Volatility (IV Crush Scanner) ═══${NC}\n"
        echo "Sell implied volatility around earnings when overpriced"
        echo ""
        echo "LIVE SCANNER:"
        echo -e "${GREEN}1)${NC} Fetch Earnings Data"
        echo -e "${GREEN}2)${NC} Fetch IV Term Structure"
        echo -e "${GREEN}3)${NC} Run Scanner (Filter + Kelly Sizing)"
        echo -e "${GREEN}4)${NC} Run Full Workflow"
        echo ""
        echo "DAILY PIPELINE:"
        echo -e "${GREEN}5)${NC} Collect Daily Snapshot"
        echo -e "${GREEN}6)${NC} Scan Signals (z-score watchlist)"
        echo ""
        echo "HISTORICAL BACKTEST (Phase 2):"
        echo -e "${GREEN}7)${NC} Fetch Historical Earnings (2022-2025)"
        echo -e "${GREEN}8)${NC} Run Historical Backtest"
        echo -e "${GREEN}9)${NC} Visualize Backtest Results"
        echo -e "${GREEN}10)${NC} Run Full Backtest Workflow"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Pricing Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_earnings_data ;;
            2) fetch_iv_term_structure ;;
            3) run_earnings_scanner ;;
            4|"") run_earnings_workflow ;;
            5) collect_earnings_vol_snapshot ;;
            6) scan_earnings_vol_signals ;;
            7) fetch_historical_earnings ;;
            8) run_historical_backtest ;;
            9) visualize_backtest ;;
            10) run_full_backtest_workflow ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_earnings_data() {
    print_header "Fetch Earnings Data"

    read -p "Enter ticker (default: NVDA): " ticker
    ticker=${ticker:-NVDA}

    print_info "Fetching earnings calendar and volume for $ticker..."

    uv run pricing/earnings_vol/python/fetch/fetch_earnings.py --ticker "$ticker"

    if [[ -f "pricing/earnings_vol/data/${ticker}_earnings.csv" ]]; then
        print_success "Earnings data saved to pricing/earnings_vol/data/"
    else
        print_error "Failed to fetch earnings data"
    fi
}

fetch_iv_term_structure() {
    print_header "Fetch IV Term Structure"

    read -p "Enter ticker (default: NVDA): " ticker
    ticker=${ticker:-NVDA}

    print_info "Fetching options IV term structure for $ticker..."

    uv run pricing/earnings_vol/python/fetch/fetch_iv_term.py --ticker "$ticker"

    if [[ -f "pricing/earnings_vol/data/${ticker}_iv_term.csv" ]]; then
        print_success "IV term structure saved to pricing/earnings_vol/data/"
    else
        print_error "Failed to fetch IV term structure"
    fi
}

run_earnings_scanner() {
    print_header "Run Earnings Volatility Scanner"

    read -p "Enter ticker (default: NVDA): " ticker
    ticker=${ticker:-NVDA}

    read -p "Enter account size (default: 10000): " account
    account=${account:-10000}

    read -p "Enter fractional Kelly (default: 0.10): " kelly
    kelly=${kelly:-0.10}

    read -p "Enter structure (straddle|calendar, default: calendar): " structure
    structure=${structure:-calendar}

    print_info "Running earnings vol scanner for $ticker..."

    if [[ ! -f "pricing/earnings_vol/data/${ticker}_earnings.csv" ]]; then
        print_error "Earnings data not found. Run 'Fetch Earnings Data' first."
        return
    fi

    if [[ ! -f "pricing/earnings_vol/data/${ticker}_iv_term.csv" ]]; then
        print_error "IV term structure not found. Run 'Fetch IV Term Structure' first."
        return
    fi

    opam exec -- dune exec pricing/earnings_vol/ocaml/bin/main.exe -- \
        -ticker "$ticker" \
        -account "$account" \
        -kelly "$kelly" \
        -structure "$structure"

    print_success "Scanner complete"
}

run_earnings_workflow() {
    print_header "Run Full Earnings Volatility Workflow"

    read -p "Enter ticker (default: NVDA): " ticker
    ticker=${ticker:-NVDA}

    read -p "Enter account size (default: 10000): " account
    account=${account:-10000}

    read -p "Enter fractional Kelly (default: 0.10): " kelly
    kelly=${kelly:-0.10}

    read -p "Enter structure (straddle|calendar, default: calendar): " structure
    structure=${structure:-calendar}

    # Step 1: Fetch earnings data
    print_info "Step 1/3: Fetching earnings data for $ticker..."
    uv run pricing/earnings_vol/python/fetch/fetch_earnings.py --ticker "$ticker"

    # Step 2: Fetch IV term structure
    print_info "Step 2/3: Fetching IV term structure for $ticker..."
    uv run pricing/earnings_vol/python/fetch/fetch_iv_term.py --ticker "$ticker"

    # Step 3: Run scanner
    print_info "Step 3/3: Running earnings volatility scanner..."
    opam exec -- dune exec pricing/earnings_vol/ocaml/bin/main.exe -- \
        -ticker "$ticker" \
        -account "$account" \
        -kelly "$kelly" \
        -structure "$structure"

    print_success "Full workflow complete!"
    print_info "Data saved to: pricing/earnings_vol/data/"
}

fetch_historical_earnings() {
    print_header "Fetch Historical Earnings (2022-2025)"

    read -p "Enter start date (YYYY-MM-DD, default: 2022-01-01): " start_date
    start_date=${start_date:-2022-01-01}

    print_info "Fetching historical earnings since $start_date..."
    print_warning "This will take 5-10 minutes (fetching 30+ stocks, 3+ years)"

    uv run pricing/earnings_vol/python/backtest/fetch_historical_earnings.py \
        --start-date "$start_date"

    if [[ -f "pricing/earnings_vol/data/backtest/historical_earnings_events.csv" ]]; then
        print_success "Historical earnings data fetched!"

        print_info "Computing IV/RV metrics..."
        uv run pricing/earnings_vol/python/backtest/compute_historical_metrics.py

        print_info "Combining data files..."
        uv run pricing/earnings_vol/python/backtest/combine_historical_data.py

        print_success "Historical data preparation complete!"
    else
        print_error "Failed to fetch historical data"
    fi
}

run_historical_backtest() {
    print_header "Run Historical Backtest"

    read -p "Enter structure (straddle|calendar, default: calendar): " structure
    structure=${structure:-calendar}

    print_info "Running backtest for $structure..."

    if [[ ! -f "pricing/earnings_vol/data/backtest/historical_combined.csv" ]]; then
        print_error "Historical data not found. Run 'Fetch Historical Earnings' first."
        return
    fi

    opam exec -- dune exec pricing/earnings_vol/ocaml/bin/backtest_main.exe -- \
        -structure "$structure"

    print_success "Backtest complete!"
    print_info "Results: pricing/earnings_vol/data/backtest/backtest_results.csv"
}

visualize_backtest() {
    print_header "Visualize Backtest Results"

    read -p "Enter structure (straddle|calendar, default: calendar): " structure
    structure=${structure:-calendar}

    if [[ ! -f "pricing/earnings_vol/data/backtest/backtest_results.csv" ]]; then
        print_error "Backtest results not found. Run 'Run Historical Backtest' first."
        return
    fi

    print_info "Generating backtest visualization..."

    uv run pricing/earnings_vol/python/viz/plot_backtest.py --structure "$structure"

    if [[ -f "pricing/earnings_vol/output/backtest_analysis_${structure}.png" ]]; then
        print_success "Visualization saved!"
        print_info "Output: pricing/earnings_vol/output/backtest_analysis_${structure}.png"
    else
        print_error "Failed to generate visualization"
    fi
}

run_full_backtest_workflow() {
    print_header "Run Full Backtest Workflow"

    read -p "Enter start date (YYYY-MM-DD, default: 2022-01-01): " start_date
    start_date=${start_date:-2022-01-01}

    read -p "Enter structure (straddle|calendar, default: calendar): " structure
    structure=${structure:-calendar}

    # Step 1: Fetch historical data
    print_info "Step 1/4: Fetching historical earnings since $start_date..."
    print_warning "This will take 5-10 minutes"

    uv run pricing/earnings_vol/python/backtest/fetch_historical_earnings.py \
        --start-date "$start_date"

    # Step 2: Compute metrics
    print_info "Step 2/4: Computing IV/RV metrics..."
    uv run pricing/earnings_vol/python/backtest/compute_historical_metrics.py

    # Step 3: Combine data
    print_info "Step 3/4: Combining data..."
    uv run pricing/earnings_vol/python/backtest/combine_historical_data.py

    # Step 4: Run backtest
    print_info "Step 4/4: Running backtest for $structure..."
    opam exec -- dune exec pricing/earnings_vol/ocaml/bin/backtest_main.exe -- \
        -structure "$structure"

    # Step 5: Visualize
    print_info "Generating visualization..."
    uv run pricing/earnings_vol/python/viz/plot_backtest.py --structure "$structure"

    print_success "Full backtest workflow complete!"
    print_info "Results: pricing/earnings_vol/output/backtest_analysis_${structure}.png"
    print_info "Data: pricing/earnings_vol/data/backtest/"
}

collect_earnings_vol_snapshot() {
    print_header "Collect Daily Earnings Vol Snapshot"

    pick_ticker_source "NVDA" || return

    print_info "Collecting earnings vol snapshot..."

    uv run pricing/earnings_vol/python/fetch/collect_snapshot.py \
        --tickers "$ticker_arg" \
        --data-dir pricing/earnings_vol/data

    if [ $? -eq 0 ]; then
        print_success "Snapshot collected"
        print_info "Data: pricing/earnings_vol/data/"
    else
        print_error "Snapshot collection failed"
    fi
}

scan_earnings_vol_signals() {
    print_header "Scan Earnings Vol Signals"

    echo -e "${GREEN}1)${NC} Overall ranking (all tickers)"
    echo -e "${GREEN}2)${NC} By price segment"
    echo ""
    echo -e "${YELLOW}Enter your choice (Enter=By segment):${NC} "
    read -r scan_choice

    local scan_args="--quiet"
    case $scan_choice in
        1) ;;
        2|"") scan_args="$scan_args --segments" ;;
        *) scan_args="$scan_args --segments" ;;
    esac

    print_info "Scanning earnings vol histories..."

    uv run pricing/earnings_vol/python/scan_signals.py \
        $scan_args \
        --output pricing/earnings_vol/output/signal_scan.csv

    if [ $? -eq 0 ]; then
        print_success "Scan complete"
        print_info "Results: pricing/earnings_vol/output/signal_scan.csv"
    else
        print_error "Scan failed"
    fi
}

# Skew Verticals (Directional Spreads) operations
show_skew_verticals_menu() {
    while true; do
        clear
        echo -e "${BLUE}═══ Skew Verticals (Directional Spreads) ═══${NC}\n"
        echo "Directional vertical spreads using momentum and volatility skew"
        echo ""
        echo -e "${GREEN}1)${NC} Fetch Options Chain"
        echo -e "${GREEN}2)${NC} Fetch Price History"
        echo -e "${GREEN}3)${NC} Run Scanner (Momentum + Skew Analysis)"
        echo -e "${GREEN}4)${NC} Run Full Workflow (Batch: Multiple Tickers)"
        echo ""
        echo "DAILY PIPELINE:"
        echo -e "${GREEN}5)${NC} Collect Daily Snapshot"
        echo -e "${GREEN}6)${NC} Scan Signals (z-score watchlist)"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Pricing Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_skew_verticals_chain ;;
            2) fetch_skew_verticals_prices ;;
            3) run_skew_verticals_scanner ;;
            4|"") run_skew_verticals_workflow ;;
            5) collect_skew_verticals_snapshot ;;
            6) scan_skew_verticals_signals ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_skew_verticals_chain() {
    print_header "Fetch Options Chain for Skew Verticals"

    read -p "Enter ticker (default: AAPL): " ticker
    ticker=${ticker:-AAPL}

    print_info "Fetching options chain for $ticker..."

    uv run pricing/skew_verticals/python/fetch/fetch_options_chain.py --ticker "$ticker"

    if [[ -f pricing/skew_verticals/data/${ticker}_*_metadata.csv ]]; then
        print_success "Options chain saved to pricing/skew_verticals/data/"
    else
        print_error "Failed to fetch options chain"
    fi

    read -p "Press Enter to continue..."
}

fetch_skew_verticals_prices() {
    print_header "Fetch Price History for Skew Verticals"

    read -p "Enter ticker (default: AAPL): " ticker
    ticker=${ticker:-AAPL}

    print_info "Fetching price history for $ticker and SPY..."

    uv run pricing/skew_verticals/python/fetch/fetch_prices.py --ticker "$ticker"

    if [[ -f pricing/skew_verticals/data/${ticker}_prices.csv ]]; then
        print_success "Price history saved to pricing/skew_verticals/data/"
    else
        print_error "Failed to fetch price history"
    fi

    read -p "Press Enter to continue..."
}

run_skew_verticals_scanner() {
    print_header "Run Skew Verticals Scanner"

    read -p "Enter ticker (default: AAPL): " ticker
    ticker=${ticker:-AAPL}

    print_info "Running skew verticals scanner for $ticker..."

    # Create output directory and log file
    mkdir -p pricing/skew_verticals/output
    TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
    LOG_FILE="pricing/skew_verticals/output/${ticker}_scan_${TIMESTAMP}.log"

    # Run scanner and capture output to both console and log file
    eval $(opam env) && dune exec skew_verticals -- "$ticker" 2>&1 | tee "$LOG_FILE"

    print_success "Skew verticals scan complete!"
    print_info "Console output saved to: $LOG_FILE"

    read -p "Press Enter to continue..."
}

run_skew_verticals_workflow() {
    print_header "Run Full Skew Verticals Workflow"

    echo "Enter tickers (space-separated, e.g., 'AAPL PYPL TSLA')"
    read -p "Tickers (default: AAPL PYPL): " tickers_input
    tickers_input=${tickers_input:-AAPL PYPL}

    # Convert to array
    IFS=' ' read -ra tickers <<< "$tickers_input"

    # Track results
    declare -a strong_buys=()
    declare -a buys=()
    declare -a passes=()

    for ticker in "${tickers[@]}"; do
        echo ""
        echo -e "${BLUE}═══════════════════════════════════════════${NC}"
        print_info "Scanning: $ticker (${#tickers[@]} total)"
        echo -e "${BLUE}═══════════════════════════════════════════${NC}"
        echo ""

        # Step 1: Fetch options chain
        print_info "Step 1/3: Fetching options chain for $ticker..."
        if ! uv run pricing/skew_verticals/python/fetch/fetch_options_chain.py --ticker "$ticker"; then
            print_error "Failed to fetch options chain for $ticker, skipping..."
            passes+=("$ticker (ERROR)")
            continue
        fi

        # Step 2: Fetch prices
        print_info "Step 2/3: Fetching price history for $ticker..."
        if ! uv run pricing/skew_verticals/python/fetch/fetch_prices.py --ticker "$ticker"; then
            print_error "Failed to fetch price history for $ticker, skipping..."
            passes+=("$ticker (ERROR)")
            continue
        fi

        # Step 3: Run scanner
        print_info "Step 3/3: Running scanner for $ticker..."

        # Create output directory and log file
        mkdir -p pricing/skew_verticals/output
        TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
        LOG_FILE="pricing/skew_verticals/output/${ticker}_scan_${TIMESTAMP}.log"

        # Run scanner and capture output to both console and log file
        eval $(opam env) && dune exec skew_verticals -- "$ticker" 2>&1 | tee "$LOG_FILE"

        # Generate visualization
        print_info "Generating spread analysis plot for $ticker..."
        uv run python pricing/skew_verticals/python/viz/plot_spread.py \
            -t "$ticker" -d pricing/skew_verticals/data \
            -s pricing/skew_verticals/output -o pricing/skew_verticals/output/plots

        # Parse JSON result to categorize
        JSON_FILE=$(ls -t pricing/skew_verticals/output/${ticker}_scan_*.json 2>/dev/null | head -1)
        if [[ -n "$JSON_FILE" && -f "$JSON_FILE" ]]; then
            recommendation=$(grep '"recommendation"' "$JSON_FILE" | head -1 | cut -d'"' -f4)
            case "$recommendation" in
                "Strong Buy")
                    strong_buys+=("$ticker")
                    ;;
                "Buy")
                    buys+=("$ticker")
                    ;;
                *)
                    passes+=("$ticker")
                    ;;
            esac
        else
            passes+=("$ticker")
        fi

        echo ""
    done

    # Print summary
    echo ""
    echo -e "${BLUE}╔════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║               BATCH SCAN SUMMARY                   ║${NC}"
    echo -e "${BLUE}╚════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo "Scanned ${#tickers[@]} ticker(s): ${tickers[*]}"
    echo ""

    if [[ ${#strong_buys[@]} -gt 0 ]]; then
        echo -e "${GREEN}✓ STRONG BUY (${#strong_buys[@]}):${NC} ${strong_buys[*]}"
    else
        echo -e "${YELLOW}✓ STRONG BUY (0)${NC}"
    fi

    if [[ ${#buys[@]} -gt 0 ]]; then
        echo -e "${GREEN}✓ BUY (${#buys[@]}):${NC} ${buys[*]}"
    else
        echo -e "${YELLOW}✓ BUY (0)${NC}"
    fi

    if [[ ${#passes[@]} -gt 0 ]]; then
        echo -e "✓ PASS (${#passes[@]}): ${passes[*]}"
    fi

    echo ""
    print_success "Batch scan complete!"
    print_info "Results saved to: pricing/skew_verticals/output/"

    read -p "Press Enter to continue..."
}

collect_skew_verticals_snapshot() {
    print_header "Collect Daily Skew Verticals Snapshot"

    pick_ticker_source "TSLA" || return

    print_info "Collecting skew verticals snapshot..."

    uv run pricing/skew_verticals/python/fetch/collect_snapshot.py \
        --tickers "$ticker_arg" \
        --data-dir pricing/skew_verticals/data

    if [ $? -eq 0 ]; then
        print_success "Snapshot collected"
        print_info "Data: pricing/skew_verticals/data/"
    else
        print_error "Snapshot collection failed"
    fi
}

scan_skew_verticals_signals() {
    print_header "Scan Skew Verticals Signals"

    echo -e "${GREEN}1)${NC} Overall ranking (all tickers)"
    echo -e "${GREEN}2)${NC} By price segment"
    echo ""
    echo -e "${YELLOW}Enter your choice (Enter=By segment):${NC} "
    read -r scan_choice

    local scan_args="--quiet"
    case $scan_choice in
        1) ;;
        2|"") scan_args="$scan_args --segments" ;;
        *) scan_args="$scan_args --segments" ;;
    esac

    print_info "Scanning skew verticals histories..."

    uv run pricing/skew_verticals/python/scan_signals.py \
        $scan_args \
        --output pricing/skew_verticals/output/signal_scan.csv

    if [ $? -eq 0 ]; then
        print_success "Scan complete"
        print_info "Results: pricing/skew_verticals/output/signal_scan.csv"
    else
        print_error "Scan failed"
    fi
}

# Pre-Earnings Straddle (ML-Based) operations
show_pre_earnings_straddle_menu() {
    while true; do
        clear
        echo -e "${BLUE}═══ Pre-Earnings Straddle (ML-Based) ═══${NC}\n"
        echo "Predict earnings moves using machine learning"
        echo -e "${DIM}Daily snapshots accept liquid tickers from Liquidity module (option 5)${NC}"
        echo ""
        echo -e "${GREEN}1)${NC} Fetch Straddle Data (Current Opportunity)"
        echo -e "${GREEN}2)${NC} Train ML Model (Historical Earnings)"
        echo -e "${GREEN}3)${NC} Run Scanner (Predict & Recommend)"
        echo -e "${GREEN}4)${NC} Run Full Workflow"
        echo -e "${GREEN}5)${NC} Collect Daily Earnings IV Snapshot"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Pricing Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_pre_earnings_data ;;
            2) train_earnings_model ;;
            3) run_pre_earnings_scanner ;;
            4|"") run_pre_earnings_workflow ;;
            5) collect_earnings_iv_snapshot ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_pre_earnings_data() {
    print_header "Fetch Pre-Earnings Straddle Data"

    read -p "Enter ticker (default: NVDA): " ticker
    ticker=${ticker:-NVDA}

    print_info "Fetching straddle data for $ticker..."

    uv run pricing/pre_earnings_straddle/python/fetch/fetch_straddle_data.py --ticker "$ticker"

    if [[ -f pricing/pre_earnings_straddle/data/${ticker}_opportunity.csv ]]; then
        print_success "Straddle data saved to pricing/pre_earnings_straddle/data/"
    else
        print_error "Failed to fetch straddle data"
    fi
}

train_earnings_model() {
    print_header "Train Earnings Prediction Model"

    print_info "Training model on historical earnings data..."

    uv run pricing/pre_earnings_straddle/python/train/train_model.py

    if [[ -f pricing/pre_earnings_straddle/data/model_coefficients.csv ]]; then
        print_success "Model trained! Coefficients saved to pricing/pre_earnings_straddle/data/"
    else
        print_error "Failed to train model"
    fi
}

run_pre_earnings_scanner() {
    print_header "Run Pre-Earnings Scanner"

    read -p "Enter ticker (default: NVDA): " ticker
    ticker=${ticker:-NVDA}

    print_info "Running pre-earnings scanner for $ticker..."

    eval $(opam env) && dune exec pre_earnings_straddle -- "$ticker"

    print_success "Pre-earnings scan complete!"
}

run_pre_earnings_workflow() {
    print_header "Run Full Pre-Earnings Workflow"

    read -p "Enter ticker (default: NVDA): " ticker
    ticker=${ticker:-NVDA}

    # Step 1: Train model if not already trained
    if [[ ! -f pricing/pre_earnings_straddle/data/model_coefficients.csv ]]; then
        print_info "Step 1/4: Training ML model..."
        uv run python pricing/pre_earnings_straddle/python/train/train_model.py
    else
        print_info "Step 1/4: Using existing model..."
    fi

    # Step 2: Fetch straddle data
    print_info "Step 2/4: Fetching straddle data..."
    uv run pricing/pre_earnings_straddle/python/fetch/fetch_straddle_data.py --ticker "$ticker"

    # Step 3: Run scanner
    print_info "Step 3/4: Running scanner..."
    eval $(opam env) && dune exec pre_earnings_straddle -- "$ticker"

    # Step 4: Generate visualization
    print_info "Step 4/4: Generating visualization..."
    uv run python pricing/pre_earnings_straddle/python/viz/plot_straddle.py \
        -t "$ticker" -d pricing/pre_earnings_straddle/data \
        -o pricing/pre_earnings_straddle/output/plots

    if [[ -f "pricing/pre_earnings_straddle/output/plots/${ticker}_straddle_analysis.png" ]]; then
        print_success "Plot saved to: pricing/pre_earnings_straddle/output/plots/${ticker}_straddle_analysis.png"
    fi

    print_success "Full pre-earnings workflow complete!"
}

collect_earnings_iv_snapshot() {
    print_header "Collect Daily Earnings IV Snapshot"

    pick_ticker_source "NVDA" || return

    print_info "Collecting earnings IV snapshot..."

    uv run pricing/pre_earnings_straddle/python/fetch/collect_earnings_iv.py \
        --tickers "$ticker_arg" \
        --data-dir pricing/pre_earnings_straddle/data

    if [ $? -eq 0 ]; then
        print_success "Snapshot collected"
        print_info "Data: pricing/pre_earnings_straddle/data/"
    else
        print_error "Snapshot collection failed"
    fi

    if [[ "$ticker_arg" == "all_liquid" || "$ticker_arg" == *.txt ]]; then
        echo ""
        echo -e "${YELLOW}Jump to:${NC}  ${GREEN}s)${NC} Skew Trading  ${GREEN}v)${NC} Variance Swaps  ${GREEN}l)${NC} Liquidity  ${GREEN}Enter)${NC} Stay"
        read -r jump
        case $jump in
            s) show_skew_trading_menu ;;
            v) show_variance_swaps_menu ;;
            l) show_liquidity_menu ;;
        esac
    fi
}

# Forward Factor (Term Structure Arbitrage) operations
show_forward_factor_menu() {
    while true; do
        clear
        echo -e "${BLUE}═══ Forward Factor (Term Structure Arbitrage) ═══${NC}\n"
        echo "Exploit volatility term structure anomalies using calendar spreads"
        echo ""
        echo -e "${GREEN}1)${NC} Fetch Options Chain (Multi-Expiration)"
        echo -e "${GREEN}2)${NC} Run Scanner (Detect Backwardation/Contango)"
        echo -e "${GREEN}3)${NC} Run Full Workflow"
        echo ""
        echo "DAILY PIPELINE:"
        echo -e "${GREEN}4)${NC} Collect Daily Snapshot"
        echo -e "${GREEN}5)${NC} Scan Signals (z-score watchlist)"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Pricing Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice (Enter=Full Workflow):${NC} "
        read -r choice

        case $choice in
            1) fetch_forward_factor_chain ;;
            2) run_forward_factor_scanner ;;
            3|"") run_forward_factor_workflow ;;
            4) collect_forward_factor_snapshot ;;
            5) scan_forward_factor_signals ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

fetch_forward_factor_chain() {
    print_header "Fetch Options Chain for Forward Factor"

    read -p "Enter ticker (default: AAPL): " ticker
    ticker=${ticker:-AAPL}

    print_info "Fetching multi-expiration options chain for $ticker..."

    uv run pricing/forward_factor/python/fetch/fetch_term_structure.py --ticker "$ticker"

    if [[ -f pricing/forward_factor/data/${ticker}_term_structure.csv ]]; then
        print_success "Term structure data saved to pricing/forward_factor/data/"
    else
        print_error "Failed to fetch term structure data"
    fi
}

run_forward_factor_scanner() {
    print_header "Run Forward Factor Scanner"

    read -p "Enter ticker (default: AAPL): " ticker
    ticker=${ticker:-AAPL}

    print_info "Running forward factor scanner for $ticker..."

    cd pricing/forward_factor && \
    opam exec -- dune exec ocaml/bin/main.exe -- "$ticker"

    print_success "Forward factor scan complete!"
}

run_forward_factor_workflow() {
    print_header "Run Full Forward Factor Workflow"

    read -p "Enter ticker (default: AAPL): " ticker
    ticker=${ticker:-AAPL}

    # Step 1: Fetch term structure
    print_info "Step 1/2: Fetching term structure data..."
    uv run pricing/forward_factor/python/fetch/fetch_term_structure.py --ticker "$ticker"

    # Step 2: Run scanner
    print_info "Step 2/2: Running scanner..."
    cd pricing/forward_factor && \
    opam exec -- dune exec ocaml/bin/main.exe -- "$ticker"

    print_success "Full forward factor workflow complete!"
}

collect_forward_factor_snapshot() {
    print_header "Collect Daily Forward Factor Snapshot"

    pick_ticker_source "AAPL" || return

    print_info "Collecting forward factor snapshot..."

    uv run pricing/forward_factor/python/fetch/collect_snapshot.py \
        --tickers "$ticker_arg" \
        --data-dir pricing/forward_factor/data

    if [ $? -eq 0 ]; then
        print_success "Snapshot collected"
        print_info "Data: pricing/forward_factor/data/"
    else
        print_error "Snapshot collection failed"
    fi
}

scan_forward_factor_signals() {
    print_header "Scan Forward Factor Signals"

    echo -e "${GREEN}1)${NC} Overall ranking (all tickers)"
    echo -e "${GREEN}2)${NC} By price segment"
    echo ""
    echo -e "${YELLOW}Enter your choice (Enter=By segment):${NC} "
    read -r scan_choice

    local scan_args="--quiet"
    case $scan_choice in
        1) ;;
        2|"") scan_args="$scan_args --segments" ;;
        *) scan_args="$scan_args --segments" ;;
    esac

    print_info "Scanning forward factor histories..."

    uv run pricing/forward_factor/python/scan_signals.py \
        $scan_args \
        --output pricing/forward_factor/output/signal_scan.csv

    if [ $? -eq 0 ]; then
        print_success "Scan complete"
        print_info "Results: pricing/forward_factor/output/signal_scan.csv"
    else
        print_error "Scan failed"
    fi
}

# Valuation Panel
show_panel_menu() {
    while true; do
        clear
        echo -e "${BLUE}═══ Valuation Panel (Multi-Model View) ═══${NC}\n"
        echo "Run multiple valuation models per ticker. Each model speaks for itself."
        echo ""
        echo -e "${GREEN}1)${NC} Custom Tickers"
        echo -e "${GREEN}2)${NC} Portfolio Holdings"
        echo -e "${GREEN}3)${NC} Full Watchlist (portfolio + watching)"
        echo -e "${GREEN}4)${NC} S&P 500 Top 50"
        echo -e "${GREEN}5)${NC} NASDAQ Top 30"
        echo ""
        echo -e "${GREEN}0)${NC} Back to Valuation Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) run_panel_custom ;;
            2) run_panel "portfolio" ;;
            3) run_panel "all_portfolio" ;;
            4) run_panel "sp50" ;;
            5) run_panel "nasdaq30" ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

run_panel_custom() {
    print_header "Panel: Custom Tickers"

    echo -e "${YELLOW}Enter tickers (comma-separated):${NC} "
    read -r tickers
    if [[ -z "$tickers" ]]; then
        print_error "No tickers provided."
        read -rp "Press Enter to continue..."
        return
    fi

    run_panel "$tickers"
}

run_panel() {
    local input="$1"
    local args=""

    # Determine if this is a universe or ticker list
    case "$input" in
        portfolio|watchlist|all_portfolio|sp50|nasdaq30|dow30|tech|healthcare|financials|energy|ai|liquid)
            args="--universe $input"
            ;;
        *)
            args="--tickers $input"
            ;;
    esac

    echo ""
    echo -e "${YELLOW}Include DCF Probabilistic (slower, Monte Carlo)? [y/N]:${NC} "
    read -r include_prob
    if [[ "$include_prob" =~ ^[Yy] ]]; then
        args="$args --include-probabilistic"
    fi

    print_info "Running valuation panel..."
    echo ""

    uv run valuation/panel/python/run.py $args

    echo ""
    read -rp "Press Enter to continue..."
}

# Run main
main
