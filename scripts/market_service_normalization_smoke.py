import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.market_service.schemas import SearchMarketsRequest
from services.market_service.service import PolymarketMarketService


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
        SearchMarketsRequest(limit=5),
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

    print(json.dumps({"status": "ok", "count": len(result), "first_market": result[0].to_dict()}, indent=2))


if __name__ == "__main__":
    main()
