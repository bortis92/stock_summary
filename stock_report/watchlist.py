from __future__ import annotations

from pathlib import Path


def load_watchlist(path: Path) -> list[str]:
    if not path.exists():
        return []
    codes: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.split("#", 1)[0].strip()
        if value:
            codes.append(value)
    return list(dict.fromkeys(codes))
