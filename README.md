# TradeHub

A small Groww-style stock app: watchlist with live up/down, candlestick charts, buy/sell, portfolio P&L, order history.
Backend = Python + FastAPI + **GraphQL (Strawberry, free)** + SQLite. Frontend = React (no build step). Everything is free.

## Run it (Windows)

```
cd tradehub
py -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
uvicorn main:app --reload --app-dir backend
```

Open http://127.0.0.1:8000 for the app and http://127.0.0.1:8000/graphql for the GraphQL playground.

No internet / yfinance problems? Set `MARKET_DATA=sim` in `.env` for fake moving prices.

## Modes

| `BROKER=` | What happens |
|-----------|--------------|
| `paper` (default) | Virtual money (₹1,00,000). Real NSE prices (delayed) from yfinance. Safe. |
| `angelone` | **Real orders** through Angel One SmartAPI (free API). Skeleton, untested. |

### Going live checklist (Angel One)
1. Have an Angel One demat account and create a SmartAPI app (API key, TOTP enabled).
2. `pip install smartapi-python pyotp logzero websocket-client`
3. Fill the `ANGEL_*` values in `.env`, set `BROKER=angelone` and `LIVE_TRADING_CONFIRM=I_UNDERSTAND`.
4. Keep `LIVE_MAX_ORDER_VALUE` small. Test with 1 share of a cheap stock.
5. SEBI's retail algo rules (from 1 April 2026) may require a registered static IP and daily login. Check Angel One's current docs.
6. yfinance prices are unofficial and delayed. Do not trade real money on them. Use the broker's market-data feed for live mode.

## Example GraphQL

```graphql
{ watchlist { symbol price changePct direction } }
mutation { placeOrder(symbol: "TCS", side: "BUY", qty: 2) { status price message } }
```

## Layout
- `backend/market.py` prices (yfinance or simulator)
- `backend/brokers.py` PaperBroker and AngelOneBroker
- `backend/engine.py` order validation and portfolio math
- `backend/schema.py` GraphQL types, queries, mutations
- `frontend/index.html` the UI
