from typing import Optional, Any, Dict, List
from dataclasses import dataclass, asdict, field


@dataclass(kw_only=True)
class OrderBookRow:
    order_id: Optional[str] = None
    exchange: Optional[str] = None
    scrip_token: Optional[int] = None
    transaction_type: Optional[str] = None
    product_type: Optional[str] = None
    order_type: Optional[str] = None
    quantity: Optional[int] = None
    price: Optional[float] = None
    trigger_price: Optional[float] = None
    disclosed_quantity: Optional[int] = None
    validity: Optional[str] = None
    status: Optional[str] = None
    traded_quantity: Optional[int] = None
    average_price: Optional[float] = None
    order_timestamp: Optional[str] = None
    symbol: Optional[str] = None
    series: Optional[str] = None
    expiry_date: Optional[str] = None
    strike_price: Optional[float] = None
    option_type: Optional[str] = None
    order_identifier: Optional[str] = None
    rejection_reason: Optional[str] = None

    def get_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(kw_only=True)
class OrdersBookResponse:
    status: str
    code: Optional[str] = None
    message: Optional[str] = None
    data: Optional[Any] = None
    metadata: Optional[Dict[str, Any]] = None

    def get_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}
