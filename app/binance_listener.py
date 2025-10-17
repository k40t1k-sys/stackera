import asyncio
import json
import logging
import random
from typing import List

import websockets

from .config import Settings
from .schemas import TickerUpdate
from .state import Broker


class BinanceListener:
    """
    Maintains a live websocket connection to Binance and publishes normalized
    TickerUpdate objects to the Broker. Handles reconnection with jittered
    exponential backoff and clean shutdown via an asyncio.Event.
    """

    def __init__(self, settings: Settings, broker: Broker, stop_event: asyncio.Event):
        self.settings = settings
        self.broker = broker
        self.stop_event = stop_event

    def _build_url(self, symbols: List[str]) -> str:
        syms = [s.lower() for s in symbols]
        base = self.settings.binance_base_url.rstrip("/")
        if len(syms) == 1:
            # Requirement explicitly references this path for BTCUSDT
            return f"{base}/ws/{syms[0]}@ticker"
        streams = "/".join(f"{s}@ticker" for s in syms)
        return f"{base}/stream?streams={streams}"

    async def run(self) -> None:
        backoff = self.settings.reconnect_min_delay
        url = self._build_url(self.settings.symbols)

        while not self.stop_event.is_set():
            try:
                async with websockets.connect(
                    url,
                    ping_interval=self.settings.ping_interval,
                    ping_timeout=self.settings.ping_timeout,
                    close_timeout=10,
                    max_size=2**20,     # 1 MiB
                    open_timeout=20,
                ) as ws:
                    logging.info("Connected to Binance WS: %s", url)
                    backoff = self.settings.reconnect_min_delay

                    async for raw in ws:
                        if self.stop_event.is_set():
                            break

                        try:
                            payload = json.loads(raw)
                        except json.JSONDecodeError:
                            logging.warning("Invalid JSON from Binance (truncated): %r", raw[:200])
                            continue

                        # Combined stream messages nest data under "data"; single stream is the payload itself
                        data = payload.get("data", payload)
                        if not isinstance(data, dict):
                            continue

                        try:
                            update = TickerUpdate.from_binance(data)
                        except Exception as e:
                            logging.debug("Skipping malformed ticker: %s (keys=%s)", e, list(data.keys()))
                            continue

                        await self.broker.publish(update)

            except asyncio.CancelledError:
                # Fast shutdown on application exit
                raise
            except Exception as e:
                logging.exception("Binance WS error: %s", e)

                # Jittered exponential backoff, bounded
                jitter = random.uniform(0, backoff)
                delay = min(self.settings.reconnect_max_delay, backoff + jitter)
                logging.warning("Reconnecting to Binance in %.2fs ...", delay)
                try:
                    await asyncio.wait_for(self.stop_event.wait(), timeout=delay)
                except asyncio.TimeoutError:
                    pass
                backoff = min(self.settings.reconnect_max_delay, backoff * 2)

        logging.info("BinanceListener stopped.")