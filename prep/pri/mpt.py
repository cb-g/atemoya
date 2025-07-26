from pathlib import Path
import yfinance as yf
import pandas as pd
import yaml

def load_tickers(yaml_path: Path) -> list[str]:
    with yaml_path.open("r") as f:
        data = yaml.safe_load(f)
    return data.get("tickers", [])

def download_adjusted_closes(tickers: list[str], start: str = "2010-01-01", end: str = None) -> pd.DataFrame:
    print(f"[INFO] Downloading data for tickers: {', '.join(tickers)}")
    df = yf.download(
        tickers=tickers,
        start=start,
        end=end,
        group_by="ticker",
        auto_adjust=False,
        progress=False,
    )
    return pd.DataFrame({t: df[t]["Adj Close"] for t in tickers})

def export_to_csv(output_dir: Path, data: dict[str, pd.DataFrame]):
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, df in data.items():
        out_path = output_dir / f"{name}.csv"
        df.to_csv(out_path, index=True)
        print(f"[INFO] Saved {name} to {out_path}")

def main():
    yaml_path = Path("data/tickers.yml")
    output_dir = Path("data/pri/mpt")

    tickers = load_tickers(yaml_path)
    prices = download_adjusted_closes(tickers)
    # log_returns = compute_log_returns(prices)

    export_to_csv(output_dir, {
        "adjusted_closes": prices,
    })

    print(f"[SUCCESS] Data exported to: {output_dir}")

if __name__ == "__main__":
    main()
