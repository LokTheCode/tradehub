"""Market data: free yfinance (real, ~15 min delayed, unofficial) or a built-in simulator."""
import hashlib
import math
import os
import random
import time
from dataclasses import dataclass
from typing import List

CACHE_SECONDS = 15


@dataclass
class Quote:
    symbol: str
    price: float
    prev_close: float

    @property
    def change(self) -> float:
        return round(self.price - self.prev_close, 2)

    @property
    def change_pct(self) -> float:
        return round((self.price - self.prev_close) / self.prev_close * 100, 2) if self.prev_close else 0.0


@dataclass
class Candle:
    time: int  # unix seconds
    open: float
    high: float
    low: float
    close: float


# range -> (yfinance period, interval, sim bars, sim bar seconds)
RANGES = {
    "1D": ("1d", "5m", 75, 300),
    "1W": ("5d", "30m", 70, 1800),
    "1M": ("1mo", "1d", 22, 86400),
    "6M": ("6mo", "1d", 126, 86400),
    "1Y": ("1y", "1d", 252, 86400),
}


class SimProvider:
    """Deterministic fake prices. Works offline; good for demos and tests."""

    def _base(self, symbol: str) -> float:
        h = int(hashlib.md5(symbol.encode()).hexdigest()[:8], 16)
        return 100 + (h % 3000)

    def _series(self, symbol: str, bars: int, step: int) -> List[Candle]:
        # Walk is seeded per symbol+time bucket so every call agrees with the last.
        end = int(time.time() // step) * step
        out, price = [], self._base(symbol)
        start = end - bars * step
        for i in range(bars + 1):
            t = start + i * step
            rnd = random.Random(f"{symbol}:{t}")
            drift = math.sin(t / 900000.0 + self._base(symbol)) * 0.0004
            o = price
            c = max(1.0, o * (1 + drift + rnd.gauss(0, 0.004)))
            hi = max(o, c) * (1 + abs(rnd.gauss(0, 0.0015)))
            lo = min(o, c) * (1 - abs(rnd.gauss(0, 0.0015)))
            out.append(Candle(t, round(o, 2), round(hi, 2), round(lo, 2), round(c, 2)))
            price = c
        return out

    def quote(self, symbol: str) -> Quote:
        s = self._series(symbol, 80, 300)
        return Quote(symbol, s[-1].close, s[-40].close)

    def history(self, symbol: str, rng: str) -> List[Candle]:
        _, _, bars, step = RANGES[rng]
        return self._series(symbol, bars, step)


class YFinanceProvider:
    def __init__(self):
        import yfinance as yf  # imported lazily so sim mode needs no install
        self.yf = yf

    def quote(self, symbol: str) -> Quote:
        fi = self.yf.Ticker(f"{symbol}.NS").fast_info
        return Quote(symbol, round(float(fi["last_price"]), 2), round(float(fi["previous_close"]), 2))

    def history(self, symbol: str, rng: str) -> List[Candle]:
        period, interval, _, _ = RANGES[rng]
        df = self.yf.Ticker(f"{symbol}.NS").history(period=period, interval=interval)
        return [
            Candle(int(ts.timestamp()), round(r.Open, 2), round(r.High, 2), round(r.Low, 2), round(r.Close, 2))
            for ts, r in df.iterrows()
        ]


class Market:
    def __init__(self):
        self.sim = SimProvider()
        self.primary = self.sim
        self.fallback_note = ""
        if os.getenv("MARKET_DATA", "yfinance").lower() == "yfinance":
            try:
                self.primary = YFinanceProvider()
            except Exception as e:  # not installed -> fall back so the app still runs
                self.fallback_note = f"yfinance unavailable ({e}); using simulated prices"
        self._cache = {}

    def quote(self, symbol: str) -> Quote:
        symbol = symbol.upper()
        hit = self._cache.get(symbol)
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
        try:
            q = self.primary.quote(symbol)
        except Exception:
            q = self.sim.quote(symbol)
        self._cache[symbol] = (time.time(), q)
        return q

    def history(self, symbol: str, rng: str = "1M") -> List[Candle]:
        symbol = symbol.upper()
        if rng not in RANGES:
            rng = "1M"
        try:
            data = self.primary.history(symbol, rng)
            if data:
                return data
        except Exception:
            pass
        return self.sim.history(symbol, rng)


market = Market()
