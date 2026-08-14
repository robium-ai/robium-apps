import React, { useCallback, useEffect, useMemo, useState, useSyncExternalStore } from "react";

import type { DriveController } from "./driveController";
import type { AdapterSnapshot, MapActionConfigKey } from "./lichtblickAdapter";
import type { Direction } from "./messages";
import { validateMapName, type PanelConfig } from "./panelConfig";

export type ControlPanelAdapter = {
  readonly snapshot: AdapterSnapshot;
  readonly drive: Pick<DriveController, "press" | "release" | "stop">;
  subscribe(listener: () => void): () => void;
  updateConfig(patch: Partial<Pick<PanelConfig, "linearSpeed" | "angularSpeed">>): void;
  runMapAction(mapName: string, action: MapActionConfigKey): Promise<void>;
  callConfiguredService(key: "goHomeService" | "navigationStopService"): Promise<void>;
};

const KEY_DIRECTIONS: Readonly<Record<string, Direction>> = {
  w: "forward",
  arrowup: "forward",
  s: "backward",
  arrowdown: "backward",
  a: "left",
  arrowleft: "left",
  d: "right",
  arrowright: "right",
};

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return (
    target.isContentEditable ||
    target.tagName === "INPUT" ||
    target.tagName === "SELECT" ||
    target.tagName === "TEXTAREA" ||
    target.tagName === "BUTTON"
  );
}

function DriveButton({
  adapter,
  direction,
  label,
  keyLabel,
}: {
  adapter: ControlPanelAdapter;
  direction: Direction;
  label: string;
  keyLabel: string;
}): React.JSX.Element {
  return (
    <button
      className={`drive-key drive-${direction}`}
      type="button"
      aria-label={label}
      onContextMenu={(event) => event.preventDefault()}
      onPointerDown={(event) => {
        event.preventDefault();
        event.currentTarget.setPointerCapture(event.pointerId);
        adapter.drive.press(direction);
      }}
      onPointerUp={() => adapter.drive.release(direction)}
      onPointerCancel={() => adapter.drive.release(direction)}
      onLostPointerCapture={() => adapter.drive.release(direction)}
    >
      <span>{keyLabel}</span>
    </button>
  );
}

