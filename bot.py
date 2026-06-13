import os
import ccxt
import pandas as pd
from datetime import datetime, date
from database import get_session, Trade, Position, DailyStats, init_db
from strategies import STRATEGIES

# ─────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────
TRADING_MODE     = os.getenv("TRADING_MODE", "paper")   # "paper" or "live"
API_KEY          = os.getenv("BINANCE_API_KEY", "")
API_SECRET       = os.getenv("BINANCE_SECRET_KEY", "")
MAX_DAILY_LOSS   = float(os.getenv("MAX_DAILY_LOSS_PCT", "5.0"))   # % of balance
PAPER_BALANCE    = float(os.getenv("PAPER_BALANCE", "10000.0"))    # starting USDT

SUPPORTED_PAIRS = ["BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "ADA/USDT"]


# ─────────────────────────────────────────────
#  Exchange Connection
# ─────────────────────────────────────────────
def get_exchange():
    if TRADING_MODE == "live":
        exchange = ccxt.binance({
            "apiKey":  API_KEY,
            "secret":  API_SECRET,
            "options": {"defaultType": "spot"},
        })
    else:
        exchange = ccxt.binance({
            "apiKey":  API_KEY,
            "secret":  API_SECRET,
            "options": {"defaultType": "spot"},
        })
        exchange.set_sandbox_mode(True)
    return exchange


def fetch_ohlcv(symbol: str, timeframe: str = "1h", limit: int = 100) -> pd.DataFrame:
    exchange = get_exchange()
    raw = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def fetch_ticker(symbol: str) -> dict:
    exchange = get_exchange()
    return exchange.fetch_ticker(symbol)


def fetch_all_tickers() -> dict:
    """Returns {symbol: price} for all supported pairs"""
    prices = {}
    exchange = get_exchange()
    for symbol in SUPPORTED_PAIRS:
        try:
            ticker = exchange.fetch_ticker(symbol)
            prices[symbol] = ticker["last"]
        except Exception:
            prices[symbol] = None
    return prices


# ─────────────────────────────────────────────
#  Paper Trading Balance
# ─────────────────────────────────────────────
def get_paper_balance(session) -> float:
    """Calculate remaining paper balance from trade history"""
    trades = session.query(Trade).filter_by(mode="paper").all()
    spent = sum(t.amount * t.price for t in trades if t.side == "buy" and not t.closed)
    pnl   = sum(t.pnl for t in trades if t.closed)
    return PAPER_BALANCE - spent + pnl


# ─────────────────────────────────────────────
#  Daily Loss Guard
# ─────────────────────────────────────────────
def daily_loss_exceeded(session, balance: float) -> bool:
    today = str(date.today())
    stats = session.query(DailyStats).filter_by(date=today).first()
    if not stats:
        return False
    max_loss = balance * (MAX_DAILY_LOSS / 100)
    return stats.realized_pnl < -max_loss


# ─────────────────────────────────────────────
#  Core Bot Logic
# ─────────────────────────────────────────────
class TradingBot:
    def __init__(self, strategy_name: str, symbol: str, timeframe: str = "1h"):
        self.strategy     = STRATEGIES[strategy_name]()
        self.strategy_name = strategy_name
        self.symbol       = symbol
        self.timeframe    = timeframe
        init_db()

    def run_once(self) -> dict:
        """Run one cycle: fetch data → generate signal → act"""
        session = get_session()
        result  = {"symbol": self.symbol, "strategy": self.strategy_name, "action": "hold", "reason": ""}

        try:
            # Fetch OHLCV data
            df     = fetch_ohlcv(self.symbol, self.timeframe)
            price  = df["close"].iloc[-1]
            signal = self.strategy.generate_signal(df)
            result["signal"] = signal
            result["price"]  = price

            # Check daily loss limit
            balance = get_paper_balance(session) if TRADING_MODE == "paper" else self._get_live_balance(session)
            if daily_loss_exceeded(session, balance):
                result["action"] = "blocked"
                result["reason"] = "Daily loss limit reached"
                return result

            # Check existing position
            position = session.query(Position).filter_by(symbol=self.symbol).first()

            # --- SELL / STOP LOGIC ---
            if position:
                sl_hit = price <= position.stop_loss
                tp_hit = price >= position.take_profit
                if signal == "sell" or sl_hit or tp_hit:
                    pnl = (price - position.entry_price) * position.amount
                    reason = "signal" if signal == "sell" else ("stop-loss" if sl_hit else "take-profit")
                    self._close_trade(session, position, price, pnl, reason)
                    result["action"] = "sell"
                    result["reason"] = reason
                    result["pnl"]    = round(pnl, 4)
                    return result

            # --- BUY LOGIC ---
            if signal == "buy" and not position:
                amount = self.strategy.calc_position_size(balance, price)
                if amount * price < 10:  # min order guard
                    result["reason"] = "Insufficient balance"
                    return result
                sl = self.strategy.calc_stop_loss(price)
                tp = self.strategy.calc_take_profit(price)
                self._open_trade(session, price, amount, sl, tp)
                result["action"] = "buy"
                result["amount"] = round(amount, 6)
                result["stop_loss"]    = round(sl, 4)
                result["take_profit"]  = round(tp, 4)

        except Exception as e:
            result["reason"] = str(e)
        finally:
            session.close()

        return result

    def _open_trade(self, session, price, amount, sl, tp):
        trade = Trade(
            symbol=self.symbol, side="buy", amount=amount,
            price=price, strategy=self.strategy_name, mode=TRADING_MODE
        )
        position = Position(
            symbol=self.symbol, entry_price=price, amount=amount,
            strategy=self.strategy_name, stop_loss=sl,
            take_profit=tp, mode=TRADING_MODE
        )
        session.add(trade)
        session.add(position)
        self._update_daily_stats(session, 0, is_new_trade=True)
        session.commit()

    def _close_trade(self, session, position, price, pnl, reason):
        trade = Trade(
            symbol=self.symbol, side="sell", amount=position.amount,
            price=price, strategy=self.strategy_name,
            mode=TRADING_MODE, pnl=pnl, closed=True
        )
        session.add(trade)
        session.delete(position)
        self._update_daily_stats(session, pnl, is_win=(pnl > 0))
        session.commit()

    def _update_daily_stats(self, session, pnl, is_new_trade=False, is_win=None):
        today = str(date.today())
        stats = session.query(DailyStats).filter_by(date=today).first()
        if not stats:
            balance = get_paper_balance(session)
            stats = DailyStats(date=today, starting_balance=balance)
            session.add(stats)
        if is_new_trade:
            stats.trades_count += 1
        if pnl != 0:
            stats.realized_pnl += pnl
            if is_win:
                stats.wins += 1
            else:
                stats.losses += 1

    def _get_live_balance(self, session):
        exchange = get_exchange()
        balance  = exchange.fetch_balance()
        return balance["USDT"]["free"]
