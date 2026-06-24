import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

from mcp.server.fastmcp import FastMCP

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.execution_service.schemas import ExecuteApprovedTradeRequest, LiveReadiness, TradeExecution  # noqa: E402
from services.market_service.schemas import SearchMarketsRequest, SearchMarketsResult  # noqa: E402
from services.opportunity_service.schemas import ScoreOpportunitiesRequest, ScoreOpportunitiesResult  # noqa: E402
from services.order_service.schemas import CreateOrderPreviewRequest, OrderPreview  # noqa: E402
from services.portfolio_service.schemas import CreatePaperPositionRequest, PaperPosition, PortfolioSnapshot  # noqa: E402
from services.trade_service.schemas import CreateTradeIntentRequest, TradeIntent  # noqa: E402
from shared.config import AppConfig  # noqa: E402

CONFIG = AppConfig.from_env()
MCP_SERVER = FastMCP(
    "Clink Polymarket MCP Server",
    instructions="Expose public MCP tools for Polymarket discovery, opportunity scoring, core-governed trade intents, and paper portfolio tracking.",
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
    agent_id: str,
    amount_usdc: str,
    market_id: str,
    question: str,
    metadata: dict,
) -> dict:
    payload = {
        "user_id": user_id,
        "agent_id": agent_id,
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
    agent_id: str,
    amount_usdc: str,
    market_id: str,
    user_confirmed: bool,
    live_mode: bool,
) -> dict:
    payload = {
        "action_id": action_id,
        "user_id": user_id,
        "agent_id": agent_id,
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
    agent_id: str,
    policy_decision_id: str | None = None,
    payload: dict | None = None,
) -> dict:
    request = {
        "event_type": event_type,
        "source_service": "clink-polymarket",
        "action_id": action_id,
        "user_id": user_id,
        "agent_id": agent_id,
        "policy_decision_id": policy_decision_id,
        "payload": payload or {},
    }
    return _request_json(f"{CONFIG.clink_core_audit_service_url.rstrip('/')}/audit/events", request)


def _choose_price(market: dict, fallback: float | None = None) -> float | None:
    price = market.get("best_yes_price")
    if price is None:
        prices = market.get("outcome_prices") if isinstance(market.get("outcome_prices"), list) else []
        price = prices[0] if prices else fallback
    try:
        return float(price) if price is not None else None
    except (TypeError, ValueError):
        return fallback


@MCP_SERVER.tool()
def search_prediction_markets(
    query: str | None = None,
    limit: int = 10,
    min_liquidity: float | None = None,
    tag_id: str | None = None,
    tradable_only: bool = False,
) -> SearchMarketsResult:
    """Search active Polymarket prediction markets. Read-only."""
    request = SearchMarketsRequest(
        query=query,
        limit=limit,
        min_liquidity=min_liquidity,
        tag_id=tag_id,
        tradable_only=tradable_only,
    )
    response = _request_json(f"{CONFIG.market_service_url}/markets/search", request.model_dump())
    return SearchMarketsResult(**response)


@MCP_SERVER.tool()
def score_market_opportunities(
    query: str | None = None,
    goal: str | None = None,
    limit: int = 10,
    max_results: int = 5,
    min_liquidity: float | None = None,
    tradable_only: bool = True,
    markets: list[dict] | None = None,
) -> ScoreOpportunitiesResult:
    """Score candidate markets so any external agent can decide what to inspect or trade."""
    candidate_markets = markets
    if candidate_markets is None:
        # Natural-language goals are often full sentences. Keep them for scoring,
        # but do not use them as exact market-search filters unless explicitly requested.
        search = search_prediction_markets(
            query=query,
            limit=limit,
            min_liquidity=min_liquidity,
            tradable_only=tradable_only,
        )
        candidate_markets = [market.model_dump() for market in search.markets]
        if not candidate_markets and query:
            fallback = search_prediction_markets(
                query=None,
                limit=limit,
                min_liquidity=min_liquidity,
                tradable_only=tradable_only,
            )
            candidate_markets = [market.model_dump() for market in fallback.markets]
    request = ScoreOpportunitiesRequest(
        markets=candidate_markets,
        goal=goal or query,
        max_results=max_results,
        min_liquidity=min_liquidity,
    )
    response = _request_json(f"{CONFIG.opportunity_service_url}/opportunities/score", request.model_dump())
    return ScoreOpportunitiesResult(**response)


