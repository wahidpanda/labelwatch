# ADR 0100: One-shot baseline before eval, BD, alerts, RAG, chat

**Date:** 2026-11-14

## Already in the repo

- Ingest, detect, judge, catalog API, React dashboard (warfarin, montelukast seeded).
- Supabase migrations `0001`–`0004` (includes `leaflet_checks`, `drugs.requested_at`).
- OpenFDA medicine request, Bangladesh leaflet OCR/compare page.
- LLM factory (Gemini, OpenRouter, Groq, Ollama), `llm_cache`, nightly worker.
- Deploy: Render API, Cloudflare Workers frontend.

## Missing (this one-shot adds)

- Migration `0005`: subscribers, email outbox, BD brands, RAG docs, eval extras, Jev methods on judgements.
- Full evaluation harness, gold admin UI, Jev integration (optional).
- SMTP alerts, RAG indexer, LangGraph assistant, dashboard chat.
- `data/bd/medicines.csv` and `docs/JEV_API.md` (user-supplied); fixtures until then.

## Deviations from the prompt file

- New SQL is `0005_alerts_bd_rag_eval.sql`, not `0002_*`, because `0002` is `lock_down_views`.
- `leaflet_checks` from `0004` remains; BD brand search is separate from leaflet upload.
