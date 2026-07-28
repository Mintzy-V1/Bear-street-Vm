from datetime import datetime, timedelta
import requests
from dataclasses import asdict
from dotenv import load_dotenv, set_key, get_key
import os
import json

from bear_street_client.models.login import LoginRequest, LoginData, LoginResponse
from bear_street_client.models.logout import LogoutData
from bear_street_client.models.balance import BalanceData, BalanceResponse

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

        self.__save_token_to_env(self.token)

        return LoginResponse(
            status=response.get("status"),
            code=response.get("code"),
            message=response.get("message"),
            data=self.login_data,
        )

    def logout(self):
        response = self._delete("authentication/v1/user/session")

        set_key(self.env_file, "BEAR_STREET_TOKEN", "")
        set_key(self.env_file, "BEAR_STREET_TOKEN_EXPIRY", "")

        self.token = None
        self.broadcast_token = None
        self.headers.pop("Authorization", None)

        if self.debug:
            print("Logged out and removed token from env file")

        return response

    def get_balance(self):
        response = self._get("authentication/v1/user/balance")
        data = BalanceData(**response.get("data", {})) if response.get("data") else None
        return BalanceResponse(
            status=response.get("status"),
            code=response.get("code"),
            message=response.get("message"),
            data=data,
        )

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
            print(f"[{method}] {url} -> {response.status_code}")

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
                return True
        except (ValueError, TypeError):
            pass
        return False

    def __save_token_to_env(self, token, expiry_hours=24):
        expiry = datetime.now() + timedelta(hours=expiry_hours)
        set_key(self.env_file, "BEAR_STREET_TOKEN", token)
        set_key(self.env_file, "BEAR_STREET_TOKEN_EXPIRY", expiry.isoformat())

        if self.debug:
            print(f"Token saved to {self.env_file}, expires at {expiry}")
