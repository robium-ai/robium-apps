export type SimulationWorld = {
  value: string;
  label: string;
};

export type PanelConfig = {
  version: 4;
  showMovement: boolean;
  showMaps: boolean;
  showNavigation: boolean;
  showSimulation: boolean;
  showQuickActions: boolean;
  simulationWorlds: SimulationWorld[];
  teleopTopic: string;
  mappingStateTopic: string;
  availableMapsTopic: string;
  simulationStateTopic: string;
  availableWaypointsTopic: string;
  navigationStateTopic: string;
  mapNameParameter: string;
  worldParameter: string;
  waypointNameParameter: string;
  startMappingService: string;
  stopMappingService: string;
  loadMapService: string;
  restartSimulationService: string;
  saveWaypointService: string;
  navigateWaypointService: string;
  deleteWaypointService: string;
  navigationStopService: string;
  linearSpeed: number;
  angularSpeed: number;
  publishRateHz: number;
};

export const DEFAULT_CONFIG: PanelConfig = {
  version: 4,
  showMovement: true,
  showMaps: false,
  showNavigation: false,
  showSimulation: false,
  showQuickActions: true,
  simulationWorlds: [],
  teleopTopic: "/cmd_vel",
  mappingStateTopic: "/mapping/state",
  availableMapsTopic: "/maps/available",
  simulationStateTopic: "/simulation/state",
  availableWaypointsTopic: "/waypoints/available",
  navigationStateTopic: "/navigation/state",
  mapNameParameter: "/session_manager.map_name",
  worldParameter: "/session_manager.world",
  waypointNameParameter: "/session_manager.waypoint_name",
  startMappingService: "/mapping/start",
  stopMappingService: "/mapping/stop",
  loadMapService: "/mapping/load",
  restartSimulationService: "/simulation/restart",
  saveWaypointService: "/waypoints/save",
  navigateWaypointService: "/waypoints/navigate",
  deleteWaypointService: "/waypoints/delete",
  navigationStopService: "/navigation/stop",
  linearSpeed: 0.2,
  angularSpeed: 0.8,
  publishRateHz: 10,
};

const LEGACY_SIMULATION_WORLDS: SimulationWorld[] = [
  { value: "furnished_house", label: "House" },
  { value: "tugbot_warehouse", label: "Warehouse" },
];

export const CAPABILITY_KEYS = [
  "showMovement",
  "showMaps",
  "showNavigation",
  "showSimulation",
  "showQuickActions",
] as const;

export type CapabilityKey = (typeof CAPABILITY_KEYS)[number];

const stringKeys: (keyof PanelConfig)[] = [
  "teleopTopic",
  "mappingStateTopic",
  "availableMapsTopic",
  "simulationStateTopic",
  "availableWaypointsTopic",
  "navigationStateTopic",
  "mapNameParameter",
  "worldParameter",
  "waypointNameParameter",
  "startMappingService",
  "stopMappingService",
  "loadMapService",
  "restartSimulationService",
  "saveWaypointService",
  "navigateWaypointService",
  "deleteWaypointService",
  "navigationStopService",
];

function normalizeSimulationWorlds(value: unknown): SimulationWorld[] {
  if (!Array.isArray(value)) {
    return [];
  }
  const worlds: SimulationWorld[] = [];
  for (const candidate of value) {
    if (
      typeof candidate === "object" &&
      candidate != undefined &&
      "value" in candidate &&
      "label" in candidate &&
      typeof candidate.value === "string" &&
      candidate.value.trim() !== "" &&
      typeof candidate.label === "string" &&
      candidate.label.trim() !== ""
    ) {
      worlds.push({ value: candidate.value.trim(), label: candidate.label.trim() });
    }
  }
  return worlds;
}

export function isSimulationWorld(value: string, worlds: SimulationWorld[]): boolean {
  return worlds.some((world) => world.value === value);
}

export function normalizeConfig(value: unknown): PanelConfig {
  if (value == undefined || typeof value !== "object") {
    return { ...DEFAULT_CONFIG, simulationWorlds: [] };
  }
  const candidate = value as Record<string, unknown>;
  const candidateVersion =
    typeof candidate.version === "number" && Number.isFinite(candidate.version)
      ? candidate.version
      : 0;
  const config: PanelConfig = { ...DEFAULT_CONFIG, simulationWorlds: [] };

  for (const key of stringKeys) {
    if (key === "navigationStopService" && candidateVersion < 3 && candidate[key] === "") {
      continue;
    }
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

  if (candidateVersion < 4) {
    for (const key of CAPABILITY_KEYS) {
      config[key] = true;
    }
    config.simulationWorlds = LEGACY_SIMULATION_WORLDS.map((world) => ({ ...world }));
  } else {
    for (const key of CAPABILITY_KEYS) {
      if (typeof candidate[key] === "boolean") {
        config[key] = candidate[key];
      }
    }
    config.simulationWorlds = normalizeSimulationWorlds(candidate.simulationWorlds);
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
