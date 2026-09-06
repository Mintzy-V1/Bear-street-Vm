import json
import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def get_access_token() -> str:
    env_token = os.getenv("UPSTOX_ACCESS_TOKEN")
    if env_token:
        logger.info("Using Upstox access token from environment variable.")
        return env_token

    token_path = Path(__file__).with_name("upstox_token.json")
    if not token_path.exists():
        logger.warning("Upstox access token file not found at %s", token_path)
        return ""

    try:
        with token_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        logger.warning("Failed to read Upstox token file %s: %s", token_path, e)
        return ""

    access_token = data.get("access_token") or ""
    if not access_token:
        logger.warning("'access_token' missing or empty in %s", token_path)
        return ""

    logger.info("Loaded Upstox access token from %s", token_path)
    return access_token
