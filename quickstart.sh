#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
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

    print_info "Installing OCaml packages: owl, yojson, csv, ppx_deriving, alcotest..."
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
    uv sync

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

    local default_tickers="AMZN,CBOE,CVX,IBKR,JPM,LLY,TAC"

    echo -e "\n${YELLOW}Enter ticker symbols for valuation (comma-separated):${NC}"
    echo -e "${BLUE}Press Enter for default (7 stocks): $default_tickers${NC}"
    read -r tickers

    if [[ -z "$tickers" ]]; then
        tickers="$default_tickers"
        print_info "Using default: 7 stocks"
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
                -python valuation/dcf_deterministic/python/fetch_financials.py
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
    if opam list csv owl yojson ppx_deriving alcotest 2>&1 | grep -q "installed"; then
        print_success "OCaml packages installed"
    else
        print_warning "Some OCaml packages may be missing"
    fi

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

    # Check build
    print_info "Checking builds..."
    if [[ -f "_build/default/pricing/regime_downside/ocaml/bin/main.exe" ]]; then
        print_success "Pricing model (regime_downside) built"
    else
        print_warning "Pricing model not built yet"
    fi

    if [[ -f "_build/default/valuation/dcf_deterministic/ocaml/bin/main.exe" ]]; then
        print_success "Valuation model (dcf_deterministic) built"
    else
        print_warning "Valuation model (dcf_deterministic) not built yet"
    fi

    if [[ -f "_build/default/valuation/dcf_probabilistic/ocaml/bin/main.exe" ]]; then
        print_success "Valuation model (dcf_probabilistic) built"
    else
        print_warning "Valuation model (dcf_probabilistic) not built yet"
    fi

    # Check data
    print_info "Checking data..."
    if [[ -f "pricing/regime_downside/data/sp500_returns.csv" ]]; then
        print_success "Benchmark data available"
    else
        print_warning "Benchmark data not fetched"
    fi

    # Check results
    print_info "Checking results..."
    if [[ -f "pricing/regime_downside/output/optimization_results.csv" ]]; then
        print_success "Optimization results available"
    else
        print_warning "No optimization results yet"
    fi

    local dcf_log_count=$(ls -1 valuation/dcf_deterministic/log/dcf_*.log 2>/dev/null | wc -l)
    if [[ $dcf_log_count -gt 0 ]]; then
        print_success "DCF deterministic results available ($dcf_log_count log(s))"
    else
        print_warning "No DCF deterministic results yet"
    fi

    local dcf_prob_log_count=$(ls -1 valuation/dcf_probabilistic/log/dcf_prob_*.log 2>/dev/null | wc -l)
    if [[ $dcf_prob_log_count -gt 0 ]]; then
        print_success "DCF probabilistic results available ($dcf_prob_log_count log(s))"
    else
        print_warning "No DCF probabilistic results yet"
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

    # List available logs
    echo -e "${YELLOW}Available valuations:${NC}"
    local i=1
    for log in "${log_files[@]}"; do
        local basename=$(basename "$log")
        echo "  $i) $basename"
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

    local default_tickers="AMZN,CBOE,CVX,IBKR,JPM,LLY,TAC"

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

    # List available logs
    echo -e "${YELLOW}Available valuations:${NC}"
    local i=1
    for log in "${log_files[@]}"; do
        local basename=$(basename "$log")
        echo "  $i) $basename"
        ((i++))
    done
    echo ""

    echo -e "${YELLOW}Enter number to view (or press Enter for most recent):${NC}"
    read -r choice

    local selected_log
    if [[ -z "$choice" ]]; then
        # Get most recent log
        selected_log=$(ls -t valuation/dcf_probabilistic/log/dcf_prob_*.log 2>/dev/null | head -1)
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

    uv run valuation/dcf_probabilistic/python/viz/plot_results.py \
        --output-dir valuation/dcf_probabilistic/output/data \
        --viz-dir valuation/dcf_probabilistic/output

    if [[ $? -eq 0 ]]; then
        local png_count=$(ls -1 valuation/dcf_probabilistic/output/*.png 2>/dev/null | wc -l)
        print_success "Visualizations complete. $png_count plot(s) generated"
        echo ""
        echo -e "${BLUE}Plots saved to:${NC} valuation/dcf_probabilistic/output/"
        ls -1 valuation/dcf_probabilistic/output/*.png 2>/dev/null | while read -r file; do
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

    # Generate frontiers for both FCFE and FCFF methods
    for method in fcfe fcff; do
        print_info "Generating $n_portfolios random portfolios using ${method^^} method..."
        echo ""

        uv run valuation/dcf_probabilistic/python/viz/plot_frontier.py \
            --output-dir valuation/dcf_probabilistic/output/data \
            --viz-dir valuation/dcf_probabilistic/output \
            --n-portfolios "$n_portfolios" \
            --method "$method"

        if [[ $? -ne 0 ]]; then
            print_error "Frontier generation failed for ${method^^}"
            return 1
        fi
        echo ""
    done

    print_success "Portfolio frontier generation complete for both FCFE and FCFF"
    echo ""
    echo -e "${BLUE}Plots saved to:${NC} valuation/dcf_probabilistic/output/portfolio/"
    echo ""
    echo -e "${BLUE}FCFE plots:${NC}"
    ls -1 valuation/dcf_probabilistic/output/portfolio/fcfe/*.png 2>/dev/null | while read -r file; do
        echo "  - $(basename "$file")"
    done
    echo ""
    echo -e "${BLUE}FCFF plots:${NC}"
    ls -1 valuation/dcf_probabilistic/output/portfolio/fcff/*.png 2>/dev/null | while read -r file; do
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

# Clean pricing model output data
clean_pricing_data() {
    print_header "Cleaning Pricing Model Data"

    echo -e "\n${YELLOW}This will remove pricing model data and outputs (benchmark, assets, results). Continue? (y/n):${NC}"
    read -r confirm
    if [[ "$confirm" != "y" ]]; then
        print_warning "Clean cancelled"
        return 0
    fi

    print_info "Removing pricing input data (benchmark and assets)..."
    rm -f pricing/regime_downside/data/*.csv
    rm -f pricing/regime_downside/data/params_temp.json

    print_info "Removing pricing output files..."
    rm -f pricing/regime_downside/output/*.csv
    rm -f pricing/regime_downside/output/*.png

    print_success "Pricing data and outputs cleaned"
}

# Clean DCF deterministic output data
clean_dcf_deterministic_data() {
    print_header "Cleaning DCF Deterministic Output Data"

    echo -e "\n${YELLOW}This will remove DCF deterministic logs, CSVs, and visualizations. Continue? (y/n):${NC}"
    read -r confirm
    if [[ "$confirm" != "y" ]]; then
        print_warning "Clean cancelled"
        return 0
    fi

    print_info "Removing DCF deterministic log files..."
    rm -f valuation/dcf_deterministic/log/*.log

    print_info "Removing DCF deterministic output files..."
    rm -rf valuation/dcf_deterministic/output/valuation/
    rm -rf valuation/dcf_deterministic/output/sensitivity/

    print_success "DCF deterministic output data cleaned"
}

# Clean DCF probabilistic output data
clean_dcf_probabilistic_data() {
    print_header "Cleaning DCF Probabilistic Output Data"

    echo -e "\n${YELLOW}This will remove DCF probabilistic logs, CSVs, and visualizations. Continue? (y/n):${NC}"
    read -r confirm
    if [[ "$confirm" != "y" ]]; then
        print_warning "Clean cancelled"
        return 0
    fi

    print_info "Removing DCF probabilistic log files..."
    rm -f valuation/dcf_probabilistic/log/*.log

    print_info "Removing DCF probabilistic output files..."
    rm -rf valuation/dcf_probabilistic/output/data/
    rm -rf valuation/dcf_probabilistic/output/single_asset/
    rm -rf valuation/dcf_probabilistic/output/portfolio/

    print_success "DCF probabilistic output data cleaned"
}

# Clean temporary files
clean_temp_files() {
    print_header "Cleaning Temporary Files"

    echo -e "\n${YELLOW}This will remove temporary files in /tmp. Continue? (y/n):${NC}"
    read -r confirm
    if [[ "$confirm" != "y" ]]; then
        print_warning "Clean cancelled"
        return 0
    fi

    print_info "Removing temporary files..."
    rm -f /tmp/lp_problem.json
    rm -f /tmp/lp_solution.json
    rm -f /tmp/dcf_market_data_*.json
    rm -f /tmp/dcf_financial_data_*.json

    print_success "Temporary files cleaned"
}

# Clean all (build artifacts + all output data)
clean_all() {
    print_header "Cleaning All Build Artifacts and Output Data"

    echo -e "\n${YELLOW}This will remove ALL build artifacts and output data. Continue? (y/n):${NC}"
    read -r confirm
    if [[ "$confirm" != "y" ]]; then
        print_warning "Clean cancelled"
        return 0
    fi

    print_info "Cleaning build artifacts..."
    opam exec -- dune clean

    print_info "Removing pricing data (benchmark and assets)..."
    rm -f pricing/regime_downside/data/*.csv
    rm -f pricing/regime_downside/data/params_temp.json

    print_info "Removing pricing output files..."
    rm -f pricing/regime_downside/output/*.csv
    rm -f pricing/regime_downside/output/*.png

    print_info "Removing DCF deterministic files..."
    rm -f valuation/dcf_deterministic/log/*.log
    rm -rf valuation/dcf_deterministic/output/valuation/
    rm -rf valuation/dcf_deterministic/output/sensitivity/

    print_info "Removing DCF probabilistic files..."
    rm -f valuation/dcf_probabilistic/log/*.log
    rm -rf valuation/dcf_probabilistic/output/data/
    rm -rf valuation/dcf_probabilistic/output/single_asset/
    rm -rf valuation/dcf_probabilistic/output/portfolio/

    print_info "Removing temporary files..."
    rm -f /tmp/lp_problem.json
    rm -f /tmp/lp_solution.json
    rm -f /tmp/dcf_market_data_*.json
    rm -f /tmp/dcf_financial_data_*.json

    print_success "All artifacts and output data cleaned"
}

# Main menu
show_main_menu() {
    clear
    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════╗"
    echo "║                                              ║"
    echo "║                   ATEMOYA                    ║"
    echo "║                                              ║"
    echo "║          github.com/cb-g/atemoya             ║"
    echo "║                                              ║"
    echo "╚══════════════════════════════════════════════╝"
    echo -e "${NC}"

    echo -e "${GREEN}1)${NC} Installation"
    echo -e "${GREEN}2)${NC} Maintenance"
    echo -e "${GREEN}3)${NC} Run"
    echo -e "${GREEN}4)${NC} Quit"
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
        echo "1) Check System Status"
        echo "2) Install OCaml Dependencies"
        echo "3) Install Python Dependencies"
        echo "4) Build Project"
        echo "5) Run Tests"
        echo "6) Do Everything"
        echo ""
        echo "0) Back to Main Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) check_status ;;
            2) install_ocaml_deps ;;
            3) install_python_deps ;;
            4) build_project ;;
            5) run_tests ;;
            6) install_all ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

# Maintenance submenu
show_maintenance_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Maintenance ═══${NC}\n"
        echo "1) Clean Build Artifacts"
        echo "2) Clean Pricing Data (benchmark, assets, results)"
        echo "3) Clean DCF Deterministic Data (logs, results, visualizations)"
        echo "4) Clean DCF Probabilistic Data (logs, results, visualizations)"
        echo "5) Clean Temporary Files"
        echo "6) Clean All"
        echo ""
        echo "0) Back to Main Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) clean_build_artifacts ;;
            2) clean_pricing_data ;;
            3) clean_dcf_deterministic_data ;;
            4) clean_dcf_probabilistic_data ;;
            5) clean_temp_files ;;
            6) clean_all ;;
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
        echo "1) Pricing"
        echo "2) Valuation"
        echo ""
        echo "0) Back to Main Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) show_pricing_menu ;;
            2) show_valuation_menu ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

# Pricing submenu
show_pricing_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Pricing ═══${NC}\n"
        echo "1) Regime-Aware Downside Optimization"
        echo "   Constructs portfolios that adapt to market regimes (normal/stress/crisis)"
        echo "   using exponentially-weighted moving average beta estimation and conditional"
        echo "   value-at-risk (CVaR) optimization to minimize downside risk"
        echo ""
        echo "0) Back to Run Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) show_regime_downside_menu ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

# Regime-aware downside optimization operations
show_regime_downside_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Regime-Aware Downside Optimization ═══${NC}\n"
        echo "1) Fetch Benchmark Data (S&P 500)"
        echo "2) Fetch Asset Data"
        echo "3) Run Portfolio Optimization"
        echo "4) Generate Plots"
        echo "5) Run Full Workflow"
        echo ""
        echo "0) Back to Pricing"
        echo ""
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) fetch_benchmark_data ;;
            2) fetch_asset_data ;;
            3) run_optimization ;;
            4) generate_plots ;;
            5) run_full_workflow ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

# Valuation submenu
show_valuation_menu() {
    while true; do
        echo ""
        echo -e "${BLUE}═══ Valuation ═══${NC}\n"
        echo "1) DCF Deterministic"
        echo "   Point estimates of intrinsic value using free cash flow (FCFE/FCFF) with"
        echo "   sensitivity analysis across growth rates, discount rates, and terminal growth"
        echo ""
        echo "2) DCF Probabilistic (Monte Carlo)"
        echo "   Probabilistic valuation with uncertainty quantification via Monte Carlo simulation,"
        echo "   generating distributions of intrinsic value and portfolio efficient frontiers"
        echo ""
        echo "0) Back to Run Menu"
        echo ""
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) show_dcf_deterministic_menu ;;
            2) show_dcf_probabilistic_menu ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
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
    local viz_dir="valuation/dcf_deterministic/output/valuation"

    if [[ ! -d "$log_dir" ]] || [[ -z "$(ls -A $log_dir/*.log 2>/dev/null)" ]]; then
        print_error "No valuation results found. Run deterministic DCF valuation first."
        return 1
    fi

    # Create output directory
    mkdir -p "$viz_dir"

    print_info "Generating valuation plots (light and dark modes)..."
    echo ""

    uv run python valuation/dcf_deterministic/python/viz/plot_results.py \
        --log-dir "$log_dir" \
        --viz-dir "$viz_dir" \
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
    local csv_dir="valuation/dcf_deterministic/output/sensitivity/data"
    local viz_dir="valuation/dcf_deterministic/output/sensitivity/plots"

    if [[ ! -d "$csv_dir" ]] || [[ -z "$(ls -A $csv_dir/*.csv 2>/dev/null)" ]]; then
        print_error "No sensitivity CSV files found. Run sensitivity analyses first."
        return 1
    fi

    # Create output directory
    mkdir -p "$viz_dir"

    print_info "Generating sensitivity plots (light and dark modes, 4-panel analysis for each ticker)..."
    echo ""

    uv run python valuation/dcf_deterministic/python/viz/plot_results.py \
        --log-dir "$log_dir" \
        --viz-dir "$viz_dir" \
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
        echo "1) Run Valuation"
        echo "2) View Valuation Results"
        echo "3) Run Sensitivity Analyses"
        echo "4) Generate Valuation Plots"
        echo "5) Generate Sensitivity Plots"
        echo "6) Do Everything"
        echo ""
        echo "0) Back to Valuation"
        echo ""
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) run_dcf_valuation ;;
            2) view_dcf_results ;;
            3) run_dcf_sensitivity_analyses ;;
            4) generate_dcf_valuation_plots ;;
            5) generate_dcf_sensitivity_plots ;;
            6) run_dcf_deterministic_all ;;
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
        echo "1) Run Valuation"
        echo "2) View Results"
        echo "3) Generate Visualizations (KDE plots)"
        echo "4) Generate Portfolio Efficient Frontier"
        echo "5) Do Everything"
        echo ""
        echo "0) Back to Valuation"
        echo ""
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) run_dcf_probabilistic ;;
            2) view_dcf_probabilistic_results ;;
            3) generate_dcf_visualizations ;;
            4) generate_portfolio_frontier ;;
            5) run_dcf_probabilistic_all ;;
            0) clear; return ;;
            *) print_error "Invalid choice." ;;
        esac
    done
}

# Main loop
main() {
    check_project_root

    while true; do
        show_main_menu
        echo -e "${YELLOW}Enter your choice:${NC} "
        read -r choice

        case $choice in
            1) show_installation_menu ;;
            2) show_maintenance_menu ;;
            3) show_run_menu ;;
            4)
                clear
                echo ""
                print_info "Goodbye!"
                echo ""
                exit 0
                ;;
            *)
                print_error "Invalid choice. Please enter 1-4."
                ;;
        esac
    done
}

# Run main
main
