# Go2 joystick control

Robot Zoo's personal copy now uses an existing, published walking policy on CPU.
It does not train a policy, teleport the base, or synthesize a gait from sine waves.

## Sources and reproduction

- Hardware API: [Unitree SDK2 Python SportClient](https://github.com/unitreerobotics/unitree_sdk2_python/blob/master/unitree_sdk2py/go2/sport/sport_client.py)
  provides `Move(vx, vy, vyaw)`, `StopMove`, `StandUp`, and `BodyHeight`.
  These call the physical robot's onboard controller; importing the SDK alone
  does not install that controller into MuJoCo.
- [Unitree MuJoCo](https://github.com/unitreerobotics/unitree_mujoco)
  provides a simulator and low-level SDK communication. It is not used here as
  an implementation of SportClient locomotion.
- Simulation locomotion: [wty-yy/go2_rl_gym](https://github.com/wty-yy/go2_rl_gym),
  pinned at `30e74dc507bec7a642a8c98be26081f2c6f0822d`.
  The adapter follows `deploy/deploy_mujoco/deploy_go2.py` and its `configs/go2.yaml`:
  45 observations, 12 joint actions, 50 Hz inference, 500 Hz physics,
  action scale 0.25, kp 20, kd 0.5, and the export's internal observation history.
- Checkpoint: `go2_moe_cts_high_slope_thre_164k_0.6715.pt` (5,208,824 bytes).
  SHA-256: `9d9ad783a1017b6eced5984eb95279cc5b36db8cc84d21e646f46ba2a8023d9d`.
  Downloaded from the pinned revision and verified before TorchScript loading.
  Cached in `~/.cache/robot-zoo/<revision>/`; `./app build` prefetches it.
- The existing Menagerie Go2 asset remains pinned by `mujoco-menagerie==2026.9.0`.
  The in-memory model uses the policy deployment model's joint damping 0.001,
  friction loss 0.1, and calf torque limit ±35.55 Nm. The asset files are unchanged.
  Retaining Menagerie's default joint damping 2 caused poor velocity tracking.
- Stationary posture endpoints come from Unitree's
  [Go2 FixStand configuration](https://github.com/unitreerobotics/unitree_rl_mjlab/blob/1425b15f73bd4095f0df53709d7c389c3eb9e790/deploy/robots/go2/config/config.yaml):
  per-leg `[0, .8, -1.5]` standing and `[0, 1.36, -2.65]` folded.
  Low profile is 60% of the way toward folded; high profile is standing.
  A 1.2-second smooth transition follows 0.8 seconds of zero-command settling.
  This reuses joint posture control; it is not height-conditioned walking.
- The upstream MIT/BSD notices are retained in
  `src/robot_zoo/GO2_POLICY_LICENSE.txt`.

The earlier CTS 150k checkpoint failed lateral-motion probes with this model;
only the newer MoE checkpoint is used. No ROS, DDS, GPU, or physical-robot
network interface is opened.

## Controls

| Input | Behavior |
| --- | --- |
| Left stick up/down | Forward/backward |
| Left stick left/right | Strafe left/right |
| Right stick left/right | Turn left/right |
| Right stick up/down | Unassigned |
| D-pad | Slow forward/backward/strafe (35% stick deflection) |
| A | Stand / resume normal walking controller at rest |
| B | Stop; gamepad must return to neutral before moving again |
| X / Y | Low / high stationary profile |
| W/S, A/D, Q/E | Forward/backward, strafe, turn |
| R / F | High / low profile |
| Space | Stop |

Stick deflection scales speed. At full speed the command limits are 0.5 m/s
forward/backward, 0.35 m/s lateral, and 0.8 rad/s yaw; the speed slider scales
all three. Diagonal translation is normalized. Gamepad axes have a rescaled
15% dead zone. A physical velocity is a target, not an exact measured speed.

Low/high posture stops walking. A new movement input resumes the policy's
trained walking height. The policy has only three velocity commands and no
height-conditioning input. Variable-height walking remains unsupported.

## Input lifecycle

The two circular controls support simultaneous touch pointers, mouse drag, and
keyboard control. Release and pointer cancellation recenter the controls.
Manual controls take priority over a gamepad, including when a screen stick is
centered. After releasing a screen stick or keyboard movement, center the
physical sticks before gamepad motion resumes. The panel shows whether a pad
is detected, waiting for neutral, or ready. Stadia is preferred when multiple
standard-mapped pads are present.

Standard-mapped Stadia USB or already-paired Bluetooth gamepads use the browser's
Gamepad API. Click **Enable gamepad**, then center both sticks and release all
buttons. Unmapped controllers are reported rather than guessing their axes.

Keep the controller window focused. Blur, hiding the page, disconnect, and Stop
clear inputs. A single in-flight request prevents a command backlog. The
simulation manager also zeros all three axes when input is stale for 500 ms,
independent of the browser's cleanup. These are simulation controls, not a
hardware emergency-stop system.

Physical Stadia hardware has not been verified in this session. WebKit/OS
mapping availability may vary; the same local controller URL printed by the
app can be opened in Chrome if the native webview does not recognize a pad.

## Verification

`./app smoke` covers the launcher, bridge, invalid/stale input rejection,
all six locomotion directions, stopping, posture changes from walking, and
resuming locomotion from low posture. Tests measure physical base displacement,
yaw, height and uprightness rather than just checking joint targets.
`node --test tests/test_input_mapping.cjs` checks gamepad and input lifecycle
behavior without requiring a physical controller.


A further 56-second MuJoCo probe exercised diagonal translation with turning,
full lateral motion with turning, abrupt reversals, and stops at maximum slider
speed. The robot remained upright throughout (minimum base height 0.270 m;
minimum body vertical alignment 0.990). This is bounded flat-ground simulation
evidence; it does not establish terrain performance or physical hardware support.
