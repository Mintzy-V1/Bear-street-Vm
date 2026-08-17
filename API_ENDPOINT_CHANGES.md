# ODIN B2C API Endpoint Changes

Comparison of what was in the code **before** vs what was changed to match the new ODIN B2C REST docs.

Files touched: `bear_street_client/bear_street_api_client.py`, models, `constants.py`, `broker_bear_street.py`, `broker_factory.py`, `api_server.py`.

---

## Global (all endpoints)

| | Before | After |
|---|---|---|
| Headers | `Content-Type: application/json` only. `Authorization` added after login. | Also sends `x-api-key` on every request. `Authorization: Bearer {access_token}` still added after login. |
| Order IDs in URL paths | Sent raw, e.g. `NWSYF00005>3` | URI-encoded, because docs say path `order_id` must be encoded |

---

## 1. User

### 1.1 Send OTP

| | Before | After |
|---|---|---|
| Endpoint | Not present | Still not added |
| Docs | `POST /authentication/v1/user/password/reset/send-otp` | — |

### 1.2 Login

`POST /authentication/v1/user/session`

**Path:** unchanged (already correct)

**Payload before**
```json
{
  "user_id": "...",
  "login_type": "PASSWORD",
  "password": "...",
  "second_auth": "...",
  "api_key": "...",
  "source": "WEBAPI"
}
```

**Payload after**
```json
{
  "user_id": "...",
  "login_type": "PASSWORD",
  "password": "...",
  "second_auth_type": "OTP",
  "second_auth": "...",
  "api_key": "...",
  "source": "WEBAPI"
}
```

- `login_type` is no longer hardcoded; it comes from credentials (default `PASSWORD`)
- Added `second_auth_type` (default `OTP`)
- Optional device fields (`UDID`, `version`, `deviceinfo`, etc.) were not added

### 1.3 Logout

`DELETE /authentication/v1/user/session`

Unchanged. Path and empty body were already correct. Now also sends `x-api-key`.

### 1.4 Validate Session

| | Before | After |
|---|---|---|
| Endpoint | Not present | Still not added |
| Docs | `PUT /authentication/v1/user/session` | — |

### 1.5 Balance

`GET /authentication/v1/user/balance`

Unchanged. Path was already correct.

### User Profile (not in new docs)

`GET /authentication/v1/user/profile`

Left as-is. This endpoint is not in the new ODIN REST spec.

---

## 2. Order

### 2.1 Place Order

`POST /transactional/v1/orders/regular`

**Path:** unchanged

**Payload:** already matched docs (`scrip_info`, `transaction_type`, `product_type`, `order_type`, `quantity`, `price`, `trigger_price`, `disclosed_quantity`, `validity`, `validity_days`, `is_amo`, `order_identifier`, `part_code`, `algo_id`, `strategy_id`, `vender_code`)

**Response parsing (in `broker_bear_street.py`)**

| Before | After |
|---|---|
| Looked for `data.order_id` | Looks for `data.orderId` first (docs field), then `data.order_id` |

### 2.2 Modify Order

`PUT /transactional/v1/orders/regular/{exchange}/{order_id}`

**Path:** unchanged except `order_id` is now URI-encoded

**Payload:** already matched docs

### 2.3 Cancel Order

`DELETE /transactional/v1/orders/regular/{exchange}/{order_id}`

**Path:** unchanged except `order_id` is now URI-encoded

### 2.4 Place Cover Order

`POST /transactional/v1/orders/cover`

**Path:** unchanged

**Payload field rename**

| Before | After |
|---|---|
| `vender_Code` | `vender_code` |

### 2.5 Modify Cover Order

`PUT /transactional/v1/orders/cover/{exchange}/{order_id}`

Unchanged except URI-encoded `order_id`

### 2.6 Cancel Cover Order

`DELETE /transactional/v1/orders/cover/{exchange}/{order_id}`

Unchanged except URI-encoded `order_id`

### 2.7 Place Bracket Order

`POST /transactional/v1/orders/bracket`

**Path:** unchanged

**Payload field rename:** `vender_Code` → `vender_code`

### 2.8 Modify Bracket Order

`PUT /transactional/v1/orders/bracket/{exchange}/{order_id}`

Unchanged except URI-encoded `order_id`

### 2.9 Exit Bracket Order

| | Before | After |
|---|---|---|
| Path | `DELETE /transactional/v1/orders/bracket/{order_id}` | `DELETE /transactional/v1/orders/bracket/{exchange}/{order_id}` |
| Function | `exit_bracket_order(order_id)` | `exit_bracket_order(exchange, order_id)` |

Broker layer now looks up `exchange` from the order book (fallback `NSE_EQ`).

### 2.10 Order Book

`GET /transactional/v1/orders`

| | Before | After |
|---|---|---|
| Query params | `offset`, `limit`, `order_id` | `offset`, `limit`, `orderStatus` (`1`=Pending, `2`=Completed, `-1`=All) |

### 2.11 Order History

`GET /transactional/v1/orders/{order_id}`

Unchanged except URI-encoded `order_id`

### 2.12 Place Multileg / Spread

| | Before | After |
|---|---|---|
| Endpoint | Not present | Still not added |
| Docs | `POST /transactional/v1/orders/multileg` | — |

