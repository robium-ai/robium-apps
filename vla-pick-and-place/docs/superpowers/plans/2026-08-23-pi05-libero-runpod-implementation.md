# Pi0.5 LIBERO VLA Pick-and-Place Implementation Plan

**Date:** 2026-08-23

**Specification:**
`docs/superpowers/specs/2026-08-23-pi05-libero-runpod-redesign.md`

Execute every task sequentially. A failed gate blocks all following gates. No
paid resource may be created before Task 4 passes, and production live sessions
remain unauthorized after the final task.

## Task 1: Commit the architecture record

1. Validate the spec and active brief for placeholders, contradictions,
   ambiguous revisions, and issue #69 scope drift.
2. Confirm only design files changed in `robium-apps`.
3. Commit the spec, plan, and active architecture brief as a documentation-only
   commit on `promote/vla-pick-and-place-issue-69`.

**Gate:** the design commit exists before application implementation.

## Task 2: Replace the application with tests first

1. Add failing tests for:
   - suite/task/state/seed mapping;
   - canonical versus experimental prompt classification;
   - 200-code-point limit and text-only rendering;
   - one-rollout locking and cooperative cancellation;
   - simulator success/failure aggregation;
   - publication-manifest schema and zero-episode guard;
   - artifact SHA-256 validation;
   - fake-policy completion with nonblank streamed frames; and
   - correct/missing/foreign capability routing.
2. Replace `pyproject.toml`, lockfile, launcher, Makefile, and Docker definition
   with pinned Pi0.5/LIBERO dependencies and commands.
3. Preserve the `vla_pick_and_place` package identity while replacing old active
   implementation modules with focused config, task, policy, rollout, evidence,
   UI, gateway, and CLI modules.
4. Remove active SmolVLA, SO-101, oracle, custom recording/training, spike, and
   Rerun files. Do not retain compatibility shims that imply those paths remain
   supported.
5. Add three small recorded fixtures and curated state metadata for IDs 0, 1,
   and 2.
6. Implement the deterministic fake rollout, streaming UI, protected gateway,
   manifest validation, and real Pi0.5/LIBERO adapter.
7. Update README, `robium-app.yaml`, app docs, and the `REGISTRY.md` row/card in
   the same application commit.

**Gate:** all local unit and integration tests pass; real inference remains
untouched.

## Task 3: Free application and container smokes

1. Run the launcher doctor and local fake-policy smoke.
2. Exercise fake rollout completion through the real UI and verify nonblank
   frames.
3. Build the pinned Linux/amd64 image's CPU/fake gateway target.
4. Start the container, claim with the correct capability, reject root/missing/
   foreign capability routes, load the embedded UI, stream a rollout, request
   shutdown, and verify process/container exit.
5. Re-run the complete app test suite from a clean environment.
6. Commit the application, README, registry, compact fixtures, and test evidence.

**Gate:** local and CPU/fake container checks are green before credential or
billing preflight and before any Pod creation.

## Task 4: Preflight the first paid gate

Perform read-only checks for:

- RunPod API authentication and positive credit balance;
- accepted checkpoint/Gemma licensing and direct file access to both the Pi0.5
  snapshot and the manually gated PaliGemma tokenizer snapshot;
- private registry authentication and immutable GPU image digest;
- dedicated RunPod template/cost center;
- existing `US-KS-2` network volume `68s0bxbv7p` with enough capacity for the
  approved same-Pod exact-revision checkpoint bootstrap;
- NVIDIA RTX PRO 4500 Blackwell Server Edition 32 GB Secure Cloud availability
  in `US-KS-2`;
- RunPod billing endpoint access; and
- a deletion-verification path.

Do not create a Pod during preflight. Stop and report if any credential,
funding, licensing, capacity, or infrastructure prerequisite is unavailable.

**Gate:** all prerequisites are verified and the user-authorized issue budget is
available.

## Task 5: Run one paid feasibility Pod

1. Create exactly one temporary NVIDIA RTX PRO 4500 Blackwell Server Edition
   32 GB Pod in `US-KS-2` from the immutable private image with existing volume
   `68s0bxbv7p`. The prior A100 request and `US-MD-1` volume path failed before
   compute, and H100 NVL final preflight found no stock. The operator authorized
   this one RTX PRO 4500 allocation request on 2026-08-24 after an exact
   inference-memory and US inventory review.
