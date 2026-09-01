"""Option pricing (Black-Scholes), option-chain construction and leg selection.

For synthetic data / backtest the chain is priced with Black-Scholes so premiums
and deltas are internally consistent. When Upstox is connected the live chain
(LTP + broker delta) replaces the synthetic pricing, but the *selection* logic
below is identical for all modes."""
from __future__ import annotations

import math
from typing import List, Optional

from models import (HedgeMethod, Leg, LegRole, OptionType, ShortLegMethod, Side,
                    StrategyConfig)

DEFAULT_IV = 0.13          # annualised; editable assumption for synthetic pricing
RISK_FREE = 0.065
DAYS_YEAR = 365.0


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_price_delta(spot: float, strike: float, t_years: float, iv: float,
                   opt: OptionType) -> tuple[float, float]:
    """Return (price, delta). t_years floored to avoid div-by-zero at expiry."""
    t = max(t_years, 1.0 / (DAYS_YEAR * 24))
    if spot <= 0 or strike <= 0:
        return 0.0, 0.0
    d1 = (math.log(spot / strike) + (RISK_FREE + 0.5 * iv * iv) * t) / (iv * math.sqrt(t))
    d2 = d1 - iv * math.sqrt(t)
    if opt == OptionType.CE:
        price = spot * _norm_cdf(d1) - strike * math.exp(-RISK_FREE * t) * _norm_cdf(d2)
        delta = _norm_cdf(d1)
    else:
        price = strike * math.exp(-RISK_FREE * t) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)
        delta = _norm_cdf(d1) - 1.0
    return round(max(price, 0.05), 2), round(delta, 4)


def round_to_step(price: float, step: int) -> float:
    return round(price / step) * step


def build_synthetic_chain(spot: float, strike_step: int, expiry: str,
                          t_years: float, exchange: str, instrument: str,
                          span: int = 30, iv: float = DEFAULT_IV) -> List[dict]:
    """Build a chain of strikes around spot."""
    atm = round_to_step(spot, strike_step)
    chain = []
    for i in range(-span, span + 1):
        strike = atm + i * strike_step
        if strike <= 0:
            continue
        ce_p, ce_d = bs_price_delta(spot, strike, t_years, iv, OptionType.CE)
        pe_p, pe_d = bs_price_delta(spot, strike, t_years, iv, OptionType.PE)
        chain.append({
            "strike": strike,
            "ce_price": ce_p, "ce_delta": ce_d,
            "pe_price": pe_p, "pe_delta": pe_d,
            "ce_key": f"{exchange}|{instrument}|{expiry}|{int(strike)}|CE",
            "pe_key": f"{exchange}|{instrument}|{expiry}|{int(strike)}|PE",
        })
    return chain


def _atm_index(chain: List[dict], center: float) -> int:
    return min(range(len(chain)), key=lambda i: abs(chain[i]["strike"] - center))


def _closest_by(chain: List[dict], key: str, target: float) -> int:
    return min(range(len(chain)), key=lambda i: abs(chain[i][key] - target))


def select_short_legs(chain: List[dict], center: float, cfg: StrategyConfig,
                      expiry: str, lot_size: int) -> tuple[Leg, Leg]:
    method = cfg.short_method
    atm_i = _atm_index(chain, center)
    step = 1
    if method == ShortLegMethod.ATM:
        ce_i, pe_i = atm_i, atm_i
        metric_ce = metric_pe = "ATM"
    elif method == ShortLegMethod.OTM:
        ce_i = min(atm_i + cfg.short_ce_otm, len(chain) - 1)
        pe_i = max(atm_i - cfg.short_pe_otm, 0)
        metric_ce = f"OTM +{cfg.short_ce_otm} steps"
        metric_pe = f"OTM -{cfg.short_pe_otm} steps"
    elif method == ShortLegMethod.DELTA:
        ce_i = _closest_by(chain, "ce_delta", cfg.short_ce_delta)
        pe_i = _closest_by(chain, "pe_delta", cfg.short_pe_delta)
        metric_ce = f"Δ {chain[ce_i]['ce_delta']:.2f} (tgt {cfg.short_ce_delta})"
        metric_pe = f"Δ {chain[pe_i]['pe_delta']:.2f} (tgt {cfg.short_pe_delta})"
    else:  # PREMIUM
        ce_i = _closest_by(chain, "ce_price", cfg.short_ce_premium)
        pe_i = _closest_by(chain, "pe_price", cfg.short_pe_premium)
        metric_ce = f"₹{chain[ce_i]['ce_price']:.2f} (tgt {cfg.short_ce_premium})"
        metric_pe = f"₹{chain[pe_i]['pe_price']:.2f} (tgt {cfg.short_pe_premium})"

    ce = _mk_leg(chain[ce_i], LegRole.SHORT_CE, OptionType.CE, Side.SELL, cfg,
                 expiry, lot_size, str(method), metric_ce)
    pe = _mk_leg(chain[pe_i], LegRole.SHORT_PE, OptionType.PE, Side.SELL, cfg,
                 expiry, lot_size, str(method), metric_pe)
    return ce, pe


