from typing import Optional, Any, Dict
from dataclasses import dataclass, asdict


@dataclass(kw_only=True)
class ScripInfo:
    exchange: str
    scrip_token: Optional[int] = None
    symbol: Optional[str] = None
    series: Optional[str] = None
    expiry_date: Optional[str] = None
    strike_price: Optional[float] = None
    option_type: Optional[str] = None

    def get_dict(self):
        return asdict(self)


@dataclass(kw_only=True)
class NewOrderRequest:
    scrip_info: ScripInfo
    transaction_type: str
    product_type: str
    order_type: str
    quantity: int
    price: float = 0
    trigger_price: Optional[float] = None
    disclosed_quantity: Optional[int] = None
    validity: str = "DAY"
    validity_days: Optional[int] = None
    is_amo: bool = False
    order_identifier: Optional[str] = None
    part_code: Optional[str] = None
    algo_id: Optional[str] = None
    strategy_id: Optional[str] = None
    vender_code: Optional[str] = None

    def get_dict(self):
        d = asdict(self)
        d["scrip_info"] = self.scrip_info.get_dict()
        return {k: v for k, v in d.items() if v is not None}


@dataclass(kw_only=True)
class NewOrderData:
    pass

    def get_dict(self):
        return asdict(self)


@dataclass(kw_only=True)
class NewOrderResponse:
    status: str
    code: Optional[str] = None
    message: Optional[str] = None
    data: Optional[Any] = None

    def get_dict(self):
        return asdict(self)
