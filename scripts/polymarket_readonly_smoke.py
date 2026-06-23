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
    return json.loads(text)


async def main() -> None:
    config = AppConfig.from_env()
    async with streamablehttp_client(config.polymarket_mcp_url) as (read_stream, write_stream, _):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            health = _content_to_dict(await session.call_tool("polymarket_adapter_health"))
            markets = _content_to_dict(
                await session.call_tool(
                    "search_prediction_markets",
                    arguments={"query": None, "limit": 3},
                )
            )
            selected = markets["markets"][0]
            intent = _content_to_dict(
                await session.call_tool(
                    "create_trade_intent",
                    arguments={
                        "user_id": "polymarket-smoke-user",
                        "market_id": selected["market_id"],
                        "question": selected["question"],
                        "outcome": selected["outcomes"][0] if selected["outcomes"] else "Yes",
                        "side": "buy",
                        "amount_usdc": "1",
                        "limit_price": selected.get("best_yes_price"),
                        "rationale": "Read-only smoke test paper trade intent; no live order submitted.",
                        "user_confirmed": True,
                    },
                )
            )
            print(json.dumps({"health": health, "markets": markets, "trade_intent": intent}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
