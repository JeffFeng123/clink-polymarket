import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from mcp.server.fastmcp import FastMCP

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.market_service.schemas import PredictionMarket, SearchMarketsRequest, SearchMarketsResult  # noqa: E402
from services.trade_service.schemas import CreateTradeIntentRequest, TradeIntent  # noqa: E402
from shared.config import AppConfig  # noqa: E402

CONFIG = AppConfig.from_env()
MCP_SERVER = FastMCP(
    "Clink Polymarket MCP Server",
    instructions="Expose read-only Polymarket market discovery and paper trade intent tools.",
    host=CONFIG.polymarket_mcp_host,
    port=CONFIG.polymarket_mcp_port,
    stateless_http=True,
    json_response=True,
)


def _request_json(url: str, payload: dict | None = None) -> dict:
    data = None
    method = "GET"
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8")
        raise RuntimeError(f"polymarket adapter request failed: {exc.code} {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"polymarket adapter request failed: {exc}") from exc


def _create_core_action_intent(
    user_id: str,
    amount_usdc: str,
    market_id: str,
    question: str,
    metadata: dict,
) -> dict:
    payload = {
        "user_id": user_id,
        "agent_id": "clink_polymarket_agent",
        "action_type": "market_trade",
        "amount_usdc": amount_usdc,
        "target": market_id,
        "description": question,
        "metadata": metadata,
    }
    return _request_json(f"{CONFIG.clink_core_action_service_url.rstrip('/')}/actions", payload)


def _evaluate_core_policy(
    action_id: str,
    user_id: str,
    amount_usdc: str,
    market_id: str,
    user_confirmed: bool,
    live_mode: bool,
) -> dict:
    payload = {
        "action_id": action_id,
        "user_id": user_id,
        "agent_id": "clink_polymarket_agent",
        "action_type": "market_trade",
        "amount_usdc": amount_usdc,
        "merchant_id": "polymarket",
        "risk_level": "medium" if live_mode else "low",
        "risk_score": 45 if live_mode else 20,
        "risk_action": "manual_review" if live_mode else "approve",
        "user_confirmed": user_confirmed,
        "requires_confirmation": True,
        "live_mode": live_mode,
        "metadata": {"market_id": market_id, "adapter": "clink-polymarket"},
    }
    return _request_json(f"{CONFIG.clink_core_policy_service_url.rstrip('/')}/policies/evaluate", payload)


def _write_core_audit_event(
    event_type: str,
    action_id: str,
    user_id: str,
    policy_decision_id: str | None = None,
    payload: dict | None = None,
) -> dict:
    request = {
        "event_type": event_type,
        "source_service": "clink-polymarket",
        "action_id": action_id,
        "user_id": user_id,
        "agent_id": "clink_polymarket_agent",
        "policy_decision_id": policy_decision_id,
        "payload": payload or {},
    }
    return _request_json(f"{CONFIG.clink_core_audit_service_url.rstrip('/')}/audit/events", request)


@MCP_SERVER.tool()
def search_prediction_markets(
    query: str | None = None,
    limit: int = 10,
    min_liquidity: float | None = None,
    tag_id: str | None = None,
) -> SearchMarketsResult:
    """Search active Polymarket prediction markets. Read-only."""
    request = SearchMarketsRequest(query=query, limit=limit, min_liquidity=min_liquidity, tag_id=tag_id)
    response = _request_json(f"{CONFIG.market_service_url}/markets/search", request.model_dump())
    return SearchMarketsResult(**response)


@MCP_SERVER.tool()
def create_trade_intent(
    user_id: str,
    market_id: str,
    question: str,
    amount_usdc: str,
    outcome: str = "Yes",
    side: str = "buy",
    limit_price: float | None = None,
    max_slippage_bps: int = 100,
    rationale: str | None = None,
    core_action_id: str | None = None,
    core_policy_decision_id: str | None = None,
    user_confirmed: bool = False,
    live_mode: bool = False,
    metadata: dict | None = None,
) -> TradeIntent:
    """Create a paper trade intent/order preview after clink-core action/policy/audit gates."""
    enriched_metadata = {
        **(metadata or {}),
        "market_id": market_id,
        "question": question,
        "outcome": outcome,
        "side": side,
        "adapter": "clink-polymarket",
        "live_mode": live_mode,
    }
    core_action = {"action_id": core_action_id} if core_action_id else _create_core_action_intent(
        user_id=user_id,
        amount_usdc=amount_usdc,
        market_id=market_id,
        question=question,
        metadata=enriched_metadata,
    )
    audit_action = _write_core_audit_event(
        event_type="polymarket_trade_intent_requested",
        action_id=core_action["action_id"],
        user_id=user_id,
        payload=enriched_metadata,
    )
    core_policy = (
        {"policy_decision_id": core_policy_decision_id, "approved": True, "decision": "approved", "reason_code": "PRECHECKED"}
        if core_policy_decision_id
        else _evaluate_core_policy(
            action_id=core_action["action_id"],
            user_id=user_id,
            amount_usdc=amount_usdc,
            market_id=market_id,
            user_confirmed=user_confirmed,
            live_mode=live_mode,
        )
    )
    audit_policy = _write_core_audit_event(
        event_type="polymarket_policy_evaluated",
        action_id=core_action["action_id"],
        user_id=user_id,
        policy_decision_id=core_policy.get("policy_decision_id"),
        payload={
            "approved": core_policy.get("approved"),
            "decision": core_policy.get("decision"),
            "reason_code": core_policy.get("reason_code"),
        },
    )
    if core_policy.get("decision") == "blocked":
        raise RuntimeError(f"clink-core policy blocked trade intent: {core_policy.get('reason_code')}")

    enriched_metadata["core_policy_decision"] = core_policy
    request = CreateTradeIntentRequest(
        user_id=user_id,
        market_id=market_id,
        question=question,
        amount_usdc=amount_usdc,
        outcome=outcome,
        side=side,
        limit_price=limit_price,
        max_slippage_bps=max_slippage_bps,
        rationale=rationale,
        core_action_id=core_action["action_id"],
        core_policy_decision_id=core_policy.get("policy_decision_id"),
        core_audit_event_ids=[
            event_id
            for event_id in [audit_action.get("event_id"), audit_policy.get("event_id")]
            if event_id
        ],
        metadata=enriched_metadata,
    )
    response = _request_json(f"{CONFIG.trade_service_url}/trade-intents", request.model_dump())
    return TradeIntent(**response)


@MCP_SERVER.tool()
def get_trade_intent(trade_intent_id: str) -> TradeIntent:
    """Fetch a stored paper trade intent."""
    response = _request_json(f"{CONFIG.trade_service_url}/trade-intents/{trade_intent_id}")
    return TradeIntent(**response)


@MCP_SERVER.tool()
def polymarket_adapter_health() -> dict:
    """Check backing service health."""
    market = _request_json(f"{CONFIG.market_service_url}/healthz")
    trade = _request_json(f"{CONFIG.trade_service_url}/healthz")
    return {"service": "clink_polymarket_adapter", "status": "ok", "market": market, "trade": trade}


def main() -> None:
    MCP_SERVER.run(transport="streamable-http")


if __name__ == "__main__":
    main()
