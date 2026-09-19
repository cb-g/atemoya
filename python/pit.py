"""Point-in-time: a boundary record for a ticker as of a past date D, from what was known
on D and nothing later (17).

Statements: the companyfacts JSON is the filer's whole history, so every tag's entries are
filtered to those filed on or before D before the per-period selection runs; the
submissions lag clause is evaluated on D too, and a filing listed but not yet in facts on
D leaves the record without statements rather than routing to the vendor, whose rows carry
no filing dates. Price: the close on the last trading day on or before D, in the terms
actually quoted that day: the vendor's closes are split-adjusted whatever auto_adjust says,
so the close is multiplied by every split ratio dated after D. Shares: the newest
dei:EntityCommonStockSharesOutstanding cover-page count filed on or before D (never the
market provider, which has no history); market cap is shares times price. Rates and FX:
FRED observations on or before D, written as a reference directory the batch runs with
(--reference data/pit/D/reference --today D); a currency whose rate source offers no
history is named on the record and the valuation refuses it. ERP, tax rates, betas and the
assumptions are held at the current vintage; the valuation declares each one whose vintage
postdates D on the record.
"""

from __future__ import annotations

import shutil
import urllib.parse
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Protocol, cast

import pandas as pd
import yfinance as yf

import boundary
import fetch
import fetch_sec
import reference
import refresh_fx
import refresh_rates as rr

REPO_ROOT = Path(__file__).resolve().parent.parent
PIT_ROOT = REPO_ROOT / "data" / "pit"
FRED_CACHE = PIT_ROOT / "fred"
REFERENCE = REPO_ROOT / "reference"
HISTORY_START = "2020-01-01"
SHARES_TAG = "EntityCommonStockSharesOutstanding"
FRED_PARSERS = ("fred_dgs", "fred_oecd_10y")  # the rate sources with history at a date
VENDOR_REASON = "vendor provider carries no filing dates"
SHARES_REASON = "dei cover page count not filed"


# --- facts filed on or before D ---------------------------------------------------------


def filed_on_or_before(facts: Mapping[str, object], d: date) -> dict[str, object]:
    """The companyfacts structure with every entry filed after [d] removed."""
    out: dict[str, object] = {}
    for key, value in facts.items():
        if key != "facts" or not isinstance(value, dict):
            out[key] = value
            continue
        taxonomies: dict[str, object] = {}
        for taxonomy, tags in cast(dict[str, object], value).items():
            kept: dict[str, object] = {}
            for tag, node in fetch_sec._as_dict(tags).items():  # pyright: ignore[reportPrivateUsage]
                units_out: dict[str, object] = {}
                for unit, entries in fetch_sec._as_dict(fetch_sec._as_dict(node).get("units")).items():  # pyright: ignore[reportPrivateUsage]
                    if isinstance(entries, list):
                        kept_entries = [e for e in cast(list[object], entries) if str(fetch_sec._as_dict(e).get("filed", "9999")) <= d.isoformat()]  # pyright: ignore[reportPrivateUsage]
                        if kept_entries:
                            units_out[unit] = kept_entries
                if units_out:
                    kept[tag] = {**fetch_sec._as_dict(node), "units": units_out}  # pyright: ignore[reportPrivateUsage]
            taxonomies[taxonomy] = kept
        out[key] = taxonomies
    return out


def submissions_on_or_before(index: Mapping[str, object] | None, d: date) -> dict[str, object] | None:
    """The submissions index with filings after [d] removed from filings.recent."""
    if index is None:
        return None
    recent = fetch_sec._as_dict(fetch_sec._as_dict(index.get("filings")).get("recent"))  # pyright: ignore[reportPrivateUsage]
    dates = recent.get("filingDate")
    if not isinstance(dates, list):
        return dict(index)
    keep = [i for i, filed in enumerate(cast(list[object], dates)) if str(filed) <= d.isoformat()]
    filtered = {name: [cast(list[object], column)[i] for i in keep] for name, column in recent.items() if isinstance(column, list)}
    return {**index, "filings": {"recent": filtered}}


# --- shares from the cover page ----------------------------------------------------------


def dei_shares(facts: Mapping[str, object], d: date) -> tuple[float, str, str, str] | None:
    """(shares, tag, cover-page date, filed) from the newest cover page filed on or before
    [d]; a filer with several share classes files one entry per class under the same date,
    and distinct values on that date are summed."""
    node = fetch_sec._as_dict(fetch_sec._as_dict(fetch_sec._as_dict(facts.get("facts")).get("dei")).get(SHARES_TAG))  # pyright: ignore[reportPrivateUsage]
    entries = [fetch_sec._as_dict(e) for e in cast(list[object], fetch_sec._as_dict(node.get("units")).get("shares", []))]  # pyright: ignore[reportPrivateUsage]
    dated = [(str(e["filed"]), str(e["end"]), float(cast(float, e["val"]))) for e in entries
             if "filed" in e and "end" in e and "val" in e and str(e["filed"]) <= d.isoformat()]
    if not dated:
        return None
    newest = max((filed, end) for filed, end, _ in dated)
    values = sorted({v for filed, end, v in dated if (filed, end) == newest})
    return sum(values), SHARES_TAG, newest[1], newest[0]


