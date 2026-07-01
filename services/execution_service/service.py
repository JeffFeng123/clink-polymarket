import json
import os
import urllib.error
import urllib.request
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from uuid import uuid4

from services.execution_service.schemas import ExecuteApprovedTradeRequest, LiveReadiness, TradeExecution
from services.order_service.schemas import OrderPreview
from shared.config import AppConfig


class PolymarketClobAdapter:
    """Small py-clob-client wrapper kept isolated for live execution and test fakes."""

    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def submit_limit_order(self, preview: OrderPreview) -> dict[str, Any]:
        if not preview.token_id:
            raise ValueError("Polymarket CLOB token_id is required for live order submission")
        if not self.config.polymarket_private_key:
            raise ValueError("POLYMARKET_PRIVATE_KEY is required")
        if not self.config.polymarket_funder_address:
            raise ValueError("POLYMARKET_FUNDER_ADDRESS is required")

        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import OrderArgs, OrderType
        from py_clob_client.order_builder.constants import BUY, SELL

        client = ClobClient(
            self.config.polymarket_clob_host,
            key=self.config.polymarket_private_key,
            chain_id=self.config.polymarket_chain_id,
            signature_type=int(self.config.polymarket_signature_type),
            funder=self.config.polymarket_funder_address,
        )
        api_creds = self._api_creds(client)
        client.set_api_creds(api_creds)

        side = BUY if (preview.side or "buy").lower() == "buy" else SELL
        order_args = OrderArgs(
            price=float(preview.limit_price),
            size=float(preview.estimated_shares),
            side=side,
            token_id=str(preview.token_id),
        )
        signed_order = client.create_order(order_args)
        response = client.post_order(signed_order, OrderType.GTC)
        return self._normalize_submit_response(response)

    def _api_creds(self, client: Any) -> Any:
        if all([self.config.polymarket_api_key, self.config.polymarket_api_secret, self.config.polymarket_api_passphrase]):
            from py_clob_client.clob_types import ApiCreds

            return ApiCreds(
                api_key=self.config.polymarket_api_key,
                api_secret=self.config.polymarket_api_secret,
                api_passphrase=self.config.polymarket_api_passphrase,
            )
        return client.create_or_derive_api_creds()

    @staticmethod
    def _normalize_submit_response(response: Any) -> dict[str, Any]:
        if hasattr(response, "model_dump"):
            payload = response.model_dump()
        elif hasattr(response, "dict"):
            payload = response.dict()
        elif isinstance(response, dict):
            payload = response
        else:
            payload = {"raw": str(response)}

        hashes = payload.get("transactionsHashes") or payload.get("transactionHashes") or payload.get("tx_hashes") or []
        if isinstance(hashes, str):
            hashes = [hashes]
        order_id = payload.get("orderID") or payload.get("order_id") or payload.get("id")
        tx_hash = payload.get("txHash") or payload.get("tx_hash") or (hashes[0] if hashes else None)
        return {
            "order_id": str(order_id) if order_id else None,
            "tx_hash": str(tx_hash) if tx_hash else None,
            "status": payload.get("status") or payload.get("state") or "submitted",
            "raw_response": payload,
        }


