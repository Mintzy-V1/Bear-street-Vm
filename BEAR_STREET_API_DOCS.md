# Bear Street (Globe Capital) API Documentation

## Overview

Globe Capital API is a set of REST APIs that provide the platform along with required data to build a Trading Platform. The API specifications is used for communicating with Globe Capital API Gateway. API specifications are based on the REST protocol that covers the functionalities which are need to develop a trading application like Login / Logout, Order Management (Place Order, Modify Order, Cancel order), Reports like Order Book, Trade Book, Position, Holding & Limit, etc. The REST API supports JSON based request and responses along with data compression.

---

## Basic Flow

1. **Login** — obtain access token via login credentials.
2. **Use access token** in all subsequent API calls as `Authorization: Bearer <token>`.
3. **Content-Type**: `application/json`.

---

## Response Structure

### Successful Request

```json
HTTP/1.1 200 OK
Content-Type: application/json

{
  "status": "success",
  "code": "",
  "message": "",
  "data": "{}"
}
```

### Failed Request

```json
HTTP/1.1 4xx/5xx
Content-Type: application/json

{
  "status": "error",
  "code": "",
  "message": "",
  "errors": "[]"
}
```

### Data Types

| Type       | Notes                                           |
| ---------- | ----------------------------------------------- |
| string     |                                                 |
| integer    |                                                 |
| number     |                                                 |
| bool       |                                                 |
| datetime   | Format: `yyyy-mm-dd HH:mm:ss` e.g. `2016-01-25 13:33:42` |

---

## HTTP Status Codes

| Code | Description                                                      |
| ---- | ---------------------------------------------------------------- |
| 400  | Bad Request — missing or bad parameters                          |
| 401  | Unauthorized — expired/revoked/invalid token                     |
| 404  | Not Found                                                        |
| 405  | Method Not Allowed                                               |
| 500  | Internal Server Error                                            |
| 503  | Service Unavailable                                              |

---

## Authentication

### Login

Creates a session and returns an `access_token` and `broadcast_access_token`.

**POST** `/authentication/v1/user/session`

**Dev Server:** `http://localhost:3100`
**Prod Server:** `http://localhost:3200`

#### Request Body

| Field        | Type   | Required | Description                                              |
| ------------ | ------ | -------- | -------------------------------------------------------- |
| user_id      | string | yes      | User ID (CAPITALIZED)                                    |
| login_type   | string | no       | Default: `PASSWORD`. Enum: `PASSWORD`, `MPIN`, `FINGERPRINT` |
| password     | string | yes      | Password / MPIN / Fingerprint                            |
| second_auth  | string | yes      | 2FA password                                             |
| api_key      | string | yes      | API key provided during subscription                     |
| source       | string | yes      | Enum: `WEBAPI`, `MOBILEAPI`                              |

```json
{
  "user_id": "TEST1",
  "login_type": "PASSWORD",
  "password": "Xyz@123",
  "second_auth": "QWERT1234Y",
  "api_key": "aasdszzzzz11",
  "source": "WEBAPI"
}
```

#### Response

```json
{
  "status": "success",
  "code": "s-101",
  "message": "Success message",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiJ9...",
    "broadcast_access_token": "eyJhbGciOiJIUzI1NiJ9...",
    "user_name": "Rest Client",
    "login_time": "2020-03-10 10:10:10",
    "exchanges": [],
    "bcastExchanges": [],
    "product_types": [],
    "product_types_exchange": {},
    "mpin_enabled": true,
    "fingerprint_enabled": true,
    "others": {}
  }
}
```

---

### Logout

Destroys the current API session.

**DELETE** `/authentication/v1/user/session`

#### Response

```json
{
  "status": "success",
  "code": "s-101",
  "message": "Success message"
}
```

---

### Balance

Retrieves the latest balance across allowed segments.

**GET** `/authentication/v1/user/balance`

#### Response

```json
{
  "status": "success",
  "code": "s-101",
  "message": "Success message",
  "data": {
    "equity": {},
    "commodity": {},
    "currency": {}
  }
}
```

---

## Order Management

### Global Constants

