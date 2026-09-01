"""Wilder ADX / +DI / -DI and ATR indicators. One implementation, shared by
backtest, paper and live so calculations never diverge across modes."""
from __future__ import annotations

from typing import List

import numpy as np


def _wilder_smooth(values: np.ndarray, period: int) -> np.ndarray:
    """Wilder's smoothing (RMA)."""
    out = np.full_like(values, np.nan, dtype=float)
    if len(values) < period:
        return out
    out[period - 1] = np.nansum(values[:period])
    for i in range(period, len(values)):
        out[i] = out[i - 1] - (out[i - 1] / period) + values[i]
    return out


def compute_indicators(highs: List[float], lows: List[float], closes: List[float],
                       adx_period: int, atr_period: int) -> dict:
    """Return arrays of atr, adx, plus_di, minus_di aligned to the input candles.
    Index i corresponds to candle i (NaN during warmup)."""
    h = np.asarray(highs, dtype=float)
    l = np.asarray(lows, dtype=float)
    c = np.asarray(closes, dtype=float)
    n = len(c)
    atr = np.full(n, np.nan)
    adx = np.full(n, np.nan)
    plus_di = np.full(n, np.nan)
    minus_di = np.full(n, np.nan)
    if n < 2:
        return {"atr": atr, "adx": adx, "plus_di": plus_di, "minus_di": minus_di}

    prev_c = np.roll(c, 1)
    tr = np.maximum.reduce([h - l, np.abs(h - prev_c), np.abs(l - prev_c)])
    tr[0] = h[0] - l[0]

    up_move = h - np.roll(h, 1)
    down_move = np.roll(l, 1) - l
    up_move[0] = down_move[0] = 0.0
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    # ATR (Wilder RMA of TR)
    atr_sm = _atr_rma(tr, atr_period)
    atr[:] = atr_sm

    # DI using ADX period smoothing of TR
    tr_sm = _atr_rma(tr, adx_period) * adx_period  # convert back to summed form
    plus_sm = _wilder_smooth(plus_dm, adx_period)
    minus_sm = _wilder_smooth(minus_dm, adx_period)

    with np.errstate(divide="ignore", invalid="ignore"):
        pdi = 100.0 * plus_sm / tr_sm
        mdi = 100.0 * minus_sm / tr_sm
        dx = 100.0 * np.abs(pdi - mdi) / (pdi + mdi)
    plus_di[:] = pdi
    minus_di[:] = mdi

    # ADX = Wilder smoothing of DX
    adx_arr = np.full(n, np.nan)
    valid = ~np.isnan(dx)
    first = np.argmax(valid) if valid.any() else n
    if valid.any():
        start = first + adx_period - 1
        if start < n:
            window = dx[first:first + adx_period]
            if len(window) == adx_period and not np.isnan(window).any():
                adx_arr[start] = np.mean(window)
                for i in range(start + 1, n):
                    if not np.isnan(dx[i]) and not np.isnan(adx_arr[i - 1]):
                        adx_arr[i] = (adx_arr[i - 1] * (adx_period - 1) + dx[i]) / adx_period
    adx[:] = adx_arr

    return {"atr": atr, "adx": adx, "plus_di": plus_di, "minus_di": minus_di}


def _atr_rma(tr: np.ndarray, period: int) -> np.ndarray:
    n = len(tr)
    out = np.full(n, np.nan)
    if n < period:
        return out
    out[period - 1] = np.mean(tr[:period])
    for i in range(period, n):
        out[i] = (out[i - 1] * (period - 1) + tr[i]) / period
    return out
