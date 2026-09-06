import json
import sys
import types

from auto_trader_exposure_expansion import AutoTrader

fake_orderbook = types.ModuleType("orderbook")
fake_orderbook.fetch_todays_intraday_orders = lambda *args, **kwargs: []
sys.modules["orderbook"] = fake_orderbook

fake_broker_angle = types.ModuleType("broker_angle")
fake_broker_angle.BrokerConnector = type("BrokerConnector", (), {})
sys.modules["broker_angle"] = fake_broker_angle

from auto_trader_exposure_expansion_org import AutoTrader as LiveAutoTrader


class FakeUpdateResult:
    matched_count = 1
    modified_count = 1


class FakeCollection:
    def __init__(self, name, database):
        self.name = name
        self.database = database
        self.docs = []
        self.indexes = []

    def create_index(self, keys, **kwargs):
        self.indexes.append((tuple(keys), dict(kwargs)))
        return kwargs.get("name", "idx")

    def _matches(self, doc, query):
        for key, expected in (query or {}).items():
            actual = doc.get(key)
            if isinstance(expected, dict):
                if "$in" in expected and actual not in expected["$in"]:
                    return False
                if "$ne" in expected and actual == expected["$ne"]:
                    return False
            elif actual != expected:
                return False
        return True

    def _project(self, doc, projection):
        if not projection:
            return dict(doc)
        include_keys = {k for k, v in projection.items() if v}
        exclude_keys = {k for k, v in projection.items() if not v}
        if include_keys:
            return {k: doc.get(k) for k in include_keys if k in doc}
        projected = dict(doc)
        for key in exclude_keys:
            projected.pop(key, None)
        return projected

    def find_one(self, query=None, projection=None, sort=None):
        rows = [doc for doc in self.docs if self._matches(doc, query or {})]
        if sort:
            for key, direction in reversed(sort):
                rows.sort(key=lambda row: row.get(key), reverse=direction < 0)
        if not rows:
            return None
        return self._project(rows[0], projection)

    def find(self, query=None, projection=None):
        return [self._project(doc, projection) for doc in self.docs if self._matches(doc, query or {})]

    def update_one(self, query, update, upsert=False):
        target = None
        for doc in self.docs:
            if self._matches(doc, query):
                target = doc
                break

        inserted = False
        if target is None:
            if not upsert:
                return FakeUpdateResult()
            target = dict(query)
            self.docs.append(target)
            inserted = True

        if "$setOnInsert" in update and inserted:
            target.update(update["$setOnInsert"])
        if "$set" in update:
            target.update(update["$set"])
        else:
            target.update(update)
        return FakeUpdateResult()

    def replace_one(self, query, replacement, upsert=False):
        for index, doc in enumerate(self.docs):
            if self._matches(doc, query):
                self.docs[index] = dict(replacement)
                return FakeUpdateResult()
        if upsert:
            self.docs.append(dict(replacement))
        return FakeUpdateResult()

    def insert_many(self, docs):
        self.docs.extend(dict(doc) for doc in docs)


class FakeDatabase:
    def __init__(self, name, client):
        self.name = name
        self.client = client
        self.collections = {}

    def __getitem__(self, collection_name):
        if collection_name not in self.collections:
            self.collections[collection_name] = FakeCollection(collection_name, self)
        return self.collections[collection_name]


class FakeClient:
    def __init__(self):
        self.databases = {}

    def __getitem__(self, database_name):
        if database_name not in self.databases:
            self.databases[database_name] = FakeDatabase(database_name, self)
        return self.databases[database_name]


class FakeRedis:
    def __init__(self):
        self.values = {}

    def setex(self, key, ttl, value):
        self.values[key] = {"ttl": ttl, "value": value}


class FakeMarketClient:
    def __init__(self):
        self.redis_client = FakeRedis()


def assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def assert_close(actual, expected, label, places=2):
    if round(float(actual), places) != round(float(expected), places):
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")


