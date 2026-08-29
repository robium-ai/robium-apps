# Quadruped locomotion

Train a Unitree Go2 walking policy with reinforcement learning in NVIDIA Isaac
Lab, compare recorded checkpoints, and optionally pilot a policy from a browser.

The simulation and training path requires a compatible Linux NVIDIA GPU host.
The repository can still verify command construction, artifact integrity, and
the recorded experience on macOS or a CPU-only machine.

## What is here

- a small wrapper around Isaac Lab's registered Go2 velocity task and RSL-RL;
- a real GPU smoke test that requires a newly written checkpoint;
- content-addressed evidence tooling for run directories and tar archives;
- five real rollout clips from the recovered 2026-07-27 training run; and
- the browser-control prototype used during that run.

The recovered baseline contains 21 checkpoints, policy exports, task and agent
configuration, a complete training log, and 15 rollout clips. Its manifest is
[`evidence/manifest.json`](evidence/manifest.json). It remains historical
evidence; a fresh current-stack run is still required to close issue #70.

## Free local checks

```bash
make sync
make test
make check
```

These checks do not pretend to run Isaac Lab. The GPU test is deliberately
deselected from `make test` and fails when explicitly invoked on the wrong host.

## GPU workflow

On a compatible host with Isaac Lab installed:

```bash
export ISAACLAB_ROOT=/path/to/IsaacLab
make doctor
make list-envs
make smoke
make train-full
make play
```

The wrapper uses Isaac Lab's unified `train` and `play` entry points. Set
`ISAACLAB_CLI_STYLE=legacy` only when reproducing an older installation that
still uses the per-library scripts. Run sizes can be adjusted through the
`GO2_*` environment variables after the initial smoke establishes what the
selected host supports.

## Evidence

Inventory a completed run or archive without copying it into Git:

```bash
make evidence \
  SOURCE=/path/to/run-or-archive \
  METADATA=/path/to/run-metadata.json
```

The output records file roles, sizes, and SHA-256 digests. Publishing the full
bundle to Hugging Face remains a separate, reviewed action.

## Documentation

- [`docs/pipeline.md`](docs/pipeline.md): how the reinforcement-learning loop works.
- [`docs/live-demo.md`](docs/live-demo.md): the verified MJPEG control prototype.
- [`docs/architecture-brief.md`](docs/architecture-brief.md): current decisions and risks.
- [`docs/case-study.md`](docs/case-study.md): portable article source.
