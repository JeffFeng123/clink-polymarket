import asyncio
import json
import sys
from pathlib import Path

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.config import AppConfig  # noqa: E402


def _content_to_dict(result) -> dict:
    text = getattr(result.content[0], "text", "{}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"MCP tool returned non-JSON content: {text}") from exc


async def main() -> None:
    config = AppConfig.from_env()
    async with streamablehttp_client(config.polymarket_mcp_url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            health = _content_to_dict(await session.call_tool("polymarket_adapter_health"))
            opportunities = _content_to_dict(
                await session.call_tool(
                    "score_market_opportunities",
                    arguments={
                        "goal": "Find a liquid AI or agent related prediction market with a tradable price",
                        "limit": 5,
                        "max_results": 3,
                    },
                )
            )
            flow = _content_to_dict(
                await session.call_tool(
                    "submit_agent_trade_intent",
                    arguments={
                        "user_id": "public-mcp-smoke-user",
                        "agent_id": "hermes_like_external_agent",
                        "goal": "Find a liquid AI or agent related prediction market with a tradable price",
                        "amount_usdc": "1",
                        "user_confirmed": True,
                    },
                )
            )
            portfolio = _content_to_dict(
                await session.call_tool(
                    "get_portfolio_status",
                    arguments={"user_id": "public-mcp-smoke-user"},
                )
            )
            print(
                json.dumps(
                    {
                        "health": health,
                        "opportunities": opportunities,
                        "agent_flow": flow,
                        "portfolio": portfolio,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )


if __name__ == "__main__":
    asyncio.run(main())
