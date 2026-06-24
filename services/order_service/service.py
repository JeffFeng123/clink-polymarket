import json
import os
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from services.order_service.schemas import CreateOrderPreviewRequest, OrderPreview
from shared.config import AppConfig


class OrderPreviewService:
    """Creates non-executing Polymarket order previews for user confirmation."""

    def __init__(self) -> None:
        self.config = AppConfig.from_env()
        default_file = Path(__file__).resolve().parent / "order_previews.jsonl"
        self.storage_file = Path(os.getenv("POLYMARKET_ORDER_PREVIEW_FILE", self.config.polymarket_order_preview_file or str(default_file)))

    def create_order_preview(self, request: CreateOrderPreviewRequest) -> OrderPreview:
        now = self._utc_now()
        expires_at = now + timedelta(minutes=10)
        amount = self._parse_amount(request.amount_usdc)
        price = self._parse_price(request.limit_price, "limit_price")
        if request.max_slippage_bps < 0 or request.max_slippage_bps > 10000:
            raise ValueError("max_slippage_bps must be between 0 and 10000")
        shares = amount / price
        slippage_usdc = amount * Decimal(request.max_slippage_bps) / Decimal("10000")
        worst_case_price = price * (Decimal("1") + Decimal(request.max_slippage_bps) / Decimal("10000"))
        if worst_case_price >= Decimal("1"):
            worst_case_price = Decimal("0.999999")

        state, next_action = self._derive_state(request.core_policy_decision)
        preview = OrderPreview(
            order_preview_id=f"preview_{uuid4().hex[:12]}",
            user_id=request.user_id,
            agent_id=request.agent_id,
            market_id=request.market_id,
            question=request.question,
            outcome=request.outcome,
            side=request.side,
            amount_usdc=self._format_amount(amount),
            limit_price=float(price),
            estimated_shares=float(shares),
            max_slippage_bps=request.max_slippage_bps,
            max_slippage_usdc=self._format_amount(slippage_usdc),
            worst_case_price=float(worst_case_price),
            state=state,
            next_action=next_action,
            requires_user_confirmation=request.requires_user_confirmation,
            live_mode=request.live_mode,
            authorization_id=request.authorization_id,
            core_action_id=request.core_action_id,
            core_policy_decision_id=request.core_policy_decision_id,
            core_audit_event_ids=request.core_audit_event_ids,
            core_policy_decision=request.core_policy_decision,
            metadata=request.metadata,
            created_at=self._format_time(now),
            expires_at=self._format_time(expires_at),
            event_log=[
                {
                    "event": "order_preview_created",
                    "state": state,
                    "next_action": next_action,
                    "created_at": self._format_time(now),
                }
            ],
        )
        self._save_preview(preview)
        return preview

    def get_order_preview(self, order_preview_id: str) -> OrderPreview | None:
        if not self.storage_file.exists():
            return None
        latest: OrderPreview | None = None
        with self.storage_file.open() as handle:
            for line in handle:
                if not line.strip():
                    continue
                preview = OrderPreview(**json.loads(line))
                if preview.order_preview_id == order_preview_id:
                    latest = preview
        return latest

    @staticmethod
    def _derive_state(policy_decision: dict | None) -> tuple[str, str]:
        if not isinstance(policy_decision, dict):
            return "confirmation_required", "confirm_before_live_execution"
        decision = str(policy_decision.get("decision") or "").lower()
        if decision == "blocked":
            return "blocked", str(policy_decision.get("required_action") or "resolve_policy_block")
        if decision in {"needs_confirmation", "review", "manual_review"}:
            return "confirmation_required", str(policy_decision.get("required_action") or "confirm_before_live_execution")
        if bool(policy_decision.get("approved")):
            return "approved_for_execution", "execute_approved_trade"
        return "confirmation_required", "confirm_before_live_execution"

    def _save_preview(self, preview: OrderPreview) -> None:
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_file.open("a") as handle:
            handle.write(json.dumps(preview.to_dict(), ensure_ascii=False) + "\n")

    @staticmethod
    def _parse_amount(value: str) -> Decimal:
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("amount_usdc must be a valid decimal string") from exc
        if amount <= Decimal("0"):
            raise ValueError("amount_usdc must be greater than zero")
        return amount

    @staticmethod
    def _parse_price(value: float | str, field_name: str) -> Decimal:
        try:
            price = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError(f"{field_name} must be a valid number") from exc
        if price <= Decimal("0") or price >= Decimal("1"):
            raise ValueError(f"{field_name} must be between 0 and 1")
        return price

    @staticmethod
    def _format_amount(value: Decimal) -> str:
        rendered = format(value.quantize(Decimal("0.000001")), "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        return rendered or "0"

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def _format_time(value: datetime) -> str:
        return value.isoformat() + "Z"
