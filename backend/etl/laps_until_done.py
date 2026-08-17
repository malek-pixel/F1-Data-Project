"""Run the lap fetch repeatedly until the calendar is actually complete.

WHY A SUPERVISOR
----------------
`laps.run()` makes ONE pass. A race that fails -- a rate limit that outlasts
the retries, or a transient DNS failure, both of which happened -- is recorded
in the failure manifest and skipped so one bad race cannot discard hours of
completed work. That is the right behaviour for a pass, but it means a single
invocation can finish with races still missing, and waiting for it to exit is
not the same as waiting for the data.

So this loops: fetch, check what is left, fetch again. It stops on one of
three conditions, and reports which:

  * complete   -- every race has lap timings
  * stalled    -- a pass added nothing, so retrying is not helping
  * exhausted  -- the pass budget ran out

Between passes it waits, because the usual reason a pass ends incomplete is
an exhausted hourly quota, and quota refills on a clock.

Run:  python -m backend.etl.laps_until_done
"""

from __future__ import annotations

import sys
import time

from backend.etl import laps

MAX_PASSES = 40
PAUSE_BETWEEN_PASSES = 10 * 60


def main() -> int:
    previous_remaining = None

    for attempt in range(1, MAX_PASSES + 1):
        before = laps.status()
        if not before["remaining"]:
            print(f"complete: {before['cached']}/{before['races']} races", flush=True)
            return 0

        print(
            f"\n=== pass {attempt}: {before['remaining']} races remaining "
            f"({before['failures']} previously failed) ===",
            flush=True,
        )
        laps.run()

        after = laps.status()
        gained = before["remaining"] - after["remaining"]
        print(
            f"pass {attempt} fetched {gained}; {after['remaining']} left",
            flush=True,
        )

        if not after["remaining"]:
            print(f"complete: {after['cached']}/{after['races']} races", flush=True)
            return 0

        # No progress twice running means the obstacle is not transient --
        # retrying the same requests forever would just burn quota and hide
        # the real problem behind an endlessly busy process.
        if gained == 0 and previous_remaining == after["remaining"]:
            print(
                f"stalled at {after['remaining']} races: two passes in a row added "
                f"nothing. Failures: {after['failures']}",
                flush=True,
            )
            return 1
        previous_remaining = after["remaining"]

        time.sleep(PAUSE_BETWEEN_PASSES)

    print(f"exhausted {MAX_PASSES} passes; {laps.status()['remaining']} races left", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
