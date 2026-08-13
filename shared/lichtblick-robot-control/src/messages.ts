export type Direction = "forward" | "backward" | "left" | "right";

export type Twist = {
  linear: { x: number; y: number; z: number };
  angular: { x: number; y: number; z: number };
};

export const ZERO_TWIST: Twist = {
  linear: { x: 0, y: 0, z: 0 },
  angular: { x: 0, y: 0, z: 0 },
};
