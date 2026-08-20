"""Check the local environment is ready, with readable errors.

The failures this catches all otherwise surface late and cryptically: a missing
variable becomes a skipped test that looks like a pass, an unencoded `@` in a
password becomes a DNS error naming the wrong host, and a missing driver
becomes an ImportError three modules deep.

**Never prints a secret.** Passwords and keys are reported as present/absent
and by length only.

Run:  python -m backend.etl.verify_env
Exit: 0 when the environment can do everything, 1 otherwise.
"""

from __future__ import annotations

import os
import sys
import urllib.parse

from backend.app import env

OK, MISSING, BAD = "ok", "missing", "bad"


def _mask(value: str) -> str:
    return f"set ({len(value)} chars)" if value else "not set"


def check() -> tuple[list[tuple[str, str, str]], bool, bool]:
    """Returns (rows, can_read, can_write)."""
    rows: list[tuple[str, str, str]] = []

    # `backend.app.env` already loaded on import; calling again is a no-op, so
    # count what the file declares rather than what this call applied.
    env.load()
    if env.ENV_PATH.exists():
        declared = sum(
            1 for line in env.ENV_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#") and "=" in line
        )
        rows.append((".env", OK, f"{env.ENV_PATH} ({declared} variables)"))
    else:
        rows.append((".env", MISSING, f"no file at {env.ENV_PATH}"))

    url = os.getenv("SUPABASE_URL", "").strip()
    if not url:
        rows.append(("SUPABASE_URL", MISSING, "needed to read from Supabase"))
    elif not url.startswith("https://"):
        rows.append(("SUPABASE_URL", BAD, f"must start with https:// -- got {url[:24]!r}"))
    else:
        rows.append(("SUPABASE_URL", OK, url))

    key = os.getenv("SUPABASE_ANON_KEY", "").strip()
    if not key:
        rows.append(("SUPABASE_ANON_KEY", MISSING, "needed to read from Supabase"))
    elif not (key.startswith("sb_publishable_") or key.startswith("eyJ")):
        rows.append(("SUPABASE_ANON_KEY", BAD,
                     "expected sb_publishable_... or a JWT starting eyJ"))
    else:
        rows.append(("SUPABASE_ANON_KEY", OK, _mask(key)))

    db = os.getenv("SUPABASE_DB_URL", "").strip()
    if not db:
        rows.append(("SUPABASE_DB_URL", MISSING, "needed to WRITE (ingestion)"))
    elif "YOUR_PASSWORD_HERE" in db:
        rows.append(("SUPABASE_DB_URL", BAD,
                     "still contains the placeholder -- put your real database password in .env"))
    else:
        parsed = urllib.parse.urlparse(db)
        if parsed.scheme not in ("postgresql", "postgres"):
            rows.append(("SUPABASE_DB_URL", BAD, f"scheme must be postgresql://, got {parsed.scheme!r}"))
        elif not parsed.hostname:
            rows.append(("SUPABASE_DB_URL", BAD,
                         "no host could be parsed -- if the password contains @ : / ? # [ ] or %, "
                         "it must be percent-encoded, or reset it to something alphanumeric"))
        elif not parsed.password:
            rows.append(("SUPABASE_DB_URL", BAD, "no password in the URL"))
        else:
            rows.append(("SUPABASE_DB_URL", OK,
                         f"host {parsed.hostname}, password {_mask(parsed.password)}"))

    try:
        import psycopg2
        rows.append(("psycopg2", OK, "installed"))
    except ImportError:
        psycopg2 = None
        rows.append(("psycopg2", MISSING, "pip install psycopg2-binary"))

    # Actually open the connection. A well-formed URL proves nothing: the
    # direct host `db.<ref>.supabase.co` is IPv6-only and does not resolve on
    # most networks, which otherwise surfaces as a DNS error midway through an
    # import rather than here.
    if psycopg2 and db and "YOUR_PASSWORD_HERE" not in db:
        try:
            connection = psycopg2.connect(db, connect_timeout=15)
            with connection.cursor() as cur:
                cur.execute("select current_user, has_table_privilege('results','INSERT')")
                user, can_insert = cur.fetchone()
            connection.close()
            rows.append(("db connection", OK if can_insert else BAD,
                         f"connected as {user}, INSERT on results: {can_insert}"))
        except Exception as error:  # noqa: BLE001 -- report any failure readably
            hint = ""
            if "translate host name" in str(error) or "not known" in str(error):
                hint = (" -- use the POOLER host "
                        "aws-0-<region>.pooler.supabase.com:5432 with username "
                        "postgres.<project-ref>; the direct db.<ref> host is IPv6-only")
            rows.append(("db connection", BAD,
                         f"{type(error).__name__}: {str(error).strip()[:110]}{hint}"))

    statuses = dict((name, status) for name, status, _ in rows)
    can_read = statuses.get("SUPABASE_URL") == OK and statuses.get("SUPABASE_ANON_KEY") == OK
    can_write = (
        can_read
        and statuses.get("SUPABASE_DB_URL") == OK
        and statuses.get("psycopg2") == OK
        # A URL that parses is not a URL that connects.
        and statuses.get("db connection") == OK
    )
    return rows, can_read, can_write


def main() -> int:
    rows, can_read, can_write = check()
    width = max(len(name) for name, _, _ in rows)

    for name, status, detail in rows:
        flag = {OK: "ok  ", MISSING: "MISS", BAD: "BAD "}[status]
        print(f"{flag}  {name:<{width}}  {detail}")

    print()
    print(f"read from Supabase (parity tests): {'YES' if can_read else 'NO'}")
    print(f"write to Supabase (ingestion):     {'YES' if can_write else 'NO'}")

    if not can_write:
        print()
        print("Next step: edit .env and replace YOUR_PASSWORD_HERE with your database")
        print("password from the Supabase dashboard, then run this again.")

    return 0 if can_write else 1


if __name__ == "__main__":
    sys.exit(main())
