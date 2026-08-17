# Shared Robotics Assets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repository-wide asset catalog and make robot-navigation consume its two simulation worlds through stable shared asset IDs.

**Architecture:** `shared/assets/` owns asset identity, provenance, manifests, safe downloading, and a reusable gitignored cache. Applications declare asset IDs in `robium-app.yaml`; Docker materializes only declared assets into `/opt/robium/assets/`, while writable maps remain local application data and are never promoted automatically.

**Tech Stack:** Python 3.11+, PyYAML 6.x, YAML manifests, `urllib`, `tarfile`, `zipfile`, Docker, ROS 2 Jazzy, Gazebo Harmonic

## Global Constraints

- Do not add, restore, or run automated tests; use bounded parser, fetch, checksum, and runtime checks only.
- Do not copy, move, delete, stage, or commit any existing file under `robot-navigation/src/robot_nav_bringup/maps/`.
- Do not switch the current `/ws/maps` runtime mount in this implementation.
- Vendored assets are limited to 5 MiB each and 25 MiB total beneath `shared/assets/`.
- Pointer assets require immutable revisions, verified SHA-256 digests, recorded licenses, and validated entrypoints.
- Do not publish assets remotely or create a separate asset repository.
- The Tugbot Warehouse pointer must record its upstream CC BY-NC-ND 4.0 restriction; do not describe it as permissively licensed.

---

### Task 1: Create the shared catalog and safe resolver

**Files:**
- Create: `shared/assets/.gitignore`
- Create: `shared/assets/README.md`
- Create: `shared/assets/catalog.yaml`
- Create: `shared/assets/scripts/fetch_assets.py`

**Interfaces:**
- Produces: `load_catalog(root: Path) -> dict[str, Asset]`, `fetch_asset(asset_id: str, destination: Path) -> Path`, and CLI `fetch_assets.py ASSET_ID [--catalog PATH] [--destination PATH]`.
- Consumes: PyYAML through `yaml.safe_load`, Python standard-library HTTP/archive modules, and version-1 catalog/manifest files.

- [ ] **Step 1: Create the cache boundary and catalog index**

Create `shared/assets/.gitignore` with:

```gitignore
.cache/
```

Create `shared/assets/catalog.yaml` with an initially empty but valid index:

```yaml
schema_version: "1"
assets: []
```

- [ ] **Step 2: Implement strict manifest loading**

In `fetch_assets.py`, define immutable data objects and reject malformed input before any network operation:

```python
@dataclass(frozen=True)
class Source:
    type: str
    url: str
    revision: str
    sha256: str
    archive: str
    strip_prefix: str | None


@dataclass(frozen=True)
class Asset:
    id: str
    revision: str
    manifest: Path
    source: Source
    entrypoints: dict[str, str]
```

`load_catalog()` must enforce schema version `"1"`, unique IDs matching
`^(world|model|map|recording)\.[a-z0-9][a-z0-9.-]*$`, manifest paths that stay
beneath the catalog root, pointer storage, a 64-character lowercase SHA-256,
supported archive values `tar.gz` or `zip`, and non-empty entrypoints.

- [ ] **Step 3: Implement safe download and extraction**

Use `urllib.request.urlopen` to stream into a temporary file below the
destination parent while updating `hashlib.sha256`. Reject a mismatch before
opening the archive. For tar files, reject absolute paths, `..` components,
symbolic links, and hard links. For zip files, reject absolute paths, `..`
components, and entries whose Unix mode identifies a symlink. Extract into a
temporary directory, apply the optional single `strip_prefix`, verify every
declared entrypoint with `Path.is_file()`, write `.asset.json` containing ID,
manifest revision, source revision, and checksum, then atomically rename the
temporary directory to the exact destination.

If the destination already has a matching `.asset.json` and all entrypoints,
print `cached: <asset-id>` and return without downloading. If validation fails,
leave the prior valid destination intact and remove only the newly-created
temporary directory.

