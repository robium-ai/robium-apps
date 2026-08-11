"""The pass bar — a REMOTE-GPU smoke test (new pattern for this repo).

Unlike every other app here, this smoke test cannot run on the Mac: it needs a
real GPU with Isaac Sim + Isaac Lab installed (see docs/architecture-brief.md §5).
It is marked `gpu` and is DESELECTED by default (see pyproject `addopts`), so a
`make test` on the Mac runs only the config guards, never a fake-passing smoke.

WHAT IT PROVES (mechanics, not policy quality): the SMOKE-profile Go2 train
completes with exit code 0 and writes a checkpoint. A run this small will NOT
walk — that is the correct result, same as vla-trial's pipe-test.

STATUS: skeleton. The Phase-2 decision (brief §6.2) is the seam — whether this
executes on the pod directly (pytest run over SSH on the pod) or the Mac wraps it
over SSH. Until Phase 0 stands up a pod, this asserts nothing real; it exists so
the pass-bar shape is committed with the app. The `pytest.skip` below is a
LOAD-BEARING guard, not a stub to delete: it must fail loudly (never silently
pass) when there is no GPU.
"""

import shutil

import pytest

from go2_locomotion import config


def _isaac_lab_available() -> bool:
    """True only on a pod with the IsaacLab tree + a launchable python."""
    return (config.ISAACLAB_ROOT / config.TRAIN_SCRIPT).exists() and (
        shutil.which(config.PYTHON) is not None
    )


@pytest.mark.gpu
def test_smoke_train_writes_checkpoint(tmp_path):
    if not _isaac_lab_available():
        pytest.skip(
            "No Isaac Lab install found at ISAACLAB_ROOT=%s — this smoke test only "
            "runs on the RunPod GPU pod (Isaac Lab has no macOS path). Not a pass."
            % config.ISAACLAB_ROOT
        )
    # TODO(Phase 2): run config.train_cmd(full=False) on the pod, assert exit 0
    # and that a fresh checkpoint appeared under config.LOG_ROOT / config.TASK.
    # Wire this once a pod exists and the smoke seam (brief §6.2) is chosen.
    pytest.fail("Phase-2 TODO: remote-GPU smoke not wired yet (see docstring).")
