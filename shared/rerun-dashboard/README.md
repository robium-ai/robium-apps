# rerun-dashboard — the workspace shell for Gradio + Rerun demos (reusable reference copy)

The Rerun-side counterpart to [`../lichtblick-dashboard`](../lichtblick-dashboard).
That one docks a control panel **inside Lichtblick** for ROS apps; this one
wraps a **Rerun viewer plus a control rail** for learning apps.

Apps **vendor** these two files (copy `dashboard.py` and `dashboard.css` next
to their demo UI) exactly the way they vendor
[`../demo-gateway/demo_gateway.py`](../demo-gateway) — each app stays
self-contained and promotion-ready, and this copy is the source they vendor
from and where fixes land first.

Used by: `vla-pick-and-place`. Next obvious consumer:
`imitation-manipulation`, which is also Gradio + Rerun.

## The layout contract

The page is **exactly one viewport tall and never scrolls.**

```
┌──────────────────────────────────────────────────────────────┐
│ ◆ robium   ● READY   <message>            <meta>  <meta>     │  62px
├─────────────────────────────────────┬────────────────────────┤
│                                     │  section               │
│   viewer — takes every pixel the    │  section               │
│   bar and rail do not               │  section               │
│                                     │  log (scrolls itself)  │
└─────────────────────────────────────┴────────────────────────┘
                                        360px
```

Below 900px the rail moves under the viewer and the split goes vertical. The
page still does not scroll; the rail scrolls internally.

## Usage

```python
from dashboard import workspace, top_bar, split, rail, section, note, bar_html

with workspace("my demo") as ui:
    bar = top_bar(state="booting", phase="BOOTING", message="loading model…")
    with split():
        viewer = Rerun(streaming=True, height="100%", elem_classes=["rd-viewer"])
        with rail():
            with section("instruction"):
                text = gr.Textbox(...)
            with section("status"):
                status = gr.Textbox(...)
                note("Whatever caveat the demo must not hide.")
```

Then mount it — this is how the stylesheet gets in:

```python
from dashboard import mount
app = mount(app, build_ui(...), path="/ui")
```

Update the bar by returning `bar_html(...)` from any event handler or
`gr.Timer` tick.

`state` is one of `idle | booting | ready | running | failed` and only
controls the health dot's color.

## Rules that are load-bearing

- **The palette and bar geometry are copied from robium-website's
  `robot-navigation.css` on purpose.** A visitor moving between a ROS demo
  and a learning demo should see one product. If you restyle one, restyle
  both.
- **Height must be forced down Gradio's whole wrapper chain.** Gradio nests
  the app several levels deep and every level defaults to auto height, so a
  lone `height: 100%` on the viewer does nothing. `dashboard.css` pins
  `html`, `body`, `gradio-app`, `.gradio-container`, `.main`, `.wrap`, and
  `.contain`. If a Gradio upgrade renames one of those, the viewer collapses
  to its intrinsic height and the page starts scrolling — that is the first
  thing to check.
- **Gradio's footer is hidden**, because "Use via API / Settings" adds enough
  height to reintroduce a scrollbar.
- **Pass `height="100%"` to the Rerun component**, not a pixel value. The
  component accepts `int | str`; a number pins it and breaks the fill.
- **Gradio 6 moved `css` and `head` off the `Blocks` constructor.** Passing
  them there warns once and is otherwise ignored — you get an unstyled,
  scrolling page with no error to grep for. They belong on `launch()` or
  `mount_gradio_app()`; `mount()` above exists so this cannot be forgotten.
- **Gradio's `Row` defaults to `align-items: flex-start`** (it emits an
  `unequal-height` class). The viewer then sits at its intrinsic height
  inside a full-height split, leaving a dead band under the canvas that
  reads as a rendering bug. `.rd-split` forces `align-items: stretch`.
- **`gr.Timer` does not fire under `mount_gradio_app`.** Verified on Gradio
  6.20: the timer and its `tick` dependency are both present in the client
  config, a direct POST to the tick endpoint returns correct markup, and the
  DOM contains zero timer nodes — so nothing ever runs the interval. Do not
  reach for `gr.Timer` to drive the bar; use `boot_watch_js`.
- **Anything polling before first paint must not latch on "done".** Gradio
  hydrates after a head script's first tick, so the bar is reliably absent on
  poll #1. Stop only once you have actually written to the DOM.
- **Gradio's stock accent is orange, and its radios are `appearance: none`.**
  The fill is `background-color`, not `accent-color`, so an `accent-color`
  override silently does nothing.
- **Every flex declaration in the split needs `!important`.** Gradio's own
  `.row`/`.column` classes set `flex: 1 1 0%`, which otherwise eats the
  rail's fixed width.
