"""The rule panel: our own generic DCF on a universe chosen by a rule, each June.

    uv run python/rule_panel.py [--top 500] [--years 2013 2014 ...] [--check-rule]

The broad study showed that cheapness sorted returns on three thousand filers since 2022
while on this tool's own universe it did not, and the reason is the universe: its names were
asked for in 2026, many for what their prices had done. A backtest on names chosen in
hindsight says little about a model. This runs the real pipeline, the point-in-time fetch
and the OCaml binary, on names chosen by a rule that reads nothing later than the date.

The universe on each 30 June: among the broad panel's filers reporting current assets,
the [--top] largest by market value that June. Size on the day and nothing else. The names
in reference/holdout.json are left out, so the holdout stays unread.

The class. A class here is declared by a person, and nobody can read a thousand filers. So
the study declares one thing for all of them and says so: a filer whose SEC industry code
is not in EXCLUDED runs as an operating company under the generic DCF, and every other is
left out with the reason, never valued. That is the tool's own rule turned into a table:
a class the generic DCF misreads (a bank, an insurer, a utility, an extractive or plainly
cyclical business) is refused rather than valued. `--check-rule` measures the table against
the classes people declared in reference/universe.json before anything is run on it.

What the records can carry. No vendor statements are fetched (a thousand calls to an
endpoint that rate-limits), so there is no cross-check and a filer with no filed
operating-income line is refused by the EBIT policy; no vendor profile, so the country is
declared as the United States and the industry is absent, which gives every name a beta
of one, said on the record. Prices and splits are the vendor's daily history per ticker,
fetched once and kept. Statements are the filer's facts cut at the date, the same
point-in-time path the panel uses.

Contract. `data/broad/rule/panel.jsonl` holds one row per admitted name and June: the
record's status, fair value, margin of safety and refusal reason, the growth shadow's
margin, the quality score, and from the broad panel the market value, the earnings yield
and the next twelve months' return beside SPY's. `data/broad/rule/universe/<date>.json`
is the study's universe file for the date, with every name's industry code and whether the
rule admitted it. Nothing fetched is tracked."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import date
from pathlib import Path
from typing import cast

import anchor_study
import fetch
import fetch_sec
import pit

REPO_ROOT = Path(__file__).resolve().parents[1]
BROAD_PANEL = REPO_ROOT / "data" / "broad" / "panel.jsonl"
ROOT = REPO_ROOT / "data" / "broad" / "rule"
HISTORIES = ROOT / "histories"
OUT = REPO_ROOT / "output" / "rule_panel"
BINARY = REPO_ROOT / "_build" / "default" / "ocaml" / "bin" / "main.exe"
TRACKED_UNIVERSE = REPO_ROOT / "reference" / "universe.json"
PACE_SECONDS = 0.6
STUDY_CLASS = "OperatingCompany"
# SEC industry codes the generic DCF is not run on, each range with the class it stands for
# here and why. Declared for this study; a name outside every range runs as STUDY_CLASS.
EXCLUDED: tuple[tuple[int, int, str], ...] = (
    (1000, 1499, "extractive: mining and oil and gas, a through-cycle or reserve-life business"),
    (2911, 2911, "extractive: petroleum refining, a spread business"),
    (3312, 3317, "cyclical: steel"),
    (3711, 3716, "cyclical: motor vehicles"),
    (4400, 4499, "cyclical: shipping"),
    (4512, 4513, "cyclical: airlines"),
    (4900, 4999, "utility: electric, gas and water, a rate-base business"),
    (6000, 6199, "financial: banks and lenders"),
    (6210, 6219, "financial: security brokers and dealers"),
    (6300, 6499, "financial: insurers"),
    (6500, 6799, "financial: real estate, holding companies and trusts"),
)
# Measured against the declared classes with --check-rule before the first run and narrowed
# once on what it showed: semiconductors (3674) run, since five of the seven here are
# declared operating companies; exchanges (6200) and investment advisers (6282) run, since
# every one here is declared an operating company. What remains wrong is said by the check.
# How this tool's declared classes read against the rule: a class the generic DCF is
# admitted for here is 'runs', every other 'left out'.
GENERIC_DCF_CLASSES = frozenset({"OperatingCompany", "HighGrowthSoftware"})
Json = dict[str, object]


def excluded_reason(sic: int | None) -> str | None:
    """Why the rule leaves an industry code out, or None when it runs."""
    if sic is None:
        return "no industry code on the filer's SEC record"
    for lo, hi, why in EXCLUDED:
        if lo <= sic <= hi:
            return why
    return None


def sic_of(cik: str, user_agent: str) -> tuple[int | None, str]:
    index = fetch_sec.submissions(cik, user_agent)
    if index is None:
        return None, ""
    raw = index.get("sic")
    return (int(raw) if isinstance(raw, str) and raw.isdigit() else None), str(index.get("sicDescription", ""))


def top_by_cap(rows: list[Json], year: int, top: int, held_out: frozenset[str]) -> list[Json]:
    """The broad panel's rows formed in June of [year], reporting current assets and carrying
    a market value, the [top] largest by that value; held-out names never among them."""
    have = [r for r in rows if str(r["formation"]) == f"{year}-06" and isinstance(r.get("market_cap"), float)
            and r.get("current_assets") is not None and str(r["ticker"]) not in held_out]
    return sorted(have, key=lambda r: (-cast(float, r["market_cap"]), str(r["ticker"])))[:top]


def history_of(ticker: str) -> pit.History | None:
    """The vendor's daily closes and splits, fetched once and kept under data/broad/rule/."""
    path = HISTORIES / f"{ticker}.json"
    if path.exists():
        raw = cast(Json, json.loads(path.read_text()))
        if raw.get("empty"):
            return None
        return pit.History({date.fromisoformat(d): v for d, v in cast(dict[str, float], raw["closes"]).items()},
                           {date.fromisoformat(d): v for d, v in cast(dict[str, float], raw["splits"]).items()},
                           {date.fromisoformat(d): v for d, v in cast(dict[str, float], raw["volumes"]).items()})
    time.sleep(PACE_SECONDS)
    try:
        h = pit.History.fetch(ticker, start="2009-01-01")
    except Exception:  # noqa: BLE001
        h = pit.History({}, {})
    path.parent.mkdir(parents=True, exist_ok=True)
    if not h.closes:
        path.write_text(json.dumps({"empty": True}))
        return None
    path.write_text(json.dumps({"closes": {d.isoformat(): v for d, v in h.closes.items()}, "splits": {d.isoformat(): v for d, v in h.splits.items()},
                                "volumes": {d.isoformat(): v for d, v in h.volumes.items()}}))
    return h


