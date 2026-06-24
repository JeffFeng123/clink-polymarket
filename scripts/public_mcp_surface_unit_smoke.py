import json
import os
import tempfile
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.opportunity_service.schemas import ScoreOpportunitiesRequest
from services.opportunity_service.service import OpportunityService
from services.portfolio_service.schemas import CreatePaperPositionRequest
from services.portfolio_service.service import PortfolioService


def main() -> None:
    markets = [
        {
            "market_id": "m1",
            "question": "Will agent trading become important in 2026?",
            "outcomes": ["Yes", "No"],
            "best_yes_price": 0.42,
            "best_no_price": 0.58,
            "liquidity": 25000,
            "volume_24hr": 8000,
            "url": "https://polymarket.com/event/m1",
        },
        {
            "market_id": "m2",
            "question": "Low liquidity market",
            "outcomes": ["Yes", "No"],
            "best_yes_price": 0.97,
            "liquidity": 50,
            "volume_24hr": 1,
        },
    ]
    opportunities = OpportunityService().score_opportunities(
        ScoreOpportunitiesRequest(markets=markets, goal="find agent trading opportunity", max_results=2)
    )
    assert opportunities.count == 2
    assert opportunities.opportunities[0].market_id == "m1"
    assert opportunities.opportunities[0].recommended_action == "paper_trade"

    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["POLYMARKET_POSITION_FILE"] = str(Path(temp_dir) / "positions.jsonl")
        portfolio = PortfolioService()
        position = portfolio.create_position(
            CreatePaperPositionRequest(
                user_id="user-1",
                trade_intent_id="trade_1",
                market_id="m1",
                question="Will agent trading become important in 2026?",
                outcome="Yes",
                amount_usdc="10",
                entry_price=0.5,
                current_price=0.55,
                core_action_id="act_1",
                core_policy_decision_id="policy_1",
            )
        )
        assert position.shares == 20.0
        assert position.current_value_usdc == "11"
        snapshot = portfolio.get_portfolio("user-1")
        assert snapshot.open_position_count == 1
        assert snapshot.total_amount_usdc == "10"
        assert snapshot.total_current_value_usdc == "11"
        assert snapshot.total_unrealized_pnl_usdc == "1"

    print(json.dumps({"status": "ok", "top_opportunity": opportunities.opportunities[0].model_dump()}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
