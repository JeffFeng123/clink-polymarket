import argparse
import json
import logging
import os
import re
import shlex
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from mcp_servers.polymarket_server import get_order_preview  # noqa: E402
from shared.config import AppConfig  # noqa: E402

APP_CONFIG = AppConfig.from_env()
LOGGER = logging.getLogger("clink_hermes_bridge")


class HermesMessageRequest(BaseModel):
    user_id: str = "console-user"
    agent_id: str = "hermes_console_agent"
    message: str
    amount_usdc: str = "1"
    source: str = "clink_console"
    metadata: dict = Field(default_factory=dict)


def _to_dict(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, list):
        return [_to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_dict(item) for key, item in value.items()}
    return value


def _extract_json_object(text: str) -> dict | None:
    decoder = json.JSONDecoder()
    best: dict | None = None
    for match in re.finditer(r"\{", text):
        try:
            value, _ = decoder.raw_decode(text[match.start():])
        except json.JSONDecodeError:
            continue
        if not isinstance(value, dict):
            continue
        if "order_preview_id" in value or "agent_messages" in value:
            return value
        best = value
    return best


def _extract_preview_id(text: str) -> str | None:
    match = re.search(r"preview_[a-fA-F0-9]{12}|preview_[A-Za-z0-9]+", text)
    return match.group(0) if match else None


def _load_preview(preview_id: str | None) -> dict | None:
    if not preview_id:
        return None
    try:
        return _to_dict(get_order_preview(preview_id))
    except Exception:
        return None


def _is_placeholder_message(message: str) -> bool:
    normalized = message.strip().lower()
    return normalized in {"", "...", "…", "。。。", "[...]", "[... ]"}


def _agent_messages(parsed: dict | None, output: str) -> list[str]:
    if isinstance(parsed, dict) and isinstance(parsed.get("agent_messages"), list):
        messages = [str(item).strip() for item in parsed["agent_messages"]]
        messages = [message for message in messages if not _is_placeholder_message(message)]
        if messages:
            return messages
        return [
            "Hermes returned a placeholder response instead of a final answer. "
            "The bridge received the response; check raw_hermes_output in the API response or clink_hermes_bridge.log."
        ]
    if output.strip():
        return [output[-4000:]]
    return ["Hermes returned no output."]


def _build_prompt(request: HermesMessageRequest, request_id: str) -> str:
    return f"""
You are Hermes Agent operating inside Clink x Hermes Mission Control.

Bridge request_id: {request_id}
User request:
{request.message}

Routing rules:
1. If the user is greeting you, asking who you are, or asking a non-trading question, answer directly. Do not call tools.
2. If the user asks to find a Polymarket opportunity or create an order preview, use the clink_polymarket MCP tools, not manual HTTP calls.
3. For trading requests, search/score tradable Polymarket opportunities relevant to the request and create a Clink order preview only. Do not execute a live trade.
4. For trading requests, use amount_usdc={request.amount_usdc} unless the user asked for a smaller amount.
5. Never call execute_approved_trade from this chat turn.
6. Do not return placeholder text such as ... or [...].

Return a concise natural-language answer plus a final JSON object.
For normal chat, use this shape with real content:
{{
  "bridge_mode": "hermes_cli",
  "status": "chat_response",
  "agent_messages": ["我是 Hermes，已经连接到 Clink 控制台。你可以让我寻找 Polymarket 机会或创建订单预览。"],
  "selected_opportunity": null,
  "order_preview_id": null
}}

For trading preview creation, use this shape with real content:
{{
  "bridge_mode": "hermes_cli",
  "status": "preview_created",
  "agent_messages": ["已找到一个可交易市场，并创建了 Clink order preview，等待你在控制台输入 LIVE 确认。"],
  "selected_opportunity": {{"market_id": "691547", "question": "Kraken IPO by December 31, 2026?"}},
  "order_preview_id": "preview_actual_id"
}}
""".strip()


