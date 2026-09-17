"""Persistent Gemini Robotics ER 2 voice session."""

from __future__ import annotations

import asyncio
import base64
import warnings
from collections.abc import Iterable
from typing import Any

from google import genai
from google.genai import types

from .config import (
    ANIMATION_NAMES,
    CONTINUOUS_CHUNK_SECONDS,
    CONTINUOUS_SYSTEM_INSTRUCTION,
    LEGO_DIRECTIONS,
    MAX_PITCH_DEG,
    MAX_SPEED,
    MAX_TEXT_CHARS,
    MAX_YAW_DEG,
    MIN_PITCH_DEG,
    MIN_SPEED,
    MIN_YAW_DEG,
    MODEL,
    PCM_CHUNK_BYTES,
    SAMPLE_RATE,
    SYSTEM_INSTRUCTION,
)
from .device import DeviceError, GuardedActions, StackChanDevice


def function_declarations(*, lego_enabled: bool = True) -> list[dict[str, Any]]:
    blocking = "BLOCKING"
    declarations = [
        {
            "name": "move_head",
            "description": "Move STACK-CHAN's head to a natural bounded yaw and pitch.",
            "behavior": blocking,
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "yaw": {
                        "type": "INTEGER",
                        "minimum": MIN_YAW_DEG,
                        "maximum": MAX_YAW_DEG,
                        "description": "Horizontal degrees; negative is right, positive is left.",
                    },
                    "pitch": {
                        "type": "INTEGER",
                        "minimum": MIN_PITCH_DEG,
                        "maximum": MAX_PITCH_DEG,
                        "description": "Vertical degrees; larger values look upward.",
                    },
                    "speed": {
                        "type": "INTEGER",
                        "minimum": MIN_SPEED,
                        "maximum": MAX_SPEED,
                        "description": "150 is a natural conversational gesture.",
                    },
                },
                "required": ["yaw", "pitch", "speed"],
            },
        },
        {
            "name": "show_text",
            "description": "Show a short requested message on STACK-CHAN's display.",
            "behavior": blocking,
            "parameters": {
                "type": "OBJECT",
                "properties": {"text": {"type": "STRING", "maxLength": MAX_TEXT_CHARS}},
                "required": ["text"],
            },
        },
        {
            "name": "speak",
            "description": (
                "Speak one short reply through STACK-CHAN and show it on the display. "
                "Never use this when the person asks for silence or display only."
            ),
            "behavior": blocking,
            "parameters": {
                "type": "OBJECT",
                "properties": {"message": {"type": "STRING", "maxLength": 240}},
                "required": ["message"],
            },
        },
        {
            "name": "look",
            "description": (
                "Capture one fresh image from STACK-CHAN's camera for visual questions. "
                "Use only when current surroundings must be seen; the image is returned after "
                "this call."
            ),
            "behavior": blocking,
            "parameters": {"type": "OBJECT", "properties": {}},
        },
        {
            "name": "animate",
            "description": (
                "Run one guarded expressive head animation. nod_yes is a quick vertical nod; "
                "shake_no is a quick horizontal no; privacy looks fully upward; turn_back "
                "uses continuous 360-degree yaw to face backward; look_straight returns to the "
                "neutral forward pose."
            ),
            "behavior": blocking,
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "animation": {
                        "type": "STRING",
                        "enum": list(ANIMATION_NAMES),
                    }
                },
                "required": ["animation"],
            },
        },
    ]
    if lego_enabled:
        declarations.append(
            {
                "name": "drive_lego",
                "description": (
                    "Move the separate LEGO robot in one simple direction. Every movement is "
                    "brief and automatically stops; use stop for an explicit immediate stop."
                ),
                "behavior": blocking,
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "direction": {
                            "type": "STRING",
                            "enum": list(LEGO_DIRECTIONS),
                        }
                    },
                    "required": ["direction"],
                },
            }
        )
    return declarations


