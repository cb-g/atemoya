"""Refresh data/reference/fx_rates.json from FRED's daily H.10 exchange-rate series.

Nothing fetched from a provider is tracked (29): the file is gitignored, every user runs
this with their own FRED key, and a missing rate fails the record naming this refresher.

    uv run python/refresh_fx.py --all
    uv run python/refresh_fx.py --currency BRL --currency EUR
    uv run python/refresh_fx.py --daily

--daily (48) writes data/reference/fx_spot_daily.json instead: the ECB's daily reference
rates for every registry currency the ECB publishes, each against the euro, the dollar
cross recorded as the two ECB rates divided. It is the FX hedge's spot and nothing else
reads it; the valuation path keeps the weekly H.10 series and its age gate. Keyless.

reference/fx_sources.json is the registry: per currency the FRED series and its quote
direction. Each fetched entry is written with the series, direction, observation date and
the quote as FRED gives it, plus `usd_per_unit`, the one normalised number the valuation
uses (a cross rate is the ratio of two of these). Validation before write: a positive
finite quote, an as_of neither in the future nor older than 30 days. A currency that fails
leaves its existing entry untouched. FRED_API_KEY as for refresh_rates.py.
"""

from __future__ import annotations

import argparse
import sys
import urllib.parse
from datetime import date

import reference
import refresh_rates as rr

REPO_ROOT = rr.REPO_ROOT
FX_PATH = REPO_ROOT / "data" / "reference" / "fx_rates.json"
DAILY_PATH = REPO_ROOT / "data" / "reference" / "fx_spot_daily.json"
ECB_EXR = "https://data-api.ecb.europa.eu/service/data/EXR/D.{codes}.EUR.SP00.A?lastNObservations=1&format=csvdata"
DAILY_MAX_AGE_DAYS = 7
DAILY_SOURCE = "ECB reference rates, USD via EUR cross"
REGISTRY_PATH = REPO_ROOT / "reference" / "fx_sources.json"
MAX_OBSERVATION_AGE_DAYS = 30


def normalise(quoted: float, direction: str) -> float:
    if direction == "usd_per_unit":
        return quoted
    if direction == "units_per_usd":
        return 1.0 / quoted
    raise rr.RefreshError(f"unknown quote direction {direction!r}")


def fetch_currency(code: str, rule: reference.FxSource, key: str, today: date) -> reference.FxRate:
    query = urllib.parse.urlencode(
        {"series_id": rule.series, "api_key": key, "file_type": "json", "sort_order": "desc", "limit": 5}
    )
    observed, text = rr.parse_fred_latest(rr._get(f"{rr.FRED_OBSERVATIONS}?{query}"), rule.series)  # pyright: ignore[reportPrivateUsage]
    try:
        quoted = float(text)
    except ValueError as e:
        raise rr.RefreshError(f"{rule.series}: {text!r} is not a number") from e
    if not quoted > 0:
        raise rr.RefreshError(f"{rule.series}: quote {quoted} is not positive")
    if observed > today:
        raise rr.RefreshError(f"{rule.series}: as_of {observed} is in the future")
    if (today - observed).days > MAX_OBSERVATION_AGE_DAYS:
        raise rr.RefreshError(f"{rule.series}: as_of {observed} is {(today - observed).days} days old")
    return reference.FxRate(
        series=rule.series, direction=rule.direction, as_of=observed.isoformat(), quoted=quoted,
        usd_per_unit=round(normalise(quoted, rule.direction), 8),
    )


def parse_ecb_exr(text: str) -> dict[str, tuple[date, float]]:
    """The ECB's SDMX CSV: per currency the latest observation (units per euro) and its date."""
    out: dict[str, tuple[date, float]] = {}
    lines = text.splitlines()
    if not lines:
        raise rr.RefreshError("ECB: empty response")
    header = lines[0].split(",")
    try:
        c_ccy, c_period, c_value = header.index("CURRENCY"), header.index("TIME_PERIOD"), header.index("OBS_VALUE")
    except ValueError as e:
        raise rr.RefreshError("ECB: unexpected columns") from e
    for line in lines[1:]:
        cols = line.split(",")
        if len(cols) <= max(c_ccy, c_period, c_value) or not cols[c_value]:
            continue
        observed = date.fromisoformat(cols[c_period])
        value = float(cols[c_value])
        if cols[c_ccy] not in out or out[cols[c_ccy]][0] < observed:
            out[cols[c_ccy]] = (observed, value)
    return out


def usd_cross(usd_per_eur: float, units_per_eur: float) -> float:
    """Dollars per unit of the currency from the two ECB rates: (USD per EUR) / (units per EUR)."""
    return usd_per_eur / units_per_eur


