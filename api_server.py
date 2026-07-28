from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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


@app.get("/api/health")
async def health():
    return {"status": "ok", "broker": "bear_street"}


@app.post("/api/login")
async def login(config: Dict[str, Any], x_plugin_api_key: str = Header(default=None)):
    try:
        broker, session = connect_broker(config)
        return {
            "status": "success",
            "data": {
                "user": session.get("user"),
                "token": session.get("token"),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))


@app.post("/api/balance")
async def balance(config: Dict[str, Any], x_plugin_api_key: str = Header(default=None)):
    try:
        broker, session = connect_broker(config)
        result = broker.get_account_balance(session)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("api_server:app", host="0.0.0.0", port=port, reload=True)
