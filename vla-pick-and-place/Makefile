.PHONY: sync doctor test smoke run image-fake image-gpu check

CAPABILITY ?= local_0123456789abcdefghijklmnopqrstuvwxyz

sync:
	uv sync --frozen

doctor:
	uv run vla-pick-and-place doctor

test:
	uv run pytest

smoke:
	uv run vla-pick-and-place smoke

run:
	VLA_RUNTIME_MODE=fake VLA_CAPABILITY=$(CAPABILITY) uv run python -m vla_pick_and_place.gateway

image-fake:
	docker buildx build --platform linux/amd64 --target fake -f docker/Dockerfile -t robium/vla-pick-and-place:fake --load .

image-gpu:
	docker buildx build --platform linux/amd64 --target gpu -f docker/Dockerfile -t robium/vla-pick-and-place:gpu --load .

check: doctor test smoke
