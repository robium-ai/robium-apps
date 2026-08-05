.PHONY: sync info fetch-artifacts demo demo-image demo-smoke smoke clean \
	train-baseline baseline-eval train-smoke eval-trained train-ladder eval-ladder upload-artifacts

# Public Hub repo holding the demo artifacts (mirrors config.LADDER_HUB_REPO).
LADDER_REPO ?= robium/pusht-act-ladder

sync:
	uv sync

info:
	uv run lerobot-info

# Get the demo artifacts (rung checkpoints + eval numbers + gallery videos)
# from the public Hub repo — no token, no training.
fetch-artifacts:
	uv run hf download $(LADDER_REPO) --repo-type model --local-dir outputs

# Preflight: catch the likely setup failures (reference-apps spec v1).
.PHONY: check
check:
	@ok=1; \
	command -v uv >/dev/null 2>&1 || { echo "FAIL: uv not installed (https://docs.astral.sh/uv/)"; ok=0; }; \
	command -v ffmpeg >/dev/null 2>&1 || { echo "FAIL: ffmpeg not installed (brew install ffmpeg) — needed for AV1 dataset decode"; ok=0; }; \
	[ -f uv.lock ] || { echo "FAIL: uv.lock missing (broken checkout)"; ok=0; }; \
	if [ -d .venv ]; then echo "ok: .venv present"; else echo "note: no .venv yet — run 'make sync' first"; fi; \
	if [ -f outputs/demo/ladder.json ]; then echo "ok: demo artifacts present"; else echo "note: no demo artifacts yet — run 'make fetch-artifacts' before 'make demo'"; fi; \
	if command -v docker >/dev/null 2>&1; then echo "ok: docker present"; else echo "note: docker not found — 'make demo-image' unavailable (native 'make demo' still works)"; fi; \
	[ $$ok -eq 1 ] && echo "CHECK PASS" || { echo "CHECK FAIL"; exit 1; }

# --- demo (design: docs/2026-08-03-public-demo-rescope-design.md)

# The browser demo, NATIVE (MPS inference) on :8765. Same app the container
# runs. Needs artifacts in outputs/ (make fetch-artifacts, or train them).
demo:
	uv run python -m imitation_manipulation.demo.app

# Build the self-contained demo container (CPU inference). Artifacts are
# fetched from the public Hub repo at build time — no local outputs needed.
demo-image:
	docker build -f docker/demo.Dockerfile -t imitation-manipulation:latest .

# The demo ship bar: app boots to DEMO READY, one T (training-distribution)
# episode and one L (out-of-distribution) episode COMPLETE through the
# Gradio API (completion is the assertion — success at this scale would be
# theater).
demo-smoke:
	uv run pytest tests/test_demo.py -v -m slow

# The pass bar: train + eval at tiny scale, asserted.
smoke:
	uv run pytest tests/test_smoke.py -v

clean:
	rm -rf outputs

# --- maintainer: reproduce the demo artifacts from scratch

# Meaningful-metrics baseline: 10k-step ACT train (~15 min on M2 Pro MPS)…
train-baseline:
	uv run python -m imitation_manipulation.run train-baseline

# …then eval it over 10 episodes.
baseline-eval:
	uv run python -m imitation_manipulation.run baseline-eval

# 200-step ACT train on lerobot/pusht (MPS).
train-smoke:
	uv run python -m imitation_manipulation.run train-smoke

# Eval the freshly trained ACT checkpoint, 2 episodes.
eval-trained:
	uv run python -m imitation_manipulation.run eval-trained

# Demo ladder: one 5k-step run saving every 1k, pruned to rungs 1k/3k/5k
# (~8 min on M2 Pro MPS). The 10k baseline run is reused as the top rung.
train-ladder:
	uv run python -m imitation_manipulation.run train-ladder

# Eval every rung (10 seeded episodes each) + write outputs/demo/ladder.json.
eval-ladder:
	uv run python -m imitation_manipulation.run eval-ladder

# Publish the locally-built artifact tree to the Hub repo. PUBLISH ACTION —
# maintainers only, with explicit operator approval; needs hf auth login.
upload-artifacts:
	uv run hf upload $(LADDER_REPO) outputs . --repo-type model \
	  --include "demo/ladder.json" \
	  --include "eval/ladder/**" \
	  --include "train/act_pusht_ladder/checkpoints/*/pretrained_model/**" \
	  --include "train/act_pusht_10k/checkpoints/010000/pretrained_model/**"