| Param        | Values                                                                       | Description                                                          |
| ------------ | ---------------------------------------------------------------------------- | -------------------------------------------------------------------- |
| product_type | `INTRADAY`, `DELIVERY`, `BTST`, `COVER`, `BRACKET`, `MTF`                   | Product type of the order                                            |
| order_type   | `RL`, `RL-MKT`, `SL`, `SL-MKT`                                              | Regular limit, regular market, stoploss limit, stoploss market       |
| validity     | `DAY`, `IOC`, `GTD`, `GTC`, `EOS`                                           | Order validity                                                       |
| order_status | `PENDING`, `EXECUTED`, `CANCELLED`, `OMS_XMITTED`, `OMS_REJECT`, `ORDER_ERROR`, `ADMIN_REJECT`, `EXCHANGE_XMITTED`, `AMO_SUBMITTED`, `AMO_CANCELLED` | Status of the order |

---

### Place Order

**POST** `/transactional/v1/orders/regular`

#### Request Body

| Field              | Type    | Required | Default  | Description                                        |
| ------------------ | ------- | -------- | -------- | -------------------------------------------------- |
| scrip_info         | object  | yes      | —        | Exchange + token OR symbol details                 |
| transaction_type   | string  | yes      | —        | `BUY` or `SELL`                                    |
| product_type       | string  | yes      | —        | See product_type constants                         |
| order_type         | string  | yes      | —        | See order_type constants                           |
| quantity           | integer | yes      | —        | Quantity to transact                               |
| price              | number  | no       | 0        | Order price                                        |
| trigger_price      | number  | no       | —        | Trigger price for SL orders                        |
| disclosed_quantity | integer | no       | —        | Quantity disclosed to market                       |
| validity           | string  | no       | `DAY`    | Order validity                                     |
| validity_days      | integer | no       | —        | Days for GTD validity                              |
| is_amo             | boolean | no       | false    | After Market Order flag                            |
| order_identifier   | string  | no       | —        | Max 8 chars, client-side tracking                  |
| part_code          | string  | no       | —        | Participant code                                   |
| algo_id            | string  | no       | —        | Algorithm ID                                       |
| strategy_id        | string  | no       | —        | Strategy ID                                        |
| vender_code        | string  | no       | —        | Vendor code                                        |

```json
{
  "scrip_info": {
    "exchange": "NSE_EQ",
    "scrip_token": 22,
    "symbol": null,
    "series": null,
    "expiry_date": null,
    "strike_price": null,
    "option_type": null
  },
  "transaction_type": "BUY",
  "product_type": "DELIVERY",
  "order_type": "RL",
  "quantity": 50,
  "price": 100,
  "trigger_price": 0,
  "disclosed_quantity": 25,
  "validity": "DAY",
  "is_amo": false,
  "order_identifier": "108108108"
}
```

#### Response

```json
{
  "status": "success",
  "code": "s-101",
  "message": "Success Message"
}
```

---

### Modify Order

**PUT** `/transactional/v1/orders/regular/{exchange}/{order_id}`

#### Path Parameters

| Param    | Type   | Required | Description                                    |
| -------- | ------ | -------- | ---------------------------------------------- |
| exchange | string | yes      | Exchange segment                               |
| order_id | string | yes      | Order ID (URL-encoded)                         |

#### Request Body

| Field              | Type    | Required | Default | Description                  |
| ------------------ | ------- | -------- | ------- | ---------------------------- |
| order_type         | string  | yes      | —       | Type of order                |
| quantity           | integer | yes      | —       | Quantity                     |
| traded_quantity    | integer | yes      | —       | Cumulative traded qty        |
| price              | number  | no       | 0       | Order price                  |
| trigger_price      | number  | no       | —       | Trigger price for SL orders  |
| disclosed_quantity | integer | no       | —       | Disclosed quantity           |
| validity           | string  | no       | `DAY`   | Order validity               |
| validity_days      | integer | no       | —       | Days for GTD validity        |

```json
{
  "order_type": "RL",
  "quantity": 50,
  "traded_quantity": 50,
  "price": 0,
  "trigger_price": 0,
  "disclosed_quantity": 25,
  "validity": "DAY"
}
```

#### Response

```json
{
  "status": "success",
  "code": "s-101",
  "message": "Success Message"
}
```

---

### Cancel Order

**DELETE** `/transactional/v1/orders/regular/{exchange}/{order_id}`

#### Path Parameters

| Param    | Type   | Required | Description          |
| -------- | ------ | -------- | -------------------- |
| exchange | string | yes      | Exchange segment     |
| order_id | string | yes      | Order ID (URL-encoded) |

#### Response

```json
{
  "status": "success",
  "code": "s-101",
  "message": "Success Message"
}
```

---

### Place Cover Order

**POST** `/transactional/v1/orders/cover`

#### Request Body

