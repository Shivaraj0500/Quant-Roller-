# QUANT-ROLLER PRO — Personal Intraday Options Algo Terminal

## Original Problem Statement
Personal-use automated intraday options trading terminal for ONE strategy: "Straddle ATR Band — Re-Centering Roller" via Upstox. Four-leg basket (SHORT CE, SHORT PE, LONG CE hedge, LONG PE hedge). Modes: Backtest, Paper, Live. Institutional/corporate-grade dark terminal UI. Single-strategy, minimal, deterministic, execution-safe. No features outside the master spec.

## Architecture
- **Backend (FastAPI)**: mode-independent strategy engine + explicit state machine.
  - `indicators.py` — Wilder ADX/+DI/-DI/ATR (one shared implementation).
  - `engine.py` — `StrategyEngine` decisions (ENTER/ROLL_UP/ROLL_DOWN/EXIT/HOLD); ADX qualifies ONLY initial entry; rolls driven ONLY by ATR closing breach.
  - `options.py` — Black-Scholes chain + short/hedge leg selection (ATM/OTM/DELTA/PREMIUM).
  - `providers.py` — synthetic data provider (two-phase: ranging→trend) for Backtest/Paper.
  - `backtest.py` — runner over historical candles using shared engine.
  - `session.py` — Paper/Live session manager (accelerated synthetic clock); paper simulated, live places real Upstox MARKET orders + verifies status; close-existing-before-open-new on rolls; emergency square-off.
  - `upstox_api.py` — Upstox v2 OAuth (auth-code), encrypted token storage, token metadata/expiry, historical/chain/ltp/orders/positions/funds.
  - `server.py` — /api routes.
- **Frontend (React)**: dark institutional terminal — Header (mode/status/clock/panic), Sidebar (nav + algo controls), CandleChart (SVG candles + ATR bands + markers), RightPanel (state/corridor/4-leg basket/margin), BottomTerminal (Orders/Positions/Trades/Events/Errors), StrategyConfigView, BacktestView, SettingsView (Upstox OAuth), LiveConfirmModal, BlotterView.
- **DB (Mongo)**: config doc, encrypted Upstox token.

## User Personas
- Single power user (personal quant trader) running one options-selling strategy intraday on Upstox.

## Core Requirements (static)
- ADX/+DI/-DI qualify ONLY initial entry; rolls use ATR boundary only.
- 4-leg basket, close-old-before-open-new, per-leg order tracking, exit-time square-off, no overnight.
- Backtest/Paper/Live share ONE strategy engine; only adapters differ.
- Secrets server-side only; LIVE requires explicit confirmation.

## Implemented (2026-06 / v2.4.0)
- ✅ Strategy engine + state machine (WAITING…COMPLETED/EXECUTION_ATTENTION/ERROR) — 23 pytest invariants pass.
- ✅ Config (instrument NIFTY/BANKNIFTY/SENSEX/BANKEX, timeframe, ADX/ATR params, timing, lots, short/hedge methods, execution assumptions) + validation + basket preview.
- ✅ Backtest engine + results (P&L, win rate, drawdown, roll counts, equity curve, daily P&L, basket history, event log).
- ✅ Paper trading (live-style loop, simulated fills, never real orders).
- ✅ Live execution wiring (Upstox MARKET orders + status verification) — gated behind connection + confirmation.
- ✅ Upstox OAuth connection workflow (Settings: status, connect/re-authorize/disconnect, token expiry, redirect/callback status, missing-config errors).
- ✅ Professional dark terminal UI; all 8 nav tabs; execution terminal tabs; live confirm modal.
- ✅ Full E2E tested: backend 100% (22/22 API + 23 invariants), frontend 100% of testable flows.

## Known limitations / MOCKED
- **Real Upstox data is now wired** (`market_data.py`): Backtest uses real V3 historical underlying candles; Paper/Live use real V3 intraday candles + real V2 option chain (LTP/delta) + real contract resolution (lot size/expiry/instrument keys) when connected. Synthetic provider is now only the OFFLINE fallback (used when Upstox is not connected).
- Backtest option-leg premiums are model-priced (Black-Scholes on the real underlying) because Upstox does not expose historical option greeks/chain snapshots; clearly labeled in the results note.
- Paper/Live intraday candles only populate during market hours (Upstox intraday returns today's candles). Outside market hours the session correctly stays WAITING with no data.

## Backlog (not built — outside current scope unless requested)
- P1: Real Upstox historical-candle + live-quote adapters wired into backtest/paper (replace synthetic) once user validates with a live token during market hours.
- P1: Real websocket market-data feed for live/paper (currently REST/synthetic).
- P2: Persist backtest runs / session history to Mongo.

## Config / Secrets
- backend/.env: UPSTOX_API_KEY, UPSTOX_API_SECRET, UPSTOX_REDIRECT_URI (= `<backend>/api/upstox/callback`), TOKEN_ENCRYPTION_KEY. Credentials configured; user completes OAuth via Settings → Connect Upstox.
