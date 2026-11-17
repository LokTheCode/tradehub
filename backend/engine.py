"""Business logic: validation, order recording, portfolio math. No GraphQL here, so it's easy to test."""
from dataclasses import dataclass
from typing import List

from brokers import get_broker
from db import connect
from market import market

SIDES = {"BUY", "SELL"}


@dataclass
class HoldingView:
    symbol: str
    qty: int
    avg_price: float
    ltp: float
    invested: float
    current: float
    pnl: float
    pnl_pct: float
    day_change: float


@dataclass
class PortfolioView:
    cash: float
    invested: float
    current: float
    pnl: float
    pnl_pct: float
    total_value: float
    holdings: List[HoldingView]
    broker: str


def place_order(symbol: str, side: str, qty: int) -> dict:
    symbol, side = symbol.strip().upper(), side.strip().upper()
    broker = get_broker()
    if side not in SIDES:
        return _record(symbol, side, qty, 0.0, "REJECTED", broker.name, None, "Side must be BUY or SELL")
    if qty <= 0:
        return _record(symbol, side, qty, 0.0, "REJECTED", broker.name, None, "Quantity must be a positive whole number")
    try:
        price = market.quote(symbol).price
    except Exception as e:
        return _record(symbol, side, qty, 0.0, "REJECTED", broker.name, None, f"No price for {symbol}: {e}")
    res = broker.place_order(symbol, side, qty, price)
    return _record(symbol, side, qty, res.price, res.status, broker.name, res.broker_order_id, res.message)


def _record(symbol, side, qty, price, status, broker, broker_order_id, message) -> dict:
    with connect() as c:
        cur = c.execute(
            "INSERT INTO orders (symbol, side, qty, price, status, broker, broker_order_id, message) VALUES (?,?,?,?,?,?,?,?)",
            (symbol, side, qty, price, status, broker, broker_order_id, message),
        )
        return dict(c.execute("SELECT * FROM orders WHERE id=?", (cur.lastrowid,)).fetchone())


def orders(limit: int = 50) -> List[dict]:
    with connect() as c:
        return [dict(r) for r in c.execute("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,))]


def portfolio() -> PortfolioView:
    broker = get_broker()
    views, invested, current, day = [], 0.0, 0.0, 0.0
    for p in broker.holdings():
        q = market.quote(p.symbol)
        inv, cur = p.qty * p.avg_price, p.qty * q.price
        invested += inv
        current += cur
        dc = p.qty * (q.price - q.prev_close)
        day += dc
        views.append(HoldingView(p.symbol, p.qty, round(p.avg_price, 2), q.price, round(inv, 2), round(cur, 2),
                                 round(cur - inv, 2), round((cur - inv) / inv * 100, 2) if inv else 0.0, round(dc, 2)))
    cash = broker.cash()
    pnl = current - invested
    return PortfolioView(round(cash, 2), round(invested, 2), round(current, 2), round(pnl, 2),
                         round(pnl / invested * 100, 2) if invested else 0.0, round(cash + current, 2), views, broker.name)


def watchlist() -> List[str]:
    with connect() as c:
        return [r["symbol"] for r in c.execute("SELECT symbol FROM watchlist ORDER BY rowid")]


def add_watch(symbol: str) -> List[str]:
    symbol = symbol.strip().upper()
    market.quote(symbol)  # raises if the symbol has no price at all
    with connect() as c:
        c.execute("INSERT OR IGNORE INTO watchlist (symbol) VALUES (?)", (symbol,))
    return watchlist()


def remove_watch(symbol: str) -> List[str]:
    with connect() as c:
        c.execute("DELETE FROM watchlist WHERE symbol=?", (symbol.strip().upper(),))
    return watchlist()
