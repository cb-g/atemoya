"""Result collection and per-module extraction. Each model's verdict stands on its own."""

import json
import statistics
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3]

def _safe_float(val) -> float | None:
    """Extract a float from a JSON value, returning None for null/invalid."""
    if val is None:
        return None
    try:
        f = float(val)
        if f != f:  # NaN check
            return None
        return f
    except (ValueError, TypeError):
        return None


# --- Per-module result extractors ---

def _extract_dcf_deterministic(ticker: str) -> dict | None:
    path = PROJECT_ROOT / f"valuation/panel/output/dcf_det_{ticker}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    fcfe = _safe_float(data.get("ivps_fcfe"))
    fcff = _safe_float(data.get("ivps_fcff"))
    fair_values = [v for v in [fcfe, fcff] if v is not None and v > 0]
    primary_fv = statistics.mean(fair_values) if fair_values else None
    return {
        "module": "dcf_deterministic",
        "fair_value": primary_fv,
        "fair_value_details": {"FCFE": fcfe, "FCFF": fcff},
        "signal": data.get("signal", ""),
        "confidence": None,
    }


def _extract_dcf_probabilistic(ticker: str) -> dict | None:
    path = PROJECT_ROOT / f"valuation/panel/output/dcf_prob_{ticker}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    fcfe_mean = _safe_float(data.get("fcfe_mean"))
    fcff_mean = _safe_float(data.get("fcff_mean"))
    fair_values = [v for v in [fcfe_mean, fcff_mean] if v is not None and v > 0]
    primary_fv = statistics.mean(fair_values) if fair_values else None
    p_under = _safe_float(data.get("p_undervalued_fcfe"))
    return {
        "module": "dcf_probabilistic",
        "fair_value": primary_fv,
        "fair_value_details": {"FCFE mean": fcfe_mean, "FCFF mean": fcff_mean},
        "signal": data.get("signal", ""),
        "confidence": round(p_under * 100, 1) if p_under is not None else None,
        "confidence_label": "P(under)",
    }


def _extract_normalized_multiples(ticker: str) -> dict | None:
    path = PROJECT_ROOT / f"valuation/normalized_multiples/output/multiples_result_{ticker}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    fv = _safe_float(data.get("median_implied_price")) or _safe_float(data.get("average_implied_price"))
    return {
        "module": "normalized_multiples",
        "fair_value": fv,
        "signal": data.get("overall_signal", ""),
        "confidence": _safe_float(data.get("confidence")),
        "confidence_label": "conf",
    }


def _extract_garp_peg(ticker: str) -> dict | None:
    path = PROJECT_ROOT / f"valuation/garp_peg/output/garp_result_{ticker}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    score = data.get("garp_score", {})
    return {
        "module": "garp_peg",
        "fair_value": _safe_float(data.get("implied_fair_price")),
        "signal": data.get("signal", ""),
        "confidence": _safe_float(score.get("total_score")),
        "confidence_label": "score",
    }


def _extract_growth_analysis(ticker: str) -> dict | None:
    path = PROJECT_ROOT / f"valuation/growth_analysis/output/growth_result_{ticker}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    score = data.get("score", {})
    return {
        "module": "growth_analysis",
        "fair_value": None,  # No explicit price target
        "signal": data.get("signal", ""),
        "confidence": _safe_float(score.get("total_score")),
        "confidence_label": "score",
    }


def _extract_dividend_income(ticker: str) -> dict | None:
    path = PROJECT_ROOT / f"valuation/dividend_income/output/dividend_result_{ticker}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    ddm = data.get("ddm_valuation", {})
    score = data.get("safety_score", {})
    return {
        "module": "dividend_income",
        "fair_value": _safe_float(ddm.get("average_fair_value")),
        "signal": data.get("signal", ""),
        "confidence": _safe_float(score.get("total_score")),
        "confidence_label": "safety",
    }


