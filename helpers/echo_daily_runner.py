#!/usr/bin/env python3
"""
Echo Daily Runner — Paper-trade Echo predictions alongside election_no_trader.

Workflow:
  1. Scans the same markets as election_no_trader (shared filters)
  2. For each candidate market, runs Echo analysis via `claude` CLI
  3. Logs predictions to echo/predictions.jsonl
  4. Generates daily comparison report

Usage:
  # Full run: scan + analyze + report
  python echo_daily_runner.py --bankroll 5000

  # Scan only (generate batch file without running Echo)
  python echo_daily_runner.py --bankroll 5000 --scan-only

  # Analyze from existing batch file
  python echo_daily_runner.py --analyze-batch echo_output/2026-03-30/batch.json

  # Generate comparison report
  python echo_daily_runner.py --compare --date 2026-03-30

  # Quick mode (single-agent instead of map-reduce)
  python echo_daily_runner.py --bankroll 5000 --quick
"""

import os
import sys
import json
import time
import subprocess
import argparse
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add paths for shared imports
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "trading"))
sys.path.insert(0, str(REPO_ROOT / "data_preparation"))

import requests

# Polymarket APIs
GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"

# Election tag IDs (subset — most important)
ELECTION_TAG_IDS = [2, 144, 1597, 101206, 100265, 101970]

ECHO_OUTPUT_DIR = Path(__file__).parent / "echo_output"
PREDICTIONS_FILE = Path(__file__).parent / "predictions.jsonl"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("echo_daily")


def safe_request(url, params=None, timeout=10, retries=3):
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                time.sleep(2 ** attempt)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt < retries - 1:
                time.sleep(1)
    return None


# ---------------------------------------------------------------------------
# Market scanning — mirrors election_no_trader's scanner
# ---------------------------------------------------------------------------

def load_filters():
    """Import the shared election filters."""
    try:
        from shared.election_filters import (
            is_strict_elon_social_market,
            is_strict_election_outcome,
            is_social_media_market,
            is_elon_social_media_market,
        )
        return {
            "strict_elon_social": is_strict_elon_social_market,
            "strict": is_strict_election_outcome,
        }
    except ImportError:
        log.warning("Could not import shared election filters. Using fallback.")
        return None


