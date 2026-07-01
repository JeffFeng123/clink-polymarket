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


class FakeClobAdapter:
    def __init__(self):
        self.calls = []

    def submit_limit_order(self, preview):
        self.calls.append(preview)
        return {
            "order_id": "0xfake_order",
            "tx_hash": "0xfake_tx",
            "status": "matched",
            "raw_response": {
                "orderID": "0xfake_order",
                "transactionsHashes": ["0xfake_tx"],
                "tradeIDs": ["trade_123"],
                "status": "matched",
            },
        }


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["POLYMARKET_ORDER_PREVIEW_FILE"] = str(Path(temp_dir) / "order_previews.jsonl")
        os.environ["POLYMARKET_EXECUTION_FILE"] = str(Path(temp_dir) / "executions.jsonl")
        os.environ["POLYMARKET_LIVE_MODE"] = "true"
        os.environ["POLYMARKET_MAX_ORDER_USDC"] = "1"
        os.environ["POLYMARKET_REQUIRE_USER_CONFIRMATION"] = "true"
        os.environ["POLYMARKET_PRIVATE_KEY"] = "0x" + "1" * 64
        os.environ["POLYMARKET_FUNDER_ADDRESS"] = "0x" + "2" * 40
        os.environ["POLYMARKET_SIGNATURE_TYPE"] = "3"
        os.environ["POLYMARKET_CHAIN_ID"] = "137"

        preview = OrderPreviewService().create_order_preview(
            CreateOrderPreviewRequest(
                user_id="live-smoke-user",
                agent_id="hermes_like_external_agent",
                market_id="691547",
                question="Kraken IPO by December 31, 2026?",
                amount_usdc="1",
                limit_price=0.375,
                outcome="Yes",
                side="buy",
                token_id="123456789",
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

        adapter = FakeClobAdapter()
        service = ExecutionService(clob_adapter=adapter)
        service._fetch_order_preview = lambda order_preview_id: (
            preview if order_preview_id == preview.order_preview_id else None
        )

        blocked = service.execute_approved_trade(
            ExecuteApprovedTradeRequest(order_preview_id=preview.order_preview_id, user_confirmed=False)
        )
        assert blocked.state == "blocked"
        assert blocked.submitted_to_polymarket is False
        assert len(adapter.calls) == 0

        submitted = service.execute_approved_trade(
            ExecuteApprovedTradeRequest(order_preview_id=preview.order_preview_id, user_confirmed=True, live_submission_confirmed=True)
        )
        assert submitted.state == "submitted"
        assert submitted.execution_mode == "live"
        assert submitted.submitted_to_polymarket is True
        assert submitted.order_id == "0xfake_order"
        assert submitted.tx_hash == "0xfake_tx"
        assert submitted.next_action == "monitor_order_status"
        assert len(adapter.calls) == 1

        saved = service.get_execution(submitted.execution_id)
        assert saved is not None
        assert saved.order_id == "0xfake_order"

        print(json.dumps({"status": "ok", "blocked": blocked.to_dict(), "submitted": submitted.to_dict()}, indent=2))


if __name__ == "__main__":
    main()