| Field              | Type    | Required | Description                                          |
| ------------------ | ------- | -------- | ---------------------------------------------------- |
| scrip_info         | object  | yes      | Exchange + token OR symbol details                   |
| transaction_type   | string  | yes      | `BUY` or `SELL`                                      |
| main_leg           | object  | no       | Main leg details (order_type, quantity, price)       |
| stoploss_leg       | object  | no       | Stop loss leg details (legs: [])                     |
| order_identifier   | string  | no       | Max 8 chars                                          |
| part_code          | string  | no       | Participant code                                     |
| algo_id            | string  | no       | Algorithm ID                                         |
| strategy_id        | string  | no       | Strategy ID                                          |
| vender_Code        | string  | no       | Vendor code                                          |

```json
{
  "scrip_info": {
    "exchange": "NSE_EQ",
    "scrip_token": 22,
    "symbol": null,
    "series": null,
    "expiry_date": null,
    "strike_price": null,
    "option_type": null
  },
  "main_leg": {
    "order_type": "RL-MKT",
    "quantity": 50,
    "price": 0
  },
  "stoploss_leg": {
    "legs": []
  },
  "order_identifier": "108108108"
}
```

#### Response

```json
{
  "status": "success",
  "code": "s-101",
  "message": "Success Message"
}
```

---

### Modify Cover Order

**PUT** `/transactional/v1/orders/cover/{exchange}/{order_id}`

#### Path Parameters

| Param    | Type   | Required | Description          |
| -------- | ------ | -------- | -------------------- |
| exchange | string | yes      | Exchange segment     |
| order_id | string | yes      | Order ID (URL-encoded) |

#### Request Body

| Field        | Type   | Required | Description            |
| ------------ | ------ | -------- | ---------------------- |
| main_leg     | object | no       | Main leg details       |
| stoploss_leg | object | no       | Stop loss leg details  |

```json
{
  "main_leg": {
    "order_type": "RL-MKT",
    "quantity": 50,
    "traded_quantity": 50,
    "price": 0
  },
  "stoploss_leg": {
    "legs": []
  }
}
```

#### Response

```json
{
  "status": "success",
  "code": "s-101",
  "message": "Success Message"
}
```

---

### Cancel Cover Order

**DELETE** `/transactional/v1/orders/cover/{exchange}/{order_id}`

#### Path Parameters

| Param    | Type   | Required | Description          |
| -------- | ------ | -------- | -------------------- |
| exchange | string | yes      | Exchange segment     |
| order_id | string | yes      | Order ID (URL-encoded) |

#### Response

```json
{
  "status": "success",
  "code": "s-101",
  "message": "Success Message"
}
```

---

### Place Bracket Order

**POST** `/transactional/v1/orders/bracket`

#### Request Body

| Field              | Type    | Required | Description            |
| ------------------ | ------- | -------- | ---------------------- |
| scrip_info         | object  | yes      | Exchange + token OR symbol |
| transaction_type   | string  | yes      | `BUY` or `SELL`         |
| main_leg           | object  | no       | Main leg details        |
| stoploss_leg       | object  | no       | Stop loss leg details   |
| profit_leg         | object  | no       | Profit leg details      |
| order_identifier   | string  | no       | Max 8 chars             |
| part_code          | string  | no       | Participant code        |
| algo_id            | string  | no       | Algorithm ID            |
| strategy_id        | string  | no       | Strategy ID             |
| vender_Code        | string  | no       | Vendor code             |

```json
{
  "scrip_info": {
    "exchange": "NSE_EQ",
    "scrip_token": 22,
    "symbol": null,
    "series": null,
    "expiry_date": null,
    "strike_price": null,
    "option_type": null
  },
  "transaction_type": "BUY",
  "main_leg": {
    "order_type": "RL",
    "quantity": 50,
    "price": 0,
    "trigger_price": 0
  },
  "stoploss_leg": {
    "legs": {},
    "trail": {}
  },
  "profit_leg": {
    "legs": []
  },
  "order_identifier": "108108108"
}
```

#### Response

```json
{
  "status": "success",
  "code": "s-101",
  "message": "Success Message"
}
```

---

### Modify Bracket Order

**PUT** `/transactional/v1/orders/bracket/{exchange}/{order_id}`

#### Path Parameters

| Param    | Type   | Required | Description          |
| -------- | ------ | -------- | -------------------- |
| exchange | string | yes      | Exchange segment     |
| order_id | string | yes      | Order ID (URL-encoded) |

#### Request Body

