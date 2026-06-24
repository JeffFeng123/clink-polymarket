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

from services.portfolio_service.schemas import CreatePaperPositionRequest
from services.portfolio_service.service import PortfolioService
from shared.config import AppConfig

APP_CONFIG = AppConfig.from_env()
SERVICE = PortfolioService()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clink Polymarket Portfolio Service",
        version="0.1.0",
        description="Paper position and portfolio tracking for agent-facing Polymarket demos.",
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
        return {"service": "polymarket_portfolio_service", "status": "ok", "mode": "paper_only"}

    @app.post("/positions")
    def create_position(request: CreatePaperPositionRequest) -> dict:
        return SERVICE.create_position(request).to_dict()

    @app.get("/positions/{position_id}")
    def get_position(position_id: str) -> dict:
        position = SERVICE.get_position(position_id)
        if position is None:
            raise HTTPException(status_code=404, detail="position not found")
        return position.to_dict()

    @app.get("/portfolio/{user_id}")
    def get_portfolio(user_id: str) -> dict:
        return SERVICE.get_portfolio(user_id).to_dict()

    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Polymarket portfolio service")
    parser.add_argument("--sample", action="store_true", help="Print a sample paper position instead of starting the server")
    args = parser.parse_args()

    if args.sample:
        result = SERVICE.create_position(
            CreatePaperPositionRequest(
                user_id="demo-user",
                trade_intent_id="trade_sample",
                market_id="mock_market_001",
                question="Will prediction market agents become a major category in 2026?",
                amount_usdc="1",
                entry_price=0.42,
            )
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    uvicorn.run(app, host=APP_CONFIG.polymarket_portfolio_service_host, port=APP_CONFIG.polymarket_portfolio_service_port)


if __name__ == "__main__":
    main()
