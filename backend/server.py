from fastapi import FastAPI, APIRouter, HTTPException, Body
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from models import (StrategyConfig, INSTRUMENTS, SUPPORTED_TIMEFRAMES,
                    ShortLegMethod, HedgeMethod, CenterSource)
from indicators import compute_indicators
from options import select_short_legs, select_hedge_legs
from providers import synthetic_candles, synthetic_range, synthetic_chain_at
from backtest import run_backtest
from session import SessionManager
import upstox_api as ux

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI(title="QUANT-ROLLER PRO API")
api_router = APIRouter(prefix="/api")

SESSION = SessionManager()
SESSION.db = db
APP_VERSION = "2.4.0"

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("quant-roller")


# --------------------------------------------------------------------------- #
async def load_config() -> StrategyConfig:
    doc = await db.config.find_one({"key": "active"})
    if doc and "config" in doc:
        return StrategyConfig(**doc["config"])
    return StrategyConfig()


def _validate(cfg: StrategyConfig) -> list:
    errs = []
    if cfg.instrument not in INSTRUMENTS:
        errs.append("Invalid instrument")
    if cfg.timeframe not in SUPPORTED_TIMEFRAMES:
        errs.append("Unsupported timeframe")
    if cfg.lots < 1:
        errs.append("Lots must be >= 1")
    if cfg.adx_period < 2 or cfg.atr_period < 2:
        errs.append("Indicator periods too small")
    if cfg.atr_multiplier <= 0:
        errs.append("ATR multiplier must be > 0")
    try:
        eh, em = map(int, cfg.entry_time.split(":"))
        xh, xm = map(int, cfg.exit_time.split(":"))
        if (eh * 60 + em) >= (xh * 60 + xm):
            errs.append("Entry time must be before exit time")
    except Exception:
        errs.append("Invalid entry/exit time format (HH:MM)")
    return errs


# --------------------------------------------------------------------------- #
@api_router.get("/")
async def root():
    return {"app": "QUANT-ROLLER PRO", "version": APP_VERSION}


@api_router.get("/meta")
async def meta():
    return {
        "version": APP_VERSION,
        "instruments": {k: {"name": v["name"], "lot_size": v["lot_size"],
                            "strike_step": v["strike_step"]} for k, v in INSTRUMENTS.items()},
        "timeframes": SUPPORTED_TIMEFRAMES,
        "short_methods": [m.value for m in ShortLegMethod],
        "hedge_methods": [m.value for m in HedgeMethod],
        "center_sources": [m.value for m in CenterSource],
    }


@api_router.get("/config")
async def get_config():
    cfg = await load_config()
    return cfg.model_dump()


@api_router.put("/config")
async def put_config(cfg: StrategyConfig):
    errs = _validate(cfg)
    if errs:
        raise HTTPException(400, {"errors": errs})
    await db.config.update_one({"key": "active"},
                               {"$set": {"key": "active", "config": cfg.model_dump(),
                                         "updated_at": datetime.now().isoformat()}},
                               upsert=True)
    return {"ok": True, "config": cfg.model_dump()}


@api_router.post("/config/validate")
async def validate_config(cfg: StrategyConfig):
    errs = _validate(cfg)
    return {"valid": len(errs) == 0, "errors": errs}


