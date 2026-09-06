import json
import threading
import time
from datetime import datetime, time as dt_time, timedelta, timezone
from typing import Callable, Dict, Iterable, List, Optional, Set

from bear_street_broadcast_feed import (
    DEFAULT_BROADCAST_SOCKET,
    BearStreetBroadcastFeed,
)

# Must match auto_trader_exposure_expansion._now_market_time() / _shared_ltp_bar().
MARKET_TZ = timezone(timedelta(hours=5, minutes=30))


class BearStreetLTPPoller:
    """
    Bear Street LTP poller.

    Primary: ODIN broadcast WebSocket (broadCastSocket + broadcast_access_token).
    Fallback: shared Redis candle LTP, Upstox 1m intraday close, then live positions.
    """

    def __init__(
        self,
        broker,
        on_tick: Callable[[str, float, float], None],
        poll_interval: float = 2.0,
        market_client=None,
    ):
        self.broker = broker
        self.on_tick = on_tick
        self.poll_interval = poll_interval
        self.market_client = market_client
        self._symbols: Set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_prices: dict = {}
        self._session = None
        self._debug_last: dict = {}
        self._token_cache: Dict[str, int] = {}
        self._upstox_last_fetch: Dict[str, float] = {}
        self._broadcast_feed: Optional[BearStreetBroadcastFeed] = None

    def _debug(self, key: str, message: str, interval: float = 10.0) -> None:
        try:
            now = time.time()
            last = float(self._debug_last.get(key, 0.0) or 0.0)
            if interval <= 0 or now - last >= interval:
                self._debug_last[key] = now
                print(message, flush=True)
        except Exception:
            pass

    def start(self, symbols: Iterable[str]) -> None:
        sym_list = [s.upper().replace("-EQ", "") for s in symbols]
        print(f"[LTP-BS] start() polling {len(sym_list)} symbols: {sym_list}")
        with self._lock:
            self._symbols.update(sym_list)
        if self._thread and self._thread.is_alive():
            if self._session is not None:
                self._ensure_broadcast_feed(self._session, list(self._symbols))
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_loop, name="BearStreetLTPPoller", daemon=True)
        self._thread.start()

    def subscribe(self, symbol: str) -> None:
        with self._lock:
            self._symbols.add(symbol.upper().replace("-EQ", ""))
            symbols = list(self._symbols)
        if self._session is not None:
            self._ensure_broadcast_feed(self._session, symbols)

    def unsubscribe(self, symbol: str) -> None:
        with self._lock:
            self._symbols.discard(symbol.upper().replace("-EQ", ""))
            symbols = list(self._symbols)
        if self._session is not None:
            self._ensure_broadcast_feed(self._session, symbols)

    def stop(self) -> None:
        self._stop.set()
        if self._broadcast_feed is not None:
            self._broadcast_feed.stop()
            self._broadcast_feed = None

    def _normalize_symbol(self, symbol: str) -> str:
        return (symbol or "").upper().replace("-EQ", "")

    def _now_market_time(self) -> datetime:
        return datetime.now(MARKET_TZ)

    def _get_symbol_token(self, symbol: str) -> Optional[int]:
        sym = self._normalize_symbol(symbol)
        cached = self._token_cache.get(sym)
        if cached:
            return cached
        try:
            token = self.broker.get_symbol_token(sym, "NSE_EQ")
            if token:
                token_int = int(token)
                self._token_cache[sym] = token_int
                return token_int
        except Exception as e:
            self._debug(
                f"token:error:{sym}",
                f"[LTP-BS] token resolve failed symbol={sym}: {e}",
                interval=30.0,
            )
        return None

    def _resolve_tokens(self, symbols: List[str]) -> Dict[str, int]:
        token_map: Dict[str, int] = {}
        for sym in symbols:
            sym = self._normalize_symbol(sym)
            token = self._get_symbol_token(sym)
            if token:
                token_map[sym] = token
            else:
                self._debug(
                    f"token:missing:{sym}",
                    f"[LTP-BS] quote skip no_token symbol={sym}",
                    interval=30.0,
                )
        return token_map

    def _get_broadcast_socket(self, session) -> str:
        sock = (session or {}).get("broadcast_socket") or ""
        if sock:
            return sock.strip()
        obj = (session or {}).get("obj")
        login_data = getattr(obj, "login_data", None) if obj else None
        others = getattr(login_data, "others", None) if login_data else None
        if isinstance(others, dict):
            return (others.get("broadCastSocket") or others.get("broadcastSocket") or "").strip()
        return ""

    def _ensure_broadcast_feed(self, session, symbols: List[str]) -> None:
        token_map = self._resolve_tokens(symbols)
        if not token_map:
            return

        socket_url = self._get_broadcast_socket(session) or DEFAULT_BROADCAST_SOCKET
        broadcast_token = (session or {}).get("broadcast_token") or getattr(
            self.broker, "broadcast_access_token", None
        )
        user_id = (session or {}).get("user") or getattr(self.broker, "user_id", None) or getattr(
            self.broker, "user", None
        )
        if not broadcast_token or not user_id:
            self._debug(
                "broadcast:missing-creds",
                "[LTP-BS] broadcast skip missing broadcast_token or user_id",
                interval=30.0,
            )
            return

        if self._broadcast_feed is None:
            self._broadcast_feed = BearStreetBroadcastFeed(
                on_debug=lambda msg: self._debug("broadcast", f"[LTP-BS] {msg}", interval=10.0),
            )
            self._broadcast_feed.start(socket_url, user_id, broadcast_token, token_map)
            return

        self._broadcast_feed.update_credentials(socket_url, user_id, broadcast_token)
        self._broadcast_feed.update_symbols(token_map)

    def _fetch_broadcast_prices(self, symbols: List[str]) -> Dict[str, float]:
        if self._broadcast_feed is None:
            return {}
        cached = self._broadcast_feed.get_prices()
        price_map: Dict[str, float] = {}
        for sym in symbols:
            sym = self._normalize_symbol(sym)
            ltp = cached.get(sym)
            if ltp is not None and ltp > 0:
                price_map[sym] = float(ltp)
        if price_map:
            self._debug(
                "broadcast:ok",
                f"[LTP-BS] broadcast prices={price_map} connected={self._broadcast_feed.is_connected()}",
                interval=10.0,
            )
        return price_map

    def _extract_ltp(self, row) -> Optional[float]:
        if row is None:
            return None
        if isinstance(row, (int, float)):
            val = float(row)
            return val if val > 0 else None
        if not isinstance(row, dict):
            return None
        for key in ("ltp", "LTP", "lastPrice", "last_price", "net_price", "close_price"):
            raw = row.get(key)
            if raw is None:
                continue
            try:
                val = float(raw)
                if val > 0:
                    return val
            except (TypeError, ValueError):
                continue
        data = row.get("data")
        if isinstance(data, dict):
            return self._extract_ltp(data)
        return None

    def _symbol_from_row(self, row, token_to_sym: Dict[int, str]) -> Optional[str]:
        if not isinstance(row, dict):
            return None
        for key in ("symbol", "tradingsymbol", "tradingSymbol", "sym"):
            raw = row.get(key)
            if raw:
                return self._normalize_symbol(str(raw))
        for key in ("symbolToken", "symbol_token", "scrip_token", "token", "code"):
            raw = row.get(key)
            if raw is None:
                continue
            try:
                return token_to_sym.get(int(raw))
            except (TypeError, ValueError):
                continue
        return None

    def _parse_quote_payload(self, payload, token_to_sym: Dict[int, str]) -> Dict[str, float]:
        price_map: Dict[str, float] = {}
        if payload is None:
            return price_map

        if isinstance(payload, dict):
            sym = self._symbol_from_row(payload, token_to_sym)
            ltp = self._extract_ltp(payload)
            if sym and ltp is not None:
                price_map[sym] = ltp
                return price_map

            data = payload.get("data")
            if isinstance(data, list):
                payload = data
            elif isinstance(data, dict):
                sym = self._symbol_from_row(data, token_to_sym)
                ltp = self._extract_ltp(data)
                if sym and ltp is not None:
                    price_map[sym] = ltp
                return price_map

        if isinstance(payload, list):
            for row in payload:
                sym = self._symbol_from_row(row, token_to_sym)
                ltp = self._extract_ltp(row)
                if sym and ltp is not None:
                    price_map[sym] = ltp
        return price_map

    def _unwrap_broker_response(self, resp) -> Optional[object]:
        if not isinstance(resp, dict):
            return resp
        if resp.get("status") not in ("success", "SUCCESS", True):
            return None
        raw = resp.get("raw")
        if raw is not None:
            return raw
        return resp.get("data", resp)

    def _fetch_quote_prices(self, session, symbols: List[str]) -> Dict[str, float]:
        token_map = self._resolve_tokens(symbols)
        if not token_map:
            return {}

        token_to_sym = {token: sym for sym, token in token_map.items()}
        price_map: Dict[str, float] = {}

        if len(token_map) == 1:
            sym, token = next(iter(token_map.items()))
            for exchange in self._quote_exchanges:
                try:
                    resp = self.broker.get_ltp(session, exchange, sym, token)
                except Exception as e:
                    self._debug(
                        f"quote:single:error:{sym}:{exchange}",
                        f"[LTP-BS] get_ltp error symbol={sym} exchange={exchange}: {e}",
                        interval=10.0,
                    )
                    continue
                payload = self._unwrap_broker_response(resp)
                parsed = self._parse_quote_payload(payload, token_to_sym)
                if parsed:
                    price_map.update(parsed)
                    self._debug(
                        "quote:single:ok",
                        f"[LTP-BS] quote single symbol={sym} exchange={exchange} prices={parsed}",
                        interval=10.0,
                    )
                    break
            return price_map

        items = [
            {"exchange": self._quote_exchanges[0], "symbolToken": token}
            for token in token_to_sym.keys()
        ]
        try:
            resp = self.broker.get_bulk_ltp(session, items)
        except Exception as e:
            self._debug(
                "quote:bulk:error",
                f"[LTP-BS] get_bulk_ltp error symbols={symbols}: {e}",
                interval=10.0,
            )
            return price_map

        payload = self._unwrap_broker_response(resp)
        parsed = self._parse_quote_payload(payload, token_to_sym)
        if parsed:
            price_map.update(parsed)
            self._debug(
                "quote:bulk:ok",
                f"[LTP-BS] quote bulk symbols={symbols} prices={parsed}",
                interval=10.0,
            )
            return price_map

        # Retry bulk with alternate exchange label if first attempt returned nothing.
        alt_items = [
            {"exchange": self._quote_exchanges[1], "symbolToken": token}
            for token in token_to_sym.keys()
        ]
        try:
            resp = self.broker.get_bulk_ltp(session, alt_items)
            payload = self._unwrap_broker_response(resp)
            parsed = self._parse_quote_payload(payload, token_to_sym)
            if parsed:
                price_map.update(parsed)
                self._debug(
                    "quote:bulk:alt:ok",
                    f"[LTP-BS] quote bulk alt exchange={self._quote_exchanges[1]} prices={parsed}",
                    interval=10.0,
                )
        except Exception as e:
            self._debug(
                "quote:bulk:alt:error",
                f"[LTP-BS] get_bulk_ltp alt exchange error: {e}",
                interval=10.0,
            )
        return price_map

    def _shared_ltp_bar(self, now: datetime) -> datetime:
        local = now
        if getattr(local, "tzinfo", None) is not None:
            local = local.replace(tzinfo=None)
        start = datetime.combine(local.date(), dt_time(9, 30))
        end = datetime.combine(local.date(), dt_time(15, 0))
        if local < start:
            return start
        asof = local if local <= end else end
        slot = (int((asof - start).total_seconds() // 60) // 15) * 15
        bar = start + timedelta(minutes=slot)
        if bar > end:
            bar = end
        return bar

    def _parse_shared_ltp(self, cached) -> Optional[float]:
        if cached is None:
            return None
        try:
            val = float(cached)
            return val if val > 0 else None
        except (ValueError, TypeError):
            pass
        try:
            data = json.loads(cached)
            val = float(data["price"])
            return val if val > 0 else None
        except Exception:
            return None

    def _redis_client(self):
        if self.market_client is not None:
            return getattr(self.market_client, "redis_client", None)
        return None

    def _fetch_redis_ltp(self, symbols: List[str]) -> Dict[str, float]:
        redis_client = self._redis_client()
        if redis_client is None:
            return {}

        now = self._now_market_time()
        bar = self._shared_ltp_bar(now)
        price_map: Dict[str, float] = {}
        for sym in symbols:
            sym = self._normalize_symbol(sym)
            redis_key = (
                f"price:ltp:{sym}.NS:{bar.strftime('%Y-%m-%d')}:{bar.strftime('%H%M')}"
            )
            try:
                cached = redis_client.get(redis_key)
                val = self._parse_shared_ltp(cached)
                if val is not None:
                    price_map[sym] = val
            except Exception as e:
                self._debug(
                    f"redis:error:{sym}",
                    f"[LTP-BS] redis fallback error symbol={sym}: {e}",
                    interval=30.0,
                )
        if price_map:
            self._debug(
                "redis:ok",
                f"[LTP-BS] redis fallback prices={price_map}",
                interval=10.0,
            )
        return price_map

    def _fetch_upstox_ltp(self, symbols: List[str]) -> Dict[str, float]:
        if self.market_client is None or not hasattr(self.market_client, "fetch_price"):
            return {}

        now = self._now_market_time()
        bar = self._shared_ltp_bar(now)
        bar_dt = bar.replace(tzinfo=MARKET_TZ) if bar.tzinfo is None else bar
        price_map: Dict[str, float] = {}
        min_interval = 30.0

        for sym in symbols:
            sym = self._normalize_symbol(sym)
            last_fetch = float(self._upstox_last_fetch.get(sym, 0.0) or 0.0)
            if time.time() - last_fetch < min_interval:
                continue
            try:
                px = self.market_client.fetch_price(
                    ticker=f"{sym}.NS",
                    target_datetime=bar_dt,
                    candle="1m",
                )
            except Exception as e:
                self._debug(
                    f"upstox:error:{sym}",
                    f"[LTP-BS] upstox fallback error symbol={sym}: {e}",
                    interval=30.0,
                )
                continue

            self._upstox_last_fetch[sym] = time.time()
            if not px:
                continue
            try:
                close = float(px.get("Close") or 0.0)
            except (TypeError, ValueError):
                close = 0.0
            if close > 0:
                price_map[sym] = close

        if price_map:
            self._debug(
                "upstox:ok",
                f"[LTP-BS] upstox fallback prices={price_map}",
                interval=10.0,
            )
        return price_map

    def _fetch_position_prices(self, session, symbols: List[str]) -> Dict[str, float]:
        wanted = {self._normalize_symbol(s) for s in symbols}
        price_map: Dict[str, float] = {}
        try:
            positions = self.broker.get_positions(session)
        except Exception as e:
            self._debug(
                "positions:error",
                f"[LTP-BS] get_positions error: {e}",
                interval=10.0,
            )
            return price_map

        if positions.get("status") != "success":
            self._debug(
                "positions:not-success",
                f"[LTP-BS] positions not-success response={positions}",
                interval=10.0,
            )
            return price_map

        rows = positions.get("raw", {}).get("data", [])
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            return price_map

        for row in rows:
            sym = self._normalize_symbol(
                row.get("tradingsymbol") or row.get("symbol") or ""
            )
            if sym not in wanted:
                continue
            ltp = self._extract_ltp(row)
            if ltp is not None:
                price_map[sym] = ltp

        if price_map:
            self._debug(
                "positions:fallback",
                f"[LTP-BS] position fallback prices={price_map}",
                interval=10.0,
            )
        return price_map

    def _emit_ticks(self, symbols: List[str], price_map: Dict[str, float]) -> None:
        for sym in symbols:
            sym = self._normalize_symbol(sym)
            try:
                ltp = price_map.get(sym)
                if ltp is None:
                    self._debug(
                        f"missing-ltp:{sym}",
                        (
                            f"[LTP-BS] missing_ltp symbol={sym} "
                            f"available_price_symbols={list(price_map.keys())}"
                        ),
                        interval=10.0,
                    )
                    continue
                price = float(ltp)
                now = time.time()
                prev = self._last_prices.get(sym)
                changed = prev is None or abs(prev - price) > 1e-9
                if changed:
                    self._last_prices[sym] = price
                self._debug(
                    f"emit:{sym}",
                    (
                        f"[LTP-BS] emit_tick symbol={sym} ltp={price:.2f} "
                        f"changed={changed}"
                    ),
                    interval=5.0,
                )
                # Re-emit even when unchanged so Redis live_pnl TTL stays fresh.
                self.on_tick(sym, price, now)
            except Exception as e:
                self._debug(
                    f"symbol-error:{sym}",
                    f"[LTP-BS] symbol loop error symbol={sym}: {e}",
                    interval=10.0,
                )

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self._session is None:
                    self._session = self.broker.get_session()
                with self._lock:
                    symbols = [self._normalize_symbol(s) for s in self._symbols]
                if not symbols:
                    time.sleep(self.poll_interval)
                    continue

                self._ensure_broadcast_feed(self._session, symbols)
                price_map = self._fetch_broadcast_prices(symbols)

                missing = [s for s in symbols if s not in price_map]
                if missing:
                    price_map.update(self._fetch_redis_ltp(missing))
                    missing = [s for s in missing if s not in price_map]

                if missing:
                    price_map.update(self._fetch_upstox_ltp(missing))
                    missing = [s for s in missing if s not in price_map]

                if missing:
                    price_map.update(self._fetch_position_prices(self._session, missing))

                self._emit_ticks(symbols, price_map)
            except Exception as e:
                print(f"[LTP-BS] poll error: {e}")
                self._session = None
            time.sleep(self.poll_interval)
