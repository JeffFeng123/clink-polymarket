import argparse
import json
import os
import re
import shlex
import subprocess
import sys
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


def _build_prompt(request: HermesMessageRequest) -> str:
    return f"""
You are Hermes Agent operating inside Clink x Hermes Mission Control.

User request:
{request.message}

Required behavior:
1. Use the clink_polymarket MCP tools, not manual HTTP calls.
2. Search/score tradable Polymarket opportunities relevant to the request.
3. Create a Clink order preview only. Do not execute a live trade.
4. Use amount_usdc={request.amount_usdc} unless the user asked for a smaller amount.
5. Return a concise explanation plus a final JSON object with these keys when available:
   bridge_mode, status, agent_messages, selected_opportunity, order_preview_id.
6. Never call execute_approved_trade from this chat turn.

Final JSON shape:
{{
  "bridge_mode": "hermes_cli",
  "status": "preview_created",
  "agent_messages": ["..."],
  "selected_opportunity": {{"market_id": "...", "question": "..."}},
  "order_preview_id": "preview_xxx"
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
        prompt = _build_prompt(request)
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

        agent_messages = []
        if isinstance(parsed, dict) and isinstance(parsed.get("agent_messages"), list):
            agent_messages = [str(item) for item in parsed["agent_messages"]]
        if not agent_messages:
            agent_messages = [hermes["output"][-4000:] if hermes["output"] else "Hermes returned no output."]
        if preview:
            agent_messages.append(f"Loaded Clink order preview: {preview.get('order_preview_id')}")

        parsed_status = (parsed or {}).get("status") if isinstance(parsed, dict) else None
        return {
            "bridge_mode": "hermes_cli",
            "status": "preview_created" if preview else parsed_status or "hermes_completed",
            "returncode": hermes["returncode"],
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
    uvicorn.run(app, host=APP_CONFIG.hermes_bridge_host, port=APP_CONFIG.hermes_bridge_port)


if __name__ == "__main__":
    main()
