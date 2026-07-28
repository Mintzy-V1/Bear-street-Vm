import json
import logging
import threading
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class BearStreetWebSocketClient:
    """
    socket.io client for Bear Street real-time order/trade streaming.

    Steps per API docs:
      1. Connect to messageSocket URL (from login response -> others.messageSocket)
      2. On connect, emit loginAPI with jToken = access_token
      3. Subscribe to MSG:DATA for order/trade responses
      4. MessageType "ORD_NRML" = order response, "TRD_MSG" = trade response
    """

    def __init__(self, url: str, access_token: str, on_order=None, on_trade=None, on_connect=None, on_disconnect=None, auto_reconnect=True):
        self.url = url
        self.access_token = access_token
        self.on_order = on_order
        self.on_trade = on_trade
        self.on_connect_cb = on_connect
        self.on_disconnect_cb = on_disconnect
        self.auto_reconnect = auto_reconnect

        self.sio = None
        self.connected = False
        self._thread = None
        self._stop = False
        self._reconnect_delay = 5

    def connect(self):
        try:
            import socketio
        except ImportError:
            raise ImportError("python-socketio is required. Install with: pip install python-socketio")

        self.sio = socketio.Client(reconnection=self.auto_reconnect)

        @self.sio.on("connect")
        def _on_connect():
            self.connected = True
            logger.info("[BS-WS] Connected to %s", self.url)
            self.sio.emit("loginAPI", {"jToken": self.access_token})
            logger.info("[BS-WS] Sent loginAPI with jToken")
            if self.on_connect_cb:
                self.on_connect_cb()

        @self.sio.on("disconnect")
        def _on_disconnect():
            self.connected = False
            logger.info("[BS-WS] Disconnected")
            if self.on_disconnect_cb:
                self.on_disconnect_cb()

        @self.sio.on("MSG:DATA")
        def _on_msg_data(data):
            try:
                msg_type = data.get("MessageType", "") if isinstance(data, dict) else ""
                if msg_type == "ORD_NRML":
                    if self.on_order:
                        self.on_order(data)
                elif msg_type == "TRD_MSG":
                    if self.on_trade:
                        self.on_trade(data)
                else:
                    logger.debug("[BS-WS] Unknown message type: %s", msg_type)
            except Exception as e:
                logger.error("[BS-WS] Error handling MSG:DATA: %s", e)

        @self.sio.on("*")
        def _on_all(event, data):
            logger.debug("[BS-WS] Unhandled event: %s", event)

        logger.info("[BS-WS] Connecting to %s", self.url)
        self.sio.connect(self.url, transports=["websocket"])
        self.sio.wait()

    def start(self, background=False):
        if background:
            self._thread = threading.Thread(target=self.connect, daemon=True)
            self._thread.start()
            return True
        else:
            self.connect()
            return True

    def stop(self):
        self._stop = True
        if self.sio:
            self.sio.disconnect()
            self.sio = None
        self.connected = False
        logger.info("[BS-WS] Stopped")

    @property
    def is_connected(self):
        return self.connected
