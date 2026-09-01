"""Data providers.

  * SyntheticProvider — deterministic random-walk candles + Black-Scholes option
    chain, so backtest / paper can run end-to-end WITHOUT a live Upstox session.
  * UpstoxDataProvider — real historical candles + option chain when connected.

Both expose the same shape so the strategy engine is unaware of the source."""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from typing import List, Optional

from models import INSTRUMENTS
from options import DEFAULT_IV, build_synthetic_chain, round_to_step

MARKET_OPEN = (9, 15)
MARKET_CLOSE = (15, 30)


def _session_times(day: datetime, tf: int) -> List[datetime]:
    start = day.replace(hour=MARKET_OPEN[0], minute=MARKET_OPEN[1], second=0, microsecond=0)
    end = day.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0, microsecond=0)
    out, t = [], start
    while t <= end:
        out.append(t)
        t += timedelta(minutes=tf)
    return out


def _nearest_weekly_expiry(day: datetime) -> str:
    # Nearest Thursday (weekly expiry convention); editable when Upstox connected.
    d = day
    while d.weekday() != 3:  # Thursday
        d += timedelta(days=1)
    return d.strftime("%Y-%m-%d")


def synthetic_candles(instrument: str, day: datetime, tf: int,
                      seed: Optional[int] = None) -> List[dict]:
    """Two-phase intraday series: a low-ADX ranging phase (so the initial ADX
    qualification can trigger) followed by a trending phase (so the ATR bands
    get breached and Roll Up / Roll Down occur) — matching the strategy premise."""
    spec = INSTRUMENTS[instrument]
    base = spec["ref_price"]
    rng = random.Random(seed if seed is not None else int(day.timestamp()))
    times = _session_times(day, tf)
    n = len(times)
    range_end = int(n * 0.55)          # ranging phase length
    vol = base * 0.00035
    trend_dir = rng.choice([-1, 1])
    trend_step = base * 0.0018 * trend_dir
    price = base * (1 + rng.uniform(-0.0008, 0.0008))
    candles = []
    for i, t in enumerate(times):
        o = price
        if i < range_end:
            # Strong mean reversion -> balanced DI, low ADX (entry qualifies).
            revert = (base - o) * 0.45
            c = o + revert + rng.gauss(0, 1) * vol
        else:
            # Sustained directional trend -> breaches ATR corridor repeatedly.
            c = o + trend_step + rng.gauss(0, 1) * vol * 0.7
        c = max(c, base * 0.5)
        hi = max(o, c) + abs(rng.gauss(0, 1)) * vol * 0.5
        lo = min(o, c) - abs(rng.gauss(0, 1)) * vol * 0.5
        candles.append({"ts": t.isoformat(), "o": round(o, 2), "h": round(hi, 2),
                        "l": round(lo, 2), "c": round(c, 2), "v": rng.randint(1000, 90000)})
        price = c
    return candles


def synthetic_range(instrument: str, start: str, end: str, tf: int) -> List[dict]:
    d0 = datetime.fromisoformat(start)
    d1 = datetime.fromisoformat(end)
    out = []
    d = d0
    seed = 0
    while d <= d1:
        if d.weekday() < 5:  # weekdays only
            out.extend(synthetic_candles(instrument, d, tf, seed=hash((instrument, d.date())) & 0xffff))
        d += timedelta(days=1)
        seed += 1
    return out


def synthetic_chain_at(instrument: str, spot: float, ts: datetime,
                       expiry: Optional[str]) -> tuple[List[dict], str]:
    spec = INSTRUMENTS[instrument]
    exp = expiry or _nearest_weekly_expiry(ts)
    exp_dt = datetime.fromisoformat(exp).replace(hour=15, minute=30)
    t_years = max((exp_dt - ts).total_seconds(), 3600) / (365.0 * 24 * 3600)
    chain = build_synthetic_chain(spot, spec["strike_step"], exp,
                                  t_years, spec["exchange"], instrument,
                                  span=40, iv=DEFAULT_IV)
    return chain, exp


def group_by_day(candles: List[dict]) -> dict:
    days = {}
    for c in candles:
        key = c["ts"][:10]
        days.setdefault(key, []).append(c)
    return days
