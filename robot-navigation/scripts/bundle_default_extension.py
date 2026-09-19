#!/usr/bin/env python3
"""Start Lichtblick only after the bundled extension and layout are in place."""

import argparse
import hashlib
import json
import re
from pathlib import Path


DEFERRED_SCRIPT = re.compile(
    r"<script"
    r"(?=[^>]*\bdefer(?:=(?:\"defer\"|'defer'|defer))?)"
    r"(?=[^>]*\bsrc=(?P<quote>[\"'])(?P<src>[^\"']+\.js)(?P=quote))"
    r"[^>]*></script>"
)

# Lichtblick persists the layout in IndexedDB, so the bundled layout in
# index.html is consulted only when the browser has no layout of its own.
# After the first visit a shipped layout change is invisible until the user
# clears site data. These constants address that store directly; they are
# verified against the Lichtblick image digest pinned in docker/Dockerfile,
# and must be re-verified whenever that digest moves.
LAYOUT_DB = "lichtblick-layouts"
LAYOUT_STORE = "layouts"
LAYOUT_ID = "0e0dd0d4-5f3a-4a7a-9a4c-6e1f2b6f9a10"
REVISION_KEY = "robium.robot-navigation.layout-revision"
PROFILE_KEY = "studio.profile-data"


def rewrite_index(html: str, revision: str = "unversioned") -> str:
    matches = list(DEFERRED_SCRIPT.finditer(html))
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one deferred main script, found {len(matches)}; "
            "upstream Lichtblick page changed"
        )

    if re.fullmatch(r"[A-Za-z0-9_-]+", revision) is None:
        raise ValueError("extension revision must be URL-safe")

    main_script = matches[0].group("src")
    bootstrap = f'''<script type="module">
// The layout revision is computed HERE, in the browser, rather than baked in
// at build time: scripts/viz_server.py re-reads its layout file on every
// request so the file can be edited live, and a build-time hash would go
// stale the moment it was. Hashing whatever the page actually carries keeps
// both serving paths honest.
const layoutRevision = (layout) => {{
  const text = JSON.stringify(layout);
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {{
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }}
  return "v1-" + hash.toString(16);
}};
const requestResult = (request) => new Promise((resolve, reject) => {{
  request.onsuccess = () => resolve(request.result);
  request.onerror = () => reject(request.error ?? new Error("IndexedDB request failed"));
}});
const transactionDone = (transaction) => new Promise((resolve, reject) => {{
  transaction.oncomplete = () => resolve();
  transaction.onerror = () => reject(transaction.error ?? new Error("IndexedDB write failed"));
  transaction.onabort = () => reject(transaction.error ?? new Error("IndexedDB write aborted"));
}});
const installBundledLayout = async (layoutData) => {{
  const openRequest = globalThis.indexedDB.open({json.dumps(LAYOUT_DB)}, 1);
  openRequest.onupgradeneeded = () => {{
    const database = openRequest.result;
    if (!database.objectStoreNames.contains({json.dumps(LAYOUT_STORE)})) {{
      const store = database.createObjectStore({json.dumps(LAYOUT_STORE)}, {{
        keyPath: ["namespace", "layout.id"],
      }});
      store.createIndex("namespace", "namespace");
    }}
  }};
  const database = await requestResult(openRequest);
  try {{
    const transaction = database.transaction([{json.dumps(LAYOUT_STORE)}], "readwrite");
    transaction.objectStore({json.dumps(LAYOUT_STORE)}).put({{
      namespace: "local",
      layout: {{
        id: {json.dumps(LAYOUT_ID)},
        name: "Robium Default",
        permission: "CREATOR_WRITE",
        baseline: {{ data: layoutData, savedAt: new Date().toISOString() }},
      }},
    }});
    await transactionDone(transaction);
  }} finally {{
    database.close();
  }}
  const stored = globalThis.localStorage.getItem({json.dumps(PROFILE_KEY)});
  const profile = stored == undefined ? {{}} : JSON.parse(stored);
  profile.currentLayoutId = {json.dumps(LAYOUT_ID)};
  globalThis.localStorage.setItem({json.dumps(PROFILE_KEY)}, JSON.stringify(profile));
}};
try {{
  const layoutData = globalThis.LICHTBLICK_SUITE_DEFAULT_LAYOUT;
  if (layoutData != undefined) {{
    const revision = layoutRevision(layoutData);
    // Only when the SHIPPED layout changes. A layout the user rearranged and
    // saved themselves survives every reload until we ship a different one.
    if (globalThis.localStorage.getItem({json.dumps(REVISION_KEY)}) !== revision) {{
      await installBundledLayout(layoutData);
      globalThis.localStorage.setItem({json.dumps(REVISION_KEY)}, revision);
    }}
  }}
}} catch (error) {{
  console.warn("Could not install the bundled Robium layout", error);
}}
import {{ installDefaultExtension }} from "./robium/preinstall-extension.mjs?v={revision}";
try {{
  await installDefaultExtension({{
    indexedDB: globalThis.indexedDB,
    fetch: globalThis.fetch.bind(globalThis),
    baseUrl: "./robium/",
  }});
}} catch (error) {{
  console.error("Could not preinstall the Robium Dashboard extension", error);
}}
const script = document.createElement("script");
script.defer = true;
script.src = {json.dumps(main_script)} + "?v={revision}";
document.head.append(script);
</script>'''
    return DEFERRED_SCRIPT.sub(bootstrap, html, count=1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("index", type=Path)
    parser.add_argument("--revision-file", required=True, type=Path)
    args = parser.parse_args()
    original = args.index.read_text(encoding="utf-8")
    revision = hashlib.sha256(args.revision_file.read_bytes()).hexdigest()[:16]
    args.index.write_text(rewrite_index(original, revision=revision), encoding="utf-8")
    print(f"bundled extension bootstrap injected into {args.index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
