# Article discovery interview guide

## Contents

- Interview posture
- Codebase-informed opening
- Question sequence
- Guided brainstorming
- Approval gates
- Brief format
- Difficult situations

## Interview posture

Treat article development as collaborative reporting, not a form to complete.
Inspect first, then ask only questions that require human context, editorial
judgment, missing evidence, or access to artifacts.

When `brainstorming@superpowers` is available, use it to expand and compare
possible article promises. When `$grill-me` is available, use it to pressure-test
the selected story, evidence, audience, exclusions, and section arc. Retain the
gates in this guide regardless of which helper runs the conversation.

Ask one focused question or one tightly connected group per turn. Do not dump a
questionnaire. After each response:

1. Reflect the new understanding in one or two sentences.
2. Identify the most important unresolved issue.
3. Recommend a direction if the user would benefit from editorial judgment.
4. Ask the next question.

Continue until the user explicitly approves both the understanding and the
article brief. “No more questions” is not approval unless the user also accepts
the summary.

## Codebase-informed opening

Before the first question, report what the repository already establishes:

- application outcome and runtime;
- important stack choices;
- existing design or architecture intent;
- current implementation state;
- available tests and measured results;
- present assets;
- known limitations or unfinished work.

Label uncertain interpretations. Then begin with the highest-value human
question, usually one of:

- “What should a reader understand or be able to do after this article?”
- “Which moment in the build best captures why this project was worth writing
  about?”
- “Who do you most want to help: a robotics newcomer, a practitioner reproducing
  the app, or an experienced engineer evaluating the design?”

## Question sequence

Adapt this sequence; skip anything already answered.

### 1. Reader and promise

- Who is the primary reader?
- What can they already be assumed to know?
- Is the promised outcome understanding, reproduction, extension, or evaluation?
- What would make the reader say the article was worth their time?
- What must the article not imply?

Offer a recommended article kind based on the answers.

### 2. Human story

- Why did the team start this application?
- Which initial assumption proved wrong or incomplete?
- What was the first observable sign that the system worked?
- Which failure consumed real attention or changed the design?
- What decision would the team make differently now?
- Which detail is obvious only after having built it?

Do not invent drama. If the work was straightforward, prefer a tutorial or deep
dive over manufacturing an engineering story.

### 3. Technical center

- What is the minimum architecture a reader needs?
- Which subsystem or boundary carries the article's main lesson?
- Which code, config, topic, message type, data format, or interface deserves a
  concrete example?
- Which terms need links or short definitions?
- What technical detail is important but would distract from this article and
  should be linked elsewhere?

Load the relevant robotics domain skill and use it to challenge imprecise claims.

### 4. Evidence and honesty

- Which commands were actually run?
- What output, result, metric, or visible state proves the central claim?
- On which machine, robot, simulator, accelerator, and version?
- How many runs, episodes, goals, seeds, or samples support the result?
- What failed, remained flaky, or was not tested?
- Which statements are team recollection rather than recorded evidence?
- Can missing evidence be supplied from logs, screenshots, or existing artifacts?

Recommend narrowing the promise if evidence is insufficient.

### 5. Visual and runnable material

- Is there a hero image, GIF, video, plot, map, diagram, or viewer recording?
- What does each visual prove?
- Does it show simulation or hardware, and is that unmistakable?
- Is the text readable at article width?
- Which commands deserve full blocks, and which values need explanation?
- Would a table, architecture diagram, timeline, or comparison materially help?
- Are asset ownership, attribution, and publication permissions clear?

Ask the user to provide missing files rather than describing an image that does
not exist.

### 6. Voice, brand, and authorship

- Should this sound like the team recounting work, a neutral technical guide, or
  a Robium-method story?
- Who receives the byline?
- How should agent collaboration be disclosed?
- Where did Robium materially affect the architecture, debugging, testing, or
  reusable guidance?
- Which product or internal details should be excluded?

Recommend the quietest brand presence that tells the truth.

### 7. Ending and action

- What should the reader try, check, or think differently afterward?
- Should the ending point to the app, a tutorial, a next experiment, or a
  diagnostic checklist?
- Which future work is genuinely relevant to the reader?

Exclude internal promotion, vendoring, backlog, and repository-maintenance work
unless the article itself is about those processes.

## Guided brainstorming

Do more than ask questions. When the repository suggests multiple stories,
offer two or three concise options with consequences:

```text
A. Engineering story: strongest human narrative; centers the failures between
   mapping and motion; assumes readers know basic ROS.
B. Tutorial: most directly reproducible; requires verified clean-clone commands
   and clearer prerequisites; leaves the build experience mostly out.
C. Deep dive: most technically durable; centers lifecycle and message-type
   boundaries; the application becomes the running example.
```

Recommend one. Ask the user to choose or reshape it. Do not present trivial
options whose only purpose is to prolong the interview.

Use the same method for opening scenes, section arcs, titles, visuals, and
conclusions.

## Approval gates

### Gate 1: understanding

Present:

- confirmed facts;
- the intended reader and promise;
- proposed kind and voice;
- key evidence;
- unresolved or excluded claims.

Ask: “Does this understanding look good, or what should change?” Continue until
the user explicitly approves.

### Gate 2: article brief

Present the full bullet brief from `SKILL.md`. Include the exact commands and
assets proposed, not placeholders such as “add code here.” Ask for approval and
revise until explicit.

### Gate 3: draft

After writing, summarize the main editorial choices, verification performed, and
remaining caveats. Ask for changes. Revise until the user approves the article.

## Brief format

Keep the brief scannable but complete:

```text
- Working title:
- Reader promise:
- Audience / assumed knowledge:
- Kind + voice + byline:
- Opening:
- Sections, one sentence each:
- Commands and code:
- Evidence and results:
- Media and captions:
- Links and sources:
- Limitations:
- Ending:
- Explicit exclusions:
- Open questions:
```

## Difficult situations

### The user wants writing immediately

Perform codebase inspection, present a provisional brief, and ask for explicit
approval. Explain that missing interview context will be labeled rather than
invented. Do not turn discovery into a long ritual when the evidence and request
are already clear.

### The codebase contradicts recollection

Show the concrete discrepancy and ask which source reflects the intended or
current state. Never silently choose the more attractive version.

### The application is incomplete

Offer an experiment report or a pipeline-status article. Separate what works
from what remains unproven. Do not call a smoke test a capability demonstration.

### There are too many stories

Select one primary reader promise and move the others to separate proposed
articles. A case study, tutorial, API deep dive, and product announcement should
not be combined merely because they share a repository.

### The user dislikes the voice but cannot name why

Offer two short rewrites of the same factual paragraph in different approved
registers. Discuss narrator, distance, sentence rhythm, detail, and brand
presence. Do not rewrite the entire article until the preferred register is
clear.
