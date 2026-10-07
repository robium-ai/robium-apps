// Standard Gamepad layout: Stadia USB/Bluetooth as mapped by the browser.
function deadzone(value, zone = 0.15) {
  if (!Number.isFinite(value) || Math.abs(value) <= zone) return 0;
  return Math.sign(value) * Math.min(1, (Math.abs(value) - zone) / (1 - zone));
}
function readPad(pad, previous = [], allowStrafe = true) {
  const pressed = i => !!pad.buttons[i]?.pressed;
  const edge = i => pressed(i) && !previous[i];
  const axes = pad.axes.map(v => deadzone(v));
  let action = null;
  if (edge(0)) action = 'Stand';
  if (edge(2)) action = 'Low profile';
  if (edge(3)) action = 'High profile';
  if (pressed(1)) action = 'Stop'; // Stop always wins, including simultaneous buttons.
  const dpadX = Number(pressed(12)) - Number(pressed(13));
  const dpadY = Number(pressed(14)) - Number(pressed(15));
  let vx = dpadX ? dpadX * .35 : -(axes[1] || 0);
  let vy = allowStrafe ? (dpadY ? dpadY * .35 : -(axes[0] || 0)) : 0;
  const magnitude = Math.hypot(vx, vy);
  if (magnitude > 1) { vx /= magnitude; vy /= magnitude; }
  return {vx, vy, wz: -(axes[2] || 0), height: 0, action,
    buttons: pad.buttons.map(b => b.pressed)};
}
if (typeof module !== 'undefined') module.exports = {deadzone, readPad};
