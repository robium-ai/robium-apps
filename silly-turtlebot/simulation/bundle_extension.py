#!/usr/bin/env python3
"""Preinstall the bundled mission-control extension before Lichtblick starts."""

import hashlib
import json
import re
import sys
from pathlib import Path


DEFERRED_SCRIPT = re.compile(
    r"<script"
    r"(?=[^>]*\bdefer(?:=(?:\"defer\"|'defer'|defer))?)"
    r"(?=[^>]*\bsrc=(?P<quote>[\"'])(?P<src>[^\"']+\.js)(?P=quote))"
    r"[^>]*></script>"
)


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "usage: bundle_extension.py INDEX_HTML EXTENSION_FOXE LAYOUT_JSON"
        )
    index = Path(sys.argv[1])
    extension = Path(sys.argv[2])
    layout = Path(sys.argv[3])
    html = index.read_text(encoding="utf-8")
    matches = list(DEFERRED_SCRIPT.finditer(html))
    if len(matches) != 1:
        raise ValueError(
            f"expected one deferred Lichtblick script, found {len(matches)}"
        )
    main_script = matches[0].group("src")
    extension_revision = hashlib.sha256(extension.read_bytes()).hexdigest()[:16]
    layout_revision = "v2-" + hashlib.sha256(layout.read_bytes()).hexdigest()[:16]
    bootstrap = f'''<script type="module">
const layoutRevisionKey = "robium.silly-turtlebot.layout-revision-v2";
const canonicalLayoutId = "927dc947-d544-4a58-9634-81f4eb3290dc";
const requestResult = (request) => new Promise((resolve, reject) => {{
  request.onsuccess = () => resolve(request.result);
  request.onerror = () => reject(request.error ?? new Error("IndexedDB request failed"));
}});
const transactionDone = (transaction) => new Promise((resolve, reject) => {{
  transaction.oncomplete = () => resolve();
  transaction.onerror = () => reject(transaction.error ?? new Error("IndexedDB write failed"));
  transaction.onabort = () => reject(transaction.error ?? new Error("IndexedDB write aborted"));
}});
const installBundledLayout = async () => {{
  const layoutData = globalThis.LICHTBLICK_SUITE_DEFAULT_LAYOUT;
  if (layoutData == undefined) {{
    throw new Error("Bundled layout is unavailable");
  }}
  const openRequest = globalThis.indexedDB.open("lichtblick-layouts", 1);
  openRequest.onupgradeneeded = () => {{
    const database = openRequest.result;
    if (!database.objectStoreNames.contains("layouts")) {{
      const store = database.createObjectStore("layouts", {{
        keyPath: ["namespace", "layout.id"],
      }});
      store.createIndex("namespace", "namespace");
    }}
  }};
  const database = await requestResult(openRequest);
  try {{
    const transaction = database.transaction(["layouts"], "readwrite");
    transaction.objectStore("layouts").put({{
      namespace: "local",
      layout: {{
        id: canonicalLayoutId,
        name: "Default",
        permission: "CREATOR_WRITE",
        baseline: {{ data: layoutData, savedAt: new Date().toISOString() }},
      }},
    }});
    await transactionDone(transaction);
  }} finally {{
    database.close();
  }}
  const profileDataKey = "studio.profile-data";
  const storedProfile = globalThis.localStorage.getItem(profileDataKey);
  const profile = storedProfile == undefined ? {{}} : JSON.parse(storedProfile);
  profile.currentLayoutId = canonicalLayoutId;
  globalThis.localStorage.setItem(profileDataKey, JSON.stringify(profile));
}};
try {{
  if (globalThis.localStorage.getItem(layoutRevisionKey) !== "{layout_revision}") {{
    await installBundledLayout();
    globalThis.localStorage.setItem(layoutRevisionKey, "{layout_revision}");
  }}
}} catch (error) {{
  console.warn("Could not migrate the bundled Silly TurtleBot layout", error);
}}
import {{ installDefaultExtension }} from "./robium/preinstall-extension.mjs?v={extension_revision}";
try {{
  await installDefaultExtension({{
    indexedDB: globalThis.indexedDB,
    fetch: globalThis.fetch.bind(globalThis),
    baseUrl: "./robium/",
  }});
}} catch (error) {{
  console.error("Could not preinstall Silly TurtleBot controls", error);
}}
const script = document.createElement("script");
script.defer = true;
script.src = {json.dumps(main_script + "?v=" + extension_revision)};
document.head.append(script);
</script>'''
    index.write_text(
        DEFERRED_SCRIPT.sub(bootstrap, html, count=1), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