- [ ] **Step 4: Implement the command-line contract**

The command must support:

```text
python3 fetch_assets.py world.aws-small-house
python3 fetch_assets.py world.aws-small-house --destination /opt/robium/assets/world.aws-small-house
python3 fetch_assets.py --list
```

Without `--destination`, resolve to
`shared/assets/.cache/<asset-id>/<source-revision>/`. Permit
`--destination` only when exactly one asset ID is supplied. Print the resolved
entrypoint paths on success and return non-zero with a concise message for
unknown IDs, invalid YAML, unsafe archives, checksum mismatches, or missing
entrypoints.

- [ ] **Step 5: Document the ownership and storage rules**

Write `shared/assets/README.md` with the asset-ID grammar, 5/25 MiB budgets,
pointer versus vendored policy, cache layout, app declaration shape, exact CLI
examples above, map-promotion checklist, and the rule that a `.foxe`, world,
or map is never uploaded or committed automatically.

- [ ] **Step 6: Run bounded static checks**

Run:

```bash
python3 -m py_compile shared/assets/scripts/fetch_assets.py
python3 -c 'import yaml; yaml.safe_load(open("shared/assets/catalog.yaml")); print("CATALOG YAML OK")'
```

If host Python lacks PyYAML, run the YAML check through:

```bash
uv run --with 'pyyaml>=6,<7' python -c 'import yaml; yaml.safe_load(open("shared/assets/catalog.yaml")); print("CATALOG YAML OK")'
```

Expected: both commands exit 0. These are syntax/configuration checks, not an
automated test suite.

- [ ] **Step 7: Commit the shared resolver**

```bash
git add shared/assets
git commit -m "feat(shared): add robotics asset catalog"
```

### Task 2: Register the House and Warehouse worlds

**Files:**
- Modify: `shared/assets/catalog.yaml`
- Create: `shared/assets/worlds/aws-small-house/asset.yaml`
- Create: `shared/assets/worlds/aws-small-house/LICENSE`
- Create: `shared/assets/worlds/tugbot-warehouse/asset.yaml`
- Create: `shared/assets/worlds/tugbot-warehouse/LICENSE`

**Interfaces:**
- Consumes: Task 1's version-1 manifest parser and safe archive resolver.
- Produces: `world.aws-small-house` with entrypoint `worlds/small_house.world` and `world.tugbot-warehouse` with entrypoint `tugbot_warehouse.sdf`.

- [ ] **Step 1: Calculate the pinned AWS archive checksum**

Download the already-selected immutable commit into a temporary directory and
capture its digest:

```bash
asset_tmp=$(mktemp -d /tmp/robium-aws-house.XXXXXX)
curl --fail --location --silent --show-error \
  https://github.com/aws-robotics/aws-robomaker-small-house-world/archive/ff9631ca6d1db9c1ba656498151464b5ab74aafe.tar.gz \
  --output "$asset_tmp/aws-small-house.tar.gz"
shasum -a 256 "$asset_tmp/aws-small-house.tar.gz"
```

The verified digest on 2026-08-15 is
`e459bd9d7bdabdfc40f8afc6770ceb1d774316e5da94a1048f036baa7388b2d9`.
The command must print that exact value before proceeding. Do not substitute a
branch, floating tag, or checksum copied from an unrelated archive URL.

- [ ] **Step 2: Add the AWS Small House manifest**

Create the manifest with these fixed values plus the digest from Step 1:

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
  sha256: e459bd9d7bdabdfc40f8afc6770ceb1d774316e5da94a1048f036baa7388b2d9
  archive: tar.gz
  strip_prefix: aws-robomaker-small-house-world-ff9631ca6d1db9c1ba656498151464b5ab74aafe
entrypoints:
  world: worlds/small_house.world
