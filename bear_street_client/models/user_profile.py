from typing import Optional, Any
from dataclasses import dataclass, asdict


@dataclass(kw_only=True)
class UserProfileData:
    user_name: Optional[str] = None
    login_time: Optional[str] = None
    exchanges: Optional[Any] = None
    product_types: Optional[Any] = None
    mpin_enabled: Optional[bool] = None
    fingerprint_enabled: Optional[bool] = None
    others: Optional[Any] = None

    def get_dict(self):
        return asdict(self)


@dataclass(kw_only=True)
class UserProfileResponse:
    status: str
    code: Optional[str] = None
    message: Optional[str] = None
    data: Optional[UserProfileData] = None

    def get_dict(self):
        return asdict(self)
