import shutil
import threading

from act_aloha_cube_transfer import config
from act_aloha_cube_transfer.calibration import EVIDENCE_PATH
from act_aloha_cube_transfer.demo.episode_runner import EpisodeRunner
from act_aloha_cube_transfer.demo.theme import CSS, THEME
from act_aloha_cube_transfer.demo.ui import build_ui


def main() -> None:
    if not EVIDENCE_PATH.is_file():
        EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(config.APP_ROOT / "assets/evidence.json", EVIDENCE_PATH)
        print("installed the measured Robium reference evidence…", flush=True)
    print("loading official ACT policy + ALOHA environment…", flush=True)
    runner = EpisodeRunner()
    ui = build_ui(runner)
    ui.launch(
        server_name="0.0.0.0",
        server_port=int(__import__("os").environ.get("PORT", config.DEFAULT_PORT)),
        quiet=True,
        prevent_thread_lock=True,
        theme=THEME,
        css=CSS,
    )
    print("DEMO READY", flush=True)
    threading.Event().wait()


if __name__ == "__main__":
    main()
