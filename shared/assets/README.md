# Shared robotics assets

This directory is the central catalog for reusable simulation worlds, robot
models, maps, waypoint sets, and recordings used by applications in this
repository. Apps refer to stable IDs such as `world.aws-small-house` in their
`robium-app.yaml`; they do not depend on another app's directory.

## Storage modes

- **Pointer:** keep metadata, an immutable upstream revision, SHA-256, license,
  and entrypoints in Git. Download the payload when it is needed.
- **Vendored:** commit a reviewed payload only when it is at most 5 MiB and the
  complete tracked payload beneath this directory remains at most 25 MiB.
- **Local:** keep user-generated maps and recordings in an app's gitignored
  data directory until somebody explicitly promotes a reviewed copy.

Downloaded pointer assets are materialized beneath
`.cache/<asset-id>/<source-revision>/` and are never committed. The cache can
be deleted and reconstructed entirely from `catalog.yaml` and each
`asset.yaml`.

## Asset IDs

IDs match `<kind>.<descriptive-name>[.<variant>]`, where kind is `world`,
`model`, `map`, or `recording`. An incompatible change gets a new ID; changing
only a pinned upstream revision increments the manifest revision.

## Commands

The resolver uses PyYAML 6.x:

```bash
uv run --with 'pyyaml>=6,<7' shared/assets/scripts/fetch_assets.py --list
uv run --with 'pyyaml>=6,<7' shared/assets/scripts/fetch_assets.py world.aws-small-house
uv run --with 'pyyaml>=6,<7' shared/assets/scripts/fetch_assets.py \
  world.aws-small-house --destination /opt/robium/assets/world.aws-small-house
```

Applications declare only what they consume:

```yaml
assets:
  worlds:
    - world.aws-small-house
  maps: []
```

## Promoting a map

1. Finish mapping so its PGM, YAML, and waypoint sidecar are complete.
2. Select one named map and record the world, robot, sensors, and generator.
3. Confirm localization and one navigation goal in Lichtblick.
4. Copy a reviewed version into `shared/assets/maps/<asset-id>/` without
   modifying the original local map.
5. Normalize filenames and the YAML image reference.
6. Add provenance, derivation, license, and file roles to `asset.yaml`.
7. Add the asset to `catalog.yaml` and the consuming app declaration.

Nothing in this workflow automatically uploads or commits a world, map,
recording, or `.foxe` file.

## Licenses

Licenses are per asset, not per catalog. Read each manifest before reuse.
`world.tugbot-warehouse`, for example, is restricted to CC BY-NC-ND 4.0 and
must not be treated as a permissive Robium-owned asset.
