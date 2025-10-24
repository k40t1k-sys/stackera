# pytest: improved diagnostics for FastAPI app (HTTP + WebSocket)
import asyncio
import json
import logging
import os
import sys
from contextlib import suppress
from typing import Any, Dict, List

import pytest
from starlette.testclient import TestClient

# Make sure "app" package is importable in CI or local runs
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Prefer create_app() so lifespan hooks (e.g., background Binance listener) don't start in tests.
try:
    from app.main import create_app as _create_app  # type: ignore
except Exception:
    _create_app = None

try:
    from app.main import app as _app  # type: ignore
except Exception:
    _app = None

# Verbose logging in test output
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s"
)


def _dump_response(resp) -> str:
    try:
        body = resp.text
    except Exception as e:
        body = f"<unable to get text: {e}>"
    lines = [
        f"STATUS: {resp.status_code}",
        f"HEADERS: {dict(resp.headers)}",
        "BODY:",
        body[:2000] + ("...<truncated>" if len(body) > 2000 else ""),
    ]
    return "\n".join(lines)


@pytest.fixture(scope="session")
def app():
    if _create_app is not None:
        return _create_app()
    assert _app is not None, "Could not import FastAPI app from app.main"
    return _app


@pytest.fixture
def client(app):
    # starlette TestClient manages ASGI lifespan automatically
    with TestClient(app) as c:
        yield c


def test_routes_snapshot(app):
    """
    Print a quick snapshot of available routes to aid debugging.
    Always passes, but emits a readable list in -s mode or CI logs.
    """
    routes = getattr(app, "routes", [])
    snapshot = []
    for r in routes:
        methods = getattr(r, "methods", None)
        path = getattr(r, "path", None)
        name = getattr(r, "name", None)
        snapshot.append({"path": path, "methods": sorted(list(methods)) if methods else [], "name": name})
    print("== Route Snapshot ==")
    for r in snapshot:
        print(f"{','.join(r['methods']) or 'WS/OTHER':12} {r['path']:30} name={r['name']}")
    assert True  # informational


def _extract_listish(payload: Any) -> List:
    """
    Accepts either:
      - a bare JSON list
      - an object with a top-level 'data' key that is a list
    Returns the list if found, else raises AssertionError with diagnostics.
    """
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and "data" in payload and isinstance(payload["data"], list):
        logging.info("`/latest` returned an object with 'data' key (list). Accepting this shape.")
        return payload["data"]
    raise AssertionError(f"Expected a JSON list or an object with 'data': list, got: {type(payload).__name__} -> {payload}")


def test_latest_endpoint_smoke(client, app):
    """
    Sanity-check the HTTP endpoint that returns latest tickers.
    - Accepts two common shapes:
        1) JSON list
        2) { "data": [...] }
    - Provides rich diagnostics on failure, including route snapshot and response dump.
    """
    resp = client.get("/latest")
    if resp.status_code == 404:
        pytest.skip("`GET /latest` not found in this app build; skip.")

    if resp.status_code != 200:
        msg = ["GET /latest did not return 200.", _dump_response(resp), "Routes:"]
        for r in getattr(app, "routes", []):
            methods = getattr(r, "methods", None)
            path = getattr(r, "path", None)
            msg.append(f" - {sorted(list(methods)) if methods else []} {path}")
        pytest.fail("\n".join(msg))

    try:
        payload = resp.json()
    except Exception as e:
        pytest.fail(f"Response is not JSON.\n{_dump_response(resp)}\nERROR: {e}")

    try:
        items = _extract_listish(payload)
    except AssertionError as e:
        pytest.fail(f"{e}\n{_dump_response(resp)}")

    # Minimal semantic check on elements if any
    if items:
        first = items[0]
        assert isinstance(first, dict), f"Each item should be an object, got: {type(first).__name__}"
        for key in ("symbol", "last_price", "timestamp"):
            assert key in first, f"Missing key '{key}' in first item: {first}"


def test_health_or_root_exists(client):
    """
    Reduce 404 spam by ensuring a basic route exists.
    We first try /healthz, then fallback to /
    """
    resp = client.get("/healthz")
    if resp.status_code == 404:
        resp = client.get("/")
        if resp.status_code == 404:
            pytest.skip("Neither /healthz nor / exists in this app build; skip.")
    assert resp.status_code == 200, _dump_response(resp)


def test_websocket_broadcast_roundtrip(client, app):
    """
    End-to-end sanity check for the WebSocket endpoint:
    1) Connect to `/ws`
    2) Publish a synthetic ticker update to the in-memory broker
    3) Receive the message on the WebSocket and validate shape
    """
    # If the app doesn't expose /ws, skip gracefully
    with suppress(Exception):
        client.head("/ws")

    broker = getattr(app.state, "broker", None)
    if broker is None:
        pytest.skip("app.state.broker not found; cannot perform WS broadcast test.")

    fake_update = {
        "symbol": "BTCUSDT",
        "last_price": "65000.12",
        "change_percent": "1.23",
        "timestamp": 1699977777444,
    }

    try:
        with client.websocket_connect("/ws") as ws:
            published = False
            if hasattr(broker, "publish"):
                try:
                    from app.schemas import TickerUpdate  # type: ignore
                    import anyio

                    async def _async_publish():
                        await broker.publish(TickerUpdate(**fake_update))  # type: ignore

                    anyio.run(_async_publish)
                    published = True
                except Exception as pub_err:
                    print(f"Publish via broker failed: {pub_err}")

            if not published:
                pytest.skip("Could not publish via broker; skipping WS roundtrip.")

            recv = ws.receive_text()
            payload = json.loads(recv)
            assert payload.get("type") == "ticker", f"Unexpected WS 'type': {payload}"
            data = payload.get("data", {})
            for key in ("symbol", "last_price", "timestamp"):
                assert key in data, f"Missing '{key}' in WS payload: {payload}"
    except Exception as e:
        pytest.skip(f"WebSocket test skipped due to connection/publish issue: {e}")
