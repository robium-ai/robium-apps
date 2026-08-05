"""Demo entry point: load the ladder, serve the Gradio UI, print DEMO READY.

Deliberately session-blind: one process serves one demo. Per-user isolation
is the container boundary — whoever runs containers (a website orchestrator,
or nobody at all on a laptop) owns lifecycle, not this app. The only
orchestration surface is the DEMO READY log line, printed when checkpoints
are loaded and the server is accepting connections.
"""

import threading

from imitation_manipulation import config
from imitation_manipulation.demo.episode_runner import EpisodeRunner
from imitation_manipulation.demo.ui import build_ui


def main() -> None:
    print("loading checkpoints + env…", flush=True)
    runner = EpisodeRunner()
    ui = build_ui(runner)
    ui.launch(
        server_name="0.0.0.0",
        server_port=config.DEMO_PORT,
        quiet=True,
        prevent_thread_lock=True,
    )
    print("DEMO READY", flush=True)
    threading.Event().wait()  # serve until the process is stopped


if __name__ == "__main__":
    main()
