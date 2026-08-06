---
title: Teaching an arm to listen — honestly
summary: A language-conditioned SmolVLA policy drives a simulated SO-101 arm. The pipeline is proven end-to-end; the full-training checkpoint is not — and this article says so.
app: vla-language-learning
date: 2026-08-05
hero: assets/hero-placeholder.svg
hero_alt: Placeholder — real footage coming
featured: true
---

# Case study: vla-language-learning

*Type "put the green cube in the bin" and a vision-language-action policy
drives a simulated robot arm toward doing it. This is the most honest app
in the portfolio: the pipeline works end-to-end, and no checkpoint has
been trained long enough to succeed yet.*

## The problem

Vision-language-action models are the current frontier of robot learning:
one policy that takes a camera image and an instruction in plain language,
and emits joint commands. The recipes are young, the tooling is moving
fast, and most public examples either assume a lab's hardware or skip the
unglamorous parts — the scene, the data, the evaluation harness. The goal
here was the whole loop on a laptop: build a manipulation scene from
scratch, collect demonstrations, fine-tune SmolVLA remotely, and evaluate
locally with a numeric success bar.

## Constraints

- **Host:** Apple Silicon Mac. MuJoCo renders offscreen via `MUJOCO_GL=cgl`;
  training locally is orders of magnitude too slow, so fine-tuning runs on
  a rented cloud GPU (HF Jobs) while everything else stays local.
- **Never Docker for the ML path:** a container loses MPS entirely on
  macOS — a documented exception to the container-first rule.
- **Honesty:** the success bar (60% over 20 episodes) is asserted only
  against a real fine-tune. Pipe-test checkpoints score what they score.

## The approach

The scene is built, not borrowed: the SO-101 arm from MuJoCo Menagerie on
a custom pedestal scene with a cube, a bin, an overview camera, and a
contact-based success predicate. A scripted oracle — inverse kinematics
with a wrist-roll solve, no learning — is both the daily canary (10/10 on
tuned seeds proves scene, physics, and predicate independent of any policy
question) and the demonstration engine: it records clean episodes,
discarding its own misses, and pushes the dataset to the Hub.

Fine-tuning follows the local-gate-before-paid-run pattern: a free CPU
`train-smoke` catches config and shape errors before any GPU spend, then
HF Jobs runs the real training remotely. Evaluation pulls the checkpoint
back and rolls it out in MuJoCo with Rerun logging every episode.

## Robium components used

The architect skill routed the stack; the environments skill's macOS rules
set the uv-native, MUJOCO_GL=cgl shape; the data skill's conventions govern
the dataset recording and Hub pushes; the testing skill shaped the split
between the mechanics smoke (checkpoint loads, episodes roll, metrics
write) and the deferred success bar; the visualization skill picked Rerun.

## Major decisions

1. **Oracle first.** Before any learning, a ground-truth IK controller had
   to hit 10/10. Every later failure then has a controlled baseline: if
   the oracle passes and the policy flails, the policy is the problem.
2. **The end-effector site is not the grasp point** — calibrate the offset
   empirically, and solve wrist roll as a 1-D root-find; a free roll can
   make grasping geometrically impossible.
3. **Remote GPU, local everything else.** An A10G on HF Jobs fine-tunes
   SmolVLA; the Mac records, evaluates, and visualizes. The M0 spike that
   proved local training non-viable is committed with numbers.
4. **The smoke test asserts mechanics, not success** — because asserting a
   success rate against a 100-step pipe-test checkpoint would be theater.
   The 60% bar is wired and waits for the funded 20k-step run.

## Results

- Oracle: 10/10 on tuned seeds; the full record → push → train (remote) →
  pull → eval loop verified end to end, including a real paid-submission
  path validated to the credit wall.
- `make smoke`, `make demo-smoke`, `make check`, and `make test` green
  (2026-08-05, post-rename cold verification).
- The demo ships two controllers, honestly labeled: `oracle` (succeeds,
  scripted and blind to language) and `trained` (the pipe-test checkpoint,
  which visibly flails).

## Limitations

- No successful learned policy yet: the ~$20-40 full fine-tune is a
  deliberate cost decision, not a technical blocker. Until it runs, this
  app demonstrates a pipeline, not a capability.
- Single object, single instruction template; language conditioning is
  exercised, not stress-tested.
- Simulation only.

## Next steps

Fund and run `make train-full`, assert the 60% bar, and promote the result
from "pipeline proven" to "capability shown" — the article will be revised
when that happens (it is a living document).
