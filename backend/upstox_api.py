"""Upstox API v2 adapter. All secrets stay server-side; tokens encrypted at rest.
Access tokens expire ~03:30 IST daily; a 401 requires a fresh OAuth login."""
from __future__ import annotations

import os
import secrets
import urllib.parse
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx
from cryptography.fernet import Fernet

API = "https://api.upstox.com/v2"
V3 = "https://api.upstox.com/v3"
HFT = "https://api-hft.upstox.com/v2"

_IST = timezone(timedelta(hours=5, minutes=30))

_fernet_cache = None


def _fernet():
    global _fernet_cache
    if _fernet_cache is None:
        _fernet_cache = Fernet(os.environ["TOKEN_ENCRYPTION_KEY"].encode())
    return _fernet_cache


def creds_configured() -> bool:
    return bool(os.environ.get("UPSTOX_API_KEY") and os.environ.get("UPSTOX_API_SECRET")
               and os.environ.get("UPSTOX_REDIRECT_URI"))


async def save_token(db, token: str):
    now = datetime.now(timezone.utc)
    ist = now.astimezone(_IST)
    # Upstox access tokens expire daily at 03:30 IST (next occurrence).
    expiry_ist = ist.replace(hour=3, minute=30, second=0, microsecond=0)
    if ist >= expiry_ist:
        expiry_ist = expiry_ist + timedelta(days=1)
    await db.tokens.update_one({"user": "me"}, {"$set": {
        "user": "me",
        "token": _fernet().encrypt(token.encode()).decode(),
        "issued_at": now.isoformat(),
        "expiry_at": expiry_ist.astimezone(timezone.utc).isoformat(),
    }}, upsert=True)


async def token_meta(db) -> dict:
    row = await db.tokens.find_one({"user": "me"})
    if not row:
        return {"issued_at": None, "expiry_at": None, "expired": True}
    expiry = row.get("expiry_at")
    expired = False
    if expiry:
        try:
            expired = datetime.now(timezone.utc) >= datetime.fromisoformat(expiry)
        except Exception:
            expired = False
    return {"issued_at": row.get("issued_at"), "expiry_at": expiry, "expired": expired}


def config_status() -> dict:
    return {
        "api_key_present": bool(os.environ.get("UPSTOX_API_KEY")),
        "api_secret_present": bool(os.environ.get("UPSTOX_API_SECRET")),
        "redirect_present": bool(os.environ.get("UPSTOX_REDIRECT_URI")),
        "redirect_uri": os.environ.get("UPSTOX_REDIRECT_URI", ""),
    }


async def get_token(db) -> Optional[str]:
    row = await db.tokens.find_one({"user": "me"})
    if not row:
        return None
    try:
        return _fernet().decrypt(row["token"].encode()).decode()
    except Exception:
        return None


async def clear_token(db):
    await db.tokens.delete_one({"user": "me"})


async def is_connected(db) -> bool:
    return (await get_token(db)) is not None


def login_url(db_state_saver=None) -> tuple[str, str]:
    state = secrets.token_urlsafe(24)
    q = urllib.parse.urlencode({
        "client_id": os.environ["UPSTOX_API_KEY"],
        "redirect_uri": os.environ["UPSTOX_REDIRECT_URI"],
        "response_type": "code",
        "state": state,
    })
    return f"{API}/login/authorization/dialog?{q}", state


async def exchange_code(code: str) -> str:
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{API}/login/authorization/token", data={
            "code": code,
            "client_id": os.environ["UPSTOX_API_KEY"],
            "client_secret": os.environ["UPSTOX_API_SECRET"],
            "redirect_uri": os.environ["UPSTOX_REDIRECT_URI"],
            "grant_type": "authorization_code",
        }, headers={"Accept": "application/json"})
    r.raise_for_status()
    return r.json()["access_token"]


async def _get(db, path: str, params=None):
    token = await get_token(db)
    if not token:
        raise PermissionError("Upstox not connected")
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(API + path, params=params,
                        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    if r.status_code == 401:
        raise PermissionError("Upstox token expired; reconnect")
    r.raise_for_status()
    return r.json()


async def option_contracts(db, underlying_key: str, expiry: Optional[str] = None):
    p = {"instrument_key": underlying_key}
    if expiry:
        p["expiry_date"] = expiry
    return await _get(db, "/option/contract", p)


async def option_chain(db, underlying_key: str, expiry: str):
    return await _get(db, "/option/chain",
                      {"instrument_key": underlying_key, "expiry_date": expiry})


async def ltp(db, instrument_keys: str):
    return await _get(db, "/market-quote/ltp", {"instrument_key": instrument_keys})


async def _get_v3(db, path: str, params=None):
    token = await get_token(db)
    if not token:
        raise PermissionError("Upstox not connected")
    async with httpx.AsyncClient(timeout=25) as c:
        r = await c.get(V3 + path, params=params,
                        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"})
    if r.status_code == 401:
        raise PermissionError("Upstox token expired; reconnect")
    r.raise_for_status()
    return r.json()


async def historical_candles(db, instrument_key: str, unit: str, interval: int,
                             to_date: str, from_date: Optional[str] = None):
    """V3 historical candles. unit=minutes|days|weeks; interval e.g. 1,3,5,15."""
    key = urllib.parse.quote(instrument_key, safe="")
    path = f"/historical-candle/{key}/{unit}/{interval}/{to_date}"
    if from_date:
        path += f"/{from_date}"
    return await _get_v3(db, path)


async def intraday_candles(db, instrument_key: str, unit: str, interval: int):
    """V3 intraday (current day) candles. unit=minutes|days; interval e.g. 1,3,5,15."""
    key = urllib.parse.quote(instrument_key, safe="")
    return await _get_v3(db, f"/historical-candle/intraday/{key}/{unit}/{interval}")


async def positions(db):
    return await _get(db, "/portfolio/short-term-positions")


async def funds(db):
    return await _get(db, "/user/get-funds-and-margin", {"segment": "SEC"})


async def place_market_order(db, instrument_token: str, quantity: int,
                             transaction_type: str):
    token = await get_token(db)
    if not token:
        raise PermissionError("Upstox not connected")
    body = {"instrument_token": instrument_token, "quantity": quantity,
            "transaction_type": transaction_type, "product": "I", "validity": "DAY",
            "price": 0, "order_type": "MARKET", "disclosed_quantity": 0,
            "trigger_price": 0, "is_amo": False, "market_protection": -1}
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(f"{HFT}/order/place", json=body,
                         headers={"Authorization": f"Bearer {token}",
                                  "Content-Type": "application/json", "Accept": "application/json"})
    r.raise_for_status()
    return r.json()


async def order_status(db, order_id: str):
    return await _get(db, "/order/history", {"order_id": order_id})
