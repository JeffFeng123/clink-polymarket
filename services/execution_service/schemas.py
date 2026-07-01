from pydantic import BaseModel, Field


class ExecuteApprovedTradeRequest(BaseModel):
    order_preview_id: str
    user_confirmed: bool = False
    live_submission_confirmed: bool = False
    confirmation_message: str | None = None
    metadata: dict = Field(default_factory=dict)


class TradeExecution(BaseModel):
    execution_id: str
    order_preview_id: str
    user_id: str | None = None
    agent_id: str | None = None
    market_id: str | None = None
    question: str | None = None
    outcome: str | None = None
    side: str | None = None
    token_id: str | None = None
    amount_usdc: str | None = None
    limit_price: float | None = None
    estimated_shares: float | None = None
    state: str
    execution_mode: str
    submitted_to_polymarket: bool = False
    live_mode_enabled: bool = False
    order_id: str | None = None
    tx_hash: str | None = None
    reason: str | None = None
    next_action: str | None = None
    core_action_id: str | None = None
    core_policy_decision_id: str | None = None
    core_audit_event_ids: list[str] = Field(default_factory=list)
    created_at: str
    event_log: list[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    def to_dict(self) -> dict:
        return self.model_dump()


class LiveReadiness(BaseModel):
    live_ready: bool
    live_mode_enabled: bool
    missing: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    configured: dict = Field(default_factory=dict)
    max_order_usdc: str
    next_action: str

    def to_dict(self) -> dict:
        return self.model_dump()
