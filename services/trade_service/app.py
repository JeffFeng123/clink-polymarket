import argparse
import json
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.trade_service.schemas import CreateTradeIntentRequest
from services.trade_service.service import TradeService
from shared.config import AppConfig

APP_CONFIG = AppConfig.from_env()
SERVICE = TradeService()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clink Polymarket Trade Service",
        version="0.1.0",
        description="Paper trade intent and order preview service for Polymarket adapter.",
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
        return {"service": "polymarket_trade_service", "status": "ok", "mode": "paper_only"}

    @app.post("/trade-intents")
    def create_trade_intent(request: CreateTradeIntentRequest) -> dict:
        return SERVICE.create_trade_intent(request).to_dict()

    @app.get("/trade-intents/{trade_intent_id}")
    def get_trade_intent(trade_intent_id: str) -> dict:
        intent = SERVICE.get_trade_intent(trade_intent_id)
        if intent is None:
            raise HTTPException(status_code=404, detail="trade intent not found")
        return intent.to_dict()

    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Polymarket trade service")
    parser.add_argument("--sample", action="store_true", help="Print a sample trade intent instead of starting the server")
    args = parser.parse_args()

    if args.sample:
        result = SERVICE.create_trade_intent(
            CreateTradeIntentRequest(
                user_id="demo-user",
                market_id="mock_market_001",
                question="Will prediction market agents become a major category in 2026?",
                outcome="Yes",
                amount_usdc="1",
                limit_price=0.42,
                rationale="Sample paper trade intent; not submitted to Polymarket.",
            )
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    uvicorn.run(app, host=APP_CONFIG.polymarket_trade_service_host, port=APP_CONFIG.polymarket_trade_service_port)


if __name__ == "__main__":
    main()
