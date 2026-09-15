"""Pygame directional pad for the LEGO differential-drive robot."""

from __future__ import annotations

import os
import textwrap
from dataclasses import dataclass

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

from .gamepad import DEFAULT_DEADZONE, GamepadManager
from .protocol import mix
from .session import DriveSession

WINDOW_SIZE = (620, 660)
MIN_UI_SPEED = 10
MAX_UI_SPEED = 60
SPEED_STEP = 5

BG = (19, 24, 33)
PANEL = (31, 39, 52)
BUTTON = (55, 69, 88)
BUTTON_ACTIVE = (47, 158, 113)
STOP = (188, 61, 66)
TEXT = (237, 241, 247)
MUTED = (159, 171, 190)
READY = (52, 199, 123)
ERROR = (242, 92, 92)


def action_from_flags(
    *, up: bool, down: bool, left: bool, right: bool, stop: bool = False
) -> tuple[float, float]:
    """Translate held controls into normalized throttle and steering."""
    if stop:
        return 0.0, 0.0
    throttle = float(up) - float(down)
    steer = float(right) - float(left)
    return throttle, steer


def action_for_robot(action: tuple[float, float]) -> tuple[float, float]:
    """Apply the wheels-up calibration while preserving the UI direction labels."""
    throttle, steer = action
    return -throttle, steer


@dataclass(frozen=True)
class PadButton:
    label: str
    rect: pygame.Rect
    action: tuple[float, float]


