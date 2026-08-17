# Robot Navigation Rename and CLI Article Design

**Date:** 2026-08-16

**Status:** Implemented locally and verified

## Goal

Rename the active `robot-navigation` reference application to
`robot-navigation` across the application, CLI examples, and website. Present
the app as a maintained Robium reference application, make the Robium CLI the
primary lifecycle interface, retain Make as the transparent alternative, and
document the supported local and server environments.

## Product identity

The public application identity is **Robot Navigation** and its stable ID is
`robot-navigation`.

The GitHub repository remains `robium-ai/robium-apps`. The application moves
from its former subdirectory to:

```text
robium-apps/robot-navigation/
```

The canonical source link becomes:

```text
https://github.com/robium-ai/robium-apps/tree/main/robot-navigation
```

Active technical identifiers use the same identity:

- application folder and manifest ID: `robot-navigation`;
- Docker image and Compose project names: `robot-navigation`;
- ROS 2 package and Python module: `robot_nav_bringup`;
- Blog slug and article asset namespace: `robot-navigation`;
- CLI examples: `robium app ... robot-navigation`.

The hosted demo may retain the existing `nav-trial` demo ID because it is a
separate demo-infrastructure identifier and does not expose the former product
name.

## Rename boundary

### Active application surfaces

Rename the application directory and every active reference used to build,
run, describe, or publish the app. This includes:

- `robium-app.yaml`, Makefile, Dockerfiles, Compose, Cloud Build, scripts, and
  launch files;
- the ROS package directory, package metadata, setup configuration, Python
  imports, and launch-package lookups;
- README, architecture brief, current case study, application registry, and
  current CLI documentation;
- active test and fixture paths that locate the app or ROS package, without
  adding or running unit tests;
- the website article slug, generated article fallback, public article assets,
  metadata, related links, and sitemap output;
- current demo image references and other active deployment configuration.

### Historical records

Historical implementation plans, specifications, changelog entries, Git
history, and dated Robium learning records preserve the name used when those
events occurred. They are evidence, not current product surfaces. They must not
be mechanically rewritten.

### Compatibility

The canonical Blog URL becomes:

```text
https://robium.ai/blog/robot-navigation/
```

The website keeps explicit permanent redirects from the two former public
routes to preserve bookmarks and search authority:

```text
/blog/robot-navigation/     -> /blog/robot-navigation/
/articles/robot-navigation/ -> /blog/robot-navigation/
```

The former name may appear only in this compatibility redirect and in the
historical records described above. It must not appear in current headings,
labels, CLI output, manifests, source links, or application identifiers.

Saved maps and waypoint sidecars are local user data. Move or preserve them
with the application directory; do not delete, stage, or commit them.

## Robium CLI workflow

The published `robium-ai@0.6.0` package already exposes the application
lifecycle commands. The article therefore presents the CLI as the primary
interface without claiming that it downloads the applications repository.

The setup flow is explicit:

```bash
npx robium-ai@latest setup
git clone https://github.com/robium-ai/robium-apps.git
cd robium-apps
```

`setup` installs the Robium skills for supported coding agents. The separate
Git clone supplies the reference applications that the lifecycle CLI reads.

From the `robium-apps` checkout, readers use:

```bash
npx robium-ai@latest app help robot-navigation
npx robium-ai@latest app doctor robot-navigation
npx robium-ai@latest app build robot-navigation
npx robium-ai@latest app run robot-navigation
npx robium-ai@latest app status robot-navigation
npx robium-ai@latest app logs robot-navigation
npx robium-ai@latest app stop robot-navigation
```

The article explains that the CLI discovers the app through
`robium-app.yaml`, changes into its directory, and runs the lifecycle command
declared by the manifest. It is a consistent interface over the app's native
commands, not a separate runtime.

The direct alternative remains visible:

```bash
cd robot-navigation
make help
make doctor
make build
make run
make status
make logs
make stop
```

The command explanation should stay short and practical. `help` shows the CLI
and Make mapping, `doctor` checks the local environment, `build` creates the
container image, `run` starts the interactive application, and the remaining
commands inspect or stop it.

## Article structure

The opening identifies Robot Navigation as a living Robium reference
application, not only a generic ROS tutorial.

An early **System requirements** section states:

- macOS with Docker Desktop is supported and tested;
- Ubuntu with Docker Engine and Compose v2 is supported and tested;
- a Linux server can run the same containerized application, with browser
  access to the documented web and WebSocket ports;
- no physical robot or GPU is required for the simulation workflow;
- the reader needs Git, Docker with Compose v2, and a modern browser.

The lifecycle section leads with Robium installation and CLI commands, then
shows their Make equivalents. Existing mapping, localization, waypoint,
navigation, Lichtblick, Foxglove, and Robium Dashboard content remains.

The closing section links directly to the Robot Navigation source directory
and the `robium-ai/robium-apps` issue tracker. It says the application receives
ongoing bug fixes and improvements, invites readers to try it, and asks them to
file an issue with reproducible observations.

## Website and asset flow

The case study in the application repository remains the canonical article.
Its `app: robot-navigation` frontmatter generates the new website slug.

Article GIFs and stills live under:

```text
robot-navigation/assets/gifs/
robot-navigation/assets/stills/
```

The website ingestion script copies those assets to:

```text
public/articles/robot-navigation/assets/
```

The local raw-frame backup moves outside Git to:

```text
/Users/mdemirst/repos/robium-backup/robot-navigation/raw/
```

The generated website fallback and public files use only the new namespace.
The former public asset directory is removed after the new article build is
verified.

## Failure handling

- If the app ID and directory disagree, stop and correct the manifest before
  running lifecycle commands.
- If a ROS package lookup still uses the former package name, treat it as a
  failed rename and fix the active reference rather than adding aliases.
- If a website build produces both article slugs, keep only the new article
  and the explicit redirects.
- If local saved maps overlap a move, preserve them in place and verify their
  destination before continuing.
- Do not publish the website or package as part of the rename unless the
  maintainer explicitly requests deployment or publication.

## Verification

The rename uses focused checks and builds rather than the repository unit or
smoke suites, matching the current prototype workflow:

1. Validate `robot-navigation/robium-app.yaml` through the published or local
   Robium CLI.
2. Confirm `app help`, `app doctor`, and command resolution use
   `robot-navigation` and the expected Make equivalents.
3. Build the renamed application container to catch Docker and ROS package
   path failures.
4. Build the website and confirm the new article, media, metadata, sitemap, and
   permanent redirects.
5. Search active surfaces for the former name, excluding historical records
   and the two deliberate redirect entries.
6. Confirm saved maps and waypoint sidecars remain present and untracked.

No unit tests, smoke tests, commit, push, package publication, or deployment
are included unless separately requested.
