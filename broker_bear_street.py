import os
import time
import json
from datetime import datetime
from pathlib import Path
import sys

from broker_factory import BROKER_BEAR_STREET, DEFAULT_BEAR_STREET_BASE_URL


def _ensure_sdk_path():
    candidates = [
        os.getenv("BEAR_STREET_SDK_PATH"),
        str(Path(__file__).resolve().parent / "bear_street_client"),
        str(Path(__file__).resolve().parent),
    ]
    for sdk_path in candidates:
        if not sdk_path:
            continue
        p = Path(sdk_path)
        if (p / "bear_street_client").is_dir() or (p.name == "bear_street_client" and p.is_dir()):
            root = str(p if (p / "bear_street_client").is_dir() else p.parent)
            if root not in sys.path:
                sys.path.insert(0, root)
            return


_ensure_sdk_path()

from bear_street_client import BearStreetClient
from bear_street_client.exceptions import BearStreetAuthError, BearStreetAPIError


class BrokerConnector:
    broker_type = BROKER_BEAR_STREET

    def __init__(self, instruments_path=None, require_totp=False):
        self.api_key = os.getenv("BEAR_STREET_API_KEY", "").strip()
        self.user_id = os.getenv("BEAR_STREET_USER_ID", "").strip()
        self.password = os.getenv("BEAR_STREET_PASSWORD", "").strip()
        self.second_auth = os.getenv("BEAR_STREET_SECOND_AUTH", "").strip()
        self.source = os.getenv("BEAR_STREET_SOURCE", "WEBAPI").strip()
        self.base_url = os.getenv("BEAR_STREET_BASE_URL", DEFAULT_BEAR_STREET_BASE_URL).strip()

        self.obj = None
        self.access_token = None
        self.broadcast_access_token = None
        self.user = None
        self.debug = os.getenv("BEAR_STREET_DEBUG", "").lower() in ("1", "true", "yes")

    def _build_client(self):
        if not self.api_key or not self.user_id or not self.password or not self.second_auth:
            raise RuntimeError("Bear Street credentials missing (api_key, user_id, password, second_auth)")
        return BearStreetClient(
            api_key=self.api_key,
            user_id=self.user_id,
            password=self.password,
            second_auth=self.second_auth,
            source=self.source,
            base_url=self.base_url,
            env_file=os.path.join(os.path.dirname(__file__), f".bear_street_{self.user_id}.env"),
        )

    def _create_session(self):
        try:
            self.obj = self._build_client()
            login_resp = self.obj.login(get_new_token=True)
            if not self.obj.token:
                raise RuntimeError(f"Bear Street login failed: {login_resp.message}")

            self.access_token = self.obj.token
            self.broadcast_access_token = self.obj.broadcast_token
            self.user = self.user_id
            print("Bear Street account linked successfully.")

            return {
                "user": self.user,
                "token": self.access_token,
                "broadcast_token": self.broadcast_access_token,
                "obj": self.obj,
            }
        except BearStreetAuthError as ex:
            raise RuntimeError(f"Bear Street login failed: {ex}") from ex
        except Exception as ex:
            raise RuntimeError(f"Bear Street login failed: {ex}") from ex

    def restore_session(self, broker_session: dict):
        token = (broker_session or {}).get("token") or ""
        if token.startswith("Bearer "):
            token = token.replace("Bearer ", "", 1)

        self.obj = self._build_client()
        if token:
            self.obj.set_access_token(token)
            self.access_token = token
        else:
            return self._create_session()

        self.user = self.user_id

        try:
            self.obj.get_balance()
        except BearStreetAuthError:
            if self.debug:
                print("[RESTORE] Token expired, re-logging in")
            login_resp = self.obj.login(get_new_token=True)
            self.access_token = self.obj.token
            self.broadcast_access_token = self.obj.broadcast_token
            if not self.access_token:
                raise RuntimeError(f"Bear Street token refresh failed: {login_resp.message}")

        return {
            "user": self.user,
            "token": self.access_token,
            "broadcast_token": self.broadcast_access_token,
            "obj": self.obj,
        }

    def get_ws_credentials(self):
        token = self.access_token or ""
        if token.startswith("Bearer "):
            token = token[len("Bearer "):]
        return {
            "auth_token": token,
            "broadcast_token": self.broadcast_access_token,
            "api_key": self.api_key,
            "user_id": self.user_id,
            "base_url": self.base_url,
        }

    def get_session(self):
        if self.obj and self.access_token:
            return {
                "user": self.user,
                "token": self.access_token,
                "broadcast_token": self.broadcast_access_token,
                "obj": self.obj,
            }
        return self._create_session()

    def refresh_session(self):
        return self._create_session()

    def _is_auth_error(self, err):
        try:
            if isinstance(err, BearStreetAuthError):
                return True
            text = str(err).lower()
            return any(m in text for m in ("401", "unauthorized", "invalid token", "token expired"))
        except Exception:
            return False

    def _call_api(self, fn, *args, **kwargs):
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return fn(*args, **kwargs)
            except BearStreetAuthError:
                raise RuntimeError("SESSION_EXPIRED_RELOGIN_REQUIRED")
            except BearStreetAPIError as e:
                if e.status_code == 429 and attempt < max_retries - 1:
                    wait = 2 ** attempt
                    print(f"[RATE LIMIT] 429 on attempt {attempt+1}/{max_retries}, retrying in {wait}s")
                    time.sleep(wait)
                    continue
                raise
            except Exception as e:
                raise RuntimeError(f"API call failed: {e}")

    def get_account_balance(self, session):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        try:
            resp = self._call_api(session["obj"].get_balance)
            return {
                "status": "success",
                "free_cash": float(resp.data.equity.get("cash", 0)) if resp and resp.data and resp.data.equity else 0,
                "data": resp.get_dict() if hasattr(resp, "get_dict") else {},
                "source": "BEAR_STREET_SDK",
            }
        except RuntimeError:
            raise
        except Exception as ex:
            return {"status": "error", "error": str(ex), "source": "BEAR_STREET_SDK"}

    def get_user_profile(self, session):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        try:
            resp = self._call_api(session["obj"].get_user_profile)
            return {"status": "success", "raw": resp.get_dict() if hasattr(resp, "get_dict") else {}}
        except RuntimeError:
            raise
        except Exception as ex:
            return {"status": "error", "error": str(ex)}

    def place_order(self, session, symbol, side, qty=None, quantity=None, price=None,
                    order_type="MARKET", product_type="INTRADAY", exchange="NSE",
                    variety="NORMAL", lot_based=False, stop_loss=None,
                    trigger_price=None, wait_for_confirmation=True, **kwargs):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided.", "filled": False}
        return {"status": "error", "error": "Not implemented (Session 2)", "filled": False}

    def modify_order(self, session, order_id, new_price=None, new_qty=None, **kwargs):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        return {"status": "error", "error": "Not implemented (Session 2)"}

    def cancel_order(self, session, order_id, variety="NORMAL"):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        return {"status": "error", "error": "Not implemented (Session 2)"}

    def get_order_book(self, session):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        return {"status": "error", "error": "Not implemented (Session 2)"}

    def get_trade_book(self, session):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        return {"status": "error", "error": "Not implemented (Session 2)"}

    def get_positions(self, session):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        return {"status": "error", "error": "Not implemented (Session 3)"}

    def get_holdings(self, session):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        return {"status": "error", "error": "Not implemented (Session 3)"}

    def get_ltp(self, session, exchange, trading_symbol, symbol_token):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        return {"status": "error", "error": "Not implemented (Session 3)"}
