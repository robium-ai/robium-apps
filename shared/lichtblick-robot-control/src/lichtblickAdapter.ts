import type {
  Immutable,
  PanelExtensionContext,
  RenderState,
  SettingsTreeAction,
  SettingsTreeFields,
} from "@lichtblick/suite";

import { DriveController } from "./driveController";
import type { Twist } from "./messages";
import {
  DEFAULT_CONFIG,
  isSimulationWorld,
  normalizeConfig,
  parseAvailableMaps,
  type PanelConfig,
  type SimulationWorld,
  validateMapName,
} from "./panelConfig";

export type MappingMode = "MAPPING" | "LOCALIZATION" | "IDLE" | "UNKNOWN";
export type NavigationState = "NAVIGATING" | "IDLE" | "UNKNOWN";
export type MapActionConfigKey = "startMappingService" | "stopMappingService" | "loadMapService";
export type WaypointActionConfigKey =
  | "saveWaypointService"
  | "navigateWaypointService"
  | "deleteWaypointService";

export type AdapterSnapshot = {
  config: PanelConfig;
  mode: MappingMode;
  maps: string[];
  waypoints: string[];
  navigationState: NavigationState;
  world: SimulationWorld | "UNKNOWN";
  selectedParameter?: string;
  colorScheme: "dark" | "light";
  canPublish: boolean;
  canCallServices: boolean;
  busy: boolean;
  status?: { kind: "success" | "error"; message: string };
};

type StringConfigKey = Exclude<
  keyof PanelConfig,
  "version" | "linearSpeed" | "angularSpeed" | "publishRateHz"
>;

const STRING_CONFIG_SETTINGS: ReadonlyArray<readonly [StringConfigKey, string]> = [
  ["teleopTopic", "Teleop topic"],
  ["mappingStateTopic", "Mapping state topic"],
  ["availableMapsTopic", "Available maps topic"],
  ["simulationStateTopic", "Simulation state topic"],
  ["availableWaypointsTopic", "Available waypoints topic"],
  ["navigationStateTopic", "Navigation state topic"],
  ["mapNameParameter", "Map-name parameter"],
  ["worldParameter", "Simulation-world parameter"],
  ["waypointNameParameter", "Waypoint-name parameter"],
  ["startMappingService", "Start mapping service"],
  ["stopMappingService", "Stop mapping service"],
  ["loadMapService", "Load map service"],
  ["restartSimulationService", "Restart simulation service"],
  ["saveWaypointService", "Save waypoint service"],
  ["navigateWaypointService", "Navigate waypoint service"],
  ["deleteWaypointService", "Delete waypoint service"],
  ["navigationStopService", "Navigation stop service"],
];

function isStringConfigKey(key: string | undefined): key is StringConfigKey {
  return STRING_CONFIG_SETTINGS.some(([candidate]) => candidate === key);
}

type PendingParameter = {
  parameter: string;
  expected: string;
  resolve: () => void;
  reject: (error: Error) => void;
  timeout: ReturnType<typeof setTimeout>;
};

type AdapterOptions = { parameterTimeoutMs?: number };

function stringMessageData(message: unknown): string {
  if (typeof message === "string") {
    return message;
  }
  if (typeof message === "object" && message != undefined && "data" in message) {
    return String(message.data);
  }
  return "";
}

function normalizeMode(message: unknown): MappingMode {
  const mode = stringMessageData(message).trim().toUpperCase();
  if (mode.includes("LOCALIZATION")) {
    return "LOCALIZATION";
  }
  if (mode.includes("MAPPING")) {
    return "MAPPING";
  }
  if (mode === "IDLE" || mode === "STOPPED") {
    return "IDLE";
  }
  return "UNKNOWN";
}

function normalizeWorld(message: unknown): SimulationWorld | "UNKNOWN" {
  const world = stringMessageData(message).trim();
  return isSimulationWorld(world) ? world : "UNKNOWN";
}

function normalizeNavigationState(message: unknown): NavigationState {
  const state = stringMessageData(message).trim().toUpperCase();
  if (state === "NAVIGATING") {
    return "NAVIGATING";
  }
  if (state === "IDLE" || state === "STOPPED") {
    return "IDLE";
  }
  return "UNKNOWN";
}

export class LichtblickAdapter {
  private config: PanelConfig;
  private driveController: DriveController;
  private readonly listeners = new Set<() => void>();
  private readonly parameterTimeoutMs: number;
  private pendingParameter?: PendingParameter;
  private disposed = false;
  private state: AdapterSnapshot;