class ExecutionService:
    """Executes approved Polymarket order previews with explicit live-submission gates."""

    def __init__(self, clob_adapter: Any | None = None) -> None:
        self.config = AppConfig.from_env()
        default_file = Path(__file__).resolve().parent / "executions.jsonl"
        self.storage_file = Path(os.getenv("POLYMARKET_EXECUTION_FILE", self.config.polymarket_execution_file or str(default_file)))
        self.clob_adapter = clob_adapter

    def check_live_readiness(self) -> LiveReadiness:
        missing: list[str] = []
        warnings: list[str] = []
        configured = {
            "POLYMARKET_CLOB_HOST": self.config.polymarket_clob_host,
            "POLYMARKET_PRIVATE_KEY": bool(self.config.polymarket_private_key),
            "POLYMARKET_FUNDER_ADDRESS": bool(self.config.polymarket_funder_address),
            "POLYMARKET_API_CREDS": all([
                self.config.polymarket_api_key,
                self.config.polymarket_api_secret,
                self.config.polymarket_api_passphrase,
            ]),
            "POLYMARKET_SIGNATURE_TYPE": self.config.polymarket_signature_type,
            "POLYMARKET_CHAIN_ID": self.config.polymarket_chain_id,
            "POLYMARKET_REQUIRE_USER_CONFIRMATION": self.config.polymarket_require_user_confirmation,
            "POLYMARKET_LIVE_MODE": self.config.polymarket_live_mode,
        }

        if not self.config.polymarket_live_mode:
            missing.append("POLYMARKET_LIVE_MODE=true")
        if not self.config.polymarket_clob_host:
            missing.append("POLYMARKET_CLOB_HOST")
        if not self.config.polymarket_private_key:
            missing.append("POLYMARKET_PRIVATE_KEY")
        if not self.config.polymarket_funder_address:
            missing.append("POLYMARKET_FUNDER_ADDRESS")
        if self.config.polymarket_signature_type != "3":
            warnings.append("POLYMARKET_SIGNATURE_TYPE should usually be 3 for Polymarket browser/deposit-wallet flow")
        if self.config.polymarket_chain_id != 137:
            missing.append("POLYMARKET_CHAIN_ID=137")
        if not self.config.polymarket_require_user_confirmation:
            missing.append("POLYMARKET_REQUIRE_USER_CONFIRMATION=true")
        supplied_api_creds = [self.config.polymarket_api_key, self.config.polymarket_api_secret, self.config.polymarket_api_passphrase]
        if any(supplied_api_creds) and not all(supplied_api_creds):
            missing.append("POLYMARKET_API_KEY/API_SECRET/API_PASSPHRASE must be provided together")
        try:
            max_order = self._parse_amount(self.config.polymarket_max_order_usdc)
            if max_order <= Decimal("0"):
                missing.append("POLYMARKET_MAX_ORDER_USDC must be greater than 0")
            elif max_order > Decimal("10"):
                warnings.append("POLYMARKET_MAX_ORDER_USDC is above 10 USDC; keep demo limits small")
        except ValueError:
            missing.append("POLYMARKET_MAX_ORDER_USDC must be a valid decimal string")

        try:
            import py_clob_client  # noqa: F401
        except Exception:
            missing.append("py-clob-client package")

        live_ready = not missing
        return LiveReadiness(
            live_ready=live_ready,
            live_mode_enabled=self.config.polymarket_live_mode,
            missing=missing,
            warnings=warnings,
            configured=configured,
            max_order_usdc=self.config.polymarket_max_order_usdc,
            next_action="execute_approved_trade" if live_ready else "configure_live_execution",
        )

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

        blocked_reason, next_action = self._blocking_reason(preview, request, now)
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

        token_id = self._resolve_token_id(preview)
        if not token_id:
            return self._build_execution(
                request=request,
                preview=preview,
                now=now,
                state="blocked",
                execution_mode="blocked",
                submitted=False,
                reason="Polymarket CLOB token_id is missing from order preview",
                next_action="recreate_order_preview_with_token_id",
            )
        preview.token_id = token_id

        try:
            result = (self.clob_adapter or PolymarketClobAdapter(self.config)).submit_limit_order(preview)
        except Exception as exc:
            return self._build_execution(
                request=request,
                preview=preview,
                now=now,
                state="failed",
                execution_mode="live",
                submitted=False,
                reason=f"Polymarket CLOB submission failed: {type(exc).__name__}: {exc}",
                next_action="inspect_execution_error",
            )

        return self._build_execution(
            request=request,
            preview=preview,
            now=now,
            state="submitted",
            execution_mode="live",
            submitted=True,
            reason=f"Polymarket order submitted with status {result.get('status') or 'submitted'}",
            next_action="monitor_order_status",
            order_id=result.get("order_id"),
            tx_hash=result.get("tx_hash"),
            extra_metadata={"polymarket_submit_response": result.get("raw_response"), "polymarket_status": result.get("status")},
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

    def _blocking_reason(self, preview: OrderPreview, request: ExecuteApprovedTradeRequest, now: datetime) -> tuple[str | None, str | None]:
        if self.config.polymarket_require_user_confirmation and not request.user_confirmed:
            return "user confirmation is required before execution", "request_user_confirmation"
        if self.config.polymarket_live_mode and not request.live_submission_confirmed:
            return "live submission requires explicit live_submission_confirmed=true", "confirm_live_submission_intent"
        if preview.state == "blocked":
            return "order preview is blocked by policy", "resolve_policy_block"
        if self._is_expired(preview.expires_at, now):
            return "order preview is expired", "create_fresh_order_preview"
        if (preview.side or "").lower() not in {"buy", "sell"}:
            return "side must be buy or sell", "create_valid_order_preview"
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

    def _resolve_token_id(self, preview: OrderPreview) -> str | None:
        if preview.token_id:
            return str(preview.token_id)
        tokens = preview.clob_token_ids or []
        if not tokens:
            metadata_tokens = preview.metadata.get("clob_token_ids") if isinstance(preview.metadata, dict) else None
            if isinstance(metadata_tokens, list):
                tokens = [str(item) for item in metadata_tokens]
        if not tokens:
            return None
        outcomes = [str(item).lower() for item in (preview.metadata.get("outcomes", []) if isinstance(preview.metadata, dict) else [])]
        outcome = (preview.outcome or "Yes").lower()
        if outcomes and outcome in outcomes:
            index = outcomes.index(outcome)
            if index < len(tokens):
                return str(tokens[index])
        if outcome == "no" and len(tokens) > 1:
            return str(tokens[1])
        return str(tokens[0])

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
        order_id: str | None = None,
        tx_hash: str | None = None,
        extra_metadata: dict | None = None,
    ) -> TradeExecution:
        metadata = dict(request.metadata or {})
        if extra_metadata:
            metadata.update(extra_metadata)
        execution = TradeExecution(
            execution_id=f"exec_{uuid4().hex[:12]}",
            order_preview_id=request.order_preview_id,
            user_id=preview.user_id if preview else None,
            agent_id=preview.agent_id if preview else None,
            market_id=preview.market_id if preview else None,
            question=preview.question if preview else None,
            outcome=preview.outcome if preview else None,
            side=preview.side if preview else None,
            token_id=preview.token_id if preview else None,
            amount_usdc=preview.amount_usdc if preview else None,
            limit_price=preview.limit_price if preview else None,
            estimated_shares=preview.estimated_shares if preview else None,
            state=state,
            execution_mode=execution_mode,
            submitted_to_polymarket=submitted,
            live_mode_enabled=self.config.polymarket_live_mode,
            order_id=order_id,
            tx_hash=tx_hash,
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
                    "order_id": order_id,
                    "tx_hash": tx_hash,
                    "created_at": self._format_time(now),
                }
            ],
            metadata=metadata,
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
    def _is_expired(expires_at: str, now: datetime) -> bool:
        try:
            normalized = expires_at.replace("Z", "+00:00")
            expires = datetime.fromisoformat(normalized)
            if expires.tzinfo is not None:
                expires = expires.replace(tzinfo=None)
            return expires <= now
        except Exception:
            return True

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def _format_time(value: datetime) -> str:
        return value.isoformat() + "Z"
