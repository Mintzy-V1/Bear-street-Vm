from typing import Optional, Any
from dataclasses import dataclass, asdict


@dataclass(kw_only=True)
class CancelOrderData:
    pass

    def get_dict(self):
        return asdict(self)


@dataclass(kw_only=True)
class CancelOrderResponse:
    status: str
    code: Optional[str] = None
    message: Optional[str] = None
    data: Optional[Any] = None

    def get_dict(self):
        return asdict(self)
