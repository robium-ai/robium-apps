---
title: PushT with Diffusion Policy
summary: A published visual Diffusion Policy, honest evidence, and reproducible live replay on Apple Silicon.
app: diffusion-policy-pusht
date: 2026-08-22
hero: assets/thumbnail.png
hero_alt: PushT Diffusion Policy evidence and live rollout workspace
featured: false
---

# Case study: PushT with Diffusion Policy

## From training demo to policy demo

The first ACT experiment trained quickly but never solved PushT. Its large
action chunk could execute much of an episode before observing again. A
task-matched visual Diffusion Policy was the right replacement, but training a
new 263M-parameter model on a laptop turned the demo into an hours-long
prerequisite.

The final reference starts from LeRobot's published 175k checkpoint instead.
Its model card reports 65.4% success and 0.955 average maximum normalized
reward over 500 episodes with the 100-denoise schedule. Those numbers are
reused with attribution rather than wastefully reproduced just to open the app.

## Experience

The browser is an experiment workspace. A visitor chooses official or local
evidence, 10- or 100-step inference, T/L/I/Z geometry, and an exact layout
seed. The live 96×96 observation is always visible directly; an embedded
Rerun timeline adds actions and coverage. Keeping the seed fixed makes
qualitative comparisons replayable.

The evidence chart deliberately does not draw a learning curve between the
official model and the incomplete local 5k experiment. They used different
training configurations. L/I/Z are likewise labeled out-of-distribution:
they are useful probes, not benchmark claims.

## macOS result

The pinned official checkpoint loads on native MPS after generating LeRobot
0.6 processor files from the exact normalization buffers embedded in the
legacy checkpoint. Its weights remain unchanged and the adaptation is recorded
in a provenance file. The T benchmark also runs in the untouched upstream
environment; only the qualitative L/I/Z probes use custom geometry.

On the tested 16 GB Apple M5, a corrected 100-denoise reference rollout solved
official seed 1000 in 231 steps, reached 0.955 maximum raw coverage, and took
164 seconds. The five-test pass bar also booted the real Gradio app, streamed
direct RGB frames, completed T and L episodes through the public API, replayed
a seeded Z layout deterministically, and released its rollout lock after cancellation.

The published 65.4% success belongs only to the official 500-episode,
100-denoise evaluation. The faster 10-denoise result is presented as an
interactive mode, not assigned the published metric.

## Reusable decisions

- Prefer an official checkpoint when the goal is a working reference app,
  not original model research.
- Pin the model revision and record compatibility transformations.
- Separate unlike experiments visually instead of manufacturing a learning
  curve.
- Make raw policy frames the reliable primary view and use rich telemetry
  additively.
- Give interactive and reference inference modes distinct evidence claims.
- Keep Apple inference native; macOS Docker cannot expose MPS.

## Current limits

The official result is slightly below this app's aspirational 70% release
bar, so the app remains experimental. PushT is a 2D benchmark, OOD letters
are qualitative, and no hosted deployment or artifact publication is part of
this change.
