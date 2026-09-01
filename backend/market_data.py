"""Real Upstox market-data provider. Produces the SAME shapes as providers.py
(candles + option-chain rows) so the shared strategy engine is unaware of the
data source. Used only when a valid Upstox connection exists."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

import upstox_api as ux
from models import INSTRUMENTS


def _tf_unit(timeframe: int) -> Tuple[str, int]:
    # V3 supports minutes with arbitrary interval (1,3,5,15 all valid).
    return "minutes", int(timeframe)


def _parse_candles(raw: dict) -> List[dict]:
    """Upstox candle = [ts, o, h, l, c, volume, oi]; returned newest-first."""
    rows = ((raw or {}).get("data") or {}).get("candles") or []
    out = [{"ts": r[0], "o": float(r[1]), "h": float(r[2]), "l": float(r[3]),
            "c": float(r[4]), "v": float(r[5]) if len(r) > 5 else 0.0} for r in rows]
    out.sort(key=lambda x: x["ts"])          # ascending for indicators
    return out


def _normalise_ts(candles: List[dict]) -> List[dict]:
    # Trim the Upstox ISO offset to a naive local ISO the engine already uses.
    for c in candles:
        c["ts"] = c["ts"][:19]
    return candles


async def resolve_contract(db, instrument: str, expiry: Optional[str]) -> dict:
    """Resolve underlying key, chosen expiry and lot size from real Upstox
    option contracts. Never infers lot size."""
    spec = INSTRUMENTS[instrument]
    underlying_key = spec["underlying_key"]
    raw = await ux.option_contracts(db, underlying_key)
    data = raw.get("data") or []
    if not data:
        raise RuntimeError(f"No option contracts returned for {instrument}")
    expiries = sorted({row["expiry"] for row in data if row.get("expiry")})
    chosen = expiry if (expiry and expiry in expiries) else (expiries[0] if expiries else None)
    if not chosen:
        raise RuntimeError(f"No expiry available for {instrument}")
    lot = next((int(row["lot_size"]) for row in data
                if row.get("expiry") == chosen and row.get("lot_size")), spec["lot_size"])
    strikes = sorted({float(row["strike_price"]) for row in data
                      if row.get("expiry") == chosen and row.get("strike_price")})
    step = spec["strike_step"]
    if len(strikes) >= 2:
        diffs = sorted({round(strikes[i + 1] - strikes[i], 2) for i in range(len(strikes) - 1)})
        if diffs and diffs[0] > 0:
            step = diffs[0]
    return {"underlying_key": underlying_key, "expiry": chosen,
            "lot_size": lot, "strike_step": step, "expiries": expiries}


async def underlying_history(db, instrument: str, timeframe: int,
                             start: str, end: str) -> List[dict]:
    unit, interval = _tf_unit(timeframe)
    key = INSTRUMENTS[instrument]["underlying_key"]
    raw = await ux.historical_candles(db, key, unit, interval, end, start)
    return _normalise_ts(_parse_candles(raw))


async def underlying_intraday(db, instrument: str, timeframe: int) -> List[dict]:
    unit, interval = _tf_unit(timeframe)
    key = INSTRUMENTS[instrument]["underlying_key"]
    raw = await ux.intraday_candles(db, key, unit, interval)
    return _normalise_ts(_parse_candles(raw))


async def chain_snapshot(db, instrument: str, expiry: str) -> Tuple[List[dict], float]:
    """Live option chain -> rows compatible with options.select_* / pricing.
    Row: {strike, ce_price, pe_price, ce_delta, pe_delta, ce_key, pe_key}."""
    underlying_key = INSTRUMENTS[instrument]["underlying_key"]
    raw = await ux.option_chain(db, underlying_key, expiry)
    data = raw.get("data") or []
    rows = []
    spot = 0.0
    for row in data:
        strike = row.get("strike_price")
        if strike is None:
            continue
        spot = row.get("underlying_spot_price") or spot
        call = row.get("call_options") or {}
        put = row.get("put_options") or {}
        cmd = call.get("market_data") or {}
        pmd = put.get("market_data") or {}
        cg = call.get("option_greeks") or {}
        pg = put.get("option_greeks") or {}
        ce_price = cmd.get("ltp") or cmd.get("close_price") or 0.0
        pe_price = pmd.get("ltp") or pmd.get("close_price") or 0.0
        # Skip strikes missing both sides' prices (chain edges).
        if not ce_price and not pe_price:
            continue
        rows.append({
            "strike": float(strike),
            "ce_price": round(float(ce_price), 2), "pe_price": round(float(pe_price), 2),
            "ce_delta": float(cg.get("delta") or 0.0), "pe_delta": float(pg.get("delta") or 0.0),
            "ce_key": call.get("instrument_key", ""), "pe_key": put.get("instrument_key", ""),
        })
    rows.sort(key=lambda x: x["strike"])
    if not rows:
        raise RuntimeError("Empty option chain from Upstox")
    return rows, float(spot)
