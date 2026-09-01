"""Shared pydantic models, enums and Mongo helpers for the trading terminal."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, List, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


# --------------------------------------------------------------------------- #
# Mongo helpers
# --------------------------------------------------------------------------- #
def _coerce_objectid(v: Any) -> str:
    if isinstance(v, ObjectId):
        return str(v)
    return v


PyObjectId = Annotated[str, BeforeValidator(_coerce_objectid)]


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    @classmethod
    def from_mongo(cls, doc: dict):
        if not doc:
            return None
        return cls(**doc)

    def to_mongo(self) -> dict:
        data = self.model_dump(by_alias=True, exclude_none=True)
        data.pop("_id", None)
        return data


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class TradingMode(str, Enum):
    BACKTEST = "BACKTEST"
    PAPER = "PAPER"
    LIVE = "LIVE"


class StrategyState(str, Enum):
    WAITING = "WAITING"
    INITIAL_QUALIFICATION = "INITIAL_QUALIFICATION"
    ENTERING = "ENTERING"
    ACTIVE_BASKET = "ACTIVE_BASKET"
    ROLL_UP = "ROLL_UP"
    ROLL_DOWN = "ROLL_DOWN"
    EXITING = "EXITING"
    COMPLETED = "COMPLETED"
    EXECUTION_ATTENTION = "EXECUTION_ATTENTION"
    ERROR = "ERROR"


class CenterSource(str, Enum):
    CLOSE = "CLOSE"
    OPEN = "OPEN"


class ShortLegMethod(str, Enum):
    ATM = "ATM"
    OTM = "OTM"          # strike-distance in ladder steps
    DELTA = "DELTA"
    PREMIUM = "PREMIUM"


class HedgeMethod(str, Enum):
    STRIKE_DISTANCE = "STRIKE_DISTANCE"
    DELTA = "DELTA"
    PREMIUM = "PREMIUM"


class OptionType(str, Enum):
    CE = "CE"
    PE = "PE"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class LegRole(str, Enum):
    SHORT_CE = "SHORT_CE"
    SHORT_PE = "SHORT_PE"
    LONG_CE = "LONG_CE"
    LONG_PE = "LONG_PE"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETE = "COMPLETE"
    REJECTED = "REJECTED"
    PARTIAL = "PARTIAL"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"


# --------------------------------------------------------------------------- #
# Instrument static specs (lot size / strike step are refreshed from Upstox
# when connected; these are editable implementation defaults, not strategy rules)
# --------------------------------------------------------------------------- #
INSTRUMENTS = {
    "NIFTY": {
        "name": "NIFTY 50",
        "underlying_key": "NSE_INDEX|Nifty 50",
        "lot_size": 75,
        "strike_step": 50,
        "exchange": "NSE_FO",
        "ref_price": 24800.0,
    },
    "BANKNIFTY": {
        "name": "NIFTY BANK",
        "underlying_key": "NSE_INDEX|Nifty Bank",
        "lot_size": 35,
        "strike_step": 100,
        "exchange": "NSE_FO",
        "ref_price": 53200.0,
    },
    "SENSEX": {
        "name": "SENSEX",
        "underlying_key": "BSE_INDEX|SENSEX",
        "lot_size": 20,
        "strike_step": 100,
        "exchange": "BSE_FO",
        "ref_price": 81300.0,
    },
    "BANKEX": {
        "name": "BANKEX",
        "underlying_key": "BSE_INDEX|BANKEX",
        "lot_size": 30,
        "strike_step": 100,
        "exchange": "BSE_FO",
        "ref_price": 61500.0,
    },
}

SUPPORTED_TIMEFRAMES = [1, 3, 5, 15]


# --------------------------------------------------------------------------- #
# Strategy configuration
# --------------------------------------------------------------------------- #
class StrategyConfig(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    # Strategy / instrument
    instrument: str = "NIFTY"
    expiry: Optional[str] = None          # YYYY-MM-DD; None = nearest weekly
    timeframe: int = 5                    # minutes

    # Indicators
    adx_period: int = 14                 # implementation default (editable)
    adx_threshold: float = 22.0          # from strategy doc
    atr_period: int = 14                 # implementation default (editable)
    atr_multiplier: float = 2.0          # from strategy doc

    center_source: CenterSource = CenterSource.CLOSE  # from strategy doc

    # Timing (IST, HH:MM)
    entry_time: str = "09:30"            # from strategy doc
    exit_time: str = "15:15"             # implementation default (editable)

    # Position size
    lots: int = 1

    # Short legs
    short_method: ShortLegMethod = ShortLegMethod.ATM
    short_ce_otm: int = 0                # ladder steps (OTM method)
    short_pe_otm: int = 0
    short_ce_delta: float = 0.30         # DELTA method
    short_pe_delta: float = -0.30
    short_ce_premium: float = 100.0      # PREMIUM method
    short_pe_premium: float = 100.0

    # Hedge legs
    hedge_enabled: bool = True
    hedge_method: HedgeMethod = HedgeMethod.STRIKE_DISTANCE
    hedge_ce_distance: int = 5           # ladder steps
    hedge_pe_distance: int = 5
    hedge_ce_delta: float = 0.10
    hedge_pe_delta: float = -0.10
    hedge_ce_premium: float = 20.0
    hedge_pe_premium: float = 20.0

    # Execution assumptions (backtest / paper)
    slippage_pct: float = 0.5            # % of premium
    brokerage_per_order: float = 20.0    # flat per leg order
    tax_pct: float = 0.05               # % of premium notional (approx STT+charges)


class ConfigDoc(BaseDocument):
    config: StrategyConfig = Field(default_factory=StrategyConfig)
    updated_at: datetime = Field(default_factory=now_utc)


# --------------------------------------------------------------------------- #
# Basket / leg runtime models
# --------------------------------------------------------------------------- #
class Leg(BaseModel):
    role: LegRole
    option_type: OptionType
    side: Side
    strike: float
    expiry: str
    instrument_key: str = ""
    lot_size: int = 0
    lots: int = 0
    quantity: int = 0
    method: str = ""
    metric: str = ""              # human readable selection metric
    entry_price: float = 0.0
    current_price: float = 0.0
    delta: float = 0.0
    order_id: Optional[str] = None
    order_status: OrderStatus = OrderStatus.PENDING
    error: Optional[str] = None

    def mtm(self) -> float:
        sign = 1 if self.side == Side.SELL else -1
        return sign * (self.entry_price - self.current_price) * self.quantity


class Basket(BaseModel):
    legs: List[Leg] = Field(default_factory=list)
    center: float = 0.0
    atr: float = 0.0
    upper: float = 0.0
    lower: float = 0.0
    opened_at: Optional[str] = None
    closed_at: Optional[str] = None

    def mtm(self) -> float:
        return sum(l.mtm() for l in self.legs)
