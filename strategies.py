import pandas as pd
import ta

class BaseStrategy:
    name = "base"
    description = "Base strategy class"

    def __init__(self, stop_loss_pct=2.0, take_profit_pct=4.0, position_size_pct=10.0):
        self.stop_loss_pct     = stop_loss_pct
        self.take_profit_pct   = take_profit_pct
        self.position_size_pct = position_size_pct

    def generate_signal(self, df: pd.DataFrame) -> str:
        raise NotImplementedError

    def calc_stop_loss(self, entry_price):
        return entry_price * (1 - self.stop_loss_pct / 100)

    def calc_take_profit(self, entry_price):
        return entry_price * (1 + self.take_profit_pct / 100)

    def calc_position_size(self, balance, price):
        return (balance * (self.position_size_pct / 100)) / price


class RSIStrategy(BaseStrategy):
    name = "RSI"
    description = "Buy when RSI < 30 (oversold), sell when RSI > 70 (overbought)"

    def __init__(self, rsi_period=14, oversold=30, overbought=70, **kwargs):
        super().__init__(**kwargs)
        self.rsi_period  = rsi_period
        self.oversold    = oversold
        self.overbought  = overbought

    def generate_signal(self, df: pd.DataFrame) -> str:
        rsi = ta.momentum.RSIIndicator(df["close"], window=self.rsi_period).rsi()
        if rsi.isna().all():
            return "hold"
        val = rsi.iloc[-1]
        if val < self.oversold:
            return "buy"
        if val > self.overbought:
            return "sell"
        return "hold"


class MACrossStrategy(BaseStrategy):
    name = "MA Crossover"
    description = "Buy when fast MA crosses above slow MA, sell on crossover below"

    def __init__(self, fast=9, slow=21, **kwargs):
        super().__init__(**kwargs)
        self.fast = fast
        self.slow = slow

    def generate_signal(self, df: pd.DataFrame) -> str:
        df = df.copy()
        df["fast_ma"] = df["close"].rolling(self.fast).mean()
        df["slow_ma"] = df["close"].rolling(self.slow).mean()
        if df["fast_ma"].isna().iloc[-1] or df["slow_ma"].isna().iloc[-1]:
            return "hold"
        prev_fast, prev_slow = df["fast_ma"].iloc[-2], df["slow_ma"].iloc[-2]
        curr_fast, curr_slow = df["fast_ma"].iloc[-1], df["slow_ma"].iloc[-1]
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return "buy"
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            return "sell"
        return "hold"


class BollingerStrategy(BaseStrategy):
    name = "Bollinger Bands"
    description = "Buy at lower band, sell at upper band"

    def __init__(self, period=20, std=2.0, **kwargs):
        super().__init__(**kwargs)
        self.period = period
        self.std    = std

    def generate_signal(self, df: pd.DataFrame) -> str:
        bb = ta.volatility.BollingerBands(df["close"], window=self.period, window_dev=self.std)
        price = df["close"].iloc[-1]
        lower = bb.bollinger_lband().iloc[-1]
        upper = bb.bollinger_hband().iloc[-1]
        if price <= lower:
            return "buy"
        if price >= upper:
            return "sell"
        return "hold"


STRATEGIES = {
    "RSI":             RSIStrategy,
    "MA Crossover":    MACrossStrategy,
    "Bollinger Bands": BollingerStrategy,
}
