import time
import threading
import ccxt
from datetime import datetime
from database import get_session, Trade, init_db
import os

TRADING_MODE  = os.getenv("TRADING_MODE", "paper")
API_KEY       = os.getenv("BINANCE_API_KEY", "")
API_SECRET    = os.getenv("BINANCE_SECRET_KEY", "")
TRADE_FEE     = 0.001
SCAN_INTERVAL = 10
MIN_PROFIT_PCT = 0.1

TRIANGLES = [
    ("BTC/USDT", "ETH/BTC",  "ETH/USDT"),
    ("BTC/USDT", "BNB/BTC",  "BNB/USDT"),
    ("ETH/USDT", "BNB/ETH",  "BNB/USDT"),
    ("BTC/USDT", "SOL/BTC",  "SOL/USDT"),
    ("ETH/USDT", "SOL/ETH",  "SOL/USDT"),
]

_lock            = threading.Lock()
_scanner_on      = False
_scanner_thread  = None
_last_scan       = []
_scan_log        = []
_trade_size      = 100.0
_total_profit    = 0.0
_trades_executed = 0


def get_state():
    with _lock:
        return {
            "running":         _scanner_on,
            "last_scan":       list(_last_scan),
            "scan_log":        list(_scan_log),
            "trade_size":      _trade_size,
            "total_profit":    _total_profit,
            "trades_executed": _trades_executed,
        }

def set_trade_size(size: float):
    global _trade_size
    with _lock:
        _trade_size = size

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
    try:
        ob  = exchange.fetch_order_book(symbol, limit=5)
        bid = ob["bids"][0][0] if ob["bids"] else None
        ask = ob["asks"][0][0] if ob["asks"] else None
        return bid, ask
    except Exception:
        return None, None

def calc_triangle_profit(exchange, triangle: tuple) -> dict:
    pair1, pair2, pair3 = triangle
    start_usdt = 1000.0
    _, ask1 = fetch_order_book_prices(exchange, pair1)
    if not ask1:
        return {"profitable": False, "error": f"No price for {pair1}"}
    coin1_amount = (start_usdt / ask1) * (1 - TRADE_FEE)
    _, ask2 = fetch_order_book_prices(exchange, pair2)
    if not ask2:
        return {"profitable": False, "error": f"No price for {pair2}"}
    coin2_amount = (coin1_amount / ask2) * (1 - TRADE_FEE)
    bid3, _ = fetch_order_book_prices(exchange, pair3)
    if not bid3:
        return {"profitable": False, "error": f"No price for {pair3}"}
    end_usdt = coin2_amount * bid3 * (1 - TRADE_FEE)
    profit_pct = ((end_usdt - start_usdt) / start_usdt) * 100
    profit_abs = end_usdt - start_usdt
    return {
        "triangle":   f"{pair1} → {pair2} → {pair3}",
        "start_usdt": round(start_usdt, 2),
        "end_usdt":   round(end_usdt, 2),
        "profit_pct": round(profit_pct, 4),
        "profit_abs": round(profit_abs, 4),
        "profitable": profit_pct > MIN_PROFIT_PCT,
        "prices": {
            pair1: round(ask1, 6),
            pair2: round(ask2, 6),
            pair3: round(bid3, 6),
        },
        "timestamp": datetime.utcnow().strftime("%H:%M:%S"),
    }

def scan_all_triangles() -> list:
    exchange = get_exchange()
    results  = []
    for triangle in TRIANGLES:
        result = calc_triangle_profit(exchange, triangle)
        if "error" not in result:
            results.append(result)
        time.sleep(0.1)
    return sorted(results, key=lambda x: x.get("profit_pct", -999), reverse=True)

def execute_paper_arb(triangle_result: dict, trade_size_usdt: float = 100.0) -> dict:
    global _total_profit, _trades_executed
    session = get_session()
    try:
        profit = (triangle_result["profit_pct"] / 100) * trade_size_usdt
        pairs  = triangle_result["triangle"].split(" → ")
        for i, pair in enumerate(pairs):
            leg_trade = Trade(
                symbol   = pair,
                side     = "buy" if i < 2 else "sell",
                amount   = trade_size_usdt / 100,
                price    = list(triangle_result["prices"].values())[i],
                strategy = "Triangular Arbitrage",
                mode     = TRADING_MODE,
                pnl      = round(profit, 6) if i == 2 else 0.0,
                closed   = True,
            )
            session.add(leg_trade)
        session.commit()
        with _lock:
            _total_profit    += profit
            _trades_executed += 1
        return {"success": True, "profit": round(profit, 6), "trade_size": trade_size_usdt, "triangle": triangle_result["triangle"]}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        session.close()

def _scanner_loop():
    global _scanner_on, _last_scan, _scan_log

    def log(msg):
        ts = datetime.utcnow().strftime("%H:%M:%S")
        entry = f"[{ts}] {msg}"
        with _lock:
            _scan_log.append(entry)
            if len(_scan_log) > 50:
                _scan_log.pop(0)

    log("🟢 Auto-scanner started")
    while True:
        with _lock:
            if not _scanner_on:
                break
            size = _trade_size
        try:
            results = scan_all_triangles()
            with _lock:
                _last_scan.clear()
                _last_scan.extend(results)
            best = results[0] if results else None
            if best and best.get("profitable"):
                log(f"✅ Opportunity: {best['triangle']} | {best['profit_pct']:+.4f}%")
                result = execute_paper_arb(best, trade_size_usdt=size)
                if result["success"]:
                    log(f"⚡ Executed! Profit: ${result['profit']:+.6f}")
                else:
                    log(f"❌ Execute failed: {result.get('error')}")
            else:
                best_pct = best["profit_pct"] if best else 0
                log(f"➖ No opportunity (best: {best_pct:+.4f}%)")
        except Exception as e:
            log(f"⚠️ Scan error: {str(e)[:60]}")
        for _ in range(SCAN_INTERVAL):
            with _lock:
                if not _scanner_on:
                    break
            time.sleep(1)
    log("🔴 Auto-scanner stopped")

def start_scanner():
    global _scanner_on, _scanner_thread
    with _lock:
        if _scanner_on:
            return False
        _scanner_on = True
    _scanner_thread = threading.Thread(target=_scanner_loop, daemon=True)
    _scanner_thread.start()
    return True

def stop_scanner():
    global _scanner_on
    with _lock:
        _scanner_on = False
    return True
