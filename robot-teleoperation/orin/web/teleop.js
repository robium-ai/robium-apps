// Teleop: hold-to-drive directional buttons + keyboard, driving a ~10 Hz Twist publish loop.
// Releasing a button (or keyup / window blur) publishes a zero Twist.
export const LIN = 0.15;   // m/s cap
export const ANG = 0.4;    // rad/s cap
const RATE_HZ = 10;

export class Teleop {
  constructor(client) {
    this.client = client;
    this.lin = 0; this.ang = 0; this.timer = null;
  }
  _tick() { this.client.publishTwist(this.lin, this.ang); }
  set(lin, ang) {
    this.lin = lin; this.ang = ang;
    if (!this.timer) this.timer = setInterval(() => this._tick(), 1000 / RATE_HZ);
    this._tick();
  }
  stop() {
    this.lin = 0; this.ang = 0;
    this.client.publishTwist(0, 0);
    if (this.timer) { clearInterval(this.timer); this.timer = null; }
  }
  bindButton(el, lin, ang) {
    const down = (e) => { e.preventDefault(); this.set(lin, ang); };
    const up = (e) => { e.preventDefault(); this.stop(); };
    el.addEventListener('pointerdown', down);
    el.addEventListener('pointerup', up);
    el.addEventListener('pointerleave', up);
    el.addEventListener('pointercancel', up);
  }
  bindKeyboard() {
    const map = {
      'w': [LIN, 0], 'arrowup': [LIN, 0], 's': [-LIN, 0], 'arrowdown': [-LIN, 0],
      'a': [0, ANG], 'arrowleft': [0, ANG], 'd': [0, -ANG], 'arrowright': [0, -ANG],
    };
    let held = null;
    window.addEventListener('keydown', (e) => {
      const k = e.key.toLowerCase(); if (!(k in map)) return;
      e.preventDefault(); held = k; this.set(map[k][0], map[k][1]);
    });
    window.addEventListener('keyup', (e) => { if (e.key.toLowerCase() === held) { held = null; this.stop(); } });
    window.addEventListener('blur', () => { held = null; this.stop(); });
  }
}
