.PHONY: sync test doctor smoke list-envs train train-full play live-patch live-image evidence clean

# --- Mac-side (no GPU) ------------------------------------------------------

sync:
	uv sync

# The default test run: Mac-testable config/command guards ONLY. The GPU smoke
# test is deselected here (pyproject addopts) so this never fake-passes off-pod.
test:
	uv run pytest tests/ -v

# --- GPU-host side (Isaac Lab installed) ------------------------------------
# run.py sets the working directory to ISAACLAB_ROOT. Override that path when
# the selected environment uses a different layout.

# Inspect the task IDs exposed by the selected installation.
list-envs:
	uv run python -m go2_locomotion.run list-envs

doctor:
	uv run python -m go2_locomotion.run doctor

# The pass bar. SMOKE profile: proves the loop assembles + writes a checkpoint
# (mechanics, not a walking policy). Runs the gpu-marked smoke test on the pod.
smoke:
	uv run pytest tests/test_smoke.py -v -m gpu

# SMOKE-profile training by hand (same command the smoke test drives).
train:
	uv run python -m go2_locomotion.run train --profile smoke

# Full training. The installed task chooses the scale unless GO2_* overrides it.
train-full:
	uv run python -m go2_locomotion.run train --profile full

# Roll out the latest checkpoint and capture a walking-Go2 MP4.
play:
	uv run python -m go2_locomotion.run play --video

live-patch:
	uv run python scripts/live_demo_patch.py

# IMAGE is the registry destination. The matched NVIDIA base remains
# overrideable through --build-arg ISAAC_LAB_IMAGE=... when the stack changes.
live-image:
	@test -n "$(IMAGE)" || { echo "IMAGE=<registry/image:tag> is required"; exit 1; }
	docker buildx build --platform linux/amd64 \
		-f containers/live/Dockerfile -t "$(IMAGE)" --push .

# SOURCE=/path/to/run-or-archive METADATA=/path/to/metadata.json
evidence:
	@test -n "$(SOURCE)" || { echo "SOURCE=/path/to/run-or-archive is required"; exit 1; }
	uv run python -m go2_locomotion.run evidence "$(SOURCE)" \
		--output evidence/manifest.json $(if $(METADATA),--metadata "$(METADATA)")

clean:
	rm -rf outputs .pytest_cache

# Preflight (reference-apps spec v1). Mac-side only: the GPU path is verifiable
# solely on a compatible GPU host; this catches local setup gaps.
.PHONY: check
check:
	@ok=1; \
	command -v uv >/dev/null 2>&1 || { echo "FAIL: uv not installed (https://docs.astral.sh/uv/)"; ok=0; }; \
	[ -f uv.lock ] || { echo "FAIL: uv.lock missing (broken checkout)"; ok=0; }; \
	if [ -d .venv ]; then echo "ok: .venv present"; else echo "note: no .venv yet — run 'make sync' first"; fi; \
	echo "note: GPU and Isaac Lab checks run on the target host with 'make doctor'"; \
	[ $$ok -eq 1 ] && echo "CHECK PASS" || { echo "CHECK FAIL"; exit 1; }
