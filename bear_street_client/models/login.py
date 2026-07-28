from typing import Optional, List, Any, Dict
from dataclasses import dataclass, asdict


@dataclass(kw_only=True)
class LoginData:
    access_token: str
    broadcast_access_token: Optional[str] = None
    user_name: Optional[str] = None
    login_time: Optional[str] = None
    exchanges: Optional[List[str]] = None
    bcastExchanges: Optional[List[str]] = None
    product_types: Optional[List[str]] = None
    product_types_exchange: Optional[Dict[str, Any]] = None
    mpin_enabled: Optional[bool] = None
    fingerprint_enabled: Optional[bool] = None
    others: Optional[Dict[str, Any]] = None

    def get_dict(self):
        return asdict(self)


@dataclass(kw_only=True)
class LoginRequest:
    user_id: str
    password: str
    second_auth: str
    api_key: str
    source: str = "WEBAPI"
    login_type: str = "PASSWORD"

    def get_dict(self):
        return asdict(self)


@dataclass(kw_only=True)
class LoginResponse:
    status: str
    code: Optional[str] = None
    message: Optional[str] = None
    data: Optional[LoginData] = None

    def get_dict(self):
        return asdict(self)
