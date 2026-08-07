# Contents

- Editorial identity and voice selection
- Shared writing rules
- Type-specific contracts
- Human cadence and AI-writing rejection rules
- Robium brand and authorship boundaries
- Frontmatter and review checklist

# Robium article voice standard

**Status:** proposed standard, 2026-08-06
**Applies to:** website articles, technical blogs, tutorials, engineering case studies, and experiment reports

## 1. Editorial identity

Robium writing should sound like engineers and researchers sharing work they actually performed. It is technically confident, candid about evidence, and generous with practical detail. It does not sound like product copy converted into a blog post, and it does not sound like a language model completing an article template.

The invariant is not a fixed tone. It is a fixed relationship with truth:

- Say what happened.
- Show how it was observed.
- Distinguish fact, inference, and expectation.
- State what was not tested.
- Give readers something they can use.

## 2. Select type and register before drafting

Every article must declare one `kind` and one `voice` in frontmatter.

```yaml
kind: engineering-story
voice: team
```

Allowed kinds:

- `engineering-story`
- `tutorial`
- `technical-deep-dive`
- `experiment-report`

Allowed voices:

- `team`
- `technical`
- `robium`

### Team voice

Use when people, decisions, and experience are part of the value.

- Prefer “we” for actions the team performed.
- Use “I” only for a genuinely single-author observation.
- Name the person or role when responsibility matters.
- Preserve useful chronology and uncertainty.
- Let personality appear through selection and judgment, not jokes or filler.

Good:

> We expected headless lidar to be the risky part. It worked on the first run. The lifecycle manager failed later, during an eight-second Docker stall.

Weak:

> Several challenges were encountered during the implementation process.

### Technical voice

Use when the reader wants to perform or understand a task and authorship is secondary.

- Use second person sparingly and imperatives naturally.
- Define the scope in the opening paragraph.
- Prefer operational verbs and exact interfaces.
- Keep organizational references out unless they affect the task.
- Optimize for comprehension and retrieval.

Good:

> Check the publisher and subscriber types before changing the controller. A `Twist` publisher will not connect to a `TwistStamped` subscription.

Weak:

> It is important to ensure that all relevant communication types are correctly configured.

### Robium voice

Use when Robium's method, skills, or product behavior is part of the subject.

- Write as the Robium team, not as an omniscient brand.
- Introduce Robium at the point where it changed a decision or result.
- Explain what the agent proposed and what execution verified.
- Treat failures as inputs to better skills, not embarrassing exceptions.
- Limit unproven capability statements.

Good:

> The architecture skill selected the conventional Jazzy–Nav2–Gazebo stack. That choice held up. The application work added the Docker-specific lifecycle and message-type failures that the original guidance did not cover.

Weak:

> Robium's powerful skill ecosystem seamlessly enabled end-to-end autonomous navigation.

## 3. Rules shared by every voice

### Open on a real object, event, question, or result

The opening should contain something that belongs only to this article.

Good opening units:

- A robot that planned but did not move.
- A measured checkpoint result.
- A dataset operation that changes files in place.
- A concrete question the experiment tested.
- The visible outcome the tutorial will produce.

Avoid opening with industry scale, rapid change, broad importance, or dictionary definitions unless the article is truly a reference page.

### Put the subject before the organization

Readers came for navigation, processors, policies, sensors, or datasets. Robium appears when it contributes to that subject.

### Use concrete nouns and active verbs

Prefer:

- “AMCL did not publish `map → odom`.”
- “The test sent two goals.”
- “Docker paused for eight seconds.”
- “The collision monitor rejected the scan.”

Avoid:

- “A localization issue occurred.”
- “Testing was undertaken.”
- “Unexpected behavior was experienced.”
- “The system leveraged advanced capabilities.”

### Explain causality, not just sequence

Do not merely say what was done next. Explain what observation justified it.

Use this shape when debugging:

```text
symptom → evidence → hypothesis → intervention → verification → reusable rule
```

