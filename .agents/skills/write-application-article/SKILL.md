---
name: write-application-article
description: >
  Interview, research, outline, write, and revise authentic robotics application
  articles grounded in the current codebase, commands, results, images, and team
  experience. Use when: 'write the article', 'technical blog', 'case study',
  'tutorial for this app', 'turn this project into a post', or brainstorming a
  publishable application write-up. Load after an application exists or has
  enough implementation evidence to describe. Not for: architecture design
  before implementation (use `architect`) or editing only website presentation.
---

# Write an application article

Develop a publishable robotics article as an approval-gated conversation. Inspect
the application, interview the user until the story is solid, agree on a bullet
brief, then draft from verified evidence in a voice appropriate to the article.

## When to use this skill

- Turn a working, partial, or failed robotics application into an engineering
  story, tutorial, technical deep dive, or experiment report.
- Improve an existing write-up that feels templated, generic, promotional, or
  AI-written.
- Help a team discover the actual story before writing.
- Cross-references: use `architect` to design a new application, the relevant
  domain skill to verify robotics facts, and website tooling to render or publish
  an already-approved article.

## Key directives

- **Delegation posture: embed + links.** This skill owns Robium's editorial
  workflow and voice standard. Delegate open-ended discovery to
  `brainstorming@superpowers` and persistent plan-sharpening to `$grill-me` when
  those skills are available; otherwise execute the interview loop below
  directly. Never skip discovery merely because either dependency is absent.
- **Inspect before asking.** Read the current app, metadata, README, architecture
  brief, tests, commands, assets, results, limitations, and relevant git history
  before asking the user for facts the repository already contains.
- **One conversation, explicit gates.** Continue guided questioning until the
  user explicitly says the understanding or brief “looks good,” “approved,” or
  equivalent. Do not interpret silence, partial answers, or lack of objections as
  approval.
- **No prose draft before brief approval.** First present the complete proposed
  article as scannable bullets: promise, audience, type, voice, opening, section
  arc, commands, evidence, media, limitations, sources, and ending.
- **Evidence leads.** Important claims require a command, configuration, log,
  measurement, test result, image, source link, or clearly attributed team
  observation. Mark unresolved claims; never smooth them into certainty.
- **Ask for missing artifacts.** Specifically ask about commands, output, logs,
  measurements, screenshots, diagrams, videos, captions, byline, links, and
  permissions when they would improve the article.
- **Sound written by people.** Use concrete nouns, active verbs, varied cadence,
  useful irregularities, and project-specific judgment. Reject generic AI prose,
  inflated adjectives, symmetrical filler, and repeated template sections.
- **Do not force Robium into the foreground.** Use the `robium` register only
  where a Robium skill, agent decision, or learning loop materially affected the
  work. The robot application remains the subject.

## Quick start

### 1. Inspect the application

Start with read-only discovery. Prefer `rg --files` and focused reads. Look for:

```text
README.md
robium-app.yaml
docs/architecture-brief.md
docs/case-study.md
Makefile / pyproject.toml / compose files
tests and smoke-test entry points
assets, screenshots, GIFs, videos, plots, maps
recent app-specific git history
```

Load the relevant robotics domain skill before evaluating technical claims. Do
not run expensive, hardware-affecting, cloud, or destructive commands merely to
collect article evidence without appropriate authorization.

### 2. Build a discovery ledger

Keep four internal lists:

- **Known:** repository-backed facts.
- **Observed:** run results, logs, measurements, or team experiences with source.
- **Inferred:** plausible interpretations that require confirmation.
- **Missing:** questions or artifacts needed for a credible article.

### 3. Run the interview loop

Ask one focused question or one tightly related group at a time. Each round:

1. Briefly reflect what is now understood.
2. Point out one ambiguity, weak claim, or storytelling opportunity.
3. Offer a recommendation when expertise can reduce user effort.
4. Ask the next highest-value question.

Cover the prompts in `references/interview-guide.md`; do not mechanically ask
questions already answered by the codebase. Continue until the user confirms
that the understanding looks good.

### 4. Present the article brief

Use this exact decision surface before drafting:

```text
- Reader promise:
- Primary audience and assumed knowledge:
- Article kind:
- Voice register and byline:
- Opening scene/question/result:
- Section arc:
- Commands/configuration to include:
- Evidence and measured results:
- Images/video/diagrams and captions:
- Honest limitations and unresolved points:
- Source and repository links:
- Ending / reader takeaway:
- Excluded material:
```

Give editorial advice where choices are weak. Ask for changes, then continue
revising the brief until the user explicitly approves it.

