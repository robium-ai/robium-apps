// Foxglove/ROS 2 CDR encoders + the app.foxglove.dev deep-link builder.
// Pure functions — no DOM, no WebSocket — so they unit-test under `node --test`.

// CDR encapsulation header, little-endian (CDR_LE): representation id 0x0001, options 0x0000.
const CDR_LE_HEADER = [0x00, 0x01, 0x00, 0x00];

// geometry_msgs/msg/Twist = {linear:{x,y,z}, angular:{x,y,z}} — six float64, 8-aligned from
// the body start so no padding. 4-byte header + 48 bytes = 52 bytes.
export function encodeTwist(linearX, angularZ) {
  const buf = new ArrayBuffer(52);
  const dv = new DataView(buf);
  CDR_LE_HEADER.forEach((b, i) => dv.setUint8(i, b));
  dv.setFloat64(4, linearX, true);    // linear.x
  dv.setFloat64(12, 0, true);         // linear.y
  dv.setFloat64(20, 0, true);         // linear.z
  dv.setFloat64(28, 0, true);         // angular.x
  dv.setFloat64(36, 0, true);         // angular.y
  dv.setFloat64(44, angularZ, true);  // angular.z
  return new Uint8Array(buf);
}

// std_msgs/msg/Empty has no fields → CDR is just the encapsulation header.
// (If the bridge/helper ever rejects a 4-byte Empty, the fallback is a trailing 0 byte;
// the undock HIL check in Task 8 is the source of truth.)
export function encodeEmpty() {
  return new Uint8Array(CDR_LE_HEADER);
}