def scan_markets(filter_mode="strict_elon_social") -> List[Dict]:
    """
    Scan Polymarket for candidate markets using the same logic as
    election_no_trader. Returns list of market dicts.
    """
    filters = load_filters()
    filter_fn = filters.get(filter_mode) if filters else None

    all_markets = []
    seen_cids = set()

    # Strategy 1: Fetch by election tag IDs
    for tag_id in ELECTION_TAG_IDS:
        data = safe_request(f"{GAMMA_BASE}/events", params={
            "tag_id": tag_id, "active": "true", "closed": "false", "limit": 100
        })
        if data:
            for event in data:
                for m in event.get("markets", []):
                    cid = m.get("conditionId")
                    if cid and cid not in seen_cids and not m.get("closed"):
                        seen_cids.add(cid)
                        m["_event_title"] = event.get("title", "")
                        m["_event_slug"] = event.get("slug", "")
                        m["_tags"] = event.get("tags", [])
                        all_markets.append(m)

    # Strategy 2: Paginate active events
    for offset in range(0, 500, 100):
        data = safe_request(f"{GAMMA_BASE}/events", params={
            "active": "true", "closed": "false", "limit": 100, "offset": offset
        })
        if not data:
            break
        for event in data:
            for m in event.get("markets", []):
                cid = m.get("conditionId")
                if cid and cid not in seen_cids and not m.get("closed"):
                    seen_cids.add(cid)
                    m["_event_title"] = event.get("title", "")
                    m["_event_slug"] = event.get("slug", "")
                    m["_tags"] = event.get("tags", [])
                    all_markets.append(m)

    # Apply filters
    candidates = []
    for m in all_markets:
        question = m.get("question", "")
        slug = m.get("slug", "") or m.get("_event_slug", "")
        tags = m.get("_tags", [])
        tag_labels = [
            str(t.get("label", t) if isinstance(t, dict) else t)
            for t in tags
        ]

        # Apply filter function if available
        if filter_fn:
            neg_risk = m.get("negRisk", False)
            try:
                if not filter_fn(tag_labels, slug, question, neg_risk):
                    continue
            except TypeError:
                # Some filter functions have different signatures
                if not filter_fn(tag_labels, slug, question):
                    continue

        # Parse prices
        outcomes = m.get("outcomes", [])
        if isinstance(outcomes, str):
            outcomes = json.loads(outcomes)
        prices_raw = m.get("outcomePrices", [])
        if isinstance(prices_raw, str):
            prices_raw = json.loads(prices_raw)

        prices = {}
        for i, o in enumerate(outcomes):
            if i < len(prices_raw):
                try:
                    prices[o] = float(prices_raw[i])
                except (ValueError, TypeError):
                    pass

        yes_price = prices.get("Yes", prices.get(outcomes[0], None)) if outcomes else None
        if yes_price is None:
            continue

        # Check IP range [0.10, 0.60) — same as bot
        if not (0.10 <= yes_price < 0.60):
            continue

        # Parse end date and TTE
        end_date_str = m.get("endDate") or m.get("end_date_iso")
        tte_days = None
        if end_date_str:
            try:
                end_dt = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
                tte_days = max(0, (end_dt - datetime.now(timezone.utc)).total_seconds() / 86400)
            except (ValueError, TypeError):
                pass

        # TTE filter: 1-60 days
        if tte_days is None or not (1 <= tte_days <= 60):
            continue

        # Volume
        volume = float(m.get("volume", 0) or 0)

        candidates.append({
            "condition_id": m.get("conditionId"),
            "question": question,
            "slug": slug,
            "event_title": m.get("_event_title", ""),
            "event_slug": m.get("_event_slug", ""),
            "outcomes": outcomes,
            "yes_price": round(yes_price, 4),
            "no_price": round(1 - yes_price, 4),
            "volume": volume,
            "tte_days": round(tte_days, 1),
            "end_date": end_date_str,
            "tags": tag_labels[:5],
            "market_type": "social" if any(
                kw in question.lower()
                for kw in ["tweet", "post", "subscriber", "follower", "tiktok"]
            ) else "election",
        })

    # Sort by volume descending
    candidates.sort(key=lambda x: x["volume"], reverse=True)
    return candidates


# ---------------------------------------------------------------------------
# Echo analysis via claude CLI
# ---------------------------------------------------------------------------

def run_echo_analysis(market: Dict, mode: str = "map_reduce") -> Optional[Dict]:
    """
    Run Echo analysis on a single market using `claude` CLI.
    Returns parsed prediction dict or None on failure.
    """
    slug = market.get("event_slug") or market.get("slug")
    question = market["question"]
    yes_price = market["yes_price"]
    tte = market["tte_days"]

    quick_flag = " --quick" if mode == "quick" else ""

    # Use the /echo skill via claude CLI
    prompt = f"/echo{quick_flag} {slug}" if slug else f"/echo{quick_flag} {market['condition_id']}"

    log.info(f"Running Echo on: {question[:60]}... (YES={yes_price:.1%}, TTE={tte:.0f}d)")

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text"],
            capture_output=True,
            text=True,
            timeout=600,  # 10 min max per market
            cwd=str(REPO_ROOT),
        )

        if result.returncode != 0:
            log.error(f"Claude CLI failed: {result.stderr[:200]}")
            return None

        output = result.stdout

        # Parse Echo probability from output
        prediction = parse_echo_output(output, market)
        return prediction

    except subprocess.TimeoutExpired:
        log.error(f"Timeout analyzing: {question[:60]}")
        return None
    except FileNotFoundError:
        log.error("claude CLI not found. Install Claude Code first.")
        return None