def select_hedge_legs(chain: List[dict], short_ce: Leg, short_pe: Leg,
                      cfg: StrategyConfig, expiry: str,
                      lot_size: int) -> tuple[Leg, Leg]:
    method = cfg.hedge_method
    ce_short_i = _atm_index(chain, short_ce.strike)
    pe_short_i = _atm_index(chain, short_pe.strike)
    if method == HedgeMethod.STRIKE_DISTANCE:
        ce_i = min(ce_short_i + cfg.hedge_ce_distance, len(chain) - 1)
        pe_i = max(pe_short_i - cfg.hedge_pe_distance, 0)
        metric_ce = f"+{cfg.hedge_ce_distance} steps"
        metric_pe = f"-{cfg.hedge_pe_distance} steps"
    elif method == HedgeMethod.DELTA:
        ce_i = _closest_by(chain, "ce_delta", cfg.hedge_ce_delta)
        pe_i = _closest_by(chain, "pe_delta", cfg.hedge_pe_delta)
        metric_ce = f"Δ {chain[ce_i]['ce_delta']:.2f} (tgt {cfg.hedge_ce_delta})"
        metric_pe = f"Δ {chain[pe_i]['pe_delta']:.2f} (tgt {cfg.hedge_pe_delta})"
    else:  # PREMIUM
        ce_i = _closest_by(chain, "ce_price", cfg.hedge_ce_premium)
        pe_i = _closest_by(chain, "pe_price", cfg.hedge_pe_premium)
        metric_ce = f"₹{chain[ce_i]['ce_price']:.2f} (tgt {cfg.hedge_ce_premium})"
        metric_pe = f"₹{chain[pe_i]['pe_price']:.2f} (tgt {cfg.hedge_pe_premium})"

    ce = _mk_leg(chain[ce_i], LegRole.LONG_CE, OptionType.CE, Side.BUY, cfg,
                 expiry, lot_size, str(method), metric_ce)
    pe = _mk_leg(chain[pe_i], LegRole.LONG_PE, OptionType.PE, Side.BUY, cfg,
                 expiry, lot_size, str(method), metric_pe)
    return ce, pe


def _mk_leg(row: dict, role: LegRole, opt: OptionType, side: Side,
            cfg: StrategyConfig, expiry: str, lot_size: int,
            method: str, metric: str) -> Leg:
    price_key = "ce_price" if opt == OptionType.CE else "pe_price"
    delta_key = "ce_delta" if opt == OptionType.CE else "pe_delta"
    key_key = "ce_key" if opt == OptionType.CE else "pe_key"
    qty = lot_size * cfg.lots
    return Leg(
        role=role, option_type=opt, side=side, strike=float(row["strike"]),
        expiry=expiry, instrument_key=row[key_key], lot_size=lot_size,
        lots=cfg.lots, quantity=qty, method=method, metric=metric,
        entry_price=float(row[price_key]), current_price=float(row[price_key]),
        delta=float(row[delta_key]),
    )


def price_leg_from_chain(leg: Leg, chain: List[dict]) -> float:
    """Return current premium for a leg's strike from a chain snapshot."""
    i = _atm_index(chain, leg.strike)
    key = "ce_price" if leg.option_type == OptionType.CE else "pe_price"
    return float(chain[i][key])
