import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from services.market_service.schemas import PredictionMarket, SearchMarketsRequest, SearchMarketsResult
from shared.config import AppConfig


class PolymarketMarketService:
    """Read-only Polymarket market discovery backed by Gamma API with demo fallback."""

    def __init__(self) -> None:
        self.config = AppConfig.from_env()

    def search_markets(self, request: SearchMarketsRequest) -> SearchMarketsResult:
        try:
            events = self._fetch_active_events(request)
            markets = self._normalize_events(events, request)
            source = "polymarket_gamma_api"
        except Exception:
            markets = self._mock_markets(request)
            source = "mock_fallback"
        if request.query:
            needle = request.query.lower()
            markets = [
                market
                for market in markets
                if needle in market.question.lower() or needle in (market.event_title or "").lower()
            ]
        if request.min_liquidity is not None:
            markets = [market for market in markets if (market.liquidity or 0) >= request.min_liquidity]
        markets = markets[: max(1, min(request.limit, 100))]
        return SearchMarketsResult(query=request.query, source=source, markets=markets, count=len(markets))

    def _fetch_active_events(self, request: SearchMarketsRequest) -> list[dict[str, Any]]:
        params: dict[str, str] = {
            "active": "true",
            "closed": "false",
            "order": "volume_24hr",
            "ascending": "false",
            "limit": str(max(1, min(request.limit, 100))),
        }
        if request.tag_id:
            params["tag_id"] = request.tag_id
        url = f"{self.config.polymarket_gamma_api_url.rstrip('/')}/events?{urllib.parse.urlencode(params)}"
        http_request = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(http_request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            return payload["data"]
        return []

    def _normalize_events(self, events: list[dict[str, Any]], request: SearchMarketsRequest) -> list[PredictionMarket]:
        normalized: list[PredictionMarket] = []
        for event in events:
            event_id = str(event.get("id") or event.get("event_id") or "")
            event_title = event.get("title") or event.get("question") or event.get("slug")
            for market in event.get("markets") or []:
                normalized.append(self._normalize_market(market, event_id, event_title))
                if len(normalized) >= request.limit:
                    return normalized
        return normalized

    def _normalize_market(self, market: dict[str, Any], event_id: str | None, event_title: str | None) -> PredictionMarket:
        outcomes = self._parse_jsonish_list(market.get("outcomes"))
        prices = [self._safe_float(item) for item in self._parse_jsonish_list(market.get("outcomePrices"))]
        yes_price = prices[0] if prices else self._safe_float(market.get("bestAsk") or market.get("lastTradePrice"))
        no_price = prices[1] if len(prices) > 1 else (1 - yes_price if yes_price is not None else None)
        slug = market.get("slug")
        return PredictionMarket(
            market_id=str(market.get("id") or market.get("market_id") or market.get("conditionId") or slug),
            condition_id=market.get("conditionId"),
            question=market.get("question") or market.get("title") or event_title or "Untitled Polymarket market",
            slug=slug,
            event_id=event_id,
            event_title=event_title,
            outcomes=[str(item) for item in outcomes],
            outcome_prices=[price for price in prices if price is not None],
            best_yes_price=yes_price,
            best_no_price=no_price,
            liquidity=self._safe_float(market.get("liquidity") or market.get("liquidityNum")),
            volume=self._safe_float(market.get("volume") or market.get("volumeNum")),
            volume_24hr=self._safe_float(market.get("volume24hr") or market.get("volume_24hr")),
            end_date=market.get("endDate") or market.get("end_date_iso"),
            active=bool(market.get("active", True)),
            closed=bool(market.get("closed", False)),
            url=f"https://polymarket.com/event/{slug}" if slug else None,
        )

    @staticmethod
    def _parse_jsonish_list(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        return []

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    def _mock_markets(self, request: SearchMarketsRequest) -> list[PredictionMarket]:
        return [
            PredictionMarket(
                market_id="mock_market_001",
                condition_id="mock_condition_001",
                question="Will a major AI agent payment protocol announce production trading support in 2026?",
                slug="mock-ai-agent-payment-trading-2026",
                event_id="mock_event_001",
                event_title="AI Agent Commerce",
                outcomes=["Yes", "No"],
                outcome_prices=[0.42, 0.58],
                best_yes_price=0.42,
                best_no_price=0.58,
                liquidity=25000,
                volume=120000,
                volume_24hr=8000,
                end_date="2026-12-31T00:00:00Z",
                url="https://polymarket.com/event/mock-ai-agent-payment-trading-2026",
            ),
            PredictionMarket(
                market_id="mock_market_002",
                condition_id="mock_condition_002",
                question="Will prediction market agent trading volume double before year end?",
                slug="mock-prediction-market-agent-volume-double",
                event_id="mock_event_002",
                event_title="Prediction Market Agents",
                outcomes=["Yes", "No"],
                outcome_prices=[0.36, 0.64],
                best_yes_price=0.36,
                best_no_price=0.64,
                liquidity=18000,
                volume=90000,
                volume_24hr=5200,
                end_date="2026-12-31T00:00:00Z",
                url="https://polymarket.com/event/mock-prediction-market-agent-volume-double",
            ),
        ][: max(1, min(request.limit, 100))]
