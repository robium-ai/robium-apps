# Shared Robotics Assets Design

**Date:** 2026-08-15

**Status:** Approved direction; specification ready for implementation review

## Goal

Give applications in `robium-apps` one central, reproducible way to share
simulation worlds, robot models, maps, waypoint sets, and later recordings
without bloating Git or mixing generated user data with application source.

The first consumer is robot-navigation. The design must preserve its pinned
AWS Small House world, Fuel-hosted warehouse world, generated maps, and
per-map waypoints while making the same assets discoverable by future apps.

## Non-goals

- Do not create a separate `robium-assets` repository yet.
- Do not publish assets to GitHub Releases, object storage, or Hugging Face in
  this phase.
- Do not automatically upload, commit, or promote user-created maps.
- Do not move or delete the existing untracked robot-navigation maps without
  a separate explicit choice from the maintainer.
- Do not introduce an asset server, database, authentication system, or new
  package manager.
- Do not add automated tests; this prototype continues to use bounded static
  checks and manual runtime validation by maintainer direction.

## Architecture

The repository will contain a shared asset catalog at `shared/assets/`.
Applications refer to stable asset IDs in their `robium-app.yaml` rather than
embedding source URLs or depending on another app's directories.

The catalog separates metadata from payload storage:

- Small, reviewed assets are **vendored** in Git alongside their manifests.
- Large public assets are **pointers** with an immutable upstream revision,
  checksum, license, and fetch recipe.
- Fetched pointer payloads live in a gitignored shared cache.
- Writable user maps remain app data and are never catalog assets until an
  explicit promotion operation creates a reviewed copy.

```text
robium-apps/
├── shared/
│   └── assets/
│       ├── README.md
│       ├── catalog.yaml
│       ├── .gitignore
│       ├── worlds/
│       │   ├── aws-small-house/
│       │   │   ├── asset.yaml
│       │   │   └── LICENSE
│       │   └── tugbot-warehouse/
│       │       ├── asset.yaml
│       │       └── LICENSE
│       ├── maps/
│       │   └── <map-asset-id>/
│       │       ├── asset.yaml
│       │       ├── map.pgm
│       │       ├── map.yaml
│       │       └── waypoints.json
│       ├── scripts/
│       │   └── fetch_assets.py
│       └── .cache/                  # generated, gitignored
└── robot-navigation/
    ├── robium-app.yaml              # declares required asset IDs
    └── data/maps/                   # writable runtime data, gitignored
```

`shared/assets/` is the source of truth for identity and provenance. The cache
is only a disposable materialization of pointer assets and must be completely
reconstructible from manifests.

## Asset identity and catalog

Asset IDs use a namespaced dotted form:

```text
<kind>.<descriptive-name>[.<variant>]
```

Initial examples:

- `world.aws-small-house`
- `world.tugbot-warehouse`
- `map.furnished-house-waffle-pi.default`

IDs are stable API. Renaming a directory does not rename an ID. If the asset's
meaning changes incompatibly, it receives a new ID; updating an upstream pin
without changing meaning increments the manifest revision.

`catalog.yaml` is a small index used for discovery. It contains the asset ID,
kind, display name, storage mode, and path to the authoritative `asset.yaml`.
It does not duplicate checksums, licenses, or source details.

```yaml
schema_version: "1"
assets:
  - id: world.aws-small-house
    kind: world
    name: AWS RoboMaker Small House
    storage: pointer
    manifest: worlds/aws-small-house/asset.yaml
```

## Asset manifest

Every catalog entry has an `asset.yaml` with this common contract:

```yaml
schema_version: "1"
id: world.aws-small-house
kind: world
name: AWS RoboMaker Small House
revision: "1"
storage: pointer
license:
  id: MIT
  file: LICENSE
source:
  type: git-archive
  repository: https://github.com/aws-robotics/aws-robomaker-small-house-world
  revision: ff9631ca6d1db9c1ba656498151464b5ab74aafe
  url: https://github.com/aws-robotics/aws-robomaker-small-house-world/archive/ff9631ca6d1db9c1ba656498151464b5ab74aafe.tar.gz
entrypoints:
  world: worlds/small_house.world
```

Pointer manifests additionally require `source.sha256`, containing exactly 64
lowercase hexadecimal characters. The implementation must calculate the real
archive checksum from the pinned download before committing the pointer
manifest. Placeholder checksums are forbidden.

Vendored map manifests add derivation metadata:

```yaml
schema_version: "1"
id: map.furnished-house-waffle-pi.default
kind: map
name: Furnished House Waffle Pi default map
revision: "1"
storage: vendored
license:
  id: MIT
derived_from:
  world: world.aws-small-house
  robot: turtlebot3_waffle_pi
  application: robot-navigation
  method: slam_toolbox
files:
  map: map.pgm
  metadata: map.yaml
  waypoints: waypoints.json
```

The map manifest records the world, robot and sensor configuration, producing
application, generation method, and file roles. This prevents a map from being
treated as portable to an unrelated world merely because its YAML loads.

## Storage policy

### Vendored assets

An asset may be committed when all of these are true:

- Its total payload is at most 5 MiB.
- The entire tracked payload beneath `shared/assets/` remains at most 25 MiB.
- Its license permits redistribution and is recorded in the manifest.
- Its provenance and derivation are known.
- It is useful to at least one current app and plausibly reusable by another.

Small occupancy maps, waypoint JSON, compact configuration fixtures, and
thumbnails are suitable. World texture and mesh trees normally are not.

### Pointer assets

