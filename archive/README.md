# archive/

The project's first phase: standalone analysis scripts, before the database,
API and frontend existed. Kept because they are the origin of the work and
still run, not because anything depends on them.

**Nothing in `backend/` or `frontend/` imports any of this.** Removing the
directory would not affect the application, its tests, or its build.

| File | What it was |
|---|---|
| `f1_utils.py` | Shared CSV loader and decade bucketing |
| `wins_by_year.py` | Leading constructor per season, printed |
| `wins_by_decade.py` | Same, rolled up to decades |
| `wins_by_driver.py` | Driver version, with chart output |
| `plot_wins.py` | Chart generation for `output/` |
| `check_positions.py` | One-off scratch script used to inspect the raw `position` column |
| `output/` | Charts these scripts produced |

Paths are anchored to this file, so they read `../results.csv` and write to
`archive/output/` regardless of working directory:

```bash
pip install matplotlib   # not in requirements.txt -- the application does not use it
python archive/wins_by_year.py
```

## Terminology warning

These scripts compute **win share** — wins / races held that season. The
application's `win_rate` is **wins / driver entries**. Different denominators,
different questions. Numbers here will not match the application, and are not
meant to. See [METHODOLOGY.md](../METHODOLOGY.md).
