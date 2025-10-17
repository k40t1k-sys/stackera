from datetime import datetime, timezone
from pydantic import BaseModel, Field


class TickerUpdate(BaseModel):
    """Normalized ticker update we broadcast to clients."""
    symbol: str = Field(..., examples=["BTCUSDT"])
    last_price: str = Field(..., description="Last traded price as string", examples=["64000.12"])
    change_percent: str = Field(..., description="24h price change percentage as string", examples=["1.25"])
    timestamp: int = Field(..., description="Event time in epoch ms", examples=[1699977777444])

    @property
    def iso_time(self) -> str:
        return datetime.fromtimestamp(self.timestamp / 1000, tz=timezone.utc).isoformat()

    @classmethod
    def from_binance(cls, d: dict) -> "TickerUpdate":
        """
        Accepts message object from either single stream or combined stream:
          - keys we rely on: s (symbol), c (last price), P (24h %), E (event time)
        """
        s = d.get("s")
        c = d.get("c")
        P = d.get("P")
        E = d.get("E")
        if s is None or c is None or P is None or E is None:
            raise ValueError(f"Missing required fields in Binance ticker message; keys={list(d.keys())}")
        return cls(symbol=str(s), last_price=str(c), change_percent=str(P), timestamp=int(E))