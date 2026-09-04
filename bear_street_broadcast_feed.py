"""
ODIN broadcast WebSocket LTP feed for Bear Street.

Uses odin-market-feed SDK (pip install odin-market-feed websockets).
"""

from __future__ import annotations

import asyncio
import re
import threading
from typing import Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

FEED_FIELD_TOKEN = re.compile(r"(?:^|\|)7=(\d+)")
FEED_FIELD_LTP = re.compile(r"(?:^|\|)8=(\d+)")
FEED_FIELD_DECIMAL = re.compile(r"(?:^|\|)399=(\d+)")

DEFAULT_BROADCAST_SOCKET = "wss://globecapitalonline.com:8443"
DEFAULT_SEGMENT_ID = 1  # NSE cash/EQ
RECONNECT_MIN_SEC = 2.0
RECONNECT_MAX_SEC = 60.0


def parse_broadcast_message(message: str) -> Optional[Tuple[int, float]]:
    """Parse ODIN broadcast touchline message for scrip token + LTP."""
    if not message:
        return None
    token_m = FEED_FIELD_TOKEN.search(message)
    ltp_m = FEED_FIELD_LTP.search(message)
    if not token_m or not ltp_m:
        return None
    token = int(token_m.group(1))
    ltp_raw = int(ltp_m.group(1))
    dec_m = FEED_FIELD_DECIMAL.search(message)
    if dec_m:
        # Field 399 is the decimal divisor (e.g. 399=100 -> divide raw LTP by 100).
        divisor = int(dec_m.group(1))
        if divisor <= 0:
            divisor = 1
    else:
        divisor = 100
    ltp = ltp_raw / divisor
    if ltp <= 0:
        return None
    return token, ltp


def parse_socket_target(url: str) -> Tuple[str, int, bool]:
    parsed = urlparse(url)
    host = parsed.hostname or ""
    if not host:
        raise ValueError(f"invalid broadcast socket url: {url!r}")
    use_ssl = parsed.scheme.lower() == "wss"
    if parsed.port:
        port = parsed.port
    else:
        port = 443 if use_ssl else 80
    return host, port, use_ssl


def segment_feed_tokens(token_map: Dict[str, int], segment_id: int) -> List[str]:
    return [f"{segment_id}_{tok}" for tok in token_map.values()]


def _import_odin_market_feed_client():
    try:
        from odin_market_feed import ODINMarketFeedClient  # type: ignore

        return ODINMarketFeedClient
    except ImportError:
        return None


