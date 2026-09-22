"""Bear Street live order pricing: band-aware RL limit orders (hardcoded config)."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Optional

# ---------------------------------------------------------------------------
# Hardcoded production defaults — edit here before VM deploy (no env vars).
# ---------------------------------------------------------------------------
BEAR_STREET_ORDER_MODE = "limit"
BEAR_STREET_LIMIT_BUY_BPS = 5.0
BEAR_STREET_LIMIT_SELL_BPS = 5.0
BEAR_STREET_LIMIT_BPS_CAP = 200.0
BEAR_STREET_DEFAULT_BAND_PCT = 0.10
BEAR_STREET_RESPECT_NSE_BAND = True
BEAR_STREET_SYMBOL_BAND_PCT: dict[str, float] = {}


@dataclass(frozen=True)
class BearStreetOrderPricingConfig:
    mode: str = "limit"
    buy_bps: float = 5.0
    sell_bps: float = 5.0
    bps_cap: float = 200.0
    default_band_pct: float = 0.10
    respect_nse_band: bool = True
    symbol_band_pct: Mapping[str, float] = None

    def __post_init__(self):
        object.__setattr__(self, "mode", (self.mode or "limit").strip().lower())
        object.__setattr__(
            self,
            "symbol_band_pct",
            dict(self.symbol_band_pct or {}),
        )


_CONFIG: Optional[BearStreetOrderPricingConfig] = None


def get_bear_street_order_pricing_config() -> BearStreetOrderPricingConfig:
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    _CONFIG = BearStreetOrderPricingConfig(
        mode=BEAR_STREET_ORDER_MODE,
        buy_bps=BEAR_STREET_LIMIT_BUY_BPS,
        sell_bps=BEAR_STREET_LIMIT_SELL_BPS,
        bps_cap=BEAR_STREET_LIMIT_BPS_CAP,
        default_band_pct=BEAR_STREET_DEFAULT_BAND_PCT,
        respect_nse_band=BEAR_STREET_RESPECT_NSE_BAND,
        symbol_band_pct=dict(BEAR_STREET_SYMBOL_BAND_PCT),
    )
    return _CONFIG


def log_bear_street_order_pricing_config() -> None:
    cfg = get_bear_street_order_pricing_config()
    print(
        "[BEAR-STREET-ORDER] limit-only (hardcoded) "
        f"buy_bps={cfg.buy_bps} sell_bps={cfg.sell_bps} "
        f"bps_cap={cfg.bps_cap} default_band_pct={cfg.default_band_pct:.2%} "
        f"respect_nse_band={cfg.respect_nse_band} "
        f"symbol_band_overrides={len(cfg.symbol_band_pct)}"
    )


def normalize_symbol(symbol: str) -> str:
    return (symbol or "").upper().replace("-EQ", "").strip()


def reference_ltp_from_order(order_req: Any) -> Optional[float]:
    meta = getattr(order_req, "metadata", None) or {}
    if isinstance(meta, dict):
        for key in ("curr_price", "ltp", "price"):
            try:
                val = float(meta.get(key) or 0)
                if val > 0:
                    return val
            except (TypeError, ValueError):
                continue
    price = getattr(order_req, "price", None)
    try:
        val = float(price or 0)
        if val > 0:
            return val
    except (TypeError, ValueError):
        pass
    return None


def round_to_nse_tick(price: float) -> float:
    p = float(price)
    if p <= 0:
        return 0.0
    if p < 250:
        tick = 0.05
    elif p < 1000:
        tick = 0.05
    elif p < 5000:
        tick = 0.10
    elif p < 10000:
        tick = 0.10
    else:
        tick = 0.50
    return round(round(p / tick) * tick, 2)


def round_to_symbol_tick(price: float, tick: Optional[float], side: str = "") -> float:
    """Round to the broker's per-symbol tick (in rupees).

    Direction-aware: round UP for buys, DOWN for sells so the limit stays
    aggressive enough to fill. Falls back to the generic NSE table when the
    symbol tick is unknown.
    """
    p = float(price)
    if p <= 0:
        return 0.0
    t = float(tick) if tick and float(tick) > 0 else None
    if t is None:
        return round_to_nse_tick(p)
    if _side_is_buy(side):
        return round(math.ceil(p / t) * t, 2)
    return round(math.floor(p / t) * t, 2)


def band_pct_for_symbol(symbol: str, cfg: Optional[BearStreetOrderPricingConfig] = None) -> float:
    cfg = cfg or get_bear_street_order_pricing_config()
    sym = normalize_symbol(symbol)
    if sym in cfg.symbol_band_pct:
        return float(cfg.symbol_band_pct[sym])
    return float(cfg.default_band_pct)


def _side_is_buy(side: str) -> bool:
    s = (side or "").upper().replace("_", "").replace(" ", "")
    return s in ("BUY", "LONG", "BUYCOVER", "COVER")


def effective_bps(side: str, cfg: Optional[BearStreetOrderPricingConfig] = None) -> float:
    cfg = cfg or get_bear_street_order_pricing_config()
    raw = cfg.buy_bps if _side_is_buy(side) else cfg.sell_bps
    return min(max(float(raw), 0.0), float(cfg.bps_cap))


def max_allowed_bps_from_ltp(
    side: str,
    ltp: float,
    band_pct: float,
    prev_close: Optional[float] = None,
) -> float:
    if ltp <= 0 or band_pct <= 0:
        return 0.0
    ref = float(prev_close) if prev_close and prev_close > 0 else float(ltp)
    upper = ref * (1.0 + band_pct)
    lower = ref * (1.0 - band_pct)
    if _side_is_buy(side):
        if ltp <= 0:
            return 0.0
        return max(0.0, (upper / ltp - 1.0) * 10000.0)
    if ltp <= 0:
        return 0.0
    return max(0.0, (1.0 - lower / ltp) * 10000.0)


def compute_limit_price(
    side: str,
    ltp: float,
    *,
    symbol: str = "",
    prev_close: Optional[float] = None,
    cfg: Optional[BearStreetOrderPricingConfig] = None,
    tick: Optional[float] = None,
) -> tuple[float, dict[str, Any]]:
    cfg = cfg or get_bear_street_order_pricing_config()
    if ltp <= 0:
        raise ValueError("reference LTP must be > 0 for limit pricing")

    band_pct = band_pct_for_symbol(symbol, cfg)
    bps = effective_bps(side, cfg)
    if cfg.respect_nse_band:
        bps = min(bps, max_allowed_bps_from_ltp(side, ltp, band_pct, prev_close))

    factor = 1.0 + (bps / 10000.0) if _side_is_buy(side) else 1.0 - (bps / 10000.0)
    raw = float(ltp) * factor

    ref = float(prev_close) if prev_close and prev_close > 0 else float(ltp)
    upper = ref * (1.0 + band_pct)
    lower = ref * (1.0 - band_pct)
    if cfg.respect_nse_band:
        if _side_is_buy(side):
            raw = min(raw, upper)
        else:
            raw = max(raw, lower)

    limit_price = round_to_symbol_tick(raw, tick, side if tick else "")
    if limit_price <= 0:
        raise ValueError(f"computed invalid limit price for {symbol} side={side} ltp={ltp}")

    details = {
        "ltp": float(ltp),
        "prev_close": float(prev_close) if prev_close else None,
        "band_pct": band_pct,
        "applied_bps": bps,
        "raw_limit": raw,
        "limit_price": limit_price,
        "tick": tick,
    }
    return limit_price, details
