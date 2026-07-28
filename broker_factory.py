import os
from typing import Any, Dict, Optional, Tuple

BROKER_BEAR_STREET = "bear_street"
SUPPORTED_BROKERS = {BROKER_BEAR_STREET}

DEFAULT_BEAR_STREET_BASE_URL = "http://localhost:3100"


def normalize_broker_type(broker_type: Optional[str]) -> str:
    bt = (broker_type or BROKER_BEAR_STREET).lower().strip()
    return bt if bt in SUPPORTED_BROKERS else BROKER_BEAR_STREET


def create_broker_connector(broker_type: Optional[str] = None, require_totp: bool = True):
    bt = normalize_broker_type(broker_type)
    from broker_bear_street import BrokerConnector
    return BrokerConnector(require_totp=require_totp)


def set_broker_env(broker_config: Dict[str, Any]) -> str:
    bt = normalize_broker_type(broker_config.get("broker_type"))
    os.environ["BEAR_STREET_API_KEY"] = broker_config.get("api_key", "")
    os.environ["BEAR_STREET_USER_ID"] = broker_config.get("user_id", "")
    os.environ["BEAR_STREET_PASSWORD"] = broker_config.get("password", "")
    os.environ["BEAR_STREET_SECOND_AUTH"] = broker_config.get("second_auth", "")
    os.environ["BEAR_STREET_SOURCE"] = broker_config.get("source", "WEBAPI")
    os.environ["BEAR_STREET_BASE_URL"] = broker_config.get("base_url") or DEFAULT_BEAR_STREET_BASE_URL
    return bt


def clear_broker_env(broker_type: Optional[str] = None) -> None:
    for key in [
        "BEAR_STREET_API_KEY", "BEAR_STREET_USER_ID", "BEAR_STREET_PASSWORD",
        "BEAR_STREET_SECOND_AUTH", "BEAR_STREET_SOURCE", "BEAR_STREET_BASE_URL",
    ]:
        os.environ.pop(key, None)


def broker_config_from_session(session_data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "broker_type": session_data.get("broker_type", BROKER_BEAR_STREET),
        "api_key": session_data.get("api_key"),
        "user_id": session_data.get("user_id"),
        "password": session_data.get("password"),
        "second_auth": session_data.get("second_auth"),
        "source": session_data.get("source", "WEBAPI"),
        "base_url": session_data.get("base_url"),
        "broker_session": session_data.get("broker_session"),
    }


def requires_totp(broker_type: Optional[str]) -> bool:
    return False


def connect_broker(
    broker_config: Dict[str, Any],
    *,
    totp: Optional[str] = None,
    restore: bool = False,
) -> Tuple[Any, Dict[str, Any]]:
    cfg = dict(broker_config)
    if totp is not None:
        cfg["totp"] = totp
    bt = set_broker_env(cfg)
    try:
        broker = create_broker_connector(bt, require_totp=False)
        if restore and cfg.get("broker_session"):
            session = broker.restore_session(cfg["broker_session"])
        else:
            session = broker.get_session()
        return broker, session
    finally:
        clear_broker_env(bt)
