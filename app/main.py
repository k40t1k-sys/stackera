import asyncio
import contextlib
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import AsyncIterator, Deque, Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from .binance_listener import BinanceListener
from .config import Settings
from .state import Broker

class InMemoryRateLimiter:
    """
    Simple sliding-window limiter per key (IP).
    Suitable for a single-process container. For distributed limits, use Redis + fastapi-limiter.
    """
    def __init__(self, capacity: int, period_seconds: float) -> None:
        self.capacity = int(max(1, capacity))
        self.period = float(max(1.0, period_seconds))
        self._buckets: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = asyncio.Lock()

    async def hit(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.period
        async with self._lock:
            q = self._buckets[key]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self.capacity:
                return False
            q.append(now)
            return True

def create_app() -> FastAPI:
    settings = Settings()
    broker = Broker(client_queue_size=settings.client_queue_size)
    stop_event = asyncio.Event()
    limiter = InMemoryRateLimiter(
        capacity=settings.price_rate_limit_per_minute,
        period_seconds=60.0,
    )

    # Track active WS connections by IP
    ws_by_ip: Dict[str, int] = defaultdict(int)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logging.basicConfig(
            level=getattr(logging, settings.log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        )

        # Share state
        app.state.settings = settings
        app.state.broker = broker
        app.state.stop_event = stop_event
        app.state.price_rl = limiter

        # Start Binance listener
        listener = BinanceListener(settings, broker, stop_event)
        task = asyncio.create_task(listener.run(), name="binance-listener")
        logging.info("Service started. Subscribed symbols: %s", settings.symbols)

        try:
            yield
        finally:
            # Graceful shutdown
            stop_event.set()
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            logging.info("Service shutdown complete.")

    app = FastAPI(
        title="Crypto Ticker WebSocket Server",
        version="1.1.0",
        default_response_class=ORJSONResponse,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # @app.get("/healthz")
    # async def healthz():
    #     return {"status": "ok"}

    @app.get("/latest")
    async def latest():
        data = await broker.latest()
        return {"data": data}

    @app.get("/price")
    async def get_price(
        request: Request,
        symbol: str | None = Query(default=None, description="e.g., BTCUSDT"),
    ):
        # Rate limit by remote IP
        ip = request.client.host if request.client else "unknown"
        allowed = await limiter.hit(f"price:{ip}")
        if not allowed:
            raise HTTPException(status_code=429, detail="Too Many Requests")

        snapshot = await broker.latest()
        if symbol:
            sym = symbol.upper().strip()
            for item in snapshot:
                if item["symbol"] == sym:
                    return {"symbol": sym, "last_price": item["last_price"], "change_percent": item["change_percent"], "timestamp": item["timestamp"]}
            raise HTTPException(status_code=404, detail=f"Symbol {sym} not found")
        # No symbol: return all
        # (Clients can filter what they need)
        return {"data": snapshot}
    
    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await websocket.accept()
        client_id, queue = await broker.register()

        try:
            while True:
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30.0)
                    await websocket.send_text(msg)
                except asyncio.TimeoutError:
                    await websocket.send_text('{"type":"keepalive"}')
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logging.exception("WS error for client %s: %s", client_id, e)
        finally:
            await broker.unregister(client_id)
            with contextlib.suppress(Exception):
                await websocket.close()

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    settings = Settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=False,
        log_level=settings.log_level.lower(),
    )