def make_trader():
    client = FakeClient()
    db = client["mintzy_plugin"]
    trading_logs = db["trading_logs"]

    trader = AutoTrader(
        prediction_client=object(),
        market_client=FakeMarketClient(),
        initial_capital=100000,
        trading_logs_collection=trading_logs,
    )
    trader.session_id = "session_test_rms"
    trader.ui_session_id = "session_test_rms"
    trader.configuration_id = "config_test"
    trader.config_db_name = "mintzy_plugin"
    trader.session = {"obj": None, "paper": True}
    trader.cash_balance = 100000
    trader.current_capital = 100000
    trader._current_cycle_count = 1
    return trader, db


def make_live_trader():
    client = FakeClient()
    db = client["mintzy_plugin"]
    trading_logs = db["trading_logs"]

    trader = LiveAutoTrader(
        prediction_client=object(),
        market_client=FakeMarketClient(),
        initial_capital=100000,
        trading_logs_collection=trading_logs,
    )
    trader.session_id = "session_test_live_rms"
    trader.ui_session_id = "session_test_live_rms"
    trader.configuration_id = "config_test"
    trader.config_db_name = "mintzy_plugin"
    trader.session = {"obj": object()}
    trader.cash_balance = 100000
    trader.current_capital = 100000
    trader._cycle_count = 1
    return trader, db


def seed_short_position(trader):
    trader.positions["INFY"] = {
        "side": "SELL",
        "qty": 12,
        "entry_price": 1133.0,
    }
    trader._paper_positions["INFY"] = {
        "symbol": "INFY",
        "side": "SELL",
        "qty": 12,
        "avg_price": 1133.0,
        "ltp": 1145.05,
    }
    trader.live_pnl["INFY"] = {
        "ltp": 1145.05,
        "pnl": -144.6,
        "qty": 12,
        "entry": 1133.0,
        "side": "SELL",
    }


def seed_live_short_position(trader):
    trader.positions["INFY"] = {
        "side": "SELL",
        "qty": 12,
        "entry_price": 1133.0,
    }
    trader._broker_positions_cache = [{
        "symbol": "INFY",
        "side": "SELL",
        "qty": 12,
        "avg_price": 1133.0,
        "ltp": 1145.05,
    }]
    trader.live_pnl["INFY"] = {
        "ltp": 1145.05,
        "pnl": -144.6,
        "qty": 12,
        "entry": 1133.0,
        "side": "SELL",
    }


def test_pending_exit_snapshot():
    trader, db = make_trader()
    seed_short_position(trader)

    trader._persist_exit_pending(
        "INFY",
        exit_reason="RMS_TICKER_EXIT",
        exit_side="BUY",
        qty=12,
        entry_price=1133.0,
        exit_order_id="PAPER-00000004",
    )

    doc = db["exited_symbols"].find_one({"session_id": trader.session_id, "symbol": "INFY"})
    assert_equal(doc["status"], "EXIT_PENDING", "pending status")
    assert_equal(doc["exit_actual_cycle"], 1, "pending actual cycle")
    assert_equal(doc["display_cycle"], 2, "pending display cycle")
    assert_close(doc["unrealized_pnl"], -144.6, "pending unrealized before fill")
    assert_equal(db["trading_logs"].docs, [], "pending should not create trading log row")