2. Before checkpoint download, record `nvidia-smi`, exact device name, host
   driver, PyTorch/CUDA versions, compute capability/support, and a minimal CUDA
   tensor operation. Any incompatibility fails the gate and deletes the Pod.
3. Record Pod/image/model startup timing and proxy behavior.
4. Bootstrap the exact pinned checkpoint onto the attached volume, verify the
   model hash and required files, write the revision marker last, remove the Hub
   token from child processes, then load checkpoint and processors offline.
5. Run one complete canonical task-8 episode to a simulator-derived result.
6. Record peak VRAM and action-latency statistics.
7. Exercise cooperative cancellation in a separate non-measured rollout only if
   it does not require creating a second Pod.
8. Delete the Pod in a `finally` path and poll until the API confirms absence.
9. Record measured cost and feasibility evidence.

Do not create a fallback Pod and do not optimize the model. Any feasibility
failure blocks later paid work.

**Gate:** real checkpoint load, processor load, full episode, required metrics,
proxy behavior, cancellation, and confirmed deletion all pass.

## Task 6: Run and publish the paid evaluation

1. Run exactly 20 sequential canonical episodes with task 8, state IDs 0-19,
   seeds 1000-1019, hard resets, batch size 1, and no retries.
2. Preserve all results and videos, including failures.
3. Generate and validate the manifest, aggregate score, reproduction config,
   revisions, GPU/cost data, and SHA-256 hashes.
4. Create or update the public Hugging Face evidence dataset and upload all 20
   videos and records.
5. Resolve the immutable dataset revision and verify every published hash.
6. Commit only the validated manifest/schema, result summary, three compact
   previews, and immutable dataset revision.

**Gate:** 20 measured episodes exist and public evidence is immutable. A score
below 16/20 is published with the required warning, not rerun.

## Task 7: Add the disabled RunPod provider and website experience

1. Add website/orchestrator tests for provider routing, RunPod create/get/delete/
   reconcile, strict ownership, one-Pod busy, budget ledger, $5 refusal, all
   lifecycle phases, disabled allocation, and secret redaction.
2. Add demo provider configuration and the RunPod REST client/driver beside the
   existing Cloud Run and local Docker drivers.
3. Add atomic GCS budget-ledger reconciliation against RunPod billing and active
   reservations; fail closed on unverifiable spend.
4. Add the VLA demo JSON with `provider: runpod`, exact GPU allowlist, volume,
   port, boot/ready/hard timeouts, concurrency 1, budget $5, and
   `VLA_LIVE_ENABLED=false` default.
5. Rewrite the VLA article and demo page from the immutable manifest, showing
   three state outcomes, upstream 97.5% attribution, Robium's own score, and any
   below-target warning.
6. Add a responsive demo-specific live workspace that keeps evidence visible in
   disabled, busy, budget-exhausted, unavailable, and failed states.
7. Run the local fake-container end-to-end lifecycle.
8. Run orchestrator unit tests, website smoke, and existing ACT, Diffusion
   Policy, Robot Navigation, app-registry, and lifecycle regressions.
9. Commit website/orchestrator integration without enabling production live
   sessions.

**Gate:** all mocked/local provider, security, UI, and regression checks pass.

## Task 8: Final real disabled integration and deployment

1. Exercise the real RunPod development flow: start, ready, rollout, result,
   stop, and confirmed deletion.
2. Verify stop, expiry, boot failure, hard timeout, and restart reconciliation
   delete only owned Pods.
3. Verify no secret or edited prompt appears in browser payloads or logs.
4. Deploy the application image, evidence-backed article, and production
   orchestrator integration with `VLA_LIVE_ENABLED=false`.
5. Verify the deployed page shows the immutable proof and explicitly states that
   live GPU sessions are disabled.
6. Confirm no production Pod is created and capture deployment evidence links.

**Gate:** disabled production integration is deployed and verified.

## Task 9: Stop before production enablement

Report commits, immutable evidence URLs, paid measurements/cost, complete test
results, deployment URL, deletion confirmations, and any remaining blockers.

Do not set `VLA_LIVE_ENABLED=true`. The awaiting step, after separate explicit
approval, is to enable the one-Pod fleet, run one production lifecycle through
confirmed deletion, and monitor first-session and budget behavior.