### Attach important claims to evidence

An important claim should be near at least one of:

- a command;
- a configuration fragment;
- a log line;
- a measurement with conditions;
- a table or plot;
- an image with an evidentiary caption;
- a test result;
- a source-code or upstream-documentation link.

### Distinguish observation, inference, and recommendation

Use explicit signals:

- “We observed…”
- “The trace showed…”
- “Our working explanation was…”
- “This suggests…”
- “We verified it by…”
- “For this application, we recommend…”
- “We did not test…”

### Name boundaries

State simulation versus hardware, host platform, accelerator, important version, test date, and known exclusions when they affect interpretation.

### Link words, not citation dumps

Link the exact technical term or claim at first meaningful use. Do not finish every section with a stack of “learn more” URLs.

### Let code perform a named job

Introduce a code block with why the reader needs it. Follow it with expected behavior or interpretation. Do not place unexplained code between prose paragraphs.

### Let images prove something

A caption should identify the evidence visible in the image. “Screenshot of the app” is not enough.

### End with changed understanding or useful action

Do not repeat the introduction. End with:

- the diagnostic order readers should use;
- the next experiment justified by the data;
- the boundary of the current result;
- the small set of implementation principles worth carrying forward.

## 4. Type-specific voice contracts

### Engineering story

**Reader promise:** understand how a working system took shape and what the experience taught.

Required qualities:

- Visible result near the top.
- A compact system model.
- Two or more consequential decisions or failures.
- Evidence from the actual build.
- A behavioral definition of done.
- A reusable takeaway.

Natural narrator: `team` or `robium`.

Avoid forcing “Problem / Constraints / Approach / Results” headings. Let the actual causal story determine sections.

### Tutorial

**Reader promise:** complete one bounded task.

Required qualities:

- Stated outcome and prerequisites.
- Tested environment.
- Linear steps.
- Observable result after meaningful commands.
- Local warnings and troubleshooting.
- Verification and cleanup.

Natural narrator: `technical`.

Use imperatives. Do not add an engineering memoir to a procedural page.

### Technical deep dive

**Reader promise:** gain a mental model strong enough to reason about and extend a subsystem.

Required qualities:

- The problem the abstraction solves.
- Architecture or data-flow model.
- One running example.
- Important invariants and boundaries.
- Implementation details connected to concepts.
- Failure modes and extension guidance.

Natural narrator: `technical`, occasionally `team`.

Avoid disconnected snippet collections and API inventories without a conceptual spine.

### Experiment report

**Reader promise:** understand the question, evidence, and justified conclusion.

Required qualities:

- Question or hypothesis.
- Setup, controls, and variations.
- Sample size, seeds, hardware, and measurement method where relevant.
- Results separated from interpretation.
- Negative or ambiguous findings retained.
- Threats to validity.
- Next experiment.

Natural narrator: `team` or `technical`.

Avoid describing a pipeline test as a capability result.

## 5. Human cadence rules

These rules exist because syntactically correct prose can still sound generated.

- Vary paragraph length according to content. Do not make every paragraph three sentences.
- Mix short diagnostic statements with longer explanation.
- Use transitions only when the relationship is not already obvious.
- Allow a plain sentence after a dense technical paragraph.
- Prefer one strong example over three parallel examples added for symmetry.
- Do not manufacture narrative tension.
- Retain useful irregularities: a surprising result, an awkward boundary, a decision that did not age well.
- Read the draft aloud. If every sentence lands with the same rhythm, revise it.

## 6. AI-writing rejection list

Reject or rewrite drafts containing these patterns:

- “In today's rapidly evolving landscape…”
- “It is important to note that…”
- “This comprehensive guide will explore…”
- “Whether you are a beginner or an experienced developer…”
- “By leveraging the power of…”
- “This not only X, but also Y” used as default rhythm.
- “Seamless,” “robust,” “powerful,” “cutting-edge,” or “innovative” without evidence.
- “Challenges were encountered” instead of naming the failure.
- Repeated “key,” “critical,” and “crucial” labels.
- A three-item list in every section.
- A recap paragraph after every heading.
- A conclusion that repeats the article outline.
- Identical section structures across unrelated projects.
- Excessive em dashes, parenthetical qualifications, and abstract nouns.
- Claims that the work was “end-to-end” without defining both ends.
- Calling an AI agent the hero of the story.