def test_final_exit_writes_exited_symbols_and_trading_logs():
    trader, db = make_trader()
    seed_short_position(trader)

    pre_exit = trader._snapshot_position_for_exit("INFY")
    trader._finalize_symbol_exit_fill(
        "INFY",
        {"side": "BUY", "qty": 12, "avg_price": 1145.05},
        {
            "order_id": "PAPER-00000004",
            "action_type": "COVER_SHORT",
            "side": "BUY",
            "qty": 12,
            "pre_exit_position": pre_exit,
            "exit_reason": "RMS_TICKER_EXIT",
        },
    )

    exit_doc = db["exited_symbols"].find_one({"session_id": trader.session_id, "symbol": "INFY"})
    assert_equal(exit_doc["status"], "EXITED", "final status")
    assert_equal(exit_doc["exit_reason"], "RMS_TICKER_EXIT", "exit reason")
    assert_equal(exit_doc["exit_actual_cycle"], 1, "final actual cycle")
    assert_equal(exit_doc["display_cycle"], 2, "final display cycle")
    assert_close(exit_doc["exit_realized_pnl"], -144.6, "exit fill realized pnl")
    assert_close(exit_doc["realized_pnl"], -144.6, "cumulative realized pnl")
    assert_close(exit_doc["unrealized_pnl"], 0.0, "final unrealized pnl")

    trade_row = db["trading_logs"].find_one({
        "session_id": trader.session_id,
        "symbol": "INFY",
        "is_exit_row": True,
    })
    assert_equal(trade_row["cycle"], 2, "trading log display cycle")
    assert_equal(trade_row["exit_actual_cycle"], 1, "trading log actual cycle")
    assert_equal(trade_row["action"], "RMS EXITED", "trading log action")
    assert_equal(trade_row["signal"], None, "invalid signal field should be null")
    assert_equal(trade_row["return_pct"], 0.0, "invalid return pct should be zero")
    assert_close(trade_row["symbol_realized_pnl"], -144.6, "trading log realized pnl")
    assert_close(trade_row["symbol_unrealized_pnl"], 0.0, "trading log unrealized pnl")

    trader.live_pnl["INFY"]["pnl"] = 9999.0
    assert_close(trader._get_symbol_unrealized_pnl("INFY"), 0.0, "exited symbol ignores stale live pnl")


def test_live_pnl_redis_marks_exited_symbol_as_closed():
    trader, _db = make_trader()
    seed_short_position(trader)
    trader._exited_symbols.add("INFY")
    trader.realized_pnl_by_symbol["INFY"] = -144.6
    trader.realized_pnl = -144.6
    trader.live_pnl["INFY"]["pnl"] = -144.6

    trader._push_live_pnl_to_redis()
    payload = json.loads(trader.market_client.redis_client.values["live_pnl:session_test_rms"]["value"])
    infy = payload["symbols"]["INFY"]

    assert_equal(infy["position_status"], "EXITED", "redis position status")
    assert_equal(infy["qty"], 0, "redis exited qty")
    assert_close(infy["unrealized_pnl"], 0.0, "redis exited unrealized pnl")
    assert_close(infy["realized_pnl"], -144.6, "redis realized pnl")
    assert_close(infy["total_pnl"], -144.6, "redis total pnl")


def test_pyramid_uses_realized_for_exited_symbol():
    trader, db = make_trader()
    seed_short_position(trader)
    trader._finalize_symbol_exit_fill(
        "INFY",
        {"side": "BUY", "qty": 12, "avg_price": 1145.05},
        {
            "order_id": "PAPER-00000004",
            "action_type": "COVER_SHORT",
            "side": "BUY",
            "qty": 12,
            "pre_exit_position": trader._snapshot_position_for_exit("INFY"),
            "exit_reason": "RMS_TICKER_EXIT",
        },
    )

    trader._fetch_saved_trading_configuration = lambda configuration_id: {
        "configuration": {
            "symbols": [{"symbol": "INFY", "capital": 13795.87, "rank": 4}]
        }
    }
    trader._build_pyramid_config_entries = lambda config_doc, symbols_list, rank_map: [
        ("INFY", {"symbol": "INFY", "capital": 13795.87, "rank": 4}, 13795.87)
    ]
    trader._get_pyramid_active_symbol_keys = lambda: ["INFY"]
    trader._get_pyramid_free_cash = lambda: 100000.0
    trader._resolve_leverage_multiplier = lambda config_doc=None, default=1.0: 1.0

    result = trader._apply_capital_pyramid_on_stop()
    assert_equal(result["live_allowed"], False, "pyramid live allowed")
    assert_equal(result["reason"], "no_profitable_symbols", "pyramid reason")

    pyramid_doc = db["pyramid_pnls"].find_one({"session_id": trader.session_id})
    row = pyramid_doc["symbols"][0]
    assert_equal(row["symbol"], "INFY", "pyramid symbol")
    assert_equal(row["position_status"], "EXITED", "pyramid position status")
    assert_equal(row["exit_reason"], "RMS_TICKER_EXIT", "pyramid exit reason")
    assert_close(row["realized_pnl"], -144.6, "pyramid realized pnl")
    assert_close(row["unrealized_pnl"], 0.0, "pyramid unrealized pnl")
    assert_close(row["total_pnl"], -144.6, "pyramid total pnl")
    assert_equal(row["is_profitable"], False, "pyramid exited symbol should not be profitable")


