import assert from "node:assert/strict";
import test from "node:test";

import { IDBFactory } from "fake-indexeddb";

import { installDefaultExtension } from "./preinstall-extension.mjs";

const PACKAGE = {
  name: "robot-control",
  displayName: "Robium Robot Control",
  description: "Robot controls",
  publisher: "robium",
  version: "0.1.0",
  main: "./dist/extension.js",
};

function response(value) {
  return {
    ok: true,
    async arrayBuffer() {
      return Uint8Array.from(value).buffer;
    },
    async json() {
      return value;
    },
    async text() {
      return value;
    },
  };
}

function makeFetch({ bytes, packageInfo = PACKAGE }) {
  const fixtures = new Map([
    ["/robium/robot-control.foxe", response(bytes)],
    ["/robium/package.json", response(packageInfo)],
    ["/robium/README.md", response("# Robot Control")],
    ["/robium/CHANGELOG.md", response("# Changes")],
  ]);
  return async (url) => {
    const found = fixtures.get(url);
    assert.ok(found, `unexpected URL: ${url}`);
    return found;
  };
}

function requestResult(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

async function readRecord(indexedDB, storeName, key) {
  const open = indexedDB.open("lichtblick-extensions-local", 1);
  const db = await requestResult(open);
  const record = await requestResult(db.transaction(storeName).objectStore(storeName).get(key));
  db.close();
  return record;
}

test("preinstalls the packaged extension into a clean Lichtblick profile", async () => {
  const indexedDB = new IDBFactory();

  const info = await installDefaultExtension({
    indexedDB,
    fetch: makeFetch({ bytes: [70, 79, 88, 69] }),
    baseUrl: "/robium/",
  });

  assert.equal(info.id, "robium.robot-control");
  assert.equal(info.namespace, "local");
  assert.equal(info.qualifiedName, "Robium Robot Control");
  assert.equal(info.readme, "# Robot Control");
  assert.equal(info.changelog, "# Changes");
  assert.equal(info.size, 4);

  const metadata = await readRecord(indexedDB, "metadata", info.id);
  const extension = await readRecord(indexedDB, "extensions", info.id);
  assert.deepEqual(metadata, info);
  assert.deepEqual(extension.info, info);
  assert.ok(extension.content instanceof Uint8Array);
  assert.deepEqual(Array.from(extension.content), [70, 79, 88, 69]);
});

test("refreshes a preinstalled extension when the bundled package changes", async () => {
  const indexedDB = new IDBFactory();
  await installDefaultExtension({
    indexedDB,
    fetch: makeFetch({ bytes: [1] }),
    baseUrl: "/robium/",
  });

  const upgradedPackage = { ...PACKAGE, version: "0.2.0" };
  await installDefaultExtension({
    indexedDB,
    fetch: makeFetch({ bytes: [2, 3], packageInfo: upgradedPackage }),
    baseUrl: "/robium/",
  });

  const extension = await readRecord(indexedDB, "extensions", "robium.robot-control");
  assert.equal(extension.info.version, "0.2.0");
  assert.equal(extension.info.size, 2);
  assert.deepEqual(Array.from(extension.content), [2, 3]);
});
