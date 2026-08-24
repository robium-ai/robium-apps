# Test assets

`fixtures/` contains three compact first-frame RGB observations from official
LIBERO demonstrations for the task prompt `put the bowl on the plate`. They are
recorded replay inputs for free tests, not Robium-generated scenes and not
claims about live rollout outcomes.

The UI state IDs 0, 1, and 2 select LIBERO's official fixed initial states at
runtime. `states.json` records that mapping. The fixture images only keep the
fake runner deterministic on machines that cannot load Pi0.5 or LIBERO.

Run `scripts/fetch_test_assets.sh` to re-fetch the files from the immutable
dataset revision, then compare their hashes with `MANIFEST.yaml`.
