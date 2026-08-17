# Polish playbook — validate & polish each public app

One agent per app, each in its own worktree on a `polish/<app-name>` branch.
The goal per app: **validated** (real smoke pass, no drift) and **polished**
(public-ready docs, generic naming, no stale paths, no secrets) so the human
can publish it confidently in the public robium-apps repo.

`robot-navigation` completed this pass on 2026-08-03 — use it as the
reference for what done looks like (its README is the template for yours).

## The checklist (run in order)

1. **Validate first, before touching anything.** Run the app's smoke bar
   exactly as its REGISTRY.md card states. If it fails, fix forward (the fix
   is part of the polish) and note the drift cause in your final report.
2. **Internal rename.** The directory was already renamed; finish the job
   inside it. Rename the snake_case package/module and every reference
   (pyproject/setup/package.xml, imports, Makefile, Dockerfiles, compose,
   tests, scripts, docs). Rename map:

   | App | Old snake_case | New snake_case |
   | --- | --- | --- |
   | imitation-manipulation | `manip_trial` | `imitation_manipulation` |
   | vla-pick-and-place | `vla_trial` | `vla_pick_and_place` |
   | quadruped-locomotion | `go2_locomotion` | `quadruped_locomotion` |
   | robot-teleoperation | (uses `tb4`/`tb4_teleop` strings) | `robot_teleoperation` / keep `tb4` where it names the physical robot |

   Exceptions (rule 5 in CLAUDE.md): Cloud Run/demo image names, robium.ai
   routes, dated learnings/spec filenames, and upstream names (the robot IS a
   TurtleBot 4; the task IS Isaac-Velocity-Flat-Unitree-**Go2**-v0 — keep
   real-world names where renaming would lie). Foxglove layout JSON files in
   your app: rename to `<app-name>-layout.json`.
3. **Re-verify.** Re-run the smoke bar after the rename. This is what
   promotes your rename from "sed ran" to "verified".
4. **Stale-path sweep.** Grep your app for pre-split paths (`apps/<old>`,
   `robium-applications`, bare `docs/superpowers/` references) — briefs
   written before 2026-08-03 have them. Spec references become "in the
   [robium](https://github.com/robium-ai/robium) repo" links.
5. **Secrets/PII scan.** Grep for keys, tokens, emails, personal names,
   private IPs/hostnames, and robot network details. Anything found:
   remove/generalize, and flag it loudly in your report (it may also live in
   git history — the human decides on history).
6. **Public README rewrite.** Follow robot-navigation/README.md's shape:
   title = capability, one-paragraph plain-language intro (assume the reader
   has never heard of the stack), a `**Stack:**` tag-chip line, What you'll
   see, Prerequisites, Quick start (the make targets), then operator detail.
   Honesty rules from the registry carry over (e.g. vla-pick-and-place's
   "pipeline proven, checkpoint not trained to success" must stay prominent).
7. **REGISTRY.md card.** Update your app's card + quick-index row ONLY:
   new names, `verified` date = your re-verified smoke date (or unchanged if
   you could not run the real bar — say so in the card).
8. **Report.** Final message: what was verified (with the actual pass
   output), what wasn't and why, drift found, anything flagged. Commit(s) on
   your branch, never push.

## Per-app status & specifics

### robot-navigation — DONE 2026-08-03 (reference example)
Cold-build smoke pass + post-rename smoke pass. Internal rename complete
(`nav_trial_bringup` → `robot_nav_bringup`). Public README done.

### imitation-manipulation — needs the pass
- Bar: `make smoke` (uv + MPS native, ~40 s warm) and `make demo-smoke`
  (Docker demo gateway). Host dep: `brew install ffmpeg`.
- Rename surface: `src/manip_trial/` package, pyproject, Makefile, demo
  Dockerfile, tests. Grep `manip_trial|manip-trial`.
- Watch: the demo image bakes artifacts from local outputs; if `outputs/`
  is empty you must run `make train-baseline` first (~15 min) — see card.

### vla-pick-and-place — needs the pass
- Bar: `make smoke` (pipeline mechanics) + `make oracle` (10/10 scripted IK
  canary). uv + MPS native, `MUJOCO_GL=cgl`. `make demo-smoke` for the demo.
- Rename surface: `src/vla_trial/` package, pyproject, Makefile, both
  Dockerfiles, tests, scripts. Grep `vla_trial|vla-trial`.
- Honesty: no checkpoint has been trained to success (deliberate cost
  deferral). This stays front-and-center in README + card. Do NOT run
  `make train-full` (it costs $20-40) without the human asking.
- Watch: `.gitignore` negation trap around `scene_pick.xml` (tracked file
  inside a bulk-ignored vendored asset dir) — don't "clean it up".

### quadruped-locomotion — needs the pass (GPU-limited)
- Bar: remote-GPU `make smoke` on a RunPod L4 pod — costs money; do NOT
  provision a pod unless the human asked. Without a pod: run Mac-side
  `make test` (config guards) and mark the card "rename verified by
  `make test` only; GPU smoke pending".
- Rename surface: `src/go2_locomotion/` package, pyproject, Makefile, tests,
  docs, `HANDOFF.md`. Keep `Go2`/`go2` where it names the Unitree robot or
  the Isaac Lab task id. Grep `go2_locomotion|go2-locomotion`.

### robot-teleoperation — needs the pass (hardware-limited)
- Bar: `make smoke` is hardware-in-the-loop (robot reachable over Wi-Fi).
  Without the robot: run the orin/ JS tests (`orin/tests/`), shellcheck the
  scripts, and mark the card "docs/rename pass; HIL smoke pending".
- Rename surface: mostly docs + `foxglove/tb4-teleop-layout.json` →
  `robot-teleoperation-layout.json` (update README import instructions).
  Keep `tb4`/TurtleBot 4 wherever it names the actual robot or its
  services (`tb4-base-watchdog.service` runs ON the robot — renaming it
  here without redeploying to the robot would lie; leave it, note it).
- Review `TODO.md`: fold still-relevant items into the README's roadmap
  ("Phases" section), delete the file if nothing survives.

## Merge notes (for the human)

Branches touch disjoint app dirs; the only shared file is REGISTRY.md.
Merge order doesn't matter — each agent edited only its own card and index
row, so conflicts, if any, are trivial. After all merges: one integration
check (`grep -ri "trial" --exclude-dir=.git .` should hit only historical
references and REGISTRY "formerly" notes).