def _extract_analyst_upside(ticker: str) -> dict | None:
    # Analyst upside writes per-ticker files
    path = PROJECT_ROOT / f"valuation/panel/output/analyst_{ticker}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    # The file has a results array
    results = data.get("results", [])
    match = next((r for r in results if r.get("ticker", "").upper() == ticker.upper()), None)
    if not match:
        return None
    return {
        "module": "analyst_upside",
        "fair_value": _safe_float(match.get("target_mean")),
        "signal": match.get("recommendation", ""),
        "confidence": match.get("num_analysts"),
        "confidence_label": "analysts",
    }


def _extract_etf_analysis(ticker: str) -> dict | None:
    path = PROJECT_ROOT / f"valuation/etf_analysis/output/etf_result_{ticker}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    score = data.get("score", {})
    return {
        "module": "etf_analysis",
        "fair_value": None,  # ETFs have no intrinsic value estimate
        "signal": data.get("signal", ""),
        "confidence": _safe_float(score.get("total_score")),
        "confidence_label": "score",
    }


def _extract_dcf_reit(ticker: str) -> dict | None:
    path = PROJECT_ROOT / f"valuation/dcf_reit/output/data/{ticker}_valuation.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    quality = _safe_float(data.get("quality", {}).get("overall_quality"))
    return {
        "module": "dcf_reit",
        "fair_value": _safe_float(data.get("fair_value")),
        "signal": data.get("signal", ""),
        "confidence": round(quality * 100, 1) if quality is not None else None,
        "confidence_label": "quality",
    }


def _extract_crypto_treasury(ticker: str) -> dict | None:
    path = PROJECT_ROOT / "valuation/crypto_treasury/output/crypto_treasury_all.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    results = data.get("results", [])
    match = next((r for r in results if r.get("ticker", "").upper() == ticker.upper()), None)
    if not match:
        return None
    return {
        "module": "crypto_treasury",
        "fair_value": _safe_float(match.get("nav_per_share")),
        "signal": match.get("signal", ""),
        "confidence": None,
    }


EXTRACTORS = {
    "dcf_deterministic": _extract_dcf_deterministic,
    "dcf_probabilistic": _extract_dcf_probabilistic,
    "normalized_multiples": _extract_normalized_multiples,
    "garp_peg": _extract_garp_peg,
    "growth_analysis": _extract_growth_analysis,
    "dividend_income": _extract_dividend_income,
    "analyst_upside": _extract_analyst_upside,
    "etf_analysis": _extract_etf_analysis,
    "dcf_reit": _extract_dcf_reit,
    "crypto_treasury": _extract_crypto_treasury,
}


def collect_results(
    execution_plan: dict[str, list[str]],
    analysis_results: dict[str, dict[str, tuple[bool, str]]],
    triage_results: list[dict],
) -> list[dict]:
    """Collect results for all tickers. Each module's verdict stands on its own."""
    triage_by_ticker = {r["ticker"]: r for r in triage_results}
    aggregated = []

    for ticker, modules in execution_plan.items():
        info = triage_by_ticker.get(ticker, {})
        price = info.get("current_price", 0.0)
        company_name = info.get("company_name", ticker)

        module_results = []
        modules_failed = []

        for module in modules:
            success, _ = analysis_results.get(ticker, {}).get(module, (False, ""))
            if not success:
                modules_failed.append(module)
                continue

            extractor = EXTRACTORS.get(module)
            if not extractor:
                modules_failed.append(module)
                continue

            result = extractor(ticker)
            if result is None:
                modules_failed.append(module)
                continue

            # Add upside vs current price (per-module, not averaged)
            fv = result.get("fair_value")
            if fv and price and price > 0:
                result["upside_pct"] = round((fv / price - 1) * 100, 1)
            else:
                result["upside_pct"] = None

            module_results.append(result)

        aggregated.append({
            "ticker": ticker,
            "company_name": company_name,
            "current_price": price,
            "security_type": _security_type(info),
            "sector": info.get("sector", ""),
            "modules_run": [r["module"] for r in module_results],
            "modules_failed": modules_failed,
            "module_results": module_results,
        })

    return aggregated


def _security_type(info: dict) -> str:
    qt = info.get("quote_type", "EQUITY")
    if qt == "ETF":
        return "etf"
    if info.get("sector") == "Real Estate":
        return "reit"
    return "equity"
