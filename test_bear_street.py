"""
Minimal end-to-end test for Bear Street (Globe Capital) API auth flow.

Usage:
    python test_bear_street.py

Set credentials via environment variables or edit below:
    BEAR_STREET_API_KEY
    BEAR_STREET_USER_ID
    BEAR_STREET_PASSWORD
    BEAR_STREET_SECOND_AUTH
    BEAR_STREET_BASE_URL  (default: http://localhost:3100)
"""

import os
import sys
import json

from dotenv import load_dotenv
load_dotenv()

API_KEY = os.getenv("BEAR_STREET_API_KEY", "")
USER_ID = os.getenv("BEAR_STREET_USER_ID", "")
PASSWORD = os.getenv("BEAR_STREET_PASSWORD", "")
SECOND_AUTH = os.getenv("BEAR_STREET_SECOND_AUTH", "")
BASE_URL = os.getenv("BEAR_STREET_BASE_URL", "http://localhost:3100")


def main():
    if not all([API_KEY, USER_ID, PASSWORD, SECOND_AUTH]):
        print("ERROR: Set BEAR_STREET_API_KEY, BEAR_STREET_USER_ID, "
              "BEAR_STREET_PASSWORD, and BEAR_STREET_SECOND_AUTH env vars.")
        sys.exit(1)

    from broker_bear_street import BrokerConnector
    import os as _os

    _os.environ["BEAR_STREET_API_KEY"] = API_KEY
    _os.environ["BEAR_STREET_USER_ID"] = USER_ID
    _os.environ["BEAR_STREET_PASSWORD"] = PASSWORD
    _os.environ["BEAR_STREET_SECOND_AUTH"] = SECOND_AUTH
    _os.environ["BEAR_STREET_BASE_URL"] = BASE_URL

    print("=" * 60)
    print("Bear Street SDK — Session 1 Auth Test")
    print("=" * 60)
    print(f"User: {USER_ID}")
    print(f"Base URL: {BASE_URL}")
    print()

    broker = BrokerConnector()

    # 1. Create session (login)
    print(">>> 1. Creating session (login)...")
    try:
        session = broker.get_session()
        print(f"    ✓ Login success. User: {session.get('user')}")
        token = session.get("token", "")
        print(f"    ✓ Token: {token[:30]}...")
        print(f"    ✓ Broadcast token: {session.get('broadcast_token', 'N/A')[:20] if session.get('broadcast_token') else 'N/A'}...")
    except Exception as e:
        print(f"    ✗ Login failed: {e}")
        sys.exit(1)
    print()

    # 2. Get balance
    print(">>> 2. Fetching balance...")
    try:
        bal = broker.get_account_balance(session)
        print(f"    ✓ Balance response: {bal.get('status')}")
        print(f"    ✓ Raw data: {json.dumps(bal.get('data', {}), indent=4)[:200]}")
    except Exception as e:
        print(f"    ✗ Balance failed: {e}")
    print()

    # 3. Get user profile
    print(">>> 3. Fetching user profile...")
    try:
        prof = broker.get_user_profile(session)
        print(f"    ✓ Profile response: {prof.get('status')}")
        print(f"    ✓ Profile data: {json.dumps(prof.get('raw', {}), indent=4)[:200]}")
    except Exception as e:
        print(f"    ✗ Profile failed: {e}")
    print()

    # 4. Restore session from token
    print(">>> 4. Testing session restore...")
    try:
        session2 = broker.restore_session({"token": token})
        print(f"    ✓ Restore success. User: {session2.get('user')}")
    except Exception as e:
        print(f"    ✗ Restore failed: {e}")
    print()

    # 5. Logout
    print(">>> 5. Logging out...")
    try:
        logout_resp = broker.obj.logout()
        print(f"    ✓ Logout success: {logout_resp}")
    except Exception as e:
        print(f"    ✗ Logout failed: {e}")
    print()

    print("=" * 60)
    print("Session 1 tests complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
