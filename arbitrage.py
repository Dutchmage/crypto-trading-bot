import time
import ccxt
from datetime import datetime
from database import get_session, Trade, DailyStats, init_db, get_paper_balance
import os

TRADING_MODE  = os.getenv("TRADING_MODE", "paper")
API_KEY       = os.getenv("BINANCE_API_KEY", "")
API_SECRET    = os.getenv("BINANCE_SECRET_KEY", "")
PAPER_BALANCE = float(os.getenv("PAPER_BALANCE", "10000.0"))
TRADE_FEE     = 0.001  # 0.1% per trade, 0.3% total for 3 legs

# Triangles to scan: (base, mid, quote) — all routed through USDT
TRIANGLES = [
    ("BTC/USDT", "ETH/BTC",  "ETH/USDT"),
    ("BTC/USDT", "BNB/BTC",  "BNB/USDT"),
    ("ETH/USDT", "BNB/ETH",  "BNB/USDT"),
    ("BTC/USDT", "SOL/BTC",  "SOL/USDT"),
    ("ETH/USDT", "SOL/ETH",  "SOL/USDT"),
]


def get_exchange():
    exchange = ccxt.binance({
        "apiKey": API_KEY,
        "secret": API_SECRET,
        "options": {"defaultType": "spot"},
    })
    if TRADING_MODE != "live":
        exchange.set_sandbox_mode(True)
    return exchange


def fetch_order_book_prices(exchange, symbol: str):
    """Returns best bid and ask for a symbol"""
    try:
        ob  = exchange.fetch_order_book(symbol, limit=5)
        bid = ob["bids"][0][0] if ob["bids"] else None
        ask = ob["asks"][0][0] if ob["asks"] else None
        return bid, ask
    except Exception:
        return None, None


def calc_triangle_profit(exchange, triangle: tuple) -> dict:
    """
    Simulate: USDT → coin1 → coin2 → USDT
    Returns profit % and details
    """
    pair1, pair2, pair3 = triangle
    start_usdt = 1000.0  # simulate with $1000

    # Leg 1: Buy coin1 with USDT  (pair1 = coin1/USDT)
    _, ask1 = fetch_order_book_prices(exchange, pair1)
    if not ask1:
        return {"profitable": False, "error": f"No price for {pair1}"}
    coin1_amount = (start_usdt / ask1) * (1 - TRADE_FEE)

    # Leg 2: Buy coin2 with coin1  (pair2 = coin2/coin1)
    _, ask2 = fetch_order_book_prices(exchange, pair2)
    if not ask2:
        return {"profitable": False, "error": f"No price for {pair2}"}
    coin2_amount = (coin1_amount / ask2) * (1 - TRADE_FEE)

    # Leg 3: Sell coin2 for USDT  (pair3 = coin2/USDT)
    bid3, _ = fetch_order_book_prices(exchange, pair3)
    if not bid3:
        return {"profitable": False, "error": f"No price for {pair3}"}
    end_usdt = coin2_amount * bid3 * (1 - TRADE_FEE)

    profit_pct = ((end_usdt - start_usdt) / start_usdt) * 100
    profit_abs = end_usdt - start_usdt

    return {
        "triangle":    f"{pair1} → {pair2} → {pair3}",
        "start_usdt":  round(start_usdt, 2),
        "end_usdt":    round(end_usdt, 2),
        "profit_pct":  round(profit_pct, 4),
        "profit_abs":  round(profit_abs, 4),
        "profitable":  profit_pct > 0.1,  # only flag if > 0.1% after fees
        "prices": {
            pair1: round(ask1, 6),
            pair2: round(ask2, 6),
            pair3: round(bid3, 6),
        },
        "timestamp": datetime.utcnow().strftime("%H:%M:%S"),
    }


def scan_all_triangles() -> list:
    """Scan all triangles and return results sorted by profit"""
    exchange = get_exchange()
    results  = []
    for triangle in TRIANGLES:
        result = calc_triangle_profit(exchange, triangle)
        if "error" not in result:
            results.append(result)
        time.sleep(0.1)  # be gentle with the API
    return sorted(results, key=lambda x: x.get("profit_pct", -999), reverse=True)


def execute_paper_arb(triangle_result: dict, trade_size_usdt: float = 100.0) -> dict:
    """
    Simulate executing an arbitrage trade on paper
    Records all 3 legs as trades in the database
    """
    session = get_session()
    try:
        profit = (triangle_result["profit_pct"] / 100) * trade_size_usdt
        pairs  = triangle_result["triangle"].split(" → ")

        for i, pair in enumerate(pairs):
            leg_trade = Trade(
                symbol   = pair,
                side     = "buy" if i < 2 else "sell",
                amount   = trade_size_usdt / 100,  # normalized
                price    = list(triangle_result["prices"].values())[i],
                strategy = "Triangular Arbitrage",
                mode     = TRADING_MODE,
                pnl      = profit if i == 2 else 0.0,
                closed   = True,
            )
            session.add(leg_trade)

        session.commit()
        return {
            "success":    True,
            "profit":     round(profit, 4),
            "trade_size": trade_size_usdt,
            "triangle":   triangle_result["triangle"],
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        session.close()
