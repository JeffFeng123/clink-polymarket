from pydantic import BaseModel, Field


class SearchMarketsRequest(BaseModel):
    query: str | None = None
    limit: int = 10
    min_liquidity: float | None = None
    tag_id: str | None = None
    tradable_only: bool = False


class PredictionMarket(BaseModel):
    market_id: str
    condition_id: str | None = None
    question: str
    slug: str | None = None
    event_id: str | None = None
    event_title: str | None = None
    outcomes: list[str] = Field(default_factory=list)
    outcome_prices: list[float] = Field(default_factory=list)
    best_yes_price: float | None = None
    best_no_price: float | None = None
    liquidity: float | None = None
    volume: float | None = None
    volume_24hr: float | None = None
    end_date: str | None = None
    active: bool = True
    closed: bool = False
    url: str | None = None

    def to_dict(self) -> dict:
        return self.model_dump()


class SearchMarketsResult(BaseModel):
    query: str | None = None
    source: str
    source_detail: str | None = None
    markets: list[PredictionMarket] = Field(default_factory=list)
    count: int

    def to_dict(self) -> dict:
        return self.model_dump()
