"""Optional Gemini Robotics ER2 text brain with guarded simulator tools."""

from __future__ import annotations

import warnings
from collections.abc import Awaitable, Callable
from typing import Any

from google import genai
from google.genai import types

from .config import ER2_MODEL

ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]

SYSTEM_INSTRUCTION = """
You control a small simulated desktop robot named Stack-chan. Be brief and friendly.
Use move_head or animate when motion helps. Use track_face only when explicitly asked
to start or stop following a face. Use speak exactly once for a normal answer. Never
claim an action happened unless its tool returned succeeded.
""".strip()


def declarations() -> list[dict[str, Any]]:
    return [
        {
            "name": "move_head",
            "description": "Move the simulated head to bounded yaw and pitch degrees.",
            "behavior": "BLOCKING",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "yaw": {"type": "NUMBER", "minimum": -40, "maximum": 40},
                    "pitch": {"type": "NUMBER", "minimum": 10, "maximum": 80},
                },
                "required": ["yaw", "pitch"],
            },
        },
        {
            "name": "animate",
            "description": "Run a short expressive head animation.",
            "behavior": "BLOCKING",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "animation": {"type": "STRING", "enum": ["nod", "shake", "showcase"]}
                },
                "required": ["animation"],
            },
        },
        {
            "name": "track_face",
            "description": "Start or stop browser-local face following.",
            "behavior": "BLOCKING",
            "parameters": {
                "type": "OBJECT",
                "properties": {"enabled": {"type": "BOOLEAN"}},
                "required": ["enabled"],
            },
        },
        {
            "name": "speak",
            "description": "Speak one short answer with local Kokoro TTS.",
            "behavior": "BLOCKING",
            "parameters": {
                "type": "OBJECT",
                "properties": {"message": {"type": "STRING", "maxLength": 240}},
                "required": ["message"],
            },
        },
    ]


class Er2Brain:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required for --brain er2")
        self.client = genai.Client(api_key=api_key)

    async def respond(self, text: str, execute: ToolExecutor) -> str:
        config = types.LiveConnectConfig(
            response_modalities=["TEXT"],
            tools=[{"function_declarations": declarations()}],
            system_instruction=types.Content(parts=[types.Part(text=SYSTEM_INSTRUCTION)]),
        )
        spoken = ""
        text_parts: list[str] = []
        async with self.client.aio.live.connect(model=ER2_MODEL, config=config) as session:
            await session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=text)]),
                turn_complete=True,
            )
            async for message in session.receive():
                if message.tool_call:
                    responses = []
                    for call in message.tool_call.function_calls:
                        arguments = dict(call.args or {})
                        result = await execute(call.name, arguments)
                        if call.name == "speak" and result.get("status") == "succeeded":
                            spoken = str(arguments.get("message", ""))
                        responses.append(
                            types.FunctionResponse(name=call.name, id=call.id, response=result)
                        )
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", UserWarning)
                        await session.send_tool_response(function_responses=responses)
                if message.server_content:
                    content = message.server_content
                    if content.model_turn and content.model_turn.parts:
                        text_parts.extend(part.text for part in content.model_turn.parts if part.text)
                    if content.turn_complete:
                        break
        return spoken or "".join(text_parts).strip()
