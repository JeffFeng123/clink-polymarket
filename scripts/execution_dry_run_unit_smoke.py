import json
import os
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.execution_service.schemas import ExecuteApprovedTradeRequest
from services.execution_service.service import ExecutionService
from services.order_service.schemas import CreateOrderPreviewRequest
from services.order_service.service import OrderPreviewService


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["POLYMARKET_ORDER_PREVIEW_FILE"] = str(Path(temp_dir) / "order_previews.jsonl")
        os.environ["POLYMARKET_EXECUTION_FILE"] = str(Path(temp_dir) / "executions.jsonl")
        os.environ["POLYMARKET_LIVE_MODE"] = "false"
        os.environ["POLYMARKET_MAX_ORDER_USDC"] = "1"
        os.environ["POLYMARKET_REQUIRE_USER_CONFIRMATION"] = "true"

        preview = OrderPreviewService().create_order_preview(
            CreateOrderPreviewRequest(
                user_id="execution-smoke-user",
                agent_id="hermes_like_external_agent",
                market_id="691547",
                question="Kraken IPO by December 31, 2026?",
                amount_usdc="1",
                limit_price=0.375,
                max_slippage_bps=100,
                core_action_id="act_preview",
                core_policy_decision_id="policy_preview",
                core_audit_event_ids=["audit_preview"],
                core_policy_decision={
                    "decision": "needs_confirmation",
                    "approved": False,
                    "required_action": "request_user_confirmation",
                    "reason_code": "LIVE_TRADE_CONFIRMATION_REQUIRED",
                },
            )
        )

        service = ExecutionService()
        blocked = service.execute_approved_trade(
            ExecuteApprovedTradeRequest(order_preview_id=preview.order_preview_id, user_confirmed=False)
        )
        assert blocked.state == "blocked"
        assert blocked.submitted_to_polymarket is False
        assert blocked.next_action == "request_user_confirmation"

        simulated = service.execute_approved_trade(
            ExecuteApprovedTradeRequest(order_preview_id=preview.order_preview_id, user_confirmed=True)
        )
        assert simulated.state == "simulated_live_execution"
        assert simulated.execution_mode == "dry_run"
        assert simulated.submitted_to_polymarket is False
        assert simulated.order_preview_id == preview.order_preview_id
        assert simulated.amount_usdc == "1"

        print(json.dumps({"status": "ok", "blocked": blocked.to_dict(), "simulated": simulated.to_dict()}, indent=2))


if __name__ == "__main__":
    main()
