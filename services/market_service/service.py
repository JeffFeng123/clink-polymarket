import json
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
        source_detail = None
        try:
            events, source_detail = self._fetch_active_events(request)
            markets = self._normalize_events(events, request)
            source = "polymarket_gamma_api"
            if not markets:
                source_detail = source_detail or "Gamma API returned no normalizable markets."
        except Exception as exc:
            markets = self._mock_markets(request)
            source = "mock_fallback"
            source_detail = f"Gamma API fallback reason: {type(exc).__name__}: {exc}"
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
        return SearchMarketsResult(
            query=request.query,
            source=source,
            source_detail=source_detail,
            markets=markets,
            count=len(markets),
        )

    def _fetch_active_events(self, request: SearchMarketsRequest) -> tuple[list[dict[str, Any]], str]:
        params: dict[str, str] = {
            "active": "true",
            "closed": "false",
            "order": "volume_24hr",
            "ascending": "false",
            "limit": str(max(1, min(request.limit, 100))),
        }
        if request.tag_id:
            params["tag_id"] = request.tag_id

        errors: list[str] = []
        for path in ["/events/keyset", "/events"]:
            url = f"{self.config.polymarket_gamma_api_url.rstrip('/')}{path}?{urllib.parse.urlencode(params)}"
            try:
                payload = self._request_json(url)
                events = self._extract_events(payload)
                if events:
                    return events, f"Fetched {len(events)} events from {path}."
                errors.append(f"{path} returned no events")
            except Exception as exc:
                errors.append(f"{path}: {type(exc).__name__}: {exc}")

        raise RuntimeError("; ".join(errors) or "Gamma API returned no events")

    @staticmethod
    def _request_json(url: str) -> Any:
        http_request = urllib.request.Request(url, headers={"User-Agent": "clink-polymarket/0.1"}, method="GET")
        with urllib.request.urlopen(http_request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))

    @staticmethod
    def _extract_events(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ["data", "events", "results"]:
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    def _normalize_events(self, events: list[dict[str, Any]], request: SearchMarketsRequest) -> list[PredictionMarket]:
        normalized: list[PredictionMarket] = []
        for event in events:
            event_id = self._first_text(event, ["id", "event_id"])
            event_title = self._first_text(event, ["title", "question", "slug"])
            event_slug = self._first_text(event, ["slug", "event_slug"])
            markets = self._extract_event_markets(event)
            if not markets and self._looks_like_market(event):
                markets = [event]
            for market in markets:
                if not isinstance(market, dict):
                    continue
                try:
                    normalized.append(self._normalize_market(market, event_id, event_title, event_slug))
                except Exception:
                    continue
                if len(normalized) >= request.limit:
                    return normalized
        return normalized

    def _extract_event_markets(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        raw_markets = event.get("markets")
        markets = self._parse_jsonish_list(raw_markets)
        return [market for market in markets if isinstance(market, dict)]

    @staticmethod
    def _looks_like_market(value: dict[str, Any]) -> bool:
        return any(key in value for key in ["conditionId", "condition_id", "outcomes", "outcomePrices", "question"])

    def _normalize_market(
        self,
        market: dict[str, Any],
        event_id: str | None,
        event_title: str | None,
        event_slug: str | None = None,
    ) -> PredictionMarket:
        outcomes = self._parse_jsonish_list(market.get("outcomes"))
        prices = [price for price in [self._safe_float(item) for item in self._parse_jsonish_list(market.get("outcomePrices"))] if price is not None]
        yes_price = prices[0] if prices else self._safe_float(
            self._first_present(market, ["bestAsk", "bestBid", "lastTradePrice", "last_trade_price"])
        )
        no_price = prices[1] if len(prices) > 1 else (round(1 - yes_price, 10) if yes_price is not None else None)
        slug = self._first_text(market, ["slug", "market_slug"])
        market_id = self._first_text(market, ["id", "market_id", "conditionId", "condition_id", "slug"]) or "unknown_market"
        url_slug = event_slug or slug
        return PredictionMarket(
            market_id=market_id,
            condition_id=self._first_text(market, ["conditionId", "condition_id"]),
            question=self._first_text(market, ["question", "title"]) or event_title or "Untitled Polymarket market",
            slug=slug,
            event_id=event_id,
            event_title=event_title,
            outcomes=[str(item) for item in outcomes],
            outcome_prices=prices,
            best_yes_price=yes_price,
            best_no_price=no_price,
            liquidity=self._safe_float(self._first_present(market, ["liquidity", "liquidityNum", "liquidity_num"])),
            volume=self._safe_float(self._first_present(market, ["volume", "volumeNum", "volume_num"])),
            volume_24hr=self._safe_float(self._first_present(market, ["volume24hr", "volume_24hr", "volume24hrNum"])),
            end_date=self._first_text(market, ["endDate", "end_date", "end_date_iso"]),
            active=self._safe_bool(market.get("active", True)),
            closed=self._safe_bool(market.get("closed", False)),
            url=f"https://polymarket.com/event/{url_slug}" if url_slug else None,
        )

    @staticmethod
    def _parse_jsonish_list(value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except json.JSONDecodeError:
                return []
        return []

    @staticmethod
    def _first_present(data: dict[str, Any], keys: list[str]) -> Any:
        for key in keys:
            if key in data and data[key] not in (None, ""):
                return data[key]
        return None

    @classmethod
    def _first_text(cls, data: dict[str, Any], keys: list[str]) -> str | None:
        value = cls._first_present(data, keys)
        if value is None:
            return None
        return str(value)

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            if isinstance(value, str):
                value = value.replace(",", "")
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _safe_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() not in {"false", "0", "no", "n", ""}
        return bool(value)

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