@MCP_SERVER.tool()
def create_trade_intent(
    user_id: str,
    market_id: str,
    question: str,
    amount_usdc: str,
    agent_id: str = "clink_polymarket_agent",
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
        agent_id=agent_id,
        amount_usdc=amount_usdc,
        market_id=market_id,
        question=question,
        metadata=enriched_metadata,
    )
    audit_action = _write_core_audit_event(
        event_type="polymarket_trade_intent_requested",
        action_id=core_action["action_id"],
        user_id=user_id,
        agent_id=agent_id,
        payload=enriched_metadata,
    )
    core_policy = (
        {"policy_decision_id": core_policy_decision_id, "approved": True, "decision": "approved", "reason_code": "PRECHECKED"}
        if core_policy_decision_id
        else _evaluate_core_policy(
            action_id=core_action["action_id"],
            user_id=user_id,
            agent_id=agent_id,
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
        agent_id=agent_id,
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
        agent_id=agent_id,
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
def create_order_preview(
    user_id: str,
    market_id: str,
    question: str,
    amount_usdc: str,
    limit_price: float,
    agent_id: str = "external_agent",
    outcome: str = "Yes",
    side: str = "buy",
    max_slippage_bps: int = 100,
    authorization_id: str | None = None,
    user_confirmed: bool = False,
    metadata: dict | None = None,
) -> OrderPreview:
    """Create a non-executing live order preview that requires user confirmation before any future live execution."""
    enriched_metadata = {
        **(metadata or {}),
        "market_id": market_id,
        "question": question,
        "outcome": outcome,
        "side": side,
        "adapter": "clink-polymarket",
        "live_mode": True,
        "preview_only": True,
    }
    core_action = _create_core_action_intent(
        user_id=user_id,
        agent_id=agent_id,
        amount_usdc=amount_usdc,
        market_id=market_id,
        question=question,
        metadata=enriched_metadata,
    )
    audit_requested = _write_core_audit_event(
        event_type="polymarket_order_preview_requested",
        action_id=core_action["action_id"],
        user_id=user_id,
        agent_id=agent_id,
        payload=enriched_metadata,
    )
    core_policy = _evaluate_core_policy(
        action_id=core_action["action_id"],
        user_id=user_id,
        agent_id=agent_id,
        amount_usdc=amount_usdc,
        market_id=market_id,
        user_confirmed=user_confirmed,
        live_mode=True,
    )
    audit_policy = _write_core_audit_event(
        event_type="polymarket_order_preview_policy_evaluated",
        action_id=core_action["action_id"],
        user_id=user_id,
        agent_id=agent_id,
        policy_decision_id=core_policy.get("policy_decision_id"),
        payload={
            "approved": core_policy.get("approved"),
            "decision": core_policy.get("decision"),
            "reason_code": core_policy.get("reason_code"),
        },
    )
    request = CreateOrderPreviewRequest(
        user_id=user_id,
        agent_id=agent_id,
        market_id=market_id,
        question=question,
        outcome=outcome,
        side=side,
        amount_usdc=amount_usdc,
        limit_price=limit_price,
        max_slippage_bps=max_slippage_bps,
        authorization_id=authorization_id,
        core_action_id=core_action["action_id"],
        core_policy_decision_id=core_policy.get("policy_decision_id"),
        core_audit_event_ids=[
            event_id
            for event_id in [audit_requested.get("event_id"), audit_policy.get("event_id")]
            if event_id
        ],
        core_policy_decision=core_policy,
        requires_user_confirmation=True,
        live_mode=True,
        metadata=enriched_metadata,
    )
    response = _request_json(f"{CONFIG.order_service_url}/order-previews", request.model_dump())
    return OrderPreview(**response)


@MCP_SERVER.tool()
def check_live_readiness() -> LiveReadiness:
    """Check whether this adapter is configured for real Polymarket execution without exposing secrets."""
    response = _request_json(f"{CONFIG.execution_service_url}/live-readiness")
    return LiveReadiness(**response)


@MCP_SERVER.tool()
def execute_approved_trade(
    order_preview_id: str,
    user_confirmed: bool = False,
    confirmation_message: str | None = None,
    metadata: dict | None = None,
) -> TradeExecution:
    """Evaluate execution for an order preview. Defaults to dry-run unless POLYMARKET_LIVE_MODE is explicitly enabled."""
    request = ExecuteApprovedTradeRequest(
        order_preview_id=order_preview_id,
        user_confirmed=user_confirmed,
        confirmation_message=confirmation_message,
        metadata=metadata or {},
    )
    response = _request_json(f"{CONFIG.execution_service_url}/executions", request.model_dump())
    execution = TradeExecution(**response)
    if execution.core_action_id:
        _write_core_audit_event(
            event_type="polymarket_trade_execution_evaluated",
            action_id=execution.core_action_id,
            user_id=execution.user_id or "unknown",
            agent_id=execution.agent_id or "unknown",
            policy_decision_id=execution.core_policy_decision_id,
            payload={
                "execution_id": execution.execution_id,
                "order_preview_id": execution.order_preview_id,
                "state": execution.state,
                "execution_mode": execution.execution_mode,
                "submitted_to_polymarket": execution.submitted_to_polymarket,
                "reason": execution.reason,
            },
        )
    return execution


@MCP_SERVER.tool()
def get_trade_execution(execution_id: str) -> TradeExecution:
    """Fetch a stored dry-run/live execution evaluation."""
    response = _request_json(f"{CONFIG.execution_service_url}/executions/{execution_id}")
    return TradeExecution(**response)


@MCP_SERVER.tool()
def get_order_preview(order_preview_id: str) -> OrderPreview:
    """Fetch a stored non-executing order preview."""
    response = _request_json(f"{CONFIG.order_service_url}/order-previews/{order_preview_id}")
    return OrderPreview(**response)


@MCP_SERVER.tool()
def create_paper_position(
    user_id: str,
    trade_intent_id: str,
    market_id: str,
    question: str,
    amount_usdc: str,
    entry_price: float,
    outcome: str = "Yes",
    side: str = "buy",
    current_price: float | None = None,
    core_action_id: str | None = None,
    core_policy_decision_id: str | None = None,
    core_audit_event_ids: list[str] | None = None,
    metadata: dict | None = None,
) -> PaperPosition:
    """Record a paper position and expose amount/PnL without live order execution."""
    request = CreatePaperPositionRequest(
        user_id=user_id,
        trade_intent_id=trade_intent_id,
        market_id=market_id,
        question=question,
        outcome=outcome,
        side=side,
        amount_usdc=amount_usdc,
        entry_price=entry_price,
        current_price=current_price,
        core_action_id=core_action_id,
        core_policy_decision_id=core_policy_decision_id,
        core_audit_event_ids=core_audit_event_ids or [],
        metadata=metadata or {},
    )
    response = _request_json(f"{CONFIG.portfolio_service_url}/positions", request.model_dump())
    return PaperPosition(**response)


@MCP_SERVER.tool()
def get_portfolio_status(user_id: str) -> PortfolioSnapshot:
    """Return open paper positions, capital deployed, current value, and unrealized PnL."""
    response = _request_json(f"{CONFIG.portfolio_service_url}/portfolio/{user_id}")
    return PortfolioSnapshot(**response)


@MCP_SERVER.tool()
def submit_agent_trade_intent(
    user_id: str,
    goal: str,
    amount_usdc: str,
    agent_id: str = "external_agent",
    query: str | None = None,
    user_confirmed: bool = False,
    max_results: int = 5,
    live_mode: bool = False,
) -> dict:
    """One-call public MCP flow for agents: score markets, pass core gates, create a paper trade intent, and record a paper position."""
    opportunities = score_market_opportunities(query=query or goal, goal=goal, limit=max_results, max_results=max_results)
    if not opportunities.opportunities:
        raise RuntimeError("no Polymarket opportunities found")
    selected = next(
        (item for item in opportunities.opportunities if item.recommended_action in {"paper_trade", "watch"}),
        opportunities.opportunities[0],
    )
    if selected.recommended_action == "reject":
        raise RuntimeError("top opportunity was rejected by adapter scoring")

    market = selected.market
    entry_price = _choose_price(market, selected.price)
    if entry_price is None:
        raise RuntimeError("selected market has no usable price")

    trade_intent = create_trade_intent(
        user_id=user_id,
        agent_id=agent_id,
        market_id=selected.market_id,
        question=selected.question,
        outcome=selected.outcome,
        side="buy",
        amount_usdc=amount_usdc,
        limit_price=entry_price,
        rationale=f"Agent goal: {goal}. Adapter score: {selected.opportunity_score}.",
        user_confirmed=user_confirmed,
        live_mode=live_mode,
        metadata={
            "goal": goal,
            "opportunity_score": selected.model_dump(),
            "public_mcp_surface": True,
        },
    )
    position = create_paper_position(
        user_id=user_id,
        trade_intent_id=trade_intent.trade_intent_id,
        market_id=trade_intent.market_id,
        question=trade_intent.question,
        outcome=trade_intent.outcome,
        side=trade_intent.side,
        amount_usdc=trade_intent.amount_usdc,
        entry_price=entry_price,
        current_price=entry_price,
        core_action_id=trade_intent.core_action_id,
        core_policy_decision_id=trade_intent.core_policy_decision_id,
        core_audit_event_ids=trade_intent.core_audit_event_ids,
        metadata={"agent_id": agent_id, "goal": goal},
    )
    portfolio = get_portfolio_status(user_id)
    return {
        "approved": True,
        "agent_id": agent_id,
        "selected_opportunity": selected.model_dump(),
        "trade_intent": trade_intent.model_dump(),
        "position": position.model_dump(),
        "portfolio": portfolio.model_dump(),
        "next_action": "paper_position_created",
    }


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
    opportunity = _request_json(f"{CONFIG.opportunity_service_url}/healthz")
    portfolio = _request_json(f"{CONFIG.portfolio_service_url}/healthz")
    order = _request_json(f"{CONFIG.order_service_url}/healthz")
    execution = _request_json(f"{CONFIG.execution_service_url}/healthz")
    return {
        "service": "clink_polymarket_adapter",
        "status": "ok",
        "public_mcp_surface": True,
        "market": market,
        "trade": trade,
        "opportunity": opportunity,
        "portfolio": portfolio,
        "order": order,
        "execution": execution,
    }


def main() -> None:
    MCP_SERVER.run(transport="streamable-http")


if __name__ == "__main__":
    main()
