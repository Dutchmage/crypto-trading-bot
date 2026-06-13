import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
import os

from database import init_db, get_session, Trade, Position, DailyStats
from bot import TRADING_MODE, get_paper_balance
from arbitrage import scan_all_triangles, execute_paper_arb, start_scanner, stop_scanner, get_state, set_trade_size

# ─────────────────────────────────────────────
#  Page Config
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="ARB Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────
#  CSS — terminal style matching reference
# ─────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap');

html, body, [class*="css"], .stApp {
    background-color: #0c0c0c !important;
    color: #d4d4d4 !important;
    font-family: 'IBM Plex Sans', sans-serif !important;
}

/* Hide streamlit chrome */
#MainMenu, footer, header, .stDeployButton { display: none !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }
section[data-testid="stSidebar"] { display: none !important; }

/* ── Top nav bar ── */
.topbar {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 10px 20px;
    background: #111;
    border-bottom: 1px solid #222;
}
.topbar-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 14px;
    font-weight: 600;
    color: #f0f0f0;
    letter-spacing: 0.05em;
}
.live-badge {
    background: #e8722a;
    color: #fff;
    font-size: 10px;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 3px;
    letter-spacing: 0.08em;
    font-family: 'IBM Plex Mono', monospace;
}
.paper-badge {
    background: #2a6be8;
    color: #fff;
    font-size: 10px;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 3px;
    letter-spacing: 0.08em;
    font-family: 'IBM Plex Mono', monospace;
}
.topbar-time {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
    color: #666;
    margin-left: 4px;
}
.topbar-right {
    margin-left: auto;
    display: flex;
    gap: 16px;
    align-items: center;
}
.nav-link {
    font-size: 12px;
    color: #666;
    cursor: pointer;
    font-family: 'IBM Plex Mono', monospace;
}

