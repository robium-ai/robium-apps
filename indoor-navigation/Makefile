COMPOSE = docker compose -f docker/compose.yaml
CONTROL_EXTENSION = ../shared/lichtblick-robot-control
CONTROL_EXTENSION_ARTIFACT = $(CONTROL_EXTENSION)/robium.robot-control-0.4.0.foxe

.PHONY: build sim mapping localize drive save-map load-map slam nav demo native-setup demo-native native-down demo-smoke demo-image demo-deploy smoke check check-map control-extension control-extension-check rtf down

# Initial dashboard values. Mapping and localization are selected explicitly
# from the control panel after the simulator starts in IDLE.
MAP_NAME ?= map
export MAP_NAME

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

control-extension:
	npm ci --prefix $(CONTROL_EXTENSION)
	npm run package --prefix $(CONTROL_EXTENSION)
	@echo "Control extension: $(abspath $(CONTROL_EXTENSION_ARTIFACT))"

control-extension-check:
	npm ci --prefix $(CONTROL_EXTENSION)
	npm test --prefix $(CONTROL_EXTENSION)
	npm run lint --prefix $(CONTROL_EXTENSION)
	npm run build --prefix $(CONTROL_EXTENSION)
	npm run package --prefix $(CONTROL_EXTENSION)
	@echo "Control extension: $(abspath $(CONTROL_EXTENSION_ARTIFACT))"

sim:
	$(COMPOSE) --profile sim up --abort-on-container-exit

# --- interactive dashboard: drive, map, save and navigate from the browser ---
#
# `make mapping` starts Gazebo plus the dashboard supervisor in IDLE. It does
# not start SLAM, map_server, AMCL, or publish /map. Start Mapping and Load &
# Localize create the appropriate mutually-exclusive child stack. Changing the
# simulation world restarts Gazebo and returns the navigation session to IDLE.
mapping:
	@echo "dashboard -> http://localhost:8080   (bridge on :8765)"
	$(COMPOSE) --profile mapping up --abort-on-container-exit

localize:
	@echo "Localization is selected from the dashboard; opening IDLE control panel."
	$(COMPOSE) --profile mapping up --abort-on-container-exit

# stamped:=true is REQUIRED, not a preference. The sim bridges /cmd_vel as
# geometry_msgs/msg/TwistStamped; a plain Twist is dropped at the bridge with
# no error printed anywhere, so the failure looks like "teleop runs fine but
# the robot never moves". -it gives teleop the TTY it needs to read keys.
drive:
	@echo "Keys: u i o / j k l / m , .   q,z speed   anything else = stop   Ctrl-C to quit"
	$(COMPOSE) --profile mapping exec -it mapping /entrypoint.sh \
	  ros2 run teleop_twist_keyboard teleop_twist_keyboard \
	  --ros-args -p stamped:=true -p use_sim_time:=true

# Terminal equivalent of the dashboard's Save button — same service, so both
# paths behave identically and honour the live map_name. Writes through the
# bind mount, so map.pgm/map.yaml land in the repo rather than dying with the
# container.
save-map:
	$(COMPOSE) --profile mapping exec -T mapping /entrypoint.sh \
	  ros2 service call /mapping/stop std_srvs/srv/Trigger

# Terminal equivalent of the dashboard's Load button: switches map_server to
# whatever map_name currently is. Localization sessions already load map_name
# at launch, so this is only needed to CHANGE map without restarting. A mapping
# session refuses it and says so.
load-map:
	$(COMPOSE) --profile mapping exec -T mapping /entrypoint.sh \
	  bash -lc 'ros2 param set /session_manager map_name "$(MAP_NAME)" && ros2 service call /mapping/load std_srvs/srv/Trigger'

slam:
	$(COMPOSE) --profile slam up --abort-on-container-exit

nav:
	$(COMPOSE) --profile nav up --abort-on-container-exit

demo:
	$(COMPOSE) --profile demo up --abort-on-container-exit

# Native Apple Silicon path: dependencies, build products, logs, and viewer
# assets remain below experiments/native-macos.
native-setup:
	python3 scripts/native_setup.py

demo-native:
	python3 scripts/native_demo.py run

native-down:
	python3 scripts/native_demo.py down

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
	$(COMPOSE) exec demo /entrypoint.sh ros2 run indoor_nav_bringup send_goals --goals "3.4,0.8" --timeout 120
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
	gcloud builds submit --project=robium-prod --config=indoor-navigation/cloudbuild.yaml ..

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

# Real-time-factor probe. Boots the sim scenario alone — no SLAM, no Nav2, no
# saved map — so it works before the house map exists, then samples gz's own
# real_time_factor next to the container's CPU utilisation.
#
# The two numbers are only useful together, because they answer different
# questions. RTF says whether the sim keeps up with wall-clock; CPU% says
# whether it is compute-bound. RTF 1.0 at 300%-of-1000% means idle cores and
# headroom to spend on a nicer camera. RTF 0.5 at 990% means the cores are
# already saturated and the only remaining lever is rendering less — lower
# resolution, lower rate, fewer lidar samples. RTF 0.5 at 300% would mean
# something is serialising and more CPU would not help at all.
#
# WORLD=tugbot_warehouse runs the alternate warehouse scene for comparison,
# which is how a regression gets attributed to the world rather than to
# anything else.
# (Bounded shell loops, not timeout(1) — absent on macOS hosts.)
WORLD ?= furnished_house
export WORLD
RTF_SAMPLES ?= 6
rtf:
	@$(COMPOSE) --profile sim up -d sim
	@echo "world=$(WORLD): waiting for gz world stats (up to ~2 min)..."
	@n=0; until $(COMPOSE) --profile sim exec -T sim /entrypoint.sh gz topic -l 2>/dev/null | grep -q '/stats'; do \
	  n=$$((n+1)); \
	  if [ $$n -ge 40 ]; then echo "TIMEOUT: gz never published world stats"; \
	    $(COMPOSE) --profile sim logs --tail 40 sim; \
	    $(COMPOSE) --profile "*" down --remove-orphans; exit 1; fi; \
	  sleep 3; done
	@echo "settling 20 s so boot transients do not skew the sample..."
	@sleep 20
	@cid=$$($(COMPOSE) --profile sim ps -q sim); \
	 topic=$$($(COMPOSE) --profile sim exec -T sim /entrypoint.sh gz topic -l 2>/dev/null | grep '/stats' | head -1 | tr -d '\r'); \
	 echo "--- world=$(WORLD)  stats topic=$$topic  (100% = 1 core, 1000% = all 10) ---"; \
	 for i in $$(seq 1 $(RTF_SAMPLES)); do \
	   rtf=$$($(COMPOSE) --profile sim exec -T sim /entrypoint.sh gz topic -e -t $$topic -n 1 2>/dev/null | awk '/real_time_factor/{print $$2}' | head -1); \
	   cpu=$$(docker stats --no-stream --format '{{.CPUPerc}}' $$cid 2>/dev/null); \
	   echo "  sample $$i: RTF=$${rtf:-?}  CPU=$${cpu:-?}"; \
	 done
	@$(COMPOSE) --profile "*" down --remove-orphans
	@echo "RTF PROBE DONE"

down:
	$(COMPOSE) --profile "*" down --remove-orphans
