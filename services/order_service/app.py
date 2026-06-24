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

from services.order_service.schemas import CreateOrderPreviewRequest
from services.order_service.service import OrderPreviewService
from shared.config import AppConfig

APP_CONFIG = AppConfig.from_env()
SERVICE = OrderPreviewService()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clink Polymarket Order Service",
        version="0.1.0",
        description="Non-executing order preview service for controlled Polymarket live trading.",
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
        return {"service": "polymarket_order_service", "status": "ok", "mode": "preview_only"}

    @app.post("/order-previews")
    def create_order_preview(request: CreateOrderPreviewRequest) -> dict:
        return SERVICE.create_order_preview(request).to_dict()

    @app.get("/order-previews/{order_preview_id}")
    def get_order_preview(order_preview_id: str) -> dict:
        preview = SERVICE.get_order_preview(order_preview_id)
        if preview is None:
            raise HTTPException(status_code=404, detail="order preview not found")
        return preview.to_dict()

    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Polymarket order preview service")
    parser.add_argument("--sample", action="store_true", help="Print a sample order preview instead of starting the server")
    args = parser.parse_args()

    if args.sample:
        result = SERVICE.create_order_preview(
            CreateOrderPreviewRequest(
                user_id="demo-user",
                market_id="691547",
                question="Kraken IPO by December 31, 2026?",
                amount_usdc="1",
                limit_price=0.375,
            )
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    uvicorn.run(app, host=APP_CONFIG.polymarket_order_service_host, port=APP_CONFIG.polymarket_order_service_port)


if __name__ == "__main__":
    main()
