"""
Standalone diagnostic for Bear Street / ODIN quote LTP paths.

STEP 2-3: REST get_ltp / get_bulk_ltp (often HTTP 500 — deprecated on ODIN).
STEP 4:   Broadcast WebSocket via login others.broadCastSocket + broadcast_access_token.

Usage:
    python debug_bear_street_ltp_quotes.py
    python debug_bear_street_ltp_quotes.py --symbols INDIGO,ICICIBANK
    python debug_bear_street_ltp_quotes.py --symbols ACC --raw-only
    python debug_bear_street_ltp_quotes.py --skip-rest
    python debug_bear_street_ltp_quotes.py --broadcast-wait 20 --verbose

Requires BEAR_STREET_* env vars (same as test_bear_street.py / .env on VM).
Broadcast step also needs: pip install odin-market-feed websockets
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import requests
from dotenv import load_dotenv

from bear_street_broadcast_feed import (
    parse_broadcast_message,
    parse_socket_target,
    segment_feed_tokens,
)

load_dotenv()

TAG = "[QUOTE-DEBUG]"
DEFAULT_SYMBOLS = ["INDIGO", "ICICIBANK", "ACC"]
QUOTE_EXCHANGES = ("NSE", "NSE_EQ", "BSE_EQ")
# ODIN broadcast feed token format: {market_segment_id}_{scrip_token}
DEFAULT_BROADCAST_SEGMENT = 1  # NSE cash/EQ in ODIN market-feed SDK examples
LTP_KEYS = ("ltp", "LTP", "lastPrice", "last_price", "net_price", "close_price")
SYMBOL_KEYS = ("symbol", "tradingsymbol", "tradingSymbol", "sym")
TOKEN_KEYS = ("symbolToken", "symbol_token", "scrip_token", "token", "code", "ScripCode", "scripCode")


def _log(msg: str) -> None:
    print(f"{TAG} {msg}", flush=True)


def _pretty(obj: Any, verbose: bool, limit: int = 1200) -> str:
    try:
        text = json.dumps(obj, indent=2, default=str)
    except Exception:
        text = repr(obj)
    if not verbose and len(text) > limit:
        return text[:limit] + "\n... [truncated; use --verbose for full JSON]"
    return text


def _normalize_symbol(symbol: str) -> str:
    return (symbol or "").upper().replace("-EQ", "")


@dataclass
class RowResult:
    symbol: str
    token: Optional[int]
    exchange: str
    call_type: str
    http_status: Optional[int] = None
    sdk_ok: bool = False
    sdk_error: str = ""
    body_has_ltp: bool = False
    poller_parser_ok: bool = False
    enhanced_parser_ok: bool = False
    extracted_ltp: Optional[float] = None
    verdict: str = "UNKNOWN"
    notes: List[str] = field(default_factory=list)


@dataclass
class BroadcastResult:
    socket_url: str
    user_id: str
    segment_tokens: List[str]
    prices: Dict[str, float] = field(default_factory=dict)
    message_count: int = 0
    connected: bool = False
    verdict: str = "UNKNOWN"
    notes: List[str] = field(default_factory=list)


def extract_ltp(row: Any) -> Optional[float]:
    if row is None:
        return None
    if isinstance(row, (int, float)):
        val = float(row)
        return val if val > 0 else None
    if not isinstance(row, dict):
        return None
    for key in LTP_KEYS:
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
        return extract_ltp(data)
    return None


def symbol_from_row(row: Any, token_to_sym: Dict[int, str]) -> Optional[str]:
    if not isinstance(row, dict):
        return None
    for key in SYMBOL_KEYS:
        raw = row.get(key)
        if raw:
            return _normalize_symbol(str(raw))
    for key in TOKEN_KEYS:
        raw = row.get(key)
        if raw is None:
            continue
        try:
            return token_to_sym.get(int(raw))
        except (TypeError, ValueError):
            continue
    return None


def parse_quote_payload_poller(payload: Any, token_to_sym: Dict[int, str]) -> Dict[str, float]:
    """Same logic as bear_street_ltp_poller.BearStreetLTPPoller._parse_quote_payload."""
    price_map: Dict[str, float] = {}
    if payload is None:
        return price_map

    if isinstance(payload, dict):
        sym = symbol_from_row(payload, token_to_sym)
        ltp = extract_ltp(payload)
        if sym and ltp is not None:
            price_map[sym] = ltp
            return price_map

        data = payload.get("data")
        if isinstance(data, list):
            payload = data
        elif isinstance(data, dict):
            sym = symbol_from_row(data, token_to_sym)
            ltp = extract_ltp(data)
            if sym and ltp is not None:
                price_map[sym] = ltp
            return price_map

    if isinstance(payload, list):
        for row in payload:
            sym = symbol_from_row(row, token_to_sym)
            ltp = extract_ltp(row)
            if sym and ltp is not None:
                price_map[sym] = ltp
    return price_map


def parse_quote_payload_enhanced(payload: Any, token_to_sym: Dict[int, str]) -> Dict[str, float]:
    """
    Poller parser + fallback: if LTP exists but symbol missing, map by single token
    when only one symbol is under test.
    """
    parsed = parse_quote_payload_poller(payload, token_to_sym)
    if parsed:
        return parsed

    if len(token_to_sym) != 1:
        return parsed

    sym, _token = next(iter(token_to_sym.items()))

    def _walk(obj: Any) -> Optional[float]:
        val = extract_ltp(obj)
        if val is not None:
            return val
        if isinstance(obj, dict):
            data = obj.get("data")
            if data is not None:
                return _walk(data)
        if isinstance(obj, list):
            for row in obj:
                val = _walk(row)
                if val is not None:
                    return val
        return None

    ltp = _walk(payload)
    if ltp is not None:
        parsed[sym] = ltp
    return parsed


def unwrap_broker_response(resp: Any) -> Any:
    if not isinstance(resp, dict):
        return resp
    if resp.get("status") not in ("success", "SUCCESS", True):
        return None
    raw = resp.get("raw")
    if raw is not None:
        return raw
    return resp.get("data", resp)


def body_has_ltp_field(payload: Any) -> bool:
    return extract_ltp(payload) is not None


def raw_http_get(
    base_url: str,
    headers: Dict[str, str],
    exchange: str,
    token: int,
    timeout: float,
) -> Tuple[int, Any, str, float]:
    url = f"{base_url.rstrip('/')}/marketdata/v1/ltp/{exchange}/{token}"
    started = time.time()
    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
        elapsed_ms = (time.time() - started) * 1000.0
        text = resp.text or ""
        try:
            body = resp.json() if text else None
        except json.JSONDecodeError:
            body = {"_non_json_body": text[:500]}
        return resp.status_code, body, "", elapsed_ms
    except Exception as exc:
        elapsed_ms = (time.time() - started) * 1000.0
        return None, None, str(exc), elapsed_ms


def raw_http_post_bulk(
    base_url: str,
    headers: Dict[str, str],
    items: List[dict],
    timeout: float,
) -> Tuple[Optional[int], Any, str, float]:
    url = f"{base_url.rstrip('/')}/marketdata/v1/ltp"
    started = time.time()
    try:
        resp = requests.post(url, headers=headers, json={"items": items}, timeout=timeout)
        elapsed_ms = (time.time() - started) * 1000.0
        text = resp.text or ""
        try:
            body = resp.json() if text else None
        except json.JSONDecodeError:
            body = {"_non_json_body": text[:500]}
        return resp.status_code, body, "", elapsed_ms
    except Exception as exc:
        elapsed_ms = (time.time() - started) * 1000.0
        return None, None, str(exc), elapsed_ms


def _login_others(client) -> Dict[str, Any]:
    login_data = getattr(client, "login_data", None)
    if login_data is None:
        return {}
    others = getattr(login_data, "others", None)
    return others if isinstance(others, dict) else {}


def _broadcast_socket_urls(client) -> List[str]:
    others = _login_others(client)
    urls: List[str] = []
    primary = (others.get("broadCastSocket") or others.get("broadcastSocket") or "").strip()
    if primary:
        urls.append(primary)
    secondary = others.get("secondBroadCastSocket") or []
    if isinstance(secondary, list):
        for item in secondary:
            item = (item or "").strip()
            if item and item not in urls:
                urls.append(item)
    return urls


_parse_socket_target = parse_socket_target
_segment_feed_tokens = segment_feed_tokens
parse_broadcast_feed_message = parse_broadcast_message


def _import_odin_market_feed_client():
    try:
        from odin_market_feed import ODINMarketFeedClient  # type: ignore

        return ODINMarketFeedClient
    except ImportError:
        return None


async def _probe_broadcast_socket(
    *,
    socket_url: str,
    user_id: str,
    broadcast_token: str,
    token_map: Dict[str, int],
    segment_id: int,
    wait_seconds: float,
    verbose: bool,
    subscribe_mode: str,
) -> BroadcastResult:
    segment_tokens = _segment_feed_tokens(token_map, segment_id)
    token_to_sym = {tok: sym for sym, tok in token_map.items()}
    result = BroadcastResult(
        socket_url=socket_url,
        user_id=user_id,
        segment_tokens=segment_tokens,
    )

    client_cls = _import_odin_market_feed_client()
    if client_cls is None:
        result.verdict = "SDK_MISSING"
        result.notes.append("pip install odin-market-feed websockets")
        return result

    if not broadcast_token:
        result.verdict = "NO_BROADCAST_TOKEN"
        result.notes.append("login response missing broadcast_access_token")
        return result

    try:
        host, port, use_ssl = _parse_socket_target(socket_url)
    except ValueError as exc:
        result.verdict = "BAD_SOCKET_URL"
        result.notes.append(str(exc))
        return result

    client = client_cls()
    connected = asyncio.Event()
    errors: List[str] = []

    async def on_open() -> None:
        connected.set()
        if subscribe_mode == "touchline":
            await client.subscribe_touchline(segment_tokens, response_type="0", ltp_change_only=False)
        else:
            await client.subscribe_ltp_touchline(segment_tokens)

    def on_message(message: str) -> None:
        result.message_count += 1
        if verbose or result.message_count <= 5:
            preview = message if verbose else (message[:240] + ("..." if len(message) > 240 else ""))
            _log(f"broadcast msg#{result.message_count}: {preview}")
        parsed = parse_broadcast_feed_message(message)
        if not parsed:
            return
        token, ltp = parsed
        sym = token_to_sym.get(token)
        if sym and ltp > 0:
            result.prices[sym] = ltp

    def on_error(error: str) -> None:
        errors.append(str(error))
        _log(f"broadcast error: {error}")

    client.on_open = on_open
    client.on_message = on_message
    client.on_error = on_error

    try:
        _log(
            f"broadcast connect host={host} port={port} ssl={use_ssl} "
            f"user={user_id} tokens={segment_tokens} mode={subscribe_mode}"
        )
        await client.connect(host, port, user_id, use_ssl, broadcast_token)
        try:
            await asyncio.wait_for(connected.wait(), timeout=15.0)
            result.connected = True
        except asyncio.TimeoutError:
            result.verdict = "CONNECT_TIMEOUT"
            result.notes.append("on_open not fired within 15s")
            return result

        await asyncio.sleep(max(1.0, wait_seconds))
    except Exception as exc:
        result.verdict = "CONNECT_FAILED"
        result.notes.append(f"{type(exc).__name__}: {exc}")
        if verbose:
            _log(traceback.format_exc())
        return result
    finally:
        try:
            await client.disconnect()
        except Exception:
            pass

    if errors:
        result.notes.extend(errors[:3])

    missing = [sym for sym in token_map if sym not in result.prices]
    if result.prices and not missing:
        result.verdict = "BROADCAST_WORKING"
    elif result.prices:
        result.verdict = "BROADCAST_PARTIAL"
        result.notes.append(f"missing_symbols={missing}")
    elif result.message_count > 0:
        result.verdict = "BROADCAST_NO_LTP_PARSE"
        result.notes.append("received messages but no 7=/8= LTP fields parsed")
    else:
        result.verdict = "BROADCAST_NO_DATA"
        result.notes.append("no broadcast messages received during wait window")
    return result


def run_broadcast_tests(
    client,
    session: Dict[str, Any],
    token_map: Dict[str, int],
    *,
    wait_seconds: float,
    segment_id: int,
    verbose: bool,
) -> List[BroadcastResult]:
    urls = _broadcast_socket_urls(client)
    if not urls:
        row = BroadcastResult(
            socket_url="",
            user_id=str(session.get("user") or ""),
            segment_tokens=[],
            verdict="NO_SOCKET_URL",
        )
        row.notes.append("login others.broadCastSocket missing")
        return [row]

    broadcast_token = (
        session.get("broadcast_token")
        or getattr(getattr(client, "login_data", None), "broadcast_access_token", None)
        or ""
    )
    user_id = str(session.get("user") or getattr(client, "user_id", "") or "")

    results: List[BroadcastResult] = []
    for url in urls:
        _log(f"--- broadcast socket {url} ---")
        for mode in ("ltp_touchline", "touchline"):
            _log(f"broadcast subscribe mode={mode}")
            result = asyncio.run(
                _probe_broadcast_socket(
                    socket_url=url,
                    user_id=user_id,
                    broadcast_token=broadcast_token,
                    token_map=token_map,
                    segment_id=segment_id,
                    wait_seconds=wait_seconds,
                    verbose=verbose,
                    subscribe_mode=mode,
                )
            )
            results.append(result)
            _log(
                f"broadcast verdict={result.verdict} prices={result.prices} "
                f"messages={result.message_count} connected={result.connected}"
            )
            if result.verdict == "BROADCAST_WORKING":
                break
        if results and results[-1].verdict == "BROADCAST_WORKING":
            break
    return results


def print_broadcast_summary(results: List[BroadcastResult], requested_symbols: List[str]) -> None:
    print("\n" + "=" * 72)
    print(f"{TAG} BROADCAST SUMMARY")
    print("=" * 72)
    for idx, row in enumerate(results, start=1):
        print(f"[{idx}] url={row.socket_url or 'n/a'} verdict={row.verdict}")
        print(f"     connected={row.connected} messages={row.message_count} prices={row.prices}")
        for note in row.notes:
            print(f"     note: {note}")

    working = [r for r in results if r.verdict == "BROADCAST_WORKING"]
    partial = [r for r in results if r.verdict == "BROADCAST_PARTIAL"]
    print("\n" + "-" * 72)
    if working:
        print(f"{TAG} BROADCAST: WORKING — use broadCastSocket + broadcast_access_token in bear_street_ltp_poller.py")
        print(f"{TAG} RECOMMENDED: replace REST get_ltp/get_bulk_ltp with ODIN broadcast subscribe_ltp_touchline")
    elif partial:
        print(f"{TAG} BROADCAST: PARTIAL — some symbols received: {partial[-1].prices}")
        print(f"{TAG} RECOMMENDED: verify segment id / token mapping for: {requested_symbols}")
    elif any(r.verdict == "SDK_MISSING" for r in results):
        print(f"{TAG} BROADCAST: SDK_MISSING — run: pip install odin-market-feed websockets")
    else:
        print(f"{TAG} BROADCAST: NOT WORKING — check socket URL, broadcast token, market hours, broker feed entitlement")


def classify_verdict(
    http_status: Optional[int],
    has_ltp: bool,
    poller_ok: bool,
    enhanced_ok: bool,
    sdk_error: str,
) -> Tuple[str, List[str]]:
    notes: List[str] = []
    if sdk_error:
        notes.append(f"sdk_error={sdk_error}")
    if http_status is None:
        return "NETWORK_ERROR", notes
    if http_status == 401:
        return "AUTH_ERROR", notes
    if http_status == 404:
        return "API_NOT_FOUND", notes + ["REST /marketdata/v1/ltp may be deprecated"]
    if http_status >= 400:
        return f"HTTP_{http_status}", notes
    if http_status == 200 and not has_ltp:
        return "API_EMPTY_BODY", notes + ["HTTP 200 but no ltp field found in JSON"]
    if http_status == 200 and has_ltp and not poller_ok and enhanced_ok:
        return "PARSE_ISSUE", notes + ["API returns LTP; poller parser drops it (field/shape)"]
    if http_status == 200 and has_ltp and not poller_ok and not enhanced_ok:
        return "PARSE_ISSUE", notes + ["LTP present but symbol mapping failed"]
    if http_status == 200 and poller_ok:
        return "WORKING", notes
    return "UNKNOWN", notes


def run_single_tests(
    broker,
    session,
    client,
    base_url: str,
    headers: Dict[str, str],
    symbol: str,
    token: int,
    verbose: bool,
    raw_only: bool,
) -> List[RowResult]:
    rows: List[RowResult] = []
    token_to_sym = {token: _normalize_symbol(symbol)}

    for exchange in QUOTE_EXCHANGES:
        row = RowResult(
            symbol=symbol,
            token=token,
            exchange=exchange,
            call_type="GET single",
        )

        status, body, net_err, elapsed_ms = raw_http_get(base_url, headers, exchange, token, client.timeout)
        row.http_status = status
        _log(f"HTTP GET /marketdata/v1/ltp/{exchange}/{token} status={status} elapsed_ms={elapsed_ms:.1f}")
        if net_err:
            _log(f"network_error={net_err}")
        else:
            _log(f"raw_body=\n{_pretty(body, verbose)}")

        row.body_has_ltp = body_has_ltp_field(body)
        poller_parsed = parse_quote_payload_poller(body, token_to_sym)
        enhanced_parsed = parse_quote_payload_enhanced(body, token_to_sym)
        row.poller_parser_ok = bool(poller_parsed)
        row.enhanced_parser_ok = bool(enhanced_parsed)
        if enhanced_parsed:
            row.extracted_ltp = next(iter(enhanced_parsed.values()))

        if not raw_only:
            try:
                sdk_body = client.get_ltp(exchange, token)
                row.sdk_ok = True
                _log(f"SDK get_ltp({exchange}, {token}) OK\n{_pretty(sdk_body, verbose)}")
                broker_resp = broker.get_ltp(session, exchange, symbol, token)
                _log(f"broker.get_ltp status={broker_resp.get('status')}")
                if broker_resp.get("status") != "success":
                    row.sdk_error = str(broker_resp.get("error") or broker_resp)
                else:
                    unwrapped = unwrap_broker_response(broker_resp)
                    _log(f"broker unwrapped=\n{_pretty(unwrapped, verbose)}")
                    bp = parse_quote_payload_poller(unwrapped, token_to_sym)
                    _log(f"broker+poller_parser prices={bp}")
            except Exception as exc:
                row.sdk_ok = False
                row.sdk_error = f"{type(exc).__name__}: {exc}"
                _log(f"SDK/broker get_ltp FAILED: {row.sdk_error}")
                if verbose:
                    _log(traceback.format_exc())

        row.verdict, row.notes = classify_verdict(
            row.http_status,
            row.body_has_ltp,
            row.poller_parser_ok,
            row.enhanced_parser_ok,
            row.sdk_error,
        )
        rows.append(row)
        _log(f"verdict={row.verdict} poller_parser={row.poller_parser_ok} enhanced_parser={row.enhanced_parser_ok}")
        print("-" * 72, flush=True)

    return rows


def run_bulk_tests(
    broker,
    session,
    client,
    base_url: str,
    headers: Dict[str, str],
    token_map: Dict[str, int],
    verbose: bool,
    raw_only: bool,
) -> List[RowResult]:
    rows: List[RowResult] = []
    token_to_sym = {tok: sym for sym, tok in token_map.items()}
    symbols_label = ",".join(token_map.keys())

    bulk_variants = [
        ("symbolToken", QUOTE_EXCHANGES[0]),
        ("symbolToken", QUOTE_EXCHANGES[1]),
        ("scrip_token", QUOTE_EXCHANGES[1]),
    ]

    for field_name, exchange in bulk_variants:
        items = [{field_name: tok, "exchange": exchange} for tok in token_to_sym.keys()]
        row = RowResult(
            symbol=symbols_label,
            token=None,
            exchange=exchange,
            call_type=f"POST bulk ({field_name})",
        )

        status, body, net_err, elapsed_ms = raw_http_post_bulk(base_url, headers, items, client.timeout)
        row.http_status = status
        _log(f"HTTP POST /marketdata/v1/ltp items={items} status={status} elapsed_ms={elapsed_ms:.1f}")
        if net_err:
            _log(f"network_error={net_err}")
        else:
            _log(f"raw_body=\n{_pretty(body, verbose)}")

        row.body_has_ltp = body_has_ltp_field(body)
        poller_parsed = parse_quote_payload_poller(body, token_to_sym)
        enhanced_parsed = parse_quote_payload_enhanced(body, token_to_sym)
        row.poller_parser_ok = bool(poller_parsed)
        row.enhanced_parser_ok = bool(enhanced_parsed)
        if enhanced_parsed:
            row.extracted_ltp = next(iter(enhanced_parsed.values()), None)

        if not raw_only:
            try:
                sdk_body = client.get_bulk_ltp(items)
                row.sdk_ok = True
                _log(f"SDK get_bulk_ltp OK\n{_pretty(sdk_body, verbose)}")
                broker_resp = broker.get_bulk_ltp(session, items)
                _log(f"broker.get_bulk_ltp status={broker_resp.get('status')}")
                if broker_resp.get("status") != "success":
                    row.sdk_error = str(broker_resp.get("error") or broker_resp)
                else:
                    unwrapped = unwrap_broker_response(broker_resp)
                    _log(f"broker unwrapped=\n{_pretty(unwrapped, verbose)}")
                    bp = parse_quote_payload_poller(unwrapped, token_to_sym)
                    _log(f"broker+poller_parser prices={bp}")
            except Exception as exc:
                row.sdk_ok = False
                row.sdk_error = f"{type(exc).__name__}: {exc}"
                _log(f"SDK/broker get_bulk_ltp FAILED: {row.sdk_error}")
                if verbose:
                    _log(traceback.format_exc())

        row.verdict, row.notes = classify_verdict(
            row.http_status,
            row.body_has_ltp,
            row.poller_parser_ok,
            row.enhanced_parser_ok,
            row.sdk_error,
        )
        rows.append(row)
        _log(f"verdict={row.verdict} poller_parser={row.poller_parser_ok} enhanced_parser={row.enhanced_parser_ok}")
        print("-" * 72, flush=True)

    return rows


def print_summary(
    all_rows: List[RowResult],
    broadcast_results: Optional[List[BroadcastResult]] = None,
    requested_symbols: Optional[List[str]] = None,
) -> None:
    print("\n" + "=" * 72)
    print(f"{TAG} REST SUMMARY")
    print("=" * 72)
    if not all_rows:
        print(f"{TAG} REST tests skipped")
    else:
        header = f"{'Symbol':<14} {'Exch':<8} {'Type':<22} {'HTTP':<6} {'LTP?':<5} {'Poller':<7} {'Verdict'}"
        print(header)
        print("-" * len(header))
        for r in all_rows:
            print(
                f"{r.symbol:<14} {r.exchange:<8} {r.call_type:<22} "
                f"{str(r.http_status or 'ERR'):<6} "
                f"{'Y' if r.body_has_ltp else 'N':<5} "
                f"{'Y' if r.poller_parser_ok else 'N':<7} "
                f"{r.verdict}"
            )
            for note in r.notes:
                print(f"  note: {note}")

    verdicts = {r.verdict for r in all_rows}
    working = [r for r in all_rows if r.verdict == "WORKING"]
    api_nf = [r for r in all_rows if r.verdict == "API_NOT_FOUND"]
    parse_issues = [r for r in all_rows if r.verdict == "PARSE_ISSUE"]
    has_ltp_no_parse = [r for r in all_rows if r.body_has_ltp and not r.poller_parser_ok]
    rest_500 = all_rows and all(r.verdict == "HTTP_500" for r in all_rows)

    broadcast_ok = bool(broadcast_results) and any(
        r.verdict in ("BROADCAST_WORKING", "BROADCAST_PARTIAL") for r in broadcast_results
    )

    print("\n" + "-" * 72)
    if working:
        print(f"{TAG} REST OVERALL: QUOTES WORKING for some exchange/payload combinations")
        print(f"{TAG} RECOMMENDED: wire working exchange into bear_street_ltp_poller.py")
    elif has_ltp_no_parse:
        print(f"{TAG} REST OVERALL: API RETURNS LTP — PARSER BUG (not API dead)")
        print(f"{TAG} RECOMMENDED: fix bear_street_ltp_poller._parse_quote_payload (ScripCode / symbol-less LTP)")
    elif api_nf and not has_ltp_no_parse:
        print(f"{TAG} REST OVERALL: API_ISSUE — REST /marketdata/v1/ltp not available (404)")
        print(f"{TAG} RECOMMENDED: implement ODIN broadcast price websocket (broadcast_access_token)")
    elif rest_500 and broadcast_ok:
        print(f"{TAG} REST OVERALL: REST LTP DEAD (HTTP 500) — expected on ODIN")
        print(f"{TAG} FINAL VERDICT: USE BROADCAST WEBSOCKET (STEP 4) instead of REST get_ltp")
    elif rest_500:
        print(f"{TAG} REST OVERALL: REST LTP DEAD (HTTP 500) on all endpoints")
        print(f"{TAG} RECOMMENDED: install odin-market-feed and verify STEP 4 broadcast socket")
    elif parse_issues:
        print(f"{TAG} REST OVERALL: PARSE_ISSUE — check summary rows above")
    elif all_rows:
        print(f"{TAG} REST OVERALL: INCONCLUSIVE — review raw_body logs above")
        print(f"{TAG} unique_verdicts={sorted(verdicts)}")
    if broadcast_results:
        print_broadcast_summary(broadcast_results, requested_symbols or [])


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose Bear Street ODIN quote LTP APIs")
    parser.add_argument(
        "--symbols",
        default=",".join(DEFAULT_SYMBOLS),
        help="Comma-separated symbols (default: INDIGO,ICICIBANK,ACC)",
    )
    parser.add_argument("--raw-only", action="store_true", help="Only raw HTTP layer (skip SDK/broker wrapper)")
    parser.add_argument("--verbose", action="store_true", help="Print full JSON bodies (no truncation)")
    parser.add_argument("--skip-bulk", action="store_true", help="Skip bulk LTP tests")
    parser.add_argument("--skip-rest", action="store_true", help="Skip REST /marketdata/v1/ltp tests (broadcast only)")
    parser.add_argument("--skip-broadcast", action="store_true", help="Skip broadcast WebSocket LTP test")
    parser.add_argument("--broadcast-wait", type=float, default=15.0, help="Seconds to wait for broadcast ticks (default 15)")
    parser.add_argument("--broadcast-segment", type=int, default=DEFAULT_BROADCAST_SEGMENT, help="ODIN market segment id (default 1 = NSE EQ)")
    args = parser.parse_args()

    symbols = [_normalize_symbol(s) for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        print("ERROR: no symbols provided", file=sys.stderr)
        return 1

    required = ["BEAR_STREET_API_KEY", "BEAR_STREET_USER_ID", "BEAR_STREET_PASSWORD", "BEAR_STREET_SECOND_AUTH"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        print(f"ERROR: missing env vars: {', '.join(missing)}", file=sys.stderr)
        return 1

    os.environ.setdefault("BEAR_STREET_DEBUG", "true")

    from broker_bear_street import BrokerConnector

    _log("=" * 72)
    _log("Bear Street ODIN quote LTP diagnostic")
    _log(f"symbols={symbols} raw_only={args.raw_only} verbose={args.verbose}")
    _log("=" * 72)

    broker = BrokerConnector()
    base_url = broker.base_url
    _log(f"base_url={base_url}")

    try:
        session = broker.get_session()
    except Exception as exc:
        _log(f"LOGIN FAILED: {exc}")
        if args.verbose:
            _log(traceback.format_exc())
        return 1

    client = session["obj"]
    token = session.get("token") or ""
    broadcast = session.get("broadcast_token") or ""
    _log(f"login user={session.get('user')} access_token={str(token)[:24]}... broadcast_token={'yes' if broadcast else 'no'}")
    socket_urls = _broadcast_socket_urls(client)
    if socket_urls:
        _log(f"login broadCastSocket={socket_urls[0]}")
    else:
        _log("login broadCastSocket missing in login_data.others")

    headers = dict(client.headers)
    headers.setdefault("Content-Type", "application/json")

    token_map: Dict[str, int] = {}
    _log("-" * 72)
    _log("STEP 1 — scrip token resolve (NSE_EQ master)")
    for sym in symbols:
        raw = broker.get_symbol_token(sym, "NSE_EQ")
        if not raw:
            _log(f"token MISSING symbol={sym}")
            continue
        tok = int(raw)
        token_map[sym] = tok
        _log(f"token OK symbol={sym} token={tok}")

    if not token_map:
        _log("FATAL: no symbols resolved to tokens — cannot test quotes")
        return 1

    all_rows: List[RowResult] = []
    broadcast_results: List[BroadcastResult] = []

    if not args.skip_rest:
        _log("-" * 72)
        _log("STEP 2 — single-symbol GET /marketdata/v1/ltp/{exchange}/{token}")
        for sym, tok in token_map.items():
            _log(f"--- symbol={sym} token={tok} ---")
            all_rows.extend(
                run_single_tests(
                    broker, session, client, base_url, headers,
                    sym, tok, args.verbose, args.raw_only,
                )
            )

        if not args.skip_bulk and len(token_map) >= 1:
            _log("-" * 72)
            _log("STEP 3 — bulk POST /marketdata/v1/ltp")
            all_rows.extend(
                run_bulk_tests(
                    broker, session, client, base_url, headers,
                    token_map, args.verbose, args.raw_only,
                )
            )
    else:
        _log("STEP 2-3 skipped (--skip-rest)")

    if not args.skip_broadcast:
        _log("-" * 72)
        _log("STEP 4 — broadcast WebSocket LTP (broadCastSocket + broadcast_access_token)")
        broadcast_results = run_broadcast_tests(
            client,
            session,
            token_map,
            wait_seconds=args.broadcast_wait,
            segment_id=args.broadcast_segment,
            verbose=args.verbose,
        )

    print_summary(all_rows, broadcast_results, symbols)
    return 0


if __name__ == "__main__":
    sys.exit(main())
