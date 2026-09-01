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
- Backtest & Paper run on a **synthetic data provider** + Black-Scholes chain (real Upstox historical/live data requires interactive OAuth + market hours). Clearly labeled in UI.
- Paper/Live intraday tick feed uses an accelerated **synthetic clock** for demonstrability; real Upstox order execution path is implemented but not auto-testable (needs live OAuth).

## Backlog (not built — outside current scope unless requested)
- P1: Real Upstox historical-candle + live-quote adapters wired into backtest/paper (replace synthetic) once user validates with a live token during market hours.
- P1: Real websocket market-data feed for live/paper (currently REST/synthetic).
- P2: Persist backtest runs / session history to Mongo.

## Config / Secrets
- backend/.env: UPSTOX_API_KEY, UPSTOX_API_SECRET, UPSTOX_REDIRECT_URI (= `<backend>/api/upstox/callback`), TOKEN_ENCRYPTION_KEY. Credentials configured; user completes OAuth via Settings → Connect Upstox.
