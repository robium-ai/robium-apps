# Adding a new application

This repo is a curated portfolio, not an examples folder. Every app is a
complete vertical slice: a recognizable problem, a one-command demo, a
smoke test that asserts real behavior, and honest metadata. The full
standard lives in [docs/reference-applications-design.md](docs/reference-applications-design.md);
this page is the short path through it.

## The contract every app ships

- `robium-app.yaml` — the machine-readable contract (schema in the design
  doc, section 5). `robium-ai app validate` must pass.
- A repository-local command surface declared by `robium-app.yaml`. Prefer an
  executable `./app` launcher for new applications; existing Make-based apps
  remain valid. It must expose the app's build/run, diagnosis, smoke/status,
  logging, and teardown operations as applicable.
- `README.md` with a five-minute quick start, tested exactly as written.
- `docs/architecture-brief.md` and `docs/case-study.md` — the case study IS
  the app's public article: frontmatter (title, summary, app, date, hero,
  featured) drives the website's articles pages and frontpage picks, and the
  body is portable markdown for cross-posting. It is a living document;
  revise it as the app evolves. Hero media may start as a placeholder.
- Honest labeling everywhere: simulated, recorded, mocked, and live
  components are never conflated; performance claims state hardware, data,
  scenario, and measurement method.

## Runtime rule of thumb

Pick by what the app touches (design doc, section 3): ROS/sim-heavy apps
are Docker-first; Python/ML apps are uv-first (Docker only when it does not
cost the accelerator); GPU-cloud apps run remote-first with the smoke test
on the GPU; hardware apps document setup in the README and smoke
hardware-in-the-loop.

## Lifecycle

1. **Proposal:** fill the app brief (design doc, section 11): outcome,
   audience, robium value, default scenario, execution modes, success
   criteria, known limitations.
2. **Prototype:** prove the end-to-end path with one reproducible scenario.
3. **Reference-ready:** metadata + verbs + docs complete; the manifest's smoke
   command is green from a clean clone; `robium-ai app validate` is green.
4. **Published:** promoted into this repo as one clean commit (app
   directory + its README index row, nothing else).
5. **Maintained or archived:** archived apps stay runnable and are marked
   `status: archived` rather than rotting silently.

## Scaffolding

Start from the closest shipped app, not from scratch:

```bash
npx robium-ai app new my-app --from robot-navigation
```

Then run the release checklist in the design doc before proposing
promotion. Nothing lands here without a human review.
