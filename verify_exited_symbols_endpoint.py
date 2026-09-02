import os
import sys
import time
import types
from datetime import datetime, timezone


# Keep this endpoint verification focused and offline except for Mongo itself.
# api_server imports these modules, but the exited-symbols endpoint does not use them.
fake_broker_angle = types.ModuleType("broker_angle")
fake_broker_angle.BrokerConnector = type("BrokerConnector", (), {})
sys.modules["broker_angle"] = fake_broker_angle

fake_alerts = types.ModuleType("alerts")
fake_alerts.AlertManager = type("AlertManager", (), {})
sys.modules["alerts"] = fake_alerts

fake_orderbook = types.ModuleType("orderbook")
fake_orderbook.fetch_todays_intraday_orders = lambda *args, **kwargs: []
sys.modules["orderbook"] = fake_orderbook

fake_broker_factory = types.ModuleType("broker_factory")
fake_broker_factory.BROKER_TRADEX = "tradex"
fake_broker_factory.BROKER_ANGEL = "angel"
fake_broker_factory.BROKER_BEAR_STREET = "bear_street"
fake_broker_factory.DEFAULT_TRADEX_BASE_URL = ""
fake_broker_factory.DEFAULT_BEAR_STREET_BASE_URL = ""
fake_broker_factory.broker_config_from_session = lambda *args, **kwargs: {}
fake_broker_factory.connect_broker = lambda *args, **kwargs: None
fake_broker_factory.requires_totp = lambda *args, **kwargs: False
fake_broker_factory.normalize_broker_type = lambda broker=None: broker or "bear_street"
sys.modules["broker_factory"] = fake_broker_factory

fake_trading_state = types.ModuleType("trading_state")
fake_trading_state.trading_snapshot = {}
sys.modules["trading_state"] = fake_trading_state

fake_trading_snapshot = types.ModuleType("trading_snapshot")
fake_trading_snapshot.insert_trading_snapshot = lambda *args, **kwargs: None
sys.modules["trading_snapshot"] = fake_trading_snapshot


class _FakeSessionManager:
    @staticmethod
    def stop_session(*args, **kwargs):
        return True

    @staticmethod
    def ensure_worker_stopped(*args, **kwargs):
        return True

    @staticmethod
    def start_session(*args, **kwargs):
        return None

    @staticmethod
    def get_session_status(*args, **kwargs):
        return {"running": False}

    @staticmethod
    def stop_simulation_session(*args, **kwargs):
        return True

    @staticmethod
    def read_pyramid_handoff_result(*args, **kwargs):
        return {}

    @staticmethod
    def clear_pyramid_handoff_result(*args, **kwargs):
        return None


fake_session_manager = types.ModuleType("session_manager")
fake_session_manager.SessionManager = _FakeSessionManager
sys.modules["session_manager"] = fake_session_manager

import api_server


def main():
    if not api_server.DB_CONNECTED or api_server.exited_symbols_collection is None:
        raise RuntimeError("MongoDB is not connected in api_server")

    session_id = os.environ.get(
        "VERIFY_EXITED_SYMBOLS_SESSION_ID",
        "session_verify_exited_symbols_endpoint",
    )
    symbol = os.environ.get("VERIFY_EXITED_SYMBOLS_SYMBOL", "VERIFYRMS")
    now_utc = datetime.now(timezone.utc).isoformat()

    fake_doc = {
        "session_id": session_id,
        "configuration_id": "verify_config_id",
        "symbol": symbol,
        "status": "EXITED",
        "position_status": "EXITED",
        "exit_reason": "RMS_TICKER_EXIT",
        "action_type": "COVER_SHORT",
        "entry_side": "SELL",
        "exit_side": "BUY",
        "qty": 12,
        "entry_price": 1133.0,
        "exit_price": 1145.05,
        "exit_realized_pnl": -144.6,
        "realized_pnl": -144.6,
        "unrealized_pnl": 0.0,
        "total_pnl": -144.6,
        "exit_actual_cycle": 1,
        "display_cycle": 2,
        "exit_order_id": "VERIFY-ORDER-1",
        "exit_order_status": "FILLED",
        "exit_time": "2026-09-03 10:35:00",
        "exit_time_utc": now_utc,
        "source": "endpoint_verification",
        "is_test_record": True,
        "updated_at": now_utc,
    }

    api_server.exited_symbols_collection.update_one(
        {"session_id": session_id, "symbol": symbol},
        {
            "$set": fake_doc,
            "$setOnInsert": {"created_at": now_utc},
        },
        upsert=True,
    )

    import asyncio

    response = asyncio.run(api_server.get_exited_symbols(session_id))
    rows = response.get("symbols") or []
    matched = [row for row in rows if row.get("symbol") == symbol]
    if not matched:
        raise AssertionError(f"Inserted symbol {symbol} was not returned by endpoint")

    row = matched[0]
    required_fields = [
        "session_id",
        "symbol",
        "status",
        "position_status",
        "exit_reason",
        "realized_pnl",
        "unrealized_pnl",
        "total_pnl",
        "exit_actual_cycle",
        "display_cycle",
        "exit_time_utc",
    ]
    missing = [field for field in required_fields if field not in row]
    if missing:
        raise AssertionError(f"Endpoint row missing fields: {missing}")
    if row.get("unrealized_pnl") != 0.0:
        raise AssertionError(f"Expected unrealized_pnl=0.0, got {row.get('unrealized_pnl')!r}")

    print("PASS exited-symbols endpoint verification")
    print(f"session_id={session_id}")
    print(f"count={response.get('count')}")
    print(
        "matched="
        f"symbol={row.get('symbol')} status={row.get('status')} "
        f"reason={row.get('exit_reason')} realized={row.get('realized_pnl')} "
        f"unrealized={row.get('unrealized_pnl')} total={row.get('total_pnl')}"
    )


if __name__ == "__main__":
    main()
