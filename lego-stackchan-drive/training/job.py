# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = ["huggingface-hub==1.24.0"]
# ///
"""HF Jobs bootstrap; the actual environment comes from the private uv.lock."""
import argparse
import json
import subprocess
from pathlib import Path

from huggingface_hub import snapshot_download

parser = argparse.ArgumentParser()
parser.add_argument("--repo", required=True)
parser.add_argument("--revision", required=True)
parser.add_argument("--stage", required=True)
parser.add_argument("--steps", required=True)
args = parser.parse_args()
root = Path("/tmp/lego-training")
snapshot_download(args.repo, revision=args.revision, local_dir=root,
                  allow_patterns=["training/**", "run_inputs/manifest.json"])
manifest_path = root / "run_inputs/manifest.json"
manifest = json.loads(manifest_path.read_text())
bundle = root / "bundle"
bundle.mkdir()
for split, spec in manifest["splits"].items():
    snapshot_download(spec["repo_id"], repo_type="dataset", revision=manifest["revisions"][split],
                      local_dir=bundle / split)
(bundle / "manifest.json").write_text(manifest_path.read_text())
subprocess.run([
    "uv", "run", "--project", str(root / "training"), "--locked", "python",
    str(root / "training/pipeline.py"), "train", "--bundle", str(bundle),
    "--output", str(root / "output"), "--device", "cuda", "--steps", args.steps,
    "--batch-size", "8", "--eval-every", "1000", "--stage", args.stage,
    "--upload-repo", args.repo,
], check=True)
