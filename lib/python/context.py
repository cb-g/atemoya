"""Optional context enrichment for pricing scanners.

Loads macro regime and sentiment data when available. Returns None
when data is missing or stale — scanners should skip enrichment columns
in that case. This is strictly additive: scanners work fine without it.
"""

import json
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Staleness thresholds in seconds
MACRO_MAX_AGE = 30 * 86400   # 30 days (FRED data updates monthly)
SENTIMENT_MAX_AGE = 7 * 86400  # 7 days


def _file_age(path: Path) -> float:
    """Return file age in seconds, or infinity if missing."""
    if not path.exists():
        return float("inf")
    return time.time() - path.stat().st_mtime


def load_macro_regime() -> dict | None:
    """Load current macro regime classification.

    Returns dict with keys: cycle_phase, risk_sentiment, recession_probability.
    Returns None if environment.json is missing or older than 30 days.
    """
    path = PROJECT_ROOT / "alternative" / "macro_dashboard" / "output" / "environment.json"
    if _file_age(path) > MACRO_MAX_AGE:
        return None
    try:
        data = json.loads(path.read_text())
        regime = data.get("regime", {})
        return {
            "cycle_phase": regime.get("cycle_phase", ""),
            "risk_sentiment": regime.get("risk_sentiment", ""),
            "recession_probability": regime.get("recession_probability"),
        }
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def load_ticker_sentiment(ticker: str) -> dict | None:
    """Load sentiment data for a specific ticker.

    Checks discord analysis first, then narrative drift signals.
    Returns dict with keys: sentiment_score (-1 to +1), sentiment_signal, source.
    Returns None if no fresh data for this ticker.
    """
    # Try discord sentiment
    discord_path = PROJECT_ROOT / "alternative" / "nlp_sentiment" / "output" / "discord_analysis.json"
    if _file_age(discord_path) <= SENTIMENT_MAX_AGE:
        try:
            data = json.loads(discord_path.read_text())
            tickers = data.get("tickers", {})
            upper = ticker.upper()
            if upper in tickers:
                t = tickers[upper]
                return {
                    "sentiment_score": t.get("combined_score", 0.0),
                    "sentiment_signal": t.get("signal", "neutral"),
                    "sentiment_confidence": t.get("confidence", 0.0),
                    "source": "discord",
                }
        except (json.JSONDecodeError, KeyError, OSError):
            pass

    # Try narrative drift signals
    signals_path = PROJECT_ROOT / "alternative" / "nlp_sentiment" / "output" / "signals.csv"
    if _file_age(signals_path) <= SENTIMENT_MAX_AGE:
        try:
            import csv
            with open(signals_path) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("ticker", "").upper() == ticker.upper():
                        score = float(row.get("composite_score", 0))
                        # composite_score is 0-1 (magnitude of change), not directional
                        # hedging_delta > 0 means more hedging = bearish
                        hedging = float(row.get("hedging_delta", 0))
                        direction = -1 if hedging > 0.3 else (1 if hedging < -0.3 else 0)
                        return {
                            "sentiment_score": score * direction if direction else 0.0,
                            "sentiment_signal": "bearish" if direction < 0 else ("bullish" if direction > 0 else "neutral"),
                            "sentiment_confidence": score,
                            "source": "narrative_drift",
                        }
        except (OSError, ValueError):
            pass

    return None
