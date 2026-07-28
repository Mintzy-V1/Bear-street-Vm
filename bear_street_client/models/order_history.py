from typing import Optional, Any, Dict, List
from dataclasses import dataclass, asdict


@dataclass(kw_only=True)
class OrderHistoryResponse:
    status: str
    code: Optional[str] = None
    message: Optional[str] = None
    data: Optional[Any] = None
    metadata: Optional[Dict[str, Any]] = None

    def get_dict(self):
        return asdict(self)