/* ── Stat cards ── */
.stat-card {
    background: #141414;
    border: 1px solid #1f1f1f;
    border-radius: 4px;
    padding: 14px 16px;
}
.stat-label {
    font-size: 10px;
    font-weight: 500;
    color: #555;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-family: 'IBM Plex Mono', monospace;
    margin-bottom: 6px;
}
.stat-value {
    font-size: 22px;
    font-weight: 600;
    color: #f0f0f0;
    font-family: 'IBM Plex Mono', monospace;
    line-height: 1.1;
}
.stat-sub {
    font-size: 11px;
    color: #555;
    margin-top: 4px;
    font-family: 'IBM Plex Mono', monospace;
}
.stat-value.green { color: #4eca7e; }
.stat-value.red   { color: #e85454; }
.stat-value.orange { color: #e8722a; }

/* ── Panel ── */
.panel {
    background: #111;
    border: 1px solid #1f1f1f;
    border-radius: 4px;
    padding: 0;
    margin-bottom: 12px;
}
.panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 16px;
    border-bottom: 1px solid #1f1f1f;
}
.panel-title {
    font-size: 11px;
    font-weight: 600;
    color: #888;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-family: 'IBM Plex Mono', monospace;
}
.panel-body { padding: 14px 16px; }

/* ── Triangle rows ── */
.tri-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 0;
    border-bottom: 1px solid #1a1a1a;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 12px;
}
.tri-row:last-child { border-bottom: none; }
.tri-name { color: #aaa; flex: 1; }
.tri-pct { font-weight: 600; min-width: 70px; text-align: right; }
.tri-pct.pos { color: #4eca7e; }
.tri-pct.neg { color: #e85454; }
.tri-pct.neutral { color: #666; }
.tri-time { color: #444; font-size: 10px; margin-left: 12px; }

/* ── Log ── */
.log-container {
    background: #0c0c0c;
    border: 1px solid #1a1a1a;
    border-radius: 3px;
    padding: 10px 12px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
    color: #666;
    max-height: 280px;
    overflow-y: auto;
    line-height: 1.8;
}
.log-line.profit { color: #4eca7e; }
.log-line.exec   { color: #e8722a; }
.log-line.error  { color: #e85454; }
.log-line.info   { color: #555; }
.log-line.start  { color: #4e8eca; }

/* ── Trade table ── */
.trade-table {
    width: 100%;
    border-collapse: collapse;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 11px;
}
.trade-table th {
    text-align: left;
    color: #444;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 6px 8px;
    border-bottom: 1px solid #1a1a1a;
    font-weight: 500;
}
.trade-table td {
    padding: 7px 8px;
    color: #999;
    border-bottom: 1px solid #161616;
}
.trade-table tr:last-child td { border-bottom: none; }
.trade-table td.symbol { color: #d4d4d4; font-weight: 500; }
.trade-table td.profit-pos { color: #4eca7e; }
.trade-table td.profit-neg { color: #e85454; }

/* ── Scanner button ── */
.stButton > button {
    background: #1a1a1a !important;
    color: #d4d4d4 !important;
    border: 1px solid #2a2a2a !important;
    border-radius: 3px !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 12px !important;
    padding: 6px 16px !important;
    transition: all 0.15s !important;
}
.stButton > button:hover {
    background: #222 !important;
    border-color: #e8722a !important;
    color: #e8722a !important;
}
.stButton > button[kind="primary"] {
    background: #e8722a !important;
    color: #fff !important;
    border-color: #e8722a !important;
}
.stButton > button[kind="primary"]:hover {
    background: #d4651f !important;
}

/* ── Number input ── */
.stNumberInput input {
    background: #141414 !important;
    border: 1px solid #222 !important;
    color: #d4d4d4 !important;
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 12px !important;
    border-radius: 3px !important;
}

/* ── Plotly chart bg ── */
.js-plotly-plot { border-radius: 4px; }

/* ── Divider ── */
hr { border-color: #1a1a1a !important; }

/* Override streamlit metric */
div[data-testid="metric-container"] {
    background: #141414;
    border: 1px solid #1f1f1f;
    border-radius: 4px;
    padding: 12px 16px;
}
div[data-testid="stMetricLabel"] p {
    font-size: 10px !important;
    color: #555 !important;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-family: 'IBM Plex Mono', monospace !important;
}
div[data-testid="stMetricValue"] {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 20px !important;
    color: #f0f0f0 !important;
}
div[data-testid="stMetricDelta"] {
    font-family: 'IBM Plex Mono', monospace !important;
    font-size: 11px !important;
}
</style>
""", unsafe_allow_html=True)

init_db()
session = get_session()
state   = get_state()
now     = datetime.utcnow()

# ─────────────────────────────────────────────
#  Top nav bar
# ─────────────────────────────────────────────
mode_badge = f'<span class="live-badge">{"LIVE" if TRADING_MODE == "live" else "PAPER"}</span>'
st.markdown(f"""
<div class="topbar">
    <span class="topbar-title">⚡ ARB TERMINAL</span>
    {mode_badge}
    <span class="topbar-time">{now.strftime("%H:%M")} UTC</span>
    <div class="topbar-right">
        <span class="nav-link">Arbitrage</span>
        <span class="nav-link">History</span>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown("<div style='padding: 16px 20px 0'>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  Top stat row
# ─────────────────────────────────────────────
arb_trades  = session.query(Trade).filter_by(strategy="Triangular Arbitrage", closed=True).all()
total_pnl   = sum(t.pnl for t in arb_trades)
wins        = sum(1 for t in arb_trades if t.pnl > 0)
win_rate    = (wins / len(arb_trades) * 100) if arb_trades else 0
balance     = get_paper_balance(session)

pnl_color   = "green" if total_pnl >= 0 else "red"
scan_status = "🟢 SCANNING" if state["running"] else "🔴 STOPPED"

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.markdown(f"""<div class="stat-card">
        <div class="stat-label">Balance</div>
        <div class="stat-value">${balance:,.2f}</div>
        <div class="stat-sub">USDT available</div>
    </div>""", unsafe_allow_html=True)
with c2:
    st.markdown(f"""<div class="stat-card">
        <div class="stat-label">Total PnL</div>
        <div class="stat-value {pnl_color}">${total_pnl:+.4f}</div>
        <div class="stat-sub">realized</div>
    </div>""", unsafe_allow_html=True)
with c3:
    st.markdown(f"""<div class="stat-card">
        <div class="stat-label">Trades</div>
        <div class="stat-value">{state['trades_executed']}</div>
        <div class="stat-sub">executed</div>
    </div>""", unsafe_allow_html=True)
with c4:
    st.markdown(f"""<div class="stat-card">
        <div class="stat-label">Win Rate</div>
        <div class="stat-value {'green' if win_rate >= 50 else 'red'}">{win_rate:.1f}%</div>
        <div class="stat-sub">{wins} wins</div>
    </div>""", unsafe_allow_html=True)
with c5:
    st.markdown(f"""<div class="stat-card">
        <div class="stat-label">Scanner</div>
        <div class="stat-value orange" style="font-size:14px;padding-top:4px">{scan_status}</div>
        <div class="stat-sub">10s interval</div>
    </div>""", unsafe_allow_html=True)

st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  Main layout: left (scanner) | right (log)
# ─────────────────────────────────────────────
col_left, col_right = st.columns([3, 2])

with col_left:
    # ── Scanner controls ──
    st.markdown('<div class="panel-header" style="background:#111;border:1px solid #1f1f1f;border-radius:4px 4px 0 0;margin-bottom:0">'
                '<span class="panel-title">🔁 Triangle Scanner</span></div>', unsafe_allow_html=True)

    ctrl1, ctrl2, ctrl3 = st.columns([2, 2, 2])
    with ctrl1:
        trade_size = st.number_input("Trade size (USDT)", min_value=10.0, max_value=10000.0,
                                      value=float(state["trade_size"]), step=10.0, label_visibility="collapsed")
        set_trade_size(trade_size)
        st.caption(f"Trade size: ${trade_size:.0f} USDT")
    with ctrl2:
        if state["running"]:
            if st.button("⏹ Stop Scanner", use_container_width=True):
                stop_scanner()
                st.rerun()
        else:
            if st.button("▶ Start Scanner", use_container_width=True, type="primary"):
                start_scanner()
                st.rerun()
    with ctrl3:
        if st.button("🔍 Scan Once", use_container_width=True):
            with st.spinner(""):
                results = scan_all_triangles()
            st.rerun()

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # ── Last scan results ──
    last_scan = state["last_scan"]
    if not last_scan:
        st.markdown("""<div class="panel-body" style="background:#111;border:1px solid #1f1f1f;border-radius:4px">
            <div style="color:#444;font-family:'IBM Plex Mono',monospace;font-size:12px;padding:20px 0;text-align:center">
            No scan data yet — start the scanner or click Scan Once
            </div></div>""", unsafe_allow_html=True)
    else:
        rows_html = ""
        for r in last_scan:
            pct = r.get("profit_pct", 0)
            tri = r.get("triangle", "").replace(" → ", " › ")
            ts  = r.get("timestamp", "")
            est = abs(pct / 100) * trade_size
            pct_class = "pos" if pct > 0.1 else ("neutral" if pct > 0 else "neg")
            indicator = "✦" if pct > 0.1 else "·"
            rows_html += f"""<div class="tri-row">
                <span style="color:#e8722a;margin-right:8px">{indicator}</span>
                <span class="tri-name">{tri}</span>
                <span class="tri-pct {pct_class}">{pct:+.4f}%</span>
                <span style="color:#4eca7e;font-family:'IBM Plex Mono',monospace;font-size:11px;margin-left:12px">
                    {'≈ $'+f'{est:.4f}' if pct > 0.1 else ''}</span>
                <span class="tri-time">{ts}</span>
            </div>"""

        st.markdown(f"""<div style="background:#111;border:1px solid #1f1f1f;border-radius:4px;padding:4px 16px">
            {rows_html}
        </div>""", unsafe_allow_html=True)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # ── PnL Chart ──
    closing_trades = [t for t in arb_trades if t.pnl != 0]
    if len(closing_trades) > 1:
        st.markdown('<div class="panel-title" style="margin-bottom:8px">CUMULATIVE PnL</div>', unsafe_allow_html=True)
        sorted_t = sorted(closing_trades, key=lambda x: x.timestamp)
        running, times, vals = 0, [], []
        for t in sorted_t:
            running += t.pnl
            times.append(t.timestamp)
            vals.append(running)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=times, y=vals, mode="lines",
            line=dict(color="#e8722a", width=2),
            fill="tozeroy",
            fillcolor="rgba(232,114,42,0.08)",
        ))
        fig.update_layout(
            paper_bgcolor="#111", plot_bgcolor="#111",
            font=dict(color="#555", family="IBM Plex Mono", size=10),
            margin=dict(l=10, r=10, t=10, b=10),
            height=160,
            xaxis=dict(gridcolor="#1a1a1a", showline=False, zeroline=False),
            yaxis=dict(gridcolor="#1a1a1a", showline=False, zeroline=False),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

with col_right:
    # ── Activity log ──
    st.markdown('<div class="panel-header" style="background:#111;border:1px solid #1f1f1f;border-radius:4px 4px 0 0">'
                '<span class="panel-title">📋 Activity Log</span>'
                f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:10px;color:#444">'
                f'last {min(len(state["scan_log"]),20)} events</span></div>', unsafe_allow_html=True)

    log = list(reversed(state["scan_log"][-20:]))
    if not log:
        st.markdown("""<div class="log-container" style="border-radius:0 0 4px 4px">
            <span style="color:#333">— waiting for scanner activity —</span>
        </div>""", unsafe_allow_html=True)
    else:
        lines_html = ""
        for line in log:
            if "✅" in line or "Profit" in line:
                cls = "profit"
            elif "⚡" in line or "Executed" in line:
                cls = "exec"
            elif "❌" in line or "⚠️" in line:
                cls = "error"
            elif "🟢" in line or "🔴" in line:
                cls = "start"
            else:
                cls = "info"
            lines_html += f'<div class="log-line {cls}">{line}</div>'
        st.markdown(f'<div class="log-container" style="border:1px solid #1a1a1a;border-top:none;border-radius:0 0 4px 4px">{lines_html}</div>',
                    unsafe_allow_html=True)

    st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)

    # ── Quick stats panel ──
    st.markdown('<div class="panel-title" style="margin-bottom:8px">TRIANGLE PERFORMANCE</div>', unsafe_allow_html=True)
    if arb_trades:
        # group by symbol (first leg = triangle identifier)
        from collections import defaultdict
        tri_stats = defaultdict(lambda: {"trades": 0, "pnl": 0.0})
        for t in arb_trades:
            tri_stats[t.symbol]["trades"] += 1
            tri_stats[t.symbol]["pnl"]    += t.pnl

        rows_html = ""
        for sym, data in sorted(tri_stats.items(), key=lambda x: x[1]["pnl"], reverse=True):
            color = "#4eca7e" if data["pnl"] >= 0 else "#e85454"
            rows_html += f"""<div class="tri-row">
                <span class="tri-name">{sym}</span>
                <span style="color:#555;font-family:'IBM Plex Mono',monospace;font-size:11px">{data['trades']}x</span>
                <span class="tri-pct" style="color:{color}">${data['pnl']:+.4f}</span>
            </div>"""
        st.markdown(f'<div style="background:#111;border:1px solid #1f1f1f;border-radius:4px;padding:4px 16px">{rows_html}</div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div style="color:#333;font-family:\'IBM Plex Mono\',monospace;font-size:11px;padding:12px 0">No trades yet</div>',
                    unsafe_allow_html=True)

# ─────────────────────────────────────────────
#  Trade History Table
# ─────────────────────────────────────────────
st.markdown("<div style='height:14px'></div>", unsafe_allow_html=True)
st.markdown('<div class="panel-header" style="background:#111;border:1px solid #1f1f1f;border-radius:4px 4px 0 0">'
            '<span class="panel-title">📜 Trade History</span>'
            f'<span style="font-family:\'IBM Plex Mono\',monospace;font-size:10px;color:#444">'
            f'{len(closing_trades)} closed trades</span></div>', unsafe_allow_html=True)

recent = session.query(Trade).filter_by(strategy="Triangular Arbitrage") \
    .order_by(Trade.timestamp.desc()).limit(50).all()

if not recent:
    st.markdown("""<div style="background:#111;border:1px solid #1f1f1f;border-top:none;border-radius:0 0 4px 4px;
        padding:24px;text-align:center;font-family:'IBM Plex Mono',monospace;font-size:12px;color:#333">
        No trades recorded yet — start the scanner to begin
    </div>""", unsafe_allow_html=True)
else:
    rows_html = "".join([
        f"""<tr>
            <td style="color:#444">{t.timestamp.strftime('%H:%M:%S') if t.timestamp else '—'}</td>
            <td class="symbol">{t.symbol}</td>
            <td style="color:{'#4eca7e' if t.side=='buy' else '#e85454'}">{t.side.upper()}</td>
            <td>{t.amount:.6f}</td>
            <td>${t.price:,.6f}</td>
            <td class="{'profit-pos' if t.pnl > 0 else 'profit-neg' if t.pnl < 0 else ''}">${t.pnl:+.6f}</td>
            <td style="color:#333">{t.mode.upper()}</td>
        </tr>"""
        for t in recent
    ])
    st.markdown(f"""<div style="background:#111;border:1px solid #1f1f1f;border-top:none;
        border-radius:0 0 4px 4px;padding:8px 16px;overflow-x:auto">
        <table class="trade-table">
            <thead><tr>
                <th>TIME</th><th>PAIR</th><th>SIDE</th>
                <th>AMOUNT</th><th>PRICE</th><th>PnL</th><th>MODE</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
    </div>""", unsafe_allow_html=True)

st.markdown("</div>", unsafe_allow_html=True)

# Auto-refresh while scanner running
if state["running"]:
    st.markdown('<meta http-equiv="refresh" content="12">', unsafe_allow_html=True)

session.close()
