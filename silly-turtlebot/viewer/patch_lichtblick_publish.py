#!/usr/bin/env python3
"""Keep Lichtblick's 3D click-to-publish topics registered.

Lichtblick v1.28.0 makes the publisher effect depend on the entire panel context.
That context changes identity during startup, so the effect cleanup can remove
the active pose channels while a later context cannot restore them correctly.
Keep the advertisements for the WebSocket session, matching the proven
robot-navigation viewer workaround. The regex intentionally fails closed when
the pinned upstream bundle changes.
"""

import re
from pathlib import Path


PUBLISH_CLEANUP = re.compile(
    r"\(\)=>\{(\w+)\.unadvertise\?\.\((\w+)\.goal\),"
    r"\1\.unadvertise\?\.\(\2\.point\),"
    r"\1\.unadvertise\?\.\(\2\.pose\)\}"
)


def main() -> None:
    matches: list[tuple[Path, list[tuple[str, str]]]] = []
    for path in Path("/opt/lichtblick").glob("*.js"):
        source = path.read_text(encoding="utf-8")
        found = PUBLISH_CLEANUP.findall(source)
        if found:
            matches.append((path, found))

    if len(matches) != 1:
        raise RuntimeError(
            "expected exactly one Lichtblick bundle with the publish-cleanup "
            f"pattern, found {len(matches)}"
        )
    path, found = matches[0]
    if len(found) != 1:
        raise RuntimeError(
            f"expected one publish cleanup in {path.name}, found {len(found)}"
        )
    source = path.read_text(encoding="utf-8")
    path.write_text(PUBLISH_CLEANUP.sub("()=>{}", source), encoding="utf-8")


if __name__ == "__main__":
    main()
