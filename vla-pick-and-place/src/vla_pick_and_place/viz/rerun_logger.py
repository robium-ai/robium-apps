"""Rerun logging — the one place that knows the archetype API and the layout.

Why Rerun and not a video rectangle: a rectangle shows what happened but
discards the joint state, the action sent, and the reward, which together are
the *explanation* of what the arm did. Rerun puts them on one scrubbable
timeline.

Archetype notes against the pinned rerun-sdk==0.34.1:

  * `rr.Scalars` (plural), taking a `Float64ArrayLike` — the singular
    `rr.Scalar` is gone, so a lone value is `rr.Scalars([x])`.
  * `rr.set_time("step", sequence=step)` — `rr.set_time_sequence` is gone too.

Every entity path is prefixed by the frame's source, so a live run and a
recording land on different branches of the tree and a viewer can never mistake
one for the other by looking at the panel titles.
"""

from __future__ import annotations

from pathlib import Path

import rerun as rr
import rerun.blueprint as rrb

from vla_pick_and_place.config import JOINT_NAMES, STREAM_JPEG_QUALITY

APP_ID = "vla_pick_and_place"


def blueprint() -> rrb.Blueprint:
    """Cameras across the top, joint state and action sent below."""
    return rrb.Blueprint(
        rrb.Vertical(
            rrb.Horizontal(
                rrb.Spatial2DView(origin="camera/overhead", name="overhead camera"),
                rrb.Spatial2DView(origin="camera/wrist", name="wrist camera"),
            ),
            rrb.Horizontal(
                rrb.TimeSeriesView(origin="state", name="joint state"),
                rrb.TimeSeriesView(origin="action", name="action sent"),
            ),
            row_shares=[3, 2],
        ),
        collapse_panels=True,
    )


def log_frame(rec: rr.RecordingStream, frame) -> None:
    """Log one `demo.session.Frame` onto an explicit recording stream.

    Images are JPEG-compressed: raw RGB at two 640x480 cameras over a few
    hundred steps is >100 MB down a browser stream, and the viewer is showing
    a demo, not doing photometry.
    """
    rec.set_time("step", sequence=int(frame.step))
    if frame.overhead is not None:
        rec.log(
            "camera/overhead",
            rr.Image(frame.overhead).compress(jpeg_quality=STREAM_JPEG_QUALITY),
        )
    if frame.wrist is not None:
        rec.log(
            "camera/wrist",
            rr.Image(frame.wrist).compress(jpeg_quality=STREAM_JPEG_QUALITY),
        )
    rec.log("source", rr.TextLog(f"{frame.source} — units: {frame.units}"))
    for name, value in zip(JOINT_NAMES, frame.state):
        rec.log(f"state/{name}", rr.Scalars([float(value)]))
    for name, value in zip(JOINT_NAMES, frame.action):
        rec.log(f"action/{name}", rr.Scalars([float(value)]))
    if frame.reward is not None:
        rec.log("reward", rr.Scalars([float(frame.reward)]))
    rec.log("success", rr.Scalars([1.0 if frame.success else 0.0]))


class RerunLogger:
    """Offline .rrd writer for the CLI paths (`run sim`, `run play`)."""

    def __init__(self, app_id: str = APP_ID, save_path: Path | None = None):
        self._rec = rr.RecordingStream(application_id=app_id)
        if save_path is not None:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            self._rec.save(str(save_path), default_blueprint=blueprint())
        self.save_path = save_path

    def log(self, frame) -> None:
        log_frame(self._rec, frame)

    def close(self) -> None:
        self._rec.flush()
