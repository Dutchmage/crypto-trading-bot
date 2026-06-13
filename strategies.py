import pandas as pd
import pandas_ta as ta

# ─────────────────────────────────────────────
#  Base Strategy
# ─────────────────────────────────────────────
class BaseStrategy:
    name = "base"
    description = "Base strategy class"

    def __init__(self, stop_loss_pct=2.0, take_profit_pct=4.0, position_size_pct=10.0):
        """
        stop_loss_pct    : % below entry to place stop loss
        take_profit_pct  : % above entry to place take profit
        position_size_pct: % of total balance to use per trade
        """
        self.stop_loss_pct     = stop_loss_pct
        self.take_profit_pct   = take_profit_pct
        self.position_size_pct = position_size_pct

    def generate_signal(self, df: pd.DataFrame) -> str:
        """Return 'buy', 'sell', or 'hold'"""
        raise NotImplementedError

    def calc_stop_loss(self, entry_price: float) -> float:
        return entry_price * (1 - self.stop_loss_pct / 100)

    def calc_take_profit(self, entry_price: float) -> float:
        return entry_price * (1 + self.take_profit_pct / 100)

    def calc_position_size(self, balance: float, price: float) -> float:
        usdt_to_use = balance * (self.position_size_pct / 100)
        return usdt_to_use / price


# ─────────────────────────────────────────────
#  Strategy 1: RSI
# ─────────────────────────────────────────────
class RSIStrategy(BaseStrategy):
    name = "RSI"
    description = "Buy when RSI < 30 (oversold), sell when RSI > 70 (overbought)"

    def __init__(self, rsi_period=14, oversold=30, overbought=70, **kwargs):
        super().__init__(**kwargs)
        self.rsi_period  = rsi_period
        self.oversold    = oversold
        self.overbought  = overbought

    def generate_signal(self, df: pd.DataFrame) -> str:
        df = df.copy()
        df.ta.rsi(length=self.rsi_period, append=True)
        col = f"RSI_{self.rsi_period}"
        if col not in df.columns or df[col].isna().all():
            return "hold"
        rsi = df[col].iloc[-1]
        if rsi < self.oversold:
            return "buy"
        if rsi > self.overbought:
            return "sell"
        return "hold"


# ─────────────────────────────────────────────
#  Strategy 2: Moving Average Crossover
# ─────────────────────────────────────────────
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
        prev_fast = df["fast_ma"].iloc[-2]
        prev_slow = df["slow_ma"].iloc[-2]
        curr_fast = df["fast_ma"].iloc[-1]
        curr_slow = df["slow_ma"].iloc[-1]
        if prev_fast <= prev_slow and curr_fast > curr_slow:
            return "buy"
        if prev_fast >= prev_slow and curr_fast < curr_slow:
            return "sell"
        return "hold"


# ─────────────────────────────────────────────
#  Strategy 3: Bollinger Band Bounce
# ─────────────────────────────────────────────
class BollingerStrategy(BaseStrategy):
    name = "Bollinger Bands"
    description = "Buy at lower band, sell at upper band"

    def __init__(self, period=20, std=2.0, **kwargs):
        super().__init__(**kwargs)
        self.period = period
        self.std    = std

    def generate_signal(self, df: pd.DataFrame) -> str:
        df = df.copy()
        df.ta.bbands(length=self.period, std=self.std, append=True)
        lower_col = f"BBL_{self.period}_{self.std}"
        upper_col = f"BBU_{self.period}_{self.std}"
        if lower_col not in df.columns or upper_col not in df.columns:
            return "hold"
        price = df["close"].iloc[-1]
        lower = df[lower_col].iloc[-1]
        upper = df[upper_col].iloc[-1]
        if price <= lower:
            return "buy"
        if price >= upper:
            return "sell"
        return "hold"


# ─────────────────────────────────────────────
#  Registry — add new strategies here
# ─────────────────────────────────────────────
STRATEGIES = {
    "RSI":             RSIStrategy,
    "MA Crossover":    MACrossStrategy,
    "Bollinger Bands": BollingerStrategy,
}
