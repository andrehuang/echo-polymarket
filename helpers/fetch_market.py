#!/usr/bin/env python3
"""
Fetch market data from Polymarket APIs.

Usage:
    python -m helpers.fetch_market <url_or_slug_or_condition_id>
    python -m helpers.fetch_market "https://polymarket.com/event/some-slug"
    python -m helpers.fetch_market "0xabc123..."

Outputs JSON to stdout with market metadata, prices, and resolution rules.
"""

import sys
import json
import re
import time
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any

GAMMA_API_URL = "https://gamma-api.polymarket.com"
CLOB_API_URL = "https://clob.polymarket.com"


def safe_request(url: str, params: Dict = None, timeout: int = 10,
                 retries: int = 3) -> Optional[Any]:
    """HTTP GET with retry logic."""
    for attempt in range(retries):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                wait = 2 ** attempt
                time.sleep(wait)
            else:
                return None
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt < retries - 1:
                time.sleep(1)
    return None


def parse_polymarket_input(user_input: str) -> Dict[str, Optional[str]]:
    """
    Parse various Polymarket URL formats or identifiers.

    Supports:
        https://polymarket.com/event/some-slug
        https://polymarket.com/event/some-slug/sub-market-slug
        0xabc123... (condition_id)
        some-slug (event slug)

    Returns dict with keys: event_slug, market_slug, condition_id
    """
    user_input = user_input.strip()
    result = {"event_slug": None, "market_slug": None, "condition_id": None}

    # URL pattern
    url_match = re.match(
        r'https?://(?:www\.)?polymarket\.com/event/([^/?#]+)(?:/([^/?#]+))?',
        user_input
    )
    if url_match:
        result["event_slug"] = url_match.group(1)
        result["market_slug"] = url_match.group(2)
        return result

    # Condition ID (hex string starting with 0x)
    if re.match(r'^0x[a-fA-F0-9]{10,}$', user_input):
        result["condition_id"] = user_input
        return result

    # Assume it's a slug
    result["event_slug"] = user_input
    return result


def fetch_event_by_slug(slug: str) -> Optional[Dict]:
    """Fetch event data from Gamma API by slug."""
    data = safe_request(f"{GAMMA_API_URL}/events", params={
        "slug": slug,
        "closed": "false",
    })
    if data and len(data) > 0:
        return data[0]

    # Try without closed filter
    data = safe_request(f"{GAMMA_API_URL}/events", params={"slug": slug})
    if data and len(data) > 0:
        return data[0]
    return None


def fetch_market_by_slug(slug: str) -> Optional[Dict]:
    """Fetch market data from Gamma API by market slug."""
    data = safe_request(f"{GAMMA_API_URL}/markets", params={"slug": slug})
    if data and len(data) > 0:
        return data[0]
    return None


def fetch_market_by_condition_id(condition_id: str) -> Optional[Dict]:
    """Fetch market data by condition_id, trying multiple methods."""
    # Method 1: Direct condition_id lookup
    data = safe_request(f"{GAMMA_API_URL}/markets",
                        params={"condition_id": condition_id})
    if data and len(data) > 0:
        exact = [m for m in data if m.get("conditionId") == condition_id]
        if exact:
            return exact[0]

    # Method 2: Via CLOB token_id
    clob_data = safe_request(f"{CLOB_API_URL}/markets/{condition_id}")
    if clob_data:
        tokens = clob_data.get("tokens", [])
        if tokens:
            token_id = tokens[0].get("token_id")
            if token_id:
                data = safe_request(f"{GAMMA_API_URL}/markets",
                                    params={"clob_token_ids": token_id})
                if data and len(data) > 0:
                    return data[0]
    return None


def fetch_orderbook(token_id: str) -> Optional[Dict]:
    """Fetch current orderbook from CLOB API."""
    return safe_request(f"{CLOB_API_URL}/book",
                        params={"token_id": token_id})


