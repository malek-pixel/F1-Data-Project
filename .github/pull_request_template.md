> **This repository does not accept outside contributions.**
>
> The code is proprietary — see [LICENSE](../LICENSE). Pull requests from
> people other than the repository owner will be closed without review, and
> opening one does not grant any licence to the code it contains.
>
> Found a bug or a wrong figure? Please open an **issue** instead. Data
> corrections are genuinely welcome as issues, with a source.
>
> Security problem? Do not open a PR or a public issue — see
> [SECURITY.md](../SECURITY.md).

---

## What changed

## Why

## Verification

- [ ] `python -m pytest backend/tests -q`
- [ ] `python -m backend.etl.audit`
- [ ] `python supabase/verify_migrations.py`
- [ ] `cd frontend && npm run typecheck && npm test && npm run build`
- [ ] No secret, credential, or `.env` value added
