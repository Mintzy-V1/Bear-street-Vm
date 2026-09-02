import threading
import time
from typing import Callable, Iterable, Optional


class BearStreetLTPPoller:
    def __init__(
        self,
        broker,
        on_tick: Callable[[str, float, float], None],
        poll_interval: float = 2.0,
    ):
        self.broker = broker
        self.on_tick = on_tick
        self.poll_interval = poll_interval
        self._symbols: set = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._last_prices: dict = {}
        self._session = None
        self._debug_last: dict = {}

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
        sym_list = [s.upper() for s in symbols]
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
            self._symbols.add(symbol.upper())

    def unsubscribe(self, symbol: str) -> None:
        with self._lock:
            self._symbols.discard(symbol.upper())

    def stop(self) -> None:
        self._stop.set()

    def _get_symbol_token(self, symbol: str) -> Optional[int]:
        try:
            token = self.broker.get_symbol_token(symbol)
            if token:
                return int(token)
        except Exception:
            pass
        return None

    def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self._session is None:
                    self._session = self.broker.get_session()
                with self._lock:
                    symbols = list(self._symbols)
                if not symbols:
                    time.sleep(self.poll_interval)
                    continue

                try:
                    positions = self.broker.get_positions(self._session)
                except Exception as e:
                    self._debug(
                        "positions:error",
                        f"[LTP-BS] get_positions error: {e}",
                        interval=10.0,
                    )
                    positions = {}
                price_map = {}
                if positions.get("status") == "success":
                    rows = positions.get("raw", {}).get("data", [])
                    self._debug(
                        "positions:success",
                        (
                            f"[LTP-BS] positions success rows={len(rows)} "
                            f"watching={symbols}"
                        ),
                        interval=10.0,
                    )
                    for row in rows:
                        sym = (row.get("tradingsymbol") or row.get("symbol") or "").upper().replace("-EQ", "")
                        if sym in symbols:
                            price_map[sym] = row.get("ltp") or row.get("net_price") or row.get("last_price")
                    self._debug(
                        "positions:price-map",
                        f"[LTP-BS] price_map symbols={list(price_map.keys())}",
                        interval=10.0,
                    )
                else:
                    self._debug(
                        "positions:not-success",
                        f"[LTP-BS] positions not-success response={positions}",
                        interval=10.0,
                    )

                for sym in symbols:
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
                        if prev is None or abs(prev - price) > 1e-9:
                            self._last_prices[sym] = price
                            self._debug(
                                f"emit:{sym}",
                                f"[LTP-BS] emit_tick symbol={sym} ltp={price:.2f} changed=True",
                                interval=5.0,
                            )
                            self.on_tick(sym, price, now)
                        elif prev is not None:
                            # Always re-emit (even if price is unchanged) so the
                            # trader's live_pnl push keeps the Redis key fresh
                            # (TTL 5s) even when ODIN's position price is static.
                            self._debug(
                                f"emit:{sym}",
                                f"[LTP-BS] emit_tick symbol={sym} ltp={price:.2f} changed=False",
                                interval=5.0,
                            )
                            self.on_tick(sym, price, now)
                    except Exception as e:
                        self._debug(
                            f"symbol-error:{sym}",
                            f"[LTP-BS] symbol loop error symbol={sym}: {e}",
                            interval=10.0,
                        )
            except Exception as e:
                print(f"[LTP-BS] poll error: {e}")
                self._session = None
            time.sleep(self.poll_interval)
