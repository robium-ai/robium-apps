"""robium workspace shell for Gradio + Rerun demo apps (reusable reference copy).

The Rerun-side counterpart to `shared/lichtblick-dashboard`: that one docks a
control panel inside Lichtblick for ROS apps, this one wraps a Rerun viewer
and a control rail for learning apps. Apps **vendor** this file (copy it next
to their demo UI) the same way they vendor `demo_gateway.py`, so each app
stays self-contained; this copy is the source they vendor from.

What it gives you:

    with workspace("my demo") as ui:
        bar = top_bar()                      # brand · health · meta
        with split():
            viewer = rerun_viewer()          # fills all remaining space
            with rail():
                with section("instruction"):
                    ...

Layout contract: the page is exactly one viewport tall and never scrolls.
The viewer takes every pixel the bar and rail do not. Only the rail may
scroll, and only internally.

Why CSS rather than a Gradio theme: the hard part here is forcing height
down Gradio's wrapper chain (see dashboard.css), which no theme API exposes.
"""

from contextlib import contextmanager
from pathlib import Path

import gradio as gr

CSS_PATH = Path(__file__).with_name("dashboard.css")

# Bar states -> the CSS modifier that colors the dot. Kept as data so an app
# can add its own without touching the stylesheet's meaning.
STATES = ("idle", "booting", "ready", "running", "failed")


def css() -> str:
    return CSS_PATH.read_text()


@contextmanager
def workspace(title: str):
    """A gr.Blocks configured for a full-viewport, non-scrolling workspace.

    Note this does NOT carry the stylesheet. Gradio 6 moved `css`/`head` off
    the Blocks constructor (it warns and silently ignores them) onto
    `launch()` and `mount_gradio_app()`. Use `mount()` below, or pass
    `css_paths=[CSS_PATH]` yourself — without it you get an unstyled,
    scrolling page and no error.
    """
    with gr.Blocks(title=title, fill_height=True) as blocks:
        yield blocks


def mount(app, blocks, path: str = "/ui", head: str = "", **kwargs):
    """`gr.mount_gradio_app` with the workspace stylesheet attached.

    The one supported way to get the CSS in when serving under FastAPI.
    """
    return gr.mount_gradio_app(
        app, blocks, path=path, css_paths=[CSS_PATH], head=head, **kwargs
    )


def bar_html(
    state: str = "idle",
    phase: str = "IDLE",
    message: str = "",
    meta: dict[str, str] | None = None,
    brand_href: str = "https://robium.ai/",
) -> str:
    """Markup for the top bar. Mirrors robot-navigation's `.rnd-bar` grid.

    `meta` renders right-aligned as `label value` pairs — checkpoint, session
    time, device, whatever the app wants to keep permanently visible.
    """
    state = state if state in STATES else "idle"
    cells = "".join(
        f'<span class="rd-{key}"><code>{value}</code></span>'
        for key, value in (meta or {}).items()
    )
    return f"""
<header class="rd-bar rd-state-{state}">
  <a class="rd-brand" href="{brand_href}" target="_blank" rel="noreferrer">
    <span class="rd-brand-word">robium</span>
  </a>
  <div class="rd-health">
    <span class="rd-dot" aria-hidden="true"></span>
    <strong>{phase}</strong>
    <span>{message}</span>
  </div>
  <div class="rd-meta">{cells}</div>
</header>
""".strip()


def top_bar(**kwargs) -> gr.HTML:
    """The bar as a component. Update it by returning `bar_html(...)`."""
    return gr.HTML(bar_html(**kwargs), elem_classes=["rd-bar-host"], padding=False)


def boot_watch_js(endpoint: str = "/ui-status", poll_ms: int = 2000) -> str:
    """A <script> for `mount(head=...)` that keeps the bar honest while booting.

    Why not `gr.Timer`: a Timer registers in the Blocks config and its `tick`
    dependency resolves correctly server-side, but the component is never
    mounted into the DOM under `mount_gradio_app` — so it has nothing to run
    an interval from and never fires. Verified 2026-08-17 on Gradio 6.20:
    config had the timer and the dep, the DOM had zero timer nodes, and the
    bar sat on BOOTING forever while a direct POST to the tick endpoint
    returned the correct READY markup.

    Scope is deliberately small: this polls only until the app reports ready,
    then stops for good. Every later bar update is a return value from the
    handler that caused it, so nothing here can race an episode in progress.

    `endpoint` must NOT be the session-guarded status route — a hosted demo
    claims the instance for the parent page's session, which would make this
    poll a foreign session and earn a 409.
    """
    return f"""
<script>
(function () {{
  var DONE = false;
  // Returns whether it actually painted. Gradio hydrates the DOM after this
  // script's first tick, so the bar is reliably absent on the initial poll —
  // stopping on `ready` alone would latch DONE without ever having written
  // anything, and the bar would sit on its build-time value forever.
  function paint(s) {{
    var bar = document.querySelector('.rd-bar');
    if (!bar) return false;
    bar.className = 'rd-bar rd-state-' + (s.ready ? 'ready' : 'booting');
    var phase = bar.querySelector('strong');
    var msg = bar.querySelector('.rd-health span:last-child');
    if (phase) phase.textContent = s.ready ? 'READY' : 'BOOTING';
    if (msg) msg.textContent = s.message || '';
    return true;
  }}
  function poll() {{
    if (DONE) return;
    fetch('{endpoint}', {{ cache: 'no-store' }})
      .then(function (r) {{ return r.ok ? r.json() : null; }})
      .then(function (s) {{
        if (!s) return;
        if (paint(s) && s.ready) DONE = true;
      }})
      .catch(function () {{}})
      .finally(function () {{ if (!DONE) setTimeout(poll, {poll_ms}); }});
  }}
  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', function () {{ setTimeout(poll, 300); }});
  }} else {{
    setTimeout(poll, 300);
  }}
}})();
</script>
""".strip()


@contextmanager
def split():
    """Horizontal split: viewer flexes, rail is fixed-width."""
    with gr.Row(elem_classes=["rd-split"], equal_height=False):
        yield


@contextmanager
def rail():
    with gr.Column(elem_classes=["rd-rail"], min_width=280):
        yield


@contextmanager
def section(label: str):
    """A labelled block in the rail."""
    with gr.Column(elem_classes=["rd-section"]):
        gr.HTML(f'<p class="rd-label">{label}</p>', padding=False)
        yield


def note(markup: str) -> gr.HTML:
    """Secondary text — caveats, checkpoint provenance, honesty notes."""
    return gr.HTML(f'<p class="rd-note">{markup}</p>', padding=False)
