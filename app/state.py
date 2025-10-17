import asyncio
import json
import logging
from typing import Dict

from .schemas import TickerUpdate


class Broker:
    """
    In-memory broker:
      - Stores latest update per symbol
      - Maintains a per-client queue to decouple slow consumers
      - Broadcasts new updates to all clients
    """
    def __init__(self, client_queue_size: int = 100):
        self._latest: Dict[str, TickerUpdate] = {}
        self._clients: Dict[int, asyncio.Queue[str]] = {}
        self._client_seq = 0
        self._lock = asyncio.Lock()
        self._client_queue_size = client_queue_size

    async def publish(self, update: TickerUpdate) -> None:
        async with self._lock:
            self._latest[update.symbol] = update
            message = json.dumps({"type": "ticker", "data": update.model_dump()})
            queues = list(self._clients.values())

        for q in queues:
            try:
                q.put_nowait(message)
            except asyncio.QueueFull:
                try:
                    _ = q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    q.put_nowait(message)
                except asyncio.QueueFull:
                    logging.debug("Client queue still full; dropping message.")

    async def register(self) -> tuple[int, asyncio.Queue[str]]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=self._client_queue_size)
        async with self._lock:
            self._client_seq += 1
            client_id = self._client_seq
            self._clients[client_id] = q

            if self._latest:
                snapshot = json.dumps({
                    "type": "snapshot",
                    "data": [u.model_dump() for u in self._latest.values()],
                })
                try:
                    q.put_nowait(snapshot)
                except asyncio.QueueFull:
                    pass

            logging.info("Client %s connected. total_clients=%d", client_id, len(self._clients))
            return client_id, q

    async def unregister(self, client_id: int) -> None:
        async with self._lock:
            self._clients.pop(client_id, None)
            logging.info("Client %s disconnected. total_clients=%d", client_id, len(self._clients))

    async def latest(self):
        async with self._lock:
            return [u.model_dump() for u in self._latest.values()]
        
    async def client_count(self) -> int:
        async with self._lock:
            return len(self._clients)