def check_rule(user_agent: str) -> str:
    """The rule against the classes people declared: for every tracked universe name with a
    filer, whether the rule runs it and whether the declared class admits the generic DCF."""
    entries = cast(list[Json], json.loads(TRACKED_UNIVERSE.read_text())["tickers"])
    cells: dict[tuple[bool, bool], list[str]] = {}
    for e in entries:
        cik = cast(str | None, e.get("cik") or e.get("map_cik"))
        if cik is None:
            continue
        sic, _ = sic_of(cik, user_agent)
        runs = excluded_reason(sic) is None
        declared = str(e["entity_class"]) in GENERIC_DCF_CLASSES
        cells.setdefault((runs, declared), []).append(f"{e['ticker']}({e['entity_class']}, {sic})")
    lines = ["the industry-code rule against the declared classes, names with a filer:"]
    for (runs, declared), label in (((True, True), "the rule runs it and the declared class admits the generic DCF"),
                                    ((False, False), "the rule leaves it out and the declared class does not admit the generic DCF"),
                                    ((True, False), "the rule runs it, the declared class does not admit the generic DCF"),
                                    ((False, True), "the rule leaves it out, the declared class admits the generic DCF")):
        names = cells.get((runs, declared), [])
        lines.append(f"  {len(names):>3}  {label}")
        if runs != declared:
            lines.append("       " + ", ".join(sorted(names)))
    return "\n".join(lines) + "\n"


