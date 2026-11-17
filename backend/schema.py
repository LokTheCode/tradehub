"""GraphQL schema (Strawberry, free & open source)."""
import asyncio
from typing import List, Optional

import strawberry

import engine
from market import market


@strawberry.type
class Quote:
    symbol: str
    price: float
    prev_close: float
    change: float
    change_pct: float
    direction: str  # UP | DOWN | FLAT


@strawberry.type
class Candle:
    time: int
    open: float
    high: float
    low: float
    close: float


@strawberry.type
class Holding:
    symbol: str
    qty: int
    avg_price: float
    ltp: float
    invested: float
    current: float
    pnl: float
    pnl_pct: float
    day_change: float


@strawberry.type
class Portfolio:
    cash: float
    invested: float
    current: float
    pnl: float
    pnl_pct: float
    total_value: float
    broker: str
    holdings: List[Holding]


@strawberry.type
class Order:
    id: int
    created_at: str
    symbol: str
    side: str
    qty: int
    price: float
    status: str
    broker: str
    message: Optional[str]


def _quote(symbol: str) -> Quote:
    q = market.quote(symbol)
    d = "UP" if q.change > 0 else "DOWN" if q.change < 0 else "FLAT"
    return Quote(symbol=q.symbol, price=q.price, prev_close=q.prev_close, change=q.change, change_pct=q.change_pct, direction=d)


def _order(o: dict) -> Order:
    return Order(id=o["id"], created_at=o["created_at"], symbol=o["symbol"], side=o["side"], qty=o["qty"],
                 price=o["price"], status=o["status"], broker=o["broker"], message=o["message"])


@strawberry.type
class Query:
    @strawberry.field
    async def watchlist(self) -> List[Quote]:
        symbols = await asyncio.to_thread(engine.watchlist)
        out = await asyncio.gather(*(asyncio.to_thread(_quote, s) for s in symbols))
        return list(out)

    @strawberry.field
    async def quote(self, symbol: str) -> Quote:
        return await asyncio.to_thread(_quote, symbol)

    @strawberry.field
    async def history(self, symbol: str, range: str = "1M") -> List[Candle]:
        rows = await asyncio.to_thread(market.history, symbol, range)
        return [Candle(time=r.time, open=r.open, high=r.high, low=r.low, close=r.close) for r in rows]

    @strawberry.field
    async def portfolio(self) -> Portfolio:
        p = await asyncio.to_thread(engine.portfolio)
        return Portfolio(
            cash=p.cash, invested=p.invested, current=p.current, pnl=p.pnl, pnl_pct=p.pnl_pct,
            total_value=p.total_value, broker=p.broker,
            holdings=[Holding(**h.__dict__) for h in p.holdings],
        )

    @strawberry.field
    async def orders(self, limit: int = 50) -> List[Order]:
        return [_order(o) for o in await asyncio.to_thread(engine.orders, limit)]


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def place_order(self, symbol: str, side: str, qty: int) -> Order:
        return _order(await asyncio.to_thread(engine.place_order, symbol, side, qty))

    @strawberry.mutation
    async def add_to_watchlist(self, symbol: str) -> List[str]:
        return await asyncio.to_thread(engine.add_watch, symbol)

    @strawberry.mutation
    async def remove_from_watchlist(self, symbol: str) -> List[str]:
        return await asyncio.to_thread(engine.remove_watch, symbol)


schema = strawberry.Schema(query=Query, mutation=Mutation)
