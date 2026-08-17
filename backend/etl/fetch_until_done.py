"""Run a resumable fetcher repeatedly until its dataset is complete.

WHY A SUPERVISOR
----------------
Both fetchers make ONE pass. A unit that fails -- a rate limit outlasting the
retries, a transient DNS failure, a session FastF1 cannot resolve, all of
which happened -- is recorded and skipped so one bad unit cannot discard hours
of completed work. That is right for a pass, but it means a single invocation
can finish with data still missing, and waiting for the process to exit is not
the same as waiting for the data.

This loops, and stops on one of three conditions, reporting which:

  * complete   -- nothing remaining
  * stalled    -- two passes in a row added nothing, so retrying is not helping
  * exhausted  -- the pass budget ran out

Stalling is a real outcome, not a failure to try hard enough. Some units are
permanently unavailable: a practice session that was never held cannot be
fetched however many times it is asked for, and spinning on it forever behind
a busy-looking process hides that.

Run:  python -m backend.etl.fetch_until_done laps
      python -m backend.etl.fetch_until_done practice
      python -m backend.etl.fetch_until_done laps practice
"""

from __future__ import annotations

import sys
import time

MAX_PASSES = 40
PAUSE_BETWEEN_PASSES = 10 * 60

FETCHERS = ("laps", "practice")


def _load(name: str):
    if name == "laps":
        from backend.etl import laps

        return laps
    if name == "practice":
        from backend.etl import practice

        return practice
    raise SystemExit(f"unknown fetcher {name!r}. Valid: {', '.join(FETCHERS)}")


def supervise(name: str) -> int:
    """Loop one fetcher to completion. Returns 0 when complete."""
    module = _load(name)
    previous_remaining = None

    for attempt in range(1, MAX_PASSES + 1):
        before = module.status()
        if not before["remaining"]:
            print(f"[{name}] complete: {before['cached']} units", flush=True)
            return 0

        print(
            f"\n[{name}] === pass {attempt}: {before['remaining']} remaining "
            f"({before['failures']} previously failed) ===",
            flush=True,
        )
        module.run()

        after = module.status()
        gained = before["remaining"] - after["remaining"]
        print(f"[{name}] pass {attempt} fetched {gained}; {after['remaining']} left", flush=True)

        if not after["remaining"]:
            print(f"[{name}] complete: {after['cached']} units", flush=True)
            return 0

        # No progress twice running means the obstacle is not transient.
        # Retrying the same requests forever would burn quota and hide the
        # real reason behind an endlessly busy process.
        if gained == 0 and previous_remaining == after["remaining"]:
            print(
                f"[{name}] stalled at {after['remaining']} remaining: two passes added "
                f"nothing. Failures: {after['failures']}",
                flush=True,
            )
            return 1
        previous_remaining = after["remaining"]

        time.sleep(PAUSE_BETWEEN_PASSES)

    print(f"[{name}] exhausted {MAX_PASSES} passes", flush=True)
    return 1


def main(argv: list[str]) -> int:
    names = [a for a in argv if a in FETCHERS] or list(FETCHERS)
    # Sequential rather than concurrent, deliberately. They hit different
    # services, so parallelism would be safe for rate limits -- but a stalled
    # first fetcher should be visible before the second starts, not buried
    # under interleaved output from both.
    worst = 0
    for name in names:
        worst = max(worst, supervise(name))
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