| Field           | Type   | Required | Description            |
| --------------- | ------ | -------- | ---------------------- |
| main_leg        | object | no       | Main leg details       |
| stoploss_leg    | object | no       | Stop loss leg details  |
| profit_leg      | object | no       | Profit leg details     |
| fields_modified | object | no       | Modified fields flags  |

```json
{
  "main_leg": {
    "order_type": "RL",
    "quantity": 50,
    "traded_quantity": 50,
    "price": 100,
    "trigger_price": 0
  },
  "stoploss_leg": {
    "legs": [],
    "trail": {}
  },
  "profit_leg": {
    "legs": []
  },
  "fields_modified": {
    "main_leg_price": true,
    "main_leg_qty": true,
    "stoploss_leg_price": true,
    "stoploss_trail_price": true,
    "profit_leg_price": true
  }
}
```

#### Response

```json
{
  "status": "success",
  "code": "s-101",
  "message": "Success Message"
}
```

---

### Exit Bracket Order

**DELETE** `/transactional/v1/orders/bracket/{order_id}`

#### Path Parameters

| Param    | Type   | Required | Description          |
| -------- | ------ | -------- | -------------------- |
| order_id | string | yes      | Order ID             |

#### Response

```json
{
  "status": "success",
  "code": "s-101",
  "message": "Success Message"
}
```

---

### Trade Book

**GET** `/transactional/v1/trades`

#### Query Parameters

| Param    | Type    | Required | Description                                      |
| -------- | ------- | -------- | ------------------------------------------------ |
| offset   | integer | yes      | Page number                                      |
| limit    | integer | yes      | Items per page                                   |
| order_id | string  | no       | Filter by order ID (URL-encoded)                 |

#### Response

```json
{
  "status": "success",
  "code": "s-101",
  "message": "Success message",
  "data": {
    "order_id": "123456",
    "exchange": "NSE_EQ",
    "scrip_token": 22,
    "trade_no": "12345678",
    "exchange_order_no": "87987978",
    "transaction_type": "BUY",
    "product_type": "DELIVERY",
    "order_type": "RL",
    "trade_quantity": 50,
    "trade_price": 100,
    "symbol": "ACC",
    "series": "EQ",
    "instrument": "EQUITIES",
    "expiry_date": "",
    "strike_price": null,
    "option_type": "",
    "trade_timestamp": "2020-01-20 12:10:10",
    "initiated_by": "WEBAPI",
    "modified_by": "",
    "order_identifier": "108108108"
  },
  "metadata": {
    "total_records": 500
  }
}
```

---

### Order Book

**GET** `/transactional/v1/orders`

#### Query Parameters

| Param    | Type    | Required | Description                      |
| -------- | ------- | -------- | -------------------------------- |
| offset   | integer | yes      | Page number                      |
| limit    | integer | yes      | Items per page                   |
| order_id | string  | no       | Filter by order ID (URL-encoded) |

#### Response

```json
{
  "status": "success",
  "code": "s-101",
  "message": "Success message",
  "data": [{}],
  "metadata": {
    "total_records": 500
  }
}
```

---

### Order History

**GET** `/transactional/v1/orders/{order_id}`

#### Path Parameters

| Param    | Type   | Required | Description              |
| -------- | ------ | -------- | ------------------------ |
| order_id | string | yes      | Order ID (URL-encoded)   |

#### Response

```json
{
  "status": "success",
  "code": "s-101",
  "message": "Success message",
  "data": [{}],
  "metadata": {
    "total_records": 500
  }
}
```

---

## Portfolio

### Positions

**GET** `/transactional/v1/portfolio/positions/{type}`

#### Path Parameters

| Param | Type   | Required | Default | Enum             |
| ----- | ------ | -------- | ------- | ---------------- |
| type  | string | yes      | `daily` | `daily`, `expiry` |

#### Response

```json
{
  "status": "success",
  "code": "s-101",
  "message": "Success message",
  "data": {
    "exchange": "NSE_EQ",
    "scrip_token": 22,
    "product_type": "INTRADAY",
    "symbol": "ACC",
    "series": "EQ",
    "instrument": "EQUITIES",
    "expiry_date": "",
    "strike_price": null,
    "option_type": "",
    "buy_quantity": 10,
    "avg_buy_price": 1500,
    "buy_value": 15000,
    "sell_quantity": 10,
    "avg_sell_price": 1600,
    "sell_value": 16000,
    "net_quantity": 0,
    "net_price": 0,
    "net_value": 0,
    "ltp": 1560,
    "close_price": 1500,
    "multiplier": 1,
    "mtm": 0
  }
}
```

