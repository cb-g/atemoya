"""Module execution: data fetching and analysis orchestration."""

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[3]

# Module fetch commands: module_name -> (script_path, args_template)
# args_template uses {ticker} as placeholder
FETCH_COMMANDS = {
    "analyst_upside": None,  # Fetched during analysis, not separately
    "dcf_deterministic": None,  # Fetched by OCaml binary itself
    "dcf_probabilistic": None,  # Fetched by OCaml binary itself
    "normalized_multiples": (
        "valuation/normalized_multiples/python/fetch/fetch_multiples_data.py",
        "--ticker {ticker}",
    ),
    "garp_peg": (
        "valuation/garp_peg/python/fetch/fetch_garp_data.py",
        "--ticker {ticker} --output valuation/garp_peg/data",
    ),
    "growth_analysis": (
        "valuation/growth_analysis/python/fetch/fetch_growth_data.py",
        "--ticker {ticker}",
    ),
    "dividend_income": (
        "valuation/dividend_income/python/fetch/fetch_dividend_data.py",
        "--ticker {ticker}",
    ),
    "etf_analysis": (
        "valuation/etf_analysis/python/fetch/fetch_etf_data.py",
        "{ticker}",
    ),
    "dcf_reit": (
        "valuation/dcf_reit/python/fetch/fetch_reit_data.py",
        "-t {ticker}",
    ),
    "crypto_treasury": (
        "valuation/crypto_treasury/python/crypto_valuation.py",
        "--ticker {ticker}",
    ),
}

# Data file patterns to check for staleness (module -> glob pattern relative to project root)
DATA_FILE_PATTERNS = {
    "normalized_multiples": "valuation/normalized_multiples/data/multiples_data_{ticker}.json",
    "garp_peg": "valuation/garp_peg/data/garp_data_{ticker}.json",
    "growth_analysis": "valuation/growth_analysis/data/growth_data_{ticker}.json",
    "dividend_income": "valuation/dividend_income/data/dividend_data_{ticker}.json",
    "etf_analysis": "valuation/etf_analysis/data/etf_data_{ticker}.json",
    "dcf_reit": "valuation/dcf_reit/data/{ticker}_reit_data.json",
}

# Analysis commands: module_name -> (command_template, uses_shell)
# Uses pre-built binaries from _build/ to avoid dune lock contention in parallel.
# {ticker} is the placeholder.
ANALYSIS_COMMANDS = {
    "analyst_upside": (
        "uv run valuation/analyst_upside/python/fetch_targets.py --tickers {ticker} --min-analysts 1 --output valuation/panel/output/analyst_{ticker}.json",
        False,
    ),
    "dcf_deterministic": (
        "_build/default/valuation/dcf_deterministic/ocaml/bin/main.exe -ticker {ticker} -json-output valuation/panel/output/dcf_det_{ticker}.json",
        False,
    ),
    "dcf_probabilistic": (
        "_build/default/valuation/dcf_probabilistic/ocaml/bin/main.exe -ticker {ticker} -json-output valuation/panel/output/dcf_prob_{ticker}.json",
        False,
    ),
    "normalized_multiples": (
        "_build/default/valuation/normalized_multiples/ocaml/bin/main.exe --tickers {ticker} --json --output valuation/normalized_multiples/output",
        False,
    ),
    "garp_peg": (
        "_build/default/valuation/garp_peg/ocaml/bin/main.exe --ticker {ticker}",
        False,
    ),
    "growth_analysis": (
        "_build/default/valuation/growth_analysis/ocaml/bin/main.exe --ticker {ticker}",
        False,
    ),
    "dividend_income": (
        "_build/default/valuation/dividend_income/ocaml/bin/main.exe --ticker {ticker}",
        False,
    ),
    "etf_analysis": (
        "_build/default/valuation/etf_analysis/ocaml/bin/main.exe valuation/etf_analysis/data/etf_data_{ticker}.json",
        False,
    ),
    "dcf_reit": (
        "_build/default/valuation/dcf_reit/ocaml/bin/main.exe -d valuation/dcf_reit/data -o valuation/dcf_reit/output/data -t {ticker}",
        False,
    ),
    "crypto_treasury": (
        "uv run valuation/crypto_treasury/python/crypto_valuation.py --ticker {ticker} --json",
        False,
    ),
}


def _is_fresh_today(filepath: Path) -> bool:
    """Check if a file was modified today."""
    if not filepath.exists():
        return False
    mtime = filepath.stat().st_mtime
    mod_date = date.fromtimestamp(mtime)
    return mod_date == date.today()


def _run_cmd(cmd: str, use_shell: bool = False, timeout: int = 300) -> tuple[int, str]:
    """Run a command and return (exit_code, output)."""
    try:
        result = subprocess.run(
            cmd if use_shell else cmd.split(),
            shell=use_shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(PROJECT_ROOT),
        )
        output = result.stdout + result.stderr
        return result.returncode, output
    except subprocess.TimeoutExpired:
        return -1, f"Timeout after {timeout}s"
    except Exception as e:
        return -1, str(e)


