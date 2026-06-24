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

from services.execution_service.schemas import ExecuteApprovedTradeRequest
from services.execution_service.service import ExecutionService
from shared.config import AppConfig

APP_CONFIG = AppConfig.from_env()
SERVICE = ExecutionService()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clink Polymarket Execution Service",
        version="0.1.0",
        description="Dry-run execution gate for approved Polymarket order previews.",
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
        return {
            "service": "polymarket_execution_service",
            "status": "ok",
            "mode": "dry_run" if not APP_CONFIG.polymarket_live_mode else "live_blocked_not_implemented",
        }

    @app.post("/executions")
    def execute_approved_trade(request: ExecuteApprovedTradeRequest) -> dict:
        return SERVICE.execute_approved_trade(request).to_dict()

    @app.get("/executions/{execution_id}")
    def get_execution(execution_id: str) -> dict:
        execution = SERVICE.get_execution(execution_id)
        if execution is None:
            raise HTTPException(status_code=404, detail="execution not found")
        return execution.to_dict()

    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Polymarket execution service")
    parser.add_argument("--sample", action="store_true", help="Print a sample blocked execution instead of starting the server")
    args = parser.parse_args()

    if args.sample:
        result = SERVICE.execute_approved_trade(
            ExecuteApprovedTradeRequest(order_preview_id="missing_preview", user_confirmed=True)
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return

    uvicorn.run(app, host=APP_CONFIG.polymarket_execution_service_host, port=APP_CONFIG.polymarket_execution_service_port)


if __name__ == "__main__":
    main()
