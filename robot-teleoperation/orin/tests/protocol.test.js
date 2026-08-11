import { test } from 'node:test';
import assert from 'node:assert/strict';
import { encodeTwist, encodeEmpty } from '../web/protocol.js';

test('encodeTwist: 52 bytes, CDR_LE header, values round-trip', () => {
  const bytes = encodeTwist(0.15, -0.4);
  assert.equal(bytes.length, 52);
  assert.deepEqual([...bytes.slice(0, 4)], [0x00, 0x01, 0x00, 0x00]);
  const dv = new DataView(bytes.buffer);
  assert.equal(dv.getFloat64(4, true), 0.15);    // linear.x
  assert.equal(dv.getFloat64(12, true), 0);      // linear.y
  assert.equal(dv.getFloat64(44, true), -0.4);   // angular.z
});

test('encodeEmpty: 4-byte CDR_LE header', () => {
  assert.deepEqual([...encodeEmpty()], [0x00, 0x01, 0x00, 0x00]);
});
