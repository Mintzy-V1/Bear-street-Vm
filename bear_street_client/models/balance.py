from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict


@dataclass(kw_only=True)
class BalanceData:
    equity: Optional[Dict[str, Any]] = None
    commodity: Optional[Dict[str, Any]] = None
    currency: Optional[Dict[str, Any]] = None

    def get_dict(self):
        return asdict(self)


@dataclass(kw_only=True)
class BalanceResponse:
    status: str
    code: Optional[str] = None
    message: Optional[str] = None
    data: Optional[BalanceData] = None

    def get_dict(self):
        return asdict(self)