## 7. Robium brand boundaries

Robium-branded writing should feel like team writing with a clear point of view.

The point of view is:

- Robotics work should be reproducible.
- Simulation and hardware claims must be distinguished.
- Tests should assert behavior, not merely process health.
- Tools should be selected by constraints, not fashion.
- Failures should improve reusable guidance.
- A narrow working vertical slice is more useful than a broad staged demo.

The brand should appear through these decisions. The word “Robium” does not need to appear repeatedly.

Maximum recommended brand presence:

- Tutorial: one brief provenance note, if relevant.
- Technical deep dive: only where a skill, abstraction, or tool is the subject.
- Engineering story: two to four moments where Robium affected the work.
- Experiment report: methodology provenance and links; results remain foregrounded.

## 8. Byline and authorship

Prefer a named human author or “Robium team.” If an agent drafted or implemented substantial portions, disclose that in a short methodology note rather than using “AI coding agent” as promotional copy.

Recommended note:

> Built and documented through collaboration between the Robium team and Codex. Commands and results in this article were verified against the referenced application.

Do not imply an agent independently witnessed an experience. Attribute observations to runs, logs, tests, or the team reviewing them.

## 9. Frontmatter standard

```yaml
---
title: From an empty map to autonomous navigation with ROS 2 and Nav2
summary: What broke while making the classical navigation loop reproducible on an Apple Silicon laptop.
kind: engineering-story
voice: team
author: Robium team
audience: robotics-developer
level: intermediate
app: indoor-navigation
date: 2026-08-05
tested: 2026-08-03
tags: [ros2, nav2, gazebo, slam]
hero: assets/trailer.gif
hero_alt: TurtleBot 3 following a Nav2 path on the saved occupancy map in simulation.
---
```

## 10. Editorial review checklist

### Identity

- [ ] Does the draft declare one type and one voice register?
- [ ] Does the opening belong specifically to this article?
- [ ] Is the reader's role clear?
- [ ] Does the voice remain stable without becoming monotonous?

### Evidence

- [ ] Are important claims attached to evidence?
- [ ] Are measurements accompanied by conditions and sample sizes?
- [ ] Are simulation and hardware clearly distinguished?
- [ ] Are limitations specific rather than ceremonial?
- [ ] Are commands taken from a tested path?

### Usefulness

- [ ] Does every code block have a purpose?
- [ ] Does every meaningful command have an expected result?
- [ ] Do figures and captions teach something?
- [ ] Are warnings next to the step they affect?
- [ ] Does the ending give the reader a next action or changed mental model?

### Authenticity

- [ ] Are failures named directly?
- [ ] Can generic claims be replaced with project-specific facts?
- [ ] Has unnecessary brand repetition been removed?
- [ ] Has templated AI phrasing been removed?
- [ ] Does sentence and paragraph rhythm vary naturally?
- [ ] Would an engineer who performed the work recognize the account?

## 11. Recommended voice for the first Robium articles

| Application | Kind | Voice | Editorial center |
| --- | --- | --- | --- |
| Indoor navigation | `engineering-story` | `team` | The failures between mapping and reliable motion |
| Imitation manipulation | `experiment-report` | `team` | What the checkpoint ladder actually measured |
| VLA language learning | `experiment-report` | `team` | What the pipeline proves and what the policy does not yet prove |

A later article explaining how application evidence changed the Robium skill pack should use `engineering-story + robium`. A standalone Nav2 setup guide should use `tutorial + technical`. Keeping those pieces separate prevents the first application article from becoming a case study, manual, product page, and tutorial at the same time.
