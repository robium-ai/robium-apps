# AGENTS.md

Canonical repository guidance for Codex, Claude Code, and other coding agents.

**robium-apps** is the canonical application library and public showcase for
robotics examples built with the [robium](https://github.com/robium-ai/robium)
plugin. Apps are developed, validated, and published here. There is no second
applications repository and no promotion-copy workflow.

## Sibling repositories

Robium is checked out as siblings inside a `robium-workspace` parent. Change
things in the repository that owns them and cross-reference rather than
duplicate.

- `../robium` owns the skills plugin, the `robium-ai` CLI, and the learning
  engine. Learnings from work here go there as `learnings/YYYY-MM-DD-<app>.md`.
- `../my-apps` is the user's own application library, when present. Their
  apps go there, not here: building here leaves this checkout dirty and
  `npx robium-ai update` then refuses it.
- `../robium-website` owns the robium.ai site and the live-demo orchestrator.
  It reads this repository by relative path at build time (overridable with
  `ROBIUM_APPS_DIR`), so app metadata and `REGISTRY.md` cards feed the site
  directly — keep them accurate rather than editing the site to compensate.

## Application rules

1. One app lives in one top-level `<name>/` directory with its own environment,
   tests, README, and `docs/architecture-brief.md`.
2. An app change is not done until its real-platform smoke test passes and its
   README and `REGISTRY.md` card are updated in the same commit.
3. Keep secrets, credentials, personal data, and ephemeral handoff/TODO files
   out of the repository. Maintainer deployment configuration must use named
   secret stores or environment variables.
4. Preserve the reference-library role: if an existing app resembles new work,
   bootstrap from its structure, environment, and test shape before diverging.

## Maintainer collaboration preference

An explicit bounded change request authorizes implementation after inspecting
the affected app; do not announce a process classification or ask for duplicate
approval. For a new app or material architecture change, present one rough
direction for approval, then proceed through implementation and verification
without additional conversational gates. Prefer the cheapest risk-reducing
probe and working software the maintainer can try. Pause only when a missing
choice materially changes the result, scope must expand, or safety/external
authority requires confirmation.

## Parallel work isolation

When agents work concurrently, isolate one app per agent in its own
worktree/branch (`promote/<app-name>`). Solo maintainer-authorized work may land
directly on local `main` when explicitly requested; that does not authorize a
push or release.

For concurrent work:

- **Write surface = your app's directory + its README/REGISTRY entries.**
  Shared infrastructure changes must be explicitly in scope.
- Learnings from any work here go to the robium repo as per-app files:
  `learnings/YYYY-MM-DD-<app>.md` — never a shared dated file.
- The human reviews public-facing changes before release.
