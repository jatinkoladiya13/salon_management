from mcp.server import MCPServer
import httpx



mcp = MCPServer(
    "Salon Management MCP"
)


@mcp.tool()
async def get_appointments(date: str):
    """
    Get appointments for a specific date.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://localhost:8000/appointments?date={date}")
        response.raise_for_status()
        return response.json()


if __name__ == "__main__":
    mcp.run(
        transport="streamable-http",
        host="localhost",
        port=8001
    )    