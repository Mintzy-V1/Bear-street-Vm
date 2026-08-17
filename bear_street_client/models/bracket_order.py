from typing import Optional, Any
from dataclasses import dataclass, asdict

from .new_order import ScripInfo


@dataclass(kw_only=True)
class MainLeg:
    order_type: str = "RL"
    quantity: int = 0
    price: float = 0
    trigger_price: Optional[float] = None
    traded_quantity: Optional[int] = None

    def get_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(kw_only=True)
class StoplossLeg:
    legs: Optional[Any] = None
    trail: Optional[Any] = None

    def get_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(kw_only=True)
class ProfitLeg:
    legs: Optional[Any] = None

    def get_dict(self):
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass(kw_only=True)
class FieldsModified:
    main_leg_price: bool = False
    main_leg_qty: bool = False
    stoploss_leg_price: bool = False
    stoploss_trail_price: bool = False
    profit_leg_price: bool = False

    def get_dict(self):
        return asdict(self)


@dataclass(kw_only=True)
class BracketOrderRequest:
    scrip_info: ScripInfo
    transaction_type: str
    main_leg: Optional[MainLeg] = None
    stoploss_leg: Optional[StoplossLeg] = None
    profit_leg: Optional[ProfitLeg] = None
    order_identifier: Optional[str] = None
    part_code: Optional[str] = None
    algo_id: Optional[str] = None
    strategy_id: Optional[str] = None
    vender_code: Optional[str] = None

    def get_dict(self):
        d = {"scrip_info": self.scrip_info.get_dict(), "transaction_type": self.transaction_type}
        if self.main_leg:
            d["main_leg"] = self.main_leg.get_dict()
        if self.stoploss_leg:
            d["stoploss_leg"] = self.stoploss_leg.get_dict()
        if self.profit_leg:
            d["profit_leg"] = self.profit_leg.get_dict()
        for k in ("order_identifier", "part_code", "algo_id", "strategy_id", "vender_code"):
            v = getattr(self, k, None)
            if v is not None:
                d[k] = v
        return d


@dataclass(kw_only=True)
class BracketOrderRequestForModify:
    main_leg: Optional[MainLeg] = None
    stoploss_leg: Optional[StoplossLeg] = None
    profit_leg: Optional[ProfitLeg] = None
    fields_modified: Optional[FieldsModified] = None

    def get_dict(self):
        d = {}
        if self.main_leg:
            d["main_leg"] = self.main_leg.get_dict()
        if self.stoploss_leg:
            d["stoploss_leg"] = self.stoploss_leg.get_dict()
        if self.profit_leg:
            d["profit_leg"] = self.profit_leg.get_dict()
        if self.fields_modified:
            d["fields_modified"] = self.fields_modified.get_dict()
        return d


@dataclass(kw_only=True)
class BracketOrderResponse:
    status: str
    code: Optional[str] = None
    message: Optional[str] = None
    data: Optional[Any] = None

    def get_dict(self):
        return asdict(self)
