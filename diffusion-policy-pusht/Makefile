.PHONY: sync info check prepare-official demo demo-gateway demo-image demo-container demo-container-smoke demo-smoke app-test smoke clean train-smoke eval-trained \
	train-to-5k calibrate resume-to train-ladder eval-ladder

sync:
	uv sync

info:
	uv run lerobot-info

check:
	@ok=1; \
	command -v uv >/dev/null 2>&1 || { echo "FAIL: uv not installed (https://docs.astral.sh/uv/)"; ok=0; }; \
	command -v ffmpeg >/dev/null 2>&1 || { echo "FAIL: ffmpeg not installed (brew install ffmpeg)"; ok=0; }; \
	[ -f uv.lock ] || { echo "FAIL: uv.lock missing (broken checkout)"; ok=0; }; \
	if [ -d .venv ]; then echo "ok: .venv present"; else echo "note: no .venv yet — run './app build'"; fi; \
	if [ -f outputs/demo/ladder.json ] && grep -q '"selected_model": "official-175k"' outputs/demo/ladder.json; then echo "ok: official Diffusion manifest present"; else echo "note: run './app build' before './app run'"; fi; \
	[ $$ok -eq 1 ] && echo "CHECK PASS" || { echo "CHECK FAIL"; exit 1; }

prepare-official:
	uv run python -m diffusion_policy_pusht.run prepare-official

# Native MPS demo. The first run downloads the pinned official checkpoint.
demo: prepare-official
	uv run python -m diffusion_policy_pusht.demo.app

# Same UI behind the website session contract, still native on macOS.
demo-gateway: prepare-official
	uv run python -m diffusion_policy_pusht.demo.gateway

demo-image:
	docker build -f docker/demo.Dockerfile -t diffusion-policy-pusht:latest .

demo-container:
	docker run --rm -p 8765:8765 diffusion-policy-pusht:latest

demo-container-smoke:
	python3 scripts/demo_container_smoke.py

demo-smoke:
	uv run pytest tests/test_demo.py -v -m slow

app-test:
	tests/test_app_cli.sh

# No training: launcher contract, provenance check, and one full official-policy MPS rollout.
smoke: app-test
	uv run pytest tests/test_smoke.py -v

# Optional local research commands below are not required by the demo.
train-smoke:
	uv run python -m diffusion_policy_pusht.run train-smoke

eval-trained:
	uv run python -m diffusion_policy_pusht.run eval-trained

# First learning gate. Refuses to overwrite an existing long run.
train-to-5k:
	uv run python -m diffusion_policy_pusht.run train-to-5k

# Compare executed-action {8,16,32} x denoising {10,100} on fixed seeds.
calibrate:
	uv run python -m diffusion_policy_pusht.run calibrate

# Example: make resume-to STEPS=10000
resume-to:
	@test -n "$(STEPS)" || { echo "usage: make resume-to STEPS=10000"; exit 2; }
	uv run python -m diffusion_policy_pusht.run resume-to $(STEPS)

# Resume the same run through every retained checkpoint up to 100k.
train-ladder:
	uv run python -m diffusion_policy_pusht.run train-ladder

# Evaluate every available rung on the fixed 50-seed benchmark and generate
# outputs/demo/ladder.json. Requires `make calibrate` first.
eval-ladder:
	uv run python -m diffusion_policy_pusht.run eval-ladder

clean:
	rm -rf outputs