def live_config(
    *, continuous: bool = False, lego_enabled: bool = True
) -> types.LiveConnectConfig:
    instruction = SYSTEM_INSTRUCTION
    if continuous:
        instruction = f"{instruction}\n\n{CONTINUOUS_SYSTEM_INSTRUCTION}"
    return types.LiveConnectConfig(
        response_modalities=["TEXT"],
        tools=[{"function_declarations": function_declarations(lego_enabled=lego_enabled)}],
        system_instruction=types.Content(parts=[types.Part(text=instruction)]),
        realtime_input_config=types.RealtimeInputConfig(
            automatic_activity_detection=types.AutomaticActivityDetection(disabled=not continuous)
        ),
        context_window_compression=types.ContextWindowCompressionConfig(
            sliding_window=types.SlidingWindow()
        ),
    )


def iter_pcm_chunks(data: bytes, chunk_bytes: int = PCM_CHUNK_BYTES) -> Iterable[bytes]:
    if chunk_bytes <= 0 or chunk_bytes % 2:
        raise ValueError("PCM chunk size must be a positive even number")
    if len(data) % 2:
        raise ValueError("signed 16-bit PCM must have an even byte length")
    for offset in range(0, len(data), chunk_bytes):
        yield data[offset : offset + chunk_bytes]


