# Security policy

## Scope

This is a single-developer portfolio project. There is no deployed production
service with users, and no authentication system: the application serves
read-only historical Formula 1 data.

Only the current state of the default branch is supported. There are no
released versions, no backports, and no security patches for older commits.

## Reporting a vulnerability

Please report privately, not in a public issue.

Use GitHub's **Report a vulnerability** button under the repository's Security
tab (Private Vulnerability Reporting). That creates a private advisory visible
only to the maintainer.

If that is unavailable, open a public issue containing **only** the words
"security report — requesting private channel" and no technical detail, and a
private channel will be arranged.

Please do not disclose details publicly until the issue has been investigated
and addressed.

Because this is a personal project maintained in spare time, please allow up to
30 days for an initial response. There is no bug-bounty programme and no
payment is offered.

## What is in scope

- Secret or credential exposure in the repository or its history
- SQL injection, XSS, or unsafe data handling in the API or frontend
- Row Level Security or permission errors in the Supabase schema
- CI/CD configuration that could allow untrusted code execution

## What is out of scope

- The absence of authentication. There is none by design; all served data is
  public historical race data.
- The public Supabase anon key and project URL. These are publishable by
  design and are constrained by Row Level Security, which grants `SELECT`
  only. Anonymous `INSERT`, `UPDATE`, and `DELETE` are refused at the
  PostgreSQL `GRANT` level on every table.
- Rate limiting and denial of service against the demo backend.
- Third-party images in `frontend/public/`. Their provenance is a licensing
  question, documented in the README, not a security vulnerability.
- Findings from automated scanners submitted without a demonstrated impact.

## Handling of credentials

No credential has ever been committed to this repository. `.env` is gitignored;
`.env.example` contains placeholders only. This has been verified by scanning
every commit in the repository's history for the live anon key and database
password: neither appears in any commit.

The Supabase **project reference** does appear in the history of two files
(`docs/database.md`, `supabase/migrations/CHECKSUMS.md5`) in commits predating
its removal. A project reference is an identifier, not a credential — it forms
part of the project's public URL — but it does disclose which hosted project
backs this repository.

If a credential is ever exposed, the correct response is rotation in the
Supabase dashboard, not merely deleting the file: git history retains the value
and anyone may already have cloned it.
