export type PanelConfig = {
  version: 1;
  teleopTopic: string;
  mappingStateTopic: string;
  availableMapsTopic: string;
  mapNameParameter: string;
  startMappingService: string;
  stopMappingService: string;
  loadMapService: string;
  goHomeService: string;
  navigationStopService: string;
  linearSpeed: number;
  angularSpeed: number;
  publishRateHz: number;
};

export const DEFAULT_CONFIG: PanelConfig = {
  version: 1,
  teleopTopic: "/cmd_vel_teleop",
  mappingStateTopic: "/mapping/state",
  availableMapsTopic: "/maps/available",
  mapNameParameter: "/map_manager.map_name",
  startMappingService: "/mapping/reset",
  stopMappingService: "/mapping/save",
  loadMapService: "/mapping/load",
  goHomeService: "",
  navigationStopService: "",
  linearSpeed: 0.2,
  angularSpeed: 0.8,
  publishRateHz: 10,
};

const stringKeys: (keyof PanelConfig)[] = [
  "teleopTopic",
  "mappingStateTopic",
  "availableMapsTopic",
  "mapNameParameter",
  "startMappingService",
  "stopMappingService",
  "loadMapService",
  "goHomeService",
  "navigationStopService",
];

export function normalizeConfig(value: unknown): PanelConfig {
  if (value == undefined || typeof value !== "object") {
    return { ...DEFAULT_CONFIG };
  }
  const candidate = value as Record<string, unknown>;
  const config = { ...DEFAULT_CONFIG };
  for (const key of stringKeys) {
    if (typeof candidate[key] === "string") {
      (config[key] as string) = candidate[key];
    }
  }
  for (const key of ["linearSpeed", "angularSpeed", "publishRateHz"] as const) {
    const next = candidate[key];
    if (typeof next === "number" && Number.isFinite(next) && next > 0) {
      config[key] = next;
    }
  }
  return config;
}

export function validateMapName(name: string): boolean {
  return /^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$/.test(name);
}

export function parseAvailableMaps(message: unknown): string[] {
  const raw =
    typeof message === "string"
      ? message
      : typeof message === "object" && message != undefined && "data" in message
        ? String(message.data)
        : "";
  return [...new Set(raw.split(/[\n,;]/).map((name) => name.trim()))]
    .filter((name) => name.toLowerCase() !== "none" && validateMapName(name))
    .sort((left, right) => left.localeCompare(right));
}
