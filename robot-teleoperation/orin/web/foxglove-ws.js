import { encodeTwist, encodeEmpty } from './protocol.js';

// Minimal Foxglove WebSocket client for CLIENT PUBLISHING only (no subscribe).
// Wire format (foxglove ws-protocol):
//   client advertise (JSON): {"op":"advertise","channels":[{id,topic,encoding:"cdr",schemaName}]}
//   client data frame (binary): [0x01][channelId uint32 LE][payload]
// This is the same client-publish path Foxglove's own Teleop panel uses on this bridge
// (foxglove_bridge 3.4.2, subprotocol foxglove.sdk.v1). Verified live in Task 8.
const CLIENT_MSG_DATA = 0x01;

export class FoxgloveClient {
  constructor(url, onStatus = () => {}) {
    this.url = url;
    this.onStatus = onStatus;
    this.ws = null;
    this.nextId = 1;
    this.channels = {}; // topic -> { id }
  }

  connect() {
    this.onStatus('connecting');
    this.ws = new WebSocket(this.url, ['foxglove.sdk.v1']);
    this.ws.binaryType = 'arraybuffer';
    this.ws.onopen = () => this._advertiseAll();
    this.ws.onclose = () => { this.onStatus('disconnected'); setTimeout(() => this.connect(), 2000); };
    this.ws.onerror = () => this.onStatus('error');
    this.ws.onmessage = (ev) => {
      if (typeof ev.data === 'string') {
        const msg = JSON.parse(ev.data);
        if (msg.op === 'serverInfo') this.onStatus('connected');
      }
    };
  }

  _advertise(topic, schemaName) {
    const id = this.nextId++;
    this.channels[topic] = { id };
    this.ws.send(JSON.stringify({ op: 'advertise', channels: [{ id, topic, encoding: 'cdr', schemaName }] }));
  }

  _advertiseAll() {
    this._advertise('/cmd_vel', 'geometry_msgs/msg/Twist');
    this._advertise('/teleop/dock', 'std_msgs/msg/Empty');
    this._advertise('/teleop/undock', 'std_msgs/msg/Empty');
  }

  _sendData(topic, payload) {
    const ch = this.channels[topic];
    if (!ch || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    const frame = new Uint8Array(5 + payload.length);
    frame[0] = CLIENT_MSG_DATA;
    new DataView(frame.buffer).setUint32(1, ch.id, true);
    frame.set(payload, 5);
    this.ws.send(frame);
  }

  publishTwist(linearX, angularZ) { this._sendData('/cmd_vel', encodeTwist(linearX, angularZ)); }
  dock() { this._sendData('/teleop/dock', encodeEmpty()); }
  undock() { this._sendData('/teleop/undock', encodeEmpty()); }
}
