import type {
  ExtensionContext,
  Immutable,
  PanelExtensionContext,
  RenderState,
} from "@lichtblick/suite";
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createRoot } from "react-dom/client";

import "./styles.css";

type ToolCall = {
  callId: string;
  name: string;
  arguments: Record<string, unknown>;
  result?: Record<string, unknown>;
  status: "running" | "finished" | "rejected";
};

type MissionResult = {
  status: string;
  mission_id?: string;
  reason?: string;
};

type HealthResult = MissionResult & {
  robot?: {
    is_docked?: boolean;
    battery_percentage?: number;
  };
  gemini_session?: {
    state?: string;
  };
  mission?: {
    active_mission_id?: string;
    state?: string;
  };
};

type DomainEvent = {
  seq: number;
  timestamp: string;
  mission_id: string;
  type: string;
  payload: Record<string, unknown>;
};

type PanelConfig = {
  missionEndpoint?: string;
};

type LogEntry = {
  seq: number;
  timestamp: string;
  level: "info" | "error";
  text: string;
};

const EVENT_TYPES = [
  "session.connecting",
  "session.ready",
  "session.reconnecting",
  "mission.accepted",
  "mission.updated",
  "mission.completed",
  "mission.stopping",
  "mission.stopped",
  "mission.failed",
  "input.sent",
  "model.text.delta",
  "model.turn.completed",
  "tool.started",
  "tool.progress",
  "tool.finished",
  "tool.rejected",
  "tool.response.sent",
  "camera.status",
] as const;

function eventLogText(event: DomainEvent): string {
  const { type, payload } = event;
  const text = (value: unknown, fallback = "") =>
    typeof value === "string" ? value : fallback;
  if (type === "model.text.delta") {
    return `Gemini: ${text(payload.text)}`;
  }
  if (type === "tool.started") {
    return `Tool started: ${text(payload.name, "tool")} ${JSON.stringify(payload.arguments ?? {})}`;
  }
  if (type === "tool.progress") {
    const elapsed =
      typeof payload.elapsed_s === "number"
        ? `${payload.elapsed_s.toFixed(1)}s`
        : "running";
    return `Tool progress: ${text(payload.name, "tool")} ${elapsed} ${JSON.stringify(payload.state ?? {})}`;
  }
  if (type === "tool.finished") {
    return `Tool finished: ${text(payload.name, "tool")} ${JSON.stringify(payload.result ?? {})}`;
  }
  if (type === "tool.rejected") {
    return `tool rejected: ${text(payload.name, "tool")} ${JSON.stringify(payload.result ?? payload)}`;
  }
  if (type === "tool.response.sent") {
    return `Tool response sent: ${text(payload.name, "tool")} (${text(payload.call_id)})`;
  }
  if (type === "input.sent" && payload.kind === "heartbeat") {
    return `Heartbeat sent: ${JSON.stringify(payload.state ?? {})}`;
  }
  if (type === "mission.accepted" || type === "mission.updated") {
    return `${type}: ${text(payload.instruction)}`;
  }
  const detail =
    Object.keys(payload).length > 0 ? ` ${JSON.stringify(payload)}` : "";
  return `${type}${detail}`;
}

