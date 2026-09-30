"""Private ACT experiment: raw capture -> datasets -> checkpoint -> offline evaluation.

This module never opens Bluetooth, the live camera, or a joystick. Heavy imports
are local to commands so pure export/budget contracts can be tested cheaply.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import time
from itertools import pairwise
from pathlib import Path

TEST_CLIPS = {"20260926-130714-cd4efa74", "20260926-130719-750ddc6f"}
CAMERA = "observation.images.stackchan"
SEED = 42
CHUNK = 10
OWNER = "robium-admin"
BASE = "lego-stackchan-road-v1"
FLAVOR = "l4x1"


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def raw_episodes(root, *, selected=None, min_episodes=4, tilt_deg=None, episode_tilts_deg=None):
    episodes = []
    paths = [Path(p) / "episode.json" for p in selected] if selected is not None else list(Path(root).glob("*/episode.json"))
    if episode_tilts_deg is not None:
        ids = [p.parent.name for p in paths]
        if len(set(ids)) != len(ids) or set(episode_tilts_deg) != set(ids):
            raise ValueError("Per-episode camera tilts must match every selected clip exactly")
        if not all(math.isfinite(v) and 0 <= v <= 85 for v in episode_tilts_deg.values()):
            raise ValueError("Invalid per-episode camera tilt")
    for path in sorted(paths):
        expected_tilt = episode_tilts_deg[path.parent.name] if episode_tilts_deg is not None else tilt_deg
        meta = json.loads(path.read_text())
        if meta.get("training_eligible") is False or meta.get("capture_purpose") == "inference-review":
            raise ValueError(f"Inference-only recording is excluded from training: {path.parent.name}")
        if path.parent.name in TEST_CLIPS or meta.get("result") != "saved" or meta["camera_only"]:
            continue
        if (meta["throttle_power_percent"], meta["steering_power_percent"]) != (75, 25):
            raise ValueError(f"Incompatible motor mapping: {path.parent.name}")
        rows = [json.loads(line) for line in (path.parent / "events.jsonl").read_text().splitlines()]
        frames = [r for r in rows if r["kind"] == "frame"]
        if not frames or len(frames) != meta["frames"]:
            raise ValueError(f"Empty/unclosed or inconsistent episode: {path.parent.name}")
        previous = None
        boundaries = [0]
        for index, frame in enumerate(frames):
            sample = frame.get("joystick", {})
            if sample.get("source") == "policy" or sample.get("control_mode") == "model":
                raise ValueError(f"Model-generated action is not an expert demonstration: {path.parent.name}")
            if meta.get("policy_checkpoint") and sample.get("control_mode") not in ("manual", "manual override"):
                raise ValueError(f"Unknown control source: {path.parent.name}")
            if expected_tilt is not None:
                pose = sample.get("head_action", [])
                if (len(pose) != 2 or not all(math.isfinite(v) for v in pose)
                        or abs(pose[0]) > .001 or abs(pose[1] * 85 - expected_tilt) > .1):
                    raise ValueError(f"Camera tilt differs from selection: {path.parent.name}")
            action = frame.get("action")
            if (not frame.get("action_valid") or action is None or len(action) != 2
                    or not all(math.isfinite(x) and abs(x) <= 1 for x in action)):
                raise ValueError(f"Invalid paired action: {path.parent.name}")
            if not frame["joystick"]["controller_connected"] or not frame["joystick"]["record_held"]:
                raise ValueError(f"Frame outside controller hold: {path.parent.name}")
            if frame["joystick"]["t"] > frame["estimated_capture_t"]:
                raise ValueError("Future joystick sample")
            if not meta["started_monotonic"] <= frame["estimated_capture_t"] < meta["ended_monotonic"]:
                raise ValueError("Frame outside recording boundaries")
            if tuple(frame.get(k) for k in ("width", "height", "jpeg_quality", "target_fps")) != (320, 240, 85, 10):
                raise ValueError("Camera profile changed")
            if previous and (frame["sequence"] != previous["sequence"] + 1
                             or frame["stream_generation"] != previous["stream_generation"]
                             or frame["estimated_capture_t"] - previous["estimated_capture_t"] > .2
                             or frame["recording_segment"] != previous["recording_segment"]):
                boundaries.append(index)
            previous = frame
        boundaries.append(len(frames))
        episodes.append({"id": path.parent.name, "path": path.parent, "meta": meta, "frames": frames,
                         "segments": list(pairwise(boundaries))})
    if len(episodes) < min_episodes:
        raise ValueError(f"Need at least {min_episodes} complete driving episodes")
    return episodes


def split_episodes(episodes):
    shuffled = list(episodes)
    random.Random(SEED).shuffle(shuffled)
    count = max(1, round(len(shuffled) * .2))
    return {"train": shuffled[count:], "val": shuffled[:count]}


def prepare(args):
    import numpy as np
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from PIL import Image

    root = args.bundle.resolve()
    if root.exists():
        raise ValueError(f"Export already exists: {root}. Use a new --bundle.")
    selection = json.loads(args.selection.read_text()) if getattr(args, "selection", None) else None
    episodes = raw_episodes(args.data, selected=selection["episodes"] if selection else None,
                            min_episodes=3 if selection else 4,
                            tilt_deg=selection["camera_tilt_deg"] if selection else None,
                            episode_tilts_deg=selection.get("episode_tilts_deg") if selection else None)
    if selection and selection.get("validation_episodes"):
        val_ids = set(selection["validation_episodes"])
        if not val_ids < {e["id"] for e in episodes}:
            raise ValueError("Validation must be a nonempty proper subset of selected clips")
        splits = {"train": [e for e in episodes if e["id"] not in val_ids],
                  "val": [e for e in episodes if e["id"] in val_ids]}
    else:
        splits = split_episodes(episodes)
    features = {
        CAMERA: {"dtype": "image", "shape": (240, 320, 3), "names": ["height", "width", "channels"]},
        "action": {"dtype": "float32", "shape": (2,), "names": ["throttle", "steer"]},
    }
    manifest = {"schema": 1, "seed": SEED, "fps": 10, "camera": CAMERA,
                "model_repo_id": f"{OWNER}/{args.repo_prefix}-act",
                "selection": selection,
                "initialization": "random" if selection else "imagenet_backbone",
                "action_names": ["throttle", "steer"], "input_state": "none",
                "excluded_button_tests": sorted(TEST_CLIPS), "splits": {},
                "source_hashes": {str(p): digest(p)
                                  for p in Path("src").rglob("*.py")},
                "training_code_sha256": digest(__file__), "created_unix": time.time(),
                "timestamp_policy": "10 Hz indexed training time; original capture/sample times preserved per frame"}
    for split, clips in splits.items():
        repo = f"{OWNER}/{args.repo_prefix}-{split}"
        dataset = LeRobotDataset.create(repo_id=repo, fps=10, features=features,
                                        root=root / split, robot_type="lego-diffdrive",
                                        use_videos=False, image_writer_threads=2, video_backend="pyav")
        provenance = []
        try:
            for episode in clips:
                frame_mapping = []
                segment_ends = {end for _, end in episode["segments"]}
                for index, f in enumerate(episode["frames"]):
                    image_path = episode["path"] / f["image"]
                    with Image.open(image_path) as image:
                        image.load()
                        if image.size != (320, 240):
                            raise ValueError(f"Wrong image dimensions: {image_path}")
                        rgb = np.asarray(image.convert("RGB"))
                    dataset.add_frame({CAMERA: rgb, "action": np.asarray(f["action"], dtype=np.float32),
                                       "task": episode["meta"]["task"]})
                    frame_mapping.append({"image": f["image"], "image_sha256": digest(image_path),
                                          "capture_t": f["estimated_capture_t"], "receipt_t": f["t"],
                                          "joystick_t": f["joystick"]["t"], "sequence": f["sequence"]})
                    if index + 1 in segment_ends:
                        dataset.save_episode()
                provenance.append({"id": episode["id"], "frames": frame_mapping,
                                   "contiguous_segments": episode["segments"],
                                   "episode_json_sha256": digest(episode["path"] / "episode.json"),
                                   "events_sha256": digest(episode["path"] / "events.jsonl"),
                                   "motor_mapping": {k: episode["meta"][k] for k in (
                                       "motor_ports", "throttle_gain", "steering_gain", "throttle_sign", "steer_sign")}})
                print(f"Exported {split}: {episode['id']} ({len(frame_mapping)} frames)", flush=True)
        finally:
            dataset.finalize()
        expected = sum(len(e["frames"]) for e in clips)
        loaded = LeRobotDataset(repo, root=root / split, video_backend="pyav")
        export_episodes = sum(len(e["segments"]) for e in clips)
        if len(loaded) != expected or loaded.num_episodes != export_episodes:
            raise RuntimeError("Export count mismatch")
        # Confirm storage round-trips images and paired actions without another
        # lossy encode; original timestamp detail lives in the manifest.
        offset = 0
        for episode in clips:
            for index in {0, len(episode["frames"]) // 2, len(episode["frames"]) - 1}:
                original = episode["frames"][index]
                sample = loaded[offset + index]
                with Image.open(episode["path"] / original["image"]) as image:
                    pixels = np.asarray(image.convert("RGB"))
                restored = (sample[CAMERA].numpy().transpose(1, 2, 0) * 255).round().astype(np.uint8)
                if not np.array_equal(restored, pixels) or not np.allclose(sample["action"].numpy(), original["action"]):
                    raise RuntimeError("Export changed a paired sample")
            offset += len(episode["frames"])
        manifest["splits"][split] = {"repo_id": repo, "episodes": export_episodes, "source_clip_count": len(clips), "frames": expected,
                                     "source_episodes": provenance}
    write_json(root / "manifest.json", manifest)
    print(json.dumps({s: {k: manifest["splits"][s][k] for k in ("episodes", "frames", "repo_id")}
                      for s in splits}, indent=2))


def device_only_batch(batch):
    """LeRobot 0.6.1 assumes OBS_STATE exists for device selection in ACT.

    The ACT configuration deliberately has no state feature/projection. This
    empty tensor supplies only the device; it contains no input information.
    Use the same adapter for training, validation, and checkpoint inference.
    """
    return {**batch, "observation.state": batch[CAMERA].new_empty((batch[CAMERA].shape[0], 0))}


def save_checkpoint(policy, pre, post, optimizer, path, step, experiment):
    import torch
    path.mkdir(parents=True, exist_ok=True)
    policy.save_pretrained(path)
    pre.save_pretrained(path, config_filename="policy_preprocessor.json")
    post.save_pretrained(path, config_filename="policy_postprocessor.json")
    torch.save({"step": step, "optimizer": optimizer.state_dict()}, path / "optimizer.pt")
    write_json(path / "experiment.json", {**experiment, "step": step, "adapter": "image-only-device-placeholder-v1"})


def load_checkpoint(path, device):
    from lerobot.policies.act.configuration_act import ACTConfig
    from lerobot.policies.act.modeling_act import ACTPolicy
    from lerobot.policies.factory import make_pre_post_processors
    cfg = ACTConfig.from_pretrained(path)
    cfg.device = device
    # The checkpoint includes the complete backbone. Reloading must not need
    # an unrelated torchvision download, including on an offline robot host.
    cfg.pretrained_backbone_weights = None
    policy = ACTPolicy.from_pretrained(path, config=cfg, strict=True)
    policy.to(device).eval()
    pre, post = make_pre_post_processors(policy.config, pretrained_path=path,
                                         preprocessor_overrides={"device_processor": {"device": device}},
                                         postprocessor_overrides={"device_processor": {"device": "cpu"}})
    if policy.config.robot_state_feature is not None:
        raise ValueError("Checkpoint must have no informative state input")
    return policy, pre, post


def evaluate_policy(policy, pre, post, dataset, mean_action, *, limit=0, shuffle_images=False):
    import numpy as np
    import torch
    from torch.utils.data import DataLoader, Subset

    count = min(len(dataset), limit) if limit else len(dataset)
    indices = list(range(count))
    permutation = list(indices)
    random.Random(SEED).shuffle(permutation)
    loader = DataLoader(Subset(dataset, indices), batch_size=8, shuffle=False, num_workers=0)
    predicted, targets, chunk_error = [], [], np.zeros(2)
    valid_count = 0
    policy.eval()
    offset = 0
    with torch.inference_mode():
        for batch in loader:
            target = batch["action"].clone().numpy()
            mask = ~batch["action_is_pad"].numpy()
            if shuffle_images:
                batch[CAMERA] = torch.stack([dataset[permutation[i]][CAMERA]
                                            for i in range(offset, offset + len(target))])
            # Inference never receives target actions, including future chunks.
            result = post(policy.predict_action_chunk(device_only_batch(pre({CAMERA: batch[CAMERA]})))).cpu().numpy()
            if not np.isfinite(result).all():
                raise ValueError("Non-finite inference output")
            error = np.abs(result - target)
            chunk_error += (error * mask[..., None]).sum(axis=(0, 1))
            valid_count += int(mask.sum())
            predicted.extend(result[:, 0].tolist())
            targets.extend(target[:, 0].tolist())
            offset += len(target)
    pred, truth = np.asarray(predicted), np.asarray(targets)
    first_error = np.abs(pred - truth)
    first_mae = first_error.mean(axis=0)
    baseline = np.abs(truth - np.asarray(mean_action)).mean(axis=0)
    return {"frames": count, "first_action_mae": first_mae.tolist(), "mean_first_action_mae": float(first_mae.mean()),
            "first_action_p95_absolute_error": np.percentile(first_error, 95, axis=0).tolist(),
            "first_action_max_absolute_error": first_error.max(axis=0).tolist(),
            "chunk_action_mae": (chunk_error / valid_count).tolist(), "mean_action_baseline_mae": baseline.tolist(),
            "zero_steering_baseline_mae": float(np.abs(truth[:, 1]).mean()),
            "predictions_outside_unit_range": int((np.abs(pred) > 1).any(axis=1).sum()),
            "maximum_range_overshoot": np.maximum(np.abs(pred) - 1, 0).max(axis=0).tolist(),
            "predicted": predicted, "target": targets}


def evaluation_artifacts(path, report):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    pred, target = np.asarray(report["predicted"]), np.asarray(report["target"])
    fig, axes = plt.subplots(2, 1, figsize=(12, 5), sharex=True)
    for axis, label, i in zip(axes, ("Throttle", "Steering"), (0, 1), strict=True):
        axis.plot(np.arange(len(target)) / 10, target[:, i], label="Demonstration", linewidth=1)
        axis.plot(np.arange(len(pred)) / 10, pred[:, i], label="ACT prediction", linewidth=1, alpha=.8)
        axis.set_ylabel(label)
        axis.legend(loc="upper right")
    axes[-1].set_xlabel("Held-out frames / 10 (whole clips concatenated for display)")
    fig.tight_layout()
    fig.savefig(path / "predictions.png", dpi=140)
    plt.close(fig)


def train(args):
    import numpy as np
    import torch
    from lerobot.configs.types import FeatureType, PolicyFeature
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    from lerobot.policies.act.configuration_act import ACTConfig
    from lerobot.policies.act.modeling_act import ACTPolicy
    from lerobot.policies.factory import make_pre_post_processors
    from torch.utils.data import DataLoader

    manifest = json.loads((args.bundle / "manifest.json").read_text())
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    if args.device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA not available on the requested GPU job")
    if args.device == "cuda":
        torch.cuda.manual_seed_all(SEED)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
        # Match LeRobot's standard CUDA trainer: faster float32 matmuls on
        # Ampere/newer GPUs, while keeping model and optimizer weights float32.
        torch.backends.cuda.matmul.allow_tf32 = True
    cfg = ACTConfig(device=args.device, chunk_size=CHUNK, n_action_steps=1,
                    input_features={CAMERA: PolicyFeature(type=FeatureType.VISUAL, shape=(3, 240, 320))},
                    output_features={"action": PolicyFeature(type=FeatureType.ACTION, shape=(2,))},
                    push_to_hub=False)
    if manifest.get("initialization") == "random":
        cfg.pretrained_backbone_weights = None
    timestamps = {"action": [i / 10 for i in range(CHUNK)]}
    datasets = {s: LeRobotDataset(manifest["splits"][s]["repo_id"], root=args.bundle / s,
                                  delta_timestamps=timestamps, video_backend="pyav") for s in ("train", "val")}
    policy = ACTPolicy(cfg).to(args.device)
    pre, post = make_pre_post_processors(cfg, dataset_stats=datasets["train"].meta.stats)
    optimizer = cfg.get_optimizer_preset().build(policy.get_optim_params())
    loader = DataLoader(datasets["train"], batch_size=args.batch_size, shuffle=True,
                        num_workers=0, generator=torch.Generator().manual_seed(SEED))
    mean = np.asarray(datasets["train"].meta.stats["action"]["mean"]).tolist()
    experiment = {"steps_requested": args.steps, "batch_size": args.batch_size, "seed": SEED,
                  "device": args.device, "chunk_size": CHUNK, "n_action_steps": 1,
                  "initialization": manifest.get("initialization", "imagenet_backbone"),
                  "environment": (manifest.get("selection") or {}).get("environment"),
                  "camera_tilt_deg": (manifest.get("selection") or {}).get("camera_tilt_deg", 0),
                  "cuda_tf32": args.device == "cuda",
                  "lerobot": "0.6.1", "torch": torch.__version__, "mean_action": mean,
                  "manifest_sha256": digest(args.bundle / "manifest.json"),
                  "dataset_revisions": manifest.get("revisions"), "training_code_sha256": digest(__file__),
                  "motor_power": {"throttle": 75, "steering": 25}, "informative_state": False}
    output = args.output
    if output.exists():
        raise ValueError(f"Output already exists: {output}")
    output.mkdir(parents=True)
    write_json(output / "experiment.json", experiment)
    log = (output / "metrics.jsonl").open("w")
    started = time.monotonic()
    best, stale_evals, iterator = math.inf, 0, iter(loader)
    best_report = None
    for step in range(1, args.steps + 1):
        try:
            batch = next(iterator)
        except StopIteration:
            iterator = iter(loader)
            batch = next(iterator)
        policy.train()
        optimizer.zero_grad(set_to_none=True)
        loss, details = policy.forward(device_only_batch(pre(batch)))
        if not torch.isfinite(loss):
            raise RuntimeError(f"Non-finite training loss at step {step}")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(policy.parameters(), 10)
        optimizer.step()
        if step == 1 or step % 20 == 0:
            record = {"step": step, "loss": loss.item(), "elapsed_s": time.monotonic() - started,
                      **details}
            log.write(json.dumps(record) + "\n")
            log.flush()
            if step == 1 or step % 100 == 0:
                print(json.dumps(record), flush=True)
        if step % args.eval_every == 0 or step == args.steps:
            report = evaluate_policy(policy, pre, post, datasets["val"], mean, limit=args.eval_limit)
            short = {k: v for k, v in report.items() if k not in ("predicted", "target")}
            print(json.dumps({"step": step, "validation": short}), flush=True)
            log.write(json.dumps({"step": step, "validation": short}) + "\n")
            log.flush()
            checkpoint = output / "checkpoints" / f"step-{step:06d}"
            save_checkpoint(policy, pre, post, optimizer, checkpoint, step, experiment)
            if report["mean_first_action_mae"] < best:
                best, stale_evals, best_report = report["mean_first_action_mae"], 0, report
                write_json(output / "best.json", {"checkpoint": str(checkpoint.relative_to(output)),
                                                   "step": step, "metrics": short})
            else:
                stale_evals += 1
            if args.upload_repo:
                upload_output(args.upload_repo, output, args.stage)
            if step >= 5000 and stale_evals >= 5:
                print("Early stop: no held-out improvement in five evaluations", flush=True)
                break
    log.close()
    chosen = json.loads((output / "best.json").read_text())
    policy, pre, post = load_checkpoint(output / chosen["checkpoint"], args.device)
    reloaded = evaluate_policy(policy, pre, post, datasets["val"], mean, limit=args.eval_limit)
    if abs(reloaded["mean_first_action_mae"] - best) > 1e-5:
        raise RuntimeError("Reloaded checkpoint changed predictions")
    shuffled = evaluate_policy(policy, pre, post, datasets["val"], mean,
                               limit=args.eval_limit, shuffle_images=True)
    best_report = reloaded
    best_report["shuffled_image_mae"] = shuffled["first_action_mae"]
    best_report["best_step"] = chosen["step"]
    best_report["reload_verified"] = True
    best_report["elapsed_s"] = time.monotonic() - started
    if args.device == "cuda":
        best_report["peak_gpu_memory_gb"] = torch.cuda.max_memory_allocated() / 1e9
    write_json(output / "evaluation.json", best_report)
    evaluation_artifacts(output, best_report)
    if args.upload_repo:
        upload_output(args.upload_repo, output, args.stage)
    print(json.dumps({k: v for k, v in best_report.items() if k not in ("predicted", "target")}), flush=True)


def upload_output(repo, output, stage):
    from huggingface_hub import HfApi
    api = HfApi()
    if not api.repo_info(repo).private:
        raise RuntimeError("Checkpoint destination is not private")
    api.upload_folder(repo_id=repo, folder_path=output, path_in_repo=f"runs/{stage}",
                      commit_message=f"Save {stage} checkpoint and offline metrics")


def cost_guard(hourly, seconds, budget):
    cost = hourly * seconds / 3600
    if not all(math.isfinite(x) for x in (hourly, seconds, budget)) or hourly <= 0 or seconds <= 0 or cost > budget:
        raise ValueError(f"Worst-case GPU cost ${cost:.2f} exceeds remaining budget ${budget:.2f}")
    return cost


def check_stage_retry(ledger, stage, statuses):
    for job in ledger["jobs"]:
        if job["stage"] != stage:
            continue
        if not job.get("id") or statuses.get(job["id"]) not in {"CANCELED", "ERROR"}:
            raise ValueError("Stage already submitted; inspect existing job rather than allocate twice")


def submit(args):
    import urllib.request

    from huggingface_hub import HfApi, get_token
    from lerobot.datasets.lerobot_dataset import LeRobotDataset

    bundle = args.bundle.resolve()
    manifest = json.loads((bundle / "manifest.json").read_text())
    api = HfApi()
    if api.whoami()["name"] != OWNER:
        raise ValueError(f"This experiment targets {OWNER}; current login differs")
    hardware = json.load(urllib.request.urlopen("https://huggingface.co/api/jobs/hardware"))
    # CLI and API can use different display field spellings; retain the raw
    # hardware response in the run ledger for an auditable price preflight.
    hardware_rows = hardware if isinstance(hardware, list) else hardware.get("hardware", [])
    selected = next(row for row in hardware_rows if row.get("name", row.get("flavor")) == args.flavor)
    if selected.get("unitLabel") == "minute":
        hourly = float(selected["unitCostUSD"]) * 60
    else:
        hourly = float(str(selected.get("cost/hour", selected.get("pricePerHour"))).replace("$", ""))
    timeout = 900 if args.stage == "smoke" else 14400
    ledger_path = bundle / "cloud.json"
    ledger = json.loads(ledger_path.read_text()) if ledger_path.exists() else {"budget_usd": 10, "jobs": []}
    statuses = {j["id"]: api.inspect_job(job_id=j["id"], namespace=OWNER).status.stage
                for j in ledger["jobs"] if j.get("id") and j["stage"] == args.stage}
    check_stage_retry(ledger, args.stage, statuses)
    reserved = sum(j["maximum_cost_usd"] for j in ledger["jobs"])
    maximum = cost_guard(hourly, timeout, ledger["budget_usd"] - reserved)
    repo = manifest.get("model_repo_id", f"{OWNER}/{BASE}-act")
    if args.stage == "smoke" and not ledger.get("source_revision"):
        # Never silently overwrite an existing experiment's repositories.
        from huggingface_hub.errors import RepositoryNotFoundError
        for destination, kind in ((repo, "model"), *[(s["repo_id"], "dataset") for s in manifest["splits"].values()]):
            try:
                api.repo_info(destination, repo_type=kind)
            except RepositoryNotFoundError:
                continue
            raise ValueError(f"Destination already exists: {destination}; use a new experiment ID")
        api.create_repo(repo_id=repo, private=True)
        revisions = {}
        for split, spec in manifest["splits"].items():
            dataset = LeRobotDataset(spec["repo_id"], root=bundle / split, video_backend="pyav")
            dataset.push_to_hub(private=True, license=None)
            info = api.repo_info(spec["repo_id"], repo_type="dataset")
            if not info.private:
                raise RuntimeError("Dataset destination is not private")
            revisions[split] = info.sha
        manifest["revisions"] = revisions
        write_json(bundle / "manifest.json", manifest)
    elif args.stage == "train":
        if not ledger.get("smoke_verified"):
            raise ValueError("Smoke checkpoint must be downloaded and verified before full training")
    if not api.repo_info(repo).private:
        raise ValueError("Experiment repository must be private")
    api.upload_folder(repo_id=repo, folder_path=Path(__file__).parent, path_in_repo="training",
                      ignore_patterns=[".venv/**", "__pycache__/**", "*.pyc"],
                      commit_message="Pin private training implementation and locked dependencies")
    api.upload_file(repo_id=repo, path_or_fileobj=bundle / "manifest.json", path_in_repo="run_inputs/manifest.json")
    ledger["source_revision"] = api.repo_info(repo).sha
    source_revision = ledger["source_revision"]
    steps = 200 if args.stage == "smoke" else 20000
    print(f"Submitting private {args.stage}: {args.flavor}, timeout {timeout}s, maximum ${maximum:.2f}", flush=True)
    # Reserve before crossing the paid API boundary. If the result is uncertain,
    # a missing job ID blocks retries rather than risking duplicate allocations.
    reservation = {"id": None, "stage": args.stage, "flavor": args.flavor,
                   "timeout_s": timeout, "hourly_usd": hourly, "maximum_cost_usd": maximum,
                   "submitted_unix": time.time(), "source_revision": source_revision}
    ledger["jobs"].append(reservation)
    ledger["model_repo"] = repo
    write_json(ledger_path, ledger)
    job = api.run_uv_job(script=str(Path(__file__).parent / "job.py"),
                         script_args=["--repo", repo, "--revision", source_revision, "--stage", args.stage,
                                      "--steps", str(steps)], flavor=args.flavor, timeout=timeout,
                         secrets={"HF_TOKEN": get_token()}, namespace=OWNER,
                         name=f"lego-road-{args.stage}", labels={"app": "lego-stackchan-drive", "stage": args.stage})
    reservation["id"] = job.id
    write_json(ledger_path, ledger)
    print(f"Job ID: {job.id}\nhttps://huggingface.co/jobs/{OWNER}/{job.id}", flush=True)


def evaluate(args):
    import torch
    from lerobot.datasets.lerobot_dataset import LeRobotDataset
    manifest = json.loads((args.bundle / "manifest.json").read_text())
    policy, pre, post = load_checkpoint(args.checkpoint, args.device)
    validation = LeRobotDataset(manifest["splits"]["val"]["repo_id"], root=args.bundle / "val",
                                delta_timestamps={"action": [i / 10 for i in range(CHUNK)]}, video_backend="pyav")
    experiment = json.loads((args.checkpoint / "experiment.json").read_text())
    report = evaluate_policy(policy, pre, post, validation, experiment["mean_action"], limit=args.limit)
    timings = []
    image = validation[0][CAMERA].unsqueeze(0)
    with torch.inference_mode():
        for i in range(25):
            start = time.monotonic()
            post(policy.predict_action_chunk(device_only_batch(pre({CAMERA: image}))))
            if args.device == "mps":
                torch.mps.synchronize()
            if i >= 5:
                timings.append((time.monotonic() - start) * 1000)
    report["inference_median_ms"] = sorted(timings)[len(timings) // 2]
    report["inference_p95_ms"] = sorted(timings)[math.ceil(len(timings) * .95) - 1]
    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "evaluation.json", report)
    evaluation_artifacts(args.output, report)
    if args.verify_smoke:
        if (experiment["steps_requested"] != 200 or experiment["device"] != "cuda"
                or experiment["manifest_sha256"] != digest(args.bundle / "manifest.json")):
            raise ValueError("Only the matching 200-step CUDA checkpoint can verify the paid smoke stage")
        ledger_path = args.bundle / "cloud.json"
        ledger = json.loads(ledger_path.read_text())
        ledger["smoke_verified"] = True
        ledger["smoke_verification"] = {"checkpoint": str(args.checkpoint), "device": args.device,
                                         "frames": report["frames"], "verified_unix": time.time()}
        write_json(ledger_path, ledger)
    print(json.dumps({k: v for k, v in report.items() if k not in ("predicted", "target")}), flush=True)


def fetch(args):
    from huggingface_hub import HfApi, snapshot_download

    ledger = json.loads((args.bundle / "cloud.json").read_text())
    info = HfApi().repo_info(ledger["model_repo"])
    if not info.private:
        raise RuntimeError("Checkpoint repository is not private")
    root = args.bundle / f"cloud-{args.stage}"
    prefix = f"runs/{args.stage}"
    snapshot_download(ledger["model_repo"], revision=info.sha, local_dir=root,
                      allow_patterns=[f"{prefix}/best.json", f"{prefix}/evaluation.json",
                                      f"{prefix}/predictions.png", f"{prefix}/experiment.json",
                                      f"{prefix}/metrics.jsonl"])
    best = json.loads((root / prefix / "best.json").read_text())
    snapshot_download(ledger["model_repo"], revision=info.sha, local_dir=root,
                      allow_patterns=[f"{prefix}/{best['checkpoint']}/*"], ignore_patterns=["**/optimizer.pt"])
    checkpoint = root / prefix / best["checkpoint"]
    write_json(root / "download.json", {"repo": ledger["model_repo"], "revision": info.sha,
                                        "checkpoint": str(checkpoint.resolve()), "stage": args.stage})
    print(f"Downloaded checkpoint: {checkpoint}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prepare_parser = sub.add_parser("prepare")
    prepare_parser.add_argument("--data", type=Path, default=Path("data"))
    prepare_parser.add_argument("--bundle", type=Path, default=Path(".local/training/road-v1"))
    prepare_parser.add_argument("--repo-prefix", default=BASE)
    prepare_parser.add_argument("--selection", type=Path, help="Explicit environment/pose/clip selection JSON")
    for name in ("smoke", "train"):
        p = sub.add_parser(name)
        p.add_argument("--bundle", type=Path, default=Path(".local/training/road-v1"))
        p.add_argument("--output", type=Path, required=True)
        p.add_argument("--device", default="cpu" if name == "smoke" else "cuda")
        p.add_argument("--steps", type=int, default=1 if name == "smoke" else 20000)
        p.add_argument("--batch-size", type=int, default=2 if name == "smoke" else 8)
        p.add_argument("--eval-every", type=int, default=1000)
        p.add_argument("--eval-limit", type=int, default=4 if name == "smoke" else 0)
        p.add_argument("--upload-repo")
        p.add_argument("--stage", default=name)
    p = sub.add_parser("submit")
    p.add_argument("--bundle", type=Path, default=Path(".local/training/road-v1"))
    p.add_argument("--stage", choices=("smoke", "train"), default="smoke")
    p.add_argument("--flavor", default=FLAVOR)
    p = sub.add_parser("fetch")
    p.add_argument("--bundle", type=Path, default=Path(".local/training/road-v1"))
    p.add_argument("--stage", choices=("smoke", "train"), default="train")
    p = sub.add_parser("evaluate")
    p.add_argument("--bundle", type=Path, default=Path(".local/training/road-v1"))
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--device", default="mps")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--verify-smoke", action="store_true")
    args = parser.parse_args()
    {"prepare": prepare, "smoke": train, "train": train, "submit": submit,
     "evaluate": evaluate, "fetch": fetch}[args.command](args)


if __name__ == "__main__":
    main()
