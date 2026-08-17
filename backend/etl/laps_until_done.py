"""Run the lap fetch until the calendar is complete.

Kept as a named entry point because it is referenced in the checklist and in
commit history. The supervision logic lives in `fetch_until_done`, which does
the same job for the practice fetch -- one implementation rather than two that
drift apart.

Run:  python -m backend.etl.laps_until_done
"""

from __future__ import annotations

import sys

from backend.etl.fetch_until_done import supervise

if __name__ == "__main__":
    sys.exit(supervise("laps"))
