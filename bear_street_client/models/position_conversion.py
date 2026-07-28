from typing import Optional, Any
from dataclasses import dataclass, asdict


@dataclass(kw_only=True)
class PositionConversionRequest:
    exchange: str
    scrip_token: int
    transaction_type: str
    quantity: int
    old_product_type: str
    new_product_type: str
    bo_order_id: Optional[str] = None

    def get_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(kw_only=True)
class PositionConversionResponse:
    status: str
    code: Optional[str] = None
    message: Optional[str] = None
    data: Optional[Any] = None

    def get_dict(self):
        return asdict(self)
