# Bear Street API Server — 3-Session Implementation Plan

## Session 1: Foundation — Client SDK & Authentication

**Goal:** Set up project structure, implement the Bear Street HTTP client SDK, and wire up authentication (login/logout/balance).

### Tasks

1. Create project directory structure mirroring `market_hub_corrected` conventions:
   - `bear_street_client/` — SDK package (HTTP client, models, exceptions, constants)
   - `bear_street_client/models/` — dataclass request/response models
   - `utils/` — shared utilities
2. Implement `bear_street_client/` core:
   - `constants.py` — enums (exchanges, product types, order types, etc.)
   - `exceptions.py` — custom exception classes (BearStreetAPIError, BearStreetAuthError, etc.)
   - `tradex_api_client.py` → `bear_street_api_client.py` — HTTP client with POST/GET/PUT/DELETE methods, token management, .env persistence
   - Model files for: Login, Logout, Balance
3. Implement `broker_bear_street.py` — broker adapter class with the same interface as `broker_tradex.BrokerConnector`:
   - `__init__`, `_build_client`, `_create_session`, `restore_session`, `get_session`, `get_ws_credentials`
   - Login/logout/balance API calls
4. Create stub files for remaining models and methods (placeholders for Sessions 2 & 3).
5. Update `broker_factory.py` (copy from market_hub and add `BROKER_BEAR_STREET` support) — **Note:** This is a separate copy for this repo.
6. Initial commit with SDK + auth working end-to-end.

### Deliverables

- Working login/logout/balance via Bear Street API
- SDK client with token management
- Broker adapter with standard interface

---

## Session 2: Order Management

**Goal:** Implement all order-related endpoints — place, modify, cancel regular orders, cover orders, bracket orders, trade book, order book, order history.

### Tasks

1. Add models for:
   - Regular order (place/modify/cancel)
   - Cover order (place/modify/cancel)
   - Bracket order (place/modify/cancel/exit)
   - Trade book, Order book, Order history
2. Add API client methods for each endpoint.
3. Add broker adapter methods:
   - `place_order`, `modify_order`, `cancel_order`
   - `place_cover_order`, `modify_cover_order`, `cancel_cover_order`
   - `place_bracket_order`, `modify_bracket_order`, `exit_bracket_order`
   - `get_trade_book`, `get_order_book`, `get_order_history`
4. Add order normalization helpers (map Bear Street order statuses to Angel-like format used by auto_trader).
5. Add order confirmation polling (`_wait_for_order_confirmation`).

### Deliverables

- Full order lifecycle working
- Order/trade book retrieval
- Session 1 features stable

---

## Session 3: Portfolio, WebSocket Feed & Factory Integration

**Goal:** Implement portfolio endpoints (positions, holdings, position conversion), real-time WebSocket streaming via socket.io, and finalize factory integration.

### Tasks

1. Add models for:
   - Positions (daily/expiry)
   - Position conversion
   - Holdings
2. Add API client methods for portfolio endpoints.
3. Add broker adapter methods:
   - `get_positions`, `get_holdings`, `get_account_balance`
   - `convert_position`
4. Implement WebSocket client (`bear_street_websocket_client.py`):
   - socket.io connection
   - Authentication with `jToken`
   - Subscribe to `MSG:DATA` events
   - Parse order (`ORD_NRML`) and trade (`TRD_MSG`) responses
   - Auto-reconnect
5. Wire Bear Street into `broker_factory.py`:
   - Add `BROKER_BEAR_STREET` constant
   - Add env var setup/teardown
   - Add connector creation
   - Add LTP stream creation
6. Final `api_server.py` — FastAPI server with Bear Street routes integrated.
7. Write end-to-end test(s) for the full flow.

### Deliverables

- Portfolio data available
- Real-time order/trade streaming via WebSocket
- Full factory integration
- API server serving Bear Street

---

## Project Structure (Final)

```
bear_street_api_server/
├── BEAR_STREET_API_DOCS.md      # API documentation
├── SESSION_PLAN.md               # This file
├── requirements.txt              # Python dependencies
├── api_server.py                 # FastAPI application
├── broker_factory.py             # Broker factory
├── broker_bear_street.py         # Bear Street broker adapter
├── bear_street_client/           # SDK package
│   ├── __init__.py
│   ├── constants.py
│   ├── exceptions.py
│   ├── bear_street_api_client.py
│   ├── bear_street_websocket_client.py
│   └── models/
│       ├── __init__.py
│       ├── login.py
│       ├── logout.py
│       ├── balance.py
│       ├── new_order.py
│       ├── modify_order.py
│       ├── cancel_order.py
│       ├── cover_order.py
│       ├── bracket_order.py
│       ├── trades_book.py
│       ├── orders_book.py
│       ├── order_history.py
│       ├── positions.py
│       ├── position_conversion.py
│       └── holdings.py
├── utils/
│   └── __init__.py
└── logs/
```
