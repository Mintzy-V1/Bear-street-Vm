import json
import threading
import time
from datetime import datetime, time as dt_time, timedelta
from typing import Callable, Dict, Iterable, List, Optional, Set


class BearStreetLTPPoller:
    """
    Bear Street LTP poller.

    Primary: ODIN market quote APIs (get_ltp / get_bulk_ltp) for watched symbols.
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
        self._quote_exchanges = ("NSE", "NSE_EQ")

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
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._poll_loop, name="BearStreetLTPPoller", daemon=True)
        self._thread.start()

    def subscribe(self, symbol: str) -> None:
        with self._lock:
            self._symbols.add(symbol.upper().replace("-EQ", ""))

    def unsubscribe(self, symbol: str) -> None:
        with self._lock:
            self._symbols.discard(symbol.upper().replace("-EQ", ""))

    def stop(self) -> None:
        self._stop.set()

    def _normalize_symbol(self, symbol: str) -> str:
        return (symbol or "").upper().replace("-EQ", "")

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

        now = datetime.now()
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

        now = datetime.now()
        bar = self._shared_ltp_bar(now)
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
                    target_datetime=bar,
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

                price_map = self._fetch_quote_prices(self._session, symbols)

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
