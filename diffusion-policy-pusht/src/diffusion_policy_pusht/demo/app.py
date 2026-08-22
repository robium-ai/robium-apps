"""Demo entry point: load the ladder, serve the Gradio UI, print DEMO READY.

Deliberately session-blind: one process serves one demo. Per-user isolation
is the container boundary — whoever runs containers (a website orchestrator,
or nobody at all on a laptop) owns lifecycle, not this app. The only
orchestration surface is the DEMO READY log line, printed when checkpoints
are loaded and the server is accepting connections.
"""

import threading

from diffusion_policy_pusht import config
from diffusion_policy_pusht.demo.episode_runner import EpisodeRunner
from diffusion_policy_pusht.demo.ui import CSS, THEME, build_ui
from diffusion_policy_pusht.official import build_demo_manifest


def main() -> None:
    print("preparing official checkpoint + evidence…", flush=True)
    build_demo_manifest()
    print("loading policy + env…", flush=True)
    runner = EpisodeRunner()
    ui = build_ui(runner)
    ui.launch(
        server_name="0.0.0.0",
        server_port=config.DEMO_PORT,
        quiet=True,
        prevent_thread_lock=True,
        theme=THEME,
        css=CSS,
    )
    print("DEMO READY", flush=True)
    threading.Event().wait()  # serve until the process is stopped


if __name__ == "__main__":
    main()
