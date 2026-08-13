# AGENTS.md

Canonical repository guidance for Codex, Claude Code, and other coding agents.

**robium-apps** is the canonical application library and public showcase for
robotics examples built with the [robium](https://github.com/robium-ai/robium)
plugin. Apps are developed, validated, and published here. There is no second
applications repository and no promotion-copy workflow.

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

For feature work in this repository, present one rough design or plan for
approval. After the maintainer approves that direction, proceed through
implementation and verification without additional conversational approval
gates. Prefer delivering working software that the maintainer can try, then
iterate from concrete feedback. Pause only when a missing choice would
materially change the result, the scope needs to expand, or safety/external
authority requires confirmation.

## Parallel work isolation (permanent policy)

One app per agent, each in its own worktree/branch (`promote/<app-name>`):

- **Write surface = your app's directory + its README/REGISTRY entries.**
  Shared infrastructure changes must be explicitly in scope.
- Learnings from any work here go to the robium repo as per-app files:
  `learnings/YYYY-MM-DD-<app>.md` — never a shared dated file.
- The human reviews public-facing changes before release.
