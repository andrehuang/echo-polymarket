#!/usr/bin/env python3
"""
Track Echo predictions and evaluate accuracy over time.

Usage:
    python -m helpers.track_predictions log <prediction_json>
    python -m helpers.track_predictions check
    python -m helpers.track_predictions score
    python -m helpers.track_predictions leaderboard
"""

import sys
import json
import os
import time
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List

PREDICTIONS_FILE = Path(__file__).parent / "predictions.jsonl"
GAMMA_API_URL = "https://gamma-api.polymarket.com"


def safe_request(url: str, params: Dict = None, timeout: int = 10) -> Optional[Dict]:
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                time.sleep(2 ** attempt)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt < 2:
                time.sleep(1)
    return None


def log_prediction(prediction: Dict) -> str:
    """
    Log a prediction to the JSONL file.

    Expected prediction format:
    {
        "market_id": "0x...",
        "question": "Will X happen?",
        "echo_probability": 0.65,
        "confidence": "medium",
        "market_price_at_prediction": 0.58,
        "timestamp": "2026-03-30T12:00:00Z",
        "domain": "politics",
        "mode": "map_reduce",  # or "react" or "quick"
        ... (additional fields preserved)
    }
    """
    # Ensure required fields
    if "timestamp" not in prediction:
        prediction["timestamp"] = datetime.now(timezone.utc).isoformat()
    if "resolved" not in prediction:
        prediction["resolved"] = False

    with open(PREDICTIONS_FILE, "a") as f:
        f.write(json.dumps(prediction, default=str) + "\n")

    return prediction.get("market_id", "unknown")


