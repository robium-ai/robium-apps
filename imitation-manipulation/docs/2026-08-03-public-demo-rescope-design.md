# Design — imitation-manipulation public demo rescope

**Date:** 2026-08-03  **Status:** approved by operator (this session)
**Supersedes** the session-gateway demo design (formerly
`docs/superpowers/specs/2026-07-15-manip-trial-demo-page-design.md` in the
[robium](https://github.com/robium-ai/robium) repo) for this app's demo layer.
The train/eval pipeline design (`architecture-brief.md`) is unchanged.

## Goal

A public user clones the repo, runs `docker build` + `docker run`, opens a
browser, and explores how imitation-learning checkpoints behave — no
training, no HF token, no Python setup. The app is identical locally and
hosted; per-user isolation is entirely the job of whoever runs containers
(e.g. a website orchestrator spawning one container per visitor). The app
knows nothing about users or sessions.

## Decisions (operator-confirmed)

1. **No user-side training path.** Checkpoints are distributed via a public
   HF Hub repo; training targets stay in the Makefile as the documented
   maintainer path to reproduce the artifacts.
2. **Env controls for generalization:** a block **shape picker**
   (T = training distribution, plus L / I / Z out-of-distribution variants)
   and a **new-random-start** control (fresh seed per run). Physics sliders
   and size sliders rejected (low visual payoff / UI noise).
3. **Session gateway deleted.** No `/start`/`/status`/`/shutdown`, no claim
   guards, no session timer. The app = Gradio UI + episode runner, served
   directly. It prints `DEMO READY` when checkpoints are loaded — a generic
   readiness signal any orchestrator (or human) can use. The robium-website
   page that spoke the old gateway contract needs a website-side update
   (out of scope for this repo).

## Architecture

```
src/imitation_manipulation/
├── config.py            # single source of run params (unchanged role)
├── run.py               # maintainer pipeline stages (unchanged role)
├── ladder.py            # eval-ladder + manifest generation (unchanged)
├── shapes.py            # NEW: block-shape vertex sets (T/L/I/Z) +
│                        #   PushShape env subclass + gym registration
└── demo/
    ├── app.py           # NEW (replaces gateway.py): boots EpisodeRunner,
    │                    #   launches Gradio on $PORT, prints DEMO READY
    ├── ui.py            # rung radio + shape radio + Run + Rerun stream +
    │                    #   gallery tab (real eval numbers, T-only)
    └── episode_runner.py  # run(rung, shape) — env built per shape
```

- **shapes.py:** `PushTEnv.add_tee` is one static method building the block
  from convex polys; `_get_coverage` and the goal-zone rendering both derive
  from `block.shapes`, so a subclass swapping vertex lists keeps the
  coverage metric and the green target silhouette consistent for any shape.
  One registered env id (`imitation_manipulation/PushShape-v0`) taking a
  `shape` kwarg; `T` reproduces upstream geometry exactly.
- **Honesty rule carried over:** `ladder.json` metrics are T-only (that's
  what the evals measured). Shape variants are labeled as
  out-of-distribution probes, never scored benchmarks. `pc_success` 0% and
  the non-monotonic ladder stay visible.

## Artifact distribution

- One public HF Hub repo (final name confirmed by operator before upload;
  working name `robium-ai/pusht-act-ladder`) holding: 4 rung checkpoints
  (`pretrained_model` only), `ladder.json`, one eval MP4 per rung. ~200 MB.
- `make fetch-artifacts` downloads the bundle into `outputs/` (native path).
- `docker/demo.Dockerfile` fetches the same bundle at build time (build-arg
  `LADDER_REPO`, no token — public repo) with a fallback to baking local
  `outputs/` so maintainers can build before/without the Hub repo.
- **Uploading is a publish action — requires explicit operator go-ahead and
  credentials; nothing is pushed automatically.**

## Tests

- `make smoke` — unchanged (200-step train + 2-episode eval, asserted).
- `make demo-smoke` — reworked: app boots to `DEMO READY`; one T episode
  completes via the Gradio API; one L (out-of-distribution) episode
  completes; process exits cleanly. Session-guard tests deleted with the
  gateway.
- `tests/test_ladder.py` — unchanged; plus shape-geometry unit tests
  (vertex sets valid/convex, T matches upstream, coverage well-defined for
  every shape).

## Ride-along (polish playbook)

Package rename `manip_trial` → `imitation_manipulation`, stale-path sweep,
secrets scan (clean), public README rewrite (Quick start = docker build/run;
maintainer section for training + upload), REGISTRY.md card + index row.
All on `polish/imitation-manipulation`; commits only, never pushed.