def _run_hermes(prompt: str) -> dict:
    command = shlex.split(os.getenv("HERMES_BRIDGE_COMMAND", "hermes chat -q") or "hermes chat -q")
    timeout = int(os.getenv("HERMES_BRIDGE_TIMEOUT_SECONDS", "180"))
    workdir = os.getenv("HERMES_BRIDGE_WORKDIR") or str(ROOT_DIR)
    env = os.environ.copy()
    env.setdefault("HERMES_ACCEPT_HOOKS", "1")
    result = subprocess.run(
        [*command, prompt],
        cwd=workdir,
        env=env,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    output = "\n".join(part for part in [result.stdout, result.stderr] if part).strip()
    return {"returncode": result.returncode, "output": output}


def create_app() -> FastAPI:
    app = FastAPI(
        title="Clink Hermes Bridge Service",
        version="0.1.0",
        description="HTTP bridge that lets Clink Console talk to real Hermes CLI sessions.",
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
            "service": "clink_hermes_bridge_service",
            "status": "ok",
            "mode": "hermes_cli",
            "command": os.getenv("HERMES_BRIDGE_COMMAND", "hermes chat -q"),
            "workdir": os.getenv("HERMES_BRIDGE_WORKDIR") or str(ROOT_DIR),
        }

    @app.post("/message")
    def message(request: HermesMessageRequest) -> dict:
        request_id = f"hmsg_{uuid.uuid4().hex[:12]}"
        LOGGER.info("received request_id=%s source=%s message_chars=%s", request_id, request.source, len(request.message))
        prompt = _build_prompt(request, request_id)
        try:
            hermes = _run_hermes(prompt)
        except subprocess.TimeoutExpired as exc:
            raise HTTPException(status_code=504, detail=f"Hermes timed out after {exc.timeout}s") from exc
        except FileNotFoundError as exc:
            raise HTTPException(status_code=500, detail="hermes command not found in PATH") from exc

        parsed = _extract_json_object(hermes["output"])
        preview_id = None
        if isinstance(parsed, dict):
            preview_id = parsed.get("order_preview_id") or (parsed.get("order_preview") or {}).get("order_preview_id")
        preview_id = preview_id or _extract_preview_id(hermes["output"])
        preview = _load_preview(preview_id)

        agent_messages = _agent_messages(parsed, hermes["output"])
        if preview:
            agent_messages.append(f"Loaded Clink order preview: {preview.get('order_preview_id')}")

        parsed_status = (parsed or {}).get("status") if isinstance(parsed, dict) else None
        LOGGER.info(
            "completed request_id=%s returncode=%s output_chars=%s status=%s preview_id=%s",
            request_id,
            hermes["returncode"],
            len(hermes["output"]),
            parsed_status or "hermes_completed",
            preview_id,
        )
        return {
            "request_id": request_id,
            "hermes_received": True,
            "bridge_mode": "hermes_cli",
            "status": "preview_created" if preview else parsed_status or "hermes_completed",
            "returncode": hermes["returncode"],
            "hermes_returncode": hermes["returncode"],
            "raw_hermes_output_length": len(hermes["output"]),
            "agent_messages": agent_messages,
            "selected_opportunity": (parsed or {}).get("selected_opportunity") if isinstance(parsed, dict) else None,
            "order_preview": preview,
            "order_preview_id": preview_id,
            "raw_hermes_output": hermes["output"],
        }

    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Clink Hermes HTTP bridge")
    parser.add_argument("--sample", action="store_true", help="Print bridge health instead of starting the server")
    args = parser.parse_args()
    if args.sample:
        print(json.dumps({"service": "clink_hermes_bridge_service", "status": "ok", "mode": "hermes_cli"}, indent=2))
        return
    logging.basicConfig(level=os.getenv("HERMES_BRIDGE_LOG_LEVEL", "INFO"))
    uvicorn.run(app, host=APP_CONFIG.hermes_bridge_host, port=APP_CONFIG.hermes_bridge_port)


if __name__ == "__main__":
    main()
