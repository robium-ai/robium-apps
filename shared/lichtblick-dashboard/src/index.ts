import type { ExtensionContext, PanelExtensionContext } from "@lichtblick/suite";
import React from "react";
import { createRoot } from "react-dom/client";

import { DashboardPanel } from "./DashboardPanel";
import { LichtblickAdapter } from "./lichtblickAdapter";
import "./styles.css";

export function initDashboardPanel(context: PanelExtensionContext): () => void {
  const adapter = new LichtblickAdapter(context, context.initialState);
  const root = createRoot(context.panelElement);
  root.render(React.createElement(DashboardPanel, { adapter }));
  return () => {
    root.unmount();
    adapter.dispose();
  };
}

export function activate(extensionContext: ExtensionContext): void {
  extensionContext.registerPanel({ name: "dashboard", initPanel: initDashboardPanel });
}
