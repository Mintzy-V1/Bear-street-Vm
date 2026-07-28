from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
import uvicorn
import os
import logging
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from broker_factory import (
    BROKER_BEAR_STREET,
    connect_broker,
    DEFAULT_BEAR_STREET_BASE_URL,
)

app = FastAPI(title="Bear Street API Server", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
LOGS_DIR = BASE_DIR / "logs"
logger = logging.getLogger(__name__)
SECRET = os.getenv("SECRET", "dev-secret")


class BrokerConfig(BaseModel):
    api_key: str
    user_id: str
    password: str
    second_auth: str
    source: str = "WEBAPI"
    base_url: Optional[str] = None


def _broker_from_config(config: BrokerConfig):
    return connect_broker({
        "broker_type": BROKER_BEAR_STREET,
        "api_key": config.api_key,
        "user_id": config.user_id,
        "password": config.password,
        "second_auth": config.second_auth,
        "source": config.source,
        "base_url": config.base_url or DEFAULT_BEAR_STREET_BASE_URL,
    })


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/api/health")
async def health():
    return {"status": "success", "message": "Bear Street API Server running", "version": "1.0.0"}


# ---------------------------------------------------------------------------
# Session 1 — Auth
# ---------------------------------------------------------------------------

@app.post("/api/v1/login")
async def login(config: BrokerConfig):
    try:
        broker, session = _broker_from_config(config)
        return {
            "status": "success",
            "message": "Logged in successfully",
            "data": {
                "user": session.get("user"),
                "access_token": session.get("token"),
                "broadcast_access_token": session.get("broadcast_token"),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Login failed: {str(e)}")


@app.post("/api/v1/logout")
async def logout(config: BrokerConfig):
    try:
        broker, session = _broker_from_config(config)
        result = broker.obj.logout() if broker.obj else {}
        return {"status": "success", "message": "Logged out", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/balance")
async def balance(config: BrokerConfig):
    try:
        broker, session = _broker_from_config(config)
        result = broker.get_account_balance(session)
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("error"))
        return {"status": "success", "data": result.get("data", {})}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/profile")
async def profile(config: BrokerConfig):
    try:
        broker, session = _broker_from_config(config)
        result = broker.get_user_profile(session)
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("error"))
        return {"status": "success", "data": result.get("raw", {})}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Session 2 — Orders
# ---------------------------------------------------------------------------

class PlaceOrderRequest(BrokerConfig):
    symbol: str
    side: str = Field(..., description="BUY or SELL")
    quantity: int
    price: float = 0
    order_type: str = "MARKET"
    product_type: str = "INTRADAY"
    exchange: str = "NSE"
    trigger_price: Optional[float] = None
    wait_for_confirmation: bool = True
    order_identifier: Optional[str] = None


class ModifyOrderRequest(BrokerConfig):
    order_id: str
    new_price: Optional[float] = None
    new_qty: Optional[int] = None


class CancelOrderRequest(BrokerConfig):
    order_id: str


@app.post("/api/v1/order/place")
async def place_order(req: PlaceOrderRequest):
    try:
        broker, session = _broker_from_config(req)
        result = broker.place_order(
            session, req.symbol, req.side,
            qty=req.quantity, price=req.price,
            order_type=req.order_type, product_type=req.product_type,
            exchange=req.exchange, trigger_price=req.trigger_price,
            wait_for_confirmation=req.wait_for_confirmation,
            order_identifier=req.order_identifier,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/order/modify")
async def modify_order(req: ModifyOrderRequest):
    try:
        broker, session = _broker_from_config(req)
        result = broker.modify_order(session, req.order_id, new_price=req.new_price, new_qty=req.new_qty)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/order/cancel")
async def cancel_order(req: CancelOrderRequest):
    try:
        broker, session = _broker_from_config(req)
        result = broker.cancel_order(session, req.order_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/order/book")
async def order_book(config: BrokerConfig):
    try:
        broker, session = _broker_from_config(config)
        result = broker.get_order_book(session)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/order/trade-book")
async def trade_book(config: BrokerConfig):
    try:
        broker, session = _broker_from_config(config)
        result = broker.get_trade_book(session)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class OrderHistoryReq(BrokerConfig):
    order_id: str


@app.post("/api/v1/order/history")
async def order_history(req: OrderHistoryReq):
    try:
        broker, session = _broker_from_config(req)
        result = broker.get_order_history(session, req.order_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class CoverOrderReq(BrokerConfig):
    symbol: str
    side: str
    quantity: int
    price: float = 0
    order_type: str = "RL-MKT"
    exchange: str = "NSE"


@app.post("/api/v1/order/cover/place")
async def place_cover(req: CoverOrderReq):
    try:
        broker, session = _broker_from_config(req)
        result = broker.place_cover_order(
            session, req.symbol, req.side, req.quantity,
            price=req.price, order_type=req.order_type, exchange=req.exchange,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class BracketOrderReq(BrokerConfig):
    symbol: str
    side: str
    quantity: int
    price: float = 0
    trigger_price: Optional[float] = None
    exchange: str = "NSE"


@app.post("/api/v1/order/bracket/place")
async def place_bracket(req: BracketOrderReq):
    try:
        broker, session = _broker_from_config(req)
        result = broker.place_bracket_order(
            session, req.symbol, req.side, req.quantity,
            price=req.price, trigger_price=req.trigger_price, exchange=req.exchange,
        )
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("api_server:app", host="0.0.0.0", port=port, reload=True)