---

### Position Conversion

**PUT** `/transactional/v1/portfolio/positions/`

#### Request Body

| Field             | Type    | Required | Description                                        |
| ----------------- | ------- | -------- | -------------------------------------------------- |
| exchange          | string  | yes      | Exchange segment                                   |
| scrip_token       | integer | yes      | Token number of the scrip                          |
| transaction_type  | string  | yes      | `BUY` or `SELL`                                    |
| quantity          | integer | yes      | Quantity to convert                                |
| old_product_type  | string  | yes      | Old product type                                   |
| new_product_type  | string  | yes      | New product type                                   |
| bo_order_id       | string  | no       | Bracket order ID (for bracket order conversion)    |

```json
{
  "exchange": "NSE_EQ",
  "scrip_token": 22,
  "transaction_type": "BUY",
  "quantity": 50,
  "old_product_type": "INTRADAY",
  "new_product_type": "DELIVERY",
  "bo_order_id": ""
}
```

#### Response

```json
{
  "status": "success",
  "code": "s-101",
  "message": "Success Message"
}
```

---

### Holdings

**GET** `/transactional/v1/portfolio/holdings`

#### Response

```json
{
  "status": "success",
  "code": "s-101",
  "message": "Success message",
  "data": {
    "isin": "INE516F01016",
    "security_info": [],
    "total_free": 1,
    "dp_free": 0,
    "pool_free": 1,
    "t1_quantity": 1,
    "average_price": 94.75,
    "last_price": 93.75,
    "pnl": -100,
    "current_value": -100,
    "inv_value": -100,
    "product": "DELIVERY",
    "collateral_quantity": 0,
    "collateral_value": 0
  }
}
```

---

## Price Feed / Real-time Streaming

### WebSocket (socket.io)

System provides real-time streaming via `socket.io`. 

**Steps:**
1. Login to obtain `broadcast_access_token` and `others.messageSocket` (streaming server endpoint).
2. Establish socket connection.
3. Authenticate with `jToken` (the `access_token`).
4. Subscribe to events.

### Connection

```js
const io = require("socket.io-client");
let ioClient = io.connect(url, { transports: ['websocket'] });  // url from "others"."messageSocket"
```

### Login

```js
ioClient.on("connect", () => {
  let msgLogin = { "jToken": "<access_token>" };
  ioClient.emit('loginAPI', msgLogin);
});
```

### Subscribe to Order/Trade Responses

```js
ioClient.on("MSG:DATA", (response) => {
  console.log('Received response:', JSON.stringify(response));
});
```

### Messages

- `MessageType`: `"ORD_NRML"` → Order Response, `"TRD_MSG"` → Trade Response

### Order Response Structure

| Key                    | Type     | Description                                                |
| ---------------------- | -------- | ---------------------------------------------------------- |
| AMOOrderID             | String   | Order ID for AMO/EqGTD orders                              |
| Buy_Sell               | String   | `1` → Buy, `2` → Sell                                     |
| CP_ID                  | String   |                                                            |
| CliOrderNumber         | Integer  | Gateway/Client order number                                |
| DQ                     | Integer  | Disclosed quantity                                         |
| DQRemaining            | Integer  | Remaining disclosed quantity                               |
| Days                   | String   | Number of days                                             |
| Exchange               | String   | Exchange code                                              |
| ExpiryDate             | String   | Expiry date (Ddmmmyyyy)                                    |
| GTDOrderStatus         | Integer  | GTD order status                                           |
| InitiatedBy            | String   | Initiated from application                                 |
| InitiatedByUserId      | String   | Initiated by user ID                                       |
| InstrumentName         | String   | Instrument name (FUTIDX, OPTIDX, etc.)                     |
| LastModifiedTime       | DateTime | Order confirmation time                                    |
| LegIndicator           | String   |                                                            |
| ManagerID              | String   | Manager ID                                                 |
| MarketType             | Integer  | `1` Normal, `2` Auction, `3` PreOpen                       |
| MessageSequenceNumber  | String   | Running message sequence number                            |
| MessageType            | String   | `ORD_NRML`                                                 |
| Misc                   | String   | SPO-LMT, SPO-MKT, PO-MKT, PO-LMT                          |
| ModifiedBy             | String   | Modified by application                                    |
| ModifiedByUserId       | String   | Modified by user ID                                        |
| Option_Type            | String   | Option type (for options)                                  |
| OrderEntryTime         | DateTime | Order entry time (24h format)                              |
| OrderNumber            | String   | Order number (0 for new, filled for modify/cancel)         |
| OrderOriginalQty       | Integer  | Total quantity                                              |
| OrderPrice             | Integer  | Price in paise                                             |
| OrderStatus            | Integer  | Order status                                               |
| OrderType              | Integer  | Order type                                                 |
| OrderValidity          | String   | Validity                                                   |
| PartCode               | String   | Participant ID                                             |
| PendingQty             | Integer  | Pending quantity                                           |
| ProCli                 | String   | `2` → PRO, `1` → Client                                   |
| Product                | String   | Product type                                               |
| Reason                 | String   | Rejection reason                                           |
| ScripCode              | String   | Scrip code                                                 |
| Series                 | String   | Security series                                            |
| SpreadFlag             | Integer  | `0` Normal, `1` Spread                                     |
| SpreadPrice            | Integer  | Spread price                                               |
| StrikePrice            | Integer  | Strike price (multiples of 100)                            |
| Symbol                 | String   | Security symbol                                            |
| TradedQTY              | String   | Traded quantity                                            |
| TriggerPrice           | Integer  | Trigger price for SL orders                                |
| UCC                    | String   | Alias UCC code                                             |
| UniqueCode             | String   | Alphanumeric value with special characters                 |
| UserID                 | String   | Exchange user ID                                           |
| UserRemarks            | String   | User remarks                                               |

