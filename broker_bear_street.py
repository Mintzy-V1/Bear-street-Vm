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
from bear_street_client.models.new_order import ScripInfo, NewOrderRequest
from bear_street_client.models.modify_order import ModifyOrderRequest
from bear_street_client.models.cover_order import (
    CoverOrderRequest, CoverOrderRequestForModify,
    MainLeg as CoverMainLeg, StoplossLeg as CoverStoplossLeg,
)
from bear_street_client.models.bracket_order import (
    BracketOrderRequest, BracketOrderRequestForModify,
    MainLeg as BracketMainLeg, StoplossLeg as BracketStoplossLeg,
    ProfitLeg, FieldsModified,
)
from bear_street_client.models.position_conversion import PositionConversionRequest


class BrokerConnector:
    broker_type = BROKER_BEAR_STREET

    def __init__(self, instruments_path=None, require_totp=False):
        self.api_key = os.getenv("BEAR_STREET_API_KEY", "").strip()
        self.user_id = os.getenv("BEAR_STREET_USER_ID", "").strip()
        self.password = os.getenv("BEAR_STREET_PASSWORD", "").strip()
        self.second_auth = os.getenv("BEAR_STREET_SECOND_AUTH", "").strip()
        self.second_auth_type = os.getenv("BEAR_STREET_SECOND_AUTH_TYPE", "OTP").strip() or "OTP"
        self.login_type = os.getenv("BEAR_STREET_LOGIN_TYPE", "PASSWORD").strip() or "PASSWORD"
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
            second_auth_type=self.second_auth_type,
            login_type=self.login_type,
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

    # -------------------------------------------------------------------------
    # ACCOUNT
    # -------------------------------------------------------------------------

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

    # -------------------------------------------------------------------------
    # ORDER BOOK / TRADE BOOK / ORDER HISTORY
    # -------------------------------------------------------------------------

    def _normalize_order_row(self, order_row: dict) -> dict:
        status = (order_row.get("status") or "").upper()
        if status in ("EXECUTED", "COMPLETE", "TRADED"):
            orderstatus = "complete"
        elif status in ("CANCELLED", "CANCELED"):
            orderstatus = "cancelled"
        elif status == "REJECTED":
            orderstatus = "rejected"
        else:
            orderstatus = status.lower() or "open"
        sym = (order_row.get("symbol") or "").upper()
        if sym and not sym.endswith("-EQ"):
            sym = f"{sym}-EQ"
        return {
            "orderid": order_row.get("order_id"),
            "tradingsymbol": sym,
            "orderstatus": orderstatus,
            "averageprice": float(order_row.get("average_price") or 0),
            "filledshares": int(order_row.get("traded_quantity") or 0),
            "price": float(order_row.get("price") or 0),
            "producttype": (order_row.get("product_type") or "").upper(),
            "transactiontype": order_row.get("transaction_type"),
            "text": order_row.get("rejection_reason") or "",
            "exchange": order_row.get("exchange"),
            "scrip_token": order_row.get("scrip_token"),
            "order_identifier": order_row.get("order_identifier"),
        }

    def _normalize_trade_row(self, trade_row: dict) -> dict:
        sym = (trade_row.get("symbol") or "").upper()
        if sym and not sym.endswith("-EQ"):
            sym = f"{sym}-EQ"
        return {
            "orderid": trade_row.get("order_id"),
            "tradingsymbol": sym,
            "trade_no": trade_row.get("trade_no"),
            "exchange_order_no": trade_row.get("exchange_order_no"),
            "transactiontype": trade_row.get("transaction_type"),
            "producttype": (trade_row.get("product_type") or "").upper(),
            "trade_quantity": int(trade_row.get("trade_quantity") or 0),
            "trade_price": float(trade_row.get("trade_price") or 0),
            "exchange": trade_row.get("exchange"),
            "trade_timestamp": trade_row.get("trade_timestamp"),
            "order_identifier": trade_row.get("order_identifier"),
        }

    def get_order_book(self, session):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        try:
            resp = self._call_api(session["obj"].get_order_book, 1, 500)
            raw_data = resp.get("data") if isinstance(resp, dict) else []
            if isinstance(raw_data, dict):
                raw_data = [raw_data]
            data = [self._normalize_order_row(r) for r in (raw_data or [])]
            return {"status": "success", "raw": {"status": True, "data": data}}
        except RuntimeError:
            raise
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_trade_book(self, session):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        try:
            resp = self._call_api(session["obj"].get_trade_book, 1, 500)
            raw_data = resp.get("data") if isinstance(resp, dict) else []
            if isinstance(raw_data, dict):
                raw_data = [raw_data]
            data = [self._normalize_trade_row(r) for r in (raw_data or [])]
            return {"status": "success", "raw": {"status": True, "data": data}}
        except RuntimeError:
            raise
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_order_status(self, session, order_id):
        try:
            book = self.get_order_book(session)
            if book.get("status") != "success":
                return {"status": "error", "error": book.get("error", "order book failed")}
            for order in book.get("raw", {}).get("data", []):
                if str(order.get("orderid")) == str(order_id):
                    return order
            return {"status": "error", "error": f"Order {order_id} not found"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _find_order_row(self, session, order_id):
        book = self.get_order_book(session)
        if book.get("status") != "success":
            return None
        for order in book.get("raw", {}).get("data", []):
            if str(order.get("orderid")) == str(order_id):
                return order
        return None

    def get_order_history(self, session, order_id):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        try:
            resp = self._call_api(session["obj"].get_order_history, order_id)
            return {"status": "success", "raw": resp if isinstance(resp, dict) else {}}
        except RuntimeError:
            raise
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # -------------------------------------------------------------------------
    # ORDER CONFIRMATION POLLING
    # -------------------------------------------------------------------------

    def _wait_for_order_confirmation(self, session, order_id, max_wait_seconds=10, check_interval=1):
        if not order_id:
            return {"filled": False, "status": "NO_ORDER_ID", "message": "No order ID provided"}
        elapsed = 0
        while elapsed < max_wait_seconds:
            try:
                book = self.get_order_book(session)
                if book.get("status") != "success":
                    time.sleep(check_interval)
                    elapsed += check_interval
                    continue
                for order in book.get("raw", {}).get("data", []):
                    oid = str(order.get("orderid"))
                    if oid != str(order_id):
                        continue
                    status = (order.get("orderstatus") or "").upper()
                    avg_price = float(order.get("averageprice") or 0)
                    if status in ("EXECUTED", "COMPLETE", "TRADED"):
                        return {"filled": True, "status": status, "avg_price": avg_price,
                                "message": f"Order {order_id} filled at {avg_price:.2f}"}
                    if status in ("REJECTED", "CANCELLED", "FAILED"):
                        return {"filled": False, "status": status, "avg_price": 0,
                                "message": f"Order {order_id} {status.lower()}"}
                time.sleep(check_interval)
                elapsed += check_interval
            except RuntimeError:
                raise
            except Exception as e:
                if self.debug:
                    print(f"[WARN] Order status check failed: {e}")
                time.sleep(check_interval)
                elapsed += check_interval
        return {"filled": False, "status": "TIMEOUT", "avg_price": 0,
                "message": f"Order {order_id} status check timed out after {max_wait_seconds}s"}

    # -------------------------------------------------------------------------
    # REGULAR ORDERS
    # -------------------------------------------------------------------------

    def place_order(self, session, symbol, side, qty=None, quantity=None, price=None,
                    order_type="MARKET", product_type="INTRADAY", exchange="NSE",
                    variety="NORMAL", lot_based=False, stop_loss=None,
                    trigger_price=None, wait_for_confirmation=True, **kwargs):
        qty = qty or quantity
        if qty is None:
            return {"status": "error", "error": "Missing quantity/qty argument", "filled": False}
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided.", "filled": False}

        side_upper = side.upper().replace("_", "").replace(" ", "")
        if side_upper in ("BUY", "LONG", "BUYCOVER", "COVER"):
            api_side = "BUY"
        elif side_upper in ("SELL", "SHORT", "SHORTSELL", "SELLSHORT"):
            api_side = "SELL"
        else:
            return {"status": "error", "error": f"Invalid side: {side}", "filled": False}

        bear_exchange = exchange
        bear_product = product_type.upper()
        is_market = order_type.upper() in ("MARKET", "RL-MKT")
        bear_order_type = "RL-MKT" if is_market else "RL"
        if stop_loss or trigger_price:
            bear_order_type = "SL" if not is_market else "SL-MKT"
        price_value = 0.0 if is_market else float(price or 0)
        trigger_value = float(trigger_price or stop_loss or 0)

        scrip = ScripInfo(exchange=bear_exchange, symbol=symbol)

        req = NewOrderRequest(
            scrip_info=scrip,
            transaction_type=api_side,
            product_type=bear_product,
            order_type=bear_order_type,
            quantity=int(qty),
            price=price_value,
            trigger_price=trigger_value if trigger_value > 0 else None,
            validity=kwargs.get("validity", "DAY"),
            order_identifier=kwargs.get("order_identifier"),
        )

        try:
            print(f"[ORDER] Bear Street {api_side} {symbol} x {qty} @ {price_value} product={bear_product} type={bear_order_type}")
            resp = self._call_api(session["obj"].place_order, req.get_dict())
            order_id = None
            if isinstance(resp, dict):
                data = resp.get("data") or {}
                order_id = resp.get("order_id") or data.get("orderId") or data.get("order_id")

            if not order_id:
                return {"status": "error", "error": "No order ID in response", "filled": False, "raw": resp}

            if wait_for_confirmation:
                confirmation = self._wait_for_order_confirmation(session, order_id)
                if confirmation.get("filled"):
                    return {"status": "success", "order_id": order_id, "filled": True,
                            "avg_price": confirmation["avg_price"], "raw": resp}
                return {"status": "error", "order_id": order_id, "filled": False,
                        "error": confirmation["message"], "raw": resp}
            return {"status": "success", "order_id": order_id, "filled": None, "raw": resp}
        except RuntimeError:
            raise
        except Exception as e:
            return {"status": "error", "error": str(e), "filled": False}

    def modify_order(self, session, order_id, new_price=None, new_qty=None, **kwargs):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        try:
            row = self._find_order_row(session, order_id)
            if not row:
                return {"status": "error", "error": f"Order {order_id} not found in order book"}

            traded_qty = int(row.get("filledshares") or 0)
            exchange = row.get("exchange") or "NSE"
            req = ModifyOrderRequest(
                order_type=kwargs.get("order_type", row.get("orderstatus", "RL")),
                quantity=int(new_qty or (traded_qty + 1)),
                traded_quantity=traded_qty,
                price=float(new_price or kwargs.get("price") or row.get("price") or 0),
                trigger_price=float(kwargs.get("trigger_price") or 0) or None,
                validity=kwargs.get("validity", "DAY"),
            )
            resp = self._call_api(session["obj"].modify_order, exchange, order_id, req.get_dict())
            return {"status": "success", "raw": resp}
        except RuntimeError:
            raise
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def cancel_order(self, session, order_id, variety="NORMAL"):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        try:
            row = self._find_order_row(session, order_id)
            exchange = (row or {}).get("exchange") or "NSE"
            resp = self._call_api(session["obj"].cancel_order, exchange, order_id)
            return {"status": "success", "raw": resp}
        except RuntimeError:
            raise
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # -------------------------------------------------------------------------
    # COVER ORDERS
    # -------------------------------------------------------------------------

    def place_cover_order(self, session, symbol, side, qty, price=0,
                          order_type="RL-MKT", exchange="NSE", **kwargs):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided.", "filled": False}
        try:
            scrip = ScripInfo(exchange=exchange, symbol=symbol)
            req = CoverOrderRequest(
                scrip_info=scrip,
                transaction_type=side.upper(),
                main_leg=CoverMainLeg(order_type=order_type, quantity=int(qty), price=float(price)),
                stoploss_leg=CoverStoplossLeg(legs=kwargs.get("stoploss_legs", [])),
                order_identifier=kwargs.get("order_identifier"),
            )
            print(f"[COVER] Bear Street {side} {symbol} x {qty}")
            resp = self._call_api(session["obj"].place_cover_order, req.get_dict())
            return {"status": "success", "raw": resp}
        except RuntimeError:
            raise
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def modify_cover_order(self, session, order_id, **kwargs):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        try:
            row = self._find_order_row(session, order_id)
            exchange = (row or {}).get("exchange") or "NSE"
            req = CoverOrderRequestForModify(
                main_leg=CoverMainLeg(
                    order_type=kwargs.get("order_type", "RL-MKT"),
                    quantity=int(kwargs.get("quantity", 0)),
                    price=float(kwargs.get("price", 0)),
                ) if kwargs.get("quantity") else None,
                stoploss_leg=CoverStoplossLeg(legs=kwargs.get("stoploss_legs", [])),
            )
            resp = self._call_api(session["obj"].modify_cover_order, exchange, order_id, req.get_dict())
            return {"status": "success", "raw": resp}
        except RuntimeError:
            raise
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def cancel_cover_order(self, session, order_id):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        try:
            row = self._find_order_row(session, order_id)
            exchange = (row or {}).get("exchange") or "NSE"
            resp = self._call_api(session["obj"].cancel_cover_order, exchange, order_id)
            return {"status": "success", "raw": resp}
        except RuntimeError:
            raise
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # -------------------------------------------------------------------------
    # BRACKET ORDERS
    # -------------------------------------------------------------------------

    def place_bracket_order(self, session, symbol, side, qty, price=0,
                            trigger_price=None, exchange="NSE", **kwargs):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided.", "filled": False}
        try:
            scrip = ScripInfo(exchange=exchange, symbol=symbol)
            req = BracketOrderRequest(
                scrip_info=scrip,
                transaction_type=side.upper(),
                main_leg=BracketMainLeg(
                    order_type=kwargs.get("order_type", "RL"),
                    quantity=int(qty),
                    price=float(price),
                    trigger_price=float(trigger_price or 0) or None,
                ),
                stoploss_leg=BracketStoplossLeg(
                    legs=kwargs.get("stoploss_legs", {}),
                    trail=kwargs.get("stoploss_trail", {}),
                ),
                profit_leg=ProfitLeg(legs=kwargs.get("profit_legs", [])),
                order_identifier=kwargs.get("order_identifier"),
            )
            print(f"[BRACKET] Bear Street {side} {symbol} x {qty}")
            resp = self._call_api(session["obj"].place_bracket_order, req.get_dict())
            return {"status": "success", "raw": resp}
        except RuntimeError:
            raise
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def modify_bracket_order(self, session, order_id, **kwargs):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        try:
            row = self._find_order_row(session, order_id)
            exchange = (row or {}).get("exchange") or "NSE"
            req = BracketOrderRequestForModify(
                main_leg=BracketMainLeg(
                    order_type=kwargs.get("order_type", "RL"),
                    quantity=int(kwargs.get("quantity", 0)),
                    price=float(kwargs.get("price", 0)),
                    trigger_price=float(kwargs.get("trigger_price", 0)) or None,
                    traded_quantity=int(kwargs.get("traded_quantity", 0)),
                ) if kwargs.get("quantity") else None,
                stoploss_leg=BracketStoplossLeg(
                    legs=kwargs.get("stoploss_legs", []),
                    trail=kwargs.get("stoploss_trail", {}),
                ),
                profit_leg=ProfitLeg(legs=kwargs.get("profit_legs", [])),
                fields_modified=FieldsModified(
                    main_leg_price=kwargs.get("modify_main_price", False),
                    main_leg_qty=kwargs.get("modify_main_qty", False),
                    stoploss_leg_price=kwargs.get("modify_sl_price", False),
                    stoploss_trail_price=kwargs.get("modify_sl_trail", False),
                    profit_leg_price=kwargs.get("modify_profit_price", False),
                ) if any(kwargs.get(k) for k in ("modify_main_price", "modify_main_qty", "modify_sl_price", "modify_sl_trail", "modify_profit_price")) else None,
            )
            resp = self._call_api(session["obj"].modify_bracket_order, exchange, order_id, req.get_dict())
            return {"status": "success", "raw": resp}
        except RuntimeError:
            raise
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def exit_bracket_order(self, session, order_id):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        try:
            row = self._find_order_row(session, order_id)
            exchange = (row or {}).get("exchange") or "NSE_EQ"
            resp = self._call_api(session["obj"].exit_bracket_order, exchange, order_id)
            return {"status": "success", "raw": resp}
        except RuntimeError:
            raise
        except Exception as e:
            return {"status": "error", "error": str(e)}

    # -------------------------------------------------------------------------
    # PORTFOLIO
    # -------------------------------------------------------------------------

    def _normalize_position_row(self, row: dict) -> dict:
        sym = (row.get("symbol") or "").upper()
        if sym and not sym.endswith("-EQ"):
            sym = f"{sym}-EQ"
        return {
            "exchange": row.get("exchange"),
            "tradingsymbol": sym,
            "producttype": (row.get("product_type") or "").upper(),
            "transactiontype": row.get("transaction_type"),
            "quantity": int(row.get("net_quantity") or 0),
            "buyqty": int(row.get("buy_quantity") or 0),
            "buyavgprice": float(row.get("avg_buy_price") or 0),
            "sellqty": int(row.get("sell_quantity") or 0),
            "sellavgprice": float(row.get("avg_sell_price") or 0),
            "ltp": float(row.get("ltp") or 0),
            "mtm": float(row.get("mtm") or 0),
            "multiplier": int(row.get("multiplier") or 1),
            "scrip_token": row.get("scrip_token"),
        }

    def get_positions(self, session):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        try:
            resp = self._call_api(session["obj"].get_positions)
            raw_data = resp.get("data") if isinstance(resp, dict) else []
            if isinstance(raw_data, dict):
                raw_data = [raw_data]
            data = [self._normalize_position_row(r) for r in (raw_data or [])]
            return {"status": "success", "raw": {"status": True, "data": data}}
        except RuntimeError:
            raise
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_holdings(self, session):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        try:
            resp = self._call_api(session["obj"].get_holdings)
            raw_data = resp.get("data") if isinstance(resp, dict) else []
            if isinstance(raw_data, dict):
                raw_data = [raw_data]
            return {"status": "success", "raw": {"status": True, "data": raw_data}}
        except RuntimeError:
            raise
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def convert_position(self, session, exchange, scrip_token, transaction_type,
                         quantity, old_product_type, new_product_type, bo_order_id=None):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        try:
            req = PositionConversionRequest(
                exchange=exchange,
                scrip_token=scrip_token,
                transaction_type=transaction_type,
                quantity=quantity,
                old_product_type=old_product_type,
                new_product_type=new_product_type,
                bo_order_id=bo_order_id,
            )
            resp = self._call_api(session["obj"].convert_position, req)
            return {"status": "success", "raw": resp}
        except RuntimeError:
            raise
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def _get_ltp_map(self, session, items):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        try:
            resp = self._call_api(session["obj"].get_bulk_ltp, items)
            return {"status": "success", "raw": resp}
        except RuntimeError:
            raise
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_ltp(self, session, exchange, trading_symbol, symbol_token):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        try:
            resp = self._call_api(session["obj"].get_ltp, exchange, symbol_token)
            return {"status": "success", "raw": resp}
        except RuntimeError:
            raise
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_bulk_ltp(self, session, items):
        if not session or "obj" not in session:
            return {"status": "error", "error": "No active session object provided."}
        try:
            resp = self._call_api(session["obj"].get_bulk_ltp, items)
            return {"status": "success", "raw": resp}
        except RuntimeError:
            raise
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def get_symbol_token(self, tradingsymbol, prefer_field="exchange_token"):
        try:
            import json, os
            from pathlib import Path
            base_dir = Path(__file__).resolve().parent
            for fname in ("NSE.json", "ticker.json"):
                fpath = base_dir / fname
                if fpath.exists():
                    with open(fpath) as f:
                        data = json.load(f)
                    sym_upper = tradingsymbol.upper().replace("-EQ", "")
                    if isinstance(data, dict):
                        for k, v in data.items():
                            k_upper = k.upper().replace("-EQ", "")
                            if k_upper == sym_upper or k_upper == f"{sym_upper}-EQ":
                                return str(v) if not isinstance(v, dict) else str(v.get(prefer_field, v.get("token", "")))
                    elif isinstance(data, list):
                        for item in data:
                            sym = (item.get("tradingsymbol") or item.get("symbol") or "").upper().replace("-EQ", "")
                            if sym == sym_upper:
                                return str(item.get(prefer_field) or item.get("token") or item.get("exchange_token") or "")
        except Exception:
            pass
        return None