Pointer mode is required when the asset exceeds the Git budget or already has
a reliable public canonical source. A pointer must use an immutable upstream
revision and verified checksum. Branch names, floating tags, and `latest` URLs
are not accepted pins.

The initial AWS Small House and Tugbot Warehouse assets remain pointers. Their
large payloads are not copied into Git.

The upstream Fuel metadata for Tugbot in Warehouse version 2 identifies its
license as CC BY-NC-ND 4.0. Its manifest and all consuming-app documentation
must surface that non-commercial, no-derivatives restriction. The pointer may
support the current prototype, but a future commercial distribution must
replace the world or obtain suitable permission rather than treating it as a
permissive Robium asset.

### Local writable assets

Maps created through Dashboard are runtime data. The long-term destination is
`robot-navigation/data/maps/<world-id>/` rather than the ROS package source
tree. That directory is gitignored and mounted into the container so maps
survive container recreation.

The current untracked directories under
`robot-navigation/src/robot_nav_bringup/maps/` are migration inputs only.
The first implementation may create and document the new destination, but it
does not switch runtime paths because doing so would hide the maintainer's
existing maps. A later explicit migration copies selected files to the new
location, verifies that the app can load them, and leaves the originals in
place until the maintainer separately authorizes removal.

## Application declarations

An app declares assets in `robium-app.yaml`:

```yaml
assets:
  worlds:
    - world.aws-small-house
    - world.tugbot-warehouse
  maps: []
```

The declaration means the application is allowed to resolve and package those
assets. It does not imply that every mode loads every asset. Runtime mode and
world selection remain application concerns.

The initial robot-navigation declaration leaves `maps` empty. A canonical
map will be added only after the maintainer selects one of the local candidates
in a separate promotion step.

## Fetch and cache behavior

`shared/assets/scripts/fetch_assets.py` resolves asset IDs through
`catalog.yaml` and materializes pointer assets under
`shared/assets/.cache/<asset-id>/<source-revision>/`.

The fetch operation must:

1. Reject unknown IDs and unsupported manifest schemas.
2. Download to a temporary directory beneath the cache parent.
3. Verify SHA-256 before extraction.
4. Reject absolute paths, parent traversal, symlinks, and hard links in
   archives.
5. Verify declared entrypoints after extraction.
6. Atomically rename the completed directory into the cache.
7. Reuse an existing verified cache entry across apps.

On network failure, checksum mismatch, unsafe archive content, or a missing
entrypoint, the command exits non-zero and leaves no apparently complete cache
entry. It does not silently fall back to a floating or cached revision with a
different checksum.

The first implementation supports the source types currently needed by
robot-navigation: immutable GitHub archives and pinned Gazebo Fuel resources.
New source types require an explicit manifest contract rather than ad hoc app
download code.

## Container integration

Docker builds keep the repository root as their build context. An app build
copies the shared catalog and fetch helper, then resolves only the asset IDs
declared by that app. The resulting image contains the required runtime files
under `/opt/robium/assets/<asset-id>/`.

The container does not mount or depend on the host cache at runtime. Docker's
build cache may reuse completed fetch layers, while `shared/assets/.cache/`
supports local/native workflows and reuse between apps outside Docker.

Indoor-navigation's launch configuration resolves its selected world from the
packaged asset directory instead of owning a special AWS download path. Fuel
resolution remains pinned through its manifest even if the underlying fetch
mechanism uses Gazebo tooling.

## Map promotion workflow

Promotion is deliberately explicit:

1. Stop mapping so the PGM, YAML, and waypoint sidecar are complete.
2. Select one named local map and identify its world and robot configuration.
3. Inspect it in Lichtblick and confirm that localization and navigation work.
4. Copy it into a new `shared/assets/maps/<asset-id>/` directory.
5. Normalize filenames to `map.pgm`, `map.yaml`, and `waypoints.json`, updating
   the YAML image reference accordingly.
6. Add derivation and license metadata to `asset.yaml`.
7. Add the entry to `catalog.yaml` and the consuming app's declaration.
8. Commit the promoted copy. Leave the original local map untouched.

There is no automatic “promote latest” behavior because choosing the wrong map
would make private, poor-quality, or environment-specific data part of the
public application library.

## Verification policy

Automated tests remain out of scope by maintainer direction. Implementation
verification consists of:

- YAML parsing for the catalog, manifests, and app declarations.
- A bounded fetch of each pointer asset with checksum and entrypoint output.
- Size-budget reporting for vendored payloads.
- A Docker build inspection showing only declared assets in the image.
- A manual robot-navigation runtime check that both House and Warehouse load.
- For a later promoted map, manual localization and one navigation goal.

Verification reports what was actually run; a static manifest check is not
described as a runtime pass.

## Initial migration scope

The first implementation will:

1. Create the shared catalog, schemas-by-example, documentation, gitignore,
   and fetch helper.
2. Register AWS Small House and Tugbot Warehouse as pointer assets using live,
   verified source metadata and checksums.
3. Declare those world IDs in robot-navigation's `robium-app.yaml`.
4. Replace robot-navigation's app-owned AWS fetch script and special asset
   path with the shared resolver.
5. Introduce and document the gitignored writable
   `robot-navigation/data/maps/` boundary without switching the current
   runtime mount.
6. Preserve every existing untracked map file in place.

Selecting and promoting a canonical map is a separate follow-up after the
maintainer reviews the candidates. Remote hosting and a separate asset
repository remain deferred until the tracked-size budget or cross-repository
reuse creates a concrete need.
