.PHONY: sync check smoke app-test test clean

sync:
	uv sync

check:
	@ok=1; \
	command -v uv >/dev/null 2>&1 || { echo "FAIL: uv not installed (https://docs.astral.sh/uv/)"; ok=0; }; \
	[ -f pyproject.toml ] || { echo "FAIL: pyproject.toml missing (broken checkout)"; ok=0; }; \
	if [ -d .venv ]; then echo "ok: .venv present"; else echo "note: no .venv yet - run './app build'"; fi; \
	[ $$ok -eq 1 ] && echo "CHECK PASS" || { echo "CHECK FAIL"; exit 1; }

app-test:
	tests/test_app_cli.sh

# Hardware-free pass bar: everything that can be proven without the robot.
smoke: app-test
	uv run pytest tests -v

# Everything above plus the tests that need robot, camera, or gamepad.
test:
	uv run pytest tests -v -m ''

clean:
	rm -rf .venv outputs/sessions
