const DATABASE_NAME = "lichtblick-extensions-local";
const DATABASE_VERSION = 1;
const METADATA_STORE = "metadata";
const EXTENSION_STORE = "extensions";

function requestResult(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("IndexedDB request failed"));
  });
}

function transactionDone(transaction) {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = () => resolve();
    transaction.onerror = () => reject(transaction.error ?? new Error("IndexedDB write failed"));
    transaction.onabort = () => reject(transaction.error ?? new Error("IndexedDB write aborted"));
  });
}

async function checkedResponse(fetchImpl, url) {
  const result = await fetchImpl(url, { cache: "no-store" });
  if (!result.ok) {
    throw new Error(`Could not load bundled extension asset: ${url}`);
  }
  return result;
}

async function openExtensionDatabase(indexedDB) {
  const request = indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
  request.onupgradeneeded = () => {
    const database = request.result;
    if (!database.objectStoreNames.contains(METADATA_STORE)) {
      database.createObjectStore(METADATA_STORE, { keyPath: "id" });
    }
    if (!database.objectStoreNames.contains(EXTENSION_STORE)) {
      database.createObjectStore(EXTENSION_STORE, { keyPath: "info.id" });
    }
  };
  return await requestResult(request);
}

export async function installDefaultExtension({ indexedDB, fetch: fetchImpl, baseUrl }) {
  const normalizedBaseUrl = baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`;
  const [foxeResponse, packageResponse, readmeResponse, changelogResponse] = await Promise.all([
    checkedResponse(fetchImpl, `${normalizedBaseUrl}robot-control.foxe`),
    checkedResponse(fetchImpl, `${normalizedBaseUrl}package.json`),
    checkedResponse(fetchImpl, `${normalizedBaseUrl}README.md`),
    checkedResponse(fetchImpl, `${normalizedBaseUrl}CHANGELOG.md`),
  ]);
  const [foxeBuffer, packageInfo, readme, changelog] = await Promise.all([
    foxeResponse.arrayBuffer(),
    packageResponse.json(),
    readmeResponse.text(),
    changelogResponse.text(),
  ]);

  if (!packageInfo.name || !packageInfo.publisher) {
    throw new Error("Bundled extension package requires name and publisher");
  }

  const content = new Uint8Array(foxeBuffer);
  const normalizedPublisher = packageInfo.publisher.replace(/[^A-Za-z0-9_\s]+/g, "");
  const normalizedName = packageInfo.name.toLowerCase();
  const info = {
    ...packageInfo,
    name: normalizedName,
    id: `${normalizedPublisher}.${normalizedName}`,
    namespace: "local",
    qualifiedName: packageInfo.displayName || normalizedName,
    readme,
    changelog,
    size: content.length,
  };

  const database = await openExtensionDatabase(indexedDB);
  try {
    const transaction = database.transaction([METADATA_STORE, EXTENSION_STORE], "readwrite");
    const done = transactionDone(transaction);
    transaction.objectStore(METADATA_STORE).put(info);
    transaction.objectStore(EXTENSION_STORE).put({ info, content });
    await done;
  } finally {
    database.close();
  }
  return info;
}
