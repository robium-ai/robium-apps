# Documentation-only TEST-NET address. Override with ROBOT=<robot-ip>.
ROBOT ?= 192.0.2.10
PORT  ?= 8765
HERE  := $(dir $(realpath $(lastword $(MAKEFILE_LIST))))

.PHONY: bridge teleop smoke

# Start foxglove_bridge on the robot over SSH, wait for the WS handshake.
bridge:
	ROBOT=$(ROBOT) PORT=$(PORT) "$(HERE)scripts/start_bridge.sh"

teleop:
	@echo "Open https://app.foxglove.dev -> Open connection -> ws://$(ROBOT):$(PORT)"
	@echo "Import layout: $(HERE)foxglove/tb4-teleop-layout.json"

# Hardware-in-the-loop smoke: start bridge, then assert bridge/scan/cmd_vel.
smoke:
	ROBOT=$(ROBOT) PORT=$(PORT) "$(HERE)scripts/start_bridge.sh"
	ROBOT=$(ROBOT) PORT=$(PORT) "$(HERE)tests/smoke.sh"

# --- Orin web console (Phase 2) ---
ORIN := $(HERE)orin

.PHONY: orin-test orin-build orin-serve orin-smoke orin-down

orin-test:
	cd "$(ORIN)" && node --test

orin-build:
	docker compose -f "$(ORIN)/docker/compose.yaml" build

orin-serve:
	docker compose -f "$(ORIN)/docker/compose.yaml" up

orin-smoke:
	cd "$(ORIN)" && node --test
	"$(ORIN)/tests/serve_smoke.sh"

orin-down:
	docker compose -f "$(ORIN)/docker/compose.yaml" down

# Preflight (reference-apps spec v1). Hardware app: this verifies reachability
# only — bridge install state and robot health need the robot itself (make smoke).
.PHONY: check
check:
	@ok=1; \
	command -v ssh >/dev/null 2>&1 || { echo "FAIL: ssh not available"; ok=0; }; \
	if ping -c 1 -t 3 $(ROBOT) >/dev/null 2>&1; then echo "ok: robot reachable at $(ROBOT)"; \
	else echo "FAIL: robot $(ROBOT) not reachable (same Wi-Fi? override with ROBOT=<ip>)"; ok=0; fi; \
	echo "note: bridge install + base discovery are only verifiable on-robot (make smoke)"; \
	[ $$ok -eq 1 ] && echo "CHECK PASS" || { echo "CHECK FAIL"; exit 1; }