class ControlWindow:
    def __init__(
        self,
        hub_name: str | None,
        scan_timeout: float,
        speed: int,
        gamepad_deadzone: float = DEFAULT_DEADZONE,
    ) -> None:
        pygame.init()
        pygame.display.set_caption("LEGO Powered Up Teleop")
        self.screen = pygame.display.set_mode(WINDOW_SIZE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 28)
        self.small = pygame.font.Font(None, 22)
        self.large = pygame.font.Font(None, 46)
        self.hub_name = hub_name
        self.scan_timeout = scan_timeout
        self.speed = max(MIN_UI_SPEED, min(MAX_UI_SPEED, speed))
        self.mouse_action = (0.0, 0.0)
        self.mouse_stop = False
        self.gamepad = GamepadManager(deadzone=gamepad_deadzone)
        self.session = self._start_session()

        cx = WINDOW_SIZE[0] // 2
        y = 250
        size = 104
        gap = 10
        self.buttons = [
            PadButton("FWD", pygame.Rect(cx - size // 2, y, size, size), (1.0, 0.0)),
            PadButton(
                "LEFT",
                pygame.Rect(cx - size // 2 - size - gap, y + size + gap, size, size),
                (0.0, -1.0),
            ),
            PadButton(
                "STOP",
                pygame.Rect(cx - size // 2, y + size + gap, size, size),
                (0.0, 0.0),
            ),
            PadButton(
                "RIGHT",
                pygame.Rect(cx + size // 2 + gap, y + size + gap, size, size),
                (0.0, 1.0),
            ),
            PadButton(
                "BACK",
                pygame.Rect(cx - size // 2, y + 2 * (size + gap), size, size),
                (-1.0, 0.0),
            ),
        ]
        self.minus_rect = pygame.Rect(40, 181, 48, 42)
        self.plus_rect = pygame.Rect(202, 181, 48, 42)
        self.retry_rect = pygame.Rect(430, 181, 150, 42)

    def _start_session(self) -> DriveSession:
        session = DriveSession(hub_name=self.hub_name, scan_timeout=self.scan_timeout)
        session.start()
        return session

    def _retry(self) -> None:
        state = self.session.state()
        if state.phase not in {"error", "stopped"}:
            return
        self.session.close()
        self.mouse_action = (0.0, 0.0)
        self.mouse_stop = False
        self.session = self._start_session()

    def _keyboard_action(self) -> tuple[float, float]:
        keys = pygame.key.get_pressed()
        return action_from_flags(
            up=bool(keys[pygame.K_UP] or keys[pygame.K_w]),
            down=bool(keys[pygame.K_DOWN] or keys[pygame.K_s]),
            left=bool(keys[pygame.K_LEFT] or keys[pygame.K_a]),
            right=bool(keys[pygame.K_RIGHT] or keys[pygame.K_d]),
            stop=bool(keys[pygame.K_SPACE]),
        )

    def _handle_mouse_down(self, position: tuple[int, int]) -> None:
        if self.minus_rect.collidepoint(position):
            self.speed = max(MIN_UI_SPEED, self.speed - SPEED_STEP)
            return
        if self.plus_rect.collidepoint(position):
            self.speed = min(MAX_UI_SPEED, self.speed + SPEED_STEP)
            return
        if self.retry_rect.collidepoint(position):
            self._retry()
            return
        for button in self.buttons:
            if button.rect.collidepoint(position):
                self.mouse_action = button.action
                self.mouse_stop = button.label == "STOP"
                return

    def _draw_text(
        self,
        text: str,
        position: tuple[int, int],
        *,
        colour: tuple[int, int, int] = TEXT,
        font: pygame.font.Font | None = None,
        center: bool = False,
    ) -> None:
        surface = (font or self.font).render(text, True, colour)
        rect = surface.get_rect(center=position) if center else surface.get_rect(topleft=position)
        self.screen.blit(surface, rect)

    def _draw(self, action: tuple[float, float]) -> None:
        state = self.session.state()
        self.screen.fill(BG)
        pygame.draw.rect(self.screen, PANEL, pygame.Rect(24, 20, 572, 142), border_radius=16)
        self._draw_text("LEGO Powered Up Teleop", (42, 36), font=self.large)
        status_colour = READY if state.is_ready else ERROR if state.is_error else MUTED
        self._draw_text(state.phase.upper(), (44, 88), colour=status_colour, font=self.small)
        if state.hub_name:
            self._draw_text(state.hub_name, (205, 87), colour=MUTED, font=self.small)
        for index, line in enumerate(textwrap.wrap(state.message, width=68)[:2]):
            self._draw_text(line, (44, 116 + index * 20), colour=MUTED, font=self.small)

        self._draw_text("Power", (40, 193), colour=MUTED, font=self.small)
        pygame.draw.rect(self.screen, BUTTON, self.minus_rect, border_radius=8)
        pygame.draw.rect(self.screen, BUTTON, self.plus_rect, border_radius=8)
        self._draw_text("-", self.minus_rect.center, center=True)
        self._draw_text("+", self.plus_rect.center, center=True)
        self._draw_text(f"{self.speed}%", (124, 202), center=True)

        retry_colour = BUTTON if state.phase in {"error", "stopped"} else PANEL
        pygame.draw.rect(self.screen, retry_colour, self.retry_rect, border_radius=8)
        self._draw_text("Retry connection", self.retry_rect.center, font=self.small, center=True)

        for button in self.buttons:
            active = action == button.action and action != (0.0, 0.0)
            colour = STOP if button.label == "STOP" else BUTTON_ACTIVE if active else BUTTON
            pygame.draw.rect(self.screen, colour, button.rect, border_radius=18)
            font = self.small if button.label in {"FWD", "BACK", "LEFT", "RIGHT", "STOP"} else self.large
            self._draw_text(button.label, button.rect.center, font=font, center=True)

        left, right = mix(*action_for_robot(action), self.speed)
        gamepad_colour = READY if self.gamepad.active is not None else MUTED
        self._draw_text(
            f"Gamepad: {self.gamepad.label}  |  left Y + right X, A stops",
            (WINDOW_SIZE[0] // 2, 612),
            colour=gamepad_colour,
            font=self.small,
            center=True,
        )
        self._draw_text(
            f"Left wheel {left:+d}%     Right wheel {right:+d}%",
            (WINDOW_SIZE[0] // 2, 638),
            colour=MUTED,
            font=self.small,
            center=True,
        )
        pygame.display.flip()

    def run(self) -> None:
        running = True
        try:
            while running:
                for event in pygame.event.get():
                    self.gamepad.handle_event(event)
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key in (pygame.K_q, pygame.K_ESCAPE):
                            running = False
                        elif event.key == pygame.K_r:
                            self._retry()
                        elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                            self.speed = max(MIN_UI_SPEED, self.speed - SPEED_STEP)
                        elif event.key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                            self.speed = min(MAX_UI_SPEED, self.speed + SPEED_STEP)
                    elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                        self._handle_mouse_down(event.pos)
                    elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                        self.mouse_action = (0.0, 0.0)
                        self.mouse_stop = False
                    elif event.type == pygame.WINDOWFOCUSLOST:
                        self.mouse_action = (0.0, 0.0)
                        self.mouse_stop = False
                        self.session.set_action(0.0, 0.0, self.speed)

                keyboard_action = self._keyboard_action()
                space_held = bool(pygame.key.get_pressed()[pygame.K_SPACE])
                gamepad_reading = self.gamepad.read()
                stop_held = space_held or self.mouse_stop or gamepad_reading.stop
                action = (0.0, 0.0) if stop_held else keyboard_action
                if action == (0.0, 0.0) and not stop_held:
                    action = self.mouse_action
                if action == (0.0, 0.0) and not stop_held:
                    action = (gamepad_reading.throttle, gamepad_reading.steer)
                self.session.set_action(*action_for_robot(action), self.speed)
                self._draw(action)
                self.clock.tick(30)
        finally:
            self.session.set_action(0.0, 0.0, self.speed)
            self.session.close()
            pygame.quit()


def run_ui(
    hub_name: str | None,
    scan_timeout: float,
    speed: int,
    gamepad_deadzone: float = DEFAULT_DEADZONE,
) -> None:
    ControlWindow(
        hub_name=hub_name,
        scan_timeout=scan_timeout,
        speed=speed,
        gamepad_deadzone=gamepad_deadzone,
    ).run()
