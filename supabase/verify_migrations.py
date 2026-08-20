"""Verify the checked-in migrations against the hosted database's own record.

The migration files in `supabase/migrations/` were recovered from
`supabase_migrations.schema_migrations` on the hosted project rather than
written by hand, so the only claim worth making about them is a byte-level one:
each file is exactly the SQL Postgres recorded as applied.

`CHECKSUMS.md5` holds those md5s. This script recomputes them from the files on
disk. A mismatch means the file drifted from what the database actually ran --
which is the whole failure mode checking them in was meant to close.

Run:  python supabase/verify_migrations.py
Exit: 0 if every file matches, 1 otherwise.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKSUMS = HERE / "migrations" / "CHECKSUMS.md5"


def expected() -> dict[str, str]:
    pairs = {}
    for line in CHECKSUMS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, name = line.split(None, 1)
        pairs[name.strip()] = digest
    return pairs


def main() -> int:
    want = expected()
    if not want:
        print(f"no checksums found in {CHECKSUMS}")
        return 1

    failures = 0
    for name, digest in sorted(want.items()):
        path = HERE / "migrations" / name
        if not path.exists():
            print(f"MISSING  {name}")
            failures += 1
            continue
        # Read bytes, never text: a CRLF rewrite is exactly the kind of silent
        # drift this is here to catch.
        raw = path.read_bytes()
        got = hashlib.md5(raw).hexdigest()
        if got == digest:
            print(f"ok       {name}  ({len(raw)} bytes)")
        else:
            note = "  (contains CRLF)" if b"\r\n" in raw else ""
            print(f"MISMATCH {name}  expected {digest} got {got}{note}")
            failures += 1

    print()
    if failures:
        print(f"{failures} of {len(want)} migrations do not match the applied SQL.")
        return 1
    print(f"all {len(want)} migrations match the SQL recorded as applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