export function RobotControlPanel({
  adapter,
}: {
  adapter: ControlPanelAdapter;
}): React.JSX.Element {
  const snapshot = useSyncExternalStore(
    (listener) => adapter.subscribe(listener),
    () => adapter.snapshot,
    () => adapter.snapshot,
  );
  const [mapName, setMapName] = useState(snapshot.selectedParameter ?? "");
  const [selectedMap, setSelectedMap] = useState("");
  const validMapName = validateMapName(mapName.trim());
  const mapping = snapshot.mode === "MAPPING";

  useEffect(() => {
    if (mapName === "" && snapshot.selectedParameter != undefined) {
      setMapName(snapshot.selectedParameter);
    }
  }, [mapName, snapshot.selectedParameter]);

  useEffect(() => {
    const keyDown = (event: KeyboardEvent) => {
      const direction = KEY_DIRECTIONS[event.key.toLowerCase()];
      if (
        direction == undefined ||
        event.repeat ||
        isEditableTarget(event.target) ||
        isEditableTarget(document.activeElement)
      ) {
        return;
      }
      event.preventDefault();
      adapter.drive.press(direction);
    };
    const keyUp = (event: KeyboardEvent) => {
      const direction = KEY_DIRECTIONS[event.key.toLowerCase()];
      if (
        direction == undefined ||
        isEditableTarget(event.target) ||
        isEditableTarget(document.activeElement)
      ) {
        return;
      }
      event.preventDefault();
      adapter.drive.release(direction);
    };
    const stop = () => adapter.drive.stop();
    const visibility = () => {
      if (document.hidden) {
        stop();
      }
    };
    window.addEventListener("keydown", keyDown);
    window.addEventListener("keyup", keyUp);
    window.addEventListener("blur", stop);
    document.addEventListener("visibilitychange", visibility);
    return () => {
      window.removeEventListener("keydown", keyDown);
      window.removeEventListener("keyup", keyUp);
      window.removeEventListener("blur", stop);
      document.removeEventListener("visibilitychange", visibility);
      stop();
    };
  }, [adapter]);

  const runMapAction = useCallback(
    (name: string, key: MapActionConfigKey) => {
      void adapter.runMapAction(name, key).catch(() => undefined);
    },
    [adapter],
  );

  const modeClass = useMemo(() => snapshot.mode.toLowerCase(), [snapshot.mode]);

  return (
    <main className={`robot-control ${snapshot.colorScheme}`}>
      <header className="panel-header">
        <h1>Robot Control</h1>
        <span className={`mode-pill ${modeClass}`}>{snapshot.mode}</span>
      </header>

      <section className="control-card drive-card" aria-labelledby="drive-heading">
        <div className="section-heading">
          <h2 id="drive-heading">Movement</h2>
        </div>
        {!snapshot.canPublish && (
          <p className="inline-warning">Publishing is unavailable on this connection.</p>
        )}
        <div className="speed-controls">
          <label className="speed-control">
            <span>
              Forward <output>{snapshot.config.linearSpeed.toFixed(2)} m/s</output>
            </span>
            <input
              type="range"
              aria-label="Forward speed"
              min="0.05"
              max="0.5"
              step="0.05"
              value={snapshot.config.linearSpeed}
              onInput={(event) =>
                adapter.updateConfig({ linearSpeed: Number(event.currentTarget.value) })
              }
            />
          </label>
          <label className="speed-control">
            <span>
              Turn <output>{snapshot.config.angularSpeed.toFixed(1)} rad/s</output>
            </span>
            <input
              type="range"
              aria-label="Turn speed"
              min="0.1"
              max="1.5"
              step="0.1"
              value={snapshot.config.angularSpeed}
              onInput={(event) =>
                adapter.updateConfig({ angularSpeed: Number(event.currentTarget.value) })
              }
            />
          </label>
        </div>
        <div className="drive-grid" aria-label="Directional movement controls">
          <DriveButton adapter={adapter} direction="forward" label="Move forward" keyLabel="W" />
          <DriveButton adapter={adapter} direction="left" label="Turn left" keyLabel="A" />
          <DriveButton adapter={adapter} direction="backward" label="Move backward" keyLabel="S" />
          <DriveButton adapter={adapter} direction="right" label="Turn right" keyLabel="D" />
        </div>
      </section>

      <section className="control-card" aria-labelledby="mapping-heading">
        <div className="section-heading">
          <h2 id="mapping-heading">Maps</h2>
        </div>

        <label htmlFor="map-name">New map name</label>
        <input
          id="map-name"
          value={mapName}
          placeholder="e.g. warehouse_floor_1"
          aria-invalid={mapName !== "" && !validMapName}
          onInput={(event) => setMapName(event.currentTarget.value)}
        />
        {mapName !== "" && !validMapName && (
          <p className="field-error">Use 1–64 letters, numbers, dashes, or underscores.</p>
        )}
        <div className="action-row">
          <button
            className="primary-action"
            type="button"
            aria-label="Start mapping"
            disabled={!validMapName || mapping || snapshot.busy || !snapshot.canCallServices}
            onClick={() => runMapAction(mapName.trim(), "startMappingService")}
          >
            Start mapping
          </button>
          <button
            type="button"
            aria-label="Stop mapping"
            disabled={!mapping || snapshot.busy || !snapshot.canCallServices}
            onClick={() => runMapAction(mapName.trim(), "stopMappingService")}
          >
            Stop mapping
          </button>
        </div>

        <label htmlFor="available-map">Available maps</label>
        <div className="load-row">
          <select
            id="available-map"
            value={selectedMap}
            onChange={(event) => setSelectedMap(event.target.value)}
          >
            <option value="">Select a map</option>
            {snapshot.maps.map((map) => (
              <option value={map} key={map}>
                {map}
              </option>
            ))}
          </select>
          <button
            className="primary-action"
            type="button"
            aria-label="Load map"
            disabled={selectedMap === "" || mapping || snapshot.busy || !snapshot.canCallServices}
            onClick={() => runMapAction(selectedMap, "loadMapService")}
          >
            Load &amp; localize
          </button>
        </div>
      </section>

      <section className="control-card destination-card" aria-labelledby="destination-heading">
        <h2 id="destination-heading">Quick actions</h2>
        <div className="action-row">
          <button
            type="button"
            aria-label="Go home"
            disabled={snapshot.config.goHomeService === "" || snapshot.busy}
            title={
              snapshot.config.goHomeService === ""
                ? "Configure a home service in panel settings"
                : undefined
            }
            onClick={() =>
              void adapter.callConfiguredService("goHomeService").catch(() => undefined)
            }
          >
            Go home
          </button>
          <button
            className="stop-action"
            type="button"
            aria-label="Stop robot"
            onClick={() => {
              adapter.drive.stop();
              if (snapshot.config.navigationStopService !== "") {
                void adapter.callConfiguredService("navigationStopService").catch(() => undefined);
              }
            }}
          >
            Stop robot
          </button>
        </div>
      </section>

      {snapshot.status != undefined && (
        <div className={`status-banner ${snapshot.status.kind}`} role="status">
          {snapshot.status.message}
        </div>
      )}
    </main>
  );
}
