import type { ExtensionContext, PanelExtensionContext } from "@lichtblick/suite";
import React from "react";
import { createRoot } from "react-dom/client";

import { RobotControlPanel } from "./RobotControlPanel";
import { LichtblickAdapter } from "./lichtblickAdapter";
import "./styles.css";

export function initRobotControlPanel(context: PanelExtensionContext): () => void {
  const adapter = new LichtblickAdapter(context, context.initialState);
  const root = createRoot(context.panelElement);
  root.render(React.createElement(RobotControlPanel, { adapter }));
  return () => {
    root.unmount();
    adapter.dispose();
  };
}

export function activate(extensionContext: ExtensionContext): void {
  extensionContext.registerPanel({ name: "robot-control", initPanel: initRobotControlPanel });
}