def load_predictions() -> List[Dict]:
    """Load all predictions from the JSONL file."""
    if not PREDICTIONS_FILE.exists():
        return []
    predictions = []
    with open(PREDICTIONS_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    predictions.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return predictions


def check_resolved() -> List[Dict]:
    """
    Check if any unresolved predictions' markets have resolved.
    Updates the predictions file with resolution outcomes.
    Returns list of newly resolved predictions.
    """
    predictions = load_predictions()
    newly_resolved = []
    updated = False

    for pred in predictions:
        if pred.get("resolved"):
            continue

        condition_id = pred.get("market_id", "")
        if not condition_id:
            continue

        # Check market status
        data = safe_request(f"{GAMMA_API_URL}/markets",
                            params={"condition_id": condition_id})
        if not data or len(data) == 0:
            continue

        market = data[0]
        if not market.get("resolved"):
            continue

        # Market has resolved - determine outcome
        outcome = market.get("resolutionOutcome", "")
        outcomes = market.get("outcomes", [])
        if isinstance(outcomes, str):
            outcomes = json.loads(outcomes)

        outcome_prices = market.get("outcomePrices", [])
        if isinstance(outcome_prices, str):
            outcome_prices = json.loads(outcome_prices)

        # Determine if "Yes" won (probability = 1.0) or "No" won (probability = 0.0)
        actual_probability = None
        if outcome and outcomes:
            yes_idx = None
            for i, o in enumerate(outcomes):
                if o.lower() == "yes":
                    yes_idx = i
                    break
            if yes_idx is not None and yes_idx < len(outcome_prices):
                try:
                    actual_probability = float(outcome_prices[yes_idx])
                except (ValueError, TypeError):
                    pass

        if actual_probability is None:
            # Try from resolution outcome directly
            if outcome.lower() == "yes":
                actual_probability = 1.0
            elif outcome.lower() == "no":
                actual_probability = 0.0

        if actual_probability is not None:
            pred["resolved"] = True
            pred["actual_outcome"] = actual_probability
            pred["resolution_date"] = datetime.now(timezone.utc).isoformat()
            pred["brier_score"] = (
                pred.get("echo_probability", 0.5) - actual_probability
            ) ** 2
            market_brier = (
                pred.get("market_price_at_prediction", 0.5) - actual_probability
            ) ** 2
            pred["market_brier_score"] = market_brier
            pred["echo_beat_market"] = (
                pred["brier_score"] < market_brier
            )
            newly_resolved.append(pred)
            updated = True

    if updated:
        # Rewrite the file with updated predictions
        with open(PREDICTIONS_FILE, "w") as f:
            for pred in predictions:
                f.write(json.dumps(pred, default=str) + "\n")

    return newly_resolved


def score_predictions() -> Dict:
    """
    Compute aggregate accuracy metrics for all resolved predictions.
    """
    predictions = load_predictions()
    resolved = [p for p in predictions if p.get("resolved")]
    unresolved = [p for p in predictions if not p.get("resolved")]

    if not resolved:
        return {
            "total_predictions": len(predictions),
            "resolved": 0,
            "unresolved": len(unresolved),
            "message": "No resolved predictions yet.",
        }

    echo_briers = [p["brier_score"] for p in resolved if "brier_score" in p]
    market_briers = [
        p["market_brier_score"] for p in resolved
        if "market_brier_score" in p
    ]
    beat_count = sum(
        1 for p in resolved if p.get("echo_beat_market", False)
    )

    # Breakdowns by domain and mode
    by_domain = {}
    by_mode = {}
    for p in resolved:
        domain = p.get("domain", "unknown")
        mode = p.get("mode", "unknown")
        bs = p.get("brier_score")
        if bs is not None:
            by_domain.setdefault(domain, []).append(bs)
            by_mode.setdefault(mode, []).append(bs)

    def avg(lst):
        return sum(lst) / len(lst) if lst else None

    return {
        "total_predictions": len(predictions),
        "resolved": len(resolved),
        "unresolved": len(unresolved),
        "echo_avg_brier": round(avg(echo_briers), 4) if echo_briers else None,
        "market_avg_brier": (
            round(avg(market_briers), 4) if market_briers else None
        ),
        "echo_beat_market_rate": (
            round(beat_count / len(resolved), 3) if resolved else None
        ),
        "by_domain": {
            d: {"count": len(bs), "avg_brier": round(avg(bs), 4)}
            for d, bs in by_domain.items()
        },
        "by_mode": {
            m: {"count": len(bs), "avg_brier": round(avg(bs), 4)}
            for m, bs in by_mode.items()
        },
    }


def leaderboard() -> str:
    """Format a human-readable leaderboard."""
    scores = score_predictions()

    lines = ["# Echo Prediction Leaderboard", ""]
    lines.append(
        f"Total: {scores['total_predictions']} predictions "
        f"({scores['resolved']} resolved, {scores['unresolved']} pending)"
    )
    lines.append("")

    if scores["resolved"] == 0:
        lines.append("No resolved predictions yet. Run `check` to update.")
        return "\n".join(lines)

    lines.append("## Accuracy")
    lines.append(f"- Echo avg Brier score: {scores['echo_avg_brier']}")
    lines.append(f"- Market avg Brier score: {scores['market_avg_brier']}")
    lines.append(
        f"- Echo beats market: "
        f"{scores['echo_beat_market_rate']:.1%} of the time"
    )
    lines.append("")

    if scores.get("by_domain"):
        lines.append("## By Domain")
        for domain, stats in sorted(scores["by_domain"].items()):
            lines.append(
                f"- {domain}: {stats['avg_brier']:.4f} "
                f"({stats['count']} predictions)"
            )
        lines.append("")

    if scores.get("by_mode"):
        lines.append("## By Mode")
        for mode, stats in sorted(scores["by_mode"].items()):
            lines.append(
                f"- {mode}: {stats['avg_brier']:.4f} "
                f"({stats['count']} predictions)"
            )

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: track_predictions.py <log|check|score|leaderboard>")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "log":
        if len(sys.argv) < 3:
            print("Usage: track_predictions.py log '<json>'")
            sys.exit(1)
        prediction = json.loads(sys.argv[2])
        mid = log_prediction(prediction)
        print(json.dumps({"status": "logged", "market_id": mid}))

    elif cmd == "check":
        newly = check_resolved()
        print(f"Checked predictions. {len(newly)} newly resolved:")
        for p in newly:
            echo_bs = p.get("brier_score", "?")
            market_bs = p.get("market_brier_score", "?")
            beat = p.get("echo_beat_market", "?")
            print(
                f"  {p.get('question', '')[:60]}: "
                f"Echo={echo_bs:.4f}, Market={market_bs:.4f}, "
                f"Beat={'YES' if beat else 'NO'}"
            )

    elif cmd == "score":
        print(json.dumps(score_predictions(), indent=2))

    elif cmd == "leaderboard":
        print(leaderboard())

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
