from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
    broker_config_from_session,
    connect_broker,
    normalize_broker_type,
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


@app.get("/api/health")
async def health():
    return {"status": "success", "message": "Bear Street API Server running", "version": "1.0.0"}


@app.post("/api/v1/login")
async def login(config: BrokerConfig, x_api_key: str = Header(default=None)):
    try:
        broker, session = connect_broker({
            "broker_type": BROKER_BEAR_STREET,
            "api_key": config.api_key,
            "user_id": config.user_id,
            "password": config.password,
            "second_auth": config.second_auth,
            "source": config.source,
            "base_url": config.base_url or DEFAULT_BEAR_STREET_BASE_URL,
        })
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
async def logout(config: BrokerConfig, x_api_key: str = Header(default=None)):
    try:
        broker, session = connect_broker({
            "broker_type": BROKER_BEAR_STREET,
            "api_key": config.api_key,
            "user_id": config.user_id,
            "password": config.password,
            "second_auth": config.second_auth,
            "source": config.source,
            "base_url": config.base_url or DEFAULT_BEAR_STREET_BASE_URL,
        })
        result = broker.obj.logout() if broker.obj else {}
        return {"status": "success", "message": "Logged out", "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/balance")
async def balance(config: BrokerConfig, x_api_key: str = Header(default=None)):
    try:
        broker, session = connect_broker({
            "broker_type": BROKER_BEAR_STREET,
            "api_key": config.api_key,
            "user_id": config.user_id,
            "password": config.password,
            "second_auth": config.second_auth,
            "source": config.source,
            "base_url": config.base_url or DEFAULT_BEAR_STREET_BASE_URL,
        })
        result = broker.get_account_balance(session)
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("error"))
        return {"status": "success", "data": result.get("data", {})}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/profile")
async def profile(config: BrokerConfig, x_api_key: str = Header(default=None)):
    try:
        broker, session = connect_broker({
            "broker_type": BROKER_BEAR_STREET,
            "api_key": config.api_key,
            "user_id": config.user_id,
            "password": config.password,
            "second_auth": config.second_auth,
            "source": config.source,
            "base_url": config.base_url or DEFAULT_BEAR_STREET_BASE_URL,
        })
        result = broker.get_user_profile(session)
        if result.get("status") == "error":
            raise HTTPException(status_code=500, detail=result.get("error"))
        return {"status": "success", "data": result.get("raw", {})}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("api_server:app", host="0.0.0.0", port=port, reload=True)