def fetch_data(
    execution_plan: dict[str, list[str]],
    fresh: bool = False,
    max_parallel: int = 8,
    quiet: bool = False,
) -> dict[str, dict[str, bool]]:
    """Fetch data for all (ticker, module) pairs. Returns success status."""
    results = {}

    # Build list of (ticker, module) pairs that need fetching
    fetch_tasks = []
    for ticker, modules in execution_plan.items():
        results[ticker] = {}
        for module in modules:
            fetch_info = FETCH_COMMANDS.get(module)
            if fetch_info is None:
                # Module handles its own fetching (dcf_deterministic, analyst_upside)
                results[ticker][module] = True
                continue

            script, args_template = fetch_info

            # Check if data is fresh
            if not fresh:
                pattern = DATA_FILE_PATTERNS.get(module, "")
                if pattern:
                    data_file = PROJECT_ROOT / pattern.format(ticker=ticker)
                    if _is_fresh_today(data_file):
                        if not quiet:
                            print(f"  [skip] {ticker}/{module}: data fresh today")
                        results[ticker][module] = True
                        continue

            fetch_tasks.append((ticker, module, script, args_template))

    if not fetch_tasks:
        return results

    if not quiet:
        print(f"Fetching data for {len(fetch_tasks)} ticker/module pairs...")

    def _do_fetch(task):
        ticker, module, script, args_template = task
        args = args_template.format(ticker=ticker)
        cmd = f"uv run {script} {args}"
        code, output = _run_cmd(cmd, timeout=120)
        return ticker, module, code == 0, output

    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        futures = [pool.submit(_do_fetch, t) for t in fetch_tasks]
        for future in as_completed(futures):
            ticker, module, success, output = future.result()
            results[ticker][module] = success
            if not quiet:
                status = "ok" if success else "FAIL"
                print(f"  [{status}] {ticker}/{module}")

    return results


def build_ocaml(modules: set[str], quiet: bool = False) -> bool:
    """Pre-build required OCaml executables (only valuation targets, not full repo)."""
    BUILD_TARGETS = {
        "dcf_deterministic": "valuation/dcf_deterministic/ocaml/bin/main.exe",
        "dcf_probabilistic": "valuation/dcf_probabilistic/ocaml/bin/main.exe",
        "normalized_multiples": "valuation/normalized_multiples/ocaml/bin/main.exe",
        "garp_peg": "valuation/garp_peg/ocaml/bin/main.exe",
        "growth_analysis": "valuation/growth_analysis/ocaml/bin/main.exe",
        "dividend_income": "valuation/dividend_income/ocaml/bin/main.exe",
        "etf_analysis": "valuation/etf_analysis/ocaml/bin/main.exe",
        "dcf_reit": "valuation/dcf_reit/ocaml/bin/main.exe",
    }
    targets = [BUILD_TARGETS[m] for m in modules if m in BUILD_TARGETS]
    if not targets:
        return True

    if not quiet:
        print(f"Building OCaml executables ({len(targets)} modules)...")

    cmd = f"eval $(opam env) && dune build {' '.join(targets)}"
    code, output = _run_cmd(cmd, use_shell=True, timeout=120)
    if code != 0 and not quiet:
        print(f"  Warning: dune build returned {code}", file=sys.stderr)
    return code == 0


def run_analysis(
    execution_plan: dict[str, list[str]],
    fetch_results: dict[str, dict[str, bool]],
    max_parallel: int = 8,
    quiet: bool = False,
) -> dict[str, dict[str, tuple[bool, str]]]:
    """Run analysis for all (ticker, module) pairs. Returns {ticker: {module: (success, output)}}."""
    results = {}
    tasks = []

    for ticker, modules in execution_plan.items():
        results[ticker] = {}
        for module in modules:
            # Skip if fetch failed
            if not fetch_results.get(ticker, {}).get(module, True):
                results[ticker][module] = (False, "Fetch failed")
                continue

            cmd_info = ANALYSIS_COMMANDS.get(module)
            if cmd_info is None:
                results[ticker][module] = (False, "No analysis command")
                continue

            cmd_template, use_shell = cmd_info
            cmd = cmd_template.format(ticker=ticker)
            tasks.append((ticker, module, cmd, use_shell))

    if not quiet:
        print(f"Running analysis for {len(tasks)} ticker/module pairs...")

    def _do_analyze(task):
        ticker, module, cmd, use_shell = task
        timeout = 600 if module == "dcf_probabilistic" else 180
        code, output = _run_cmd(cmd, use_shell=use_shell, timeout=timeout)
        return ticker, module, code == 0, output

    with ThreadPoolExecutor(max_workers=max_parallel) as pool:
        futures = [pool.submit(_do_analyze, t) for t in tasks]
        for future in as_completed(futures):
            ticker, module, success, output = future.result()
            results[ticker][module] = (success, output)
            if not quiet:
                status = "ok" if success else "FAIL"
                print(f"  [{status}] {ticker}/{module}")

    return results
