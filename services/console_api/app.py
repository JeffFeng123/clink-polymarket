import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from mcp_servers.polymarket_server import (  # noqa: E402
    check_live_readiness,
    create_order_preview,
    execute_approved_trade,
    get_order_preview,
    get_trade_execution,
    polymarket_adapter_health,
    score_market_opportunities,
)
from shared.config import AppConfig  # noqa: E402

APP_CONFIG = AppConfig.from_env()
SITE_DIR = ROOT_DIR / "console_site"


class AgentMessageRequest(BaseModel):
    user_id: str = "console-user"
    agent_id: str = "hermes_console_agent"
    message: str
    amount_usdc: str = "1"
    max_results: int = 3
    execute_preview: bool = False


class ExecutePreviewRequest(BaseModel):
    order_preview_id: str
    live_phrase: str
    metadata: dict = Field(default_factory=dict)


class PreviewLookupRequest(BaseModel):
    order_preview_id: str


def _to_dict(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_dict(item) for key, item in value.items()}
    return value


def _post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _call_hermes_bridge(request: AgentMessageRequest) -> dict | None:
    bridge_url = os.getenv("HERMES_AGENT_HTTP_URL", "").strip()
    if not bridge_url:
        return None
    try:
        return _post_json(
            bridge_url.rstrip("/") + "/message",
            {
                "user_id": request.user_id,
                "agent_id": request.agent_id,
                "message": request.message,
                "amount_usdc": request.amount_usdc,
                "source": "clink_console",
            },
        )
    except Exception as exc:
        return {
            "bridge_mode": "http_bridge_failed",
            "error": f"{type(exc).__name__}: {exc}",
        }


def _run_local_hermes_flow(request: AgentMessageRequest) -> dict:
    opportunities = score_market_opportunities(
        goal=request.message,
        query=None,
        limit=20,
        max_results=request.max_results,
        tradable_only=True,
    )
    opportunities_payload = opportunities.model_dump()
    items = opportunities_payload.get("opportunities", [])
    if not items:
        return {
            "bridge_mode": "local_mcp_runner",
            "status": "no_opportunity",
            "agent_messages": [
                "Hermes-compatible runner searched tradable markets but did not find a usable opportunity.",
                "Try a more specific market query, for example: Kraken IPO or Fed rates.",
            ],
            "opportunities": opportunities_payload,
        }

    selected = items[0]
    market = selected.get("market") or {}
    preview = create_order_preview(
        user_id=request.user_id,
        agent_id=request.agent_id,
        market_id=str(selected.get("market_id")),
        question=str(selected.get("question")),
        outcome=str(selected.get("outcome") or "Yes"),
        side="buy",
        amount_usdc=request.amount_usdc,
        limit_price=float(selected.get("price")),
        max_slippage_bps=100,
        metadata={
            "console_message": request.message,
            "hermes_bridge_mode": "local_mcp_runner",
            "selected_opportunity": selected,
            "market": market,
        },
    )
    preview_payload = preview.model_dump()
    return {
        "bridge_mode": "local_mcp_runner",
        "status": "preview_created",
        "agent_messages": [
            "Hermes-compatible runner received the user goal.",
            f"Selected market: {selected.get('question')}",
            f"Created Clink order preview: {preview_payload.get('order_preview_id')}",
            "Waiting for human LIVE confirmation in the console.",
        ],
        "opportunities": opportunities_payload,
        "selected_opportunity": selected,
        "order_preview": preview_payload,
    }


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clink x Hermes Mission Control",
        version="0.1.0",
        description="Human console for Hermes-driven Polymarket previews and Clink live execution confirmation.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/healthz")
    def healthz() -> dict:
        return {
            "service": "clink_hermes_console_api",
            "status": "ok",
            "mode": "hermes_http_bridge" if os.getenv("HERMES_AGENT_HTTP_URL") else "local_mcp_runner",
            "site_dir": str(SITE_DIR),
        }

    @app.get("/api/readiness")
    def readiness() -> dict:
        return _to_dict(check_live_readiness())

    @app.get("/api/adapter-health")
    def adapter_health() -> dict:
        return _to_dict(polymarket_adapter_health())

    @app.post("/api/agent/message")
    def agent_message(request: AgentMessageRequest) -> dict:
        bridged = _call_hermes_bridge(request)
        if bridged is not None and bridged.get("bridge_mode") != "http_bridge_failed":
            return bridged
        local = _run_local_hermes_flow(request)
        if bridged is not None:
            local["hermes_bridge_error"] = bridged.get("error")
        return local

    @app.post("/api/previews/lookup")
    def lookup_preview(request: PreviewLookupRequest) -> dict:
        return _to_dict(get_order_preview(request.order_preview_id))

    @app.post("/api/executions")
    def execute_preview(request: ExecutePreviewRequest) -> dict:
        if request.live_phrase.strip() != "LIVE":
            raise HTTPException(status_code=400, detail="Type LIVE to confirm live Polymarket submission")
        return _to_dict(
            execute_approved_trade(
                order_preview_id=request.order_preview_id,
                user_confirmed=True,
                live_submission_confirmed=True,
                confirmation_message="Confirmed from Clink x Hermes Mission Control",
                metadata={"source": "clink_console", **request.metadata},
            )
        )

    @app.get("/api/executions/{execution_id}")
    def execution(execution_id: str) -> dict:
        return _to_dict(get_trade_execution(execution_id))

    if SITE_DIR.exists():
        app.mount("/", StaticFiles(directory=str(SITE_DIR), html=True), name="console_site")

    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Clink x Hermes Mission Control console")
    parser.add_argument("--sample", action="store_true", help="Print readiness instead of starting the server")
    args = parser.parse_args()
    if args.sample:
        print(json.dumps({"service": "clink_hermes_console_api", "status": "ok", "mode": "hermes_http_bridge" if os.getenv("HERMES_AGENT_HTTP_URL") else "local_mcp_runner"}, indent=2))
        return
    uvicorn.run(app, host=APP_CONFIG.console_api_host, port=APP_CONFIG.console_api_port)


if __name__ == "__main__":
    main()
