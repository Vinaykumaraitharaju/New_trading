"""Independent synthetic trade arrivals; rates are not estimates of real liquidity."""
import heapq
import random
import time


def trade_arrivals(symbols, stop, *, rng=random, clock=time.monotonic):
    start = clock()
    rates = {symbol: rng.uniform(0.6, 3.0) for symbol in symbols}
    pending = [(start + rng.expovariate(rate), symbol) for symbol, rate in rates.items()]
    heapq.heapify(pending)
    while pending and not stop.is_set():
        due, symbol = heapq.heappop(pending)
        if stop.wait(max(0.0, due - clock())):
            return
        yield symbol
        # Schedule from completion: slow processing must not cause catch-up bursts.
        heapq.heappush(pending, (clock() + rng.expovariate(rates[symbol]), symbol))
