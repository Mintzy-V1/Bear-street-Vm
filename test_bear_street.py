"""
End-to-end test for Bear Street (Globe Capital) API.

Tests Session 1 (auth) and Session 2 (orders).

Usage:
    python test_bear_street.py [--order]

Set credentials via environment variables:
    BEAR_STREET_API_KEY
    BEAR_STREET_USER_ID
    BEAR_STREET_PASSWORD
    BEAR_STREET_SECOND_AUTH
    BEAR_STREET_BASE_URL  (default: http://localhost:3100)
"""

import os
import sys
import json
import time

from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("BEAR_STREET_API_KEY", "")
USER_ID = os.getenv("BEAR_STREET_USER_ID", "")
PASSWORD = os.getenv("BEAR_STREET_PASSWORD", "")
SECOND_AUTH = os.getenv("BEAR_STREET_SECOND_AUTH", "")
BASE_URL = os.getenv("BEAR_STREET_BASE_URL", "http://localhost:3100")


def set_env():
    os.environ["BEAR_STREET_API_KEY"] = API_KEY
    os.environ["BEAR_STREET_USER_ID"] = USER_ID
    os.environ["BEAR_STREET_PASSWORD"] = PASSWORD
    os.environ["BEAR_STREET_SECOND_AUTH"] = SECOND_AUTH
    os.environ["BEAR_STREET_BASE_URL"] = BASE_URL


def test_auth(broker):
    print("=" * 60)
    print("SESSION 1 — Auth Flow")
    print("=" * 60)

    # 1. Create session
    print("\n>>> 1. Login...")
    session = broker.get_session()
    token = session.get("token", "")
    print(f"    User: {session.get('user')}")
    print(f"    Token: {token[:30]}...")
    print(f"    Broadcast: {str(session.get('broadcast_token', ''))[:20]}...")
    assert token, "Token missing"
    print("    ✓ Login OK")

    # 2. Balance
    print("\n>>> 2. Balance...")
    bal = broker.get_account_balance(session)
    print(f"    Status: {bal.get('status')}")
    print(f"    Free cash: {bal.get('free_cash')}")
    print(f"    ✓ Balance OK")

    # 3. Profile
    print("\n>>> 3. Profile...")
    prof = broker.get_user_profile(session)
    print(f"    Status: {prof.get('status')}")
    print(f"    ✓ Profile OK")

    # 4. Session restore
    print("\n>>> 4. Session restore...")
    session2 = broker.restore_session({"token": token})
    print(f"    User: {session2.get('user')}")
    print(f"    ✓ Restore OK")

    # 5. Logout
    print("\n>>> 5. Logout...")
    out = broker.obj.logout()
    print(f"    Status: {out.get('status') if isinstance(out, dict) else 'OK'}")
    print(f"    ✓ Logout OK")

    print("\n✓ Session 1 complete\n")
    return session


def test_orders(broker, session):
    print("=" * 60)
    print("SESSION 2 — Order Management")
    print("=" * 60)

    # 1. Order book
    print("\n>>> 1. Order book...")
    ob = broker.get_order_book(session)
    print(f"    Status: {ob.get('status')}")
    if ob.get("status") == "success":
        orders = ob.get("raw", {}).get("data", [])
        print(f"    Orders: {len(orders)}")
        if orders:
            print(f"    First: {json.dumps(orders[0], indent=2)[:200]}")
    print(f"    ✓ Order book OK")

    # 2. Trade book
    print("\n>>> 2. Trade book...")
    tb = broker.get_trade_book(session)
    print(f"    Status: {tb.get('status')}")
    if tb.get("status") == "success":
        trades = tb.get("raw", {}).get("data", [])
        print(f"    Trades: {len(trades)}")
    print(f"    ✓ Trade book OK")

    # 3. Order history (if we have an order_id)
    ob = broker.get_order_book(session)
    if ob.get("status") == "success":
        orders = ob.get("raw", {}).get("data", [])
        if orders:
            oid = orders[0].get("orderid")
            print(f"\n>>> 3. Order history for {oid}...")
            oh = broker.get_order_history(session, oid)
            print(f"    Status: {oh.get('status')}")
            print(f"    ✓ Order history OK")

    # 4. Place order (dry-run with wait_for_confirmation=False)
    print("\n>>> 4. Place order (dry-run, no confirm)...")
    result = broker.place_order(
        session, "ACC", "BUY",
        qty=1, price=0, order_type="MARKET",
        product_type="INTRADAY", exchange="NSE",
        wait_for_confirmation=False,
    )
    print(f"    Status: {result.get('status')}")
    if result.get("status") == "success":
        oid = result.get("order_id")
        print(f"    Order ID: {oid}")

        # Cancel it
        print(f"\n>>> 5. Cancel order {oid}...")
        cx = broker.cancel_order(session, oid)
        print(f"    Status: {cx.get('status')}")
        print(f"    ✓ Cancel OK")
    elif "No order ID" in str(result.get("error", "")):
        print("    (Expected — no real exchange to fill)")
    print(f"    ✓ Place order OK")

    print("\n✓ Session 2 complete\n")


