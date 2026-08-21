.PHONY: sync test test-all clean contract dataset-check controllers expert record sim play demo demo-image demo-smoke check

sync:
	uv sync

# The regression suite. Excludes `slow` — the tests that boot the real gateway
# or pull a pinned dataset from the Hub. Everything left is fast and offline.
test:
	uv run pytest tests/ -v

test-all:
	uv run pytest tests/ -v -m ""

clean:
	rm -rf outputs

# What the pinned environment actually is: spaces, cameras, control rate,
# info keys, success key. Writes outputs/contract.json and exits non-zero if
# the live environment has drifted from the contract the app was built on.
contract:
	uv run python -m vla_pick_and_place.run contract

# Whether the pinned datasets match this environment — schema AND scene. The
# second candidate is expected to fail the scene check; that is the report,
# not a regression. Exits non-zero only if the PRIMARY dataset fails.
dataset-check:
	uv run python -m vla_pick_and_place.run dataset-check

# Which controllers may run here, and the named reason the rest may not.
controllers:
	uv run python -m vla_pick_and_place.run controllers

# The scripted expert's pass bar: success rate over a fixed seed band.
N ?= 30
expert:
	uv run python -m vla_pick_and_place.run expert $(N)

# Record N SUCCESSFUL expert demonstrations into outputs/dataset/ (never pushed).
EPISODES ?= 50
record:
	uv run python -m vla_pick_and_place.run record $(EPISODES)

# Drive the simulator headless and write an .rrd: `make sim SEED=3 STEPS=60`.
# open with: uv run rerun outputs/viz/sim_seed3.rrd
SEED ?= 0
STEPS ?= 60
sim:
	uv run python -m vla_pick_and_place.run sim $(SEED) $(STEPS)

# Replay a pinned recorded episode headless and write an .rrd.
EPISODE ?= 0
play:
	uv run python -m vla_pick_and_place.run play $(EPISODE)

# --- demo page --------------------------------------------------------------

# The demo gateway, NATIVE. MUJOCO_GL=cgl is required on macOS and contexts
# are thread-affine — read src/vla_pick_and_place/demo/session.py's docstring
# before "simplifying" the worker thread away.
demo:
	MUJOCO_GL=cgl uv run python -m vla_pick_and_place.demo.gateway

# The demo container. No build secret: the environment is a public pip package
# and the demonstration dataset is a public Hub repo.
demo-image:
	docker build -f docker/demo.Dockerfile -t vla-pick-and-place:latest .

# The ship bar: gateway boots to DEMO READY, session guards hold (409/403),
# a real reset frame and a real driven step arrive through the Gradio API,
# dataset playback advances, and /shutdown exits the process.
demo-smoke:
	uv run pytest tests/test_demo.py -v -m slow

# Preflight: catch the likely setup failures.
check:
	@ok=1; \
	command -v uv >/dev/null 2>&1 || { echo "FAIL: uv not installed (https://docs.astral.sh/uv/)"; ok=0; }; \
	[ -f uv.lock ] || { echo "FAIL: uv.lock missing (broken checkout)"; ok=0; }; \
	if [ -d .venv ]; then echo "ok: .venv present"; else echo "note: no .venv yet — run 'make sync' first"; fi; \
	[ "$$(uname)" = "Darwin" ] && echo "note: macOS requires MUJOCO_GL=cgl (./app sets it)"; \
	[ $$ok -eq 1 ] && echo "CHECK PASS" || { echo "CHECK FAIL"; exit 1; }
