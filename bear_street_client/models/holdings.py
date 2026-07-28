from typing import Optional, Any, List
from dataclasses import dataclass, asdict, field


@dataclass(kw_only=True)
class HoldingsData:
    isin: Optional[str] = None
    security_info: Optional[List[Any]] = None
    total_free: Optional[int] = None
    dp_free: Optional[int] = None
    pool_free: Optional[int] = None
    t1_quantity: Optional[int] = None
    average_price: Optional[float] = None
    last_price: Optional[float] = None
    pnl: Optional[float] = None
    current_value: Optional[float] = None
    inv_value: Optional[float] = None
    product: Optional[str] = None
    collateral_quantity: Optional[int] = None
    collateral_value: Optional[float] = None

    def get_dict(self):
        return asdict(self)


@dataclass(kw_only=True)
class HoldingsResponse:
    status: str
    code: Optional[str] = None
    message: Optional[str] = None
    data: Optional[Any] = None

    def get_dict(self):
        return asdict(self)
