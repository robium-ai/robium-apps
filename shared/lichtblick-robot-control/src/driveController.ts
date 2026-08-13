import type { Direction, Twist } from "./messages";
import { ZERO_TWIST } from "./messages";
import type { PanelConfig } from "./panelConfig";

type DriveControllerOptions = {
  config: Pick<PanelConfig, "linearSpeed" | "angularSpeed" | "publishRateHz">;
  publish: (message: Twist) => void;
  setInterval?: (callback: () => void, intervalMs: number) => unknown;
  clearInterval?: (handle: unknown) => void;
};

export class DriveController {
  private readonly held = new Set<Direction>();
  private readonly publish: (message: Twist) => void;
  private readonly setIntervalFn: (callback: () => void, intervalMs: number) => unknown;
  private readonly clearIntervalFn: (handle: unknown) => void;
  private readonly config: DriveControllerOptions["config"];
  private intervalHandle: unknown;

  public constructor(options: DriveControllerOptions) {
    this.config = options.config;
    this.publish = options.publish;
    this.setIntervalFn =
      options.setInterval ?? ((callback, ms) => globalThis.setInterval(callback, ms));
    this.clearIntervalFn =
      options.clearInterval ?? ((handle) => globalThis.clearInterval(handle as number));
  }

  public press(direction: Direction): void {
    this.held.add(direction);
    this.publishCurrent();
    this.intervalHandle ??= this.setIntervalFn(
      () => this.publishCurrent(),
      1000 / this.config.publishRateHz,
    );
  }

  public release(direction: Direction): void {
    this.held.delete(direction);
    if (this.held.size === 0) {
      this.clearTimer();
    }
    this.publishCurrent();
  }

  public stop(): void {
    this.held.clear();
    this.clearTimer();
    this.publish({
      ...ZERO_TWIST,
      linear: { ...ZERO_TWIST.linear },
      angular: { ...ZERO_TWIST.angular },
    });
  }

  public dispose(): void {
    this.stop();
  }

  private clearTimer(): void {
    if (this.intervalHandle != undefined) {
      this.clearIntervalFn(this.intervalHandle);
      this.intervalHandle = undefined;
    }
  }

  private publishCurrent(): void {
    const forward = Number(this.held.has("forward")) - Number(this.held.has("backward"));
    const turn = Number(this.held.has("left")) - Number(this.held.has("right"));
    this.publish({
      linear: { x: forward * this.config.linearSpeed, y: 0, z: 0 },
      angular: { x: 0, y: 0, z: turn * this.config.angularSpeed },
    });
  }
}