### 5. Draft and verify

Write only after approval. Preserve portable Markdown by default. Use frontmatter
from `references/article-standard.md`. Link technical terms at first meaningful
use, keep warnings next to affected steps, and introduce every code block with
its job and expected result.

After drafting:

1. Trace every important claim to the discovery ledger.
2. Verify commands against the current codebase; run safe checks proportionate
   to the claim when authorized.
3. Verify local asset paths and external links.
4. Apply the authenticity and type-specific checklist in
   `references/article-standard.md`.
5. Show the user a concise change summary and any remaining questions.
6. Revise until the user approves the article; do not call a draft final merely
   because it is complete.

## Decision guidance

### Choose article kind

- **Engineering story:** decisions, failures, integration boundaries, and the
  path to a behavioral result.
- **Tutorial:** one bounded reader outcome through tested sequential steps.
- **Technical deep dive:** a mental model and running example for understanding
  or extending a subsystem.
- **Experiment report:** a question, controlled setup, results, interpretation,
  limitations, and next experiment.

Do not combine all four. If a project supports multiple promises, recommend
separate articles and select one primary kind for the current draft.

### Choose voice register

- **`team`:** use “we” for actions the team performed; preserve judgment,
  chronology, uncertainty, and useful failures.
- **`technical`:** foreground the subject and reader; use direct instructions,
  precise interfaces, and minimal organizational presence.
- **`robium`:** write as the Robium team and show where skills or agent work
  changed decisions, evidence, or reusable guidance. Avoid product superlatives.

Read `references/article-standard.md` for the full contracts. Inspect the
concrete samples selectively:

- `references/sample-groot.md`: policy reference, warnings, long commands,
  benchmark tables.
- `references/sample-processor.md`: technical deep dive with one running example.
- `references/sample-dataset-tools.md`: command cookbook and local warnings.
- `references/sample-unitree-g1.md`: end-to-end hardware guide with images,
  numbered parts, networking, and exact commands.

Use samples to study structure and cadence, never to imitate sentences or insert
content unrelated to the app.

### Decide whether the evidence is sufficient

Proceed to a publishable draft only when the central promise has evidence. If
the project is incomplete, propose an honest experiment report or “pipeline
proven, capability unproven” article instead of manufacturing success. If the
user wants a capability claim that the codebase does not support, explain the
gap and ask for the missing run or narrow the claim.

## Platform gotchas

- Hardware and cloud evidence can be expensive or disruptive to reproduce.
  Prefer existing run artifacts; request authorization before new runs.
- A command valid in simulation may be unsafe on a physical robot. Label the
  environment and do not run hardware commands solely for article verification.
- Website rendering may ingest `docs/case-study.md` from another repository.
  Identify the canonical source before editing so a build step does not overwrite
  the article.

## Customization

- Default output is the application's existing article path, usually
  `docs/case-study.md`; confirm the canonical path from repository conventions.
- Use `.md` for portable articles. Use `.mdx` only for real interactive
  components that cannot degrade cleanly to Markdown callouts, tables, images,
  code, or links.
- Short reference-app pages may compress the workflow, but they still require a
  bounded promise, tested environment, and source link.
- For a non-Robium repository, keep the same interview and evidence gates while
  replacing Robium-specific frontmatter and brand guidance.

## References

- `references/article-standard.md`: article kinds, voice registers, shared style
  rules, AI-writing rejection list, frontmatter, and editorial checklist.
- `references/interview-guide.md`: adaptive grilling sequence, artifact prompts,
  approval gates, and guided-question patterns.
- `references/evidence-guide.md`: codebase inspection, claim ledger, commands,
  media, captions, and verification requirements.
- `references/sample-groot.md`: concrete LeRobot policy reference sample.
- `references/sample-processor.md`: concrete LeRobot processor tutorial sample.
- `references/sample-dataset-tools.md`: concrete LeRobot dataset cookbook sample.
- `references/sample-unitree-g1.md`: concrete LeRobot hardware guide sample.
- Upstream: [LeRobot documentation](https://huggingface.co/docs/lerobot/),
  [Rerun examples](https://rerun.io/examples),
  [NVIDIA Technical Blog](https://developer.nvidia.com/blog/), and
  [Foxglove blog](https://foxglove.dev/blog/). Related skills:
  `brainstorming@superpowers`, `$grill-me`, `architect`, and robotics domain skills.

## Changelog

- 0.1.0 (2026-08-06): initial interview-gated, evidence-backed application
  article workflow with four kinds, three voices, and concrete LeRobot samples.
