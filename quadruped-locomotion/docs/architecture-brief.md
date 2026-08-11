# go2-locomotion — architecture brief

Train a **Unitree Go2 quadruped to walk** via **reinforcement learning in NVIDIA
Isaac Lab**, on a **cloud NVIDIA L4 GPU**, and produce a walking-robot video plus a
repo smoke test. Satisfies robium-applications **issue #3 — "Demo: Isaac Lab RL
policy"**.

Primary intent is **learning Isaac Lab RL by doing**, with a real repo deliverable
as the by-product. Not chasing SOTA — smoke-scale correctness, like
`manip-trial`/`vla-trial`.

> **Provenance & status.** Kickoff-stage (2026-07-26). Written by hand from the
> `HANDOFF.md` scoping brief, following the on-disk robium `architect` +
> `isaac-lab` skills. The robium plugin (agents + skills) is **not loaded in this
> session** — the `robium-architect` agent that repo convention wants to author
> this file was unavailable, so the kickoff was *not* routed through it. Logged as
> a skill/plugin gap in `learnings/2026-07-26-isaac-go2.md`; surfaced, not papered
> over (two-hats rule). Sections marked _(pending)_ fill in as the build lands.

---

## 1. What is fundamentally different about this app

Every existing app in this repo (`nav-trial`, `manip-trial`, `vla-trial`,
`tb4-teleop`) is **Mac-native or GPU-less** and honors the repo's
`local == remote reproduce` norm. **This app cannot.**

- **Isaac Lab does not run on macOS / Apple Silicon, at all.** Omniverse Kit needs
  an RTX-class NVIDIA GPU + CUDA and runs only on Linux/Windows. Docker on the Mac
  cannot help — there is no GPU to pass through. (GPU floor is `isaac-sim`'s; not
  re-derived here.)
- Therefore the **MacBook is a thin SSH/browser client**; sim, training, and even
  the smoke test run **entirely on a cloud GPU VM**.
- This **breaks the `environments` skill's virtual-first, local==remote model** —
  the model that underpins every other app here. This is a documented
  **`environments` skill gap** (see `learnings/2026-07-26-isaac-go2.md`): the
  skill needs a distinct *"GPU-only-in-cloud, no local mirror"* pattern for this
  class of app (any future Isaac Sim / GR00T / heavy-CUDA app hits the same wall).
  We do **not** paper over it with a fake local path.

**Consequence for the pass bar:** `make smoke` is a **remote-GPU** test — a short
Go2 train on the L4 that asserts a checkpoint was produced and exit codes are
clean. This is the remote-GPU variant of `manip-trial`'s policy-eval-as-smoke, and
it is a **new pattern for this repo**. Design §5 covers it.

---

## 2. Stack rationale

| Layer | Choice | Why (and what was rejected) |
| --- | --- | --- |
| Framework | **Isaac Lab** on Isaac Sim / Omniverse | User wants the NVIDIA stack specifically. `isaac-lab` skill owns the RL/IL training layer on top of an already-running Isaac Sim. |
| Workload | **Reinforcement learning** (PPO) | User pivoted through VLA/imitation and landed on RL. The flagship Isaac Lab path with the most examples. |
| Task | **`Isaac-Velocity-Flat-Unitree-Go2-v0`** (flat first) | Flagship Go2 locomotion task; fastest route to a walking policy (~20–40 min on an L4). Rough terrain (`Isaac-Velocity-Rough-Unitree-Go2-v0`, name to verify at runtime) is a Phase-3 follow-on. Task id confirmed via ctx7 `/websites/isaac-sim_github_io_isaaclab_main`, 2026-07-26. **Re-verify with `list_envs.py` on the VM — never trust a task id from memory (skill directive).** |
| RL library | **`rsl_rl`** (default PPO) | Isaac Lab default, most examples/docs. `play.py` for `rsl_rl` also auto-exports the policy to TorchScript + ONNX under `exported/` — free Phase-3 sim-to-real hand-off. Alternatives (`skrl`, `rl_games`, `sb3`) not needed for a walking policy. |
| Compute | **RunPod L4 24 GB pod** (booting the NVIDIA Isaac Sim NGC container as the pod image) | **Switched off GCP 2026-07-27** — GCP's new-project GPU quota gate (§3) is a bad default for a *reference app* others bootstrap from. RunPod has **zero quota gate** (pod live in ~1 min), per-second billing (L4 ~$0.39/hr), built-in idle timeout, and lets you boot the **official Isaac Sim container as the image** — the easiest Isaac Lab setup (no driver wrangling). The whole Go2 job is ~4–8 GPU-hr ≈ **$2–6**, so $/hr is noise; ease + no-quota won. GCP kept as the "already-in-ecosystem / Phase-3 GPU-backed robium.ai demo" alternative (§3). |
| Install path | **Isaac Sim NGC container as the RunPod pod image**, Isaac Lab cloned + `./isaaclab.sh --install` on top | On RunPod the container path is *easier* than pip (no host driver setup — the image ships the CUDA/Omniverse stack). Corrects the earlier pip-vs-NGC deliberation: with RunPod, container wins. Exact image tag + Isaac Sim↔Isaac Lab version pairing verified at Phase 0 (skill directive — never pin from memory). |
| App shape | **Bootstrap from `apps/vla-trial`** (structure only) | Closest existing app for `config.py` single-source, `Makefile`, brief shape, `make smoke`-as-pytest, two-run-profile pattern. Diverges entirely on the env/compute layer (cloud GPU vs. Mac uv). |
| Env tooling | **uv on the VM** for the thin app wrapper; **Isaac Sim/Lab installed per its own docs** | The app's own Python (config, smoke harness, thin CLI) is uv-managed; Isaac Sim itself is a heavy pinned install that follows NVIDIA's install docs on the Linux VM, not a uv dependency. |

