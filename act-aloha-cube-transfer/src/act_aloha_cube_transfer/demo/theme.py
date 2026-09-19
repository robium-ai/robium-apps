import gradio as gr

THEME = gr.themes.Base(primary_hue="blue", neutral_hue="zinc")

CSS = """
:root { --act-bg:#18181b; --act-panel:#27272a; --act-card:#27272a; --act-line:#3f3f46;
  --act-muted:#a1a1aa; --act-accent:#2563eb; --act-accent-soft:#172554; --act-success:#4ade80; }
html, body { width:100%; height:100%; margin:0; overflow:hidden !important; }
body, .gradio-container { background:var(--act-bg) !important; color:#f4f4f5 !important; color-scheme:dark; }
.gradio-container {
  --body-background-fill:var(--act-bg); --background-fill-primary:var(--act-bg);
  --background-fill-secondary:var(--act-panel); --block-background-fill:var(--act-card);
  --block-border-color:var(--act-line); --block-label-background-fill:var(--act-card);
  --input-background-fill:var(--act-bg); --input-border-color:var(--act-line);
  --button-secondary-background-fill:var(--act-card); --button-secondary-border-color:var(--act-line);
  --button-secondary-text-color:#f4f4f5; --body-text-color:#f4f4f5;
  --body-text-color-subdued:var(--act-muted); --block-label-text-color:var(--act-muted);
  --block-title-text-color:#f4f4f5; --input-placeholder-color:var(--act-muted);
  --checkbox-label-background-fill:var(--act-card); --checkbox-label-background-fill-hover:#323238;
  --checkbox-label-background-fill-selected:var(--act-accent-soft); --checkbox-label-border-color:var(--act-line);
  --checkbox-label-border-color-hover:var(--act-accent); --checkbox-label-border-color-selected:var(--act-accent);
  --checkbox-label-text-color:#f4f4f5; --checkbox-label-text-color-selected:#f4f4f5;
  width:100% !important; height:100dvh !important; max-width:none !important; padding:0 !important;
  overflow:hidden !important;
}
.gradio-container > main { max-width:none !important; margin:0 !important; padding:0 !important; }
.gradio-container .main.app { padding:0 !important; }
.gradio-container footer { display:none !important; }
.gradio-container, .gradio-container * { font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
.act-shell, .act-body { flex-wrap:nowrap !important; }
.act-body { height:100dvh; min-height:0 !important; gap:0 !important; overflow:hidden; }
.act-controls { min-width:280px; max-width:350px; height:100%; padding:18px !important;
  flex-direction:column !important; flex-wrap:nowrap !important;
  overflow:hidden; align-self:flex-start;
  border-right:1px solid var(--act-line); background:var(--act-panel); }
.act-main { min-width:0 !important; max-width:none !important; height:100%; min-height:0 !important; padding:18px !important;
  flex-direction:column !important; flex-wrap:nowrap !important; overflow:hidden; }
.act-section { color:var(--act-muted); font:600 11px/1.4 ui-monospace,monospace; letter-spacing:.1em; text-transform:uppercase; }
.act-frame { flex:1 1 auto !important; min-width:0 !important; min-height:0 !important; overflow:hidden !important; }
.act-frame, .act-frame > div { height:100% !important; background:#05070b !important; padding:0 !important; }
.act-frame [data-testid="status-tracker"] { display:none !important; visibility:hidden !important;
  opacity:0 !important; pointer-events:none !important; }
.act-frame, .act-frame *, .act-stream, .act-stream img { animation:none !important; transition:none !important; }
.act-stream { position:relative; width:100%; height:100%; display:flex; align-items:center; justify-content:center;
  overflow:hidden; border:1px solid var(--act-line); border-radius:4px; background:#05070b; }
.act-stream-label { position:absolute; z-index:1; top:0; left:0; padding:6px 10px; color:var(--act-muted);
  border-right:1px solid var(--act-line); border-bottom:1px solid var(--act-line); background:var(--act-card); }
.act-stream img { display:block; width:100%; height:100%; object-fit:contain; background:#05070b; }
.act-controls label, .act-controls input { color:#f4f4f5 !important; }
.act-controls input { background:var(--act-bg) !important; border-color:var(--act-line) !important; }
.act-controls input[type="radio"] { appearance:none !important; -webkit-appearance:none !important;
  width:18px !important; height:18px !important; min-width:18px !important;
  border:2px solid #71717a !important; border-radius:50% !important; background:var(--act-bg) !important; }
.act-controls input[type="radio"]:checked { border-color:#60a5fa !important; background:#60a5fa !important;
  box-shadow:inset 0 0 0 4px var(--act-bg),0 0 0 1px rgba(96,165,250,.25) !important; }
.act-controls label:has(input[type="radio"]:checked) { border-color:#3b82f6 !important; background:var(--act-accent-soft) !important; }
button.primary { background:var(--act-accent) !important; border-color:var(--act-accent) !important; }
.act-controls button:not(.primary) { background:var(--act-card) !important; border:1px solid var(--act-line) !important; }
.act-mode-panel, .act-arm-panel { flex-direction:column !important; flex-wrap:nowrap !important; }
.act-mode-panel > *, .act-arm-panel > * { flex-shrink:0 !important; }
.act-mode-content { flex:1 1 auto !important; min-height:0 !important; overflow:hidden; }
.act-mode-content > * { flex-shrink:0 !important; }
.act-arm-panel > .form { display:block !important; width:100% !important; max-width:100% !important;
  border:0 !important; background:transparent !important; }
.act-mode-toggle, .act-arm-toggle { margin-bottom:4px !important; }
.act-mode-toggle .wrap, .act-arm-toggle .wrap { flex-direction:row !important; flex-wrap:nowrap !important; }
.act-mode-toggle label, .act-arm-toggle label { flex:1 1 0 !important; justify-content:center !important;
  min-width:0 !important; text-align:center; }
.act-health { flex:0 0 auto !important; margin-top:8px !important; background:var(--act-panel) !important; }
.act-joint-slider { margin:0 !important; padding:5px 2px !important; border:0 !important;
  overflow:visible !important; background:transparent !important; box-shadow:none !important; }
.act-joint-slider > .wrap:not(.hide) { display:grid !important;
  grid-template-columns:minmax(116px,42%) minmax(0,1fr); align-items:center; gap:10px; }
.act-joint-slider .head { display:contents !important; }
.act-joint-slider .head label { grid-column:1; grid-row:1; min-width:0; margin:0 !important;
  font-size:12px !important; white-space:nowrap; }
.act-joint-slider .tab-like-container,
.act-joint-slider .min_value,
.act-joint-slider .max_value { display:none !important; }
.act-joint-slider .slider_input_container { display:block !important; grid-column:2; grid-row:1;
  min-width:0; width:100% !important; }
.act-joint-slider input[type="range"] { display:block !important; width:100% !important; margin:0 !important; }
.act-controls.form, .act-controls > .form { display:block !important;
  width:100% !important; max-width:100% !important; }
.act-controls > * { flex-shrink:0 !important; }
.act-controls > .act-mode-content { flex:1 1 auto !important; min-height:0 !important; }
.act-controls > .act-health { flex:0 0 auto !important; }
.act-controls .wrap { min-width:0 !important; }
.act-controls .label-wrap, .act-controls .label-wrap * { color:#f4f4f5 !important; opacity:1 !important; }
"""
