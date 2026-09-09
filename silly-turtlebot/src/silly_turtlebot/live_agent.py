"""Gemini Robotics ER 2 Streaming client connected to a guarded adapter."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from .config import MODEL, SYSTEM_INSTRUCTION
from .guard import GuardRejected, MissionGuard
from .tools import live_tools

PCM_CHUNK_BYTES = 3200  # 100 ms of signed 16-bit mono PCM at 16 kHz.


def iter_pcm_chunks(data: bytes, chunk_bytes: int = PCM_CHUNK_BYTES) -> Iterable[bytes]:
    if chunk_bytes <= 0 or chunk_bytes % 2:
        raise ValueError("PCM chunk size must be a positive, even byte count")
    if len(data) % 2:
        raise ValueError("16-bit PCM input must contain an even number of bytes")
    for offset in range(0, len(data), chunk_bytes):
        yield data[offset : offset + chunk_bytes]


class GeminiRoboticsLiveAgent:
    def __init__(self, api_key: str, guard: MissionGuard, model: str = MODEL):
        if not api_key:
            raise ValueError("GEMINI_API_KEY is required for live mode")
        self.client = genai.Client(api_key=api_key)
        self.guard = guard
        self.model = model

    def _config(self) -> types.LiveConnectConfig:
        return types.LiveConnectConfig(
            response_modalities=["TEXT"],
            tools=live_tools(),
            system_instruction=types.Content(
                parts=[types.Part(text=SYSTEM_INSTRUCTION)]
            ),
        )

    async def _send_input(
        self,
        session: Any,
        text: str | None,
        image_path: Path | None,
        audio_path: Path | None,
        image_bytes: bytes | None = None,
    ) -> None:
        if audio_path is not None and text:
            raise ValueError("send either --text or --audio in one live turn, not both")

        if image_path is not None and image_bytes is not None:
            raise ValueError("send a file image or robot-camera image, not both")

        image = image_bytes
        if image_path is not None:
            if image_path.suffix.lower() not in {".jpg", ".jpeg"}:
                raise ValueError("image input must be a JPEG file")
            image = image_path.read_bytes()

        if image is not None and audio_path is not None:
            await session.send_realtime_input(
                video=types.Blob(data=image, mime_type="image/jpeg")
            )
        elif image is not None:
            parts = [
                types.Part(inline_data=types.Blob(data=image, mime_type="image/jpeg"))
            ]
            if text:
                parts.append(types.Part(text=text))
            await session.send_client_content(
                turns=types.Content(role="user", parts=parts),
                turn_complete=True,
            )
        elif text:
            await session.send_client_content(
                turns=types.Content(role="user", parts=[types.Part(text=text)]),
                turn_complete=True,
            )

        if audio_path is not None:
            for chunk in iter_pcm_chunks(audio_path.read_bytes()):
                await session.send_realtime_input(
                    media=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                )
            await session.send_realtime_input(audio_stream_end=True)

    async def _receive_turn(self, session: Any, timeout_s: float) -> list[str]:
        text_parts: list[str] = []

        async def receive() -> None:
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
                elif message.tool_call:
                    responses = []
                    for call in message.tool_call.function_calls:
                        try:
                            result = await asyncio.to_thread(
                                self.guard.execute,
                                call.name,
                                dict(call.args or {}),
                            )
                        except GuardRejected as error:
                            result = {"status": "rejected", "reason": str(error)}
                        print(
                            f"\n[tool] {call.name}({dict(call.args or {})}) -> {result}"
                        )
                        responses.append(
                            types.FunctionResponse(
                                name=call.name,
                                response=result,
                                id=call.id,
                            )
                        )
                        take_frames = getattr(
                            self.guard.adapter, "consume_camera_frames", None
                        )
                        if take_frames is not None:
                            for frame in take_frames():
                                await session.send_realtime_input(
                                    video=types.Blob(
                                        data=frame,
                                        mime_type="image/jpeg",
                                    )
                                )
                    await session.send_tool_response(function_responses=responses)

        try:
            await asyncio.wait_for(receive(), timeout=timeout_s)
        except TimeoutError:
            try:
                await asyncio.to_thread(
                    self.guard.execute,
                    "stop",
                    {"reason": "Gemini turn timed out"},
                )
            except Exception as error:  # noqa: BLE001 - emergency cancellation.
                print(f"WARN failed to cancel robot after timeout: {error}")
            raise
        return text_parts

    async def run_once(
        self,
        *,
        text: str | None = None,
        image_path: Path | None = None,
        audio_path: Path | None = None,
        image_bytes: bytes | None = None,
        timeout_s: float = 240.0,
    ) -> list[str]:
        if not any((text, image_path, audio_path, image_bytes)):
            raise ValueError("live mode needs --text, --image, or --audio")
        async with self.client.aio.live.connect(
            model=self.model,
            config=self._config(),
        ) as session:
            await self._send_input(
                session,
                text,
                image_path,
                audio_path,
                image_bytes,
            )
            return await self._receive_turn(session, timeout_s)
