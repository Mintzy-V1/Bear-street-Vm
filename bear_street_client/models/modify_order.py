from typing import Optional, Any
from dataclasses import dataclass, asdict


@dataclass(kw_only=True)
class ModifyOrderRequest:
    order_type: str
    quantity: int
    traded_quantity: int
    price: float = 0
    trigger_price: Optional[float] = None
    disclosed_quantity: Optional[int] = None
    validity: str = "DAY"
    validity_days: Optional[int] = None

    def get_dict(self):
        return asdict(self)


@dataclass(kw_only=True)
class ModifyOrderData:
    pass

    def get_dict(self):
        return asdict(self)


@dataclass(kw_only=True)
class ModifyOrderResponse:
    status: str
    code: Optional[str] = None
    message: Optional[str] = None
    data: Optional[Any] = None

    def get_dict(self):
        return asdict(self)