# --- price on the last trading day on or before D ---------------------------------------


class History:
    """A ticker's closes and splits as the vendor serves them, fetched once."""

    def __init__(self, closes: Mapping[date, float], splits: Mapping[date, float]) -> None:
        self.closes = dict(closes)
        self.splits = dict(splits)

    @classmethod
    def fetch(cls, symbol: str, *, start: str = HISTORY_START) -> History:
        ticker = yf.Ticker(symbol)
        frame = ticker.history(start=start, end=(datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d"), auto_adjust=False)
        closes: dict[date, float] = {}
        for stamp, close in frame["Close"].items():
            if isinstance(stamp, pd.Timestamp) and isinstance(close, float) and close == close:
                closes[stamp.date()] = float(close)
        splits: dict[date, float] = {}
        for stamp, ratio in ticker.splits.items():
            if isinstance(stamp, pd.Timestamp) and isinstance(ratio, float) and ratio > 0:
                splits[stamp.date()] = float(ratio)
        return cls(closes, splits)


def price_on(history: History, d: date, *, lookback_days: int = 10) -> tuple[date, float, float] | None:
    """(price_date, close as served, split factor): the last trading day on or before [d]
    within [lookback_days], and the product of the split ratios dated after [d]."""
    candidates = [day for day in history.closes if day <= d and (d - day).days <= lookback_days]
    if not candidates:
        return None
    price_date = max(candidates)
    factor = 1.0
    for day, ratio in history.splits.items():
        if day > d:
            factor *= ratio
    return price_date, history.closes[price_date], factor


# --- FRED observations on or before D ----------------------------------------------------


def observation_on_or_before(body: bytes, series_id: str, d: date) -> tuple[date, float]:
    """The newest observation with a value dated on or before [d] in a full-history FRED
    response; FRED quotes yields in percent, FX as quoted."""
    parsed = rr.Observations.model_validate_json(body)
    for observation in sorted(parsed.observations, key=lambda o: o.date, reverse=True):
        if observation.date <= d and observation.value != ".":
            return observation.date, float(observation.value)
    raise rr.RefreshError(f"{series_id}: no observation on or before {d}")


def fred_history(series_id: str, key: str) -> bytes:
    """The whole series, cached under data/pit/fred for a day."""
    path = FRED_CACHE / f"{series_id}.json"
    if path.exists() and (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) < fetch_sec.CACHE_SECONDS:
        return path.read_bytes()
    query = urllib.parse.urlencode({"series_id": series_id, "api_key": key, "file_type": "json", "observation_start": HISTORY_START})
    body = rr._get(f"{rr.FRED_OBSERVATIONS}?{query}")  # pyright: ignore[reportPrivateUsage]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return body


def curve_on(rule: reference.RateSource, d: date, key: str) -> reference.Curve | None:
    """A country's curve as observed on or before [d], for the FRED-backed sources; None
    for a source without history."""
    if rule.parser == "fred_dgs":
        points = {tenor: observation_on_or_before(fred_history(series_id, key), series_id, d) for tenor, series_id in rule.series}
        as_of = max(observed for observed, _ in points.values())
        return reference.Curve(source=rule.source, tier=rule.tier, as_of=as_of.isoformat(),
                               rates=[(t, round(r / 100.0, 6)) for t, (_, r) in points.items()],
                               notes=[f"point-in-time: observed on or before {d}"])
    if rule.parser == "fred_oecd_10y":
        series_id = dict(rule.series)["10y"]
        observed, rate = observation_on_or_before(fred_history(series_id, key), series_id, d)
        fetched = rr._substituted(rr.Fetched(as_of=rr._month_end(observed), rates={"10y": round(rate / 100.0, 6)},  # pyright: ignore[reportPrivateUsage]
                                             notes=[f"monthly average for {observed.strftime('%B %Y')}; point-in-time: observed on or before {d}"]), rule)
        return reference.Curve(source=rule.source, tier=rule.tier, as_of=fetched.as_of.isoformat(), rates=list(fetched.rates.items()),
                               estimated=fetched.estimated, tenor_used=list(fetched.tenor_used.items()), notes=fetched.notes)
    return None


def fx_on(code: str, rule: reference.FxSource, d: date, key: str) -> reference.FxRate:
    observed, quoted = observation_on_or_before(fred_history(rule.series, key), rule.series, d)
    return reference.FxRate(series=rule.series, direction=rule.direction, as_of=observed.isoformat(), quoted=quoted,
                            usd_per_unit=round(refresh_fx.normalise(quoted, rule.direction), 8))


def write_reference(d: date, out: Path, *, countries: set[str], currencies: set[str], key: str) -> dict[str, str]:
    """reference/ as of [d] under [out]: every file copied, the risk-free and FX files
    rewritten from FRED history for the countries and currencies asked for. Returns the
    series -> observation date used; a country whose source has no history is left out."""
    out.mkdir(parents=True, exist_ok=True)
    for path in REFERENCE.glob("*.json"):
        shutil.copy(path, out / path.name)
    registry = reference.RateSources.from_json_string((REFERENCE / "rate_sources.json").read_text())
    rates = reference.RiskFreeRates.from_json_string((REFERENCE / "risk_free_rates.json").read_text())
    observed: dict[str, str] = {}
    curves: list[tuple[str, reference.Curve]] = []
    for country, rule in registry.countries:
        if country not in countries:
            continue
        curve = curve_on(rule, d, key)
        if curve is not None:
            curves.append((country, curve))
            observed[f"risk_free {country}"] = curve.as_of
    (out / "risk_free_rates.json").write_text(reference.RiskFreeRates(
        max_age_days=rates.max_age_days, tenors=rates.tenors, aliases=rates.aliases, countries=curves,
        notes=[f"point-in-time: FRED observations on or before {d}; countries whose source has no history are absent"]).to_json_string(indent=2) + "\n")
    fx_sources = reference.FxSources.from_json_string((REFERENCE / "fx_sources.json").read_text())
    fx: list[tuple[str, reference.FxRate]] = []
    for code, rule in fx_sources.currencies:
        if code in currencies:
            rate = fx_on(code, rule, d, key)
            fx.append((code, rate))
            observed[f"fx {code}"] = rate.as_of
    (out / "fx_rates.json").write_text(reference.FxRates(source=f"FRED H.10, point-in-time observations on or before {d}", currencies=fx).to_json_string(indent=2) + "\n")
    return observed


def rate_history_available(country: str) -> bool:
    registry = reference.RateSources.from_json_string((REFERENCE / "rate_sources.json").read_text())
    return any(c == country and rule.parser in FRED_PARSERS for c, rule in registry.countries)


# --- the record -----------------------------------------------------------------------


class SecLike(Protocol):
    """What the statements need from fetch.SecContext (a test can hand in a stand-in)."""

    user_agent: str
    tickers: dict[str, object]
    tags: reference.XbrlTags
    definitions: reference.FieldDefinitions


def statements_on(symbol: str, d: date, sec: SecLike, notes: list[str]) -> tuple[list[boundary.FiscalPeriod], fetch_sec.Decision | None, str | None, boundary.Submission | None, Mapping[str, object] | None]:
    """(periods, decision, why none, submission on d, facts as filed by d)."""
    cik = fetch_sec.cik_for(symbol, sec.tickers)
    if cik is None:
        return [], None, VENDOR_REASON, None, None
    facts = fetch_sec.companyfacts(cik, sec.user_agent)
    if facts is None:
        return [], None, VENDOR_REASON, None, None
    filtered = filed_on_or_before(facts, d)
    submission, _ = fetch_sec.latest_annual_submission(submissions_on_or_before(fetch_sec.submissions(cik, sec.user_agent), d))
    decision = fetch_sec.decide(filtered, sec.tags)
    if not decision.xbrl or decision.currency is None:
        return [], decision, VENDOR_REASON, submission, filtered
    periods = fetch_sec.periods_from_facts(decision.facts, sec.tags, sec.definitions, notes, taxonomy=decision.taxonomy, unit=decision.currency, dei=decision.dei)
    notes.append(f"CIK {cik}: {len(decision.facts)} {decision.taxonomy} tags filed by {d}; {len(periods)} annual periods in {decision.currency}")
    lag = fetch.lag_of(submission, periods)
    if lag is not None:
        facts_age = (d - date.fromisoformat(lag.facts_filed)).days
        if facts_age > sec.tags.max_filing_age_days:
            return periods, decision, f"filed statements lag on {d}: {lag.text}", submission, filtered
        notes.append(f"{lag.text} on {d}; the facts are {facts_age} days old, within max_filing_age_days, so the filing is kept")
    return periods, decision, None, submission, filtered


def record(symbol: str, d: date, sec: SecLike, history: History, quote: fetch.Quote | None, profile: fetch.Profile | None) -> boundary.Financials:
    notes: list[str] = []
    periods, decision, why, submission, facts = statements_on(symbol, d, sec, notes)
    priced = price_on(history, d)
    shares = dei_shares(facts, d) if facts is not None else None
    trading = quote.trading_currency if quote else None
    divisor = quote.price_unit_divisor if quote else 1.0
    price = None if priced is None else priced[1] * priced[2] / divisor
    market_cap = None if price is None or shares is None else price * shares[0]
    filing_currency = decision.currency if decision is not None and decision.xbrl else None
    currency = filing_currency if filing_currency is not None and filing_currency == trading else None
    rate_country = None
    if trading is not None:
        fx_sources = reference.FxSources.from_json_string((REFERENCE / "fx_sources.json").read_text())
        rate_country = dict(fx_sources.currency_countries).get(trading)
    rates_unavailable = None if why is not None or rate_country is None or rate_history_available(rate_country) else trading
    if priced is None:
        notes.append(f"no close within 10 days on or before {d}")
    pit = boundary.PointInTime(
        as_of_date=d.isoformat(),
        price_date=None if priced is None else priced[0].isoformat(),
        close_as_served=None if priced is None else priced[1],
        split_factor=None if priced is None else priced[2],
        shares_source="dei cover page",
        shares_tag=None if shares is None else shares[1],
        shares_as_of=None if shares is None else shares[2],
        shares_filed=None if shares is None else shares[3],
        rate_observations=[],
        anachronistic_inputs=[],
        statements_unavailable=why,
        shares_unavailable=None if shares is not None or why is not None else SHARES_REASON,
        rates_unavailable=rates_unavailable,
    )
    provider = fetch_sec.PROVIDER if why is None else "yfinance"
    return boundary.Financials(
        ticker=symbol, as_of=f"{d.isoformat()}T00:00:00+00:00",
        currency=currency, financial_currency=filing_currency if why is None else (quote.financial_currency if quote else None),
        trading_currency=trading,
        price_unit=boundary.PriceUnit(boundary.Minor() if quote and quote.currency in fetch.MINOR_UNITS else boundary.Major()),
        price_unit_divisor=divisor, price=price, market_cap=market_cap,
        country=profile.country if profile else None, industry=profile.industry if profile else None,
        periods=periods if why is None else [], notes=notes, provider=provider,
        taxonomy=decision.taxonomy if decision is not None and why is None else "",
        vendor_financial_currency=(quote.financial_currency if quote else None) if why is None else None,
        market_provider="yfinance (closes and splits), SEC dei (shares)", provider_reason=(decision.reason if decision is not None and why is None else why or ""),
        latest_filing=fetch_sec.latest_filing(periods) if why is None else None,
        submissions_latest_annual=submission, point_in_time=pit,
    )


def run_date(d: date, tickers: list[str], *, histories: dict[str, History], quotes: dict[str, tuple[fetch.Quote | None, fetch.Profile | None]],
             sec: SecLike, out_root: Path = PIT_ROOT) -> Path:
    """data/pit/<D>/ with a record per ticker and the reference as of D."""
    out = out_root / d.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    records: list[boundary.Financials] = []
    for symbol in tickers:
        if symbol not in histories:
            histories[symbol] = History.fetch(symbol)
        if symbol not in quotes:
            quotes[symbol] = fetch._info(yf.Ticker(symbol), [])  # pyright: ignore[reportPrivateUsage]
        quote, profile = quotes[symbol]
        records.append(record(symbol, d, sec, histories[symbol], quote, profile))
    countries: set[str] = set()
    currencies: set[str] = set()
    fx_sources = reference.FxSources.from_json_string((REFERENCE / "fx_sources.json").read_text())
    for r in records:
        if r.point_in_time is None or r.point_in_time.statements_unavailable is not None:
            continue
        if r.trading_currency is not None:
            country = dict(fx_sources.currency_countries).get(r.trading_currency)
            if country is not None:
                countries.add(country)
            if r.trading_currency != "USD":
                currencies.add(r.trading_currency)
        if r.financial_currency is not None and r.financial_currency != "USD":
            currencies.add(r.financial_currency)
    key = rr._api_key()  # pyright: ignore[reportPrivateUsage]
    observed = write_reference(d, out / "reference", countries=countries, currencies=currencies, key=key)
    for r in records:
        if r.point_in_time is not None and r.point_in_time.statements_unavailable is None:
            r.point_in_time.rate_observations = sorted(observed.items())
        text = r.to_json_string(indent=2, allow_nan=False)
        boundary.Financials.from_json_string(text)
        (out / f"{r.ticker}.json").write_text(text + "\n")
    return out
