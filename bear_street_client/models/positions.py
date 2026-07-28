from typing import Optional, Any
from dataclasses import dataclass, asdict


@dataclass(kw_only=True)
class PositionsData:
    exchange: Optional[str] = None
    scrip_token: Optional[int] = None
    product_type: Optional[str] = None
    symbol: Optional[str] = None
    series: Optional[str] = None
    instrument: Optional[str] = None
    expiry_date: Optional[str] = None
    strike_price: Optional[float] = None
    option_type: Optional[str] = None
    buy_quantity: Optional[int] = None
    avg_buy_price: Optional[float] = None
    buy_value: Optional[float] = None
    sell_quantity: Optional[int] = None
    avg_sell_price: Optional[float] = None
    sell_value: Optional[float] = None
    net_quantity: Optional[int] = None
    net_price: Optional[float] = None
    net_value: Optional[float] = None
    ltp: Optional[float] = None
    close_price: Optional[float] = None
    multiplier: Optional[int] = None
    mtm: Optional[float] = None

    def get_dict(self):
        return asdict(self)

    @staticmethod
    def parse_list(response):
        return [PositionsData(**item) for item in response.get("data", [])]


@dataclass(kw_only=True)
class PositionsResponse:
    status: str
    code: Optional[str] = None
    message: Optional[str] = None
    data: Optional[Any] = None

    def get_dict(self):
        return asdict(self)
