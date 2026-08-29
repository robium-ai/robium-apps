import subprocess
import sys
from pathlib import Path


def test_live_patch_adds_capability_status_reset_and_stream(tmp_path):
    source = tmp_path / "play.py"
    output = tmp_path / "live_demo.py"
    source.write_text(
        'render_mode="rgb_array" if args_cli.video else None\n'
        '        env_cfg.scene.num_envs = args_cli.num_envs if args_cli.num_envs is not None else env_cfg.scene.num_envs\n'
        '        # reset environment\n'
        '        obs = env.get_observations()\n'
        '        try:\n'
        '            while simulation_app.is_running():\n'
        '                pass\n'
        '        except KeyboardInterrupt:\n'
        '            pass\n'
    )
    script = Path(__file__).parents[1] / "scripts" / "live_demo_patch.py"
    result = subprocess.run(
        [sys.executable, str(script), "--play", str(source), "--output", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    patched = output.read_text()
    assert 'os.environ.get("DEMO_CAPABILITY"' in patched
    assert 'route.startswith("/status")' in patched
    assert 'route.startswith("/reset")' in patched
    assert 'multipart/x-mixed-replace' in patched
