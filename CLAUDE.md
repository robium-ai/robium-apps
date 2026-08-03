# CLAUDE.md

**robium-apps** is the public showcase of polished robotics example
applications built with the [robium](https://github.com/robium-ai/robium)
plugin. Apps are developed and iterated in the private robium-internal-apps
repo and arrive here only by **promotion**: one validated, polished app per
single clean commit. This repo has no messy history and must stay that way.

## Promotion rules

1. A promotion commit contains exactly: the app's directory (copied from the
   internal repo at its validated state) + this repo's README apps index
   updated with the app's row. Nothing else.
2. Promote only apps whose internal polish pass is complete: real smoke pass
   on the real platform, internal names renamed, stale paths fixed,
   secrets/PII sweep clean, public-facing README (indoor-navigation's README
   is the shape). The human verifies before the commit lands.
3. Never copy internal-only files: REGISTRY.md cards, HANDOFF/TODO files,
   deploy configs that require robium credentials stay internal unless the
   app's README explicitly marks them as maintainer-only.
4. Re-promotion (updating an already-public app) is the same: one commit,
   copied from a re-validated internal state.

## Parallel work isolation (permanent policy)

One app per agent, each in its own worktree/branch (`promote/<app-name>`):

- **Write surface = your app's directory + your row in the README apps
  index.** Never other apps, never shared/root files beyond that row.
- Learnings from any work here go to the robium repo as per-app files:
  `learnings/YYYY-MM-DD-<app>.md` — never a shared dated file.
- **Never push.** The human reviews, merges, and pushes — this repo is
  public-facing; nothing lands without human review.
