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
    if len(sys.argv) != 3:
        raise SystemExit("usage: bundle_extension.py INDEX_HTML EXTENSION_FOXE")
    index = Path(sys.argv[1])
    extension = Path(sys.argv[2])
    html = index.read_text(encoding="utf-8")
    matches = list(DEFERRED_SCRIPT.finditer(html))
    if len(matches) != 1:
        raise ValueError(
            f"expected one deferred Lichtblick script, found {len(matches)}"
        )
    main_script = matches[0].group("src")
    revision = hashlib.sha256(extension.read_bytes()).hexdigest()[:16]
    bootstrap = f'''<script type="module">
import {{ installDefaultExtension }} from "./robium/preinstall-extension.mjs?v={revision}";
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
script.src = {json.dumps(main_script)};
document.head.append(script);
</script>'''
    index.write_text(
        DEFERRED_SCRIPT.sub(bootstrap, html, count=1), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
