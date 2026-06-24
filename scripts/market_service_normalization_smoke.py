import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.market_service.schemas import SearchMarketsRequest
from services.market_service.service import PolymarketMarketService
from services.opportunity_service.schemas import ScoreOpportunitiesRequest
from services.opportunity_service.service import OpportunityService


def main() -> None:
    service = PolymarketMarketService()
    event_with_json_string_markets = {
        "id": "16183",
        "slug": "kraken-ipo-in-2025",
        "title": "Kraken IPO by ___ ?",
        "markets": json.dumps(
            [
                {
                    "id": "12345",
                    "conditionId": "0xabc",
                    "question": "Kraken IPO by December 31, 2025?",
                    "slug": "kraken-ipo-by-december-31-2025",
                    "outcomes": '["Yes", "No"]',
                    "outcomePrices": '["0.41", "0.59"]',
                    "liquidityNum": "12500.50",
                    "volume24hr": "800.25",
                    "endDate": "2025-12-31T00:00:00Z",
                    "active": "true",
                    "closed": "false",
                }
            ]
        ),
    }
    direct_event_market = {
        "id": "999",
        "conditionId": "0xdef",
        "slug": "direct-event-market",
        "title": "Direct event market?",
        "outcomes": ["Yes", "No"],
        "outcomePrices": [0.22, 0.78],
        "liquidity": "2500",
        "volume_24hr": "900",
        "active": True,
        "closed": False,
    }

    result = service._normalize_events(
        [event_with_json_string_markets, direct_event_market],
        limit=5,
    )

    assert len(result) == 2
    assert result[0].market_id == "12345"
    assert result[0].condition_id == "0xabc"
    assert result[0].best_yes_price == 0.41
    assert result[0].best_no_price == 0.59
    assert result[0].active is True
    assert result[0].closed is False
    assert result[0].url == "https://polymarket.com/event/kraken-ipo-in-2025"
    assert result[1].market_id == "999"
    assert result[1].best_yes_price == 0.22


    deep_events = [
        {
            "id": str(index),
            "slug": f"generic-event-{index}",
            "title": f"Generic market {index}",
            "markets": [
                {
                    "id": str(2000 + index),
                    "conditionId": f"0xgeneric{index}",
                    "question": f"Will generic event {index} happen?",
                    "slug": f"generic-market-{index}",
                    "outcomes": ["Yes", "No"],
                    "outcomePrices": [0.5, 0.5],
                }
            ],
        }
        for index in range(4)
    ]
    deep_events.append(
        {
            "id": "target-event",
            "slug": "agentic-payment-target",
            "title": "Agentic payment adoption",
            "markets": [
                {
                    "id": "target-market",
                    "conditionId": "0xtarget",
                    "question": "Will agentic payment adoption accelerate in 2026?",
                    "slug": "agentic-payment-adoption-2026",
                    "outcomes": ["Yes", "No"],
                    "outcomePrices": [0.44, 0.56],
                }
            ],
        }
    )
    service._fetch_active_events = lambda request: (deep_events, "test fetch")
    searched = service.search_markets(SearchMarketsRequest(query="agentic payment", limit=1))
    assert searched.count == 1
    assert searched.markets[0].market_id == "target-market"


    tradable_events = [
        {
            "id": "tradable-event",
            "slug": "tradable-event",
            "title": "Tradable event",
            "markets": [
                {
                    "id": "null-price",
                    "question": "Null price market?",
                    "slug": "null-price-market",
                    "outcomes": ["Yes", "No"],
                    "outcomePrices": [],
                    "liquidity": "1000",
                },
                {
                    "id": "zero-price",
                    "question": "Zero price market?",
                    "slug": "zero-price-market",
                    "outcomes": ["Yes", "No"],
                    "outcomePrices": [0, 1],
                    "liquidity": "1000",
                },
                {
                    "id": "no-liquidity",
                    "question": "No liquidity market?",
                    "slug": "no-liquidity-market",
                    "outcomes": ["Yes", "No"],
                    "outcomePrices": [0.4, 0.6],
                    "liquidity": "0",
                },
                {
                    "id": "tradable-market",
                    "question": "Tradable Kraken market?",
                    "slug": "tradable-kraken-market",
                    "outcomes": ["Yes", "No"],
                    "outcomePrices": [0.37, 0.63],
                    "liquidity": "4100",
                },
            ],
        }
    ]
    service._fetch_active_events = lambda request: (tradable_events, "tradable test fetch")
    tradable = service.search_markets(SearchMarketsRequest(query="market", limit=10, tradable_only=True))
    assert tradable.count == 1
    assert tradable.markets[0].market_id == "tradable-market"

    scores = OpportunityService().score_opportunities(
        ScoreOpportunitiesRequest(
            markets=[market.to_dict() for market in service._normalize_events(tradable_events, limit=10)],
            max_results=10,
        )
    )
    by_id = {item.market_id: item for item in scores.opportunities}
    assert by_id["tradable-market"].recommended_action in {"paper_trade", "watch"}
    assert by_id["zero-price"].recommended_action == "reject"
    assert by_id["no-liquidity"].recommended_action == "reject"

    print(
        json.dumps(
            {
                "status": "ok",
                "count": len(result),
                "first_market": result[0].to_dict(),
                "searched_market": searched.markets[0].to_dict(),
                "tradable_market": tradable.markets[0].to_dict(),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
