# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# --- Do not remove these imports ---
import numpy as np
import pandas as pd
from datetime import datetime
from pandas import DataFrame
from typing import Dict, List
import json
import pathlib

from freqtrade.strategy import (
    IStrategy,
    Trade,
    BooleanParameter,
    CategoricalParameter,
    DecimalParameter,
    IntParameter,
)
import talib.abstract as ta
from technical import qtpylib

class FibonacciStrategy(IStrategy):
    """
    Enhanced Fibonacci Retracement Strategy
    - Uses pre-computed Fibonacci levels from historical_data/fib_levels.csv
    - Supports Long and Short positions
    - Hyperoptable touch tolerance (leeway)
    - Configurable multiple entry levels
    - Custom stoploss: 0% after 10 days
    """
    INTERFACE_VERSION = 3

    # Strategy parameters
    can_short: bool = True
    timeframe = '1d'
    minimal_roi = {
        "0": 0.20  # Take profit at 20%
    }
    stoploss = -0.99  # Wide stoploss, managed in custom_stoploss

    # --- Hyperopt parameters ---

    # Leeway (Touch Tolerance): 0% to 2%
    fib_leeway = DecimalParameter(0.0, 0.02, default=0.005, space='buy', optimize=True)

    # Long Entry Ratios (Toggle on/off)
    buy_fib_0236 = BooleanParameter(default=True, space='buy', optimize=True)
    buy_fib_0382 = BooleanParameter(default=True, space='buy', optimize=True)
    buy_fib_0500 = BooleanParameter(default=True, space='buy', optimize=True)
    buy_fib_0618 = BooleanParameter(default=True, space='buy', optimize=True)
    buy_fib_0650 = BooleanParameter(default=True, space='buy', optimize=True)
    buy_fib_0786 = BooleanParameter(default=True, space='buy', optimize=True)
    buy_fib_0886 = BooleanParameter(default=True, space='buy', optimize=True)

    # Short Entry Ratios (Toggle on/off)
    short_fib_0236 = BooleanParameter(default=True, space='sell', optimize=True)
    short_fib_0382 = BooleanParameter(default=True, space='sell', optimize=True)
    short_fib_0500 = BooleanParameter(default=True, space='sell', optimize=True)
    short_fib_0618 = BooleanParameter(default=True, space='sell', optimize=True)
    short_fib_0650 = BooleanParameter(default=True, space='sell', optimize=True)
    short_fib_0786 = BooleanParameter(default=True, space='sell', optimize=True)
    short_fib_0886 = BooleanParameter(default=True, space='sell', optimize=True)

    # Exit Ratios (Simplified for now, using a single ratio for exit signal)
    sell_fib_ratio = CategoricalParameter(['0.236', '0.382', '0.5', '0.618', '0.65', '0.786', '0.886', '1.0'], default='1.0', space='sell', optimize=True)
    exit_short_fib_ratio = CategoricalParameter(['0.0', '0.236', '0.382', '0.5', '0.618', '0.65', '0.786'], default='0.0', space='buy', optimize=True)

    # Startup period
    startup_candle_count: int = 0

    # Internal data
    fib_data: Dict[str, list] = {}
    RATIO_MAP = {
        '0236': '0.236', '0382': '0.382', '0500': '0.5', 
        '0618': '0.618', '0650': '0.65', '0786': '0.786', '0886': '0.886'
    }

    def __init__(self, config: dict) -> None:
        super().__init__(config)
        self.load_fibonacci_levels()

    def load_fibonacci_levels(self):
        """Loads the Fibonacci grids from the CSV file"""
        csv_path = pathlib.Path(__file__).parent.parent.parent / "historical_data" / "fib_levels.csv"
        if csv_path.exists():
            df = pd.read_csv(csv_path)
            for _, row in df.iterrows():
                ticker = row['ticker']
                # Store both spot and futures formats to be safe
                pairs = [f"{ticker}/USDT", f"{ticker}/USDT:USDT"]
                for p in pairs:
                    self.fib_data[p] = json.loads(row['fib_levels'])
        else:
            print(f"WARNING: Fibonacci levels file not found at {csv_path}")

    def get_fib_price(self, pair: str, price: float, ratio_str: str) -> float:
        """Finds the price for a given fib ratio in the appropriate grid."""
        if pair not in self.fib_data:
            return 0.0
        
        ratio = float(ratio_str)
        grids = self.fib_data[pair]
        
        active_grid = grids[-1]
        for g in grids:
            if g['top'] >= price:
                active_grid = g
                break
        
        levels = active_grid['levels']
        return float(levels.get(ratio_str, 0.0))

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        pair = metadata['pair']
        
        # All possible ratios
        ratios = ['0.0', '0.236', '0.382', '0.5', '0.618', '0.65', '0.786', '0.886', '1.0']
        
        for r in ratios:
            dataframe[f'fib_{r}'] = dataframe['close'].apply(lambda x: self.get_fib_price(pair, x, r))

        # Stochastic Oscillator (26 day period as requested)
        stoch = ta.STOCH(dataframe, fastk_period=26, slowk_period=3, slowd_period=3)
        dataframe['stoch_k'] = stoch['slowk']
        dataframe['stoch_d'] = stoch['slowd']

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        leeway = self.fib_leeway.value
        
        # --- Long Entries ---
        long_conditions = []
        for key, ratio in self.RATIO_MAP.items():
            param_name = f'buy_fib_{key}'
            if getattr(self, param_name).value:
                # Price within leeway zone of the Fibonacci level
                # Bounce/Touch: price came from above or is near the level
                condition = (
                    (dataframe['close'] <= dataframe[f'fib_{ratio}'] * (1 + leeway)) &
                    (dataframe['close'] >= dataframe[f'fib_{ratio}'] * (1 - leeway))
                )
                long_conditions.append(condition)

        if long_conditions:
            dataframe.loc[
                (
                    (np.logical_or.reduce(long_conditions)) &
                    (dataframe['stoch_k'] < 20) &  # Stochastic below 20 for long entries
                    (dataframe['volume'] > 0)
                ),
                'enter_long'] = 1

        # --- Short Entries ---
        short_conditions = []
        for key, ratio in self.RATIO_MAP.items():
            param_name = f'short_fib_{key}'
            if getattr(self, param_name).value:
                # Price within leeway zone of the Fibonacci level (acting as resistance)
                condition = (
                    (dataframe['close'] >= dataframe[f'fib_{ratio}'] * (1 - leeway)) &
                    (dataframe['close'] <= dataframe[f'fib_{ratio}'] * (1 + leeway))
                )
                short_conditions.append(condition)

        if short_conditions:
            dataframe.loc[
                (
                    (np.logical_or.reduce(short_conditions)) &
                    (dataframe['stoch_k'] > 80) &  # Stochastic above 80 for short entries
                    (dataframe['volume'] > 0)
                ),
                'enter_short'] = 1

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Long Exit (Take Profit/Resistance hit)
        sell_ratio = self.sell_fib_ratio.value
        dataframe.loc[
            (qtpylib.crossed_above(dataframe['close'], dataframe[f'fib_{sell_ratio}'])),
            'exit_long'] = 1

        # Short Exit (Take Profit/Support hit)
        exit_short_ratio = self.exit_short_fib_ratio.value
        dataframe.loc[
            (qtpylib.crossed_below(dataframe['close'], dataframe[f'fib_{exit_short_ratio}'])),
            'exit_short'] = 1

        return dataframe

    def custom_stoploss(self, pair: str, trade: Trade, current_time: datetime,
                        current_rate: float, current_profit: float, **kwargs) -> float:
        # 10 days rule
        time_diff = current_time - trade.open_date_utc
        if time_diff.days >= 10:
            if current_profit >= 0:
                # For both long and short, current_profit > 0 means we are in the green.
                # Locked in break-even (slightly below to avoid immediate exit on spread)
                return -0.001 
        
        return -0.99