def run_year(year: int, rows: list[Json], top: int, sec: fetch.SecContext, held_out: frozenset[str], binary: Path, log: bool = True) -> list[Json]:
    d = date(year, 6, 30)
    chosen = top_by_cap(rows, year, top, held_out)
    universe: list[Json] = []
    admitted: list[Json] = []
    for r in chosen:
        cik = str(r["cik"]).zfill(10)
        sic, description = sic_of(cik, sec.user_agent)
        why = excluded_reason(sic)
        universe.append({"ticker": r["ticker"], "cik": cik, "sic": sic, "sic_description": description, "admitted": why is None, "left_out": why})
        if why is None:
            admitted.append(r)
    (ROOT / "universe").mkdir(parents=True, exist_ok=True)
    (ROOT / "universe" / f"{d.isoformat()}.json").write_text(json.dumps(universe, indent=1) + "\n")
    tickers = [str(r["ticker"]) for r in admitted]
    ciks = {str(r["ticker"]): str(r["cik"]).zfill(10) for r in admitted}
    histories: dict[str, pit.History] = {}
    for i, t in enumerate(tickers, 1):
        h = history_of(t)
        if h is not None:
            histories[t] = h
        if log and i % 50 == 0:
            print(f"  {d}: prices {i}/{len(tickers)}", flush=True)
    priced = [t for t in tickers if t in histories]
    quote = fetch.Quote(currency="USD", financial_currency="USD", price=None, market_cap=None)
    profile = fetch.Profile(country="United States", industry=None)
    pit_dir = pit.run_date(d, priced, histories=histories, quotes={t: (quote, profile) for t in priced}, sec=sec, out_root=ROOT / "pit",
                           vendors={t: [] for t in priced}, ciks={t: ciks[t] for t in priced}, insiders=False)
    study_universe = {"notes": ["the rule panel's universe for the date: every name the industry-code rule admits, declared an operating company for the study"],
                      "tickers": [{"ticker": t, "entity_class": STUDY_CLASS, "why": "admitted by the rule panel's industry-code rule; declared for the study, not read by a person", "cik": ciks[t]} for t in priced]}
    universe_path = ROOT / "universe" / f"{d.isoformat()}.study.json"
    universe_path.write_text(json.dumps(study_universe, indent=1) + "\n")
    out = OUT / d.isoformat()
    out.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(binary), str(pit_dir), "--reference", str(pit_dir / "reference"), "--fetched", str(pit_dir / "reference"),
                    "--today", d.isoformat(), "--universe", str(universe_path), "--out", str(out)], check=True, capture_output=True, cwd=REPO_ROOT)
    by_ticker = {str(r["ticker"]): r for r in admitted}
    result: list[Json] = []
    for line in (out / "valuations.jsonl").read_text().splitlines():
        if not line.strip():
            continue
        v = cast(Json, json.loads(line))
        b = by_ticker.get(str(v["ticker"]))
        if b is None:
            continue
        shadow, quality = v.get("growth_shadow"), v.get("quality")
        cap, income = cast(float, b["market_cap"]), b.get("net_income")
        result.append({
            "ticker": v["ticker"], "date": d.isoformat(), "status": v["status"], "fair_value": v.get("fair_value"), "price": v.get("price"),
            "margin_of_safety": v.get("margin_of_safety"), "failed_reason": v.get("failed_reason"),
            "shadow_margin": cast(Json, shadow).get("margin_of_safety") if isinstance(shadow, dict) else None,
            "f_score": cast(Json, quality).get("f_score") if isinstance(quality, dict) else None,
            "market_cap": cap, "earnings_yield": (income / cap) if isinstance(income, float) else None,
            "forward_12m": b.get("forward_12m"), "spy_12m": b.get("spy_12m")})
    if log:
        ok = sum(1 for r in result if r["status"] == "Ok")
        print(f"{d}: {len(chosen)} largest, {len(admitted)} admitted by the rule, {len(priced)} with prices, {len(result)} records, {ok} Ok", flush=True)
    return result


RATE_HISTORY_START = "2009-01-01"


def main(argv: list[str]) -> int:
    # The point-in-time path keeps rate and currency history from 2020, which is as far back
    # as the panel's dates go. This study forms Junes from 2013, so it reads the series from
    # 2009 into a cache of its own and leaves the panel's cache and its start as they are.
    pit.HISTORY_START = RATE_HISTORY_START
    pit.FRED_CACHE = ROOT / "fred"
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--top", type=int, default=500, help="how many of the largest filers by market value each June")
    parser.add_argument("--years", nargs="*", type=int, default=list(range(2013, 2026)), help="the Junes to form; the DCF needs three filed years, so 2013 is the first")
    parser.add_argument("--check-rule", action="store_true", help="print the industry-code rule against the declared classes and stop")
    parser.add_argument("--binary", type=Path, default=BINARY)
    args = parser.parse_args(argv)
    binary: Path = args.binary
    sec = fetch.SecContext()
    if args.check_rule:
        sys.stdout.write(check_rule(sec.user_agent))
        return 0
    if not BROAD_PANEL.exists():
        print(f"{BROAD_PANEL} not built: run python/broad_panel.py first", file=sys.stderr)
        return 2
    if not binary.exists():
        print(f"{binary} not built: run dune build first", file=sys.stderr)
        return 2
    rows = [cast(Json, json.loads(line)) for line in BROAD_PANEL.read_text().splitlines() if line.strip()]
    held_out = anchor_study.load_holdout().names
    years = cast(list[int], args.years)
    panel_path = ROOT / "panel.jsonl"
    kept = [cast(Json, json.loads(line)) for line in panel_path.read_text().splitlines() if line.strip()] if panel_path.exists() else []
    kept = [r for r in kept if int(str(r["date"])[:4]) not in years]
    for year in years:
        kept += run_year(year, rows, int(args.top), sec, held_out, binary)
        ROOT.mkdir(parents=True, exist_ok=True)
        panel_path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in sorted(kept, key=lambda r: (str(r["date"]), str(r["ticker"])))))
    print(f"{len(kept)} rows -> {panel_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
