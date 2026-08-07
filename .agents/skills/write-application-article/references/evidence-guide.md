# Codebase and evidence guide

## Contents

- Inspection order
- Claim ledger
- Commands and results
- Images and captions
- Technical verification
- Final evidence audit

## Inspection order

Read enough of the current codebase to understand the application before
interviewing. Use focused searches instead of dumping the repository.

### 1. Project contract

Inspect:

- `robium-app.yaml` or equivalent metadata;
- the opening, quick start, prerequisites, and limitations in `README.md`;
- standard command surfaces such as `Makefile`, `pyproject.toml`, compose files,
  or package scripts.

Record the public promise, runtime, requirements, and supported scenarios.

### 2. Design intent

Inspect architecture briefs, design documents, plans, and prior article drafts.
Separate original intent from implemented reality. A design document is evidence
of a decision, not proof that the implementation works.

### 3. Implementation

Read the entry points, launch or orchestration files, core configuration, and
the modules that implement the claimed behavior. Follow references to relevant
robotics skills for version-sensitive technical facts.

### 4. Verification

Inspect smoke tests, unit and integration tests, evaluation scripts, fixture
data, stored metrics, CI configuration, and captured logs. Determine what each
test actually asserts.

### 5. Media and artifacts

Inventory images, GIFs, videos, plots, maps, MCAP files, recordings, datasets,
and generated reports. Check resolution, labeling, provenance, and whether each
asset reflects the current application.

### 6. History

Use app-scoped git history to recover the real order of important changes and
the reasons recorded in commits. Preserve unrelated working-tree changes and do
not infer authorship from commit metadata alone.

## Claim ledger

Maintain a ledger while researching:

| Claim | Status | Evidence | Conditions | Article use |
| --- | --- | --- | --- | --- |
| Two goals succeed | observed | smoke output / test | saved map, warm image | result |
| Works without GPU | observed | host + renderer logs | Apple Silicon Docker | opening |
| Suitable for cameras | unsupported | none | lidar only | exclude |

Status values:

- `verified`: reproduced or asserted by an appropriate passing test.
- `observed`: supported by a dated artifact, log, measurement, or team account.
- `implemented`: code exists, but behavior was not independently verified.
- `inferred`: interpretation requiring confirmation.
- `unsupported`: no credible evidence; exclude or state as future work.

Do not convert `implemented` into “works,” or `inferred` into fact.

## Commands and results

For every proposed command block, answer:

- Is this copied from the current command surface?
- Which directory and environment does it require?
- Is it simulation, hardware, local, container, or cloud?
- Was it run as written?
- What should the reader see next?
- What is the safe stop or cleanup command?
- Does it require credentials, payment, hardware motion, or destructive changes?

Prefer the shortest public command that exercises the real path. Avoid internal
maintenance commands unless maintainers are the audience.

When verification is safe and authorized, run commands proportionate to the
claim. Do not launch paid jobs, move hardware, deploy services, overwrite maps,
or edit datasets merely to strengthen an article without explicit authority.

## Images and captions

Each visual needs:

- a purpose in the section;
- source or ownership;
- accurate simulation/hardware labeling;
- descriptive alt text;
- a caption naming the evidence;
- sufficient resolution at rendered width.

Strong caption:

> The local costmap marks the center pillar as occupied while the global path
> bends around its inflated boundary; the purple line is the controller's active
> trajectory.

Weak caption:

> Navigation demo screenshot.

Use figures after the paragraph that tells the reader what to inspect. Do not
use decorative architecture art where a small diagram or real screenshot would
teach more.

Ask specifically for missing assets:

- “Do you have the smoke-test terminal output from the successful run?”
- “Can you provide the GIF showing the clicked goal and completed motion?”
- “Is there a plot with per-checkpoint episode results rather than only the
  aggregate table?”

## Technical verification

Load the relevant domain skill and check:

- version-sensitive package and API claims;
- message, frame, topic, dataset, and configuration terminology;
- environment and accelerator requirements;
- simulation versus physical-hardware boundaries;
- whether a parameter shown is a project setting or upstream default;
- whether a failure explanation is proven or merely plausible.

Prefer primary upstream documentation for external technical facts. Link it at
the relevant term. Date claims likely to change.

## Final evidence audit

Before presenting the draft:

- [ ] The opening result is supported.
- [ ] Every measurement includes conditions and sample size where meaningful.
- [ ] Commands match the current repository.
- [ ] Code excerpts match the current implementation.
- [ ] Images exist, load, and have useful alt text and captions.
- [ ] Relative links resolve from the article's canonical location.
- [ ] Simulation and hardware are unambiguous.
- [ ] Product and version claims have current primary sources.
- [ ] Team recollections are presented as observations, not instrumented facts.
- [ ] Flaky, incomplete, negative, and untested outcomes remain visible.
- [ ] The article does not imply a broader capability than the evidence shows.
