"""Paper / Live session manager. Runs the SHARED StrategyEngine against a
real-time feed. Paper uses simulated execution (never sends real orders); Live
places real Upstox MARKET orders and verifies broker status.

NOTE (V1): the intraday tick feed is a synthetic accelerated clock so the
terminal is demonstrable outside market hours / without an interactive Upstox
OAuth session. Order execution wiring to Upstox is real and gated behind a live
connection + explicit confirmation."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import List, Optional

from engine import Action, Context, StrategyEngine
from indicators import compute_indicators
from models import (INSTRUMENTS, OrderStatus, Side, StrategyConfig, StrategyState,
                    TradingMode)
from options import price_leg_from_chain
from providers import synthetic_candles, synthetic_chain_at
import market_data as md
import upstox_api as ux

TICK_SECONDS = 1.5      # accelerated synthetic demo clock
REAL_POLL_SECONDS = 12  # live Upstox poll cadence


class SessionManager:
    def __init__(self):
        self.reset()
        self._task: Optional[asyncio.Task] = None
        self.db = None

    def reset(self):
        self.mode: Optional[str] = None
        self.running = False
        self.cfg: Optional[StrategyConfig] = None
        self.engine: Optional[StrategyEngine] = None
        self.instrument = "NIFTY"
        self.data_source = "SYNTHETIC"
        self.lot_size = 0
        self.expiry_resolved: Optional[str] = None
        self._last_ts: Optional[str] = None
        self.candles: List[dict] = []
        self._all_day: List[dict] = []
        self._idx = 0
        self.spot = 0.0
        self.prev_spot = 0.0
        self.events: List[dict] = []
        self.orders: List[dict] = []
        self.errors: List[dict] = []
        self.trades: List[dict] = []
        self.basket_pnl = 0.0
        self.next_event = "—"

    # ------------------------------------------------------------------ #
    def _log(self, bucket: List[dict], **kw):
        kw["ts"] = kw.get("ts") or datetime.now().isoformat()
        bucket.insert(0, kw)
        del bucket[400:]

    async def start(self, mode: str, cfg: StrategyConfig):
        if self.running:
            raise RuntimeError("Session already running")
        self.reset()
        self.mode = mode
        self.cfg = cfg
        self.instrument = cfg.instrument
        self.engine = StrategyEngine(cfg)

        connected = False
        try:
            connected = await ux.is_connected(self.db)
        except Exception:
            connected = False

        # LIVE always uses real data (gated upstream). PAPER uses real data when
        # connected, otherwise the synthetic offline feed. BACKTEST is separate.
        use_real = connected and mode in (TradingMode.PAPER.value, TradingMode.LIVE.value)

        if use_real:
            meta = await md.resolve_contract(self.db, self.instrument, cfg.expiry)
            self.data_source = "UPSTOX"
            self.lot_size = meta["lot_size"]
            self.expiry_resolved = meta["expiry"]
            self.cfg.expiry = meta["expiry"]
            self.running = True
            self._log(self.events, type="SESSION START",
                      reason=f"{mode} session · UPSTOX live data · expiry {meta['expiry']}")
            self._task = asyncio.create_task(self._loop_real())
        else:
            if mode == TradingMode.LIVE.value:
                raise RuntimeError("LIVE requires a valid Upstox connection")
            self.data_source = "SYNTHETIC"
            self.lot_size = INSTRUMENTS[self.instrument]["lot_size"]
            today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            self._all_day = self._pick_qualifying_day(today, cfg)
            self._idx = 0
            self.running = True
            self._log(self.events, type="SESSION START",
                      reason=f"{mode} session · SYNTHETIC feed (Upstox not connected)")
            self._task = asyncio.create_task(self._loop_synthetic())

    def _pick_qualifying_day(self, day, cfg):
        """Pick a synthetic day where the initial ADX qualification is reachable,
        so a demo session reliably enters a basket."""
        from engine import qualifies_initial
        import random as _r
        base_seed = int(datetime.now().timestamp()) % 100000
        entry_min = int(cfg.entry_time.split(":")[0]) * 60 + int(cfg.entry_time.split(":")[1])
        best = None
        for k in range(20):
            seed = (base_seed + k * 131) % 100000
            candles = synthetic_candles(self.instrument, day, cfg.timeframe, seed=seed)
            highs = [c["h"] for c in candles]; lows = [c["l"] for c in candles]; closes = [c["c"] for c in candles]
            ind = compute_indicators(highs, lows, closes, cfg.adx_period, cfg.atr_period)
            if best is None:
                best = candles
            for i, c in enumerate(candles):
                ts = datetime.fromisoformat(c["ts"])
                if ts.hour * 60 + ts.minute < entry_min:
                    continue
                if qualifies_initial(_v(ind["adx"], i), _v(ind["plus_di"], i),
                                     _v(ind["minus_di"], i), cfg.adx_threshold):
                    return candles
        return best

    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
        self._log(self.events, type="SESSION STOP", reason="Algo stopped by user")

    async def _loop_synthetic(self):
        try:
            while self.running and self._idx < len(self._all_day):
                candle = self._all_day[self._idx]
                self.candles.append(candle)
                ts_dt = datetime.fromisoformat(candle["ts"])
                chain, _ = synthetic_chain_at(self.instrument, candle["c"], ts_dt, self.cfg.expiry)
                await self._process(candle, chain)
                self._idx += 1
                await asyncio.sleep(TICK_SECONDS)
            self.running = False
        except asyncio.CancelledError:
            pass
        except Exception as e:  # surface, never hide
            self.running = False
            if self.engine:
                self.engine.set_error(str(e))
            self._log(self.errors, type="LOOP ERROR", reason=str(e))

    async def _loop_real(self):
        """Poll real Upstox intraday candles; act on each newly CLOSED candle and
        mark-to-market from the live option chain in between."""
        try:
            self.candles = await md.underlying_intraday(self.db, self.instrument, self.cfg.timeframe)
            if self.candles:
                self._last_ts = self.candles[-1]["ts"]
                chain, spot = await md.chain_snapshot(self.db, self.instrument, self.expiry_resolved)
                await self._process(self.candles[-1], chain)
            while self.running:
                await asyncio.sleep(REAL_POLL_SECONDS)
                if not self.running:
                    break
                try:
                    latest = await md.underlying_intraday(self.db, self.instrument, self.cfg.timeframe)
                    chain, spot = await md.chain_snapshot(self.db, self.instrument, self.expiry_resolved)
                except PermissionError as e:
                    self.engine.set_error(str(e))
                    self._log(self.errors, type="DATA ERROR", reason=str(e))
                    self.running = False
                    break
                except Exception as e:
                    self._log(self.errors, type="DATA FEED", reason=str(e))
                    continue
                new = [c for c in latest if self._last_ts is None or c["ts"] > self._last_ts]
                if new:
                    for c in new:
                        self.candles.append(c)
                        self._last_ts = c["ts"]
                    await self._process(self.candles[-1], chain)
                elif self.engine.basket:
                    for leg in self.engine.basket.legs:
                        leg.current_price = price_leg_from_chain(leg, chain)
                    self.basket_pnl = round(self.engine.basket.mtm(), 2)
            self.running = False
        except asyncio.CancelledError:
            pass
        except Exception as e:  # surface, never hide
            self.running = False
            if self.engine:
                self.engine.set_error(str(e))
            self._log(self.errors, type="LOOP ERROR", reason=str(e))

    async def _process(self, candle: dict, chain: list):
        """Shared per-candle processing for synthetic and real feeds. Acts on the
        latest candle in self.candles (already appended by the caller)."""
        self.prev_spot = self.spot
        self.spot = candle["c"]
        ts_dt = datetime.fromisoformat(candle["ts"])

        highs = [c["h"] for c in self.candles]
        lows = [c["l"] for c in self.candles]
        closes = [c["c"] for c in self.candles]
        ind = compute_indicators(highs, lows, closes, self.cfg.adx_period, self.cfg.atr_period)
        i = len(self.candles) - 1

        # Mark-to-market current basket from the same chain snapshot.
        if self.engine.basket:
            for leg in self.engine.basket.legs:
                leg.current_price = price_leg_from_chain(leg, chain)
            self.basket_pnl = round(self.engine.basket.mtm(), 2)

        ctx = Context(ts=ts_dt, o=candle["o"], h=candle["h"], l=candle["l"], c=candle["c"],
                      adx=_v(ind["adx"], i), plus_di=_v(ind["plus_di"], i),
                      minus_di=_v(ind["minus_di"], i), atr=_v(ind["atr"], i),
                      chain=chain, lot_size=self.lot_size)
        dec = self.engine.evaluate(ctx)

        if dec.action == Action.ENTER:
            ok = await self._execute_open(dec, "INITIAL ENTRY", candle["ts"])
            if ok:
                self.engine.on_enter_filled(dec)
                self._mark_event(candle["ts"], "INITIAL ENTRY", dec)
        elif dec.action in (Action.ROLL_UP, Action.ROLL_DOWN):
            closed = await self._execute_close(self.engine.basket, candle["ts"], f"{dec.action}")
            if closed:
                ok = await self._execute_open(dec, dec.action, candle["ts"])
                if ok:
                    self.engine.on_roll_filled(dec)
                    self._mark_event(candle["ts"], dec.action, dec)
        elif dec.action == Action.EXIT:
            closed = await self._execute_close(self.engine.basket, candle["ts"], "EXIT")
            if closed:
                self.engine.on_exit_filled()
                self._mark_event(candle["ts"], "EXIT", dec)
                self.running = False

        self._compute_next(ctx, dec)

    def _mark_event(self, ts, etype, dec):
        self._log(self.events, ts=ts, type=etype, reason=dec.reason,
                  center=round(dec.center, 2), upper=round(dec.upper, 2),
                  lower=round(dec.lower, 2))

    def _compute_next(self, ctx, dec):
        if self.engine.state == StrategyState.ACTIVE_BASKET:
            self.next_event = f"Roll if close > {self.engine.upper:.1f} or < {self.engine.lower:.1f}"
        elif self.engine.state == StrategyState.WAITING:
            self.next_event = "Await ADX qualification / entry time"
        elif self.engine.state == StrategyState.COMPLETED:
            self.next_event = "Session complete — no further action"
        else:
            self.next_event = dec.reason

    # ------------------------- execution ------------------------------ #
    async def _execute_open(self, dec, evt_type, ts) -> bool:
        legs = dec.target_basket.legs
        for leg in legs:
            price = leg.entry_price
            if self.mode == TradingMode.LIVE.value:
                ok = await self._live_order(leg, ts)
                if not ok:
                    self.engine.set_attention(f"Leg {leg.role} failed on {evt_type}")
                    self._log(self.errors, type="EXECUTION ATTENTION",
                              reason=f"{evt_type} leg {leg.role} not confirmed")
                    return False
            else:  # PAPER — simulated, never real
                leg.order_id = f"PAPER-{len(self.orders)+1}"
                leg.order_status = OrderStatus.COMPLETE
                leg.entry_price = price
                leg.current_price = price
            self._log(self.orders, ts=ts, leg=leg.role.value, side=leg.side.value,
                      strike=leg.strike, qty=leg.quantity, price=leg.entry_price,
                      status=leg.order_status.value,
                      order_id=leg.order_id, event=evt_type)
        return True

    async def _execute_close(self, basket, ts, reason) -> bool:
        if not basket:
            return True
        for leg in basket.legs:
            close_side = Side.BUY if leg.side == Side.SELL else Side.SELL
            if self.mode == TradingMode.LIVE.value:
                ok = await self._live_order(leg, ts, override_side=close_side, closing=True)
                if not ok:
                    self.engine.set_attention(f"Close failed leg {leg.role}")
                    self._log(self.errors, type="EXECUTION ATTENTION",
                              reason=f"Close leg {leg.role} not confirmed")
                    return False
            realized = leg.mtm()
            self.trades.insert(0, {"ts": ts, "leg": leg.role.value, "side": close_side.value,
                                   "strike": leg.strike, "qty": leg.quantity,
                                   "entry": leg.entry_price, "exit": leg.current_price,
                                   "pnl": round(realized, 2), "reason": reason})
            self._log(self.orders, ts=ts, leg=leg.role.value, side=close_side.value,
                      strike=leg.strike, qty=leg.quantity, price=leg.current_price,
                      status="COMPLETE", order_id=f"{'LIVE' if self.mode==TradingMode.LIVE.value else 'PAPER'}-CLOSE",
                      event=f"CLOSE/{reason}")
        del self.trades[400:]
        return True

    async def _live_order(self, leg, ts, override_side=None, closing=False) -> bool:
        """Place a real Upstox MARKET order and verify status."""
        try:
            import upstox_api as ux
            side = override_side.value if override_side else leg.side.value
            resp = await ux.place_market_order(self.db, leg.instrument_key,
                                               leg.quantity, side)
            order_id = (resp.get("data") or {}).get("order_id") or resp.get("order_id")
            leg.order_id = order_id
            # Verify broker status — never assume submitted == filled.
            status = await ux.order_status(self.db, order_id)
            data = status.get("data") or []
            last = data[-1] if isinstance(data, list) and data else {}
            st = (last.get("status") or "").lower()
            if "complete" in st:
                leg.order_status = OrderStatus.COMPLETE
                return True
            if "reject" in st:
                leg.order_status = OrderStatus.REJECTED
                leg.error = last.get("status_message", "rejected")
                return False
            leg.order_status = OrderStatus.PENDING
            return False
        except Exception as e:
            leg.error = str(e)
            self._log(self.errors, type="ORDER ERROR", reason=str(e))
            return False

    async def emergency_squareoff(self):
        if self.engine and self.engine.basket:
            await self._execute_close(self.engine.basket, datetime.now().isoformat(),
                                      "EMERGENCY SQUARE-OFF")
            self.engine.on_exit_filled()
            self._log(self.events, type="EMERGENCY", reason="Emergency square-off executed")
        self.running = False

    # ------------------------- status snapshot ------------------------ #
    def status(self) -> dict:
        eng = self.engine
        basket = None
        if eng and eng.basket:
            basket = {
                "center": eng.center, "atr": eng.atr, "upper": eng.upper, "lower": eng.lower,
                "pnl": self.basket_pnl,
                "legs": [{
                    "role": l.role.value, "type": l.option_type.value, "side": l.side.value,
                    "strike": l.strike, "expiry": l.expiry, "qty": l.quantity, "lots": l.lots,
                    "avg_price": l.entry_price, "ltp": l.current_price,
                    "pnl": round(l.mtm(), 2), "status": l.order_status.value,
                    "order_id": l.order_id, "metric": l.metric,
                } for l in eng.basket.legs],
            }
        return {
            "mode": self.mode, "running": self.running,
            "data_source": self.data_source,
            "expiry": self.expiry_resolved,
            "lot_size": self.lot_size,
            "state": str(eng.state.value) if eng else "WAITING",
            "attention": eng.attention_reason if eng else None,
            "instrument": self.instrument,
            "spot": self.spot, "prev_spot": self.prev_spot,
            "center": eng.center if eng else 0, "atr": eng.atr if eng else 0,
            "upper": eng.upper if eng else 0, "lower": eng.lower if eng else 0,
            "atr_multiplier": self.cfg.atr_multiplier if self.cfg else 0,
            "basket": basket, "basket_pnl": self.basket_pnl,
            "next_event": self.next_event,
            "candles": self.candles[-120:],
            "events": self.events[:60],
            "orders": self.orders[:80],
            "trades": self.trades[:80],
            "errors": self.errors[:40],
        }


def _v(arr, i):
    import math
    val = float(arr[i])
    return None if math.isnan(val) else val
