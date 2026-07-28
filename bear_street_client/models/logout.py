from dataclasses import dataclass, asdict
from typing import Optional


@dataclass(kw_only=True)
class LogoutData:
    status: Optional[str] = None
    code: Optional[str] = None
    message: Optional[str] = None

    def get_dict(self):
        return asdict(self)
