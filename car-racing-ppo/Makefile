.PHONY: sync check smoke test clean

sync:
	uv sync

check:
	./app check

smoke:
	uv run pytest -q
	tests/test_app_cli.sh
	uv run python -m car_racing_ppo check --episodes 1

test:
	uv run pytest -q

clean:
	rm -rf .venv .pytest_cache outputs
