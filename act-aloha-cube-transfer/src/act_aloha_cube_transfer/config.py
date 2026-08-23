from __future__ import annotations

import os
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[2]
MODEL_REPO_ID = "lerobot/act_aloha_sim_transfer_cube_human"
MODEL_REVISION = "ba73b2766f1371cdc133ca4efb97eb090d744625"
MODEL_DIR = Path(
    os.environ.get(
        "ACT_ALOHA_MODEL_DIR",
        APP_ROOT / "outputs/model/official-transfer-cube",
    )
)
MODEL_SOURCE_DIR = APP_ROOT / "outputs/model/source" / MODEL_REVISION
MODEL_MANIFEST = MODEL_DIR / "manifest.json"
ENV_ID = "gym_aloha/AlohaTransferCube-v0"
DEFAULT_PORT = 8765
ACTION_CHUNK_SIZE = 100
EXECUTION_HORIZONS = (25, 50, 100)
MAX_EPISODE_STEPS = 300
DEMO_SESSION_SECONDS = 1800
DEMO_FLEET_BUDGET = 2
