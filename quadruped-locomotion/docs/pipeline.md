# How the RL pipeline works (go2-locomotion)

A plain-language walkthrough of what this app actually does. Written for learning —
this app's primary goal is understanding Isaac Lab RL by doing. Exact per-task
numbers (observation size, reward terms) are confirmed against the live env config
on the pod and updated here as we go.

## 1. It trains from scratch — no pretrained policy

This is the most important idea, and it's the **opposite** of the sibling app
`vla-trial` (which fine-tuned a pretrained SmolVLA on a dataset):

- The policy is a **freshly-initialized neural network with random weights.**
- At iteration 0 the Go2 flails and falls over — it has never seen a walking gait.
- It learns to walk **purely from a reward signal** — no demonstrations, no dataset,
  no pretrained model. That is what makes it *reinforcement* learning rather than
  imitation or supervised learning.
- The only pre-authored things are the **robot model** (Go2's USD/physics: masses,
  joints, motor limits) and the **task/reward definition**. The *behavior* is
  discovered from zero.

## 2. The target

A Go2 that does **velocity tracking on flat ground**: given a commanded base
velocity — "forward at 1 m/s", "strafe", "turn at 0.5 rad/s" — it produces a stable
walking gait that *matches that command* without falling. The task id encodes it:
`Isaac-Velocity-Flat-Unitree-Go2-v0` → **Velocity** (what's rewarded) · **Flat**
(terrain). Concrete deliverable: a trained checkpoint + a walking-Go2 video + a
passing smoke test.

## 3. The training loop (the whole pipeline)

```
        ┌─────────────────────────────────────────────────┐
        │  Isaac Lab spins up ~4096 Go2s in parallel on    │
        │  the GPU  (this parallelism is the speed trick)  │
        └─────────────────────────────────────────────────┘
                              │
   ┌──── for each of ~N iterations ─────────────────────────────┐
   │                                                            │
   │  1. OBSERVE   each robot's state → observation vector      │
   │     (base linear/angular velocity, gravity direction,      │
   │      joint positions/velocities, last action, the          │
   │      velocity COMMAND)                                      │
   │  2. ACT       policy(obs) → 12 joint targets  (4 legs ×    │
   │               3 joints), sent to PD motor controllers      │
   │  3. STEP      physics sim advances; robots move / fall     │
   │  4. REWARD    + for matching the commanded velocity        │
   │               − for falling, energy use, jerky motion …    │
   │  5. LEARN     PPO nudges the network toward higher-reward  │
   │               actions, using experience from ALL 4096      │
   │               robots at once                               │
   │                                                            │
   └────────────── reward climbs → a gait emerges ──────────────┘
                              │
        ┌─────────────────────────────────────────────────┐
        │  play.py loads a checkpoint, rolls it out,       │
        │  records the walking-Go2 MP4 (+ exports ONNX/JIT)│
        └─────────────────────────────────────────────────┘
```

## 4. The RL policy

**Algorithm: PPO** (Proximal Policy Optimization) via the **`rsl_rl`** library
(Isaac Lab's default). It is actor-critic:

- **Actor** = the policy network (an MLP, ~3 hidden layers). Input = the observation
  vector; output = 12 target joint positions fed to PD controllers. *This is the
  artifact that ships* (exported to TorchScript + ONNX by `play.py`).
- **Critic** = a value network estimating "how good is this state," used to compute
  PPO's advantage for stable updates. Used only during training, then discarded.

Exact observation vector, action scaling, and the full reward-term list live in the
Isaac Lab env config for this task — we read them on the pod and pin the specifics
here. _(pending: confirmed values from the live config.)_

## 5. Why thousands of robots in parallel

That is Isaac Lab's whole reason to exist. ~4096 Go2s collecting experience
simultaneously on one GPU is how a walking policy trains in **~20–40 minutes**
instead of days — the "walk in minutes" result (Rudin et al., §7). Fewer envs =
less experience per iteration = slower and noisier learning.

## 6. Our two run profiles (`config.py`)

| Profile | envs / iters | Purpose |
| --- | --- | --- |
| **smoke** (`make smoke`) | 32 / 10 | The pass bar. Proves the loop *runs* and writes a checkpoint (mechanics). Will **not** walk — that is the correct result, same as vla-trial's pipe-test. |
| **full** (`make train-full`) | 4096 / task-default | The real ~20–40 min walking policy, with video capture. |

Both invocations are built from the same `config.py` constants, so the smoke run and
a hand-run stage cannot drift apart.

## 7. How you watch it (there is no local GUI)

Everything runs headless on the cloud GPU pod (Isaac Lab has no macOS path). You
observe it three ways:

- **Recorded MP4 clips — the main way.** `--video --video_interval N` records a
  rollout clip every N training iterations → a **progression** from flailing → walking.
  `play.py` on any saved `model_<iter>.pt` renders a clean per-checkpoint video. Clips
  land in `logs/rsl_rl/<task>/<run>/videos/` on the pod and are `scp`'d back to the Mac.
- **TensorBoard reward curves** — over an SSH tunnel; watch reward climb live.
- **Live Isaac Sim GUI (optional, fiddly)** — Isaac Sim can livestream its viewport
  over WebRTC to a browser, but it's awkward through RunPod's port mapping and costs
  training throughput. Practical only for a short `play.py` livestream on a finished
  checkpoint, not for watching the training run. Not relied upon.

## 8. Reading (best → supporting)

1. **⭐ Rudin et al., "Learning to Walk in Minutes Using Massively Parallel Deep
   Reinforcement Learning" (CoRL 2021)** — *the* paper behind this exact stack
   (`legged_gym` → `rsl_rl` → Isaac Lab). Short and readable: https://arxiv.org/abs/2109.11978
2. **Isaac Lab docs** — locomotion env + rsl_rl training workflow:
   https://isaac-sim.github.io/IsaacLab/
3. **`rsl_rl`** — the PPO implementation we run: https://github.com/leggedrobotics/rsl_rl
4. **PPO** — Schulman et al. 2017 (https://arxiv.org/abs/1707.06347), or Karpathy's
   "Deep RL: Pong from Pixels" for a gentler intro.
5. **`docs/architecture-brief.md`** — this app's decisions, compute, and phased plan.
