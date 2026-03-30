#!/bin/bash
# =============================================================================
# Echo Daily Runner — Orchestration Script
#
# Runs Echo prediction pipeline alongside election_no_trader.
# Designed to run on MagicQuant_Server1 via cron or manual SSH.
#
# Usage:
#   ./run_echo_daily.sh                    # Full run (scan + analyze all)
#   ./run_echo_daily.sh --scan-only        # Just scan, don't analyze
#   ./run_echo_daily.sh --quick            # Quick mode (single agent)
#   ./run_echo_daily.sh --max-markets 5    # Limit to 5 markets (testing)
#   ./run_echo_daily.sh --compare          # Compare Echo vs bot (after bot runs)
#
# Cron example (run daily at 10:00 UTC):
#   0 10 * * * /path/to/run_echo_daily.sh >> /path/to/echo_cron.log 2>&1
# =============================================================================

set -euo pipefail

# --- Configuration ---
REPO_DIR="/Users/owl/polymarket/TheMagicQuant/polymarket"
ECHO_DIR="$REPO_DIR/echo"
TRADING_DIR="$REPO_DIR/trading"
DATE=$(date -u +"%Y-%m-%d")
LOG_FILE="$ECHO_DIR/echo_output/$DATE/run.log"

# Ensure output directory exists
mkdir -p "$ECHO_DIR/echo_output/$DATE"

echo "=============================================" | tee -a "$LOG_FILE"
echo "Echo Daily Run — $DATE $(date -u +"%H:%M:%S UTC")" | tee -a "$LOG_FILE"
echo "=============================================" | tee -a "$LOG_FILE"

# --- Step 1: Scan markets ---
echo "" | tee -a "$LOG_FILE"
echo "[Step 1/3] Scanning markets..." | tee -a "$LOG_FILE"

cd "$REPO_DIR"
python3 -m echo.echo_daily_runner --scan-only "$@" 2>&1 | tee -a "$LOG_FILE"

BATCH_FILE="$ECHO_DIR/echo_output/$DATE/batch.json"
if [ ! -f "$BATCH_FILE" ]; then
    echo "ERROR: Batch file not created. Aborting." | tee -a "$LOG_FILE"
    exit 1
fi

NUM_MARKETS=$(python3 -c "import json; print(json.load(open('$BATCH_FILE'))['num_markets'])")
echo "Found $NUM_MARKETS candidate markets." | tee -a "$LOG_FILE"

# Check if scan-only was requested
if echo "$@" | grep -q "\-\-scan-only"; then
    echo "Scan-only mode. Exiting." | tee -a "$LOG_FILE"
    exit 0
fi

# Check if compare was requested
if echo "$@" | grep -q "\-\-compare"; then
    echo "" | tee -a "$LOG_FILE"
    echo "[Compare] Running Echo vs Bot comparison..." | tee -a "$LOG_FILE"
    python3 -m echo.echo_daily_runner --compare --date "$DATE" 2>&1 | tee -a "$LOG_FILE"
    exit 0
fi

# --- Step 2: Run Echo analysis ---
echo "" | tee -a "$LOG_FILE"
echo "[Step 2/3] Running Echo analysis on $NUM_MARKETS markets..." | tee -a "$LOG_FILE"
echo "This will take approximately $((NUM_MARKETS * 5)) minutes." | tee -a "$LOG_FILE"

# Pass through any extra args (--quick, --max-markets, etc.)
python3 -m echo.echo_daily_runner --analyze-batch "$BATCH_FILE" "$@" 2>&1 | tee -a "$LOG_FILE"

# --- Step 3: Compare with bot (if bot has run today) ---
TRADE_LOG="$TRADING_DIR/trade_log.jsonl"
if [ -f "$TRADE_LOG" ] && grep -q "$DATE" "$TRADE_LOG" 2>/dev/null; then
    echo "" | tee -a "$LOG_FILE"
    echo "[Step 3/3] Comparing Echo vs bot trades..." | tee -a "$LOG_FILE"
    python3 -m echo.echo_daily_runner --compare --date "$DATE" 2>&1 | tee -a "$LOG_FILE"
else
    echo "" | tee -a "$LOG_FILE"
    echo "[Step 3/3] No bot trades for today. Skipping comparison." | tee -a "$LOG_FILE"
    echo "Run with --compare after the bot trades to see comparison." | tee -a "$LOG_FILE"
fi

echo "" | tee -a "$LOG_FILE"
echo "=============================================" | tee -a "$LOG_FILE"
echo "Echo Daily Run Complete — $(date -u +"%H:%M:%S UTC")" | tee -a "$LOG_FILE"
echo "Output: $ECHO_DIR/echo_output/$DATE/" | tee -a "$LOG_FILE"
echo "=============================================" | tee -a "$LOG_FILE"
