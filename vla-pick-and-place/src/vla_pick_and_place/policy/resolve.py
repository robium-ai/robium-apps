"""Fail loudly, and early, on a checkpoint that cannot produce a rollout.

`SmolVLAPolicy.from_pretrained` is where a bad checkpoint blows up today, and
it does so several frames deep in `huggingface_hub` with a message about
repository resolution — by which point the demo gateway has already told the
visitor it is starting, or `make eval` has spent a minute loading the base VLM.

Both failures this app has actually hit are cheap to detect up front:

  * **Wrong namespace.** HF Jobs pushes the trained model to the *submitting
    user's* namespace, never the org's, regardless of `--policy.repo_id`.
    `DEMO_CHECKPOINT` read `robium/train_2026-07-15_08-09-36` for two weeks;
    the artifact was always at `robium-admin/train_2026-07-15_08-09-36`.
  * **Weights-less repo.** A job that dies after writing its config but
    before pushing weights leaves a repo that resolves fine and contains only
    `train_config.json` (`robium-admin/train_2026-08-04_05-35-54` is one).
    "The repo exists" is not the check; "the weights exist" is.
"""

from pathlib import Path

# The file lerobot actually loads the policy tensors from. A checkpoint dir
# without it is a directory, not a checkpoint.
WEIGHTS_FILE = "model.safetensors"


class CheckpointError(RuntimeError):
    """A checkpoint reference that cannot be rolled out, with the fix named."""


def _hub_files(repo_id: str) -> list[str]:
    from huggingface_hub import HfApi

    return list(HfApi().list_repo_files(repo_id))


def resolve_checkpoint(reference: str, _lister=_hub_files) -> str:
    """Return `reference` unchanged if it can be loaded; else raise.

    Accepts a local checkpoint directory or a Hub repo id. `_lister` is a seam
    for tests — production always uses the real Hub listing.
    """
    local = Path(reference)
    if local.exists():
        if not (local / WEIGHTS_FILE).is_file():
            raise CheckpointError(
                f"{reference} has no model weights ({WEIGHTS_FILE} missing).\n"
                "That directory is not a checkpoint. If this is a training "
                "output dir, the checkpoint lives one level deeper, e.g. "
                "checkpoints/000005/pretrained_model."
            )
        return reference

    try:
        files = _lister(reference)
    except Exception as exc:  # noqa: BLE001 — any Hub failure means "unusable"
        raise CheckpointError(
            f"cannot resolve checkpoint {reference!r} on the Hub ({exc}).\n"
            "Check the namespace first: HF Jobs pushes the trained model to "
            "the SUBMITTING USER's namespace, not an org's, and it ignores "
            "--policy.repo_id. A run submitted by robium-admin lands at "
            "robium-admin/train_<timestamp>, not robium/train_<timestamp>. "
            "Read the 'Model pushed to <url>' line in the job log for the "
            "real id.\n"
            "If the repo is private, `hf auth login` first."
        ) from exc

    if WEIGHTS_FILE not in files:
        raise CheckpointError(
            f"{reference} exists on the Hub but has no model weights "
            f"({WEIGHTS_FILE} missing; it holds {sorted(files)}).\n"
            "This is what a training job that died before pushing weights "
            "leaves behind. Re-run the fine-tune; do not point the demo here."
        )
    return reference
