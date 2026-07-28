from typing import Optional, Any, Dict, List
from dataclasses import dataclass, asdict, field


@dataclass(kw_only=True)
class TradeData:
    order_id: Optional[str] = None
    exchange: Optional[str] = None
    scrip_token: Optional[int] = None
    trade_no: Optional[str] = None
    exchange_order_no: Optional[str] = None
    transaction_type: Optional[str] = None
    product_type: Optional[str] = None
    order_type: Optional[str] = None
    trade_quantity: Optional[int] = None
    trade_price: Optional[float] = None
    symbol: Optional[str] = None
    series: Optional[str] = None
    instrument: Optional[str] = None
    expiry_date: Optional[str] = None
    strike_price: Optional[float] = None
    option_type: Optional[str] = None
    trade_timestamp: Optional[str] = None
    initiated_by: Optional[str] = None
    modified_by: Optional[str] = None
    order_identifier: Optional[str] = None

    def get_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(kw_only=True)
class TradesBookData:
    order_id: Optional[str] = None
    exchange: Optional[str] = None
    scrip_token: Optional[int] = None
    trade_no: Optional[str] = None
    exchange_order_no: Optional[str] = None
    transaction_type: Optional[str] = None
    product_type: Optional[str] = None
    order_type: Optional[str] = None
    trade_quantity: Optional[int] = None
    trade_price: Optional[float] = None
    symbol: Optional[str] = None
    series: Optional[str] = None
    instrument: Optional[str] = None
    expiry_date: Optional[str] = None
    strike_price: Optional[float] = None
    option_type: Optional[str] = None
    trade_timestamp: Optional[str] = None
    initiated_by: Optional[str] = None
    modified_by: Optional[str] = None
    order_identifier: Optional[str] = None

    def get_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}

    @staticmethod
    def parse_list(response):
        items = response.get("data", [])
        if isinstance(items, dict):
            items = [items]
        return [TradesBookData(**item) for item in items]


@dataclass(kw_only=True)
class TradesBookResponse:
    status: str
    code: Optional[str] = None
    message: Optional[str] = None
    data: Optional[Any] = None
    metadata: Optional[Dict[str, Any]] = None

    def get_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}
