# Fibonacci Bot 📉

A custom crypto futures trading bot I built on [Freqtrade](https://www.freqtrade.io/) for a client project. The strategy enters long/short positions when price touches Fibonacci retracement levels (with a configurable tolerance zone), confirmed by a stochastic oscillator. It was backtested across 2022-2025 on 7 pairs (BTC, ETH, ADA, CHZ, DASH, ZEC, AAVE) and hyperopted with Sharpe-ratio loss.

## Why this exists

This was a paid gig. A client came to me with a trading idea rooted in Fibonacci retracements — price reacts at certain ratios (0.236, 0.382, 0.5, 0.618, 0.65, 0.786, 0.886) between significant swing highs and lows. My job was to translate that idea into something that actually executes trades, backtest it rigorously, and deploy it live.

I picked Freqtrade because it gave me a fast backtesting loop, Docker-based reproducibility, and hyperopt out of the box. That let me iterate on the client's ideas quickly instead of building trading infrastructure from scratch.

## How the strategy works

1. **Fibonacci grid construction** — `historical_data/get_atl.py` fetches full price history per ticker from CryptoCompare, finds the all-time low (ATL) and the all-time high before that ATL, and exports stats to CSV.
2. **Level computation** — `historical_data/fib_retracement.py` builds expanding Fibonacci grids anchored at the ATL, stacking each grid so its 0.236 level aligns with the previous grid's 1.0. It outputs a CSV the strategy loads at runtime and also generates Pine Script overlays for TradingView.
3. **Entry logic** (`FibonacciStrategy.py`) — on each daily candle, the bot checks if price wick crosses any active Fibonacci level within a hyperoptable leeway tolerance. Longs require stochastic K < 20 (oversold); shorts require K > 80 (overbought).
4. **Exit logic** — fixed ROI take-profit, wide stoploss managed by a custom time-based exit that force-closes trades after N days (hyperoptable 7-60).

## The honest result

We ran dozens of backtests and hyperopt sessions across different timeranges. The best config turned a 47% profit on the 2024 backtest with 493 trades and a 68% win rate — but that same config lost 10% on 2022 data and bled on walk-forward segments. The strategy was curve-fit to a specific period, and the client's performance expectations weren't met across broader market conditions.

## What I'd continue working on

- **Add regime filtering** (trend vs. range) — Fibonacci levels behave differently in trending vs. chopping markets.

## Tech stack

Python · Freqtrade · Docker · pandas/NumPy · TA-Lib · CCXT (via Freqtrade) · CryptoCompare API

## Project structure

```
user_data/strategies/FibonacciStrategy.py   # entry/exit logic, hyperopt params
historical_data/get_atl.py                   # fetches price history, computes ATL/ATH
historical_data/fib_retracement.py           # builds fib grids, exports CSV + Pine Script
user_data/backtest_config.json               # Freqtrade config (secrets scrubbed)
docker-compose.yml                           # Docker setup for backtesting & live runs
run.txt                                      # example backtest / hyperopt commands
```

## Run a backtest

```bash
docker compose run --rm freqtrade backtesting \
  --config user_data/backtest_config.json \
  --strategy FibonacciStrategy \
  --timerange 20240101-
```

See `run.txt` for hyperopt and plotting commands.