---

## 3. Compute foundation — RunPod (and why not GCP)

**Decision (2026-07-27): host the Isaac Sim VM on RunPod, not GCP.** RunPod has no
new-account GPU quota gate — you sign up, add a few dollars of credit, and a pod
with a chosen image is live in ~1 minute. For Isaac Lab specifically it's the
easiest path: boot the **official NVIDIA Isaac Sim NGC container as the pod image**
(the CUDA/Omniverse stack ships inside it — no host-driver wrangling), then clone
Isaac Lab and `./isaaclab.sh --install` on top. Per-second billing, L4 ~$0.39/hr,
built-in idle timeout. The whole Go2 job is ~4–8 GPU-hr ≈ **$2–6**.

**User action (billing-tied):** create a RunPod account + add ~$10 credit. Nothing
else is blocked on quotas.

### Why not GCP — the quota gate we hit (kept for the record + Phase-3 demo)

GCP spot is actually *cheaper* (L4 ~$0.20–0.30/hr) and the robium ecosystem lives
there (Cloud Run demos, robium.ai DNS), so GCP remains the option for the eventual
**Phase-3 GPU-backed live demo**. But as the *default* for a reference app it fails
newcomers — measured on `robium-prod` / us-central1, 2026-07-26:

| Quota | Scope | Limit | Usage | Enough for 1 L4 spot VM? |
| --- | --- | --- | --- | --- |
| `NVIDIA_L4_GPUS` | region | 1 | 0 | ✅ yes |
| `PREEMPTIBLE_NVIDIA_L4_GPUS` | region | 1 | 0 | ✅ yes (spot bills here) |
| **`GPUS_ALL_REGIONS`** | **global** | **0** | 0 | ❌ **NO — this is the gate** |

GCP enforces **both** the per-region GPU quota and the global all-regions GPU
quota; the lower one binds. The regional L4 quota is already sufficient for one
L4 — **the only thing blocking any GPU-VM launch is the global
`GPUS_ALL_REGIONS = 0`.** The handoff's instruction to "request `NVIDIA_L4_GPUS`"
targets a quota that is already fine.

**What happened (2026-07-27):** raising **`GPUs (all regions)`**
(`compute.googleapis.com/gpus_all_regions`) → 2 was **auto-denied in 0.4 s**
(verified via the Cloud Quotas API `quotaPreferences` endpoint). Google Support
confirmed: *"wait 48h until you resubmit… or until your billing account has
additional history."* Root cause is account standing, not the request: the
**project** is 15 days old (the billing account is ~5.5 months / paid / active, so
the *project* age + thin GPU-tier spend is the block), and GPU is a special-risk
quota GCP gates tightly. A paid account with history has decent odds on the 48h
resubmit — but that 2-day, uncertain gate is exactly why GCP is not the default.

> Generalizable findings (candidates for the `environments`/`isaac-lab` skills):
> (1) a GPU-cloud app on GCP must check **both** the per-region GPU quota and the
> global `GPUS_ALL_REGIONS`; the lower binds. (2) A GPU quota request can hard-fail
> on account standing regardless of how well-formed it is — budget 2+ days or use a
> no-quota provider. (3) For a *reference* app, default to the low-onboarding-
> friction provider (RunPod), not the cheapest. See learnings.

