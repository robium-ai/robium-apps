COMPOSE = docker compose -f docker/compose.yaml

.PHONY: build sim slam nav demo demo-smoke demo-image demo-deploy smoke check check-map down

# Preflight: catch the likely setup failures before any scenario runs.
# (Bounded checks only; no timeout(1) — absent on macOS hosts.)
check:
	@ok=1; \
	command -v docker >/dev/null 2>&1 || { echo "FAIL: docker not installed (install Docker Desktop or compatible)"; ok=0; }; \
	if [ $$ok -eq 1 ] && ! docker info >/dev/null 2>&1; then echo "FAIL: docker daemon not running"; ok=0; fi; \
	if [ $$ok -eq 1 ] && ! docker compose version >/dev/null 2>&1; then echo "FAIL: docker compose v2 not available"; ok=0; fi; \
	if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then \
	  echo "FAIL: port 8765 already in use (make down, or stop whatever holds it)"; ok=0; fi; \
	if docker image inspect indoor-navigation:latest >/dev/null 2>&1; then \
	  echo "ok: image indoor-navigation:latest present"; \
	else echo "note: image not built yet — 'make build' first (~10 min cold)"; fi; \
	[ $$ok -eq 1 ] && echo "CHECK PASS" || { echo "CHECK FAIL"; exit 1; }

build:
	$(COMPOSE) build sim

sim:
	$(COMPOSE) --profile sim up --abort-on-container-exit

slam:
	$(COMPOSE) --profile slam up --abort-on-container-exit

nav:
	$(COMPOSE) --profile nav up --abort-on-container-exit

demo:
	$(COMPOSE) --profile demo up --abort-on-container-exit

# Demo gate: boot the demo scenario, assert the gateway tunnels the Foxglove
# WebSocket, serves the bundled viewer, /status reaches ready, session
# guards hold (409/403 for intruders), one nav goal succeeds, and /shutdown
# kills the container. (Bounded shell loops, not timeout(1) — absent on
# macOS hosts.)
demo-smoke:
	$(COMPOSE) --profile demo up --build -d demo
	n=0; until bash tests/check_ws.sh http://localhost:8765; do \
	  n=$$((n+1)); [ $$n -ge 20 ] && echo "WS TIMEOUT" && exit 1; sleep 3; done
	curl -sf -X POST "http://localhost:8765/start?session=smoke" | grep -q '"ok": true'
	curl -sf "http://localhost:8765/status?session=smoke" | grep -q '"budget": 5'
	n=0; until curl -sf "http://localhost:8765/status?session=smoke" | grep -q '"ready": *true'; do \
	  n=$$((n+1)); [ $$n -ge 48 ] && echo "READY TIMEOUT" && exit 1; sleep 5; done
	curl -sf "http://localhost:8765/status?session=smoke"
	test "$$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:8765/status?session=intruder")" = "409"
	test "$$(curl -s -o /dev/null -w '%{http_code}' -X POST "http://localhost:8765/shutdown?session=intruder")" = "403"
	test "$$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:8765/?session=smoke")" = "302"
	curl -sfL "http://localhost:8765/?session=smoke" | grep -qi "<html"
	test "$$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:8765/fs/list?session=smoke&path=src")" = "404"
	test "$$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:8765/pty?session=smoke")" = "404"
	test "$$(curl -s -o /dev/null --path-as-is -w '%{http_code}' "http://localhost:8765/../etc/passwd")" = "404"
	$(COMPOSE) exec demo /entrypoint.sh ros2 run indoor_nav_bringup send_goals --goals "0.3,0.5" --timeout 120
	curl -s -X POST "http://localhost:8765/shutdown?session=smoke" | grep -q bye
	n=0; until [ -z "$$($(COMPOSE) ps -q demo)" ] || [ "$$(docker inspect -f '{{.State.Running}}' $$($(COMPOSE) ps -q demo) 2>/dev/null)" != "true" ]; do \
	  n=$$((n+1)); [ $$n -ge 10 ] && echo "SHUTDOWN TIMEOUT" && exit 1; sleep 2; done
	$(COMPOSE) --profile "*" down --remove-orphans
	@echo "DEMO SMOKE PASS"

smoke:
	$(COMPOSE) --profile test up --build --abort-on-container-exit --exit-code-from smoke

# --- live demo on Cloud Run (per-visitor instances; see robium.ai spec) ---
DEMO_IMAGE = us-central1-docker.pkg.dev/robium-prod/robium/demo-nav-trial:latest

demo-image:
	gcloud builds submit --project=robium-prod --config=cloudbuild.yaml .

demo-deploy:
	gcloud run deploy demo-nav-trial --image=$(DEMO_IMAGE) \
	  --region=us-central1 --project=robium-prod --platform=managed \
	  --port=8765 --concurrency=4 --session-affinity --min-instances=0 --max-instances=5 \
	  --timeout=1800 --cpu=8 --memory=8Gi --cpu-boost --no-cpu-throttling \
	  --execution-environment=gen2 \
	  --service-account=demo-nav-trial-sa@robium-prod.iam.gserviceaccount.com \
	  --network=demo-net --subnet=demo-subnet --vpc-egress=all-traffic \
	  --set-env-vars=GZ_RELAY=127.0.0.1,GZ_IP=127.0.0.1,FASTDDS_BUILTIN_TRANSPORTS=UDPv4 \
	  --command=/entrypoint.sh --args="ros2,launch,indoor_nav_bringup,demo.launch.py" \
	  --allow-unauthenticated --quiet
# GZ_RELAY/GZ_IP: gz-transport discovery is UDP-multicast-based and Cloud Run
# has no multicast — without the unicast loopback relay, gz server is
# undiscoverable and spawn/bridge wait forever (verified 2026-07-12).

check-map:
	python3 tests/check_map.py src/indoor_nav_bringup/maps/map.yaml

down:
	$(COMPOSE) --profile "*" down --remove-orphans