def daily_spots(observations: dict[str, tuple[date, float]], wanted: list[str], today: date) -> tuple[dict[str, reference.FxSpot], list[str]]:
    """The daily spots for the wanted currencies; a currency the ECB does not publish, or
    whose observation is older than a week, is skipped and named."""
    if "USD" not in observations:
        raise rr.RefreshError("ECB: no USD/EUR observation")
    usd_date, usd_per_eur = observations["USD"]
    spots: dict[str, reference.FxSpot] = {}
    skipped: list[str] = []
    for code in wanted:
        if code == "EUR":
            spots[code] = reference.FxSpot(as_of=usd_date.isoformat(), per_eur=1.0, usd_per_unit=round(usd_per_eur, 8))
            continue
        if code not in observations or (today - observations[code][0]).days > DAILY_MAX_AGE_DAYS:
            skipped.append(code)
            continue
        observed, per_eur = observations[code]
        spots[code] = reference.FxSpot(as_of=min(observed, usd_date).isoformat(), per_eur=per_eur, usd_per_unit=round(usd_cross(usd_per_eur, per_eur), 8))
    return spots, skipped


def refresh_daily(registry: reference.FxSources, today: date) -> int:
    wanted = sorted(set(dict(registry.currencies)) | {"EUR"})
    codes = "+".join(sorted((set(wanted) - {"EUR"}) | {"USD"}))
    body = rr._get(ECB_EXR.format(codes=codes))  # pyright: ignore[reportPrivateUsage]
    spots, skipped = daily_spots(parse_ecb_exr(body.decode("utf-8")), wanted, today)
    table = reference.FxSpotDaily(source=DAILY_SOURCE, fetched_on=today.isoformat(),
                                  notes=["the FX hedge's spot only; the valuation path reads the weekly H.10 file", "fetched data, never tracked"],
                                  currencies=sorted(spots.items()))
    text = table.to_json_string(indent=2, allow_nan=False, ensure_ascii=False)
    reference.FxSpotDaily.from_json_string(text)
    DAILY_PATH.parent.mkdir(parents=True, exist_ok=True)
    rr.write_atomically(DAILY_PATH, text + "\n")
    for code, s in sorted(spots.items()):
        print(f"{code:5s} ECB {s.as_of}  {s.per_eur:g} per EUR  -> {s.usd_per_unit:.6f} USD per unit")
    print(f"\nwrote {len(spots)} daily spot(s) to {DAILY_PATH}" + (f"; not published or stale at the ECB: {', '.join(skipped)}" if skipped else ""))
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--currency", action="append", default=[], help="an ISO 4217 code in the registry; repeatable")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--daily", action="store_true", help="the ECB daily reference rates for the FX hedge's spot (48)")
    args = parser.parse_args(argv)
    wanted: list[str] = [c.upper() for c in args.currency]
    registry = reference.FxSources.from_json_string(REGISTRY_PATH.read_text())
    if args.daily:
        try:
            return refresh_daily(registry, date.today())
        except rr.RefreshError as e:
            sys.exit(str(e))
    table = (reference.FxRates.from_json_string(FX_PATH.read_text()) if FX_PATH.exists()
             else reference.FxRates(source="written by python/refresh_fx.py from the series in fx_sources.json; fetched data, never tracked", currencies=[]))
    rules = dict(registry.currencies)
    if args.all:
        wanted = list(rules)
    if not wanted:
        parser.error("give --currency CODE (repeatable) or --all")
    unknown = [c for c in wanted if c not in rules]
    if unknown:
        parser.error(f"not in {REGISTRY_PATH}: {', '.join(unknown)}")
    try:
        key = rr._api_key()  # pyright: ignore[reportPrivateUsage]
    except rr.RefreshError as e:
        sys.exit(str(e))
    today = date.today()
    fetched: dict[str, reference.FxRate] = {}
    failures: list[str] = []
    for code in wanted:
        try:
            fetched[code] = fetch_currency(code, rules[code], key, today)
        except rr.RefreshError as e:
            failures.append(code)
            print(f"{code:5s} FAILED  {e}", file=sys.stderr)
            continue
        r = fetched[code]
        print(f"{code:5s} {r.series:8s} as_of {r.as_of}  quoted {r.quoted:g} ({r.direction})  -> {r.usd_per_unit:.6f} USD per unit")
    if fetched:
        kept = [(c, v) for c, v in table.currencies if c not in fetched]
        table.currencies = sorted(list(fetched.items()) + kept)
        text = table.to_json_string(indent=2, allow_nan=False, ensure_ascii=False)
        reference.FxRates.from_json_string(text)
        FX_PATH.parent.mkdir(parents=True, exist_ok=True)
        rr.write_atomically(FX_PATH, text + "\n")
        print(f"\nwrote {len(fetched)} rate(s) to {FX_PATH}")
    if failures:
        print(f"\n{len(failures)} currency(ies) failed and were left untouched: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