**Passing check for Phase 0 (not yet run):** a RunPod pod launches with the Isaac
Sim image and `nvidia-smi` sees the L4 inside it. Until then every technical fact
below sourced from docs is **tentative**.

---

## 4. Phased plan

**Phase 0 — Compute foundation (RunPod; billing step is the user's):**
1. Create a RunPod account + add ~$10 credit. *(no quota gate — minutes, not days)*
2. Launch an **L4 24 GB pod** with the **Isaac Sim NGC container** as the image (exact image tag verified at provision time). Confirm `nvidia-smi` sees the L4.
3. Cost control: rely on RunPod's per-second billing + idle-timeout / manual stop (no systemd guard needed — the GCP auto-shutdown design is moot here).
4. Clone Isaac Lab, `./isaaclab.sh --install` on top of the container's Isaac Sim. **Verify the current Isaac Sim ↔ Isaac Lab supported-version pairing against the install docs at provision time** — do not pin a version from this brief (skill directive; as of 2026-07-10 the skill cites Isaac Sim 5.1.0 / Isaac Lab v3.0.0-beta2, which may have moved).
5. **Gate check:** `list_envs.py` shows the Go2 task AND a short headless Cartpole train (`--max_iterations ~50`) completes → proves GPU → sim → train before touching Go2.

**Phase 1 — Go2 flat locomotion (the deliverable):** train
`Isaac-Velocity-Flat-Unitree-Go2-v0` with `rsl_rl` PPO (~20–40 min); export
`--video` rollouts + TensorBoard curves; `play.py` the checkpoint → walking-Go2
MP4. Watch from the Mac via TensorBoard over an SSH tunnel and the exported MP4s
(optionally Isaac Sim WebRTC for a live GUI).

**Phase 2 — Repo integration ("done" bar):** build `apps/go2-locomotion/` from the
`vla-trial` skeleton — `config.py` (single source: task id, num_envs, iterations,
seed; smoke vs. full profiles), `Makefile`, this brief, README. **Remote-GPU
`make smoke`** (§5). Add the **REGISTRY.md card** and update learnings — **same
commit as the app** (repo rule).

**Phase 3 — later / optional:** rough terrain; policy export (ONNX/TorchScript,
already free from `rsl_rl` `play.py`); sim-to-real notes; live demo under
robium.ai/demos (needs a GPU backend — different infra from the existing Cloud-Run
scale-to-zero demos).

---

## 5. Smoke-test design (remote-GPU — new pattern for this repo)

The pass bar cannot run on the Mac. Design:

- **What it proves (mechanics, not policy quality):** a short Go2 train
  (`--headless`, low `--num_envs`, `--max_iterations` in the tens) on the L4
  completes with exit code 0 and writes a checkpoint under
  `logs/rsl_rl/<task>/<run>/`. Mirrors `vla-trial`'s "pipe-test proves the loop,
  not the score" split — a smoke-scale checkpoint will NOT walk well, and that is
  the correct result.
- **Where it runs:** on the RunPod pod. From the Mac, `make smoke` is a thin
  wrapper that SSHes to the (running) pod and invokes the remote train + a
  checkpoint-exists assertion, or the test is executed on the pod directly. Exact
  seam decided in Phase 2 — the constraint is that it must **not** silently pass
  when there is no GPU (no fake-local fallback).
- **Two run profiles in `config.py`** (the `vla-trial` pattern): a cheap
  **smoke profile** (tiny num_envs / iterations, the pass-bar run) and the **full
  profile** (thousands of envs, full iterations, the real ~20–40 min walking
  policy). Makefile targets and tests both build invocations from these constants
  so a hand-run stage and the pass-bar run cannot drift.
- **Cost honesty:** the smoke run bills GPU time (per-second on RunPod). Keep it
  short; stop the pod when idle.

_(Exact `num_envs` / `max_iterations` numbers: pending — measured against real L4
throughput once the pod exists, then pinned in `config.py` with a comment.)_

---

## 6. Open decisions (confirm before the phase that needs them)

1. ~~Install path — pip vs. NGC container~~ **RESOLVED (2026-07-27):** on RunPod,
   boot the **Isaac Sim NGC container as the pod image** (the container ships the
   CUDA/Omniverse stack, so it's *easier* than pip here), then Isaac Lab from source
   on top. Exact image tag + version pairing verified at Phase 0.
2. **Smoke seam** — SSH-wrapper from Mac vs. run-on-pod (§5). Decide in Phase 2.
3. **GPU choice on RunPod** — L4 24 GB (parity with the plan) vs. a faster 24 GB
   card (RTX 4090 / A10) at similar $/hr. Default L4; revisit if throughput is tight.

---

## 7. Cost envelope

RunPod L4 ≈ **$0.39/hr running** (per-second billing); pod storage billed while the
pod exists (stopped or running) — **delete the pod, not just stop it, when done** to
stop storage charges. Whole Go2 job ≈ **$2–6** of GPU time (setup + gate check +
~20–40 min train + iteration + smoke). **Stopping/deleting the pod when idle is what
keeps this cheap** — no systemd guard needed (that was the GCP design).
*(GCP reference, if that path is ever taken for the Phase-3 demo: L4 spot
≈$0.20–0.30/hr + $4–17/mo persistent disk until deleted.)*

## 8. Out of scope

The parked **VLA bake-off** (`apps/vla-bakeoff`, future: SmolVLA vs π0.5 vs OpenVLA
on LIBERO) is a *separate* app centered on Hugging Face + LeRobot, not Isaac. See
`HANDOFF.md` §7. Do not build it here.

## 9. Results (2026-07-27, RunPod L4)

Verified end-to-end. Environment: `nvcr.io/nvidia/isaac-lab:3.0.0-beta2-post1`,
NVIDIA L4 (driver 580.159.04, 23 GB), Python 3.12, Isaac Lab at
`/workspace/isaaclab`.

- **Gate check ✓** — `list_envs.py` confirms `Isaac-Velocity-Flat-Unitree-Go2-v0`
  (#106, `UnitreeGo2FlatEnvCfg`); a 32-env/10-iter smoke train wrote
  `model_0.pt`/`model_9.pt` in 8 s → proves GPU → sim → train → checkpoint.
- **Full walking policy ✓** — 4096 envs, 2000 iters, seed 42, `agent.save_interval=100`
  → **32.3 min** (`Training time: 1937.53 s`). Mean reward **−0.5 → +36** (crosses
  positive by ~iter 90, converged by ~iter 300); mean episode length reaches the
  **1000-step max (never falls)**; velocity-tracking error `xy` 0.85 → 0.09.
  21 checkpoints saved; policy exported to `exported/policy.pt` (JIT) + `policy.onnx`.
- **Videos** — `play.py --video` rollouts rendered from checkpoints (iter 0 → 1999);
  a clickable reward-vs-iteration dashboard with inline checkpoint clips:
  <https://claude.ai/code/artifact/1661f6a2-c375-4975-9a90-0561517272d7>.
- **Live control panel ✓** — real-time velocity-command joystick (sliders + WASD/arrows
  + hot-swappable checkpoints), MJPEG-streamed at ~13 fps over the RunPod proxy. See
  `docs/live-demo.md` and `scripts/live_demo_patch.py`.
- **Artifacts** — checkpoints + exported policy + videos preserved (see the app's
  `outputs/` locally; git-ignored). Pod terminated after capture.
- **Cost** — ~4–5 GPU-hours all-in (training + iteration + the live demo + the
  provisioning saga) ≈ **$1.50–2** of L4 time.

## 10. Battle scars

Full detail (verbatim errors, dead-ends, passing checks) is in
`learnings/2026-07-26-isaac-go2.md`; this is the index.

1. **GCP GPU quota is a hard gate for new projects** — the real blocker is the
   *global* `GPUS_ALL_REGIONS = 0`, not the per-region L4 quota; and a well-formed
   increase request is **auto-denied** on a young project (Google: "wait 48h or
   more billing history"). Drove the switch to RunPod (§3).
- **For a reference app, default to a low-onboarding-friction GPU provider** — the
  whole job is ~$2 on any provider, so ease beats the cheapest $/hr.
2. **RunPod + a custom NVIDIA image: don't install sshd** — the proxy SSH
   `docker exec`s in, so it only needs (a) your key on the *account* and (b) the
   container simply *running* (`dockerEntrypoint:["/bin/sleep"]`, `["infinity"]`).
   "start container: begin" with no "success" is a silent `sleep`, **not** a hang —
   don't terminate over it.
3. **The prebuilt `nvcr.io/nvidia/isaac-lab` image bundles a matched Isaac Sim** —
   no version-pairing dance; query exact tags via the nvcr.io registry API.
4. **Stopping a SECURE pod releases its GPU** — it may not restart if the host
   fills up. Set the right config at *create* time; never stop/start mid-run.
5. **Live streaming: MJPEG, not polling** — see `docs/live-demo.md`.