```

Copy the MIT license text from that exact upstream commit into `LICENSE` and
retain its copyright notice.

- [ ] **Step 3: Add the versioned Tugbot Warehouse manifest**

Use the version-2 Fuel zip URL verified on 2026-08-15. Its downloaded SHA-256
was `22af262814fe01326723b4e21457869470d1d3aaa10db7abc47e3536d13adfbb`:

```yaml
schema_version: "1"
id: world.tugbot-warehouse
kind: world
name: Tugbot in Warehouse
revision: "1"
storage: pointer
license:
  id: CC-BY-NC-ND-4.0
  file: LICENSE
  url: https://creativecommons.org/licenses/by-nc-nd/4.0/
source:
  type: fuel-world-zip
  repository: https://fuel.gazebosim.org/1.0/OpenRobotics/worlds/Tugbot%20in%20Warehouse
  revision: "2"
  url: https://fuel.gazebosim.org/1.0/OpenRobotics/worlds/Tugbot%20in%20Warehouse/2/Tugbot%20in%20Warehouse.zip
  sha256: 22af262814fe01326723b4e21457869470d1d3aaa10db7abc47e3536d13adfbb
  archive: zip
  strip_prefix: null
entrypoints:
  world: tugbot_warehouse.sdf
```

Store the official CC BY-NC-ND 4.0 license text in `LICENSE`. The README and
catalog must visibly call this a restricted non-commercial, no-derivatives
asset rather than implying that all shared assets are MIT.

- [ ] **Step 4: Index both manifests**

Replace the empty catalog list with:

```yaml
schema_version: "1"
assets:
  - id: world.aws-small-house
    kind: world
    name: AWS RoboMaker Small House
    storage: pointer
    manifest: worlds/aws-small-house/asset.yaml
  - id: world.tugbot-warehouse
    kind: world
    name: Tugbot in Warehouse
    storage: pointer
    manifest: worlds/tugbot-warehouse/asset.yaml
```

- [ ] **Step 5: Fetch and inspect both registered assets**

Run the resolver for each ID using PyYAML 6.x, then inspect the reported
entrypoint paths and vendored byte count:

```bash
uv run --with 'pyyaml>=6,<7' shared/assets/scripts/fetch_assets.py world.aws-small-house
uv run --with 'pyyaml>=6,<7' shared/assets/scripts/fetch_assets.py world.tugbot-warehouse
du -sh shared/assets/.cache
find shared/assets -path '*/.cache' -prune -o -type f -print
```

Expected: both commands report their declared world file, `.cache` remains
untracked, and tracked assets contain metadata/licenses only. This is a real
download/integrity check, not an automated test.

- [ ] **Step 6: Commit the two world records**

```bash
git add shared/assets/catalog.yaml shared/assets/README.md shared/assets/worlds
git commit -m "feat(shared): catalog indoor navigation worlds"
```

### Task 3: Consume shared worlds from robot-navigation

**Files:**
- Modify: `robot-navigation/robium-app.yaml`
- Modify: `robot-navigation/docker/Dockerfile`
- Modify: `robot-navigation/docker/Dockerfile.dockerignore`
- Modify: `robot-navigation/src/robot_nav_bringup/launch/sim.launch.py`
- Delete: `robot-navigation/scripts/fetch_aws_small_house.py`

**Interfaces:**
- Consumes: Task 2 asset IDs and resolver CLI.
- Produces: image paths `/opt/robium/assets/world.aws-small-house/` and `/opt/robium/assets/world.tugbot-warehouse/`, selected through the unchanged app world values `furnished_house` and `tugbot_warehouse`.

- [ ] **Step 1: Declare the app's required world IDs**

Add this top-level section to `robium-app.yaml` after `requirements`:

```yaml
assets:
  worlds:
    - world.aws-small-house
    - world.tugbot-warehouse
  maps: []