# ----------------------------- basket preview ------------------------------ #
@api_router.post("/basket/preview")
async def basket_preview(cfg: StrategyConfig):
    errs = _validate(cfg)
    if errs:
        raise HTTPException(400, {"errors": errs})
    import math
    spec = INSTRUMENTS[cfg.instrument]
    now = datetime.now()
    connected = await ux.is_connected(db)

    if connected:
        try:
            import market_data as md
            meta = await md.resolve_contract(db, cfg.instrument, cfg.expiry)
            expiry = meta["expiry"]
            lot_size = meta["lot_size"]
            chain, spot = await md.chain_snapshot(db, cfg.instrument, expiry)
            # ATR from real candles: intraday first, else recent history.
            rc = await md.underlying_intraday(db, cfg.instrument, cfg.timeframe)
            if len([c for c in rc]) < cfg.atr_period + 2:
                frm = (now - timedelta(days=7)).strftime("%Y-%m-%d")
                rc = await md.underlying_history(db, cfg.instrument, cfg.timeframe,
                                                 frm, now.strftime("%Y-%m-%d"))
            if rc:
                ind = compute_indicators([c["h"] for c in rc], [c["l"] for c in rc],
                                         [c["c"] for c in rc], cfg.adx_period, cfg.atr_period)
                atr = next((float(ind["atr"][k]) for k in range(len(rc) - 1, -1, -1)
                            if not math.isnan(ind["atr"][k])), spot * 0.006)
            else:
                atr = spot * 0.006
            source = "UPSTOX"
            note = "Live Upstox option chain — strikes, premiums (LTP) and deltas are real."
        except Exception as e:
            raise HTTPException(400, f"Upstox chain error: {e}")
    else:
        lot_size = spec["lot_size"]
        day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        candles = synthetic_candles(cfg.instrument, day, cfg.timeframe, seed=42)
        ind = compute_indicators([c["h"] for c in candles], [c["l"] for c in candles],
                                 [c["c"] for c in candles], cfg.adx_period, cfg.atr_period)
        atr = next((float(ind["atr"][k]) for k in range(len(candles) - 1, -1, -1)
                    if not math.isnan(ind["atr"][k])), spec["ref_price"] * 0.006)
        spot = SESSION.spot if (SESSION.running and SESSION.data_source == "SYNTHETIC") else candles[-1]["c"]
        chain, expiry = synthetic_chain_at(cfg.instrument, spot, now, cfg.expiry)
        source = "SYNTHETIC"
        note = "Synthetic Black-Scholes preview (Upstox not connected). Real strikes/premiums resolve from the live Upstox chain when connected."

    center = spot
    short_ce, short_pe = select_short_legs(chain, center, cfg, expiry, lot_size)
    legs = [short_ce, short_pe]
    if cfg.hedge_enabled:
        h_ce, h_pe = select_hedge_legs(chain, short_ce, short_pe, cfg, expiry, lot_size)
        legs += [h_ce, h_pe]
    upper = center + atr * cfg.atr_multiplier
    lower = center - atr * cfg.atr_multiplier
    est_premium = sum((1 if l.side.value == "SELL" else -1) * l.entry_price * l.quantity for l in legs)
    return {
        "instrument": cfg.instrument, "expiry": expiry, "spot": round(spot, 2),
        "center": round(center, 2), "atr": round(atr, 2),
        "upper": round(upper, 2), "lower": round(lower, 2),
        "lot_size": lot_size, "lots": cfg.lots,
        "total_qty": lot_size * cfg.lots,
        "net_premium": round(est_premium, 2),
        "data_source": source, "note": note,
        "legs": [{
            "role": l.role.value, "type": l.option_type.value, "side": l.side.value,
            "strike": l.strike, "expiry": l.expiry, "qty": l.quantity, "lots": l.lots,
            "premium": l.entry_price, "delta": l.delta, "method": l.method, "metric": l.metric,
        } for l in legs],
    }


# ------------------------------- backtest ---------------------------------- #
@api_router.post("/backtest/run")
async def backtest_run(payload: dict = Body(...)):
    cfg = StrategyConfig(**payload.get("config", {}))
    errs = _validate(cfg)
    if errs:
        raise HTTPException(400, {"errors": errs})
    start = payload.get("start")
    end = payload.get("end")
    if not start or not end:
        end_dt = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        start_dt = end_dt - timedelta(days=14)
        start, end = start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d")

    connected = await ux.is_connected(db)
    if connected:
        try:
            import market_data as md
            candles = await md.underlying_history(db, cfg.instrument, cfg.timeframe, start, end)
            source = "UPSTOX"
            note = "Real Upstox historical underlying candles. Option legs are model-priced (Black-Scholes) as Upstox does not expose historical option greeks/chain."
        except Exception as e:
            raise HTTPException(400, f"Upstox historical data error: {e}")
        if not candles:
            raise HTTPException(400, "Upstox returned no historical candles for this range (retention/non-trading days).")
    else:
        candles = synthetic_range(cfg.instrument, start, end, cfg.timeframe)
        source = "SYNTHETIC"
        note = "Synthetic historical data (Upstox not connected). Connect Upstox for real historical candles."
        if not candles:
            raise HTTPException(400, "No candles in selected range")

    result = run_backtest(cfg, candles, cfg.instrument)
    result["meta"] = {"start": start, "end": end, "instrument": cfg.instrument,
                      "timeframe": cfg.timeframe, "data_source": source, "note": note}
    return result