def parse_echo_output(output: str, market: Dict) -> Optional[Dict]:
    """
    Parse the Echo prediction from claude CLI output.
    Looks for the structured report format.
    """
    import re

    prediction = {
        "market_id": market["condition_id"],
        "question": market["question"],
        "market_price_at_prediction": market["yes_price"],
        "domain": classify_domain(market),
        "mode": "map_reduce",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tte_days": market["tte_days"],
        "market_type": market.get("market_type", "election"),
        "event_title": market.get("event_title", ""),
    }

    # Try to extract probability from various formats
    # Format 1: "Echo probability | **XX%**"
    prob_match = re.search(r'Echo probability\s*\|\s*\*?\*?(\d+(?:\.\d+)?)\%', output)
    if not prob_match:
        # Format 2: "PROBABILITY_ESTIMATE: 0.XX"
        prob_match = re.search(r'PROBABILITY_ESTIMATE:\s*0?\.?(\d+)', output)
    if not prob_match:
        # Format 3: "Echo probability: XX%"
        prob_match = re.search(r'Echo probability[:\s]+(\d+(?:\.\d+)?)\%', output)
    if not prob_match:
        # Format 4: any "XX%" near "Echo" or "probability"
        prob_match = re.search(r'(?:echo|probability|estimate)[^%]*?(\d{1,3}(?:\.\d+)?)\%', output, re.IGNORECASE)

    if prob_match:
        prob_str = prob_match.group(1)
        prob = float(prob_str)
        if prob > 1:
            prob = prob / 100.0  # Convert from percentage
        prediction["echo_probability"] = round(prob, 4)
    else:
        log.warning(f"Could not parse probability from output for {market['question'][:40]}")
        return None

    # Try to extract confidence
    conf_match = re.search(r'Confidence\s*\|\s*(\w+)', output)
    if not conf_match:
        conf_match = re.search(r'CONFIDENCE:\s*(\w+)', output)
    prediction["confidence"] = conf_match.group(1).lower() if conf_match else "medium"

    # Try to extract confidence interval
    ci_match = re.search(r'90% CI\s*\|\s*\[(\d+(?:\.\d+)?)\%?,?\s*(\d+(?:\.\d+)?)\%?\]', output)
    if ci_match:
        low = float(ci_match.group(1))
        high = float(ci_match.group(2))
        if low > 1:
            low /= 100
        if high > 1:
            high /= 100
        prediction["confidence_interval"] = [round(low, 4), round(high, 4)]

    # Try to extract fragility
    frag_match = re.search(r'Fragility\s*\|\s*(\d+(?:\.\d+)?)', output)
    if not frag_match:
        frag_match = re.search(r'fragility[:\s]+(\d+(?:\.\d+)?)', output, re.IGNORECASE)
    prediction["fragility_score"] = float(frag_match.group(1)) if frag_match else 0.5

    # Count evidence items
    evidence_count = len(re.findall(r'\[(?:DIRECT|SUPPORTING|CONTRADICTING)\]', output))
    prediction["num_evidence_items"] = evidence_count

    # Store raw output (truncated) for debugging
    prediction["raw_output_preview"] = output[:500]

    return prediction


def classify_domain(market: Dict) -> str:
    """Classify market into domain based on question and tags."""
    q = market["question"].lower()
    tags = " ".join(market.get("tags", [])).lower()

    crypto_terms = ["bitcoin", "ethereum", "crypto", "btc", "eth", "solana"]
    if any(t in q or t in tags for t in crypto_terms):
        return "crypto"

    sports_terms = ["nba", "nfl", "mlb", "fifa", "championship", "tournament"]
    if any(t in q or t in tags for t in sports_terms):
        return "sports"

    econ_terms = ["fed", "interest rate", "gdp", "inflation", "recession"]
    if any(t in q or t in tags for t in econ_terms):
        return "economics"

    return "politics"


# ---------------------------------------------------------------------------
# Batch operations
# ---------------------------------------------------------------------------