  public constructor(
    private readonly context: PanelExtensionContext,
    initialConfig: unknown = context.initialState,
    options: AdapterOptions = {},
  ) {
    this.config = normalizeConfig(initialConfig);
    this.parameterTimeoutMs = options.parameterTimeoutMs ?? 3000;
    this.state = {
      config: this.config,
      mode: "UNKNOWN",
      maps: [],
      waypoints: [],
      navigationState: "UNKNOWN",
      world: "UNKNOWN",
      colorScheme: "dark",
      canPublish: context.publish != undefined && context.advertise != undefined,
      canCallServices: context.callService != undefined,
      busy: false,
    };
    this.driveController = this.createDriveController();

    for (const field of ["currentFrame", "parameters", "colorScheme"] as const) {
      context.watch(field);
    }
    this.subscribeToTopics();
    this.advertise();
    context.setDefaultPanelTitle("Robot Control");
    this.updateSettingsEditor();
    context.onRender = (renderState, done) => {
      try {
        this.processRender(renderState);
      } finally {
        done();
      }
    };
  }

  public get snapshot(): AdapterSnapshot {
    return this.state;
  }

  public get drive(): DriveController {
    return this.driveController;
  }

  public subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  public updateConfig(patch: Partial<PanelConfig>): void {
    const previousTopic = this.config.teleopTopic;
    this.driveController.dispose();
    if (this.context.unadvertise != undefined) {
      this.context.unadvertise(previousTopic);
    }
    this.config = normalizeConfig({ ...this.config, ...patch });
    this.driveController = this.createDriveController();
    this.state = { ...this.state, config: this.config };
    this.context.saveState(this.config);
    this.subscribeToTopics();
    this.advertise();
    this.updateSettingsEditor();
    this.emit();
  }

  public async runMapAction(mapName: string, actionKey: MapActionConfigKey): Promise<void> {
    const trimmedName = mapName.trim();
    if (!validateMapName(trimmedName)) {
      throw new Error("Enter a valid map name using letters, numbers, dashes, or underscores.");
    }
    const service = this.config[actionKey];
    if (service === "") {
      throw new Error("This action is not configured.");
    }
    if (this.context.callService == undefined) {
      throw new Error("This connection does not support service calls.");
    }

    this.setStatus(undefined, true);
    try {
      await this.setParameterAndWait(this.config.mapNameParameter, trimmedName);
      this.requireServiceSuccess(await this.context.callService(service, {}));
      this.setStatus(
        { kind: "success", message: `Requested ${actionKeyLabel(actionKey)}.` },
        false,
      );
    } catch (error) {
      const normalized = error instanceof Error ? error : new Error(String(error));
      this.setStatus({ kind: "error", message: normalized.message }, false);
      throw normalized;
    }
  }

  public async runSimulationAction(world: SimulationWorld): Promise<void> {
    if (!isSimulationWorld(world)) {
      throw new Error("Select a supported simulation world.");
    }
    if (this.context.callService == undefined) {
      throw new Error("This connection does not support service calls.");
    }
    this.setStatus(undefined, true);
    try {
      await this.setParameterAndWait(this.config.worldParameter, world);
      this.requireServiceSuccess(
        await this.context.callService(this.config.restartSimulationService, {}),
      );
      this.setStatus({ kind: "success", message: "Simulation restart requested." }, false);
    } catch (error) {
      const normalized = error instanceof Error ? error : new Error(String(error));
      this.setStatus({ kind: "error", message: normalized.message }, false);
      throw normalized;
    }
  }

  public async runWaypointAction(
    waypointName: string,
    actionKey: WaypointActionConfigKey,
  ): Promise<void> {
    const trimmedName = waypointName.trim();
    if (!validateMapName(trimmedName)) {
      throw new Error(
        "Enter a valid waypoint name using letters, numbers, dashes, or underscores.",
      );
    }
    const service = this.config[actionKey];
    if (service === "") {
      throw new Error("This action is not configured.");
    }
    if (this.context.callService == undefined) {
      throw new Error("This connection does not support service calls.");
    }

    this.setStatus(undefined, true);
    try {
      await this.setParameterAndWait(this.config.waypointNameParameter, trimmedName);
      this.requireServiceSuccess(await this.context.callService(service, {}));
      this.setStatus(
        { kind: "success", message: waypointActionMessage(actionKey, trimmedName) },
        false,
      );
    } catch (error) {
      const normalized = error instanceof Error ? error : new Error(String(error));
      this.setStatus({ kind: "error", message: normalized.message }, false);
      throw normalized;
    }
  }

  public async callConfiguredService(key: "navigationStopService"): Promise<void> {
    const service = this.config[key];
    if (service === "" || this.context.callService == undefined) {
      throw new Error("This action is not configured for the current connection.");
    }
    this.setStatus(undefined, true);
    try {
      this.requireServiceSuccess(await this.context.callService(service, {}));
      this.setStatus(
        { kind: "success", message: "Stop requested." },
        false,
      );
    } catch (error) {
      const normalized = error instanceof Error ? error : new Error(String(error));
      this.setStatus({ kind: "error", message: normalized.message }, false);
      throw normalized;
    }
  }