### 2.13 Cancel Multileg / Spread

| | Before | After |
|---|---|---|
| Endpoint | Not present | Still not added |
| Docs | `PUT /transactional/v1/orders/multileg/{order_flag}/{gateway_order_no}` | — |

### 2.14 Trade Book

`GET /transactional/v1/trades`

| | Before | After |
|---|---|---|
| Query params | `offset`, `limit`, `order_id` | Same, plus optional `order_ids` (comma-separated) |

---

## 3. Portfolio

### 3.1 Positions

| | Before | After |
|---|---|---|
| Path | `GET /portfolio/v1/positions` | `GET /transactional/v1/portfolio/positions/{type}` |
| Path param | none | `type` = `all` / `daily` / `expiry` (default `all`) |
| Query | none | optional `intropStatus` (`0`=OFF, `1`=ON) |

### 3.2 Position Conversion

| | Before | After |
|---|---|---|
| Path | `PUT /portfolio/v1/positions/convert` | `PUT /transactional/v1/portfolio/positions` |

**Payload:** already matched docs (`exchange`, `scrip_token`, `transaction_type`, `quantity`, `old_product_type`, `new_product_type`, `bo_order_id`)

### 3.3 Position Conversion Inquiry

| | Before | After |
|---|---|---|
| Endpoint | Not present | Added `GET /transactional/v1/portfolio/positions?orderId={order_id}` |
| Function | — | `get_position_conversion_inquiry(order_id)` |

### 3.4 Holdings

| | Before | After |
|---|---|---|
| Path | `GET /portfolio/v1/holdings` | `GET /transactional/v1/portfolio/holdings` |

---

## 4. Price Feed / LTP

Not REST in the new docs (broadcast socket using `broadcast_access_token`).

Existing methods left as-is:

- `GET /marketdata/v1/ltp/{exchange}/{symbol_token}`
- `POST /marketdata/v1/ltp`

---

## 5. Real-time Streaming (Socket.IO)

`bear_street_websocket_client.py` already matched the docs. No change.

1. Connect with `transports=['websocket']`
2. Emit `loginAPI` with `{ jToken: access_token }`
3. Listen on `MSG:DATA` (`ORD_NRML` / `TRD_MSG`)

---

## Plugin credentials intake (`/api/auth/credentials`)

This is **not** an ODIN endpoint. It is our plugin API that collects login fields and forwards them to ODIN login.

**Body before**
```json
{
  "broker_type": "bear_street",
  "api_key": "...",
  "client_code": "...",
  "password": "...",
  "second_auth": "...",
  "source": "WEBAPI",
  "user_id_broker": "...",
  "base_url": "...",
  "websocket_url": "..."
}
```

**Body after** — added:
```json
{
  "second_auth_type": "OTP",
  "login_type": "PASSWORD"
}
```

These now persist/restore with the session and flow through `broker_factory` → `broker_bear_street` → ODIN login.

Device metadata from the ODIN login example (`UDID`, `version`, `deviceinfo`, etc.) is **not** accepted here.

---

## Constants (`bear_street_client/constants.py`)

| Constant | Before | After |
|---|---|---|
| `valid_login_types` | `PASSWORD`, `MPIN`, `FINGERPRINT` | + `TP_TOKEN` |
| `valid_second_auth_types` | not present | `OTP`, `TOTP`, `FINGERPRINT`, `REGISTER` |
| `valid_exchanges` | `NSE_EQ`, `NSE_FO`, `NSE_CD`, `BSE_EQ`, `BSE_FO`, `BSE_CD`, `MCX`, `NCDEX` | `NSE_EQ`, `NSE_FO`, `BSE_EQ`, `BSE_FO`, `MCX_FO`, `NCDEX_FO`, `NSE_CUR`, `NSE_COMM`, `BSE_CUR`, `BSE_COMM`, `MSE_CUR`, `NSE_OTS` |
| `valid_validity` | `DAY`, `IOC`, `GTD`, `GTC`, `EOS` | + `EOSESS`, `EOTODY` |
| `valid_order_statuses` | `OMS_XMITTED`, `OMS_REJECT`, `ORDER_ERROR`, `ADMIN_REJECT`, `EXCHANGE_XMITTED`, `AMO_SUBMITTED`, `AMO_CANCELLED` | `OMSXMITTED`, `OMSREJECT`, `ORDERERROR`, `ADMINREJECT`, `EXXMITTED`, `AMOACCEPTED`, `AMOWITHDRAWN` |
| `valid_position_types` | `daily`, `expiry` | + `all` |

---

## Still not matching / not done

| Item | Notes |
|---|---|
| Send OTP | Not implemented |
| Validate Session | Not implemented |
| Place / Cancel Multileg | Not implemented |
| `get_user_profile` | Still in client, not in new REST docs |
| LTP REST methods | Still in client; new docs say broadcast socket instead |
| `broker_bear_street.py` exchange default | Still often `NSE` instead of `NSE_EQ` |
| Place order `scrip_info` | Broker layer often omits `scrip_token` |
| Optional login device fields | Not sent (`UDID`, `version`, `deviceinfo`, …) |
