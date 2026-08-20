import os
from typing import Any, Dict, Optional, Tuple

BROKER_ANGEL = "angel"
BROKER_TRADEX = "tradex"
BROKER_BEAR_STREET = "bear_street"
SUPPORTED_BROKERS = {BROKER_ANGEL, BROKER_TRADEX, BROKER_BEAR_STREET}

DEFAULT_TRADEX_BASE_URL = "https://tradex.saral-info.com:30001/TradeXApi/v1"
DEFAULT_TRADEX_WEBSOCKET_URL = "wss://tradex.saral-info.com:30001"
DEFAULT_BEAR_STREET_BASE_URL = "https://connectorservices.odinconnector.co.in/interactive"


def normalize_broker_type(broker_type: Optional[str]) -> str:
    if not broker_type:
        return BROKER_BEAR_STREET
    bt = broker_type.lower().strip()
    return bt if bt in SUPPORTED_BROKERS else BROKER_BEAR_STREET


def create_broker_connector(broker_type: Optional[str] = None, require_totp: bool = True):
    bt = normalize_broker_type(broker_type)
    if bt == BROKER_TRADEX:
        from broker_tradex import BrokerConnector
        return BrokerConnector(require_totp=require_totp)
    elif bt == BROKER_ANGEL:
        from broker_angle import BrokerConnector
        return BrokerConnector(require_totp=require_totp)
    from broker_bear_street import BrokerConnector
    return BrokerConnector(require_totp=require_totp)


def set_broker_env(broker_config: Dict[str, Any]) -> str:
    bt = normalize_broker_type(broker_config.get("broker_type"))
    if bt == BROKER_TRADEX:
        os.environ["TRADEX_APP_KEY"] = broker_config.get("api_key", "")
        os.environ["TRADEX_SECRET_KEY"] = broker_config.get("password", "")
        os.environ["TRADEX_CLIENT_ID"] = broker_config.get("client_code", "")
        os.environ["TRADEX_USER_ID"] = (
            broker_config.get("user_id_broker")
            or broker_config.get("user_id")
            or broker_config.get("client_code", "")
        )
        os.environ["TRADEX_BASE_URL"] = broker_config.get("base_url") or DEFAULT_TRADEX_BASE_URL
        os.environ["TRADEX_WEBSOCKET_URL"] = (
            broker_config.get("websocket_url") or DEFAULT_TRADEX_WEBSOCKET_URL
        )
    elif bt == BROKER_ANGEL:
        os.environ["ANGEL_API_KEY"] = broker_config.get("api_key", "")
        os.environ["ANGEL_CLIENT_CODE"] = broker_config.get("client_code", "")
        os.environ["ANGEL_PASSWORD"] = broker_config.get("password", "")
        if broker_config.get("totp") is not None:
            os.environ["ANGEL_TOTP"] = broker_config.get("totp") or ""
    else:
        os.environ["BEAR_STREET_API_KEY"] = broker_config.get("api_key", "")
        os.environ["BEAR_STREET_USER_ID"] = broker_config.get("user_id_broker") or broker_config.get("client_code", "")
        os.environ["BEAR_STREET_PASSWORD"] = broker_config.get("password", "")
        os.environ["BEAR_STREET_SECOND_AUTH"] = broker_config.get("second_auth") or ""
        os.environ["BEAR_STREET_SECOND_AUTH_TYPE"] = broker_config.get("second_auth_type") or ""
        os.environ["BEAR_STREET_LOGIN_TYPE"] = broker_config.get("login_type") or "PASSWORD"
        os.environ["BEAR_STREET_SOURCE"] = broker_config.get("source", "WEBAPI")
        os.environ["BEAR_STREET_BASE_URL"] = broker_config.get("base_url") or DEFAULT_BEAR_STREET_BASE_URL
    return bt


def clear_broker_env(broker_type: Optional[str] = None) -> None:
    bt = normalize_broker_type(broker_type)
    if bt == BROKER_TRADEX:
        for key in [
            "TRADEX_APP_KEY", "TRADEX_SECRET_KEY", "TRADEX_CLIENT_ID",
            "TRADEX_USER_ID", "TRADEX_BASE_URL", "TRADEX_WEBSOCKET_URL",
        ]:
            os.environ.pop(key, None)
    elif bt == BROKER_ANGEL:
        for key in ["ANGEL_API_KEY", "ANGEL_CLIENT_CODE", "ANGEL_PASSWORD", "ANGEL_TOTP"]:
            os.environ.pop(key, None)
    else:
        for key in [
            "BEAR_STREET_API_KEY", "BEAR_STREET_USER_ID", "BEAR_STREET_PASSWORD",
            "BEAR_STREET_SECOND_AUTH", "BEAR_STREET_SECOND_AUTH_TYPE", "BEAR_STREET_LOGIN_TYPE",
            "BEAR_STREET_SOURCE", "BEAR_STREET_BASE_URL",
        ]:
            os.environ.pop(key, None)


def broker_config_from_session(session_data: Dict[str, Any]) -> Dict[str, Any]:
    bt = normalize_broker_type(session_data.get("broker_type"))
    if bt in (BROKER_TRADEX, BROKER_ANGEL):
        return {
            "broker_type": bt,
            "api_key": session_data.get("api_key"),
            "client_code": session_data.get("client_code"),
            "password": session_data.get("password"),
            "user_id_broker": session_data.get("user_id_broker"),
            "base_url": session_data.get("base_url"),
            "websocket_url": session_data.get("websocket_url"),
            "broker_session": session_data.get("broker_session"),
            "totp": session_data.get("totp"),
        }
    return {
        "broker_type": bt,
        "api_key": session_data.get("api_key"),
        "client_code": session_data.get("client_code") or session_data.get("user_id"),
        "password": session_data.get("password"),
        "second_auth": session_data.get("second_auth", ""),
        "second_auth_type": session_data.get("second_auth_type") or "",
        "login_type": session_data.get("login_type") or "PASSWORD",
        "source": session_data.get("source", "WEBAPI"),
        "user_id_broker": session_data.get("user_id_broker") or session_data.get("user_id"),
        "base_url": session_data.get("base_url") or DEFAULT_BEAR_STREET_BASE_URL,
        "broker_session": session_data.get("broker_session"),
    }


def requires_totp(broker_type: Optional[str]) -> bool:
    return normalize_broker_type(broker_type) == BROKER_ANGEL


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
        need_totp = requires_totp(bt) and not restore
        broker = create_broker_connector(bt, require_totp=need_totp)
        if restore and cfg.get("broker_session"):
            session = broker.restore_session(cfg["broker_session"])
        else:
            session = broker.get_session()
        return broker, session
    finally:
        clear_broker_env(bt)


def create_ltp_stream(broker, on_tick):
    bt = normalize_broker_type(getattr(broker, "broker_type", BROKER_BEAR_STREET))
    if bt == BROKER_TRADEX:
        from live_ltp_ws_tradex import TradeXLTPPoller
        return TradeXLTPPoller(broker, on_tick)
    if bt == BROKER_BEAR_STREET:
        from bear_street_ltp_poller import BearStreetLTPPoller
        return BearStreetLTPPoller(broker, on_tick)
    from live_ltp_ws import LiveLTPStream
    return LiveLTPStream(broker, on_tick)
