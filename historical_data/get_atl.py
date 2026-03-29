import os
import pathlib
import requests
import time
import ssl
import pandas as pd
import urllib3
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.util.ssl_ import create_urllib3_context

# Suppress the InsecureRequestWarning that appears when verify=False
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class TLSAdapter(HTTPAdapter):
    """Custom adapter that forces TLS 1.2+ with relaxed ciphers to fix
    SSLEOFError / UNEXPECTED_EOF_WHILE_READING on Windows."""

    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.set_ciphers("DEFAULT@SECLEVEL=1")
        ctx.options |= ssl.OP_NO_SSLv2 | ssl.OP_NO_SSLv3
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)


def _make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0 (compatible; TradingBot/1.0)"})
    retry = Retry(
        total=5,
        backoff_factor=1,          # waits 1, 2, 4, 8, 16 s between retries
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = TLSAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.verify = False         # Skip cert verification (fixes SSL EOF on Windows)
    return session


def get_full_historical(symbol: str, vs_currency: str = "USD"):
    all_data = []
    to_ts = -1
    previous_oldest = None
    session = _make_session()
    
    while True:
        url = (
            f"https://min-api.cryptocompare.com/data/v2/histoday"
            f"?fsym={symbol.upper()}&tsym={vs_currency}&limit=2000&toTs={to_ts}"
        )
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            
            if data.get("Response") != "Success" or not data.get("Data", {}).get("Data"):
                break
                
            batch = data["Data"]["Data"]
            if not batch:
                break
                
            all_data.extend(batch)
            
            # === NEW: Stop when we no longer get older data (prevents padding loop) ===
            oldest_ts = min(d["time"] for d in batch)
            if previous_oldest is not None and oldest_ts >= previous_oldest:
                break  # No new history → hit the real start of the coin
            previous_oldest = oldest_ts
            
            to_ts = oldest_ts - 1
            
            if len(batch) < 2000:
                break
                
            time.sleep(0.15)  # Very light politeness (CC allows ~100/min)
            
        except Exception as e:
            print(f"Error on {symbol}: {e}")
            break
    
    if not all_data:
        return pd.DataFrame()
    
    # === Clean the data once (removes any residual zeros/duplicates) ===
    df = pd.DataFrame(all_data)
    df = df.drop_duplicates(subset=['time'])                    # remove any overlap
    df = df.sort_values('time').reset_index(drop=True)
    df = df[(df['close'] > 0) & (df['time'] > 1_000_000)]      # real trading days only
    df['date'] = pd.to_datetime(df['time'], unit='s')
    
    print(f"{symbol}: Fetched {len(df)} real days (from {df['date'].min().date()})")
    return df


def compute_atl_and_ath_until_atl(df, symbol: str = "N/A"):
    if df.empty:
        return None
    atl_row = df.loc[df["low"].idxmin()]
    atl_price = atl_row["low"]
    atl_date = atl_row["date"]
    atl_ts = atl_row["time"]

    ath_row = df.loc[df["high"].idxmax()]
    ath_price = ath_row["high"]
    ath_date = ath_row["date"]
    
    period = df[df["time"] <= atl_ts]
    ath_until_atl = period["high"].max()
    ath_until_atl_date = period.loc[period["high"].idxmax()]["date"]
    
    return {
        "ticker": symbol,
        "atl_price": float(atl_price),
        "atl_date": atl_date.strftime("%Y-%m-%d"),
        "ath_price": float(ath_price),
        "ath_date": ath_date.strftime("%Y-%m-%d"),
        "ath_until_atl_price": float(ath_until_atl),
        "ath_until_atl_date": ath_until_atl_date.strftime("%Y-%m-%d"),
        "total_days": len(df)
    }


# ---------------------------------------------------------------------------
# Load tickers from tickers.txt (one ticker per line; # lines are comments)
# ---------------------------------------------------------------------------
TICKERS_FILE = pathlib.Path(__file__).parent / "tickers.txt"
OUTPUT_CSV   = pathlib.Path(__file__).parent / "atl_ath_stats.csv"

if not TICKERS_FILE.exists():
    raise FileNotFoundError(
        f"tickers.txt not found at {TICKERS_FILE}. "
        "Create it with one ticker symbol per line."
    )

tickers = [
    line.strip().upper()
    for line in TICKERS_FILE.read_text().splitlines()
    if line.strip() and not line.strip().startswith("#")
]

print(f"Loaded {len(tickers)} tickers from {TICKERS_FILE.name}: {tickers}\n")

# ---------------------------------------------------------------------------
# Run and write results incrementally (one row per ticker, saved immediately)
# ---------------------------------------------------------------------------
CSV_COLUMNS = [
    "ticker", "atl_price", "atl_date",
    "ath_price", "ath_date",
    "ath_until_atl_price", "ath_until_atl_date",
    "total_days",
]

# Write header once (overwrite any previous run)
pd.DataFrame(columns=CSV_COLUMNS).to_csv(OUTPUT_CSV, index=False)

for symbol in tickers:
    df = get_full_historical(symbol)
    stats = compute_atl_and_ath_until_atl(df, symbol)
    if stats:
        print(stats)
        # Append this row without rewriting the whole file
        pd.DataFrame([stats])[CSV_COLUMNS].to_csv(
            OUTPUT_CSV, mode="a", header=False, index=False
        )

print(f"\nDone! Results saved to: {OUTPUT_CSV}")