class BearStreetBroadcastFeed:
    """Background asyncio thread maintaining ODIN broadcast LTP cache."""

    def __init__(
        self,
        segment_id: int = DEFAULT_SEGMENT_ID,
        on_debug: Optional[Callable[[str], None]] = None,
    ):
        self.segment_id = segment_id
        self._on_debug = on_debug or (lambda _msg: None)
        self._price_lock = threading.Lock()
        self._config_lock = threading.Lock()
        self._prices: Dict[str, float] = {}
        self._token_to_sym: Dict[int, str] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._socket_url = ""
        self._user_id = ""
        self._broadcast_token = ""
        self._token_map: Dict[str, int] = {}
        self._config_version = 0
        self._connected = False

    def start(
        self,
        socket_url: str,
        user_id: str,
        broadcast_token: str,
        token_map: Dict[str, int],
    ) -> None:
        self._set_config(socket_url, user_id, broadcast_token, token_map)
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_thread,
            name="BearStreetBroadcastFeed",
            daemon=True,
        )
        self._thread.start()

    def update_symbols(self, token_map: Dict[str, int]) -> None:
        with self._config_lock:
            if token_map == self._token_map:
                return
            self._token_map = dict(token_map)
            self._rebuild_token_index()
            self._config_version += 1

    def update_credentials(
        self,
        socket_url: Optional[str] = None,
        user_id: Optional[str] = None,
        broadcast_token: Optional[str] = None,
    ) -> None:
        with self._config_lock:
            changed = False
            if socket_url is not None and socket_url != self._socket_url:
                self._socket_url = socket_url
                changed = True
            if user_id is not None and user_id != self._user_id:
                self._user_id = user_id
                changed = True
            if broadcast_token is not None and broadcast_token != self._broadcast_token:
                self._broadcast_token = broadcast_token
                changed = True
            if changed:
                self._config_version += 1

    def get_prices(self) -> Dict[str, float]:
        with self._price_lock:
            return dict(self._prices)

    def is_connected(self) -> bool:
        return self._connected

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)

    def _set_config(
        self,
        socket_url: str,
        user_id: str,
        broadcast_token: str,
        token_map: Dict[str, int],
    ) -> None:
        with self._config_lock:
            self._socket_url = (socket_url or DEFAULT_BROADCAST_SOCKET).strip()
            self._user_id = user_id or ""
            self._broadcast_token = broadcast_token or ""
            self._token_map = dict(token_map)
            self._rebuild_token_index()
            self._config_version += 1

    def _rebuild_token_index(self) -> None:
        self._token_to_sym = {tok: sym for sym, tok in self._token_map.items()}

    def _debug(self, message: str) -> None:
        try:
            self._on_debug(message)
        except Exception:
            pass

    def _snapshot_config(self) -> Tuple[str, str, str, Dict[str, int], int]:
        with self._config_lock:
            return (
                self._socket_url,
                self._user_id,
                self._broadcast_token,
                dict(self._token_map),
                self._config_version,
            )

    def _run_thread(self) -> None:
        try:
            asyncio.run(self._async_main())
        except Exception as exc:
            self._debug(f"broadcast thread exited: {exc}")

    async def _async_main(self) -> None:
        backoff = RECONNECT_MIN_SEC

        while not self._stop.is_set():
            socket_url, user_id, broadcast_token, token_map, version = self._snapshot_config()
            if not broadcast_token or not token_map:
                self._debug("broadcast waiting for token_map / broadcast_token")
                await asyncio.sleep(2.0)
                continue

            if not socket_url:
                socket_url = DEFAULT_BROADCAST_SOCKET

            client_cls = _import_odin_market_feed_client()
            if client_cls is None:
                self._debug("broadcast SDK missing (pip install odin-market-feed websockets)")
                await asyncio.sleep(30.0)
                continue

            try:
                host, port, use_ssl = parse_socket_target(socket_url)
            except ValueError as exc:
                self._debug(f"broadcast bad socket url: {exc}")
                await asyncio.sleep(30.0)
                continue

            client = client_cls()
            connected_evt = asyncio.Event()
            subscribed_version = -1

            async def on_open() -> None:
                self._connected = True
                connected_evt.set()
                self._debug(
                    f"broadcast connected user={user_id} "
                    f"tokens={segment_feed_tokens(token_map, self.segment_id)}"
                )

            def on_message(message: str) -> None:
                parsed = parse_broadcast_message(message)
                if not parsed:
                    return
                token, ltp = parsed
                sym = self._token_to_sym.get(token)
                if not sym:
                    return
                with self._price_lock:
                    self._prices[sym] = ltp

            def on_error(error: str) -> None:
                self._debug(f"broadcast error: {error}")

            client.on_open = on_open
            client.on_message = on_message
            client.on_error = on_error

            try:
                await client.connect(host, port, user_id, use_ssl, broadcast_token)
                await asyncio.wait_for(connected_evt.wait(), timeout=15.0)
                backoff = RECONNECT_MIN_SEC
                subscribed_version = version
                segment_tokens = segment_feed_tokens(token_map, self.segment_id)
                if segment_tokens:
                    await client.subscribe_ltp_touchline(segment_tokens)
                    self._debug(f"broadcast subscribed tokens={segment_tokens}")

                while not self._stop.is_set():
                    _, _, _, latest_map, latest_version = self._snapshot_config()
                    if latest_version != subscribed_version:
                        segment_tokens = segment_feed_tokens(latest_map, self.segment_id)
                        if segment_tokens:
                            await client.subscribe_ltp_touchline(segment_tokens)
                            subscribed_version = latest_version
                            self._debug(f"broadcast resubscribed tokens={segment_tokens}")
                    await asyncio.sleep(0.5)

            except asyncio.TimeoutError:
                self._debug("broadcast connect timeout")
            except Exception as exc:
                self._debug(f"broadcast connect failed: {type(exc).__name__}: {exc}")
            finally:
                self._connected = False
                try:
                    await client.disconnect()
                except Exception:
                    pass

            if self._stop.is_set():
                break

            self._debug(f"broadcast reconnect in {backoff:.0f}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, RECONNECT_MAX_SEC)
