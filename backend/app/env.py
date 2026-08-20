"""Load `.env` into the process environment.

Standard library only, matching the rest of the ETL layer -- this project
carries no dependency it does not need, and a `.env` parser is ~20 lines.

Rules, chosen to be unsurprising:
  * A real environment variable always wins. `.env` is a convenience for local
    development, never an override of what the deployment actually set.
  * Missing file is fine. A fresh clone has no `.env` and must still run.
  * `export FOO=bar` and quoted values are accepted, because people paste them.
  * Values are never logged. This file holds a database password.
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def load(path: Path = ENV_PATH) -> list[str]:
    """Load `path` into os.environ. Returns the names it set (never values)."""
    if not path.exists():
        return []

    applied = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()

        name, _, value = line.partition("=")
        name = name.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]

        # A real environment variable wins.
        if name and name not in os.environ:
            os.environ[name] = value
            applied.append(name)
    return applied


# Loaded on import so any module reading os.getenv sees the file's values,
# regardless of import order.
load()
