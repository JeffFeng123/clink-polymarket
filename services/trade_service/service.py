import json
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from services.trade_service.schemas import CreateTradeIntentRequest, TradeIntent
from shared.config import AppConfig


class TradeService:
    """Creates read-only/paper trade intents. It never signs or submits live orders."""

    def __init__(self) -> None:
        self.config = AppConfig.from_env()
        default_file = Path(__file__).resolve().parent / "trade_intents.jsonl"
        self.storage_file = Path(os.getenv("POLYMARKET_TRADE_INTENT_FILE", self.config.polymarket_trade_intent_file or str(default_file)))

    def create_trade_intent(self, request: CreateTradeIntentRequest) -> TradeIntent:
        now = self._utc_now()
        amount = self._parse_amount(request.amount_usdc)
        estimated_shares = None
        if request.limit_price and request.limit_price > 0:
            estimated_shares = float(amount / Decimal(str(request.limit_price)))
        intent = TradeIntent(
            trade_intent_id=f"trade_{uuid4().hex[:12]}",
            user_id=request.user_id,
            agent_id=request.agent_id,
            market_id=request.market_id,
            question=request.question,
            outcome=request.outcome,
            side=request.side,
            amount_usdc=self._format_amount(amount),
            limit_price=request.limit_price,
            estimated_shares=estimated_shares,
            max_slippage_bps=request.max_slippage_bps,
            state="preview_ready",
            rationale=request.rationale,
            core_action_id=request.core_action_id,
            core_policy_decision_id=request.core_policy_decision_id,
            metadata=request.metadata,
            created_at=self._format_time(now),
            updated_at=self._format_time(now),
            event_log=[
                {
                    "event": "trade_intent_created",
                    "state": "preview_ready",
                    "created_at": self._format_time(now),
                }
            ],
        )
        self._save_intent(intent)
        return intent

    def get_trade_intent(self, trade_intent_id: str) -> TradeIntent | None:
        if not self.storage_file.exists():
            return None
        latest: TradeIntent | None = None
        with self.storage_file.open() as handle:
            for line in handle:
                if not line.strip():
                    continue
                intent = TradeIntent(**json.loads(line))
                if intent.trade_intent_id == trade_intent_id:
                    latest = intent
        return latest

    def _save_intent(self, intent: TradeIntent) -> None:
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_file.open("a") as handle:
            handle.write(json.dumps(intent.to_dict(), ensure_ascii=False) + "\n")

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
    def _format_amount(value: Decimal) -> str:
        rendered = format(value, "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        return rendered or "0"

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def _format_time(value: datetime) -> str:
        return value.isoformat() + "Z"
