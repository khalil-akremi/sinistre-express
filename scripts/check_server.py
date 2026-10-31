"""Connect to the MCP server like the Cominty agent does, and list its tools.

Usage:  uv run python scripts/check_server.py [URL]
Default URL: http://localhost:8000/mcp
"""

import asyncio
import sys

from mcp.client.client import Client

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000/mcp"


async def main() -> None:
    async with Client(URL) as client:
        tools = (await client.list_tools()).tools
        print(f"Connected to {URL}")
        print(f"{len(tools)} tools on the menu:")
        for tool in tools:
            print(f"  - {tool.name}")
        result = await client.call_tool("get_policy", {"policy_id": "VER-1002", "claim_ref": "CHECK"})
        print("\nTest call get_policy('VER-1002'):")
        print(result.content[0].text)


asyncio.run(main())
