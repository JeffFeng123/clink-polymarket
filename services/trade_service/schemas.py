from pydantic import BaseModel, Field


class CreateTradeIntentRequest(BaseModel):
    user_id: str
    agent_id: str = "clink_polymarket_agent"
    market_id: str
    question: str
    outcome: str = "Yes"
    side: str = "buy"
    amount_usdc: str
    limit_price: float | None = None
    max_slippage_bps: int = 100
    rationale: str | None = None
    core_action_id: str | None = None
    core_policy_decision_id: str | None = None
    metadata: dict = Field(default_factory=dict)


class TradeIntent(BaseModel):
    trade_intent_id: str
    user_id: str
    agent_id: str
    market_id: str
    question: str
    outcome: str
    side: str
    amount_usdc: str
    limit_price: float | None = None
    estimated_shares: float | None = None
    max_slippage_bps: int
    state: str
    rationale: str | None = None
    core_action_id: str | None = None
    core_policy_decision_id: str | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: str
    updated_at: str
    event_log: list[dict] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return self.model_dump()