async function jsonRequest<T extends MissionResult>(
  url: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(url, {
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = (await response.json()) as T;
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
  const eventSourceRef = useRef<EventSource | undefined>(undefined);
  const logRef = useRef<HTMLTextAreaElement | null>(null);
  const [colorScheme, setColorScheme] = useState<"dark" | "light">("dark");
  const [instruction, setInstruction] = useState<string>("");
  const [serviceReady, setServiceReady] = useState(false);
  const [isDocked, setIsDocked] = useState<boolean>();
  const [batteryPercentage, setBatteryPercentage] = useState<number>();
  const [message, setMessage] = useState("Checking Gemini mission service…");
  const [missionId, setMissionId] = useState<string>();
  const [missionState, setMissionState] = useState("idle");
  const [sessionState, setSessionState] = useState("disconnected");
  const [modelText, setModelText] = useState("");
  const [toolCalls, setToolCalls] = useState<ToolCall[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);

  const missionActive = missionId != undefined;
  const logText = useMemo(
    () =>
      logs
        .map((entry) => {
          const instant = new Date(entry.timestamp);
          const time = Number.isNaN(instant.getTime())
            ? entry.timestamp
            : instant.toLocaleTimeString([], {
                hour12: false,
                hour: "2-digit",
                minute: "2-digit",
                second: "2-digit",
                fractionalSecondDigits: 3,
              });
          return `[${time}] ${entry.level === "error" ? "ERROR " : ""}${entry.text}`;
        })
        .join("\n"),
    [logs],
  );

  useEffect(() => {
    const element = logRef.current;
    if (element != undefined) {
      element.scrollTop = element.scrollHeight;
    }
  }, [logText]);

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
    let readyAnnounced = false;
    const checkHealth = async () => {
      try {
        const health = await jsonRequest<HealthResult>(`${endpoint}/health`);
        if (active) {
          setServiceReady(true);
          setIsDocked(health.robot?.is_docked);
          setBatteryPercentage(health.robot?.battery_percentage);
          setSessionState(health.gemini_session?.state ?? "disconnected");
          if (!readyAnnounced && !missionActive) {
            setMessage("Ready for instructions");
          }
          readyAnnounced = true;
        }
      } catch (error) {
        if (active) {
          setServiceReady(false);
          setIsDocked(undefined);
          setBatteryPercentage(undefined);
          setMessage(error instanceof Error ? error.message : String(error));
          readyAnnounced = false;
        }
      } finally {
        if (active) {
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
  }, [endpoint, missionActive]);

  useEffect(
    () => () => {
      eventSourceRef.current?.close();
    },
    [],
  );

  const handleDomainEvent = useCallback((domainEvent: DomainEvent) => {
    const { type, payload } = domainEvent;
    setLogs((current) => [
      ...current.slice(-399),
      {
        seq: domainEvent.seq,
        timestamp: domainEvent.timestamp,
        level:
          type === "tool.rejected" || type === "mission.failed"
            ? "error"
            : "info",
        text: eventLogText(domainEvent),
      },
    ]);
    if (type.startsWith("session.")) {
      setSessionState(type.slice("session.".length));
    }
    if (type === "mission.accepted") {
      setMissionState("accepted");
      setMessage("Mission accepted · connecting to Gemini…");
    } else if (type === "mission.updated") {
      setMissionState("running");
      setMessage("Updated instruction queued");
    } else if (type === "input.sent") {
      setMissionState("running");
      setMessage(
        payload.kind === "heartbeat"
          ? "Gemini is checking the latest view…"
          : "Gemini is working on the mission…",
      );
    } else if (type === "model.text.delta") {
      const text = typeof payload.text === "string" ? payload.text : "";
      setModelText((current) => current + text);
      setMessage("Gemini is responding…");
    } else if (type === "tool.started") {
      const callId = typeof payload.call_id === "string" ? payload.call_id : "";
      const name = typeof payload.name === "string" ? payload.name : "tool";
      const args =
        typeof payload.arguments === "object" && payload.arguments != undefined
          ? (payload.arguments as Record<string, unknown>)
          : {};
      setToolCalls((current) => {
        const existing = current.findIndex((call) => call.callId === callId);
        const next: ToolCall = {
          callId,
          name,
          arguments: args,
          status: "running",
        };
        if (existing < 0) {
          return [...current, next];
        }
        return current.map((call, index) => (index === existing ? next : call));
      });
      setMessage(`Running guarded action · ${name}`);
    } else if (type === "tool.finished" || type === "tool.rejected") {
      const callId = typeof payload.call_id === "string" ? payload.call_id : "";
      const result =
        typeof payload.result === "object" && payload.result != undefined
          ? (payload.result as Record<string, unknown>)
          : {};
      setToolCalls((current) =>
        current.map((call) =>
          call.callId === callId
            ? {
                ...call,
                result,
                status: type === "tool.rejected" ? "rejected" : "finished",
              }
            : call,
        ),
      );
    } else if (type === "mission.stopping") {
      setMissionState("stopping");
      setMessage("Stopping robot safely…");
    } else if (type === "mission.completed") {
      setMissionState("completed");
      setMessage("Mission complete");
      setMissionId(undefined);
      eventSourceRef.current?.close();
    } else if (type === "mission.stopped") {
      setMissionState("stopped");
      setMessage("Robot stopped");
      setMissionId(undefined);
      eventSourceRef.current?.close();
    } else if (type === "mission.failed") {
      setMissionState("failed");
      setMessage(
        typeof payload.reason === "string" ? payload.reason : "Mission failed",
      );
      setMissionId(undefined);
      eventSourceRef.current?.close();
    }
  }, []);

  const openEventStream = useCallback(
    (nextMissionId: string) => {
      eventSourceRef.current?.close();
      const source = new EventSource(
        `${endpoint}/events/${encodeURIComponent(nextMissionId)}`,
      );
      eventSourceRef.current = source;
      for (const eventType of EVENT_TYPES) {
        source.addEventListener(eventType, (event: MessageEvent<string>) => {
          try {
            handleDomainEvent(JSON.parse(event.data) as DomainEvent);
          } catch {
            setMessage("Received an invalid mission event");
          }
        });
      }
      source.onerror = () => {
        if (eventSourceRef.current === source) {
          setMessage("Mission event stream reconnecting…");
        }
      };
    },
    [endpoint, handleDomainEvent],
  );

  const runMission = useCallback(async () => {
    const trimmed = instruction.trim();
    if (trimmed === "") {
      return;
    }
    const updating = missionActive;
    if (!updating) {
      setModelText("");
      setToolCalls([]);
      setLogs([]);
      setMissionState("accepted");
    }
    setMessage(updating ? "Updating mission…" : "Submitting mission…");
    try {
      const next = await jsonRequest<MissionResult>(`${endpoint}/missions`, {
        method: "POST",
        body: JSON.stringify({
          instruction: trimmed,
          camera_source: "primary",
        }),
      });
      if (next.mission_id == undefined) {
        throw new Error("Mission service did not return a mission ID");
      }
      if (!updating || next.mission_id !== missionId) {
        setMissionId(next.mission_id);
        openEventStream(next.mission_id);
      }
      setMessage(updating ? "Updated instruction queued" : "Mission accepted");
    } catch (error) {
      if (!updating) {
        setMissionState("failed");
      }
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }, [endpoint, instruction, missionActive, missionId, openEventStream]);

  const stop = useCallback(async () => {
    setMessage("Requesting a safe stop…");
    try {
      await jsonRequest(`${endpoint}/stop`, { method: "POST", body: "{}" });
      if (!missionActive) {
        setMessage("Stop requested");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : String(error));
    }
  }, [endpoint, missionActive]);

  return (
    <main className={`mission-panel ${colorScheme}`}>
      <header>
        <div>
          <h1>Silly TurtleBot</h1>
          <p>Gemini mission control</p>
        </div>
        <span className={serviceReady ? "ready" : "waiting"}>
          {serviceReady
            ? isDocked == undefined
              ? "Robot ready"
              : isDocked
                ? "Robot ready · Docked"
                : "Robot ready · Undocked"
            : "Robot starting"}
          {serviceReady
            ? ` · ${batteryPercentage == undefined ? "Battery —" : `${Math.round(batteryPercentage).toString()}%`}`
            : ""}
        </span>
      </header>

      <section>
        <label htmlFor="mission-instruction">Tell the robot what to do</label>
        <textarea
          id="mission-instruction"
          value={instruction}
          maxLength={2000}
          onChange={(event) => setInstruction(event.currentTarget.value)}
          onKeyDown={(event) => {
            if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
              event.preventDefault();
              void runMission();
            }
          }}
        />
        <div className="action-row">
          <button
            className="run"
            type="button"
            disabled={!serviceReady || instruction.trim() === ""}
            onClick={() => void runMission()}
          >
            {missionActive ? "Update mission" : "Run mission"}
          </button>
          <button className="stop" type="button" onClick={() => void stop()}>
            Stop robot
          </button>
        </div>
      </section>

      <section className="transcript" aria-live="polite">
        <h2>Live agent log</h2>
        <div className="state-row">
          <span>
            Gemini <strong>{sessionState}</strong>
          </span>
          <span>
            Mission <strong>{missionState}</strong>
          </span>
        </div>
        <p>{message}</p>
        <textarea
          ref={logRef}
          className="event-log"
          readOnly
          aria-label="Timestamped Gemini and robot event log"
          value={logText}
        />
        {modelText !== "" && <blockquote>{modelText}</blockquote>}
        {toolCalls.length > 0 && (
          <ol>
            {toolCalls.map((call, index) => (
              <li key={call.callId || `${call.name}-${index.toString()}`}>
                <strong>{call.name}</strong>
                <span>
                  {call.status === "finished"
                    ? typeof call.result?.status === "string"
                      ? call.result.status
                      : "finished"
                    : call.status}
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
