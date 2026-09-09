#!/usr/bin/env python3
"""Keep Lichtblick's 3D click-to-publish topics registered.

Lichtblick v1.28.0 makes the publisher effect depend on the entire panel context.
That context changes identity during startup, so the effect cleanup unadvertises
the pose topics without reliably advertising them again. Depend on the stable
publish methods instead. The exact replacement intentionally fails closed when
the pinned upstream bundle changes.
"""

from pathlib import Path


OLD = "},[lt,e,e.dataSourceProfile]);const On="
NEW = "},[lt,e.advertise,e.unadvertise,e.dataSourceProfile]);const On="


def main() -> None:
    matches: list[Path] = []
    for path in Path("/opt/lichtblick").glob("*.js"):
        source = path.read_text(encoding="utf-8")
        count = source.count(OLD)
        if count == 0:
            continue
        if count != 1:
            raise RuntimeError(f"expected one publish effect in {path}, found {count}")
        path.write_text(source.replace(OLD, NEW), encoding="utf-8")
        matches.append(path)

    if len(matches) != 1:
        raise RuntimeError(
            f"expected one Lichtblick 3D publish bundle, patched {len(matches)}"
        )


if __name__ == "__main__":
    main()
