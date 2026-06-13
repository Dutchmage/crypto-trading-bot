import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import os

from database import init_db, get_session, Trade, Position, DailyStats
from bot import fetch_all_tickers, fetch_ohlcv, TradingBot, SUPPORTED_PAIRS, TRADING_MODE, get_paper_balance
from strategies import STRATEGIES
from arbitrage import scan_all_triangles, execute_paper_arb

# ─────────────────────────────────────────────
#  Page Config
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Crypto Trading Bot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────
#  Custom CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #0d1117; color: #e6edf3; }
    .metric-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 16px 20px;
        margin-bottom: 8px;
    }
    .metric-label { font-size: 12px; color: #8b949e; text-transform: uppercase; letter-spacing: 1px; }
    .metric-value { font-size: 28px; font-weight: 700; color: #e6edf3; }
    .metric-sub   { font-size: 13px; color: #8b949e; margin-top: 2px; }
    .green { color: #3fb950; }
    .red   { color: #f85149; }
    .mode-badge {
        display: inline-block;
        padding: 3px 10px;
        border-radius: 20px;
        font-size: 12px;
        font-weight: 600;
        background: #1f6feb;
        color: white;
    }
    div[data-testid="stMetricValue"] { font-size: 24px !important; }
    .stTabs [data-baseweb="tab"] { color: #8b949e; }
    .stTabs [aria-selected="true"] { color: #e6edf3; border-bottom: 2px solid #1f6feb; }
    .stDataFrame { background: #161b22; }
    thead tr th { background: #161b22 !important; }
</style>
""", unsafe_allow_html=True)

init_db()

# ─────────────────────────────────────────────
#  Sidebar
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Bot Controls")
    mode_label = "🟡 PAPER" if TRADING_MODE == "paper" else "🟢 LIVE"
    st.markdown(f"**Mode:** {mode_label}")
    st.divider()

    st.markdown("### Run a Strategy")
    selected_symbol   = st.selectbox("Asset", SUPPORTED_PAIRS)
    selected_strategy = st.selectbox("Strategy", list(STRATEGIES.keys()))
    selected_timeframe = st.selectbox("Timeframe", ["1m", "3m", "15m", "1h", "4h", "1d"])

    if st.button("▶ Run Once", use_container_width=True, type="primary"):
        with st.spinner("Running strategy..."):
            bot    = TradingBot(selected_strategy, selected_symbol, selected_timeframe)
            result = bot.run_once()
        action = result.get("action", "hold")
        if action == "buy":
            st.success(f"✅ BUY signal executed at ${result.get('price', 0):,.2f}")
        elif action == "sell":
            pnl = result.get("pnl", 0)
            color = "🟢" if pnl >= 0 else "🔴"
            st.info(f"{color} SELL executed | PnL: ${pnl:+.2f} ({result.get('reason','')})")
        elif action == "blocked":
            st.warning(f"⛔ {result.get('reason')}")
        else:
            st.info(f"⏸ Hold — no signal ({result.get('reason', 'waiting for signal')})")

    st.divider()
    st.markdown("### Risk Settings")
    st.caption("Configured via environment variables on Render")
    st.code(f"""MAX_DAILY_LOSS_PCT = {os.getenv('MAX_DAILY_LOSS_PCT', '5.0')}%
PAPER_BALANCE = ${os.getenv('PAPER_BALANCE', '10000')}
TRADING_MODE = {TRADING_MODE}""")

    if st.button("🔄 Refresh Dashboard", use_container_width=True):
        st.rerun()

# ─────────────────────────────────────────────
#  Main Content
# ─────────────────────────────────────────────
st.markdown("# 📈 Crypto Trading Dashboard")
st.markdown(f"*{TRADING_MODE.upper()} MODE — Last updated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC*")
st.divider()

session = get_session()
prices  = fetch_all_tickers()

# ─────────────────────────────────────────────
#  Top Metrics Row
# ─────────────────────────────────────────────
paper_balance = get_paper_balance(session)
trades        = session.query(Trade).all()
open_positions = session.query(Position).all()
closed_trades  = [t for t in trades if t.closed]
total_pnl      = sum(t.pnl for t in closed_trades)
win_trades     = [t for t in closed_trades if t.pnl > 0]
win_rate       = (len(win_trades) / len(closed_trades) * 100) if closed_trades else 0

# Unrealized PnL from open positions
unrealized_pnl = 0
for pos in open_positions:
    current_price = prices.get(pos.symbol, pos.entry_price) or pos.entry_price
    unrealized_pnl += (current_price - pos.entry_price) * pos.amount

col1, col2, col3, col4, col5 = st.columns(5)
with col1:
    st.metric("💰 Balance", f"${paper_balance:,.2f}", help="Available USDT balance")
with col2:
    color = "normal" if total_pnl >= 0 else "inverse"
    st.metric("📊 Realized PnL", f"${total_pnl:+,.2f}")
with col3:
    st.metric("⚡ Unrealized PnL", f"${unrealized_pnl:+,.2f}")
with col4:
    st.metric("🏆 Win Rate", f"{win_rate:.1f}%", f"{len(win_trades)}/{len(closed_trades)} trades")
with col5:
    st.metric("📂 Open Positions", len(open_positions))

st.divider()

# ─────────────────────────────────────────────
#  Tabs
# ─────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs(["📡 Live Prices", "📂 Open Positions", "📜 Trade History", "📊 Performance", "🔁 Arbitrage"])

# ── Tab 1: Live Prices ──────────────────────
with tab1:
    st.markdown("### Live Market Prices")
    price_cols = st.columns(len(SUPPORTED_PAIRS))
    for i, symbol in enumerate(SUPPORTED_PAIRS):
        price = prices.get(symbol)
        with price_cols[i]:
            if price:
                st.metric(symbol, f"${price:,.4f}")
            else:
                st.metric(symbol, "—")

    st.divider()
    st.markdown("### Price Chart")
    chart_symbol    = st.selectbox("Select asset", SUPPORTED_PAIRS, key="chart_symbol")
    chart_timeframe = st.selectbox("Timeframe", ["1m", "3m", "15m", "1h", "4h", "1d"], key="chart_tf")

    with st.spinner("Loading chart..."):
        try:
            df = fetch_ohlcv(chart_symbol, chart_timeframe, limit=100)
            fig = go.Figure(data=[go.Candlestick(
                x=df["timestamp"],
                open=df["open"], high=df["high"],
                low=df["low"],   close=df["close"],
                increasing_line_color="#3fb950",
                decreasing_line_color="#f85149",
            )])
            fig.update_layout(
                paper_bgcolor="#0d1117",
                plot_bgcolor="#161b22",
                font_color="#e6edf3",
                xaxis_rangeslider_visible=False,
                margin=dict(l=0, r=0, t=30, b=0),
                height=450,
                title=f"{chart_symbol} — {chart_timeframe}",
            )
            fig.update_xaxes(gridcolor="#30363d")
            fig.update_yaxes(gridcolor="#30363d")
            st.plotly_chart(fig, use_container_width=True)
        except Exception as e:
            st.error(f"Chart error: {e}")

# ── Tab 2: Open Positions ──────────────────
with tab2:
    st.markdown("### Open Positions")
    if not open_positions:
        st.info("No open positions. Run a strategy from the sidebar to start trading.")
    else:
        rows = []
        for pos in open_positions:
            current = prices.get(pos.symbol, pos.entry_price) or pos.entry_price
            pnl     = (current - pos.entry_price) * pos.amount
            pnl_pct = ((current - pos.entry_price) / pos.entry_price) * 100
            rows.append({
                "Symbol":        pos.symbol,
                "Strategy":      pos.strategy,
                "Entry Price":   f"${pos.entry_price:,.4f}",
                "Current Price": f"${current:,.4f}",
                "Amount":        round(pos.amount, 6),
                "Stop Loss":     f"${pos.stop_loss:,.4f}",
                "Take Profit":   f"${pos.take_profit:,.4f}",
                "PnL":           f"${pnl:+.2f}",
                "PnL %":         f"{pnl_pct:+.2f}%",
                "Opened":        pos.opened_at.strftime("%Y-%m-%d %H:%M") if pos.opened_at else "—",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ── Tab 3: Trade History ───────────────────
with tab3:
    st.markdown("### Trade History")
    if not closed_trades:
        st.info("No closed trades yet.")
    else:
        rows = []
        for t in sorted(closed_trades, key=lambda x: x.timestamp, reverse=True):
            rows.append({
                "Time":     t.timestamp.strftime("%Y-%m-%d %H:%M") if t.timestamp else "—",
                "Symbol":   t.symbol,
                "Side":     t.side.upper(),
                "Amount":   round(t.amount, 6),
                "Price":    f"${t.price:,.4f}",
                "PnL":      f"${t.pnl:+.2f}",
                "Strategy": t.strategy,
                "Mode":     t.mode.upper(),
            })
        df_trades = pd.DataFrame(rows)
        st.dataframe(df_trades, use_container_width=True, hide_index=True)

        # PnL over time
        if len(closed_trades) > 1:
            st.markdown("#### Cumulative PnL")
            sorted_trades = sorted(closed_trades, key=lambda x: x.timestamp)
            cum_pnl = []
            running = 0
            for t in sorted_trades:
                running += t.pnl
                cum_pnl.append({"Time": t.timestamp, "Cumulative PnL": running})
            fig2 = px.line(pd.DataFrame(cum_pnl), x="Time", y="Cumulative PnL",
                           color_discrete_sequence=["#1f6feb"])
            fig2.update_layout(
                paper_bgcolor="#0d1117", plot_bgcolor="#161b22",
                font_color="#e6edf3", height=300,
                margin=dict(l=0, r=0, t=20, b=0),
            )
            fig2.update_xaxes(gridcolor="#30363d")
            fig2.update_yaxes(gridcolor="#30363d")
            st.plotly_chart(fig2, use_container_width=True)

# ── Tab 4: Performance ─────────────────────
with tab4:
    st.markdown("### Strategy Performance")
    all_closed = session.query(Trade).filter_by(closed=True).all()

    if not all_closed:
        st.info("No closed trades to analyze yet.")
    else:
        # Group by strategy
        strat_stats = {}
        for t in all_closed:
            s = t.strategy
            if s not in strat_stats:
                strat_stats[s] = {"trades": 0, "wins": 0, "pnl": 0.0}
            strat_stats[s]["trades"] += 1
            strat_stats[s]["pnl"]    += t.pnl
            if t.pnl > 0:
                strat_stats[s]["wins"] += 1

        rows = []
        for strat, data in strat_stats.items():
            wr = (data["wins"] / data["trades"] * 100) if data["trades"] > 0 else 0
            rows.append({
                "Strategy":   strat,
                "Trades":     data["trades"],
                "Wins":       data["wins"],
                "Win Rate":   f"{wr:.1f}%",
                "Total PnL":  f"${data['pnl']:+.2f}",
                "Avg PnL":    f"${data['pnl']/data['trades']:+.2f}",
            })

        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # PnL by strategy bar chart
        fig3 = px.bar(
            pd.DataFrame([{"Strategy": k, "PnL": v["pnl"]} for k, v in strat_stats.items()]),
            x="Strategy", y="PnL", color="PnL",
            color_continuous_scale=["#f85149", "#3fb950"],
        )
        fig3.update_layout(
            paper_bgcolor="#0d1117", plot_bgcolor="#161b22",
            font_color="#e6edf3", height=300,
            margin=dict(l=0, r=0, t=20, b=0),
            coloraxis_showscale=False,
        )
        fig3.update_xaxes(gridcolor="#30363d")
        fig3.update_yaxes(gridcolor="#30363d")
        st.plotly_chart(fig3, use_container_width=True)

        # Daily stats
        st.markdown("### Daily Summary")
        daily = session.query(DailyStats).all()
        if daily:
            rows2 = []
            for d in sorted(daily, key=lambda x: x.date, reverse=True):
                wr = (d.wins / (d.wins + d.losses) * 100) if (d.wins + d.losses) > 0 else 0
                rows2.append({
                    "Date":          d.date,
                    "Starting Bal":  f"${d.starting_balance:,.2f}",
                    "Realized PnL":  f"${d.realized_pnl:+.2f}",
                    "Trades":        d.trades_count,
                    "Win Rate":      f"{wr:.1f}%",
                })
            st.dataframe(pd.DataFrame(rows2), use_container_width=True, hide_index=True)

# ── Tab 5: Arbitrage ──────────────────────
with tab5:
    st.markdown("### 🔁 Triangular Arbitrage Scanner")
    st.caption("Scans BTC/ETH/BNB/SOL triangles on Binance for profit opportunities after fees (0.3% total)")

    col_scan, col_size = st.columns([2, 1])
    with col_size:
        trade_size = st.number_input("Trade size (USDT)", min_value=10.0, max_value=10000.0, value=100.0, step=10.0)
    with col_scan:
        scan_clicked = st.button("🔍 Scan Now", type="primary", use_container_width=True)

    if scan_clicked:
        with st.spinner("Scanning all triangles... this takes ~5 seconds"):
            results = scan_all_triangles()

        st.markdown("#### Scan Results")
        for r in results:
            profit_pct = r.get("profit_pct", 0)
            triangle   = r.get("triangle", "")
            profit_abs = r.get("profit_abs", 0) * (trade_size / 1000)
            is_profit  = r.get("profitable", False)

            if is_profit:
                st.success(f"✅ **{triangle}** | Profit: **{profit_pct:+.4f}%** (≈ ${profit_abs:+.4f} on ${trade_size})")
            else:
                st.info(f"➖ {triangle} | {profit_pct:+.4f}%")

        # Show best opportunity
        best = results[0] if results else None
        if best and best.get("profitable"):
            st.divider()
            st.markdown("#### 🎯 Best Opportunity")
            c1, c2, c3 = st.columns(3)
            c1.metric("Triangle",   best["triangle"].split(" → ")[0] + " →...")
            c2.metric("Profit %",   f"{best['profit_pct']:+.4f}%")
            c3.metric("Est. Profit", f"${(best['profit_abs'] * trade_size / 1000):+.4f}")

            st.markdown("**Prices used:**")
            for pair, price in best["prices"].items():
                st.code(f"{pair}: {price}")

            if st.button("⚡ Execute Paper Trade", type="primary"):
                exec_result = execute_paper_arb(best, trade_size_usdt=trade_size)
                if exec_result["success"]:
                    st.success(f"✅ Paper trade executed! Profit: ${exec_result['profit']:+.4f}")
                else:
                    st.error(f"❌ Error: {exec_result.get('error')}")
        elif results:
            st.warning("⚠️ No profitable opportunities found right now. Try scanning again in a few seconds.")

    st.divider()
    st.markdown("#### Recent Arbitrage Trades")
    arb_trades = session.query(Trade).filter_by(strategy="Triangular Arbitrage").order_by(Trade.timestamp.desc()).limit(20).all()
    if not arb_trades:
        st.info("No arbitrage trades executed yet. Run a scan and execute a paper trade above.")
    else:
        rows = []
        for t in arb_trades:
            rows.append({
                "Time":    t.timestamp.strftime("%Y-%m-%d %H:%M:%S") if t.timestamp else "—",
                "Route":   t.symbol,
                "Side":    t.side.upper(),
                "PnL":     f"${t.pnl:+.4f}",
                "Mode":    t.mode.upper(),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

session.close()