def save_batch(candidates: List[Dict], output_dir: Path) -> Path:
    """Save scanned candidates as a batch file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    batch_path = output_dir / "batch.json"
    with open(batch_path, "w") as f:
        json.dump({
            "scan_time": datetime.now(timezone.utc).isoformat(),
            "num_markets": len(candidates),
            "markets": candidates,
        }, f, indent=2, default=str)
    log.info(f"Saved {len(candidates)} markets to {batch_path}")
    return batch_path


def load_batch(batch_path: Path) -> List[Dict]:
    """Load a batch file."""
    with open(batch_path) as f:
        data = json.load(f)
    return data["markets"]


def run_batch(candidates: List[Dict], mode: str, output_dir: Path) -> List[Dict]:
    """Run Echo analysis on all candidates. Returns predictions."""
    predictions = []
    total = len(candidates)

    for i, market in enumerate(candidates, 1):
        log.info(f"[{i}/{total}] Analyzing: {market['question'][:60]}...")

        prediction = run_echo_analysis(market, mode=mode)

        if prediction:
            predictions.append(prediction)
            # Log to predictions file
            log_prediction(prediction)

            # Save individual result
            result_path = output_dir / f"{market['condition_id'][:16]}.json"
            with open(result_path, "w") as f:
                json.dump(prediction, f, indent=2, default=str)

            echo_prob = prediction.get("echo_probability", 0)
            market_price = market["yes_price"]
            delta = echo_prob - market_price
            direction = "+" if delta > 0 else ""
            log.info(
                f"  -> Echo: {echo_prob:.1%} vs Market: {market_price:.1%} "
                f"({direction}{delta:.1%})"
            )
        else:
            log.warning(f"  -> Failed to get prediction")

        # Small delay between markets to be nice to APIs
        if i < total:
            time.sleep(2)

    return predictions


def log_prediction(prediction: Dict):
    """Append prediction to the JSONL log."""
    clean = {k: v for k, v in prediction.items() if k != "raw_output_preview"}
    with open(PREDICTIONS_FILE, "a") as f:
        f.write(json.dumps(clean, default=str) + "\n")


# ---------------------------------------------------------------------------
# Comparison & reporting
# ---------------------------------------------------------------------------

def generate_daily_report(predictions: List[Dict], candidates: List[Dict],
                          date_str: str) -> str:
    """Generate a daily comparison report."""
    lines = [
        f"# Echo Daily Report — {date_str}",
        "",
        f"Markets scanned: {len(candidates)}",
        f"Predictions generated: {len(predictions)}",
        "",
    ]

    if not predictions:
        lines.append("No predictions generated.")
        return "\n".join(lines)

    # Summary stats
    echo_probs = [p["echo_probability"] for p in predictions if "echo_probability" in p]
    market_prices = [p["market_price_at_prediction"] for p in predictions]
    deltas = [e - m for e, m in zip(echo_probs, market_prices)]

    lines.append("## Summary")
    lines.append(f"- Avg Echo probability: {sum(echo_probs)/len(echo_probs):.1%}")
    lines.append(f"- Avg market price: {sum(market_prices)/len(market_prices):.1%}")
    lines.append(f"- Avg delta (Echo - Market): {sum(deltas)/len(deltas):+.1%}")
    lines.append("")

    # Disagreements (>10% delta)
    disagreements = [
        (p, d) for p, d in zip(predictions, deltas) if abs(d) > 0.10
    ]
    if disagreements:
        lines.append(f"## Major Disagreements (|delta| > 10%)")
        lines.append("")
        lines.append("| Market | Echo | Market | Delta |")
        lines.append("|--------|------|--------|-------|")
        for p, d in sorted(disagreements, key=lambda x: abs(x[1]), reverse=True):
            q = p["question"][:50]
            lines.append(
                f"| {q} | {p['echo_probability']:.1%} | "
                f"{p['market_price_at_prediction']:.1%} | {d:+.1%} |"
            )
        lines.append("")

    # All predictions table
    lines.append("## All Predictions")
    lines.append("")
    lines.append("| Market | Echo | Mkt | Delta | Conf | Domain |")
    lines.append("|--------|------|-----|-------|------|--------|")
    for p, d in sorted(zip(predictions, deltas), key=lambda x: abs(x[1]), reverse=True):
        q = p["question"][:45]
        lines.append(
            f"| {q} | {p['echo_probability']:.1%} | "
            f"{p['market_price_at_prediction']:.1%} | {d:+.1%} | "
            f"{p.get('confidence', '?')} | {p.get('domain', '?')} |"
        )
    lines.append("")

    # Paper trade recommendations
    lines.append("## Paper Trade Signals")
    lines.append("")
    lines.append("Markets where Echo suggests YES is overpriced (buy NO):")
    overpriced = [
        (p, d) for p, d in zip(predictions, deltas)
        if d < -0.05  # Echo thinks YES is 5%+ lower than market
    ]
    if overpriced:
        for p, d in sorted(overpriced, key=lambda x: x[1]):
            lines.append(
                f"- **{p['question'][:60]}**: Echo {p['echo_probability']:.1%} "
                f"vs Mkt {p['market_price_at_prediction']:.1%} ({d:+.1%})"
            )
    else:
        lines.append("- None (Echo agrees with market within 5%)")
    lines.append("")

    lines.append("Markets where Echo suggests YES is underpriced (buy YES):")
    underpriced = [
        (p, d) for p, d in zip(predictions, deltas)
        if d > 0.05  # Echo thinks YES is 5%+ higher than market
    ]
    if underpriced:
        for p, d in sorted(underpriced, key=lambda x: x[1], reverse=True):
            lines.append(
                f"- **{p['question'][:60]}**: Echo {p['echo_probability']:.1%} "
                f"vs Mkt {p['market_price_at_prediction']:.1%} ({d:+.1%})"
            )
    else:
        lines.append("- None (Echo agrees with market within 5%)")

    return "\n".join(lines)


def compare_with_bot(date_str: str, trade_log_path: Path, rejection_log_path: Path):
    """
    Compare Echo predictions with bot's actual trade/rejection decisions.
    """
    # Load today's Echo predictions
    predictions = {}
    if PREDICTIONS_FILE.exists():
        with open(PREDICTIONS_FILE) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    p = json.loads(line)
                    ts = p.get("timestamp", "")
                    if date_str in ts:
                        predictions[p["market_id"]] = p
                except json.JSONDecodeError:
                    continue

    if not predictions:
        return f"No Echo predictions found for {date_str}"

    # Load bot's trade log
    bot_trades = {}
    if trade_log_path.exists():
        with open(trade_log_path) as f:
            for line in f:
                try:
                    t = json.loads(line.strip())
                    ts = t.get("logged_at", "")
                    if date_str in ts:
                        bot_trades[t["condition_id"]] = t
                except (json.JSONDecodeError, KeyError):
                    continue

    # Load bot's rejection log
    bot_rejections = {}
    if rejection_log_path.exists():
        with open(rejection_log_path) as f:
            for line in f:
                try:
                    r = json.loads(line.strip())
                    ts = r.get("timestamp", "")
                    if date_str in ts:
                        bot_rejections[r.get("condition_id", "")] = r
                except (json.JSONDecodeError, KeyError):
                    continue

    lines = [
        f"# Echo vs Bot Comparison — {date_str}",
        "",
        f"Echo predictions: {len(predictions)}",
        f"Bot trades: {len(bot_trades)}",
        f"Bot rejections: {len(bot_rejections)}",
        "",
    ]

    # Find overlaps
    lines.append("## Agreement/Disagreement")
    lines.append("")
    lines.append("| Market | Echo Prob | Bot Action | Agreement |")
    lines.append("|--------|----------|------------|-----------|")

    for cid, pred in predictions.items():
        echo_prob = pred.get("echo_probability", 0.5)
        q = pred["question"][:45]

        if cid in bot_trades:
            # Bot traded this market (bought NO)
            # Echo agrees if Echo thinks YES is overpriced (echo_prob < market)
            bot_action = "TRADE (buy NO)"
            agrees = echo_prob < pred["market_price_at_prediction"]
            agreement = "AGREE" if agrees else "DISAGREE"
        elif cid in bot_rejections:
            bot_action = f"SKIP ({bot_rejections[cid].get('reason', '?')})"
            agreement = "N/A"
        else:
            bot_action = "NOT SEEN"
            agreement = "N/A"

        lines.append(f"| {q} | {echo_prob:.1%} | {bot_action} | {agreement} |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Echo Daily Runner")
    parser.add_argument("--bankroll", type=float, help="Bankroll (for context)")
    parser.add_argument("--scan-only", action="store_true",
                        help="Only scan markets, don't run Echo")
    parser.add_argument("--analyze-batch", type=str,
                        help="Run Echo on existing batch file")
    parser.add_argument("--compare", action="store_true",
                        help="Compare Echo vs bot for a given date")
    parser.add_argument("--date", type=str,
                        default=datetime.now().strftime("%Y-%m-%d"),
                        help="Date for comparison (YYYY-MM-DD)")
    parser.add_argument("--quick", action="store_true",
                        help="Use quick mode (single agent, faster)")
    parser.add_argument("--filter-mode", default="strict_elon_social",
                        help="Market filter mode (default: strict_elon_social)")
    parser.add_argument("--max-markets", type=int, default=None,
                        help="Max markets to analyze (for testing)")
    parser.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    date_str = args.date
    mode = "quick" if args.quick else "map_reduce"
    output_dir = ECHO_OUTPUT_DIR / date_str
    output_dir.mkdir(parents=True, exist_ok=True)

    # --- Compare mode ---
    if args.compare:
        trading_dir = REPO_ROOT / "trading"
        report = compare_with_bot(
            date_str,
            trading_dir / "trade_log.jsonl",
            trading_dir / "rejection_log.jsonl",
        )
        print(report)
        report_path = output_dir / "comparison.md"
        with open(report_path, "w") as f:
            f.write(report)
        log.info(f"Comparison saved to {report_path}")
        return

    # --- Analyze existing batch ---
    if args.analyze_batch:
        batch_path = Path(args.analyze_batch)
        candidates = load_batch(batch_path)
        if args.max_markets:
            candidates = candidates[:args.max_markets]
        log.info(f"Loaded {len(candidates)} markets from {batch_path}")
        predictions = run_batch(candidates, mode, output_dir)
        report = generate_daily_report(predictions, candidates, date_str)
        print(report)
        report_path = output_dir / "report.md"
        with open(report_path, "w") as f:
            f.write(report)
        log.info(f"Report saved to {report_path}")
        return

    # --- Full run: scan + analyze ---
    log.info(f"Scanning markets with filter: {args.filter_mode}")
    candidates = scan_markets(args.filter_mode)
    log.info(f"Found {len(candidates)} candidate markets")

    if args.max_markets:
        candidates = candidates[:args.max_markets]
        log.info(f"Limited to {args.max_markets} markets")

    # Save batch
    batch_path = save_batch(candidates, output_dir)

    if args.scan_only:
        print(f"\nScan complete. {len(candidates)} markets saved to {batch_path}")
        print("\nTop 10 by volume:")
        for i, c in enumerate(candidates[:10], 1):
            print(
                f"  {i}. {c['question'][:55]} | "
                f"YES={c['yes_price']:.1%} | TTE={c['tte_days']:.0f}d | "
                f"Vol=${c['volume']:,.0f}"
            )
        return

    # Run Echo analysis
    log.info(f"Running Echo ({mode}) on {len(candidates)} markets...")
    predictions = run_batch(candidates, mode, output_dir)

    # Generate report
    report = generate_daily_report(predictions, candidates, date_str)
    print(report)

    report_path = output_dir / "report.md"
    with open(report_path, "w") as f:
        f.write(report)
    log.info(f"Report saved to {report_path}")

    # Summary
    print(f"\n{'='*60}")
    print(f"Echo Daily Run Complete")
    print(f"  Markets scanned: {len(candidates)}")
    print(f"  Predictions: {len(predictions)}")
    print(f"  Output: {output_dir}")
    print(f"  Predictions log: {PREDICTIONS_FILE}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