class StackChanAgent:
    def __init__(
        self,
        api_key: str,
        device: StackChanDevice,
        actions: GuardedActions,
        *,
        model: str = MODEL,
        lego_enabled: bool = True,
    ):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required")
        self.client = genai.Client(api_key=api_key)
        self.device = device
        self.actions = actions
        self.model = model
        self.lego_enabled = lego_enabled

    async def _send_audio(self, session: Any, pcm: bytes) -> None:
        await session.send_realtime_input(activity_start=types.ActivityStart())
        for chunk in iter_pcm_chunks(pcm):
            await session.send_realtime_input(
                audio=types.Blob(data=chunk, mime_type=f"audio/pcm;rate={SAMPLE_RATE}")
            )
        await session.send_realtime_input(activity_end=types.ActivityEnd())

    async def _send_text(self, session: Any, text: str) -> None:
        await session.send_client_content(
            turns=types.Content(role="user", parts=[types.Part(text=text)]),
            turn_complete=True,
        )

    async def _execute_tool_calls(
        self,
        session: Any,
        function_calls: Any,
        listening: asyncio.Event | None = None,
    ) -> set[str]:
        if listening is not None:
            listening.clear()
        responses = []
        successful_tools: set[str] = set()
        for call in function_calls:
            arguments = dict(call.args or {})
            try:
                result = await asyncio.to_thread(self.actions.execute, call.name, arguments)
                image = result.pop("_image", None)
                if result.get("status") == "succeeded":
                    successful_tools.add(call.name)
            except (DeviceError, ValueError, RuntimeError) as error:
                result = {"status": "rejected", "reason": str(error)}
                image = None
            print(f"\n[tool] {call.name}({arguments}) -> {result}")
            parts = None
            if image is not None:
                # google-genai 2.23.0 exposes FunctionResponsePart.from_bytes,
                # but its Live transport calls model_dump(mode="python") and
                # then json.dumps, leaving bytes unserialized. Construct the
                # documented base64 wire value until the SDK encodes it itself.
                encoded_image = base64.b64encode(image).decode("ascii")
                parts = [
                    types.FunctionResponsePart.model_construct(
                        inline_data=types.FunctionResponseBlob.model_construct(
                            data=encoded_image,
                            mime_type="image/jpeg",
                        )
                    )
                ]
            responses.append(
                types.FunctionResponse(
                    name=call.name,
                    response=result,
                    id=call.id,
                    parts=parts,
                )
            )
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning, module=r"pydantic\.main")
            await session.send_tool_response(function_responses=responses)
        return successful_tools

    async def _receive_turn(self, session: Any, timeout_s: float = 90) -> list[str]:
        text_parts: list[str] = []
        successful_tools: set[str] = set()

        async def receive() -> None:
            nonlocal successful_tools
            async for message in session.receive():
                if message.server_content:
                    content = message.server_content
                    if content.model_turn and content.model_turn.parts:
                        for part in content.model_turn.parts:
                            if part.text:
                                text_parts.append(part.text)
                                print(part.text, end="", flush=True)
                    if content.turn_complete:
                        print()
                        return
                if message.tool_call:
                    successful_tools.update(
                        await self._execute_tool_calls(session, message.tool_call.function_calls)
                    )

        await asyncio.wait_for(receive(), timeout=timeout_s)
        if (
            "speak" not in successful_tools
            and "show_text" not in successful_tools
            and "animate" not in successful_tools
            and "drive_lego" not in successful_tools
            and text_parts
        ):
            fallback = "".join(text_parts).strip()
            if fallback:
                await asyncio.to_thread(self.actions.execute, "speak", {"message": fallback[:240]})
        return text_parts

    async def _continuous_audio_loop(
        self,
        session: Any,
        listening: asyncio.Event,
        chunk_seconds: float = CONTINUOUS_CHUNK_SECONDS,
    ) -> None:
        while True:
            await listening.wait()
            pcm = await asyncio.to_thread(self.device.record_audio_chunk, chunk_seconds)
            if not listening.is_set():
                continue
            for chunk in iter_pcm_chunks(pcm):
                await session.send_realtime_input(
                    audio=types.Blob(data=chunk, mime_type=f"audio/pcm;rate={SAMPLE_RATE}")
                )

    async def _continuous_receive_loop(
        self,
        session: Any,
        listening: asyncio.Event,
    ) -> None:
        text_parts: list[str] = []
        successful_tools: set[str] = set()
        while True:
            received_message = False
            async for message in session.receive():
                received_message = True
                if message.server_content:
                    content = message.server_content
                    if content.model_turn and content.model_turn.parts:
                        for part in content.model_turn.parts:
                            if part.text:
                                text_parts.append(part.text)
                                print(part.text, end="", flush=True)
                    if content.turn_complete:
                        if (
                            "speak" not in successful_tools
                            and "show_text" not in successful_tools
                            and "animate" not in successful_tools
                            and "drive_lego" not in successful_tools
                            and text_parts
                        ):
                            fallback = "".join(text_parts).strip()
                            if fallback:
                                listening.clear()
                                await asyncio.to_thread(
                                    self.actions.execute, "speak", {"message": fallback[:240]}
                                )
                        text_parts.clear()
                        successful_tools.clear()
                        listening.set()
                        print("\nListening for 'Stack Chan'...", flush=True)
                if message.tool_call:
                    successful_tools.update(
                        await self._execute_tool_calls(
                            session,
                            message.tool_call.function_calls,
                            listening,
                        )
                    )
            if not received_message:
                raise RuntimeError("Gemini live session closed")

    async def _run_continuous(self, session: Any) -> None:
        listening = asyncio.Event()
        listening.set()
        await asyncio.to_thread(self.device.show_text, "Listening for\nStack Chan...")
        print("Continuously listening for 'Stack Chan'. Press Ctrl+C to stop.", flush=True)
        try:
            async with asyncio.TaskGroup() as tasks:
                tasks.create_task(self._continuous_audio_loop(session, listening))
                tasks.create_task(self._continuous_receive_loop(session, listening))
        finally:
            listening.clear()
            await asyncio.to_thread(self.device.stop_listening)

    async def run(
        self,
        *,
        listen_seconds: float = 4.0,
        text: str | None = None,
        push_to_talk: bool = False,
    ) -> None:
        continuous = text is None and not push_to_talk
        async with self.client.aio.live.connect(
            model=self.model,
            config=live_config(continuous=continuous, lego_enabled=self.lego_enabled),
        ) as session:
            if text is not None:
                await self._send_text(session, text)
                await self._receive_turn(session)
                return

            if continuous:
                await self._run_continuous(session)
                return

            print("Press Enter to talk, or type q then Enter to quit.")
            while True:
                choice = await asyncio.to_thread(input, "\nSTACK-CHAN> ")
                if choice.strip().lower() in {"q", "quit", "exit"}:
                    return
                print(f"Listening for {listen_seconds:g} seconds...", flush=True)
                await asyncio.to_thread(self.device.show_text, "Listening...")
                pcm = await asyncio.to_thread(self.device.record_audio, listen_seconds)
                print("Thinking...", flush=True)
                await asyncio.to_thread(self.device.show_text, "Thinking...")
                await self._send_audio(session, pcm)
                await self._receive_turn(session)
                print("Ready for the next turn.", flush=True)