### Trade Response Structure

| Key                     | Type     | Description                                    |
| ----------------------- | -------- | ---------------------------------------------- |
| Buy_Sell                | String   | `1` → Buy, `2` → Sell                          |
| CP_ID                   | String   |                                                |
| CliOrderNumber          | Integer  | Gateway/Client order number                    |
| DQ                      | String   | Disclosed quantity                             |
| DQRemaining             | String   | Remaining disclosed quantity                   |
| Days                    | Integer  | Number of days                                 |
| Exchange                | Integer  | Exchange                                       |
| ExpiryDate              | String   | Expiry date (Ddmmmyyyy)                        |
| InitiatedBy             | String   | Initiated from application                     |
| InitiatedByUserId       | String   | Initiated by user ID                           |
| InstrumentName          | String   | Instrument name                                |
| LegIndicator            | String   |                                                |
| ManagerID               | Integer  | Manager ID                                     |
| MessageSequenceNumber   | Integer  | Running message sequence number                |
| MessageType             | String   | `TRD_MSG`                                      |
| Misc                    | String   | SPO-LMT, SPO-MKT, PO-MKT, PO-LMT              |
| ModifiedBy              | String   | Modified by application                        |
| ModifiedByUserId        | String   | Modified by user ID                            |
| Option_Type             | String   | Option type                                    |
| OrderLastModifiedTime   | DateTime | Order confirmation time                        |
| OrderNumber             | String   | Order number                                   |
| OrderOriginalQty        | Integer  | Total quantity                                  |
| OrderPrice              | Integer  | Order price in paisa                           |
| OrderTime               | DateTime | Order time (24h format)                        |
| OrderType               | Integer  | Order type                                     |
| PartCode                | String   | Participant ID                                 |
| PendingQty              | String   | Pending quantity                               |
| ProCli                  | String   | `2` → PRO, `1` → Client                        |
| Product                 | String   | Product type                                   |
| QuantityTradedToday     | Integer  | Total traded quantity today                    |
| ScripCode               | Integer  | Scrip code                                     |
| Series                  | String   | Security series                                |
| SpreadFlag              | Integer  | `0` Normal, `1` Spread                         |
| SpreadPrice             | Integer  | Spread price                                   |
| StrikePrice             | Integer  | Strike price (multiples of 100)                |
| Symbol                  | String   | Security symbol                                |
| TradeNumber             | String   | Trade number                                   |
| TradeQty                | String   | Traded quantity                                |
| TradeTime               | DateTime | Trade time (24h format)                        |
| TradedPrice             | String   | Trade price in paisa                           |
| UCC                     | String   | Alias UCC code                                 |
| UniqueCode              | String   | Alphanumeric value with special characters     |
| UserID                  | String   | Exchange user ID                               |
| UserRemarks             | String   | User remarks                                   |

---

## Reference Server URLs

| Environment | URL                            |
| ----------- | ------------------------------ |
| Development | `http://localhost:3100`        |
| Production  | `http://localhost:3200`        |
