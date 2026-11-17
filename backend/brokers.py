"""Brokers. The rest of the app only talks to the Broker interface.

PaperBroker  - virtual money in SQLite. Safe default.
AngelOneBroker - REAL money through Angel One SmartAPI (free API). UNTESTED skeleton:
                 try it with 1 share of a cheap stock first.
"""
import os
from dataclasses import dataclass
from typing import List, Optional

from db import connect


@dataclass
class OrderResult:
    status: str  # COMPLETE | REJECTED | PENDING
    price: float
    message: str = ""
    broker_order_id: Optional[str] = None


@dataclass
class Position:
    symbol: str
    qty: int
    avg_price: float


class Broker:
    name = "base"

    def place_order(self, symbol: str, side: str, qty: int, price: float) -> OrderResult:
        raise NotImplementedError

    def holdings(self) -> List[Position]:
        raise NotImplementedError

    def cash(self) -> float:
        raise NotImplementedError


class PaperBroker(Broker):
    name = "paper"

    def place_order(self, symbol, side, qty, price) -> OrderResult:
        with connect() as c:  # single transaction: either everything applies or nothing
            cash = c.execute("SELECT cash FROM account WHERE id=1").fetchone()["cash"]
            row = c.execute("SELECT qty, avg_price FROM holdings WHERE symbol=?", (symbol,)).fetchone()
            value = round(price * qty, 2)
            if side == "BUY":
                if value > cash:
                    return OrderResult("REJECTED", price, f"Insufficient funds: need {value:.2f}, have {cash:.2f}")
                old_q, old_p = (row["qty"], row["avg_price"]) if row else (0, 0.0)
                new_q = old_q + qty
                new_avg = (old_q * old_p + qty * price) / new_q
                c.execute(
                    "INSERT INTO holdings (symbol, qty, avg_price) VALUES (?,?,?) "
                    "ON CONFLICT(symbol) DO UPDATE SET qty=excluded.qty, avg_price=excluded.avg_price",
                    (symbol, new_q, round(new_avg, 4)),
                )
                c.execute("UPDATE account SET cash = cash - ? WHERE id=1", (value,))
            else:  # SELL
                if not row or row["qty"] < qty:
                    have = row["qty"] if row else 0
                    return OrderResult("REJECTED", price, f"Not enough shares: have {have}, trying to sell {qty}")
                left = row["qty"] - qty
                if left == 0:
                    c.execute("DELETE FROM holdings WHERE symbol=?", (symbol,))
                else:
                    c.execute("UPDATE holdings SET qty=? WHERE symbol=?", (left, symbol))
                c.execute("UPDATE account SET cash = cash + ? WHERE id=1", (value,))
        return OrderResult("COMPLETE", price, "Filled (paper)")

    def holdings(self) -> List[Position]:
        with connect() as c:
            return [Position(r["symbol"], r["qty"], r["avg_price"]) for r in c.execute("SELECT * FROM holdings ORDER BY symbol")]

    def cash(self) -> float:
        with connect() as c:
            return c.execute("SELECT cash FROM account WHERE id=1").fetchone()["cash"]


class AngelOneBroker(Broker):
    """REAL orders. Needs: pip install smartapi-python pyotp logzero websocket-client

    Notes (please verify against Angel One's current docs before trusting this):
    - SEBI's retail algo rules (from 1 April 2026) can require a registered static IP,
      a fresh login each day, and no plain market orders. So we send LIMIT orders.
    - Orders are placed as DELIVERY (CNC) on NSE.
    """
    name = "angelone"
    SCRIP_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"

    def __init__(self):
        if os.getenv("LIVE_TRADING_CONFIRM") != "I_UNDERSTAND":
            raise RuntimeError("Real trading is locked. Set LIVE_TRADING_CONFIRM=I_UNDERSTAND in .env to unlock.")
        import pyotp
        from SmartApi import SmartConnect

        self.api = SmartConnect(api_key=os.environ["ANGEL_API_KEY"])
        session = self.api.generateSession(
            os.environ["ANGEL_CLIENT_CODE"], os.environ["ANGEL_PIN"], pyotp.TOTP(os.environ["ANGEL_TOTP_SECRET"]).now()
        )
        if not session or not session.get("status"):
            raise RuntimeError(f"Angel One login failed: {session}")
        self.max_value = float(os.getenv("LIVE_MAX_ORDER_VALUE", "5000"))
        self._tokens = None

    def _token(self, symbol: str):
        if self._tokens is None:
            import json
            import urllib.request

            with urllib.request.urlopen(self.SCRIP_URL, timeout=30) as r:
                data = json.load(r)
            self._tokens = {
                d["name"]: (d["symbol"], d["token"]) for d in data if d.get("exch_seg") == "NSE" and d["symbol"].endswith("-EQ")
            }
        return self._tokens.get(symbol)

    def place_order(self, symbol, side, qty, price) -> OrderResult:
        value = price * qty
        if value > self.max_value:
            return OrderResult("REJECTED", price, f"Blocked by safety cap: order value {value:.0f} > LIVE_MAX_ORDER_VALUE {self.max_value:.0f}")
        tok = self._token(symbol)
        if not tok:
            return OrderResult("REJECTED", price, f"Symbol {symbol} not found in Angel One instrument list")
        tradingsymbol, token = tok
        # Marketable limit: 0.5% through the price so it fills like a market order
        limit = round(price * (1.005 if side == "BUY" else 0.995), 1)
        params = {
            "variety": "NORMAL", "tradingsymbol": tradingsymbol, "symboltoken": token,
            "transactiontype": side, "exchange": "NSE", "ordertype": "LIMIT",
            "producttype": "DELIVERY", "duration": "DAY", "price": str(limit), "quantity": str(qty),
        }
        try:
            order_id = self.api.placeOrder(params)
        except Exception as e:
            return OrderResult("REJECTED", price, f"Broker error: {e}")
        # Status is PENDING: the exchange may not have filled it yet. Check the Angel One app.
        return OrderResult("PENDING", limit, "Sent to Angel One", str(order_id))

    def holdings(self) -> List[Position]:
        resp = self.api.holding() or {}
        return [Position(h["tradingsymbol"].replace("-EQ", ""), int(h["quantity"]), float(h["averageprice"])) for h in (resp.get("data") or [])]

    def cash(self) -> float:
        resp = self.api.rmsLimit() or {}
        return float((resp.get("data") or {}).get("availablecash", 0))


_broker: Optional[Broker] = None


def get_broker() -> Broker:
    global _broker
    if _broker is None:
        _broker = AngelOneBroker() if os.getenv("BROKER", "paper").lower() == "angelone" else PaperBroker()
    return _broker