# ------------------------------- session ----------------------------------- #
@api_router.post("/session/start")
async def session_start(payload: dict = Body(...)):
    mode = payload.get("mode", "PAPER")
    cfg = StrategyConfig(**payload.get("config", {}))
    errs = _validate(cfg)
    if errs:
        raise HTTPException(400, {"errors": errs})
    if mode == "LIVE":
        if not await ux.is_connected(db):
            raise HTTPException(400, "Connect Upstox before starting a LIVE session")
        if not payload.get("confirmed"):
            raise HTTPException(400, "LIVE session requires explicit confirmation")
    try:
        await SESSION.start(mode, cfg)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    return {"ok": True, "mode": mode}


@api_router.post("/session/stop")
async def session_stop():
    await SESSION.stop()
    return {"ok": True}


@api_router.post("/session/emergency")
async def session_emergency():
    await SESSION.emergency_squareoff()
    return {"ok": True}


@api_router.get("/session/status")
async def session_status():
    return SESSION.status()


# ------------------------------- upstox ------------------------------------ #
@api_router.get("/upstox/status")
async def upstox_status():
    connected = await ux.is_connected(db)
    cfg = ux.config_status()
    meta = await ux.token_meta(db)
    return {
        "configured": ux.creds_configured(),
        "connected": connected and not meta.get("expired", False),
        "has_token": connected,
        "token_expired": meta.get("expired", True) if connected else False,
        "issued_at": meta.get("issued_at"),
        "expiry_at": meta.get("expiry_at"),
        **cfg,
    }


@api_router.get("/upstox/login")
async def upstox_login():
    if not ux.creds_configured():
        raise HTTPException(400, "Upstox API credentials not configured on server")
    url, state = ux.login_url()
    await db.oauth_state.insert_one({"state": state, "created": datetime.now().isoformat()})
    return {"url": url}


@api_router.get("/upstox/callback", response_class=HTMLResponse)
async def upstox_callback(code: str = "", state: str = ""):
    row = await db.oauth_state.find_one_and_delete({"state": state})
    if not row:
        return HTMLResponse("<h3>Invalid OAuth state. Close and retry.</h3>", status_code=400)
    try:
        token = await ux.exchange_code(code)
        await ux.save_token(db, token)
        return HTMLResponse("<h3>Upstox connected. You can close this tab.</h3>"
                            "<script>setTimeout(()=>window.close(),1200)</script>")
    except Exception as e:
        return HTMLResponse(f"<h3>Token exchange failed: {e}</h3>", status_code=400)


@api_router.post("/upstox/disconnect")
async def upstox_disconnect():
    await ux.clear_token(db)
    return {"ok": True}


@api_router.get("/upstox/funds")
async def upstox_funds():
    if not await ux.is_connected(db):
        return {"connected": False, "data": None}
    try:
        return {"connected": True, "data": await ux.funds(db)}
    except Exception as e:
        raise HTTPException(400, str(e))


@api_router.get("/upstox/positions")
async def upstox_positions():
    if not await ux.is_connected(db):
        return {"connected": False, "data": None}
    try:
        return {"connected": True, "data": await ux.positions(db)}
    except Exception as e:
        raise HTTPException(400, str(e))


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
