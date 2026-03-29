# AI Agent Instructions for Fibonacci Bot

Welcome! If you are an AI coding assistant (like GitHub Copilot, Cursor, or ChatGPT), this document contains the vital context and rules you need to interact with, understand, and optimize this Freqtrade trading repository.

## 1. Project Overview & Freqtrade Context

This project is an automated cryptocurrency trading bot built on top of [Freqtrade](https://www.freqtrade.io/).
The primary focus of this specific repository is the **FibonacciStrategy**, which utilizes custom data scripts alongside standard Freqtrade architecture.

### How Freqtrade Works (For AI Agents)
- **Architecture:** Freqtrade is an event-driven framework. The bot runs through "candles" (timeframes) and triggers `populate_indicators()`, `populate_entry_trend()`, and `populate_exit_trend()` on the active strategy.
- **Docker-First:** This repository is set up to run via Docker Compose. All major commands (backtesting, hyperopting, downloading data) MUST be executed through the `docker compose run --rm freqtrade <command>` wrapper to ensure the correct environment and dependencies are used.
- **State & Data:** Freqtrade stores downloaded historical data inside `user_data/data/`. User configurations, API keys, and strategy parameters are kept in `.json` files within `user_data/`. **NEVER commit sensitive `.json` configs with API keys.**

## 2. Directory Navigation

When navigating this repository, adhere to the standard Freqtrade layout:
- `user_data/strategies/`: Contains the core trading logic (`FibonacciStrategy.py`). This is your primary workspace for optimization.
- `historical_data/`: Contains custom Python scripts (like `fib_retracement.py` and `get_atl.py`) used to fetch or pre-calculate specific market data before Freqtrade runs.
- `user_data/backtest_config.json`: The main configuration file used during local testing.

## 3. The Strategy & Trading Logic

The core file is `user_data/strategies/FibonacciStrategy.py`.

### Strategy Mechanics
- The strategy calculates Fibonacci retracements between significant swing highs and lows.
- It is designed to support both **Long** and **Short** positions in a futures-mode setup.
- It utilizes a "leeway" or "tolerance" percentage. Price does not need to hit a Fibonacci level perfectly; it triggers if it enters the accepted tolerance zone around a level.

### Optimization Rules (Hyperopting)
When asked to optimize or modify the strategy:
1. **Understand the Spaces:** Freqtrade's Hyperopt feature searches for the best parameters. You will define the parameter spaces (e.g., IntegerParameter, DecimalParameter) directly inside the strategy class.
2. **Loss Function:** We utilize a custom or standard objective function (like `SharpeHyperOptLoss`) to determine the "best" set of parameters.
3. **Patience:** Hyperopting takes time. When writing hyperopt spaces, start with broad searches and refine them based on initial results.

## 4. Execution Commands

These are the exact commands you MUST use when asked to execute a backtest or a hyperopt session. They are predefined in `run.txt`.

### Backtesting
Run this command from the root directory to backtest the strategy on the historical data (from Jan 1, 2024 onwards):
```bash
docker compose run --rm freqtrade backtesting --config user_data/backtest_config.json --strategy FibonacciStrategy --timerange 20240101-
```

### Hyperoptimization
Run this command to optimize the buy and sell spaces over 100 epochs using the Sharpe ratio:
```bash
docker compose run --rm freqtrade hyperopt --config user_data/backtest_config.json --strategy FibonacciStrategy --hyperopt-loss SharpeHyperOptLoss --spaces buy sell --timerange 20240101- -e 100
```

## 5. Strict Rules for AI

1. **Test Every Logic Change:** If you modify `FibonacciStrategy.py`, you MUST formulate a plan to backtest it using the command above. Do not claim a logic change works without testing.
2. **Respect the Context:** When calculating indicators, you operate on pandas DataFrames (`dataframe['close']`). Do not use standard Python loops over the dataframe; use vectorized operations (e.g., NumPy or Pandas built-ins) for performance.
3. **Secrets:** You must never expose real API keys, tokens, or personal identifiers in your output or in commits.
