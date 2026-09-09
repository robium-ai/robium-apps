import type {
  ExtensionContext,
  Immutable,
  PanelExtensionContext,
  RenderState,
} from "@lichtblick/suite";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";

import "./styles.css";

type ToolCall = {
  name: string;
  arguments: Record<string, unknown>;
  result: Record<string, unknown>;
};

type MissionResult = {
  status: string;
  response?: string;
  reason?: string;
  tool_calls?: ToolCall[];
};

type PanelConfig = {
  missionEndpoint?: string;
};

const PRESETS = [
  {
    label: "Look & joke",
    instruction:
      "Look around carefully and make one short, silly comment about the scene.",
  },
  {
    label: "Living room",
    instruction:
      "Go to the living room, inspect it, and report any mess with a funny comment.",
  },
  {
    label: "Sock patrol",
    instruction:
      "Patrol for a sock or other mess. Complain theatrically, refuse to clean it, and stop safely.",
  },
] as const;

async function jsonRequest(
  url: string,
  options?: RequestInit,
): Promise<MissionResult> {
  const response = await fetch(url, {
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = (await response.json()) as MissionResult;
  if (!response.ok) {
    throw new Error(
      payload.reason ??
        `Mission service returned HTTP ${response.status.toString()}`,
    );
  }
  return payload;
}

function MissionPanel({
  context,
}: {
  context: PanelExtensionContext;
}): React.JSX.Element {
  const config = (context.initialState ?? {}) as PanelConfig;
  const endpoint = useMemo(
    () => (config.missionEndpoint ?? "/api").replace(/\/$/, ""),
    [config.missionEndpoint],
  );
  const [colorScheme, setColorScheme] = useState<"dark" | "light">("dark");
  const [instruction, setInstruction] = useState<string>(
    PRESETS[0].instruction,
  );
  const [running, setRunning] = useState(false);
  const [serviceReady, setServiceReady] = useState(false);
  const [cameraTick, setCameraTick] = useState(0);
  const [message, setMessage] = useState("Checking Gemini mission service…");
  const [result, setResult] = useState<MissionResult>();

  useEffect(() => {
    context.watch("colorScheme");
    context.setDefaultPanelTitle("Silly TurtleBot Mission Control");
    context.onRender = (state: Immutable<RenderState>, done) => {
      if (state.colorScheme != undefined) {
        setColorScheme(state.colorScheme);
      }
      done();
    };
    return () => {
      context.onRender = undefined;
    };
  }, [context]);

  useEffect(() => {
    let active = true;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const checkHealth = async () => {
      try {
        await jsonRequest(`${endpoint}/health`);
        if (active) {
          setServiceReady(true);
          setMessage("Ready for instructions");
        }
      } catch (error) {
        if (active) {
          setServiceReady(false);
          setMessage(error instanceof Error ? error.message : String(error));
          retry = setTimeout(() => void checkHealth(), 2000);
        }
      }
    };
    void checkHealth();
    return () => {
      active = false;
      if (retry != undefined) {
        clearTimeout(retry);
      }
    };
  }, [endpoint]);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setCameraTick((value) => value + 1);
    }, 1000);
    return () => window.clearInterval(timer);
  }, []);

  const runMission = useCallback(async () => {
    const trimmed = instruction.trim();
    if (trimmed === "" || running) {
      return;
    }
    setRunning(true);
    setResult(undefined);
    setMessage("Gemini is running the mission…");
    try {
      const next = await jsonRequest(`${endpoint}/missions`, {
        method: "POST",
        body: JSON.stringify({
          instruction: trimmed,
          camera_source: "primary",
        }),
      });
      setResult(next);
      setMessage(
        `Mission complete · ${(next.tool_calls?.length ?? 0).toString()} guarded action(s)`,
      );
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    } finally {
      setRunning(false);
    }
  }, [endpoint, instruction, running]);

  const stop = useCallback(async () => {
    setMessage("Requesting a safe stop…");
    try {
      await jsonRequest(`${endpoint}/stop`, { method: "POST", body: "{}" });
      setMessage("Stop requested");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }, [endpoint]);

  const runRobotAction = useCallback(
    async (action: "dock" | "undock") => {
      if (running) {
        return;
      }
      setRunning(true);
      setResult(undefined);
      setMessage(action === "dock" ? "Docking…" : "Undocking…");
      try {
        const next = await jsonRequest(`${endpoint}/${action}`, {
          method: "POST",
          body: "{}",
        });
        setResult(next);
        setMessage(action === "dock" ? "Dock complete" : "Undock complete");
      } catch (error) {
        setMessage(error instanceof Error ? error.message : String(error));
      } finally {
        setRunning(false);
      }
    },
    [endpoint, running],
  );

  return (
    <main className={`mission-panel ${colorScheme}`}>
      <header>
        <div>
          <h1>Silly TurtleBot</h1>
          <p>Gemini mission control</p>
        </div>
        <span className={serviceReady ? "ready" : "waiting"}>
          {serviceReady ? "Ready" : "Starting"}
        </span>
      </header>

      <section>
        <label htmlFor="mission-instruction">Tell the robot what to do</label>
        <textarea
          id="mission-instruction"
          value={instruction}
          maxLength={2000}
          disabled={running}
          onChange={(event) => setInstruction(event.currentTarget.value)}
          onKeyDown={(event) => {
            if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
              event.preventDefault();
              void runMission();
            }
          }}
        />
        <div className="preset-row">
          {PRESETS.map((preset) => (
            <button
              type="button"
              key={preset.label}
              disabled={running}
              onClick={() => setInstruction(preset.instruction)}
            >
              {preset.label}
            </button>
          ))}
        </div>
        <div className="action-row">
          <button
            className="run"
            type="button"
            disabled={!serviceReady || running || instruction.trim() === ""}
            onClick={() => void runMission()}
          >
            {running ? "Running…" : "Run mission"}
          </button>
          <button className="stop" type="button" onClick={() => void stop()}>
            Stop robot
          </button>
        </div>
        <div className="dock-row">
          <button
            type="button"
            disabled={!serviceReady || running}
            onClick={() => void runRobotAction("undock")}
          >
            Undock
          </button>
          <button
            type="button"
            disabled={!serviceReady || running}
            onClick={() => void runRobotAction("dock")}
          >
            Dock
          </button>
        </div>
        <p className="hint">⌘/Ctrl + Enter runs the instruction</p>
        <p className="hint">
          Map goal: in the 3D panel choose Publish pose; it sends /goal_pose
          directly to Nav2.
        </p>
      </section>

      <section className="camera-card">
        <div className="camera-heading">
          <h2>OAK-D live view</h2>
          <span>{serviceReady ? "live" : "waiting"}</span>
        </div>
        <img
          src={`${endpoint}/camera?t=${cameraTick.toString()}`}
          alt="Live view from the TurtleBot OAK-D camera"
        />
      </section>

      <section className="transcript" aria-live="polite">
        <h2>Status</h2>
        <p>{message}</p>
        {result?.response != undefined && (
          <blockquote>{result.response}</blockquote>
        )}
        {(result?.tool_calls?.length ?? 0) > 0 && (
          <ol>
            {result?.tool_calls?.map((call, index) => (
              <li key={`${call.name}-${index.toString()}`}>
                <strong>{call.name}</strong>
                <span>
                  {typeof call.result.status === "string"
                    ? call.result.status
                    : "completed"}
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </main>
  );
}

function initPanel(context: PanelExtensionContext): () => void {
  const root = createRoot(context.panelElement);
  root.render(<MissionPanel context={context} />);
  return () => root.unmount();
}

export function activate(context: ExtensionContext): void {
  context.registerPanel({ name: "mission-control", initPanel });
}
