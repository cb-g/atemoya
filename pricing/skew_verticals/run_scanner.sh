#!/bin/bash
# Skew Verticals Scanner - Complete Workflow
#
# Usage: ./run_scanner.sh TICKER

set -e

if [ -z "$1" ]; then
    echo "Usage: ./run_scanner.sh TICKER"
    echo ""
    echo "Example: ./run_scanner.sh AAPL"
    exit 1
fi

TICKER=$1
BASE_DIR="pricing/skew_verticals"
DATA_DIR="$BASE_DIR/data"

echo ""
echo "╔════════════════════════════════════════════════════╗"
echo "║  Skew Vertical Spreads Scanner                     ║"
echo "╚════════════════════════════════════════════════════╝"
echo ""
echo "Ticker: $TICKER"
echo ""

# Create data directory
mkdir -p "$DATA_DIR"

# Step 1: Fetch options chain
echo "Step 1/3: Fetching options chain..."
uv run "$BASE_DIR/python/fetch/fetch_options_chain.py" --ticker "$TICKER" --output-dir "$DATA_DIR"

if [ $? -ne 0 ]; then
    echo "✗ Failed to fetch options chain"
    exit 1
fi

# Step 2: Fetch price history
echo ""
echo "Step 2/3: Fetching price history..."
uv run "$BASE_DIR/python/fetch/fetch_prices.py" --ticker "$TICKER" --days 252 --output-dir "$DATA_DIR"

if [ $? -ne 0 ]; then
    echo "✗ Failed to fetch price history"
    exit 1
fi

# Step 3: Run scanner
echo ""
echo "Step 3/3: Running scanner..."
echo ""

# Create output directory and log file
OUTPUT_DIR="$BASE_DIR/output"
mkdir -p "$OUTPUT_DIR"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
LOG_FILE="$OUTPUT_DIR/${TICKER}_scan_${TIMESTAMP}.log"

# Run scanner and capture output to both console and log file
(cd "$BASE_DIR/ocaml" && dune exec bin/main.exe "$TICKER" 2>&1) | tee "$LOG_FILE"

echo ""
echo "✓ Scan complete!"
echo "✓ Console output saved to: $LOG_FILE"
echo ""
echo "To log this scan to the forward-testing database, manually run:"
echo "  uv run $BASE_DIR/python/tracking/trade_logger.py [options]"
echo ""
echo "To view trade history:"
echo "  uv run $BASE_DIR/python/tracking/view_history.py"
echo ""
