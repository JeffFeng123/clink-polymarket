from pydantic import BaseModel, Field


class CreateOrderPreviewRequest(BaseModel):
    user_id: str
    agent_id: str = "external_agent"
    market_id: str
    question: str
    outcome: str = "Yes"
    side: str = "buy"
    amount_usdc: str
    limit_price: float
    max_slippage_bps: int = 100
    authorization_id: str | None = None
    core_action_id: str | None = None
    core_policy_decision_id: str | None = None
    core_audit_event_ids: list[str] = Field(default_factory=list)
    core_policy_decision: dict | None = None
    requires_user_confirmation: bool = True
    live_mode: bool = True
    metadata: dict = Field(default_factory=dict)


class OrderPreview(BaseModel):
    order_preview_id: str
    user_id: str
    agent_id: str
    market_id: str
    question: str
    outcome: str
    side: str
    amount_usdc: str
    limit_price: float
    estimated_shares: float
    max_slippage_bps: int
    max_slippage_usdc: str
    worst_case_price: float
    state: str
    next_action: str
    execution_mode: str = "preview_only"
    requires_user_confirmation: bool = True
    live_mode: bool = True
    authorization_id: str | None = None
    core_action_id: str | None = None
    core_policy_decision_id: str | None = None
    core_audit_event_ids: list[str] = Field(default_factory=list)
    core_policy_decision: dict | None = None
    metadata: dict = Field(default_factory=dict)
    created_at: str
    expires_at: str
    event_log: list[dict] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return self.model_dump()