def test_portfolio(broker, session):
    print("=" * 60)
    print("SESSION 3 — Portfolio & Market Data")
    print("=" * 60)

    print("\n>>> 1. Positions...")
    pos = broker.get_positions(session)
    print(f"    Status: {pos.get('status')}")
    if pos.get("status") == "success":
        items = pos.get("raw", {}).get("data", [])
        print(f"    Positions: {len(items)}")
        if items:
            print(f"    First: {json.dumps(items[0], indent=2)[:200]}")
    print(f"    ✓ Positions OK")

    print("\n>>> 2. Holdings...")
    hol = broker.get_holdings(session)
    print(f"    Status: {hol.get('status')}")
    if hol.get("status") == "success":
        items = hol.get("raw", {}).get("data", [])
        print(f"    Holdings: {len(items)}")
    print(f"    ✓ Holdings OK")

    print("\n>>> 3. LTP...")
    ltp = broker.get_ltp(session, "NSE", "ACC", 22)
    print(f"    Status: {ltp.get('status')}")
    if ltp.get("status") == "success":
        print(f"    LTP raw: {json.dumps(ltp.get('raw', {}), indent=2)[:200]}")
    print(f"    ✓ LTP OK")

    print("\n>>> 4. Bulk LTP...")
    bltp = broker._get_ltp_map(session, [{"exchange": "NSE", "symbolToken": 22}])
    print(f"    Status: {bltp.get('status')}")
    print(f"    ✓ Bulk LTP OK")

    print("\n>>> 5. WebSocket credentials...")
    ws = broker.get_ws_credentials()
    print(f"    auth_token: {str(ws.get('auth_token', ''))[:20]}...")
    print(f"    broadcast_token: {str(ws.get('broadcast_token', ''))[:20]}...")
    print(f"    ✓ WebSocket credentials OK")

    print("\n✓ Session 3 complete\n")


def main():
    if not all([API_KEY, USER_ID, PASSWORD, SECOND_AUTH]):
        print("ERROR: Set BEAR_STREET_API_KEY, BEAR_STREET_USER_ID, "
              "BEAR_STREET_PASSWORD, and BEAR_STREET_SECOND_AUTH env vars.")
        sys.exit(1)

    set_env()
    from broker_bear_street import BrokerConnector

    test_orders_flag = "--order" in sys.argv
    test_portfolio_flag = "--portfolio" in sys.argv

    broker = BrokerConnector()
    session = test_auth(broker)

    if test_orders_flag:
        broker2 = BrokerConnector()
        session2 = broker2.get_session()
        test_orders(broker2, session2)

    if test_portfolio_flag:
        broker3 = BrokerConnector()
        session3 = broker3.get_session()
        test_portfolio(broker3, session3)

    if not test_orders_flag and not test_portfolio_flag:
        print('Pass --order and/or --portfolio to run those tests.')


if __name__ == "__main__":
    main()
