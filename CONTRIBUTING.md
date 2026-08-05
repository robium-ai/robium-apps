# Adding a new application

This repo is a curated portfolio, not an examples folder. Every app is a
complete vertical slice: a recognizable problem, a one-command demo, a
smoke test that asserts real behavior, and honest metadata. The full
standard lives in [docs/reference-applications-design.md](docs/reference-applications-design.md);
this page is the short path through it.

## The contract every app ships

- `robium-app.yaml` — the machine-readable contract (schema in the design
  doc, section 5). `robium-ai app validate` must pass.
- A `Makefile` speaking the standard verbs: `build` (when there is
  something to build), `demo` (the default showable experience), `smoke`
  (the pass bar, exits nonzero on failure), `check` (preflight), `down`
  (teardown where applicable).
- `README.md` with a five-minute quick start, tested exactly as written.
- `docs/architecture-brief.md` and, for mature apps, `docs/case-study.md`.
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
3. **Reference-ready:** metadata + verbs + docs complete; `make smoke`
   green from a clean clone; `robium-ai app validate` green.
4. **Published:** promoted into this repo as one clean commit (app
   directory + its README index row, nothing else).
5. **Maintained or archived:** archived apps stay runnable and are marked
   `status: archived` rather than rotting silently.

## Scaffolding

Start from the closest shipped app, not from scratch:

```bash
npx robium-ai app new my-app --from indoor-navigation
```

Then run the release checklist in the design doc before proposing
promotion. Nothing lands here without a human review.
