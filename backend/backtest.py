"""Backtest runner — drives the SHARED StrategyEngine over historical candles.
No simplified strategy: identical engine used by paper / live."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from engine import Action, Context, StrategyEngine
from indicators import compute_indicators
from models import INSTRUMENTS, Side, StrategyConfig
from options import price_leg_from_chain
from providers import group_by_day, synthetic_chain_at


def _fill(price: float, side, opening: bool, slip: float) -> float:
    """Adverse slippage: buys pay up, sells receive less. `opening` flips the
    effective transaction for closing trades."""
    s = side.value if hasattr(side, "value") else side
    is_buy = (s == "BUY") if opening else (s == "SELL")
    adj = 1 + slip / 100.0 if is_buy else 1 - slip / 100.0
    return round(price * adj, 2)


def run_backtest(cfg: StrategyConfig, candles: List[dict],
                 instrument: str) -> dict:
    spec = INSTRUMENTS[instrument]
    lot_size = spec["lot_size"]
    days = group_by_day(candles)

    baskets: List[dict] = []
    events: List[dict] = []
    equity: List[dict] = []
    daily_pnl: dict = {}
    cum_pnl = 0.0
    roll_up = roll_down = 0

    for day_key in sorted(days.keys()):
        day_candles = days[day_key]
        highs = [c["h"] for c in day_candles]
        lows = [c["l"] for c in day_candles]
        closes = [c["c"] for c in day_candles]
        ind = compute_indicators(highs, lows, closes, cfg.adx_period, cfg.atr_period)

        engine = StrategyEngine(cfg)
        open_basket: Optional[dict] = None
        day_pnl = 0.0

        def close_basket(ob, chain, ts, reason):
            nonlocal cum_pnl, day_pnl
            pnl = 0.0
            for leg in ob["legs"]:
                cur = price_leg_from_chain_local(leg, chain)
                exit_fill = _fill(cur, leg["side"], opening=False, slip=cfg.slippage_pct)
                if leg["side"] == "SELL":
                    leg_pnl = (leg["entry_fill"] - exit_fill) * leg["quantity"]
                else:
                    leg_pnl = (exit_fill - leg["entry_fill"]) * leg["quantity"]
                cost = cfg.brokerage_per_order + (exit_fill * leg["quantity"] * cfg.tax_pct / 100.0)
                leg_pnl -= cost
                leg["exit_fill"] = exit_fill
                pnl += leg_pnl
            ob["pnl"] = round(pnl, 2)
            ob["exit_ts"] = ts
            ob["close_reason"] = reason
            baskets.append(ob)
            cum_pnl += pnl
            day_pnl += pnl
            equity.append({"ts": ts, "equity": round(cum_pnl, 2)})

        def open_new(decision, ts, evt_type):
            legs = []
            for leg in decision.target_basket.legs:
                entry_fill = _fill(leg.entry_price, leg.side, opening=True, slip=cfg.slippage_pct)
                legs.append({
                    "role": leg.role.value, "option_type": leg.option_type.value,
                    "side": leg.side.value, "strike": leg.strike, "expiry": leg.expiry,
                    "quantity": leg.quantity, "lots": leg.lots,
                    "entry_price": leg.entry_price, "entry_fill": entry_fill,
                    "delta": leg.delta, "method": leg.method, "metric": leg.metric,
                })
            return {
                "day": day_key, "entry_ts": ts, "open_reason": decision.reason,
                "open_event": evt_type, "center": decision.center, "atr": decision.atr,
                "upper": decision.upper, "lower": decision.lower, "legs": legs,
                "pnl": 0.0, "exit_ts": None, "close_reason": None,
            }

        for i, candle in enumerate(day_candles):
            ts = candle["ts"]
            ts_dt = datetime.fromisoformat(ts)
            spot = candle["c"]
            chain, expiry = synthetic_chain_at(instrument, spot, ts_dt, cfg.expiry)
            ctx = Context(ts=ts_dt, o=candle["o"], h=candle["h"], l=candle["l"],
                          c=candle["c"], adx=_v(ind["adx"], i), plus_di=_v(ind["plus_di"], i),
                          minus_di=_v(ind["minus_di"], i), atr=_v(ind["atr"], i),
                          chain=chain, lot_size=lot_size)
            dec = engine.evaluate(ctx)

            if dec.action == Action.ENTER:
                open_basket = open_new(dec, ts, "INITIAL ENTRY")
                engine.on_enter_filled(dec)
                events.append({"ts": ts, "type": "INITIAL ENTRY", "reason": dec.reason,
                               "center": dec.center, "upper": dec.upper, "lower": dec.lower})
            elif dec.action in (Action.ROLL_UP, Action.ROLL_DOWN):
                # Invariant: close existing basket BEFORE opening the new one.
                close_basket(open_basket, chain, ts,
                             f"{dec.action} — {dec.reason}")
                open_basket = open_new(dec, ts, dec.action)
                engine.on_roll_filled(dec)
                if dec.action == Action.ROLL_UP:
                    roll_up += 1
                else:
                    roll_down += 1
                events.append({"ts": ts, "type": dec.action, "reason": dec.reason,
                               "center": dec.center, "upper": dec.upper, "lower": dec.lower})
            elif dec.action == Action.EXIT:
                close_basket(open_basket, chain, ts, "EXIT — " + dec.reason)
                engine.on_exit_filled()
                events.append({"ts": ts, "type": "EXIT", "reason": dec.reason})
                open_basket = None

        # Safety: force square-off if still open at end of day (no overnight).
        if open_basket is not None:
            last = day_candles[-1]
            ts_dt = datetime.fromisoformat(last["ts"])
            chain, _ = synthetic_chain_at(instrument, last["c"], ts_dt, cfg.expiry)
            close_basket(open_basket, chain, last["ts"], "EOD FORCED SQUARE-OFF")
            events.append({"ts": last["ts"], "type": "EXIT", "reason": "EOD forced square-off"})
            open_basket = None

        daily_pnl[day_key] = round(day_pnl, 2)

    stats = _stats(baskets, equity, roll_up, roll_down)
    return {"stats": stats, "baskets": baskets, "events": events,
            "equity": equity, "daily_pnl": daily_pnl}


def price_leg_from_chain_local(leg: dict, chain: list) -> float:
    i = min(range(len(chain)), key=lambda k: abs(chain[k]["strike"] - leg["strike"]))
    key = "ce_price" if leg["option_type"] == "CE" else "pe_price"
    return float(chain[i][key])


def _v(arr, i):
    import math
    val = float(arr[i])
    return None if math.isnan(val) else val


def _stats(baskets, equity, roll_up, roll_down):
    total = round(sum(b["pnl"] for b in baskets), 2)
    wins = sum(1 for b in baskets if b["pnl"] > 0)
    losses = sum(1 for b in baskets if b["pnl"] <= 0)
    n = len(baskets)
    peak = 0.0
    max_dd = 0.0
    for pt in equity:
        peak = max(peak, pt["equity"])
        max_dd = min(max_dd, pt["equity"] - peak)
    return {
        "total_pnl": total,
        "total_baskets": n,
        "winning_baskets": wins,
        "losing_baskets": losses,
        "win_rate": round(100.0 * wins / n, 1) if n else 0.0,
        "max_drawdown": round(max_dd, 2),
        "roll_up_count": roll_up,
        "roll_down_count": roll_down,
    }
