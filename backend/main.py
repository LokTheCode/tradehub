import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastapi import FastAPI
from fastapi.responses import FileResponse
from strawberry.fastapi import GraphQLRouter

from db import init_db
from schema import schema

init_db(float(os.getenv("PAPER_START_CASH", "100000")))

app = FastAPI(title="TradeHub")
app.include_router(GraphQLRouter(schema, graphql_ide="graphiql"), prefix="/graphql")  # open /graphql to explore

FRONTEND = os.path.join(os.path.dirname(__file__), "..", "frontend", "index.html")


@app.get("/")
def home():
    return FileResponse(FRONTEND)
