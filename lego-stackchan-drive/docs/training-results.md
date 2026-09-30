# First road-following ACT experiment

Training completed successfully. Validation selected the 5,000-step ACT
checkpoint; the run stopped at 10,000 steps after five checks without improvement.
The final downloaded weights match the checkpoint evaluated on all 856 held-out
frames on the Mac. Autonomous road-following behavior has not yet been verified.

## Data

The experiment uses 4,079 image/action pairs from 16 saved driving clips,
approximately 6.8 minutes at 10 FPS. The two initial button tests are excluded.
Thirteen complete source clips (3,223 frames) train the policy; three complete
clips (856 frames) are held out. A 250 ms capture gap splits one training clip
into two learning segments without discarding frames or crossing the split.

The raw JPEGs, episode metadata, and event logs remain unchanged. SHA-256 checks
passed for all 4,079 images and all 16 pairs of episode/event files. Exported
RGB images are stored losslessly; original timestamps and hashes are retained
in `.local/training/road-v1/manifest.json`.

The private datasets are
[train](https://huggingface.co/datasets/robium-admin/lego-stackchan-road-v1-train)
and [validation](https://huggingface.co/datasets/robium-admin/lego-stackchan-road-v1-val).

## Policy and GPU test

Image-only ACT predicts normalized throttle and steering from the 320×240 image.
It sees no previous action or measured robot state. The 10-action prediction
chunk is configured to use one action per new observation. Future targets stay
within each contiguous episode, with padding masked from loss/evaluation.
LeRobot 0.6.1 and the full dependency environment are pinned in `training/uv.lock`.

The [200-step L4 test](https://huggingface.co/jobs/robium-admin/6ab82ce56b030d633f696539)
completed, saved weights and normalization processors, and reproduced its
predictions after reload. On all 856 validation frames:

| Measure | Throttle MAE | Steering MAE |
| --- | ---: | ---: |
| ACT, correct images | 0.0185 | 0.2054 |
| Constant training-mean action | 0.0689 | 0.4893 |
| ACT, shuffled images | 0.0184 | 0.5482 |

Errors are in normalized joystick units. Worse steering with shuffled images
supports image dependence. The same checkpoint runs on the Mac M5 using MPS;
the 25-forward-pass timing probe measured a 9.94 ms median and 17.32 ms p95
(five warmup passes excluded). This excludes camera/network/control latency.

Artifacts are under `.local/training/road-v1/cloud-smoke/` and
`.local/training/road-v1/cloud-smoke-check/`. The private checkpoint repository is
[lego-stackchan-road-v1-act](https://huggingface.co/robium-admin/lego-stackchan-road-v1-act).

## Full run

The [L4 training job](https://huggingface.co/jobs/robium-admin/6ab82e026b030d633f69657c)
completed after 44 minutes, using batch 8 and full held-out validation every
1,000 steps. The best checkpoint was selected by mean first-action MAE and
reproduced its results after reload. Peak allocated GPU memory was 1.18 GB.

| Final measure (856 held-out frames) | Throttle MAE | Steering MAE |
| --- | ---: | ---: |
| ACT, correct images (GPU) | 0.0090 | 0.1519 |
| Constant training-mean action | 0.0689 | 0.4893 |
| ACT, shuffled images (GPU) | 0.0090 | 0.5410 |
| ACT, correct images (Mac MPS) | 0.0090 | 0.1518 |

Steering MAE is 69% below the constant-action baseline. Mac inference measured
8.58 ms median and 10.24 ms p95, excluding camera/transport latency. The Mac's
95th-percentile absolute steering error is 0.865 and its maximum is 1.033;
occasional large transition errors remain. Maximum raw range overshoot was
0.0206 for throttle and 0.0463 for steering.

The final checkpoint is
`.local/training/road-v1/cloud-train/runs/train/checkpoints/step-005000/`.
Reports, prediction plots, and file-hash verification are in
`.local/training/road-v1/final-mac-evaluation/`. The full training metrics log is
in `.local/training/road-v1/cloud-train/runs/train/metrics.jsonl`.

Both GPU jobs completed and the queued L40S job is canceled. Estimated compute
cost from recorded job runtimes and submitted rates is $0.63; this is an estimate,
not a billing receipt. The conservative timeout reservation ceiling remains
$3.85, within the authorized $10 budget. All datasets and checkpoints are private.

The app's 82 checks pass. Real evidence additionally includes the exported image/
action round-trip, all 17 segment-end padding masks, finite full-clip predictions,
GPU reload verification, Mac offline reload, and matching final checkpoint hashes.

## What this evidence covers

This evaluates imitation on held-out clips from the same demonstrated circuit
and direction. It does not establish autonomous physical road following or
recovery from leaving the demonstrated path. Over 98% of held-out throttle labels
are full forward; the data provides little evidence for learning when to slow
or stop. Predictions can slightly exceed normalized limits, so later deployment
must clamp them through the existing motor mapping.

## Live inference preflight

The app now supports `./app run --policy`: hold R1 for model control, release
R1 or move a driving stick for manual takeover. Each R1 hold is bounded to
20 seconds for the first track trials. Model inference runs in a separate
process using the saved processors and verified step-5000 weights. It uses
only the first action for each new latest image and clamps both normalized
outputs before applying the existing T75/S25 motor mapping.

On September 26, the actual Stack Chan stream at 320×240, 10 FPS, Q85 produced
100 predictions over a ten-second observation window. The trailing inference
rate was 9.72 Hz. JPEG decoding plus model inference measured 15.9 ms median
and 22.1 ms p95; this excludes camera/network and BLE latency. This test used
video-only workers and sent no motor or head commands. The captured view shows
the demonstrated black-tape circuit. The paired Stadia controller was detected
with neutral sticks and R1 released.

All 95 app checks pass, including immediate manual takeover, release,
prediction expiry, stream mismatch, invalid outputs, and trial time limits.
The local inference subprocess also passed immediate shutdown cleanup.
After temporary USB provisioning restored direct Wi-Fi, the running trial
window confirmed startup centering and the direct LEGO READY/zero-power PONG
handshake. Its readiness snapshot contains 489 live predictions, 349 zero-power
BLE commands, recent inference at 10.0 Hz, and no model faults. The latest
ten-second inference window measured 14.92 ms median and 17.85 ms p95.
The hub heartbeat was 132 ms old. This establishes live readiness; physical
road-following behavior remains unverified until the operator holds R1 on the
track. Trial clips are stored in `.local/policy-trials/`, separate from the
expert demonstrations. The readiness snapshot and runtime log are under
`.local/policy-runs/20260926-144031-d4d49163/`.

The first operator trial sent model-driven motor commands, but exposed an
overly tight 250 ms capture-age limit. Predictions were already about 210 ms
old when available; the next image arrives about 100 ms later. The resulting
expiry inserted zero commands between healthy predictions, despite no model
faults and uninterrupted LEGO heartbeats. The limit is now 500 ms, including
acquisition/encoding and inference latency. A replay of the observed trial at
120 Hz produced 1,435 expiry stops and 397 mode transitions with the old limit,
and zero expiry stops/transitions with the new limit. This replay covers timing,
not road-following success; release, manual takeover, stream mismatch, and
stalled-image expiry remain enforced.

After restart, a 15-second check of the live prediction stream produced 1,327
model-eligible checks with zero capture-age expirations (maximum age 319 ms).
The operator also held R1 during this run: the observed motor trace contains
368 model commands, all nonzero, with zero freshness-stop transitions, model
faults, or hub-busy events. These checks establish removal of the command pauses;
they do not measure lap completion or road-following accuracy. Evidence is in
`.local/policy-runs/20260926-144419-943f7e98/expiry-fix-live-check.json` and
`expiry-fix-motor-check.json`. All 96 app checks pass.

## Later filmed black-tape iteration

On September 27, the team gathered more demonstrations after changing the
camera pose. Two new ACT models trained from scratch were evaluated on the same
943 held-out frames at a 20° camera angle:

| Model | Training frames | Best step | Throttle MAE | Steering MAE | Mean action MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| New 20° data only | 3,378 | 4,000 | 0.2398 | 0.3954 | 0.3176 |
| New 20° plus earlier same-day 0° black-tape data | 7,037 | 9,000 | 0.2413 | 0.3898 | 0.3156 |

These are offline errors on a different held-out set from the first road-v1
experiment. The small difference does not establish a better physical policy.
The operator reported successful supervised laps during filming, but the saved
session records do not identify which of these checkpoints produced each lap.
The [finished video](https://www.youtube.com/watch?v=_1pQTt8gqZM) shows the
project on its filmed track; it is not a measured success rate or a test of
unseen tracks and lighting. Local comparison details remain in
`.local/training/tape-comparison-20260927/results.md`.
