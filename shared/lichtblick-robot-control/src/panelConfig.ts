export type PanelConfig = {
  version: 3;
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
  version: 3,
  teleopTopic: "/cmd_vel_teleop",
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

export const SIMULATION_WORLDS = [
  { value: "furnished_house", label: "House" },
  { value: "tugbot_warehouse", label: "Warehouse" },
] as const;

export type SimulationWorld = (typeof SIMULATION_WORLDS)[number]["value"];

export function isSimulationWorld(value: string): value is SimulationWorld {
  return SIMULATION_WORLDS.some((world) => world.value === value);
}

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
