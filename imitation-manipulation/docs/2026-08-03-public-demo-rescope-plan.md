# imitation-manipulation Public-Demo Rescope Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the package, replace the session-gateway demo with a plain Gradio app that adds block-shape (T/L/I/Z) and fresh-start generalization controls, and make the Docker image self-contained via HF-Hub-distributed checkpoints.

**Architecture:** `config.py` stays the single source of run params. New `shapes.py` registers a `PushShape` env subclass whose block geometry (and therefore coverage metric + goal silhouette) comes from named vertex sets. `demo/app.py` (replacing `gateway.py`) boots the `EpisodeRunner` then serves Gradio directly, printing `DEMO READY`. Checkpoint artifacts mirror the `outputs/` tree in one public HF repo; `hf download` hydrates them for both native runs and the Docker build.

**Tech Stack:** Python 3.12 (uv), lerobot 0.6.0 (pinned), gym-pusht, pymunk, Gradio 6 + gradio_rerun 0.34.1 + rerun-sdk 0.34.1, huggingface_hub CLI, Docker (linux/arm64 or amd64, CPU).

## Global Constraints

- Spec: `imitation-manipulation/docs/2026-08-03-public-demo-rescope-design.md`. Read it first.
- Work only inside `imitation-manipulation/` + this app's REGISTRY.md card/index row (repo CLAUDE.md write-surface policy).
- Branch `polish/imitation-manipulation`; commit as `robium-admin`; **never push** (git). **Never upload to HF Hub without explicit operator go-ahead** (publish action).
- Package rename map: `manip_trial` → `imitation_manipulation`; image/app display name `manip-trial` → `imitation-manipulation`. Historical names stay in dated filenames and "formerly" notes.
- Honesty copy rules: `pc_success` is 0% at every rung; the ladder is non-monotonic (5k evals 0.474 avg_max_reward vs 10k's 0.283); L/I/Z are out-of-distribution probes, never scored benchmarks. These statements must remain visible in UI + README.
- All demo run params live in `config.py`; tests import constants, never re-type literals.
- Device: MPS native / CPU in container, resolved at runtime (`config.demo_device()`).
- HF artifact repo working name: `robium/pusht-act-ladder` (org confirmed available; final confirmation at upload time).

---

### Task 1: Package rename `manip_trial` → `imitation_manipulation`

**Files:**
- Rename: `src/manip_trial/` → `src/imitation_manipulation/` (git mv, all modules)
- Modify: `pyproject.toml`, `Makefile`, `docker/demo.Dockerfile`, `tests/test_smoke.py`, `tests/test_ladder.py`, `tests/test_demo.py`, `README.md`, `docs/architecture-brief.md`
- Modify: `src/imitation_manipulation/__init__.py` (drop the hello-world `main`)

**Interfaces:**
- Produces: importable package `imitation_manipulation` with unchanged module API (`config`, `run`, `ladder`, `demo.*`); `uv run python -m imitation_manipulation.run <stage>` works.

- [ ] **Step 1: git mv and sweep references**

```bash
cd imitation-manipulation
git mv src/manip_trial src/imitation_manipulation
grep -rl 'manip_trial' --exclude-dir=.venv --exclude-dir=outputs --exclude=uv.lock . | xargs sed -i '' 's/manip_trial/imitation_manipulation/g'
grep -rl 'manip-trial' Makefile pyproject.toml docker README.md docs/architecture-brief.md src tests 2>/dev/null | xargs sed -i '' 's/manip-trial/imitation-manipulation/g'
```

Then hand-fix what sed can't judge:
- `pyproject.toml`: `name = "imitation-manipulation"`, description `"ACT imitation-learning on PushT — train, eval, and a browser demo, GPU-free"`; **delete** the `[project.scripts]` block (the hello-world entry point is dead weight).
- `src/imitation_manipulation/__init__.py`: replace contents with a one-line docstring `"""imitation-manipulation — ACT on PushT, entirely on a GPU-less Mac."""`
- `docs/architecture-brief.md`: title line becomes `# Architecture Brief — imitation-manipulation (formerly manip-trial)`; the `apps/manip-trial/` tree line becomes `imitation-manipulation/`; leave dated spec references (`2026-07-15-manip-trial-demo-page-design.md`) as-is but rewrite bare `docs/superpowers/specs/...` paths as "in the [robium](https://github.com/robium-ai/robium) repo".
- README/Makefile/config comments still referencing the old demo spec path: point at the robium repo the same way (full README rewrite comes in Task 9 — only keep it consistent here).

- [ ] **Step 2: Re-sync and run the fast tests**

```bash
uv sync   # rebuilds the editable install under the new name
uv run pytest tests/test_ladder.py -v
```
Expected: PASS (4 tests). `grep -rn "manip_trial\|manip-trial" --exclude-dir=.venv --exclude-dir=outputs --exclude=uv.lock .` returns only historical/dated references.

- [ ] **Step 3: Re-verify the pass bar**

Run: `make smoke`
Expected: 2 passed (~2 min warm).

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "refactor(imitation-manipulation): rename package manip_trial -> imitation_manipulation"
```

### Task 2: Start artifact training (background, wall-clock overlap)

**Files:** none modified — produces `outputs/train/act_pusht_ladder/` and `outputs/train/act_pusht_10k/`.

**Interfaces:**
- Produces: rung checkpoints consumed by Task 7 (`eval-ladder`) and every demo-smoke run.

- [ ] **Step 1: Kick off both training runs sequentially in one background shell**

```bash
cd imitation-manipulation
(make train-ladder && make train-baseline) &> /tmp/ladder-training.log &
```
(~8 min + ~15 min on M2 Pro MPS. Tasks 3–6 proceed while this runs.)

- [ ] **Step 2 (on completion): verify checkpoints exist**

```bash
ls outputs/train/act_pusht_ladder/checkpoints   # expect 001000 003000 005000
ls outputs/train/act_pusht_10k/checkpoints      # expect 010000 + last
```

### Task 3: `shapes.py` — named block geometries + PushShape env

**Files:**
- Create: `src/imitation_manipulation/shapes.py`
- Test: `tests/test_shapes.py`

**Interfaces:**
- Produces: `SHAPES: dict[str, list[list[tuple]]]` (keys `"T" "L" "I" "Z"`, values = lists of convex-polygon vertex lists in the T's local frame/scale); `ENV_ID = "imitation_manipulation/PushShape-v0"`; importing the module registers the env; `gym.make(ENV_ID, shape="L", obs_type="pixels_agent_pos", render_mode="rgb_array")` works. `PushShapeEnv(PushTEnv)` with `__init__(self, shape="T", **kwargs)`.

- [ ] **Step 1: Write the failing tests**

```python
"""Shape-variant env tests — geometry + coverage stay well-defined per shape."""
import gymnasium as gym
import numpy as np
import pytest

from imitation_manipulation import shapes


def test_shape_catalog():
    assert list(shapes.SHAPES) == ["T", "L", "I", "Z"]
    for name, rects in shapes.SHAPES.items():
        assert len(rects) >= 1
        for rect in rects:
            assert len(rect) == 4  # convex quads only


def test_t_matches_upstream_geometry():
    # T must reproduce gym-pusht's add_tee exactly (scale=30, length=4):
    # policy inputs are pixels — any drift here silently shifts the
    # training distribution.
    bar, stem = shapes.SHAPES["T"]
    assert bar == [(-60, 30), (60, 30), (60, 0), (-60, 0)]
    assert stem == [(-15, 30), (-15, 120), (15, 120), (15, 30)]


@pytest.mark.parametrize("shape", ["T", "L", "I", "Z"])
def test_env_steps_and_coverage(shape):
    env = gym.make(
        shapes.ENV_ID, shape=shape, obs_type="pixels_agent_pos", render_mode="rgb_array"
    )
    obs, _ = env.reset(seed=0)
    assert obs["pixels"].shape == (96, 96, 3)
    obs, reward, terminated, truncated, info = env.step(np.array([256.0, 256.0]))
    assert 0.0 <= info["coverage"] <= 1.0
    assert 0.0 <= reward <= 1.0
    env.close()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_shapes.py -v`
Expected: FAIL — `ModuleNotFoundError: imitation_manipulation.shapes`

- [ ] **Step 3: Implement `shapes.py`**

```python
"""Named block geometries for the PushShape env.

T is byte-identical to gym-pusht's add_tee(scale=30, length=4) — it IS the
training distribution; L/I/Z are out-of-distribution probes. All rects are
convex quads in the T's local frame, non-overlapping (shapely coverage math
assumes it), edge-sharing allowed. gym-pusht derives BOTH the coverage
metric and the goal-zone silhouette from block.shapes, so every shape gets
a correctly-shaped goal and a meaningful reward for free.
"""

import gymnasium as gym
import pygame
import pymunk
from gym_pusht.envs.pusht import PushTEnv

# fmt: off
SHAPES = {
    "T": [  # upstream add_tee: 120x30 bar + 30x90 stem
        [(-60, 30), (60, 30), (60, 0), (-60, 0)],
        [(-15, 30), (-15, 120), (15, 120), (15, 30)],
    ],
    "L": [  # 30x120 stem + 60x30 foot (edge-shared at x=15)
        [(-15, 0), (15, 0), (15, 120), (-15, 120)],
        [(15, 90), (75, 90), (75, 120), (15, 120)],
    ],
    "I": [  # single 30x150 bar
        [(-15, 0), (15, 0), (15, 150), (-15, 150)],
    ],
    "Z": [  # two 90x30 bars, offset, edge-shared at y=30
        [(-60, 0), (30, 0), (30, 30), (-60, 30)],
        [(-30, 30), (60, 30), (60, 60), (-30, 60)],
    ],
}
# fmt: on

ENV_ID = "imitation_manipulation/PushShape-v0"


def _add_block(space, position, angle, rects, color="LightSlateGray"):
    """gym-pusht's add_tee generalized to any list of convex quads."""
    mass = 1
    polys = [pymunk.Poly(None, r) for r in rects]
    body = pymunk.Body(mass, sum(pymunk.moment_for_poly(mass, r) for r in rects))
    shapes_ = []
    for r in rects:
        s = pymunk.Poly(body, r)
        s.color = pygame.Color(color)
        s.filter = pymunk.ShapeFilter(mask=pymunk.ShapeFilter.ALL_MASKS())
        shapes_.append(s)
    body.center_of_gravity = sum(
        (s.center_of_gravity for s in shapes_), pymunk.Vec2d(0, 0)
    ) / len(shapes_)
    body.angle = angle
    body.position = position
    body.friction = 1
    space.add(body, *shapes_)
    return body, shapes_


class PushShapeEnv(PushTEnv):
    """PushT with the block geometry swapped by name. shape='T' == upstream."""

    def __init__(self, shape="T", **kwargs):
        if shape not in SHAPES:
            raise ValueError(f"unknown shape {shape!r}; choose from {list(SHAPES)}")
        self.shape = shape
        super().__init__(**kwargs)

    # Upstream _setup calls self.add_tee(...); overriding it swaps the block
    # (and with it the goal silhouette + coverage geometry) in one place.
    def add_tee(self, space, position, angle, scale=30, color="LightSlateGray", mask=None):
        return _add_block(space, position, angle, SHAPES[self.shape], color)


gym.register(id=ENV_ID, entry_point=PushShapeEnv, max_episode_steps=300)
```

Note: drop the unused `polys = [pymunk.Poly(None, r) ...]` line if it survives to review — moments come from `moment_for_poly` directly.

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_shapes.py -v`
Expected: 6 passed (2 + 4 parametrized).

- [ ] **Step 5: Commit**

```bash
git add src/imitation_manipulation/shapes.py tests/test_shapes.py
git commit -m "feat(imitation-manipulation): PushShape env — named T/L/I/Z block geometries"
```

### Task 4: Episode runner takes a shape

**Files:**
- Modify: `src/imitation_manipulation/demo/episode_runner.py`
- Modify: `src/imitation_manipulation/config.py` (add `DEMO_DEFAULT_SHAPE = "T"`, drop `DEMO_SESSION_SECONDS`/`DEMO_FLEET_BUDGET`)

**Interfaces:**
- Consumes: `shapes.ENV_ID`, `shapes.SHAPES` from Task 3.
- Produces: `EpisodeRunner.run(rung: str, rec: rr.RecordingStream, shape: str = "T")` generator of `StepEvent` (fields unchanged); `runner.rungs`; `runner.device`. `request_abort()` is **deleted** (it existed for session takeovers).

- [ ] **Step 1: Update `episode_runner.py`**

- Replace `import gym_pusht  # noqa` with `from imitation_manipulation import shapes` (importing registers the env).
- Both `gym.make("gym_pusht/PushT-v0", ...)` calls (boot probe and `_run_locked`) become `gym.make(shapes.ENV_ID, shape=..., obs_type="pixels_agent_pos", render_mode="rgb_array")` — probe uses `config.DEMO_DEFAULT_SHAPE`, run uses the caller's `shape`.
- `run(self, rung, rec, shape="T")`: validate `shape in shapes.SHAPES` (raise `ValueError`), thread `shape` through to `_run_locked(rung, shape, rec)`.
- Delete the `self._abort` event, `request_abort()`, and the abort branch in the step loop; delete `aborted` from `StepEvent`. Keep the run lock (two browser tabs on one local container is still possible; second Run waits then errors).
- Module docstring: replace the session/abort language with the shape story (T = training distribution, L/I/Z = OOD probes).

- [ ] **Step 2: Fast import check** (full runner test needs checkpoints, Task 8)

Run: `uv run python -c "from imitation_manipulation.demo.episode_runner import EpisodeRunner, StepEvent; import inspect; assert 'shape' in inspect.signature(EpisodeRunner.run).parameters; assert not hasattr(EpisodeRunner, 'request_abort')"`
Expected: exits 0.

- [ ] **Step 3: Commit**

```bash
git add -A src/imitation_manipulation
git commit -m "feat(imitation-manipulation): episode runner takes a block shape; session-abort machinery removed"
```

### Task 5: `demo/app.py` replaces the gateway; UI gains shape + new-start controls

**Files:**
- Delete: `src/imitation_manipulation/demo/gateway.py`
- Create: `src/imitation_manipulation/demo/app.py`
- Modify: `src/imitation_manipulation/demo/ui.py`
- Modify: `Makefile` (`demo` target)

**Interfaces:**
- Consumes: `EpisodeRunner.run(rung, rec, shape)` from Task 4.
- Produces: `python -m imitation_manipulation.demo.app` serves Gradio at `0.0.0.0:$PORT` (default 8765) and prints `DEMO READY` once checkpoints are loaded and the server is up. `build_ui(runner) -> gr.Blocks` with `api_name="run_episode"` taking `[rung, shape]`.

- [ ] **Step 1: Write `app.py`**

```python
"""Demo entry point: load the ladder, serve the Gradio UI, print DEMO READY.

Deliberately session-blind: one process serves one demo. Per-user isolation
is the container boundary — whoever runs containers (a website orchestrator,
or nobody at all on a laptop) owns lifecycle, not this app. The only
orchestration surface is the DEMO READY log line, printed when checkpoints
are loaded and the server is accepting connections.
"""

import threading

from imitation_manipulation import config
from imitation_manipulation.demo.episode_runner import EpisodeRunner
from imitation_manipulation.demo.ui import build_ui


def main() -> None:
    print("loading checkpoints + env…", flush=True)
    runner = EpisodeRunner()
    ui = build_ui(runner)
    ui.launch(
        server_name="0.0.0.0",
        server_port=config.DEMO_PORT,
        show_api=False,
        quiet=True,
        prevent_thread_lock=True,
    )
    print("DEMO READY", flush=True)
    threading.Event().wait()  # serve until the process is stopped


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Rework `ui.py`**

- `build_ui(runner)` — takes the runner directly (it exists before the UI now); drop the `get_runner`/None handling.
- Add a shape radio under the rung radio:

```python
SHAPE_CHOICES = [
    ("T — the shape it was trained on", "T"),
    ("L — never seen in training", "L"),
    ("I — never seen in training", "I"),
    ("Z — never seen in training", "Z"),
]
shape = gr.Radio(choices=SHAPE_CHOICES, value=config.DEMO_DEFAULT_SHAPE,
                 label="block shape (T = training distribution; the rest probe generalization)")
```

- `run_episode(rung, shape)` generator: unchanged streaming pattern (fresh `RecordingStream` + uuid per run, `yield stream.read()`), passes `shape` to `runner.run(rung, rec, shape=shape)`; drop the `aborted` verdict branch; when `shape != "T"` prefix the verdict with `out-of-distribution probe — ` and append `— the policy only ever saw the T` to the no-success line.
- Every run already gets a fresh random start (seed counter in the runner) — surface it: the Run button caption becomes `Run episode (fresh random start each run)`.
- Intro markdown: keep the honesty lines (pc_success 0%, non-monotonic ladder, ≥95%-coverage success rule) and add one line: *"Switch the block to L, I or Z — shapes the policy never saw — and watch how (whether) 5k/10k-step training generalizes."*
- `gr.Blocks(title="imitation-manipulation — robium demo")`.
- Gallery tab unchanged (T-only real evals; that's what the numbers mean).

- [ ] **Step 3: Delete the gateway, point the Makefile at the app**

```bash
git rm src/imitation_manipulation/demo/gateway.py
```
Makefile: `demo:` runs `uv run python -m imitation_manipulation.demo.app`; comment: "The browser demo, native (MPS). Same app the container runs."

- [ ] **Step 4: Import check** (boot needs checkpoints — full test in Task 8)

Run: `uv run python -c "import imitation_manipulation.demo.app, imitation_manipulation.demo.ui"`
Expected: exits 0.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat(imitation-manipulation): session-blind demo app — gateway deleted, shape + fresh-start controls added"
```

### Task 6: Rewrite `tests/test_demo.py` for the session-blind app

**Files:**
- Rewrite: `tests/test_demo.py`

**Interfaces:**
- Consumes: `python -m imitation_manipulation.demo.app` + `DEMO READY` line (Task 5); Gradio API route `/gradio_api/call/run_episode` with `{"data": [rung, shape]}`.

- [ ] **Step 1: Rewrite the test file**

Keep: the log-tailing boot fixture (`PORT=8798`, `BOOT_TIMEOUT_S=180`), the SSE polling helper, `EPISODE_TIMEOUT_S=300`, `pytestmark = pytest.mark.slow`. Change: module command to `imitation_manipulation.demo.app`; API path loses the `/ui` prefix. Delete: claim/409/403/shutdown tests. The episode tests become:

```python
def _run_episode_via_api(payload):
    code, sub = _http("POST", "/gradio_api/call/run_episode", {"data": payload})
    assert code == 200 and "event_id" in sub, sub
    req = urllib.request.Request(f"{BASE}/gradio_api/call/run_episode/{sub['event_id']}")
    final_status = None
    deadline = time.time() + EPISODE_TIMEOUT_S
    with urllib.request.urlopen(req, timeout=EPISODE_TIMEOUT_S) as r:
        for raw in r:
            if time.time() > deadline:
                break
            line = raw.decode("utf-8", "replace").strip()
            if not line.startswith("data:") or line == "data: null":
                continue
            payload_ = json.loads(line[len("data:"):])
            if isinstance(payload_, list) and payload_ and isinstance(payload_[-1], str):
                final_status = payload_[-1]
                if "finished at step" in final_status:
                    break
    assert final_status and "finished at step" in final_status, final_status
    return final_status


def test_trained_shape_episode_completes(app):
    status = _run_episode_via_api(["1k", "T"])
    assert "reward" in status  # the honest metric is always in the verdict


def test_out_of_distribution_shape_episode_completes(app):
    status = _run_episode_via_api(["5k", "L"])
    assert "out-of-distribution" in status


def test_episode_runner_shape_roundtrip():
    from imitation_manipulation.demo.episode_runner import EpisodeRunner

    runner = EpisodeRunner()
    assert set(runner.rungs) == {"1k", "3k", "5k", "10k"}
    rec = rr.RecordingStream(application_id="imitation_manipulation_test", recording_id="t0")
    events = list(runner.run("1k", rec, shape="Z"))
    last = events[-1]
    assert last.done and 0.0 <= last.max_reward <= 1.0
    with pytest.raises(ValueError):
        list(runner.run("1k", rec, shape="X"))
```

(the boot fixture is renamed `app`; teardown = `proc.kill()` — there is no shutdown endpoint anymore.)

- [ ] **Step 2: Collect-only check** (execution needs Task 2's checkpoints)

Run: `uv run pytest tests/test_demo.py --collect-only -q`
Expected: 3 tests collected, no import errors.

- [ ] **Step 3: Commit**

```bash
git add tests/test_demo.py && git commit -m "test(imitation-manipulation): demo-smoke for the session-blind app (T + OOD shape episodes)"
```

### Task 7: Evaluate the ladder + build the manifest (after Task 2 completes)

**Files:** none modified — produces `outputs/eval/ladder/*` + `outputs/demo/ladder.json`.

- [ ] **Step 1: Verify Task 2's checkpoints, then run**

```bash
make eval-ladder   # 4 rungs x 10 seeded episodes + writes outputs/demo/ladder.json
```
Expected: exits 0; `outputs/demo/ladder.json` lists 4 rungs with numeric `avg_max_reward` and video paths. Note the fresh numbers — README/REGISTRY (Task 9) must quote THESE, not the 2026-07 ones.

- [ ] **Step 2: Native demo-smoke**

Run: `make demo-smoke`
Expected: 3 passed.

### Task 8: Artifact distribution — `fetch-artifacts` + Hub-fetching Dockerfile

**Files:**
- Modify: `Makefile` (add `fetch-artifacts`, `upload-artifacts` targets; group maintainer targets)
- Modify: `docker/demo.Dockerfile`
- Modify: `src/imitation_manipulation/config.py` (add `LADDER_HUB_REPO = "robium/pusht-act-ladder"`)
- Modify: `.dockerignore` (outputs/ no longer enters the build context at all)

**Interfaces:**
- Consumes: `outputs/` tree produced by Tasks 2+7 (upload side); HF repo layout == the `outputs/` subtree: `demo/ladder.json`, `eval/ladder/**`, `train/act_pusht_ladder/checkpoints/*/pretrained_model/**`, `train/act_pusht_10k/checkpoints/010000/pretrained_model/**`.
- Produces: `make fetch-artifacts` hydrates `outputs/` on any machine; `docker build` needs no local outputs.

- [ ] **Step 1: Makefile targets**

```makefile
# Get the demo artifacts (rung checkpoints + eval numbers + gallery videos)
# from the public Hub repo — no token, no training.
fetch-artifacts:
	uv run hf download $(LADDER_REPO) --repo-type model --local-dir outputs

# Maintainers only, and ONLY with operator approval (publish action):
# push the locally-built outputs/ artifact tree to the Hub repo.
upload-artifacts:
	uv run hf upload $(LADDER_REPO) outputs . --repo-type model \
	  --include "demo/ladder.json" --include "eval/ladder/**" \
	  --include "train/act_pusht_ladder/checkpoints/*/pretrained_model/**" \
	  --include "train/act_pusht_10k/checkpoints/010000/pretrained_model/**"
```
with `LADDER_REPO ?= robium/pusht-act-ladder` at the top. Reorder the file: user targets (`fetch-artifacts`, `demo`, `demo-image`, `demo-smoke`, `smoke`) first, then a `# --- maintainer: reproduce the artifacts` section (`train-smoke`, `eval-trained`, `train-baseline`, `baseline-eval`, `train-ladder`, `eval-ladder`, `upload-artifacts`).

- [ ] **Step 2: Dockerfile — fetch from Hub instead of COPY**

Replace the four `COPY outputs/...` lines with:

```dockerfile
# Demo artifacts (rung checkpoints, real eval numbers, gallery videos) come
# from the public Hub repo — the image is reproducible from a bare clone.
ARG LADDER_REPO=robium/pusht-act-ladder
RUN hf download ${LADDER_REPO} --repo-type model --local-dir outputs \
    && rm -rf /root/.cache/huggingface
```
placed after the `uv pip install --system -e .` layer (the CLI ships with huggingface_hub). Keep: the `-e`-install APP_ROOT comment, the build-time `EpisodeRunner()` boot probe, `HF_HUB_OFFLINE=1` **after** the fetch layer, `CMD ["python", "-m", "imitation_manipulation.demo.app"]`. `.dockerignore`: replace the per-path `outputs/...` entries with a single `outputs/`.

- [ ] **Step 3: Gate — ask the operator for upload go-ahead**

Show the artifact tree + total size (`du -sh` per rung) and ask to run `make upload-artifacts` (creates the public repo). **STOP until answered.** After upload: `make fetch-artifacts` into a scratch dir to verify layout round-trips.

- [ ] **Step 4: Full container verification**

```bash
make demo-image        # docker build — includes the Hub fetch + boot probe
docker run --rm -d -p 8765:8765 --name imdemo imitation-manipulation:latest
sleep 60 && docker logs imdemo | grep "DEMO READY"
curl -sf -X POST localhost:8765/gradio_api/call/run_episode -H 'content-type: application/json' -d '{"data": ["1k", "L"]}'
docker rm -f imdemo
```
Expected: build succeeds without local `outputs/`; `DEMO READY` in logs; the API call returns an `event_id`.

- [ ] **Step 5: Commit**

```bash
git add Makefile docker/demo.Dockerfile .dockerignore src/imitation_manipulation/config.py
git commit -m "feat(imitation-manipulation): self-contained demo image — artifacts fetched from the Hub"
```

### Task 9: Public README, REGISTRY card, stale-path sweep

**Files:**
- Rewrite: `README.md`
- Modify: `../REGISTRY.md` (imitation-manipulation card + quick-index row ONLY)

- [ ] **Step 1: README rewrite** — follow `robot-navigation/README.md`'s shape:
  title `# imitation-manipulation`; plain-language intro (imitation learning: the policy learned to push a T-block by watching demonstrations; it runs entirely on a laptop, no GPU); `**Stack:**` chip line (LeRobot 0.6.0 · ACT · gym-pusht · Gradio + Rerun · uv · Docker); **What you'll see** (checkpoint ladder 1k→10k with real eval numbers; live Rerun stream of the 96×96 policy view, actions, coverage reward; shape picker T/L/I/Z probing generalization; gallery of real eval videos); **Prerequisites** (Docker; or uv + `brew install ffmpeg` for the native MPS path); **Quick start** = `docker build` (`make demo-image`) + `docker run -p 8765:8765` + open `localhost:8765` — checkpoints come from the Hub, nothing to train; native path `make fetch-artifacts && make demo`; **maintainer section**: reproduce artifacts (`train-ladder`/`train-baseline`/`eval-ladder`, timings), `upload-artifacts`, `make smoke` as the pass bar, and the gotchas list (async-envs flag, no usable pretrained Hub baseline, ffmpeg). Honesty lines from Global Constraints are mandatory. Quote Task 7's fresh eval numbers.
- [ ] **Step 2: REGISTRY.md** — update the card: new demo story (session-blind app, Hub-distributed artifacts, shape-generalization probe), smoke bar unchanged + `make demo-smoke` (3 tests), `verified` = today's date with what was actually run; index row: Viz column `Gradio + Rerun (browser)`, Smoke column unchanged. Note the deleted gateway ("website demo page needs a website-side update — old session contract retired").
- [ ] **Step 3: Sweep** — `grep -rn "manip_trial\|manip-trial\|docs/superpowers\|apps/manip" --exclude-dir=.venv --exclude-dir=outputs --exclude=uv.lock .` → only dated-filename references and "formerly" notes remain. Secrets scan re-run (expect clean).
- [ ] **Step 4: Final verification** — `make smoke` + `make demo-smoke` one last time on the final tree; then commit:

```bash
git add README.md ../REGISTRY.md && git commit -m "docs(imitation-manipulation): public README + registry card for the self-contained demo"
```

## Self-Review Notes

- Spec coverage: HF distribution (T8), gateway removal (T5), shape picker + fresh start (T3–T5), tests (T3/T6/T7), rename + sweep + README/REGISTRY (T1/T9), upload gating (T8 step 3 hard stop). ✔
- Type consistency: `EpisodeRunner.run(rung, rec, shape="T")` used identically in T4 (produce), T5 (ui), T6 (tests). `DEMO READY` string identical in T5 app and T6 fixture and T8 docker check. ✔
- Known risk, accepted: Gradio 6 `launch(prevent_thread_lock=True)` + `/gradio_api/call/...` route names verified against the installed version during T5/T6 execution; if the route differs, fix the tests' path, not the contract.
