from app.schemas import TickerUpdate


def test_ticker_from_binance_single():
    payload = {"s": "BTCUSDT", "c": "65000.01", "P": "2.15", "E": 1699999999000}
    t = TickerUpdate.from_binance(payload)
    assert t.symbol == "BTCUSDT"
    assert t.last_price == "65000.01"
    assert t.change_percent == "2.15"
    assert t.timestamp == 1699999999000


def test_ticker_from_binance_combined():
    message = {
        "stream": "btcusdt@ticker",
        "data": {"s": "BTCUSDT", "c": "65100.00", "P": "-0.25", "E": 1699999999555},
    }
    t = TickerUpdate.from_binance(message["data"])
    assert t.symbol == "BTCUSDT"
    assert t.last_price == "65100.00"
    assert t.change_percent == "-0.25"
    assert t.timestamp == 1699999999555
