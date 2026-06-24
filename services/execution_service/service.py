import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from services.execution_service.schemas import ExecuteApprovedTradeRequest, TradeExecution
from services.order_service.schemas import OrderPreview
from shared.config import AppConfig


class ExecutionService:
    """Executes approved previews in dry-run mode until live execution is explicitly enabled."""

    def __init__(self) -> None:
        self.config = AppConfig.from_env()
        default_file = Path(__file__).resolve().parent / "executions.jsonl"
        self.storage_file = Path(os.getenv("POLYMARKET_EXECUTION_FILE", self.config.polymarket_execution_file or str(default_file)))

    def execute_approved_trade(self, request: ExecuteApprovedTradeRequest) -> TradeExecution:
        now = self._utc_now()
        preview = self._fetch_order_preview(request.order_preview_id)
        if preview is None:
            return self._build_execution(
                request=request,
                preview=None,
                now=now,
                state="blocked",
                execution_mode="blocked",
                submitted=False,
                reason="order preview not found",
                next_action="create_order_preview",
            )

        blocked_reason, next_action = self._blocking_reason(preview, request.user_confirmed)
        if blocked_reason:
            return self._build_execution(
                request=request,
                preview=preview,
                now=now,
                state="blocked",
                execution_mode="blocked",
                submitted=False,
                reason=blocked_reason,
                next_action=next_action,
            )

        if not self.config.polymarket_live_mode:
            return self._build_execution(
                request=request,
                preview=preview,
                now=now,
                state="simulated_live_execution",
                execution_mode="dry_run",
                submitted=False,
                reason="POLYMARKET_LIVE_MODE is false; no live order was submitted",
                next_action="enable_live_mode_for_real_execution",
            )

        return self._build_execution(
            request=request,
            preview=preview,
            now=now,
            state="blocked",
            execution_mode="live_not_implemented",
            submitted=False,
            reason="live Polymarket execution is not implemented in this adapter version",
            next_action="implement_clob_execution_adapter",
        )

    def get_execution(self, execution_id: str) -> TradeExecution | None:
        if not self.storage_file.exists():
            return None
        latest: TradeExecution | None = None
        with self.storage_file.open() as handle:
            for line in handle:
                if not line.strip():
                    continue
                execution = TradeExecution(**json.loads(line))
                if execution.execution_id == execution_id:
                    latest = execution
        return latest

    def _blocking_reason(self, preview: OrderPreview, user_confirmed: bool) -> tuple[str | None, str | None]:
        if self.config.polymarket_require_user_confirmation and not user_confirmed:
            return "user confirmation is required before execution", "request_user_confirmation"
        if preview.state == "blocked":
            return "order preview is blocked by policy", "resolve_policy_block"
        if self._parse_amount(preview.amount_usdc) > Decimal(str(self.config.polymarket_max_order_usdc)):
            return (
                f"amount_usdc exceeds POLYMARKET_MAX_ORDER_USDC={self.config.polymarket_max_order_usdc}",
                "reduce_order_amount",
            )
        policy = preview.core_policy_decision or {}
        decision = str(policy.get("decision") or "").lower()
        if decision == "blocked":
            return "core policy decision is blocked", str(policy.get("required_action") or "resolve_policy_block")
        return None, None

    def _fetch_order_preview(self, order_preview_id: str) -> OrderPreview | None:
        url = f"{self.config.order_service_url}/order-previews/{order_preview_id}"
        request = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return OrderPreview(**json.loads(response.read().decode("utf-8")))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            raise

    def _build_execution(
        self,
        request: ExecuteApprovedTradeRequest,
        preview: OrderPreview | None,
        now: datetime,
        state: str,
        execution_mode: str,
        submitted: bool,
        reason: str,
        next_action: str,
    ) -> TradeExecution:
        execution = TradeExecution(
            execution_id=f"exec_{uuid4().hex[:12]}",
            order_preview_id=request.order_preview_id,
            user_id=preview.user_id if preview else None,
            agent_id=preview.agent_id if preview else None,
            market_id=preview.market_id if preview else None,
            question=preview.question if preview else None,
            outcome=preview.outcome if preview else None,
            side=preview.side if preview else None,
            amount_usdc=preview.amount_usdc if preview else None,
            limit_price=preview.limit_price if preview else None,
            estimated_shares=preview.estimated_shares if preview else None,
            state=state,
            execution_mode=execution_mode,
            submitted_to_polymarket=submitted,
            live_mode_enabled=self.config.polymarket_live_mode,
            reason=reason,
            next_action=next_action,
            core_action_id=preview.core_action_id if preview else None,
            core_policy_decision_id=preview.core_policy_decision_id if preview else None,
            core_audit_event_ids=preview.core_audit_event_ids if preview else [],
            created_at=self._format_time(now),
            event_log=[
                {
                    "event": "trade_execution_evaluated",
                    "state": state,
                    "execution_mode": execution_mode,
                    "submitted_to_polymarket": submitted,
                    "reason": reason,
                    "created_at": self._format_time(now),
                }
            ],
            metadata=request.metadata,
        )
        self._save_execution(execution)
        return execution

    def _save_execution(self, execution: TradeExecution) -> None:
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_file.open("a") as handle:
            handle.write(json.dumps(execution.to_dict(), ensure_ascii=False) + "\n")

    @staticmethod
    def _parse_amount(value: str) -> Decimal:
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("amount_usdc must be a valid decimal string") from exc

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def _format_time(value: datetime) -> str:
        return value.isoformat() + "Z"
