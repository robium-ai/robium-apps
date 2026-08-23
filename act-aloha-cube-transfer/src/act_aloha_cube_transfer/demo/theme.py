import gradio as gr

THEME = gr.themes.Base(primary_hue="blue", neutral_hue="zinc")

CSS = """
:root { --act-bg:#18181b; --act-panel:#27272a; --act-card:#27272a; --act-line:#3f3f46;
  --act-muted:#a1a1aa; --act-accent:#2563eb; --act-accent-soft:#172554; --act-success:#4ade80; }
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
  max-width:none !important; padding:0 !important;
}
.gradio-container > main { max-width:none !important; margin:0 !important; padding:0 !important; }
.gradio-container .main.app { padding:0 !important; }
.gradio-container, .gradio-container * { font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; }
.act-shell, .act-shell .row, .act-shell .column, .act-shell .form { flex-wrap:nowrap !important; }
.act-topbar { min-height:62px; display:flex; align-items:center; gap:14px; padding:8px 18px;
  border-bottom:1px solid var(--act-line); background:var(--act-bg); }
.act-brand { font-size:23px; font-weight:700; letter-spacing:-.03em; }
.act-title { color:#f7f8fa; font-weight:650; }
.act-subtitle { color:var(--act-muted); font-size:12px; margin-left:auto; }
.act-dot { display:inline-block; width:9px; height:9px; margin-right:7px; border-radius:50%;
  background:var(--act-success); box-shadow:0 0 0 4px rgba(74,222,128,.12); }
.act-body { min-height:calc(100dvh - 62px); gap:0 !important; }
.act-controls { min-width:280px; max-width:350px; padding:18px !important; border-right:1px solid var(--act-line); background:var(--act-panel); }
.act-main { min-width:0; padding:18px !important; }
.act-section { color:var(--act-muted); font:600 11px/1.4 ui-monospace,monospace; letter-spacing:.1em; text-transform:uppercase; }
.act-frame, .act-frame > div { background:#05070b !important; padding:0 !important; }
.act-stream { position:relative; height:520px; display:flex; align-items:center; justify-content:center;
  overflow:hidden; border:1px solid var(--act-line); border-radius:4px; background:#05070b; }
.act-stream-label { position:absolute; z-index:1; top:0; left:0; padding:6px 10px; color:var(--act-muted);
  border-right:1px solid var(--act-line); border-bottom:1px solid var(--act-line); background:var(--act-card); }
.act-stream img { display:block; width:640px; height:480px; max-width:92%; max-height:92%; object-fit:contain; background:#05070b; }
.act-controls label, .act-controls input { color:#f4f4f5 !important; }
.act-controls input { background:var(--act-bg) !important; border-color:var(--act-line) !important; }
.act-controls input[type="radio"] { appearance:none !important; -webkit-appearance:none !important;
  width:18px !important; height:18px !important; min-width:18px !important;
  border:2px solid #71717a !important; border-radius:50% !important; background:var(--act-bg) !important; }
.act-controls input[type="radio"]:checked { border-color:#60a5fa !important; background:#60a5fa !important;
  box-shadow:inset 0 0 0 4px var(--act-bg),0 0 0 1px rgba(96,165,250,.25) !important; }
.act-controls label:has(input[type="radio"]:checked) { border-color:#3b82f6 !important; background:var(--act-accent-soft) !important; }
.act-result { border:1px solid var(--act-line); border-radius:6px; padding:12px 14px; background:var(--act-card); }
.act-result strong { color:#fff; }
.act-note { color:var(--act-muted); font-size:12px; line-height:1.55; }
button.primary { background:var(--act-accent) !important; border-color:var(--act-accent) !important; }
.act-controls button:not(.primary) { background:var(--act-card) !important; border:1px solid var(--act-line) !important; }
@media (max-width:820px) {
  .act-body { flex-direction:column !important; }
  .act-controls { min-width:0; max-width:none; border-right:0; border-bottom:1px solid var(--act-line); }
  .act-subtitle { display:none; }
}
"""
