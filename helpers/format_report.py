#!/usr/bin/env python3
"""
Format Echo prediction results as markdown reports or JSON.

Usage:
    python -m helpers.format_report <prediction_json> [--json|--markdown]
"""

import sys
import json
from datetime import datetime
from typing import Dict, List, Optional


def format_markdown(prediction: Dict) -> str:
    """Format a prediction as a readable markdown report."""
    lines = []

    # Header
    question = prediction.get("question", "Unknown Market")
    lines.append(f"# Echo Prediction Report")
    lines.append("")
    lines.append(f"**Market:** {question}")
    if prediction.get("event_title"):
        lines.append(f"**Event:** {prediction['event_title']}")
    if prediction.get("url"):
        lines.append(f"**URL:** {prediction['url']}")
    lines.append(f"**Analyzed:** {prediction.get('timestamp', 'N/A')}")
    if prediction.get("days_remaining") is not None:
        lines.append(
            f"**Days remaining:** {prediction['days_remaining']}"
        )
    lines.append(f"**Domain:** {prediction.get('domain', 'N/A')}")
    lines.append(f"**Mode:** {prediction.get('mode', 'N/A')}")
    lines.append("")

    # Probability estimate
    lines.append("## Prediction")
    lines.append("")
    echo_prob = prediction.get("echo_probability")
    confidence = prediction.get("confidence", "N/A")
    market_price = prediction.get("market_price_at_prediction")

    if echo_prob is not None:
        lines.append(
            f"| Metric | Value |"
        )
        lines.append(f"|--------|-------|")
        lines.append(f"| Echo probability | **{echo_prob:.1%}** |")
        lines.append(f"| Confidence | {confidence} |")
        if prediction.get("confidence_interval"):
            ci = prediction["confidence_interval"]
            lines.append(f"| 90% CI | [{ci[0]:.1%}, {ci[1]:.1%}] |")
        if market_price is not None:
            lines.append(f"| Market price (YES) | {market_price:.1%} |")
            delta = echo_prob - market_price
            direction = "higher" if delta > 0 else "lower"
            lines.append(
                f"| Echo vs Market | {abs(delta):.1%} {direction} |"
            )
        lines.append("")

    # Probability distribution (multi-outcome markets)
    if prediction.get("probability_distribution"):
        lines.append("### Probability Distribution")
        lines.append("")
        lines.append("| Outcome | Echo | Market |")
        lines.append("|---------|------|--------|")
        market_prices = prediction.get("current_prices", {})
        for outcome, prob in prediction["probability_distribution"].items():
            mp = market_prices.get(outcome)
            mp_str = f"{mp:.1%}" if mp is not None else "N/A"
            lines.append(f"| {outcome} | {prob:.1%} | {mp_str} |")
        lines.append("")

    # Evidence base
    if prediction.get("evidence"):
        lines.append("## Evidence")
        lines.append("")
        for i, ev in enumerate(prediction["evidence"], 1):
            role = ev.get("role", "unknown")
            role_emoji = {
                "direct": "[DIRECT]",
                "supporting": "[SUPPORTING]",
                "contradicting": "[CONTRADICTING]",
                "contextual": "[CONTEXT]",
            }.get(role, f"[{role.upper()}]")

            lines.append(f"**{i}. {role_emoji}** {ev.get('summary', '')}")
            if ev.get("source"):
                lines.append(f"   Source: {ev['source']}")
            lines.append("")

    # Reasoning
    if prediction.get("reasoning"):
        lines.append("## Reasoning")
        lines.append("")
        lines.append(prediction["reasoning"])
        lines.append("")

    # Sub-task results (from Map-Reduce)
    if prediction.get("sub_tasks"):
        lines.append("## Research Sub-Tasks")
        lines.append("")
        for st in prediction["sub_tasks"]:
            name = st.get("name", "Unknown")
            prob = st.get("probability")
            conf = st.get("confidence", "N/A")
            prob_str = f"{prob:.1%}" if prob is not None else "N/A"
            lines.append(f"### {name}")
            lines.append(f"Estimate: {prob_str} (confidence: {conf})")
            lines.append("")
            if st.get("findings"):
                for f in st["findings"]:
                    lines.append(f"- {f}")
                lines.append("")

    # Counterfactual fragility
    if prediction.get("reversal_scenarios"):
        lines.append("## Counterfactual Fragility")
        lines.append("")
        fragility = prediction.get("fragility_score")
        if fragility is not None:
            label = (
                "robust" if fragility < 0.3
                else "moderate" if fragility < 0.6
                else "fragile"
            )
            lines.append(
                f"Fragility score: **{fragility:.2f}** ({label})"
            )
            lines.append("")

        for rs in prediction["reversal_scenarios"]:
            impact = rs.get("impact_magnitude", 0)
            direction = rs.get("impact_direction", "?")
            lines.append(
                f"- **{rs.get('description', '')}** "
                f"(probability: {rs.get('probability', 0):.0%}, "
                f"impact: {direction} {impact:.0%})"
            )
        lines.append("")

    # Monitoring recommendations
    if prediction.get("monitoring"):
        lines.append("## Monitoring Recommendations")
        lines.append("")
        for mon in prediction["monitoring"]:
            freq = mon.get("check_frequency", "")
            lines.append(
                f"- **{mon.get('trigger', '')}** "
                f"(check: {freq})"
            )
            if mon.get("impact_if_triggered"):
                lines.append(
                    f"  Impact: {mon['impact_if_triggered']}"
                )
        lines.append("")

    # Conflicts (from Map-Reduce)
    if prediction.get("conflicts"):
        lines.append("## Conflicts Between Sub-Agents")
        lines.append("")
        for conflict in prediction["conflicts"]:
            lines.append(f"- {conflict}")
        lines.append("")

    return "\n".join(lines)


def format_json(prediction: Dict) -> str:
    """Format prediction as pretty-printed JSON."""
    return json.dumps(prediction, indent=2, default=str)


def format_comparison(prediction: Dict) -> str:
    """Short comparison view: Echo vs Market."""
    q = prediction.get("question", "?")
    echo = prediction.get("echo_probability")
    market = prediction.get("market_price_at_prediction")
    confidence = prediction.get("confidence", "?")

    echo_str = f"{echo:.1%}" if echo is not None else "N/A"
    market_str = f"{market:.1%}" if market is not None else "N/A"

    delta = ""
    if echo is not None and market is not None:
        d = echo - market
        direction = "+" if d > 0 else ""
        delta = f" (delta: {direction}{d:.1%})"

    return (
        f"{q}\n"
        f"  Echo: {echo_str} [{confidence}] | Market: {market_str}{delta}"
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: format_report.py <json_string> [--json|--markdown|--compare]")
        sys.exit(1)

    prediction = json.loads(sys.argv[1])
    fmt = sys.argv[2] if len(sys.argv) > 2 else "--markdown"

    if fmt == "--json":
        print(format_json(prediction))
    elif fmt == "--compare":
        print(format_comparison(prediction))
    else:
        print(format_markdown(prediction))


if __name__ == "__main__":
    main()
