"""Automated tests for the critical strategy invariants (spec section 40/41)."""
import os
from datetime import datetime

os.environ.setdefault("TOKEN_ENCRYPTION_KEY", "lGLkNvSAKiO3UECWJxzd2bzRejq2nvhA2Qd0tQDZoFE=")

from engine import Action, Context, StrategyEngine, qualifies_initial
from models import INSTRUMENTS, ShortLegMethod, HedgeMethod, StrategyConfig, StrategyState
from options import build_synthetic_chain

SPEC = INSTRUMENTS["NIFTY"]
CHAIN = build_synthetic_chain(24800, 50, "2026-06-25", 0.02, "NSE_FO", "NIFTY", span=40)


def ctx(ts, c, adx=10, pdi=30, mdi=25, atr=60, o=None):
    return Context(ts=datetime.fromisoformat(ts), o=o if o is not None else c, h=c + 5,
                   l=c - 5, c=c, adx=adx, plus_di=pdi, minus_di=mdi, atr=atr,
                   chain=CHAIN, lot_size=SPEC["lot_size"])


def cfg(**kw):
    base = dict(instrument="NIFTY", timeframe=5, atr_multiplier=2.0, adx_threshold=22.0,
                entry_time="09:30", exit_time="15:15")
    base.update(kw)
    return StrategyConfig(**base)


# ---------------- initial qualification ---------------- #
def test_qualifies_valid():
    assert qualifies_initial(10, 30, 25, 22) is True

def test_qualifies_threshold_fail():
    assert qualifies_initial(25, 30, 28, 22) is False

def test_qualifies_plus_di_fail():
    assert qualifies_initial(20, 15, 30, 22) is False

def test_qualifies_minus_di_fail():
    assert qualifies_initial(20, 30, 15, 22) is False


# ---------------- entry timing ---------------- #
def test_no_entry_before_time():
    e = StrategyEngine(cfg())
    d = e.evaluate(ctx("2026-06-25T09:20:00", 24800))
    assert d.action == Action.HOLD

def test_entry_after_time_qualified():
    e = StrategyEngine(cfg())
    d = e.evaluate(ctx("2026-06-25T09:35:00", 24800))
    assert d.action == Action.ENTER
    assert d.target_basket is not None

def test_no_entry_when_adx_unqualified():
    e = StrategyEngine(cfg())
    d = e.evaluate(ctx("2026-06-25T09:35:00", 24800, adx=30))
    assert d.action == Action.HOLD


# ---------------- ATR corridor ---------------- #
def _activate(e):
    d = e.evaluate(ctx("2026-06-25T09:35:00", 24800, atr=60))
    e.on_enter_filled(d)
    return d

def test_hold_inside_band():
    e = StrategyEngine(cfg())
    _activate(e)
    d = e.evaluate(ctx("2026-06-25T10:00:00", 24850))  # within ±120
    assert d.action == Action.HOLD

def test_roll_up_on_upper_breach():
    e = StrategyEngine(cfg())
    _activate(e)  # center 24800, upper 24920
    d = e.evaluate(ctx("2026-06-25T10:00:00", 24950))
    assert d.action == Action.ROLL_UP

def test_roll_down_on_lower_breach():
    e = StrategyEngine(cfg())
    _activate(e)  # lower 24680
    d = e.evaluate(ctx("2026-06-25T10:00:00", 24650))
    assert d.action == Action.ROLL_DOWN


# ---------------- rolls ignore ADX ---------------- #
def test_roll_up_ignores_bad_adx():
    e = StrategyEngine(cfg())
    _activate(e)
    d = e.evaluate(ctx("2026-06-25T10:00:00", 24950, adx=40, pdi=5, mdi=5))
    assert d.action == Action.ROLL_UP

def test_roll_down_ignores_bad_adx():
    e = StrategyEngine(cfg())
    _activate(e)
    d = e.evaluate(ctx("2026-06-25T10:00:00", 24650, adx=40, pdi=5, mdi=5))
    assert d.action == Action.ROLL_DOWN