  public dispose(): void {
    if (this.disposed) {
      return;
    }
    this.disposed = true;
    this.pendingParameter?.reject(new Error("Panel closed before parameter acknowledgement."));
    if (this.pendingParameter != undefined) {
      clearTimeout(this.pendingParameter.timeout);
      this.pendingParameter = undefined;
    }
    this.driveController.dispose();
    this.context.unadvertise?.(this.config.teleopTopic);
    this.context.unsubscribeAll();
    this.context.onRender = undefined;
    this.listeners.clear();
  }

  private createDriveController(): DriveController {
    return new DriveController({
      config: this.config,
      publish: (message: Twist) => this.context.publish?.(this.config.teleopTopic, message),
    });
  }

  private advertise(): void {
    this.context.advertise?.(this.config.teleopTopic, "geometry_msgs/msg/Twist");
  }

  private subscribeToTopics(): void {
    this.context.subscribe([
      { topic: this.config.mappingStateTopic },
      { topic: this.config.availableMapsTopic },
      { topic: this.config.simulationStateTopic },
      { topic: this.config.availableWaypointsTopic },
      { topic: this.config.navigationStateTopic },
    ]);
  }

  private processRender(renderState: Immutable<RenderState>): void {
    let next = this.state;
    for (const event of renderState.currentFrame ?? []) {
      if (event.topic === this.config.mappingStateTopic) {
        next = { ...next, mode: normalizeMode(event.message) };
      } else if (event.topic === this.config.availableMapsTopic) {
        next = { ...next, maps: parseAvailableMaps(event.message) };
      } else if (event.topic === this.config.simulationStateTopic) {
        next = { ...next, world: normalizeWorld(event.message) };
      } else if (event.topic === this.config.availableWaypointsTopic) {
        next = { ...next, waypoints: parseAvailableMaps(event.message) };
      } else if (event.topic === this.config.navigationStateTopic) {
        next = { ...next, navigationState: normalizeNavigationState(event.message) };
      }
    }
    const selectedParameter = renderState.parameters?.get(this.config.mapNameParameter);
    const selectedMapName = typeof selectedParameter === "string" ? selectedParameter : undefined;
    if (selectedMapName != undefined) {
      next = { ...next, selectedParameter: selectedMapName };
    }
    if (renderState.colorScheme != undefined) {
      next = { ...next, colorScheme: renderState.colorScheme };
    }
    this.state = next;
    if (
      this.pendingParameter != undefined &&
      renderState.parameters?.get(this.pendingParameter.parameter) ===
        this.pendingParameter.expected
    ) {
      const pending = this.pendingParameter;
      this.pendingParameter = undefined;
      clearTimeout(pending.timeout);
      pending.resolve();
    }
    this.emit();
  }

  private setParameterAndWait(parameter: string, value: string): Promise<void> {
    if (this.pendingParameter != undefined) {
      return Promise.reject(new Error("Another map action is already in progress."));
    }
    return new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pendingParameter = undefined;
        reject(new Error("Timed out waiting for parameter acknowledgement."));
      }, this.parameterTimeoutMs);
      this.pendingParameter = { parameter, expected: value, resolve, reject, timeout };
      try {
        this.context.setParameter(parameter, value);
      } catch (error) {
        clearTimeout(timeout);
        this.pendingParameter = undefined;
        reject(error instanceof Error ? error : new Error(String(error)));
      }
    });
  }

  private setStatus(status: AdapterSnapshot["status"], busy: boolean): void {
    this.state = { ...this.state, status, busy };
    this.emit();
  }

  private requireServiceSuccess(response: unknown): void {
    if (
      typeof response === "object" &&
      response != undefined &&
      "success" in response &&
      response.success === false
    ) {
      const message = "message" in response ? String(response.message) : "Service refused action.";
      throw new Error(message);
    }
  }

  private emit(): void {
    for (const listener of this.listeners) {
      listener();
    }
  }

  private updateSettingsEditor(): void {
    const fields: SettingsTreeFields = {};
    for (const [key, label] of STRING_CONFIG_SETTINGS) {
      fields[key] = { label, input: "string", value: this.config[key] };
    }
    this.context.updatePanelSettingsEditor({
      actionHandler: (action: SettingsTreeAction) => {
        if (action.action !== "update") {
          return;
        }
        const key = action.payload.path.at(-1);
        const value = "value" in action.payload ? action.payload.value : undefined;
        if (isStringConfigKey(key) && typeof value === "string") {
          const patch: Partial<PanelConfig> = {};
          patch[key] = value;
          this.updateConfig(patch);
        }
      },
      nodes: { ros: { label: "ROS interfaces", fields } },
    });
  }
}

function actionKeyLabel(key: MapActionConfigKey): string {
  if (key === "startMappingService") {
    return "start mapping";
  }
  if (key === "stopMappingService") {
    return "stop mapping";
  }
  return "load map";
}

function waypointActionMessage(key: WaypointActionConfigKey, name: string): string {
  if (key === "saveWaypointService") {
    return `Saved current position as ${name}.`;
  }
  if (key === "navigateWaypointService") {
    return `Navigation request sent for ${name}.`;
  }
  return `Deleted waypoint ${name}.`;
}

export { DEFAULT_CONFIG };
