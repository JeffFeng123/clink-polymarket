from pydantic import BaseModel, Field


class CreatePaperPositionRequest(BaseModel):
    user_id: str
    trade_intent_id: str
    market_id: str
    question: str
    outcome: str = "Yes"
    side: str = "buy"
    amount_usdc: str
    entry_price: float
    current_price: float | None = None
    core_action_id: str | None = None
    core_policy_decision_id: str | None = None
    core_audit_event_ids: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class PaperPosition(BaseModel):
    position_id: str
    user_id: str
    trade_intent_id: str
    market_id: str
    question: str
    outcome: str
    side: str
    amount_usdc: str
    entry_price: float
    shares: float
    current_price: float
    current_value_usdc: str
    unrealized_pnl_usdc: str
    unrealized_pnl_pct: float
    state: str = "open"
    core_action_id: str | None = None
    core_policy_decision_id: str | None = None
    core_audit_event_ids: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return self.model_dump()


class PortfolioSnapshot(BaseModel):
    user_id: str
    positions: list[PaperPosition] = Field(default_factory=list)
    open_position_count: int
    total_amount_usdc: str
    total_current_value_usdc: str
    total_unrealized_pnl_usdc: str
    total_unrealized_pnl_pct: float

    def to_dict(self) -> dict:
        return self.model_dump()
