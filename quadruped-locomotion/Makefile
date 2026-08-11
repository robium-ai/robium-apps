.PHONY: sync test smoke list-envs train train-full play clean

# --- Mac-side (no GPU) ------------------------------------------------------

sync:
	uv sync

# The default test run: Mac-testable config/command guards ONLY. The GPU smoke
# test is deselected here (pyproject addopts) so this never fake-passes off-pod.
test:
	uv run pytest tests/ -v

# --- Pod-side (RunPod GPU pod, Isaac Lab installed) -------------------------
# These run ON the pod. Launched from anywhere in the app; run.py sets the CWD
# to ISAACLAB_ROOT. Override ISAACLAB_ROOT / ISAACLAB_PYTHON via env if the pod
# layout differs (see config.py).

# The source of truth for the task id — RUN THIS FIRST on a fresh pod and confirm
# Isaac-Velocity-Flat-Unitree-Go2-v0 is listed before trusting config.TASK.
list-envs:
	uv run python -m go2_locomotion.run list-envs

# The pass bar. SMOKE profile: proves the loop assembles + writes a checkpoint
# (mechanics, not a walking policy). Runs the gpu-marked smoke test on the pod.
smoke:
	uv run pytest tests/test_smoke.py -v -m gpu

# SMOKE-profile training by hand (same command the smoke test drives).
train:
	uv run python -m go2_locomotion.run train

# The real ~20-40 min walking policy. Add video capture of rollouts.
train-full:
	uv run python -m go2_locomotion.run train --full --video

# Roll out the latest checkpoint and capture a walking-Go2 MP4.
play:
	uv run python -m go2_locomotion.run play --video

clean:
	rm -rf outputs .pytest_cache

# Preflight (reference-apps spec v1). Mac-side only: the GPU path is verifiable
# solely on the RunPod pod (make smoke there); this catches local setup gaps.
.PHONY: check
check:
	@ok=1; \
	command -v uv >/dev/null 2>&1 || { echo "FAIL: uv not installed (https://docs.astral.sh/uv/)"; ok=0; }; \
	command -v ssh >/dev/null 2>&1 || { echo "FAIL: ssh not available (needed for the RunPod pod)"; ok=0; }; \
	[ -f uv.lock ] || { echo "FAIL: uv.lock missing (broken checkout)"; ok=0; }; \
	if [ -d .venv ]; then echo "ok: .venv present"; else echo "note: no .venv yet — run 'make sync' first"; fi; \
	echo "note: Isaac Lab / GPU checks run on the pod (make smoke there); nothing GPU is verified here"; \
	[ $$ok -eq 1 ] && echo "CHECK PASS" || { echo "CHECK FAIL"; exit 1; }
