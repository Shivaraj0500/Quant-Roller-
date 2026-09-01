"""Mode-independent strategy engine + explicit state machine for the
"Straddle ATR Band — Re-Centering Roller".

CRITICAL INVARIANTS (enforced here and by tests):
  * ADX / +DI / -DI qualify ONLY the initial entry.
  * Roll Up / Roll Down are driven ONLY by an ATR-boundary CLOSING breach.
  * Rolls never re-check ADX/+DI/-DI.
  * Price inside the corridor => HOLD (no roll, no re-center).
  * No entry / no roll after exit time. No overnight position.

The engine makes DECISIONS from market data only. It never places orders.
Execution adapters (backtest / paper / live) carry out the decision and report
fills, after which the orchestrator calls the on_*_filled hooks."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from models import Basket, Leg, StrategyConfig, StrategyState
from options import select_hedge_legs, select_short_legs


class Action:
    HOLD = "HOLD"
    ENTER = "ENTER"
    ROLL_UP = "ROLL_UP"
    ROLL_DOWN = "ROLL_DOWN"
    EXIT = "EXIT"


@dataclass
class Decision:
    action: str
    reason: str = ""
    center: float = 0.0
    atr: float = 0.0
    upper: float = 0.0
    lower: float = 0.0
    target_basket: Optional[Basket] = None


@dataclass
class Context:
    ts: datetime
    o: float
    h: float
    l: float
    c: float
    adx: float
    plus_di: float
    minus_di: float
    atr: float
    chain: list
    lot_size: int


def _mins(t: str) -> int:
    hh, mm = t.split(":")
    return int(hh) * 60 + int(mm)


def qualifies_initial(adx: float, plus_di: float, minus_di: float,
                      threshold: float) -> bool:
    """Initial-entry qualification: ADX < threshold AND ADX < +DI AND ADX < -DI."""
    if any(v is None for v in (adx, plus_di, minus_di)):
        return False
    return (adx < threshold) and (adx < plus_di) and (adx < minus_di)


class StrategyEngine:
    def __init__(self, cfg: StrategyConfig):
        self.cfg = cfg
        self.state = StrategyState.WAITING
        self.basket: Optional[Basket] = None
        self.center = 0.0
        self.atr = 0.0
        self.upper = 0.0
        self.lower = 0.0
        self.attention_reason: Optional[str] = None

    # ------------------------------------------------------------------ #
    def _build_target(self, ctx: Context) -> Basket:
        center = ctx.c if self.cfg.center_source == "CLOSE" else ctx.o
        expiry = self.cfg.expiry or "NEAREST"
        short_ce, short_pe = select_short_legs(ctx.chain, center, self.cfg,
                                               expiry, ctx.lot_size)
        legs: List[Leg] = [short_ce, short_pe]
        if self.cfg.hedge_enabled:
            hedge_ce, hedge_pe = select_hedge_legs(ctx.chain, short_ce, short_pe,
                                                   self.cfg, expiry, ctx.lot_size)
            legs += [hedge_ce, hedge_pe]
        atr = ctx.atr
        upper = center + atr * self.cfg.atr_multiplier
        lower = center - atr * self.cfg.atr_multiplier
        return Basket(legs=legs, center=center, atr=atr, upper=upper, lower=lower,
                      opened_at=ctx.ts.isoformat())

    def evaluate(self, ctx: Context) -> Decision:
        """Return the decision for a *closed* candle. Pure: no side effects on
        broker; only reads engine state."""
        if self.state in (StrategyState.COMPLETED, StrategyState.ERROR,
                           StrategyState.EXECUTION_ATTENTION):
            return Decision(Action.HOLD, reason=f"State {self.state}")

        t = ctx.ts.hour * 60 + ctx.ts.minute
        exit_t = _mins(self.cfg.exit_time)
        entry_t = _mins(self.cfg.entry_time)

        # Mandatory intraday exit — overrides everything once a basket is live.
        if t >= exit_t:
            if self.state in (StrategyState.ACTIVE_BASKET,):
                return Decision(Action.EXIT, reason="Exit time reached")
            # After exit time, no entry / no roll.
            return Decision(Action.HOLD, reason="After exit time — session locked")

        if self.state == StrategyState.WAITING:
            if t < entry_t:
                return Decision(Action.HOLD, reason="Before entry time")
            if qualifies_initial(ctx.adx, ctx.plus_di, ctx.minus_di,
                                 self.cfg.adx_threshold):
                tgt = self._build_target(ctx)
                return Decision(Action.ENTER, reason="Initial ADX qualification",
                                center=tgt.center, atr=tgt.atr,
                                upper=tgt.upper, lower=tgt.lower, target_basket=tgt)
            return Decision(Action.HOLD, reason="Awaiting ADX qualification")

        if self.state == StrategyState.ACTIVE_BASKET:
            # ONLY ATR boundary — ADX intentionally ignored here.
            if ctx.c > self.upper:
                tgt = self._build_target(ctx)
                return Decision(Action.ROLL_UP,
                                reason=f"Close {ctx.c:.2f} > upper {self.upper:.2f}",
                                center=tgt.center, atr=tgt.atr,
                                upper=tgt.upper, lower=tgt.lower, target_basket=tgt)
            if ctx.c < self.lower:
                tgt = self._build_target(ctx)
                return Decision(Action.ROLL_DOWN,
                                reason=f"Close {ctx.c:.2f} < lower {self.lower:.2f}",
                                center=tgt.center, atr=tgt.atr,
                                upper=tgt.upper, lower=tgt.lower, target_basket=tgt)
            return Decision(Action.HOLD, reason="Inside ATR corridor")

        return Decision(Action.HOLD, reason=f"State {self.state}")

    # --------------------- state transition hooks --------------------- #
    def on_enter_filled(self, decision: Decision):
        self.basket = decision.target_basket
        self.center, self.atr = decision.center, decision.atr
        self.upper, self.lower = decision.upper, decision.lower
        self.state = StrategyState.ACTIVE_BASKET

    def on_roll_filled(self, decision: Decision):
        """Old basket MUST already be closed by the orchestrator before this."""
        self.basket = decision.target_basket
        self.center, self.atr = decision.center, decision.atr
        self.upper, self.lower = decision.upper, decision.lower
        self.state = StrategyState.ACTIVE_BASKET

    def on_exit_filled(self):
        self.basket = None
        self.state = StrategyState.COMPLETED

    def set_attention(self, reason: str):
        self.attention_reason = reason
        self.state = StrategyState.EXECUTION_ATTENTION

    def set_error(self, reason: str):
        self.attention_reason = reason
        self.state = StrategyState.ERROR
