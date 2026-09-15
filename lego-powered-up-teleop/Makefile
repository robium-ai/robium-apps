.PHONY: build check test smoke clean

build:
	uv sync

check:
	uv run ruff check src tests
	uv run pytest -q

test: check

# Real-platform smoke: connects to the hub, starts the saved bridge, verifies
# both configured motors initialized, and exchanges a PING/PONG while stopped.
smoke: check
	./app smoke

clean:
	rm -rf .venv .pytest_cache .ruff_cache
