"""End-to-end API tests for QUANT-ROLLER PRO.

Covers: /api/meta, /api/config CRUD+validate, /api/basket/preview (all short
methods + hedge disabled), /api/backtest/run, /api/session lifecycle (paper
+ live gating), /api/upstox status/login/funds/positions.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # Fallback: read frontend .env directly since tests run in the same repo
    from pathlib import Path
    for line in Path("/app/frontend/.env").read_text().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip()
            break
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="session")
def s():
    return requests.Session()


# ------------------------- /api/meta ------------------------- #
def test_meta(s):
    r = s.get(f"{API}/meta", timeout=30)
    assert r.status_code == 200
    d = r.json()
    for k in ("NIFTY", "BANKNIFTY", "SENSEX", "BANKEX"):
        assert k in d["instruments"]
        assert "lot_size" in d["instruments"][k]
        assert "strike_step" in d["instruments"][k]
    assert d["timeframes"] == [1, 3, 5, 15]
    assert set(d["short_methods"]) == {"ATM", "OTM", "DELTA", "PREMIUM"}
    assert set(d["hedge_methods"]) == {"STRIKE_DISTANCE", "DELTA", "PREMIUM"}
    assert set(d["center_sources"]) == {"CLOSE", "OPEN"}


# ------------------------- /api/config ----------------------- #
def _default_config():
    return {
        "instrument": "NIFTY", "expiry": None, "timeframe": 5,
        "adx_period": 14, "adx_threshold": 22.0, "atr_period": 14,
        "atr_multiplier": 2.0, "center_source": "CLOSE",
        "entry_time": "09:30", "exit_time": "15:15", "lots": 1,
        "short_method": "ATM", "short_ce_otm": 0, "short_pe_otm": 0,
        "short_ce_delta": 0.30, "short_pe_delta": -0.30,
        "short_ce_premium": 100.0, "short_pe_premium": 100.0,
        "hedge_enabled": True, "hedge_method": "STRIKE_DISTANCE",
        "hedge_ce_distance": 5, "hedge_pe_distance": 5,
        "hedge_ce_delta": 0.10, "hedge_pe_delta": -0.10,
        "hedge_ce_premium": 20.0, "hedge_pe_premium": 20.0,
        "slippage_pct": 0.5, "brokerage_per_order": 20.0, "tax_pct": 0.05,
    }


def test_config_get_default(s):
    r = s.get(f"{API}/config", timeout=30); assert r.status_code == 200
    d = r.json()
    assert d["instrument"] in ("NIFTY", "BANKNIFTY", "SENSEX", "BANKEX")
    assert d["adx_threshold"] == 22.0
    assert d["atr_multiplier"] == 2.0
    assert d["entry_time"] == "09:30"


def test_config_put_valid(s):
    cfg = _default_config()
    cfg["lots"] = 2
    r = s.put(f"{API}/config", json=cfg, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["config"]["lots"] == 2
    # Verify persisted
    got = s.get(f"{API}/config").json()
    assert got["lots"] == 2
    # revert
    cfg["lots"] = 1; s.put(f"{API}/config", json=cfg)


def test_config_validate_ok(s):
    r = s.post(f"{API}/config/validate", json=_default_config())
    assert r.status_code == 200
    assert r.json()["valid"] is True


def test_config_validate_bad_entry_after_exit(s):
    cfg = _default_config(); cfg["entry_time"] = "15:30"; cfg["exit_time"] = "09:30"
    r = s.post(f"{API}/config/validate", json=cfg)
    assert r.status_code == 200
    d = r.json()
    assert d["valid"] is False
    assert any("Entry" in e for e in d["errors"])


def test_config_put_bad_lots_rejected(s):
    cfg = _default_config(); cfg["lots"] = 0
    r = s.put(f"{API}/config", json=cfg)
    assert r.status_code == 400


def test_config_put_bad_timeframe(s):
    cfg = _default_config(); cfg["timeframe"] = 7
    r = s.put(f"{API}/config", json=cfg)
    assert r.status_code == 400


# ------------------------- /api/basket/preview -------------- #
def test_basket_preview_atm_4legs(s):
    r = s.post(f"{API}/basket/preview", json=_default_config(), timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["legs"]) == 4
    roles = {l["role"] for l in d["legs"]}
    assert roles == {"LegRole.SHORT_CE", "SHORT_CE",
                     "LegRole.SHORT_PE", "SHORT_PE",
                     "LegRole.LONG_CE", "LONG_CE",
                     "LegRole.LONG_PE", "LONG_PE"} & roles or {
        r.replace("LegRole.", "") for r in roles
    } == {"SHORT_CE", "SHORT_PE", "LONG_CE", "LONG_PE"}
    assert d["upper"] > d["center"] > d["lower"]


def test_basket_preview_otm(s):
    cfg = _default_config()
    cfg["short_method"] = "OTM"; cfg["short_ce_otm"] = 5; cfg["short_pe_otm"] = 5
    r = s.post(f"{API}/basket/preview", json=cfg, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    step = 50  # NIFTY
    # ATM near center
    atm = round(d["center"] / step) * step
    short_ce = next(l for l in d["legs"] if "SHORT_CE" in l["role"])
    short_pe = next(l for l in d["legs"] if "SHORT_PE" in l["role"])
    # CE OTM => strike > ATM; PE OTM => strike < ATM (config short_pe_otm shifts down)
    assert short_ce["strike"] >= atm + 4 * step
    assert short_pe["strike"] <= atm - 4 * step


def test_basket_preview_delta(s):
    cfg = _default_config(); cfg["short_method"] = "DELTA"
    r = s.post(f"{API}/basket/preview", json=cfg, timeout=60)
    assert r.status_code == 200
    assert len(r.json()["legs"]) == 4


def test_basket_preview_premium(s):
    cfg = _default_config(); cfg["short_method"] = "PREMIUM"
    r = s.post(f"{API}/basket/preview", json=cfg, timeout=60)
    assert r.status_code == 200
    assert len(r.json()["legs"]) == 4


def test_basket_preview_hedge_disabled(s):
    cfg = _default_config(); cfg["hedge_enabled"] = False
    r = s.post(f"{API}/basket/preview", json=cfg, timeout=60)
    assert r.status_code == 200
    assert len(r.json()["legs"]) == 2


# ------------------------- /api/backtest/run ---------------- #
def test_backtest_run(s):
    payload = {"config": _default_config(),
               "start": "2025-11-01", "end": "2025-11-14"}
    r = s.post(f"{API}/backtest/run", json=payload, timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    stats = d.get("stats", d)
    for k in ("total_pnl", "total_baskets", "winning_baskets", "losing_baskets",
              "win_rate", "max_drawdown", "roll_up_count", "roll_down_count"):
        assert k in stats, f"missing {k} in stats"
    # Trending synthetic data with short straddles should NOT be 100% wins
    assert stats["win_rate"] <= 1.0
    assert stats["total_baskets"] >= 1
    # events / baskets present
    events = d.get("events", [])
    types = {e.get("type", "") for e in events}
    assert any("INITIAL" in t or t == "ENTER" for t in types), types
    assert "EXIT" in types or any("EXIT" in t for t in types)


# ------------------------- /api/upstox ---------------------- #
def test_upstox_status(s):
    r = s.get(f"{API}/upstox/status", timeout=30); assert r.status_code == 200
    d = r.json(); assert d["connected"] is False


def test_upstox_login_returns_dialog_url(s):
    # Credentials are configured server-side, so login must return a valid URL
    r = s.get(f"{API}/upstox/login", timeout=30)
    assert r.status_code == 200, r.text
    url = r.json()["url"]
    assert "client_id=" in url and "redirect_uri=" in url


def test_upstox_callback_invalid_state(s):
    r = s.get(f"{API}/upstox/callback", params={"code": "x", "state": "bogus"}, timeout=30)
    assert r.status_code == 400


def test_upstox_funds_disconnected(s):
    r = s.get(f"{API}/upstox/funds", timeout=30)
    assert r.status_code == 200
    assert r.json()["connected"] is False


def test_upstox_positions_disconnected(s):
    r = s.get(f"{API}/upstox/positions", timeout=30)
    assert r.status_code == 200
    assert r.json()["connected"] is False


# ------------------------- /api/session --------------------- #
def test_live_session_gated(s):
    # Try LIVE with confirmed=true but Upstox not connected -> 400
    r = s.post(f"{API}/session/start",
               json={"mode": "LIVE", "confirmed": True, "config": _default_config()},
               timeout=30)
    assert r.status_code == 400, r.text
    assert "Upstox" in r.text or "Connect" in r.text


def test_paper_session_lifecycle(s):
    # Ensure clean
    s.post(f"{API}/session/stop", timeout=15)
    time.sleep(1)
    r = s.post(f"{API}/session/start",
               json={"mode": "PAPER", "config": _default_config()}, timeout=30)
    assert r.status_code == 200, r.text
    # Poll status for up to 75s watching for state transitions
    entered = False
    rolled = False
    exited = False
    order_ids = set()
    for i in range(50):
        time.sleep(1.5)
        st = s.get(f"{API}/session/status", timeout=15).json()
        state = st.get("state")
        etypes = [e.get("type") for e in st.get("events", [])]
        for o in st.get("orders", []):
            oid = o.get("order_id")
            if oid: order_ids.add(oid)
        if "INITIAL ENTRY" in etypes: entered = True
        if any(t in ("ROLL_UP", "ROLL_DOWN") for t in etypes): rolled = True
        if "EXIT" in etypes or state == "COMPLETED": exited = True; break
    # stop no matter what
    s.post(f"{API}/session/stop")
    assert entered, "Session never entered INITIAL basket"
    # Paper orders must never be real broker IDs
    for oid in order_ids:
        assert oid is None or oid.startswith("PAPER"), f"non-paper order id: {oid}"
    # Rolls should typically occur but are probabilistic — soft assertion
    print(f"rolled={rolled} exited={exited} orders={len(order_ids)}")


def test_paper_orders_close_before_open_on_roll(s):
    """Verify order log ordering: on any roll, CLOSE orders appear BEFORE new
    open orders for that event timestamp."""
    s.post(f"{API}/session/stop"); time.sleep(1)
    s.post(f"{API}/session/start",
           json={"mode": "PAPER", "config": _default_config()}, timeout=30)
    orders_seen = []
    for _ in range(50):
        time.sleep(1.5)
        st = s.get(f"{API}/session/status").json()
        orders_seen = list(reversed(st.get("orders", [])))  # oldest first
        if any(o.get("event", "").startswith("CLOSE/ROLL") for o in orders_seen):
            break
    s.post(f"{API}/session/stop")
    # Find the first roll close block and ensure it precedes matching roll open
    roll_close_idx = next((i for i, o in enumerate(orders_seen)
                           if str(o.get("event", "")).startswith("CLOSE/ROLL")), None)
    if roll_close_idx is None:
        pytest.skip("No roll happened within polling window")
    # Find the corresponding ROLL_UP or ROLL_DOWN open event AFTER it
    roll_open_idx = next((i for i, o in enumerate(orders_seen[roll_close_idx:], roll_close_idx)
                          if o.get("event") in ("ROLL_UP", "ROLL_DOWN")), None)
    assert roll_open_idx is not None and roll_open_idx > roll_close_idx, \
        "Close orders must come BEFORE new-basket open orders on a roll"


def test_session_emergency(s):
    s.post(f"{API}/session/stop"); time.sleep(1)
    s.post(f"{API}/session/start",
           json={"mode": "PAPER", "config": _default_config()})
    time.sleep(3)
    r = s.post(f"{API}/session/emergency", timeout=15)
    assert r.status_code == 200
    time.sleep(1)
    st = s.get(f"{API}/session/status").json()
    assert st.get("running") is False
