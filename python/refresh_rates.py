"""Regenerate the United States risk-free curve in reference/risk_free_rates.json from FRED.

    uv run python/refresh_rates.py

Pulls DGS1, DGS3, DGS5, DGS7 and DGS10 (constant-maturity Treasury yields, percent, daily)
from the FRED observations API, takes each series' latest observation whose value is not
"." (FRED's marker for a non-trading day), and writes the United States entry with
`source: FRED` and the observation date as `as_of`. Every other country's curve is left
untouched.

The API key is read from FRED_API_KEY, either already in the environment (direnv loads
.env on cd) or parsed from .env at the repo root. No key: exit non-zero, write nothing.
"""

from __future__ import annotations

import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

import reference

REPO_ROOT = Path(__file__).resolve().parent.parent
RATES_PATH = REPO_ROOT / "reference" / "risk_free_rates.json"
DOTENV_PATH = REPO_ROOT / ".env"
FRED_OBSERVATIONS = "https://api.stlouisfed.org/fred/series/observations"
SERIES = {"1y": "DGS1", "3y": "DGS3", "5y": "DGS5", "7y": "DGS7", "10y": "DGS10"}
COUNTRY = "United States"
PLAUSIBLE_RATE = (0.0, 0.30)  # decimal per year; outside this the response is not trusted


class Observation(BaseModel):
    """One row of a FRED observations response, untrusted until validated."""

    model_config = ConfigDict(frozen=True, strict=True)

    date: date
    value: str  # percent as text, or "." on a non-trading day


class Observations(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True)

    observations: list[Observation]


def _api_key() -> str:
    key = os.environ.get("FRED_API_KEY", "")
    if not key and DOTENV_PATH.is_file():
        for line in DOTENV_PATH.read_text().splitlines():
            name, sep, value = line.strip().partition("=")
            if sep and name.strip() == "FRED_API_KEY":
                key = value.strip().strip("'\"")
    if not key:
        sys.exit(
            "FRED_API_KEY is not set. Put it in .env at the repo root (see .env.example) "
            "or export it; nothing was written."
        )
    return key


def _latest(series_id: str, key: str) -> tuple[date, float]:
    """The newest observation with a value, as (observation date, decimal rate)."""
    query = urllib.parse.urlencode(
        {"series_id": series_id, "api_key": key, "file_type": "json", "sort_order": "desc", "limit": 5}
    )
    try:
        with urllib.request.urlopen(f"{FRED_OBSERVATIONS}?{query}", timeout=30) as response:
            body = response.read()
    except urllib.error.HTTPError as e:  # FRED explains itself in the body; the URL holds the key, so it is never echoed
        sys.exit(f"{series_id}: FRED returned HTTP {e.code}: {e.read().decode(errors='replace')[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"{series_id}: cannot reach FRED: {e.reason}")
    try:
        parsed = Observations.model_validate_json(body)
    except ValidationError as e:
        sys.exit(f"{series_id}: unexpected FRED response: {e}")
    for observation in parsed.observations:  # newest first: sort_order=desc
        if observation.value == ".":
            continue
        try:
            rate = round(float(observation.value) / 100.0, 6)  # FRED quotes 2 dp of a percent; 6 dp is exact
        except ValueError:
            sys.exit(f"{series_id}: value {observation.value!r} on {observation.date} is not a number")
        if not PLAUSIBLE_RATE[0] <= rate <= PLAUSIBLE_RATE[1]:
            sys.exit(f"{series_id}: implausible rate {observation.value}% on {observation.date}")
        return observation.date, rate
    sys.exit(f"{series_id}: none of the last {len(parsed.observations)} observations has a value")


def main() -> int:
    key = _api_key()
    table = reference.RiskFreeRates.from_json_string(RATES_PATH.read_text())
    missing = [tenor for tenor in table.tenors if tenor not in SERIES]
    if missing:
        sys.exit(f"no FRED series mapped for tenor(s) {', '.join(missing)} listed in {RATES_PATH}")

    points = {tenor: _latest(series_id, key) for tenor, series_id in SERIES.items()}
    dates = sorted({observed for observed, _ in points.values()})
    as_of = dates[0]  # the oldest tenor's date, so the entry's age is never understated
    notes: list[str] = []
    if len(dates) > 1:
        notes.append(
            "tenors observed on different dates: "
            + ", ".join(f"{tenor} {observed.isoformat()}" for tenor, (observed, _) in points.items())
        )
    curve = reference.Curve(
        source="FRED",
        as_of=as_of.isoformat(),
        rates=[(tenor, rate) for tenor, (_, rate) in points.items()],
        estimated=[],
        notes=notes,
    )
    table.countries = [(COUNTRY, curve)] + [(c, v) for c, v in table.countries if c != COUNTRY]

    text = table.to_json_string(indent=2, allow_nan=False, ensure_ascii=False)
    reference.RiskFreeRates.from_json_string(text)  # parse-time type check of what we wrote
    RATES_PATH.write_text(text + "\n")
    rates = ", ".join(f"{tenor} {rate:.4%}" for tenor, (_, rate) in points.items())
    print(f"{COUNTRY}: as_of {as_of.isoformat()} from FRED: {rates} -> {RATES_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
