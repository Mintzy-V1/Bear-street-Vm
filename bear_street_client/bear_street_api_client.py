from datetime import datetime, timedelta
import requests
from dataclasses import asdict
from dotenv import load_dotenv, set_key, get_key
import os
import json

from bear_street_client.models.login import LoginData, LoginResponse
from bear_street_client.models.balance import BalanceData, BalanceResponse
from bear_street_client.models.user_profile import UserProfileData, UserProfileResponse
from bear_street_client.models.position_conversion import PositionConversionRequest, PositionConversionResponse

from bear_street_client.exceptions import (
    BearStreetAPIError,
    BearStreetAuthError,
    BearStreetDataFetchError,
    BearStreetInvalidResponseError,
)


class BearStreetClient:

    def __init__(self, api_key, user_id, password, second_auth, source="WEBAPI",
                 base_url=None, debug=False, timeout=10, env_file=".env"):
        self.env_file = env_file
        load_dotenv(dotenv_path=self.env_file)

        self.debug = debug
        self.timeout = timeout
        self.request_session = requests.Session()
        self.base_url = base_url or os.environ.get("BEAR_STREET_BASE_URL", "http://localhost:3100")
        self.api_key = api_key
        self.user_id = user_id
        self.password = password
        self.second_auth = second_auth
        self.source = source

        self.token = None
        self.broadcast_token = None

        self.headers = {
            "Content-Type": "application/json",
        }

        if not self.api_key or not self.user_id or not self.password or not self.second_auth:
            raise ValueError("api_key, user_id, password, and second_auth are required")

    def login(self, get_new_token=False):
        if self.__check_existing_token() and not get_new_token:
            if self.debug:
                print("Using existing token from env file")
            return LoginResponse(status="success", code="s-101", message="Using existing token", data=None)

        payload = {
            "user_id": self.user_id,
            "login_type": "PASSWORD",
            "password": self.password,
            "second_auth": self.second_auth,
            "api_key": self.api_key,
            "source": self.source,
        }

        if self.debug:
            print(f"[LOGIN] POST /authentication/v1/user/session user_id={self.user_id}")

        response = self._post("authentication/v1/user/session", payload=payload)

        if not response or "data" not in response:
            raise BearStreetAuthError("Login failed. No valid response received.")

        data = response["data"]
        self.login_data = LoginData(**data) if data else None

        if "access_token" not in data:
            raise BearStreetAuthError("Login response missing access_token")

        self.token = data["access_token"]
        self.broadcast_token = data.get("broadcast_access_token")
        self.headers["Authorization"] = f"Bearer {self.token}"

        self.__save_token_to_env(self.token, self.broadcast_token)

        if self.debug:
            print(f"[LOGIN] Success. Token={self.token[:20]}... Broadcast={self.broadcast_token[:20] if self.broadcast_token else 'N/A'}...")

        return LoginResponse(
            status=response.get("status"),
            code=response.get("code"),
            message=response.get("message"),
            data=self.login_data,
        )

    def logout(self):
        if self.debug:
            print("[LOGOUT] DELETE /authentication/v1/user/session")

        response = self._delete("authentication/v1/user/session")

        set_key(self.env_file, "BEAR_STREET_TOKEN", "")
        set_key(self.env_file, "BEAR_STREET_TOKEN_EXPIRY", "")
        set_key(self.env_file, "BEAR_STREET_BROADCAST_TOKEN", "")

        self.token = None
        self.broadcast_token = None
        self.headers.pop("Authorization", None)

        if self.debug:
            print("[LOGOUT] Done, token cleared from env")

        return response

    def get_balance(self):
        if self.debug:
            print("[BALANCE] GET /authentication/v1/user/balance")

        response = self._get("authentication/v1/user/balance")
        data = BalanceData(**response.get("data", {})) if response.get("data") else None
        return BalanceResponse(
            status=response.get("status"),
            code=response.get("code"),
            message=response.get("message"),
            data=data,
        )

    def get_user_profile(self):
        if self.debug:
            print("[USER PROFILE] GET /authentication/v1/user/profile")

        response = self._get("authentication/v1/user/profile")
        data = UserProfileData(**response.get("data", {})) if response.get("data") else None
        return UserProfileResponse(
            status=response.get("status"),
            code=response.get("code"),
            message=response.get("message"),
            data=data,
        )

    # -------------------------------------------------------------------------
    # ORDER ENDPOINTS
    # -------------------------------------------------------------------------

    def place_order(self, order_details):
        if self.debug:
            print(f"[PLACE ORDER] POST /transactional/v1/orders/regular")
        response = self._post("transactional/v1/orders/regular", payload=order_details)
        return response

    def modify_order(self, exchange, order_id, modify_details):
        if self.debug:
            print(f"[MODIFY ORDER] PUT /transactional/v1/orders/regular/{exchange}/{order_id}")
        response = self._put(f"transactional/v1/orders/regular/{exchange}/{order_id}", payload=modify_details)
        return response

    def cancel_order(self, exchange, order_id):
        if self.debug:
            print(f"[CANCEL ORDER] DELETE /transactional/v1/orders/regular/{exchange}/{order_id}")
        response = self._delete(f"transactional/v1/orders/regular/{exchange}/{order_id}")
        return response

    def place_cover_order(self, order_details):
        if self.debug:
            print("[PLACE COVER] POST /transactional/v1/orders/cover")
        response = self._post("transactional/v1/orders/cover", payload=order_details)
        return response

    def modify_cover_order(self, exchange, order_id, modify_details):
        if self.debug:
            print(f"[MODIFY COVER] PUT /transactional/v1/orders/cover/{exchange}/{order_id}")
        response = self._put(f"transactional/v1/orders/cover/{exchange}/{order_id}", payload=modify_details)
        return response

    def cancel_cover_order(self, exchange, order_id):
        if self.debug:
            print(f"[CANCEL COVER] DELETE /transactional/v1/orders/cover/{exchange}/{order_id}")
        response = self._delete(f"transactional/v1/orders/cover/{exchange}/{order_id}")
        return response

    def place_bracket_order(self, order_details):
        if self.debug:
            print("[PLACE BRACKET] POST /transactional/v1/orders/bracket")
        response = self._post("transactional/v1/orders/bracket", payload=order_details)
        return response

    def modify_bracket_order(self, exchange, order_id, modify_details):
        if self.debug:
            print(f"[MODIFY BRACKET] PUT /transactional/v1/orders/bracket/{exchange}/{order_id}")
        response = self._put(f"transactional/v1/orders/bracket/{exchange}/{order_id}", payload=modify_details)
        return response

    def exit_bracket_order(self, order_id):
        if self.debug:
            print(f"[EXIT BRACKET] DELETE /transactional/v1/orders/bracket/{order_id}")
        response = self._delete(f"transactional/v1/orders/bracket/{order_id}")
        return response

    def get_order_book(self, offset=1, limit=100, order_id=None):
        if self.debug:
            print(f"[ORDER BOOK] GET /transactional/v1/orders offset={offset} limit={limit}")
        params = {"offset": offset, "limit": limit}
        if order_id:
            params["order_id"] = order_id
        response = self._get("transactional/v1/orders", params=params)
        return response

    def get_trade_book(self, offset=1, limit=100, order_id=None):
        if self.debug:
            print(f"[TRADE BOOK] GET /transactional/v1/trades offset={offset} limit={limit}")
        params = {"offset": offset, "limit": limit}
        if order_id:
            params["order_id"] = order_id
        response = self._get("transactional/v1/trades", params=params)
        return response

    def get_order_history(self, order_id):
        if self.debug:
            print(f"[ORDER HISTORY] GET /transactional/v1/orders/{order_id}")
        response = self._get(f"transactional/v1/orders/{order_id}")
        return response

    # -------------------------------------------------------------------------
    # PORTFOLIO ENDPOINTS
    # -------------------------------------------------------------------------

    def get_positions(self):
        if self.debug:
            print("[POSITIONS] GET /portfolio/v1/positions")
        response = self._get("portfolio/v1/positions")
        return response

    def get_holdings(self):
        if self.debug:
            print("[HOLDINGS] GET /portfolio/v1/holdings")
        response = self._get("portfolio/v1/holdings")
        return response

    def convert_position(self, req: PositionConversionRequest):
        if self.debug:
            print(f"[CONVERT] PUT /portfolio/v1/positions/convert")
        response = self._put("portfolio/v1/positions/convert", payload=req.get_dict())
        return response

    def get_ltp(self, exchange, symbol_token):
        if self.debug:
            print(f"[LTP] GET /marketdata/v1/ltp/{exchange}/{symbol_token}")
        response = self._get(f"marketdata/v1/ltp/{exchange}/{symbol_token}")
        return response

    def get_bulk_ltp(self, items):
        if self.debug:
            print(f"[BULK LTP] POST /marketdata/v1/ltp items={len(items)}")
        response = self._post("marketdata/v1/ltp", payload={"items": items})
        return response

    def set_access_token(self, token):
        self.token = token
        self.headers["Authorization"] = f"Bearer {token}"

    def _get(self, endpoint, params=None):
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        return self._request("GET", url, params=params)

    def _post(self, endpoint, payload=None, params=None):
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        return self._request("POST", url, payload=payload, params=params)

    def _put(self, endpoint, payload=None, params=None):
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        return self._request("PUT", url, payload=payload, params=params)

    def _delete(self, endpoint, params=None):
        url = f"{self.base_url.rstrip('/')}/{endpoint.lstrip('/')}"
        return self._request("DELETE", url, params=params)

    def _request(self, method, url, payload=None, params=None):
        response = self.request_session.request(
            method, url, json=payload, params=params, headers=self.headers, timeout=self.timeout
        )

        if self.debug:
            print(f"[HTTP] {method} {url} -> {response.status_code}")

        try:
            response_json = response.json() if response.text else None
        except requests.exceptions.JSONDecodeError:
            raise BearStreetAPIError(f"Invalid JSON response. Status: {response.status_code}")

        if response_json is None:
            raise BearStreetAPIError(f"Empty response from {url}. Status: {response.status_code}")

        if response.status_code == 200:
            return response_json
        elif response.status_code == 401:
            raise BearStreetAuthError(
                f"Unauthorized for {url}",
                status_code=401,
                response_message=response_json.get("message"),
                response_data=response_json.get("data"),
            )
        elif response.status_code == 400:
            raise BearStreetInvalidResponseError(
                f"Bad request for {url}",
                status_code=400,
                response_message=response_json.get("message"),
                response_data=response_json.get("data"),
            )
        elif response.status_code == 404:
            raise BearStreetDataFetchError(
                f"Not found: {url}",
                response_message=response_json.get("message"),
            )
        elif response.status_code == 405:
            raise BearStreetInvalidResponseError(
                f"Method not allowed for {url}",
                status_code=405,
                response_message=response_json.get("message"),
            )
        elif response.status_code == 429:
            raise BearStreetAPIError(
                f"Rate limit exceeded for {url}",
                status_code=429,
                response_message=response_json.get("message", "Too Many Requests"),
                response_data=response_json.get("data", {}),
            )
        elif response.status_code >= 500:
            raise BearStreetAPIError(
                f"Server error for {url}",
                status_code=response.status_code,
                response_message=response_json.get("message"),
                response_data=response_json.get("data"),
            )

        return response_json

    def __check_existing_token(self):
        token = get_key(self.env_file, "BEAR_STREET_TOKEN")
        token_expiry = get_key(self.env_file, "BEAR_STREET_TOKEN_EXPIRY")

        if not token or not token_expiry:
            return False

        try:
            expiry = datetime.fromisoformat(token_expiry)
            if datetime.now() + timedelta(minutes=5) < expiry:
                self.token = token
                self.headers["Authorization"] = f"Bearer {self.token}"
                self.broadcast_token = get_key(self.env_file, "BEAR_STREET_BROADCAST_TOKEN")
                return True
        except (ValueError, TypeError):
            pass
        return False

    def __save_token_to_env(self, token, broadcast_token=None, expiry_hours=24):
        expiry = datetime.now() + timedelta(hours=expiry_hours)
        set_key(self.env_file, "BEAR_STREET_TOKEN", token)
        set_key(self.env_file, "BEAR_STREET_TOKEN_EXPIRY", expiry.isoformat())
        if broadcast_token:
            set_key(self.env_file, "BEAR_STREET_BROADCAST_TOKEN", broadcast_token)

        if self.debug:
            print(f"Token saved to {self.env_file}, expires at {expiry}")
