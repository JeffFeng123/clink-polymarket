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

from services.opportunity_service.schemas import ScoreOpportunitiesRequest
from services.opportunity_service.service import OpportunityService
from shared.config import AppConfig

APP_CONFIG = AppConfig.from_env()
SERVICE = OpportunityService()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clink Polymarket Opportunity Service",
        version="0.1.0",
        description="Scores Polymarket markets for agent-readable trade opportunity selection.",
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
        return {"service": "polymarket_opportunity_service", "status": "ok", "mode": "paper_signal"}

    @app.post("/opportunities/score")
    def score_opportunities(request: ScoreOpportunitiesRequest) -> dict:
        return SERVICE.score_opportunities(request).to_dict()

    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Polymarket opportunity service")
    parser.add_argument("--sample", action="store_true", help="Print a sample score instead of starting the server")
    args = parser.parse_args()

    if args.sample:
        result = SERVICE.score_opportunities(
            ScoreOpportunitiesRequest(
                goal="agent trading",
                markets=[
                    {
                        "market_id": "mock_market_001",
                        "question": "Will agent trading volume double in 2026?",
                        "outcomes": ["Yes", "No"],
                        "best_yes_price": 0.42,
                        "liquidity": 25000,
                        "volume_24hr": 8000,
                    }
                ],
            )
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    uvicorn.run(app, host=APP_CONFIG.polymarket_opportunity_service_host, port=APP_CONFIG.polymarket_opportunity_service_port)


if __name__ == "__main__":
    main()
