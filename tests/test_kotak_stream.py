import asyncio
from contextlib import asynccontextmanager
from threading import Event
from types import SimpleNamespace

from data.kotak_neo_feed import KotakNeoFeed


def test_sdk_stream_routes_indices_and_stops_idle_socket():
    received, closed = Event(), Event()
    groups = {}

    class Socket:
        async def subscribe_scrips(self, tokens):
            groups["stocks"] = [t.instrument_token for t in tokens]

        async def subscribe_index(self, tokens):
            groups["indices"] = [t.instrument_token for t in tokens]

        async def __aiter__(self):
            yield SimpleNamespace(model_dump=lambda: dict(instrument_token="1",
                                  last_traded_price=123.5, volume_traded_today=200))
            await asyncio.Event().wait()

    @asynccontextmanager
    async def socket():
        try:
            yield Socket()
        finally:
            closed.set()

    feed = KotakNeoFeed("test")
    feed._client = SimpleNamespace(create_websocket=socket)
    feed._authenticated = True
    try:
        feed.start_live_feed([dict(instrument_token="1", symbol="TEST"),
                              dict(instrument_token="2", is_index=True)],
                             on_tick=lambda _: received.set(), wait_timeout=3)
        assert received.wait(3)
        assert groups == {"stocks": ["1"], "indices": ["2"]}
        tick = feed.get_latest_live_ticks()["1"]
        assert (tick.symbol, tick.ltp, tick.raw["v"]) == ("TEST", 123.5, 200)
    finally:
        feed.stop_live_feed()
    assert closed.wait(3)