def test_db_sync_blocks_pending_and_exited_symbols():
    trader, db = make_trader()
    db["exited_symbols"].update_one(
        {"session_id": trader.session_id, "symbol": "BRITANNIA"},
        {"$set": {"session_id": trader.session_id, "symbol": "BRITANNIA", "status": "EXIT_PENDING"}},
        upsert=True,
    )
    db["exited_symbols"].update_one(
        {"session_id": trader.session_id, "symbol": "INFY"},
        {"$set": {"session_id": trader.session_id, "symbol": "INFY", "status": "EXITED"}},
        upsert=True,
    )

    trader._sync_exited_symbols_from_db()
    assert_equal("BRITANNIA" in trader._exited_symbols, True, "pending symbol blocks next cycle")
    assert_equal("INFY" in trader._exited_symbols, True, "exited symbol blocks next cycle")


def test_live_org_final_exit_writes_exited_symbols_and_trading_logs():
    trader, db = make_live_trader()
    seed_live_short_position(trader)

    pre_exit = trader._snapshot_position_for_exit("INFY")
    trader._finalize_symbol_exit_fill(
        "INFY",
        {"side": "BUY", "qty": 12, "avg_price": 1145.05},
        {
            "order_id": "LIVE-ORDER-1",
            "action_type": "COVER_SHORT",
            "side": "BUY",
            "qty": 12,
            "pre_exit_position": pre_exit,
            "exit_reason": "RMS_TICKER_EXIT",
        },
    )

    exit_doc = db["exited_symbols"].find_one({"session_id": trader.session_id, "symbol": "INFY"})
    assert_equal(exit_doc["source"], "live", "live org source")
    assert_equal(exit_doc["status"], "EXITED", "live org final status")
    assert_equal(exit_doc["display_cycle"], 2, "live org display cycle")
    assert_close(exit_doc["realized_pnl"], -144.6, "live org realized pnl")
    assert_close(exit_doc["unrealized_pnl"], 0.0, "live org unrealized pnl")

    trade_row = db["trading_logs"].find_one({
        "session_id": trader.session_id,
        "symbol": "INFY",
        "is_exit_row": True,
    })
    assert_equal(trade_row["cycle"], 2, "live org trading log display cycle")
    assert_equal(trade_row["action"], "RMS EXITED", "live org trading log action")
    assert_close(trade_row["symbol_realized_pnl"], -144.6, "live org trading log realized pnl")
    assert_close(trade_row["symbol_unrealized_pnl"], 0.0, "live org trading log unrealized pnl")

    trader.live_pnl["INFY"]["pnl"] = 9999.0
    assert_close(trader._get_symbol_unrealized_pnl("INFY"), 0.0, "live org ignores stale live pnl")


def test_live_org_pending_exit_blocks_next_cycle():
    trader, db = make_live_trader()
    seed_live_short_position(trader)

    trader._persist_exit_pending(
        "INFY",
        exit_reason="RMS_TICKER_EXIT",
        exit_side="BUY",
        qty=12,
        entry_price=1133.0,
        exit_order_id="LIVE-ORDER-1",
    )
    trader._sync_exited_symbols_from_db()

    assert_equal("INFY" in trader._exited_symbols, True, "live org pending exit blocks next cycle")
    doc = db["exited_symbols"].find_one({"session_id": trader.session_id, "symbol": "INFY"})
    assert_equal(doc["status"], "EXIT_PENDING", "live org pending status")
    assert_equal(db["trading_logs"].docs, [], "live org pending should not create final trading log row")


def run_all():
    tests = [
        test_pending_exit_snapshot,
        test_final_exit_writes_exited_symbols_and_trading_logs,
        test_live_pnl_redis_marks_exited_symbol_as_closed,
        test_pyramid_uses_realized_for_exited_symbol,
        test_db_sync_blocks_pending_and_exited_symbols,
        test_live_org_final_exit_writes_exited_symbols_and_trading_logs,
        test_live_org_pending_exit_blocks_next_cycle,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print("All exited-symbol flow checks passed.")


if __name__ == "__main__":
    run_all()
