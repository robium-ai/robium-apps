#!/usr/bin/env python3
"""Start Lichtblick only after the bundled local extension is available."""

import argparse
import json
import re
from pathlib import Path


DEFERRED_SCRIPT = re.compile(
    r"<script"
    r"(?=[^>]*\bdefer(?:=(?:\"defer\"|'defer'|defer))?)"
    r"(?=[^>]*\bsrc=(?P<quote>[\"'])(?P<src>[^\"']+\.js)(?P=quote))"
    r"[^>]*></script>"
)


def rewrite_index(html: str) -> str:
    matches = list(DEFERRED_SCRIPT.finditer(html))
    if len(matches) != 1:
        raise ValueError(
            f"expected exactly one deferred main script, found {len(matches)}; "
            "upstream Lichtblick page changed"
        )

    main_script = matches[0].group("src")
    bootstrap = f'''<script type="module">
import {{ installDefaultExtension }} from "./robium/preinstall-extension.mjs";
try {{
  await installDefaultExtension({{
    indexedDB: globalThis.indexedDB,
    fetch: globalThis.fetch.bind(globalThis),
    baseUrl: "./robium/",
  }});
}} catch (error) {{
  console.error("Could not preinstall the Robium Robot Control extension", error);
}}
const script = document.createElement("script");
script.defer = true;
script.src = {json.dumps(main_script)};
document.head.append(script);
</script>'''
    return DEFERRED_SCRIPT.sub(bootstrap, html, count=1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("index", type=Path)
    args = parser.parse_args()
    original = args.index.read_text(encoding="utf-8")
    args.index.write_text(rewrite_index(original), encoding="utf-8")
    print(f"bundled extension bootstrap injected into {args.index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