```

- [ ] **Step 2: Include the shared catalog in the Docker build context**

Add these allow-list lines before the cache/artifact exclusions in
`Dockerfile.dockerignore`:

```dockerignore
!shared/assets/
!shared/assets/**
```

The nested `shared/assets/.gitignore` keeps local cache content out of Git;
the Docker ignore must additionally exclude `shared/assets/.cache/**` so local
downloads cannot inflate the build context.

- [ ] **Step 3: Materialize both worlds during the image build**

Install `python3-yaml`, copy the shared catalog to
`/opt/robium/asset-catalog`, and replace the app-owned AWS fetch block with:

```dockerfile
COPY shared/assets /opt/robium/asset-catalog
RUN python3 /opt/robium/asset-catalog/scripts/fetch_assets.py \
      --catalog /opt/robium/asset-catalog/catalog.yaml \
      --destination /opt/robium/assets/world.aws-small-house \
      world.aws-small-house \
 && python3 /opt/robium/asset-catalog/scripts/fetch_assets.py \
      --catalog /opt/robium/asset-catalog/catalog.yaml \
      --destination /opt/robium/assets/world.tugbot-warehouse \
      world.tugbot-warehouse
```

Remove `ARG AWS_SMALL_HOUSE_COMMIT` and the old
`scripts/fetch_aws_small_house.py` invocation. Delete that app-owned script
only after Docker uses the shared resolver.

- [ ] **Step 4: Resolve both worlds from the packaged asset root**

In `sim.launch.py`, replace `FUEL_ROOT` and `AWS_SMALL_HOUSE_ROOT` with:

```python
ROBIUM_ASSETS_ROOT = Path(os.environ.get(
    'ROBIUM_ASSETS_ROOT', '/opt/robium/assets'))
AWS_SMALL_HOUSE_ROOT = ROBIUM_ASSETS_ROOT / 'world.aws-small-house'
TUGBOT_WAREHOUSE_WORLD = (
    ROBIUM_ASSETS_ROOT / 'world.tugbot-warehouse' / 'tugbot_warehouse.sdf')
```

Return `str(TUGBOT_WAREHOUSE_WORLD)` for `tugbot_warehouse`; retain the
existing spawn pose and House preparation logic. Add a missing-file error for
the warehouse equivalent to the existing House error. Keep Gazebo's Fuel cache
volume because the warehouse SDF can still reference external model assets.

- [ ] **Step 5: Run bounded integration checks**

Run:

```bash
python3 -m py_compile robot-navigation/src/robot_nav_bringup/launch/sim.launch.py
python3 -c 'import yaml; data=yaml.safe_load(open("robot-navigation/robium-app.yaml")); assert data["assets"]["worlds"] == ["world.aws-small-house", "world.tugbot-warehouse"]; print("APP ASSETS OK")'
git status --short -- robot-navigation/src/robot_nav_bringup/maps
```

Use `uv run --with 'pyyaml>=6,<7'` for the YAML command if necessary. Expected:
Python syntax and the declaration pass, while map status is unchanged from the
start of the task.

- [ ] **Step 6: Commit the app integration**

```bash
git add robot-navigation/robium-app.yaml robot-navigation/docker/Dockerfile robot-navigation/docker/Dockerfile.dockerignore robot-navigation/src/robot_nav_bringup/launch/sim.launch.py robot-navigation/scripts/fetch_aws_small_house.py
git commit -m "refactor(robot-navigation): consume shared world assets"
```

### Task 4: Establish the future writable-map boundary

**Files:**
- Create: `robot-navigation/data/maps/.gitignore`
- Modify: `robot-navigation/README.md`
- Modify: `robot-navigation/docs/architecture-brief.md`
- Modify: `REGISTRY.md`

**Interfaces:**
- Consumes: approved policy and shared asset IDs.
- Produces: documented local writable location without changing `/ws/maps` or touching current map files.

- [ ] **Step 1: Create the gitignored data directory**

Create `robot-navigation/data/maps/.gitignore` with:

```gitignore
*
!.gitignore
```

Do not add a compose volume for this directory in this implementation.

- [ ] **Step 2: Update operator and architecture documentation**

Update the README to distinguish:

- shared world metadata/pointers in `shared/assets/`;
- downloaded payloads in its gitignored `.cache/`;
- current maps still written beneath `src/robot_nav_bringup/maps/`;
- `data/maps/` as the approved future writable location;
- explicit promotion into `shared/assets/maps/` only after map review;
- AWS Small House as MIT and Tugbot Warehouse as CC BY-NC-ND 4.0.

Replace the architecture brief's statement that maps are committed by default.
Document the stable IDs, pointer materialization path, 5/25 MiB limits, and the
fact that the current mount remains temporarily unchanged to preserve local
maps.

- [ ] **Step 3: Update the registry card**

Keep the current runtime-validation-only smoke status and add shared pinned
world assets to the robot-navigation registry description. Do not claim a
runtime pass unless one was actually performed.

- [ ] **Step 4: Verify documentation and map preservation**

Run:

```bash
rg -n "shared/assets|world.aws-small-house|world.tugbot-warehouse|data/maps|CC BY-NC-ND" robot-navigation/README.md robot-navigation/docs/architecture-brief.md REGISTRY.md
git status --short -- robot-navigation/src/robot_nav_bringup/maps
git diff --check
```

Expected: all boundaries and both IDs are documented, no tracked map change is
present, and the diff has no whitespace errors.

- [ ] **Step 5: Commit the storage boundary documentation**

```bash
git add robot-navigation/data/maps/.gitignore robot-navigation/README.md robot-navigation/docs/architecture-brief.md REGISTRY.md
git commit -m "docs(robot-navigation): define shared asset boundaries"
```

### Task 5: Perform final non-test verification

**Files:**
- Inspect: `shared/assets/**`
- Inspect: `robot-navigation/robium-app.yaml`
- Inspect: `robot-navigation/docker/Dockerfile`
- Inspect: `robot-navigation/src/robot_nav_bringup/launch/sim.launch.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: evidence for manifest integrity, source safety, size budgets, and map preservation; no automated test claim.

- [ ] **Step 1: Re-run fresh catalog and fetch checks**

Run both fetches into a new temporary directory so the check does not rely on
the shared cache:

```bash
verify_root=$(mktemp -d /tmp/robium-assets-verify.XXXXXX)
uv run --with 'pyyaml>=6,<7' shared/assets/scripts/fetch_assets.py \
  --destination "$verify_root/aws" world.aws-small-house
uv run --with 'pyyaml>=6,<7' shared/assets/scripts/fetch_assets.py \
  --destination "$verify_root/tugbot" world.tugbot-warehouse
test -f "$verify_root/aws/worlds/small_house.world"
test -f "$verify_root/tugbot/tugbot_warehouse.sdf"
```

Expected: both checks exit 0 and print their verified checksums and
entrypoints. The temporary directory may be discarded manually after review;
do not use a broad recursive delete command in the repository.

- [ ] **Step 2: Check size and source-tree boundaries**

Run:

```bash
find shared/assets -path 'shared/assets/.cache' -prune -o -type f -print0 \
  | xargs -0 du -ch | tail -1
git status --short -- robot-navigation/src/robot_nav_bringup/maps
git ls-files shared/assets | rg '/\.cache/' && exit 1 || true
git diff --check HEAD~4..HEAD
```

Expected: tracked payload is below 25 MiB, no cache file is tracked, the map
status matches the pre-implementation baseline, and the committed diff has no
whitespace errors.

- [ ] **Step 3: Record runtime verification honestly**

Do not run automated tests. If the maintainer chooses to rebuild now, run
`make build` and manually start House and Warehouse; record exactly which
worlds loaded. If the rebuild is deferred, report manifest/fetch verification
only and state that Docker/runtime validation remains pending.

- [ ] **Step 4: Inspect final repository state**

Run:

```bash
git log --oneline -5
git status --short --branch
```

Expected: only the pre-existing untracked saved-map directories remain in the
app worktree; no cache, archive, or temporary asset is staged.
