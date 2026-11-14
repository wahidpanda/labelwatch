# One-shot implementation status (2026-11-14)

## Done in this pass

- **WP-1:** Migration `0005`, ORM models, repositories (BD, subscribers), ADR 0100.
- **WP-3 (partial):** Fixture CSV, import script, `GET /api/v1/bd/brands`, `/bd` page.
- **WP-4 (partial):** Subscribe + confirm + unsubscribe tokens, dry-run `.eml` outbox, env vars.
- **WP-5 (partial):** `rag_docs` table + simple retriever (keyword).
- **WP-6 (partial):** SSE `/api/v1/chat/stream` + dashboard ChatPanel (overview stub).
- **WP-7 (stub):** `JevClient` behind `JEV_ENABLED=false`, ADR 0101.
- **WP-2 (stub):** `GET /api/v1/eval/runs` reads existing `eval_runs` table.

## Not done yet (continue in a follow-up session)

- Full evaluation harness (B0–B5), gold admin UI, LangSmith export.
- Email templates (EN/BN), worker `notify`, weekly digest workflow.
- LangGraph tool loop, RAG indexer worker, Jev cascade in judge pipeline.
- Voice (WP-9), Playwright smoke, full i18n.

## You still do by hand

1. Paste TypeSafe docs into `docs/JEV_API.md` and set `TYPESAFE_API_KEY`.
2. Add real `data/bd/medicines.csv` + license in `data/bd/LICENSE_NOTE.md`.
3. Set `EMAIL_TOKEN_SECRET` and SMTP (or keep `EMAIL_DRY_RUN=true`).
4. Run `py scripts/import_bd_brands.py --fixture` then migrate: `python -m app.db.migrate`.
5. Label ~150 gold pairs when the admin UI is extended.
