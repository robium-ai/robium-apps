.PHONY: sync info check prepare-official calibrate demo demo-gateway demo-image demo-container demo-container-smoke demo-smoke app-test smoke clean

sync:
	uv sync

info:
	uv run lerobot-info

check:
	@./app doctor

prepare-official:
	uv run python -m act_aloha_cube_transfer.run prepare-official

calibrate: prepare-official
	uv run python -m act_aloha_cube_transfer.run calibrate

demo: prepare-official
	uv run python -m act_aloha_cube_transfer.demo.app

demo-gateway: prepare-official
	uv run python -m act_aloha_cube_transfer.demo.gateway

demo-image:
	docker build -f docker/demo.Dockerfile -t act-aloha-cube-transfer:latest .

demo-container:
	docker run --rm -p 8765:8765 act-aloha-cube-transfer:latest

demo-container-smoke:
	python3 scripts/demo_container_smoke.py

demo-smoke:
	uv run pytest tests/test_demo.py tests/test_evidence.py -v

app-test:
	tests/test_app_cli.sh

smoke: app-test
	uv run pytest tests/test_environment.py tests/test_rollout.py tests/test_demo.py tests/test_evidence.py -v
	uv run pytest tests/test_checkpoint.py tests/test_policy.py tests/test_smoke.py -v -m slow

clean:
	rm -rf outputs
