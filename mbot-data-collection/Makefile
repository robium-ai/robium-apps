.PHONY: sync check smoke clean

sync:
	uv sync

check:
	@ok=1; \
	command -v uv >/dev/null 2>&1 || { echo "FAIL: uv not installed (https://docs.astral.sh/uv/)"; ok=0; }; \
	[ -f pyproject.toml ] || { echo "FAIL: pyproject.toml missing (broken checkout)"; ok=0; }; \
	if [ -d .venv ]; then echo "ok: .venv present"; else echo "note: no .venv yet - run './app build'"; fi; \
	[ $$ok -eq 1 ] && echo "CHECK PASS" || { echo "CHECK FAIL"; exit 1; }

# The pass bar: the real robot, camera and controller, end to end.
smoke:
	./app doctor

clean:
	rm -rf .venv build outputs
