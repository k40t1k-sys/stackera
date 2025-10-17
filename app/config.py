import json
from typing import List, Annotated
from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _parse_csv_or_json(v, upper=False):
    """
    Accepts a native list, a JSON array string, or a CSV string.
    Optionally uppercases elements (for symbols).
    """
    def _cast_list(lst):
        out = [str(x).strip() for x in lst if str(x).strip()]
        return [s.upper() for s in out] if upper else out

    if isinstance(v, list):
        return _cast_list(v)
    if isinstance(v, str):
        s = v.strip()
        if s.startswith("["):
            try:
                return _cast_list(json.loads(s))
            except Exception:
                pass
        return _cast_list([part for part in s.split(",")])
    return v



CsvSymbols = Annotated[List[str], BeforeValidator(lambda v: _parse_csv_or_json(v, upper=True))]
CsvList    = Annotated[List[str], BeforeValidator(lambda v: _parse_csv_or_json(v, upper=False))]

class Settings(BaseSettings):
    # First symbol should remain BTCUSDT per requirements.
    symbols: CsvSymbols = ["BTCUSDT", "ETHUSDT"]

    binance_base_url: str = "wss://stream.binance.com:9443"

    reconnect_min_delay: float = 1.0
    reconnect_max_delay: float = 30.0

    ping_interval: float = 20.0
    ping_timeout: float = 20.0

    client_queue_size: int = 100
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    max_ws_connections: int = 200
    max_ws_connections_per_ip: int = 10
    price_rate_limit_per_minute: int = 120  # per IP for GET /price

    cors_allow_origins: CsvList = ["*"]

    model_config = SettingsConfigDict(env_prefix="APP_", case_sensitive=False)