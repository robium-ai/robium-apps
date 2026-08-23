from __future__ import annotations

import rerun as rr
import rerun.blueprint as rrb


def blueprint() -> rrb.Blueprint:
    return rrb.Blueprint(
        rrb.Horizontal(
            rrb.Spatial2DView(origin="sim", name="top camera"),
            rrb.Vertical(
                rrb.TimeSeriesView(origin="reward", name="reward stage"),
                rrb.TimeSeriesView(origin="action", name="14D action"),
                rrb.TimeSeriesView(origin="state", name="14D joint state"),
            ),
            column_shares=[3, 2],
        ),
        collapse_panels=True,
    )


def log_event(recording: rr.RecordingStream, event) -> None:
    recording.set_time("step", sequence=event.step)
    recording.log("sim", rr.Image(event.frame).compress(jpeg_quality=88))
    recording.log("reward/stage", rr.Scalars([float(event.reward)]))
    recording.log("policy/call", rr.Scalars([float(event.policy_call)]))
    recording.log("policy/chunk_index", rr.Scalars([float(event.chunk_index)]))
    recording.log("policy/inference_ms", rr.Scalars([event.inference_s * 1000.0]))
    for index, value in enumerate(event.state):
        recording.log(f"state/joint_{index:02d}", rr.Scalars([float(value)]))
    if event.action is not None:
        for index, value in enumerate(event.action):
            recording.log(f"action/joint_{index:02d}", rr.Scalars([float(value)]))
