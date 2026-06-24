import json
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from uuid import uuid4

from services.portfolio_service.schemas import CreatePaperPositionRequest, PaperPosition, PortfolioSnapshot
from shared.config import AppConfig


class PortfolioService:
    """Stores paper Polymarket positions for agent-facing portfolio/PnL views."""

    def __init__(self) -> None:
        self.config = AppConfig.from_env()
        default_file = Path(__file__).resolve().parent / "positions.jsonl"
        self.storage_file = Path(os.getenv("POLYMARKET_POSITION_FILE", self.config.polymarket_position_file or str(default_file)))

    def create_position(self, request: CreatePaperPositionRequest) -> PaperPosition:
        now = self._format_time(self._utc_now())
        amount = self._parse_amount(request.amount_usdc)
        entry_price = self._parse_price(request.entry_price, "entry_price")
        current_price = self._parse_price(request.current_price if request.current_price is not None else request.entry_price, "current_price")
        shares = amount / entry_price
        current_value = shares * current_price
        pnl = current_value - amount
        pnl_pct = float((pnl / amount) * Decimal("100")) if amount else 0.0
        position = PaperPosition(
            position_id=f"pos_{uuid4().hex[:12]}",
            user_id=request.user_id,
            trade_intent_id=request.trade_intent_id,
            market_id=request.market_id,
            question=request.question,
            outcome=request.outcome,
            side=request.side,
            amount_usdc=self._format_decimal(amount),
            entry_price=float(entry_price),
            shares=float(shares),
            current_price=float(current_price),
            current_value_usdc=self._format_decimal(current_value),
            unrealized_pnl_usdc=self._format_decimal(pnl),
            unrealized_pnl_pct=round(pnl_pct, 4),
            core_action_id=request.core_action_id,
            core_policy_decision_id=request.core_policy_decision_id,
            core_audit_event_ids=request.core_audit_event_ids,
            metadata=request.metadata,
            created_at=now,
            updated_at=now,
        )
        self._save_position(position)
        return position

    def get_position(self, position_id: str) -> PaperPosition | None:
        for position in self._read_positions():
            if position.position_id == position_id:
                return position
        return None

    def get_portfolio(self, user_id: str) -> PortfolioSnapshot:
        positions = [position for position in self._read_positions() if position.user_id == user_id and position.state == "open"]
        amount = sum((self._parse_amount(position.amount_usdc) for position in positions), Decimal("0"))
        current_value = sum((self._parse_amount(position.current_value_usdc) for position in positions), Decimal("0"))
        pnl = current_value - amount
        pnl_pct = float((pnl / amount) * Decimal("100")) if amount > 0 else 0.0
        return PortfolioSnapshot(
            user_id=user_id,
            positions=positions,
            open_position_count=len(positions),
            total_amount_usdc=self._format_decimal(amount),
            total_current_value_usdc=self._format_decimal(current_value),
            total_unrealized_pnl_usdc=self._format_decimal(pnl),
            total_unrealized_pnl_pct=round(pnl_pct, 4),
        )

    def _read_positions(self) -> list[PaperPosition]:
        if not self.storage_file.exists():
            return []
        positions: list[PaperPosition] = []
        with self.storage_file.open() as handle:
            for line in handle:
                if line.strip():
                    positions.append(PaperPosition(**json.loads(line)))
        return positions

    def _save_position(self, position: PaperPosition) -> None:
        self.storage_file.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_file.open("a") as handle:
            handle.write(json.dumps(position.to_dict(), ensure_ascii=False) + "\n")

    @staticmethod
    def _parse_amount(value: str) -> Decimal:
        try:
            amount = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ValueError("amount_usdc must be a valid decimal string") from exc
        if amount < Decimal("0"):
            raise ValueError("amount_usdc cannot be negative")
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
    def _format_decimal(value: Decimal) -> str:
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
