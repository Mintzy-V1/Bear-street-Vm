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

                for sym in symbols:
                    try:
                        resp = self.broker.get_ltp(self._session, "NSE", sym, 0)
                        if resp.get("status") == "success":
                            raw = resp.get("raw", {})
                            data = raw.get("data", raw) if isinstance(raw, dict) else raw
                            ltp = None
                            if isinstance(data, dict):
                                ltp = data.get("ltp") or data.get("LTP") or data.get("last_price")
                            if ltp is not None:
                                price = float(ltp)
                                now = time.time()
                                prev = self._last_prices.get(sym)
                                if prev is None or abs(prev - price) > 1e-9:
                                    self._last_prices[sym] = price
                                    self.on_tick(sym, price, now)
                    except Exception:
                        pass
            except Exception as e:
                print(f"[LTP-BS] poll error: {e}")
                self._session = None
            time.sleep(self.poll_interval)
