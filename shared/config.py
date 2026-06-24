import os
from dataclasses import asdict, dataclass


@dataclass
class AppConfig:
    polymarket_gamma_api_url: str = "https://gamma-api.polymarket.com"
    polymarket_market_service_host: str = "127.0.0.1"
    polymarket_market_service_port: int = 8020
    polymarket_trade_service_host: str = "127.0.0.1"
    polymarket_trade_service_port: int = 8021
    polymarket_opportunity_service_host: str = "127.0.0.1"
    polymarket_opportunity_service_port: int = 8022
    polymarket_portfolio_service_host: str = "127.0.0.1"
    polymarket_portfolio_service_port: int = 8023
    polymarket_order_service_host: str = "127.0.0.1"
    polymarket_order_service_port: int = 8024
    polymarket_mcp_host: str = "127.0.0.1"
    polymarket_mcp_port: int = 9020
    polymarket_trade_intent_file: str = "services/trade_service/trade_intents.jsonl"
    polymarket_position_file: str = "services/portfolio_service/positions.jsonl"
    polymarket_order_preview_file: str = "services/order_service/order_previews.jsonl"
    clink_core_action_mcp_url: str = "http://127.0.0.1:9016/mcp/"
    clink_core_policy_mcp_url: str = "http://127.0.0.1:9015/mcp/"
    clink_core_audit_mcp_url: str = "http://127.0.0.1:9017/mcp/"
    clink_core_action_service_url: str = "http://127.0.0.1:8016"
    clink_core_policy_service_url: str = "http://127.0.0.1:8015"
    clink_core_audit_service_url: str = "http://127.0.0.1:8017"

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            polymarket_gamma_api_url=os.getenv("POLYMARKET_GAMMA_API_URL", "https://gamma-api.polymarket.com"),
            polymarket_market_service_host=os.getenv("POLYMARKET_MARKET_SERVICE_HOST", "127.0.0.1"),
            polymarket_market_service_port=int(os.getenv("POLYMARKET_MARKET_SERVICE_PORT", "8020")),
            polymarket_trade_service_host=os.getenv("POLYMARKET_TRADE_SERVICE_HOST", "127.0.0.1"),
            polymarket_trade_service_port=int(os.getenv("POLYMARKET_TRADE_SERVICE_PORT", "8021")),
            polymarket_opportunity_service_host=os.getenv("POLYMARKET_OPPORTUNITY_SERVICE_HOST", "127.0.0.1"),
            polymarket_opportunity_service_port=int(os.getenv("POLYMARKET_OPPORTUNITY_SERVICE_PORT", "8022")),
            polymarket_portfolio_service_host=os.getenv("POLYMARKET_PORTFOLIO_SERVICE_HOST", "127.0.0.1"),
            polymarket_portfolio_service_port=int(os.getenv("POLYMARKET_PORTFOLIO_SERVICE_PORT", "8023")),
            polymarket_order_service_host=os.getenv("POLYMARKET_ORDER_SERVICE_HOST", "127.0.0.1"),
            polymarket_order_service_port=int(os.getenv("POLYMARKET_ORDER_SERVICE_PORT", "8024")),
            polymarket_mcp_host=os.getenv("POLYMARKET_MCP_HOST", "127.0.0.1"),
            polymarket_mcp_port=int(os.getenv("POLYMARKET_MCP_PORT", "9020")),
            polymarket_trade_intent_file=os.getenv(
                "POLYMARKET_TRADE_INTENT_FILE",
                "services/trade_service/trade_intents.jsonl",
            ),
            polymarket_position_file=os.getenv(
                "POLYMARKET_POSITION_FILE",
                "services/portfolio_service/positions.jsonl",
            ),
            polymarket_order_preview_file=os.getenv(
                "POLYMARKET_ORDER_PREVIEW_FILE",
                "services/order_service/order_previews.jsonl",
            ),
            clink_core_action_mcp_url=os.getenv("CLINK_CORE_ACTION_MCP_URL", "http://127.0.0.1:9016/mcp/"),
            clink_core_policy_mcp_url=os.getenv("CLINK_CORE_POLICY_MCP_URL", "http://127.0.0.1:9015/mcp/"),
            clink_core_audit_mcp_url=os.getenv("CLINK_CORE_AUDIT_MCP_URL", "http://127.0.0.1:9017/mcp/"),
            clink_core_action_service_url=os.getenv("CLINK_CORE_ACTION_SERVICE_URL", "http://127.0.0.1:8016"),
            clink_core_policy_service_url=os.getenv("CLINK_CORE_POLICY_SERVICE_URL", "http://127.0.0.1:8015"),
            clink_core_audit_service_url=os.getenv("CLINK_CORE_AUDIT_SERVICE_URL", "http://127.0.0.1:8017"),
        )

    def describe(self) -> dict:
        return asdict(self)

    @property
    def market_service_url(self) -> str:
        return f"http://{self.polymarket_market_service_host}:{self.polymarket_market_service_port}"

    @property
    def trade_service_url(self) -> str:
        return f"http://{self.polymarket_trade_service_host}:{self.polymarket_trade_service_port}"

    @property
    def opportunity_service_url(self) -> str:
        return f"http://{self.polymarket_opportunity_service_host}:{self.polymarket_opportunity_service_port}"

    @property
    def portfolio_service_url(self) -> str:
        return f"http://{self.polymarket_portfolio_service_host}:{self.polymarket_portfolio_service_port}"

    @property
    def order_service_url(self) -> str:
        return f"http://{self.polymarket_order_service_host}:{self.polymarket_order_service_port}"

    @property
    def polymarket_mcp_url(self) -> str:
        return f"http://{self.polymarket_mcp_host}:{self.polymarket_mcp_port}/mcp/"
