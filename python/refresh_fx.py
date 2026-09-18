"""Refresh reference/fx_rates.json from FRED's daily H.10 exchange-rate series.

    uv run python/refresh_fx.py --all
    uv run python/refresh_fx.py --currency BRL --currency EUR

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
FX_PATH = REPO_ROOT / "reference" / "fx_rates.json"
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


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--currency", action="append", default=[], help="an ISO 4217 code in the registry; repeatable")
    parser.add_argument("--all", action="store_true")
    args = parser.parse_args(argv)
    wanted: list[str] = [c.upper() for c in args.currency]
    registry = reference.FxSources.from_json_string(REGISTRY_PATH.read_text())
    table = reference.FxRates.from_json_string(FX_PATH.read_text())
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
        rr.write_atomically(FX_PATH, text + "\n")
        print(f"\nwrote {len(fetched)} rate(s) to {FX_PATH}")
    if failures:
        print(f"\n{len(failures)} currency(ies) failed and were left untouched: {', '.join(failures)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
