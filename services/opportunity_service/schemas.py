from pydantic import BaseModel, Field


class ScoreOpportunitiesRequest(BaseModel):
    markets: list[dict] = Field(default_factory=list)
    goal: str | None = None
    max_results: int = 5
    min_liquidity: float | None = None
    preferred_price_min: float = 0.2
    preferred_price_max: float = 0.8


class OpportunityScore(BaseModel):
    market_id: str
    question: str
    outcome: str = "Yes"
    price: float | None = None
    liquidity: float | None = None
    volume_24hr: float | None = None
    opportunity_score: int
    risk_level: str
    recommended_action: str
    reasons: list[str] = Field(default_factory=list)
    market: dict = Field(default_factory=dict)


class ScoreOpportunitiesResult(BaseModel):
    goal: str | None = None
    opportunities: list[OpportunityScore] = Field(default_factory=list)
    count: int

    def to_dict(self) -> dict:
        return self.model_dump()
