# 🚀 Crypto Trading Bot Dashboard

A standalone crypto trading dashboard built with Streamlit, connected to Binance via CCXT. Supports paper trading and live trading with multiple pluggable strategies.

## Features
- 📡 Live prices for BTC, ETH, BNB, SOL, ADA
- 📊 Candlestick charts
- 📂 Open positions with real-time P&L
- 📜 Trade history & cumulative P&L chart
- 📈 Strategy performance comparison
- ⛔ Risk management: stop-loss, take-profit, position sizing, daily loss limit
- 🔄 Paper → Live trading switch via environment variable

## Strategies Included
1. **RSI** — Buy oversold (< 30), sell overbought (> 70)
2. **MA Crossover** — Fast/slow moving average crossover
3. **Bollinger Bands** — Buy at lower band, sell at upper band

## Deployment on Render

### 1. Push to GitHub
```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/Dutchmage/crypto-trading-bot.git
git push -u origin main
```

### 2. Create Render Web Service
1. Go to render.com → New → Web Service
2. Connect your GitHub repo
3. Render auto-detects `render.yaml`

### 3. Set Environment Variables on Render
| Variable | Value |
|---|---|
| `BINANCE_API_KEY` | Your Binance Testnet API key |
| `BINANCE_SECRET_KEY` | Your Binance Testnet Secret key |
| `TRADING_MODE` | `paper` (change to `live` when ready) |
| `PAPER_BALANCE` | `10000` (starting fake USDT) |
| `MAX_DAILY_LOSS_PCT` | `5.0` (max % loss per day before bot stops) |

## Going Live
1. Get real Binance API keys (with trading permissions)
2. Change `TRADING_MODE` to `live` in Render environment variables
3. Upgrade Render plan to avoid spin-down
