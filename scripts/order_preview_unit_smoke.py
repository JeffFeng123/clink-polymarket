import json
import os
import sys
import tempfile
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.order_service.schemas import CreateOrderPreviewRequest
from services.order_service.service import OrderPreviewService


def main() -> None:
    with tempfile.TemporaryDirectory() as temp_dir:
        os.environ["POLYMARKET_ORDER_PREVIEW_FILE"] = str(Path(temp_dir) / "order_previews.jsonl")
        service = OrderPreviewService()
        preview = service.create_order_preview(
            CreateOrderPreviewRequest(
                user_id="preview-smoke-user",
                agent_id="hermes_like_external_agent",
                market_id="691547",
                question="Kraken IPO by December 31, 2026?",
                amount_usdc="1",
                limit_price=0.375,
                max_slippage_bps=100,
                core_policy_decision={
                    "decision": "needs_confirmation",
                    "approved": False,
                    "required_action": "request_user_confirmation",
                    "reason_code": "LIVE_TRADE_CONFIRMATION_REQUIRED",
                },
            )
        )
        assert preview.execution_mode == "preview_only"
        assert preview.live_mode is True
        assert preview.requires_user_confirmation is True
        assert preview.state == "confirmation_required"
        assert preview.next_action == "request_user_confirmation"
        assert preview.estimated_shares == 2.6666666666666665
        assert service.get_order_preview(preview.order_preview_id) is not None
        print(json.dumps({"status": "ok", "order_preview": preview.to_dict()}, indent=2))


if __name__ == "__main__":
    main()