# ---------------- roll re-centers & fresh corridor ---------------- #
def test_roll_creates_new_center_and_corridor():
    e = StrategyEngine(cfg())
    _activate(e)
    old_center, old_upper = e.center, e.upper
    d = e.evaluate(ctx("2026-06-25T10:00:00", 24950, atr=70))
    e.on_roll_filled(d)
    assert e.center != old_center
    assert e.upper != old_upper
    assert e.upper == e.center + 70 * 2.0
    assert e.lower == e.center - 70 * 2.0


# ---------------- exit behaviour ---------------- #
def test_exit_at_exit_time():
    e = StrategyEngine(cfg())
    _activate(e)
    d = e.evaluate(ctx("2026-06-25T15:15:00", 24800))
    assert d.action == Action.EXIT

def test_no_roll_after_exit_time():
    e = StrategyEngine(cfg())
    _activate(e)
    d = e.evaluate(ctx("2026-06-25T15:20:00", 24950))
    assert d.action != Action.ROLL_UP

def test_no_entry_after_exit_time():
    e = StrategyEngine(cfg())
    d = e.evaluate(ctx("2026-06-25T15:30:00", 24800))
    assert d.action == Action.HOLD

def test_completed_state_holds():
    e = StrategyEngine(cfg())
    _activate(e)
    d = e.evaluate(ctx("2026-06-25T15:15:00", 24800))
    e.on_exit_filled()
    assert e.state == StrategyState.COMPLETED
    d2 = e.evaluate(ctx("2026-06-25T15:20:00", 24950))
    assert d2.action == Action.HOLD


# ---------------- basket construction ---------------- #
def test_four_leg_basket():
    e = StrategyEngine(cfg(hedge_enabled=True))
    d = e.evaluate(ctx("2026-06-25T09:35:00", 24800))
    roles = {str(l.role) for l in d.target_basket.legs}
    assert roles == {"LegRole.SHORT_CE", "LegRole.SHORT_PE", "LegRole.LONG_CE", "LegRole.LONG_PE"}

def test_atm_selection():
    e = StrategyEngine(cfg(short_method="ATM"))
    d = e.evaluate(ctx("2026-06-25T09:35:00", 24800))
    ce = next(l for l in d.target_basket.legs if str(l.role) == "LegRole.SHORT_CE")
    assert ce.strike == 24800

def test_otm_selection():
    e = StrategyEngine(cfg(short_method="OTM", short_ce_otm=5, short_pe_otm=5, hedge_enabled=False))
    d = e.evaluate(ctx("2026-06-25T09:35:00", 24800))
    ce = next(l for l in d.target_basket.legs if str(l.role) == "LegRole.SHORT_CE")
    pe = next(l for l in d.target_basket.legs if str(l.role) == "LegRole.SHORT_PE")
    assert ce.strike == 24800 + 5 * 50
    assert pe.strike == 24800 - 5 * 50

def test_delta_selection_short():
    e = StrategyEngine(cfg(short_method="DELTA", short_ce_delta=0.30, short_pe_delta=-0.30, hedge_enabled=False))
    d = e.evaluate(ctx("2026-06-25T09:35:00", 24800))
    ce = next(l for l in d.target_basket.legs if str(l.role) == "LegRole.SHORT_CE")
    assert abs(ce.delta - 0.30) < 0.15

def test_premium_selection_short():
    e = StrategyEngine(cfg(short_method="PREMIUM", short_ce_premium=100, short_pe_premium=100, hedge_enabled=False))
    d = e.evaluate(ctx("2026-06-25T09:35:00", 24800))
    ce = next(l for l in d.target_basket.legs if str(l.role) == "LegRole.SHORT_CE")
    assert abs(ce.entry_price - 100) < 60

def test_hedge_strike_distance():
    e = StrategyEngine(cfg(short_method="ATM", hedge_method="STRIKE_DISTANCE",
                           hedge_ce_distance=5, hedge_pe_distance=5))
    d = e.evaluate(ctx("2026-06-25T09:35:00", 24800))
    lce = next(l for l in d.target_basket.legs if str(l.role) == "LegRole.LONG_CE")
    lpe = next(l for l in d.target_basket.legs if str(l.role) == "LegRole.LONG_PE")
    assert lce.strike == 24800 + 5 * 50
    assert lpe.strike == 24800 - 5 * 50
