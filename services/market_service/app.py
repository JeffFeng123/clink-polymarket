import argparse
import json
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.market_service.schemas import SearchMarketsRequest
from services.market_service.service import PolymarketMarketService
from shared.config import AppConfig

APP_CONFIG = AppConfig.from_env()
SERVICE = PolymarketMarketService()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clink Polymarket Market Service",
        version="0.1.0",
        description="Read-only market discovery adapter for Polymarket.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz")
    def healthz() -> dict:
        return {"service": "polymarket_market_service", "status": "ok", "mode": "read_only"}

    @app.post("/markets/search")
    def search_markets(request: SearchMarketsRequest) -> dict:
        return SERVICE.search_markets(request).to_dict()

    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Polymarket market service")
    parser.add_argument("--sample", action="store_true", help="Print a sample market search instead of starting the server")
    parser.add_argument("--query", default=None)
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()

    if args.sample:
        result = SERVICE.search_markets(SearchMarketsRequest(query=args.query, limit=args.limit))
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    uvicorn.run(app, host=APP_CONFIG.polymarket_market_service_host, port=APP_CONFIG.polymarket_market_service_port)


if __name__ == "__main__":
    main()