def parse_market_data(market: Dict, event: Optional[Dict] = None) -> Dict:
    """Parse raw Gamma API market data into a clean structure."""
    # Parse outcomes and prices
    outcomes = market.get("outcomes", [])
    if isinstance(outcomes, str):
        outcomes = json.loads(outcomes)

    prices_raw = market.get("outcomePrices", [])
    if isinstance(prices_raw, str):
        prices_raw = json.loads(prices_raw)

    prices = {}
    for i, outcome in enumerate(outcomes):
        if i < len(prices_raw):
            try:
                prices[outcome] = round(float(prices_raw[i]), 4)
            except (ValueError, TypeError):
                prices[outcome] = None

    # Parse CLOB token IDs
    clob_token_ids = market.get("clobTokenIds", [])
    if isinstance(clob_token_ids, str):
        clob_token_ids = json.loads(clob_token_ids)
    token_map = {}
    for i, outcome in enumerate(outcomes):
        if i < len(clob_token_ids):
            token_map[outcome] = clob_token_ids[i]

    # Parse end date
    end_date_str = market.get("endDate") or market.get("end_date_iso")
    end_date = None
    days_remaining = None
    if end_date_str:
        try:
            end_date = datetime.fromisoformat(
                end_date_str.replace("Z", "+00:00")
            ).isoformat()
            end_dt = datetime.fromisoformat(
                end_date_str.replace("Z", "+00:00")
            )
            days_remaining = max(
                0, (end_dt - datetime.now(timezone.utc)).days
            )
        except (ValueError, TypeError):
            pass

    # Resolution source / rules
    resolution_source = market.get("resolutionSource", "")
    description = market.get("description", "")

    result = {
        "condition_id": market.get("conditionId", ""),
        "question": market.get("question", ""),
        "slug": market.get("slug", ""),
        "outcomes": outcomes,
        "current_prices": prices,
        "token_ids": token_map,
        "volume": float(market.get("volume", 0) or 0),
        "liquidity": float(market.get("liquidity", 0) or 0),
        "end_date": end_date,
        "days_remaining": days_remaining,
        "closed": market.get("closed", False),
        "resolved": market.get("resolved", False),
        "resolution_source": resolution_source,
        "description": description,
        "event_title": (event or {}).get("title", "")
            or market.get("groupItemTitle", ""),
        "event_slug": (event or {}).get("slug", ""),
        "tags": [
            str(t.get("label", t) if isinstance(t, dict) else t)
            for t in (market.get("tags") or (event or {}).get("tags") or [])
        ],
        "url": f"https://polymarket.com/event/"
               f"{(event or {}).get('slug', market.get('slug', ''))}",
    }

    return result


def fetch_market(user_input: str) -> Optional[Dict]:
    """
    Main entry point: fetch market data from any input format.
    Returns parsed market dict or None.
    """
    parsed = parse_polymarket_input(user_input)

    market_raw = None
    event_raw = None

    if parsed["condition_id"]:
        market_raw = fetch_market_by_condition_id(parsed["condition_id"])

    elif parsed["event_slug"]:
        event_raw = fetch_event_by_slug(parsed["event_slug"])
        if event_raw:
            markets = event_raw.get("markets", [])
            if parsed["market_slug"]:
                # Find specific sub-market
                for m in markets:
                    if m.get("slug") == parsed["market_slug"]:
                        market_raw = m
                        break
                if not market_raw:
                    market_raw = fetch_market_by_slug(parsed["market_slug"])
            elif len(markets) == 1:
                market_raw = markets[0]
            else:
                # Return event with all markets
                return {
                    "is_event": True,
                    "event_title": event_raw.get("title", ""),
                    "event_slug": event_raw.get("slug", ""),
                    "num_markets": len(markets),
                    "markets": [
                        parse_market_data(m, event_raw) for m in markets
                        if m.get("conditionId")
                    ],
                }

    if not market_raw:
        return None

    return parse_market_data(market_raw, event_raw)


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: fetch_market.py <url_or_slug_or_id>"}))
        sys.exit(1)

    user_input = sys.argv[1]
    result = fetch_market(user_input)

    if result is None:
        print(json.dumps({"error": f"Could not find market: {user_input}"}))
        sys.exit(1)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
