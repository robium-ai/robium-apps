---
title: Teaching Stack Chan to drive with LEGO, Pybricks, and Robium
summary: We recorded camera views and joystick commands, trained an ACT policy on Hugging Face, and tested it on a real LEGO car.
collection: blog
category: tutorial
kind: tutorial
voice: product-lab
author: Robium team
audience: robotics-developer
level: intermediate
app: lego-stackchan-drive
date: 2026-09-30
tested: 2026-09-27
tags: [robium, stackchan, lego, pybricks, imitation-learning, lerobot, hugging-face, act]
hero: assets/social/stackchan-video-cover.png
hero_alt: Video cover showing Stack Chan mounted on a LEGO Technic car beside the Robium name
social_image: assets/social/stackchan-video-cover.png
featured: false
---

Stack Chan wanted to drive. We put its camera and expressive head on a LEGO
Technic car, drew a track, and taught it from a handful of human-driven runs.
The result is a small, physical imitation-learning project: the robot sees the
route through its own camera, while a policy predicts steering and speed. The
film shows the build, the mistakes, and the supervised track trials.

<div style="width:100%;aspect-ratio:16/9;margin:1.5rem 0 2rem">
  <iframe title="Stack Chan learns to drive with Robium" src="https://www.youtube-nocookie.com/embed/_1pQTt8gqZM" style="width:100%;height:100%;border:0" loading="lazy" referrerpolicy="strict-origin-when-cross-origin" allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share" allowfullscreen></iframe>
</div>

[Watch on YouTube](https://www.youtube.com/watch?v=_1pQTt8gqZM) if the player
does not load.

## One robot, three jobs

The M5Stack Stack Chan K151 supplies 320×240 camera frames over Wi-Fi, plus
its face, head movement, and speaker. A LEGO hub running
[Pybricks](https://pybricks.com/) drives two motors on ports D and B. A Mac
receives the camera stream, reads a gamepad, and sends bounded motor commands
over Bluetooth LE. The Mac also saves each image with the joystick action that
was current when the image was captured.

The learned controller runs on the Mac, not on Stack Chan's microcontroller.
It uses [LeRobot](https://github.com/huggingface/lerobot)'s Action Chunking
Transformer (ACT) to predict throttle and steering from each camera image.
Although ACT predicts a short action chunk, the driver applies only its first
action and observes a fresh frame before asking again. A one-second watchdog
in the hub brakes the motors if commands stop arriving.

## From demonstrations to a driving policy

1. **Build and check the hardware.** Install the app's locked Python runtime,
   load the documented Pybricks hub program, and configure Stack Chan's camera
   firmware and Wi-Fi. `./app probe` checks the camera and stopped hub with zero
   motor power before a driving session.
2. **Drive and record.** Open `./app run`, steer the car with a controller or
   keyboard, and hold a recording trigger for each demonstration. The capture
   pairs camera images with throttle and steering samples. We rejected
   unsuccessful clips and kept whole runs together when splitting the data.
3. **Prepare and train.** `./app training prepare` exports the accepted runs as
   LeRobot datasets. We used private Hugging Face dataset repositories and an
   L4 GPU job: a 200-step smoke run first, then full ACT training with
   validation every 1,000 steps. `./app training fetch --stage train` brought
   the selected weights back to the Mac for offline evaluation.
4. **Try it on the track.** `./app run --policy` loads the local checkpoint.
   Hold R1 or Space for policy control; release it or move a driving stick to
   take over. Each hold is limited to 20 seconds. The operator remains beside
   the robot during the trial.

The [app README](https://github.com/robium-ai/robium-apps/tree/main/lego-stackchan-drive)
has the firmware, Wi-Fi, safety, capture, and training commands. The datasets
and checkpoints from this experiment are private, so reproducing the training
run requires collecting your own demonstrations and using your own Hugging Face
account.

## What the runs told us

Our first dataset contained **4,079 image/action pairs** from 16 saved clips.
Thirteen clips trained the policy; three complete clips, or 856 frames, were
held out. The L4 job selected its 5,000-step checkpoint and stopped at 10,000
steps when validation stopped improving. On those held-out frames, steering
mean absolute error was **0.1519** in normalized joystick units, compared with
**0.4893** for a constant-action baseline. Shuffling the images raised the
policy's steering error to **0.5410**, evidence that it used the visual input.

The filmed black-tape work then changed the camera angle and collected more
examples. Two fresh models trained from those later recordings scored **0.3176**
and **0.3156** mean action error on the same 943 held-out frames. Those figures
are from a different dataset and cannot be compared directly with the first
run's steering-only number. The team observed successful supervised laps, but
the saved records do not identify which later checkpoint produced each filmed
lap. The video is a demonstration on the shown track, not a measured success
rate or a claim about new tracks and lighting.

The full [training record](https://github.com/robium-ai/robium-apps/blob/main/lego-stackchan-drive/docs/training-results.md)
includes the first run's split, baselines, Mac inference checks, and limits.

## Keep building with Stack Chan

Robium also has a [Stack Chan ER2 companion](https://github.com/robium-ai/robium-apps/tree/main/stackchan-er2)
that uses voice, vision, and guarded robot actions, and a
[browser-backed Stack Chan simulator](https://github.com/robium-ai/robium-apps/tree/main/stackchan-er2-sim)
for trying its face and voice loop without hardware. The
[LEGO Powered Up teleoperation app](https://github.com/robium-ai/robium-apps/tree/main/lego-powered-up-teleop)
is a smaller starting point for the Pybricks motor path. The driving app joins
those pieces with data collection and a learned policy, and keeps its source and
setup notes in the [Robium applications library](https://github.com/robium-ai/robium-apps/tree/main/lego-stackchan-drive).
