from  decouple import config

from  openai import OpenAI
from  mcp import Client

from  mcp_server.server import mcp

import json
import asyncio
from datetime import date

if not config("OPENAI_API_KEY"):
    raise RuntimeError("OPENAI_API_KEY is not set in the environment variables.")

ai = OpenAI(api_key=config("OPENAI_API_KEY"))

# Describe the tool to OpenAI.
# Keep this schema synchronized with the MCP tool.
OPENAI_TOOLS = [
    {
        "type": "function",
        "name": "get_today_appointments",
        "description": (
            "Get today's real salon appointments and their count."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": False,
    }
]


def serialize_result(result):
    structured = getattr(result, "structured_content", None)

    if structured is not None:
        return json.dumps(structured, default=str)

    text_parts = [
        item.text
        for item in getattr(result, "content", [])
        if hasattr(item, "text")
    ]

    if text_parts:
        return "\n".join(text_parts)

    return json.dumps({"result": str(result)})


async def chat():
    # In-memory MCP connection; no separate MCP HTTP server needed.
    async with Client(mcp) as mcp_client:

        tools_result = await mcp_client.list_tools()

        available = getattr(tools_result, "tools", None)
        if available is None:
            raise RuntimeError("MCP client returned an unexpected tools response.")

        available_names = {tool.name for tool in available}

        if "get_appointments" not in available_names:
            raise RuntimeError("MCP appointment tool was not found.")

        print("Salon AI is ready.")
        print("Ask about today's appointments.")
        print("Type 'exit' to stop.\n")

        while True:
            question = input("You: ").strip()

            if question.lower() in {"exit", "quit"}:
                break

            if not question:
                continue

            try:
                response = ai.responses.create(
                    model="gpt-4.1-mini",
                    instructions=(
                        "You are a salon management assistant. "
                        "Use tools for real appointment data. "
                        "Never invent appointment counts. "
                        "If a tool fails, clearly say that the "
                        "appointment data could not be retrieved."
                    ),
                    input=question,
                    tools=OPENAI_TOOLS,
                )

                # OpenAI may request a tool call.
                while True:
                    calls = [
                        item
                        for item in response.output
                        if item.type == "function_call"
                    ]

                    if not calls:
                        print(f"AI: {response.output_text}\n")
                        break

                    tool_outputs = []

                    for call in calls:
                        if call.name != "get_today_appointments":
                            output = json.dumps({
                                "error": "Tool is not allowed."
                            })
                        else:
                            try:
                                arguments = json.loads(call.arguments)

                                # This tool takes no arguments.
                                if arguments:
                                    raise ValueError(
                                        "Unexpected tool arguments."
                                    )

                                result = await mcp_client.call_tool(
                                    "get_appointments",
                                    {"date": date.today().isoformat()},
                                )

                                if getattr(result, "is_error", False):
                                    raise RuntimeError(
                                        serialize_result(result)
                                    )

                                output = serialize_result(result)

                            except Exception as exc:
                                output = json.dumps({
                                    "error": str(exc)
                                })

                        tool_outputs.append({
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": output,
                        })

                    response = ai.responses.create(
                        model="gpt-4.1-mini",
                        previous_response_id=response.id,
                        input=tool_outputs,
                        tools=OPENAI_TOOLS,
                    )

            except Exception as exc:
                print(f"Error: {exc}\n")


if __name__ == "__main__":
    asyncio.run(chat())
