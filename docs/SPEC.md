# Label Lag Radar: Cursor Build Spec and Prompts

Version 1.0, 13 Nov 2026. Stack: FastAPI, React, Supabase Postgres, LangChain and LangGraph, LangSmith, in-browser voice. Every component is free or open source.

## 1. How to use this document with Cursor

1. Create a repo named label-lag-radar and save this document as docs/SPEC.md.
2. Create the rule files from section 17 inside .cursor/rules/.
3. Open Cursor in Agent mode, paste the Master Prompt (section 2), then run the phase prompts from section 18 one at a time.
4. Commit after each phase. Do not start the next phase until its acceptance checks pass.
5. Anything marked (verify) is a detail I could not confirm from documentation, such as an exact field name. Cursor must check it against a real API response and record the result in docs/adr/.

## 2. Master prompt (paste first)

```text
You are a senior full-stack and ML engineer. Build the project described in docs/SPEC.md, phase by phase.

Hard rules:
1. Free and open source only. Never add a dependency, service or API that needs a paid plan or a credit card.
2. Read docs/SPEC.md fully before writing code. If the spec and reality disagree (for example a field name in a real API response), trust reality, fix the code, and write a short note in docs/adr/.
3. Never invent library APIs. If unsure, read the installed package source or the official docs first.
4. Work in small steps: plan, implement, test, commit. Each phase ends with its acceptance checks passing.
5. Backend: Python 3.12, FastAPI, async SQLAlchemy 2, Pydantic v2, uv for dependencies, ruff and mypy clean.
6. Frontend: React, TypeScript strict, Vite, Tailwind, TanStack Query. No any types.
7. Every LLM call goes through backend/app/llm/ with structured output, caching, budget checks and the LangSmith rules from section 11.
8. Every claim shown in the UI must link to evidence (quoted text, set id, version, section). Model quotes must be verified verbatim against stored text before they are saved.
9. Never present output as medical advice or as proof of a regulatory violation. Follow the wording rules in section 3.
10. Write tests with every feature. LLM tests use fake chat models, never live calls.
11. Secrets only via environment variables. Provide .env.example. Never commit secrets.
12. Keep memory low (assume 512 MB on the free host). Stream-parse XML and avoid loading whole datasets.
Start by confirming your plan for Phase 0, then execute.
```

## 3. Product scope

**Research question.** When a brand-name drug label gets a new safety change, how many days pass before each generic label shows the same change, and which generics still do not show it?

**Users.** Pharmacists, regulatory and pharmacovigilance analysts, health informatics researchers. For you, it is a portfolio and office-pitch project.

**Outputs.**

- Lag distribution per drug, drug class and labeler.
- List of generic labels whose published text does not yet reflect a brand safety change.
- Evidence viewer: brand text and generic text side by side, with the exact quoted sentences.
- CSV export of the full dataset.
- Voice-enabled assistant that answers questions about the data.

**Non-goals.** Not clinical decision support. No dosing or treatment advice. No patient data. Not a compliance finding. Not all of DailyMed: start with 25 seed drugs. No biologics or biosimilars. No non-US labels.

**Wording rules (enforced in UI copy and assistant prompts).**

- Say: discrepancy signal, not yet reflected in the published label text, lag between published versions.
- Never say: violation, non-compliant, unsafe generic, illegal.
- Always show: dates are DailyMed publication dates, not FDA approval dates; DailyMed holds company-submitted labeling; a change may be pending at FDA or implemented under a different wording.

**Definitions.**

- Brand label: SPL set whose application is an NDA or BLA and is the reference listed drug.
- Generic label: SPL set under an ANDA whose reference drug is that brand.
- Safety event: a new or strengthened safety statement found by comparing two consecutive versions of the brand label in the safety sections.
- Propagation status: propagated, partial, not\_propagated, insufficient\_evidence.
- Lag days: published date of the first generic version containing the change minus the brand version date of the event. Zero or negative means concurrent or earlier.
- Stale generic: not\_propagated, still the current version, and more than 90 days after the event (configurable).

## 4. Free-tier constraints that shape the design (checked Nov 2026)

| Service | Free limit | Design consequence |
| --- | --- | --- |
| Supabase Free | 500 MB database, 1 GB file storage, 5 GB egress, 50,000 auth users, project pauses after 7 idle days | Content-addressed section store, 25 seed drugs, database size guard at 400 MB, weekly keep-alive job, browser never talks to Supabase directly |
| LangSmith Developer | 1 seat, 5,000 traces a month, hard cap until a card is added, 14-day retention | Trace sampling, one root trace per batch, trace budget counter, local evaluation runner |
| LLM APIs (Gemini, Groq, OpenRouter) | Per-model rate and daily limits that change without notice; limits are shown in each provider console | Provider-agnostic factory, model names in env, database job queue with daily budgets, cache by content hash, Ollama local fallback |
| Render free web service | Sleeps when idle, slow wake-up, small RAM, 5 GB bandwidth | Stateless API, heavy work in GitHub Actions, lazy loading |
| Cloudflare Pages | Free static hosting, no card | Hosts the React app |
| GitHub Actions | Free minutes (generous for public repos) (verify private limits) | Nightly ingestion and judging jobs |
| Hugging Face Docker Spaces, Fly.io | No longer free | Do not use |
| Voice | Runs on the visitor's device | No server cost, audio never leaves the browser |

## 5. Architecture

```text
 Browser: React SPA (Cloudflare Pages)
   voice: Whisper speech-to-text + Kokoro text-to-speech, on-device (WebGPU, WASM fallback)
        | HTTPS + Server-Sent Events
        v
 FastAPI (Docker, Render free)
   routers -> services -> repositories
   LangGraph assistant (read-only tools)    LangChain judge chains
        |                    |                      |
        |                    |                      +--> LLM providers: Gemini free, Groq free, OpenRouter free, Ollama
        |                    +--> LangSmith (sampled traces)
        v
 Supabase Postgres (free)  <--- Worker jobs (GitHub Actions cron and manual dispatch)
                                 fetch DailyMed + Orange Book, parse, diff, judge, refresh views
```

**Responsibilities.**

- Frontend: read-only dashboards, evidence viewer, assistant, admin screens. Talks only to FastAPI.
- API: validation, read endpoints, assistant streaming, admin endpoints protected by Supabase Auth JWT.
- Worker: same Python package as the API, run as CLI (python -m app.worker run). Pulls jobs from the jobs table, respects daily LLM budgets, is resumable.
- Database: system of record. Raw SPL files are not stored (too large); only parsed safety sections, deduplicated by hash.

**Flows.**

1. Ingestion: seed drug -> resolve application numbers -> list SPL sets -> fetch version history -> download each needed version -> parse sections -> store.
2. Detection: diff brand versions -> classify changed units -> create safety events.
3. Judging: for each event and generic set, find the first generic version containing the change -> store judgement with evidence.
4. Browse: frontend reads precomputed views.
5. Voice query: browser transcribes speech -> sends text to /assistant/query -> LangGraph agent calls read-only tools -> streamed answer with citations -> browser speaks a short summary.

## 6. Repository structure

```text
label-lag-radar/
  docs/ (SPEC.md, adr/, runbook.md, methodology.md)
  .cursor/rules/
  .github/workflows/ (ci.yml, ingest.yml, keepalive.yml, deploy-frontend.yml)
  supabase/migrations/ (0001_init.sql ...)
  backend/
    pyproject.toml, uv.lock, Dockerfile, .env.example
    app/
      main.py, config.py, logging.py, deps.py, errors.py
      api/v1/ (drugs.py, events.py, judgements.py, stats.py, sets.py, assistant.py, eval.py, admin.py, health.py)
      core/ (security.py, rate_limit.py, budget.py)
      db/ (session.py, models.py, repositories/)
      ingest/ (dailymed.py, orange_book.py, srlc.py, spl_parser.py, normalize.py, linker.py)
      detect/ (units.py, differ.py, classify.py)
      judge/ (retrieve.py, judge.py, verify.py, search.py, lag.py)
      llm/ (factory.py, schemas.py, prompts.py, cache.py, tracing.py)
      assistant/ (graph.py, tools.py, guardrails.py)
      worker/ (__main__.py, queue.py)
      evaluation/ (gold.py, baselines.py, metrics.py, runner.py)
    tests/ (unit/, integration/, fixtures/spl/)
  frontend/
    package.json, vite.config.ts, tailwind.config.ts
    src/ (app/, pages/, components/, features/voice/, features/assistant/, lib/api/, lib/format/, styles/)
    tests/ (vitest) and e2e/ (playwright)
  docker-compose.yml, Makefile, README.md, LICENSE (MIT)
```

## 7. Data sources and ingestion

| Source | What we take | Access |
| --- | --- | --- |
| DailyMed REST API v2 (https://dailymed.nlm.nih.gov/dailymed/services/v2) | spls (paginated, 100 per page max), spls/{SETID}, spls/{SETID}/history, applicationnumbers, drugnames, rxcuis | Free, GET only, JSON or XML by file extension |
| DailyMed older versions | getFile.cfm?type=zip&setid={SETID}&version={N} returns a ZIP holding that SPL version | Free |
| FDA Orange Book data files | products.txt, tilde-delimited: ingredient and dosage form, trade name, applicant, strength, application type and number, RLD flag (verify header names) | Free monthly ZIP from the FDA Orange Book page |
| FDA Safety-related Labeling Changes (SrLC) | Dated safety label changes since January 2016, NDA and BLA only, no ANDAs. Used only to validate brand-side events | Web search with download, no documented API found (verify), so a manual CSV import script |
| RxNav / RxNorm API | Optional ingredient normalisation (verify terms) | Free |

**Politeness and reliability rules.**

- At most 2 requests per second, a User-Agent with a contact email, retries with exponential backoff and jitter, honour HTTP 429 and Retry-After.
- Outbound requests go only to an allow-list of hosts (dailymed.nlm.nih.gov, api.fda.gov, www.fda.gov, www.accessdata.fda.gov, rxnav.nlm.nih.gov). Reject anything else (SSRF guard).
- Cache by URL plus ETag or Last-Modified when present. Never store raw SPL ZIPs; store sha256 and the source URL.
- Every run writes an ingestion\_runs row with counts, errors and duration.

**Steps.**

1. Seed: read config/seed\_drugs.yaml (25 ingredients, below). Normalise names (lowercase, strip salts).
2. Orange Book: load products.txt. For each seed ingredient, find all products. A product with RLD = Yes is the reference. Link each ANDA product to the RLD with the same ingredient, dosage form, route and strength. Store link\_method and link\_confidence. Provide a manual override table (application\_links) for ambiguous cases.
3. DailyMed: search drugnames and spls for each ingredient. For each SPL set, parse the application number from the SPL XML approval element (verify path), so every set maps to an NDA, ANDA or BLA. Assign role: brand (NDA or BLA and RLD), generic (ANDA), authorized\_generic (NDA but not RLD), else other. Mark likely repackagers (verify heuristic) so the UI can filter them.
4. Versions: call spls/{SETID}/history. For each version, download the ZIP only if the version is needed (brand: all versions since 2012; generics: all versions, fetched lazily by the binary search in section 8).
5. Parse with lxml (namespace urn:hl7-org:v3). Extract only safety sections by LOINC code (verify against the FDA SPL implementation guide): 34066-1 boxed warning, 43685-7 warnings and precautions, 34071-1 warnings (old format), 42232-9 precautions (old format), 34084-4 adverse reactions, 34070-3 contraindications, 34073-7 drug interactions, 43684-0 use in specific populations, 42228-7 pregnancy.
6. Normalise to units: one unit per paragraph, list item or table row, joined with a newline. Unicode NFKC, collapse whitespace, keep original case for display and a lowercase copy for hashing. Store the section text in section\_texts keyed by sha256 of the normalised text, so unchanged sections across versions share one row.
7. Record version\_sections rows. Update spl\_sets.latest\_version and latest\_published.

**Seed drugs (verify each has an RLD and at least 3 generic labelers):** montelukast, zolpidem, gabapentin, tramadol, ciprofloxacin, levofloxacin, metformin, atorvastatin, levothyroxine, warfarin, clopidogrel, citalopram, escitalopram, sertraline, fluoxetine, methotrexate, amiodarone, ondansetron, losartan, lisinopril, amlodipine, tizanidine, cyclobenzaprine, finasteride, duloxetine.

## 8. Detection and judging pipeline

**Step A. Units.** Convert every stored section into units (section 7, step 6).

**Step B. Brand event detection (no LLM).** For each pair of consecutive brand versions and each safety section: compute added, removed and modified units. Use difflib plus rapidfuzz: ratio at or above 0.90 means modified, below means added or removed. Skip pairs whose section hash is identical.

**Step C. Classify candidates (LLM, structured).** For each added or modified unit, ask the classify chain: is this a substantive safety change or editorial (formatting, renumbering, reference update)? Output change\_type (added, strengthened, modified), severity (boxed, major, moderate, minor), a one-sentence claim summary. Drop editorial units. Create a safety\_events row. Deduplicate by claim\_hash so the same claim is not recorded twice. If an SrLC export is loaded, set srlc\_ref when the date and drug match (validation only).

**Step D. Candidate retrieval in generic labels.** For one event and one generic set, take the same section (and neighbouring safety sections) of a generic version. Rank its units against the claim with BM25 (rank\_bm25) plus trigram similarity. Keep the top 5 units.

**Step E. Deterministic shortcuts (saves LLM calls).** If a candidate unit matches the brand unit after normalisation at ratio 0.97 or higher, mark propagated with method baseline\_exact. If the generic section hash equals a version that predates the event and no candidate scores above 0.35, mark not\_propagated with method baseline\_unchanged. Otherwise go to the judge.

**Step F. Judge (LLM, structured).** Input: claim, brand unit, top 5 generic units. Output: status, quotes (exact sentences copied from the generic units), confidence, short rationale. **Verification:** every quote must appear verbatim (after normalisation, fuzzy ratio at or above 0.95) in the supplied generic text. If not, discard the quotes and set insufficient\_evidence.

**Step G. First-propagation search.** List generic versions by date. Assume the change, once present, stays present. Binary search for the earliest version that is propagated. Then check the version just before it and one earlier one linearly to catch non-monotonic cases. Flag the judgement with a non\_monotonic marker when a later version drops the claim.

**Step H. Lag and stale flag.** lag\_days = first\_version\_date minus event\_date. If no version is propagated, status is not\_propagated and the stale rule in section 3 applies.

**Known limits (publish these on the Methodology page).** Dates are publication dates. Companies may implement a change with different wording. A generic may be waiting on FDA review. Old-format labels use different section structures. Repackager labels copy their source and can inflate counts.

## 9. Database schema (Supabase Postgres)

Put this in supabase/migrations/0001\_init.sql. Row Level Security is on for every table with no policies for anon or authenticated roles; only the backend database role reads and writes. The browser never touches Supabase directly.

```sql
create extension if not exists pg_trgm;

create table drugs (
  id uuid primary key default gen_random_uuid(),
  ingredient text not null,
  ingredient_norm text not null unique,
  rxcui text,
  drug_class text,
  is_seed boolean not null default false,
  created_at timestamptz not null default now()
);

create table applications (
  id uuid primary key default gen_random_uuid(),
  drug_id uuid not null references drugs(id) on delete cascade,
  appl_type text not null check (appl_type in ('NDA','ANDA','BLA')),
  appl_no text not null,
  applicant text,
  trade_name text,
  is_rld boolean not null default false,
  products jsonb not null default '[]',
  reference_application_id uuid references applications(id),
  link_method text check (link_method in ('orange_book_rld','heuristic','manual')),
  link_confidence numeric(3,2),
  unique (appl_type, appl_no)
);
create index on applications (drug_id);
create index on applications (reference_application_id);

create table spl_sets (
  id uuid primary key default gen_random_uuid(),
  setid uuid not null unique,
  drug_id uuid not null references drugs(id) on delete cascade,
  application_id uuid references applications(id),
  title text not null,
  labeler text,
  role text not null check (role in ('brand','generic','authorized_generic','other')),
  is_repackager boolean not null default false,
  is_active boolean not null default true,
  latest_version int,
  latest_published date,
  last_checked_at timestamptz
);
create index on spl_sets (drug_id, role);
create index on spl_sets (application_id);

create table spl_versions (
  id uuid primary key default gen_random_uuid(),
  spl_set_id uuid not null references spl_sets(id) on delete cascade,
  version int not null,
  published_date date not null,
  source_url text not null,
  raw_sha256 text,
  fetched_at timestamptz not null default now(),
  unique (spl_set_id, version)
);
create index on spl_versions (spl_set_id, published_date);

create table section_texts (
  hash text primary key,
  body text not null,
  char_len int not null,
  created_at timestamptz not null default now()
);

create table version_sections (
  version_id uuid not null references spl_versions(id) on delete cascade,
  section_key text not null check (section_key in ('boxed_warning','warnings_precautions','warnings','precautions','adverse_reactions','contraindications','drug_interactions','specific_populations','pregnancy')),
  loinc text,
  text_hash text not null references section_texts(hash),
  primary key (version_id, section_key)
);
create index on version_sections (text_hash);

create table safety_events (
  id uuid primary key default gen_random_uuid(),
  drug_id uuid not null references drugs(id) on delete cascade,
  brand_set_id uuid not null references spl_sets(id) on delete cascade,
  from_version_id uuid references spl_versions(id),
  to_version_id uuid not null references spl_versions(id),
  event_date date not null,
  section_key text not null,
  change_type text not null check (change_type in ('added','strengthened','modified')),
  severity text not null check (severity in ('boxed','major','moderate','minor')),
  claim_text text not null,
  claim_hash text not null,
  brand_unit text not null,
  classifier jsonb,
  srlc_ref text,
  created_at timestamptz not null default now(),
  unique (brand_set_id, claim_hash)
);
create index on safety_events (drug_id, event_date);

create table propagation_judgements (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references safety_events(id) on delete cascade,
  generic_set_id uuid not null references spl_sets(id) on delete cascade,
  status text not null check (status in ('propagated','partial','not_propagated','insufficient_evidence')),
  first_version_id uuid references spl_versions(id),
  first_version_date date,
  lag_days int,
  non_monotonic boolean not null default false,
  evidence jsonb not null default '{}',
  method text not null check (method in ('baseline_exact','baseline_unchanged','baseline_lexical','llm','human')),
  model text,
  prompt_version text,
  confidence numeric(3,2),
  cache_key text not null,
  trace_id text,
  created_at timestamptz not null default now(),
  unique (event_id, generic_set_id, method, cache_key)
);
create index on propagation_judgements (event_id);
create index on propagation_judgements (generic_set_id);
create index on propagation_judgements (status);

create table jobs (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('fetch_set','parse_version','detect_events','judge_pair','refresh_views')),
  payload jsonb not null,
  status text not null default 'queued' check (status in ('queued','running','done','failed','deferred')),
  attempts int not null default 0,
  run_after timestamptz not null default now(),
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index on jobs (status, run_after);

create table gold_labels (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references safety_events(id) on delete cascade,
  generic_set_id uuid not null references spl_sets(id) on delete cascade,
  status text not null check (status in ('propagated','partial','not_propagated','insufficient_evidence')),
  first_version_number int,
  split text not null check (split in ('dev','test')),
  annotator text not null,
  notes text,
  created_at timestamptz not null default now(),
  unique (event_id, generic_set_id, annotator)
);

create table eval_runs (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  method text not null,
  model text,
  prompt_version text,
  split text not null,
  metrics jsonb not null,
  langsmith_experiment text,
  git_sha text,
  created_at timestamptz not null default now()
);

create table eval_items (
  run_id uuid not null references eval_runs(id) on delete cascade,
  gold_id uuid not null references gold_labels(id) on delete cascade,
  predicted_status text not null,
  correct boolean not null,
  latency_ms int,
  primary key (run_id, gold_id)
);

create table ingestion_runs (
  id uuid primary key default gen_random_uuid(),
  kind text not null,
  status text not null,
  params jsonb,
  stats jsonb,
  error text,
  started_at timestamptz not null default now(),
  finished_at timestamptz
);

create table llm_budget (
  day date not null,
  provider text not null,
  model text not null,
  calls int not null default 0,
  tokens_in bigint not null default 0,
  tokens_out bigint not null default 0,
  primary key (day, provider, model)
);

create table trace_budget (
  month date primary key,
  traces int not null default 0
);

create table audit_log (
  id bigint generated always as identity primary key,
  actor text not null,
  action text not null,
  entity text,
  payload jsonb,
  created_at timestamptz not null default now()
);

-- Human labels win over model labels.
create view v_current_judgement as
select distinct on (event_id, generic_set_id) *
from propagation_judgements
where method in ('llm','baseline_exact','baseline_unchanged','baseline_lexical','human')
order by event_id, generic_set_id, (method = 'human') desc, created_at desc;

create materialized view mv_drug_lag as
select e.drug_id,
  count(distinct e.id) as events,
  count(*) filter (where j.status = 'propagated') as propagated,
  count(*) filter (where j.status = 'partial') as partial,
  count(*) filter (where j.status = 'not_propagated') as not_propagated,
  percentile_cont(0.5) within group (order by j.lag_days) filter (where j.status = 'propagated') as median_lag_days,
  percentile_cont(0.9) within group (order by j.lag_days) filter (where j.status = 'propagated') as p90_lag_days
from safety_events e
join v_current_judgement j on j.event_id = e.id
group by e.drug_id;
create unique index on mv_drug_lag (drug_id);

-- Row Level Security: deny by default for anon and authenticated roles.
do $$
declare t text;
begin
  for t in select tablename from pg_tables where schemaname = 'public' loop
    execute format('alter table %I enable row level security', t);
  end loop;
end $$;
```

**Connection notes (verify against the Supabase dashboard).** Use the transaction pooler for the running API and set asyncpg prepared statement cache size to 0. Use the session pooler or a direct connection for migrations. Add a size check job that reads pg\_database\_size and blocks ingestion above 400 MB.

## 10. API specification

Base path /api/v1, JSON only. Errors use RFC 7807 problem+json with type, title, status, detail and request\_id. Pagination uses limit (default 25, max 100) and an opaque cursor. Timestamps are ISO 8601 UTC. IDs are UUIDs. CORS allow-list comes from env. Public endpoints are limited to 60 requests a minute per IP, the assistant to 10 a minute. Admin endpoints need an Authorization Bearer token that is a Supabase Auth JWT whose app\_metadata role equals admin; verify the signature against the project JWKS (verify) and cache the keys.

**Public endpoints**

| Method | Path | Purpose |
| --- | --- | --- |
| GET | /healthz | Liveness, no database call |
| GET | /readyz | Readiness: database reachable, schema version, build sha |
| GET | /drugs | List or search drugs (q, drug\_class, has\_stale) with lag counts from mv\_drug\_lag |
| GET | /drugs/{drug\_id} | Drug detail: brand set, generic count, event count, KPIs |
| GET | /drugs/{drug\_id}/events | Safety events, newest first (filters: severity, section\_key) |
| GET | /drugs/{drug\_id}/matrix | Heatmap data: rows are generic sets, columns are events, cells hold status and lag |
| GET | /events/{event\_id} | Claim, brand evidence unit, brand version and date |
| GET | /events/{event\_id}/judgements | Per-generic status list (filters: status, labeler, include\_repackagers) |
| GET | /judgements/{id} | Evidence: quotes, generic version, section hash, method, confidence |
| GET | /sets/{setid} | Label set metadata |
| GET | /sets/{setid}/versions | Version list with dates |
| GET | /sets/{setid}/versions/{version}/sections/{section\_key} | Stored section text for the viewer |
| GET | /generics/stale | Stale generics (min\_days, drug\_id, labeler); CSV when Accept is text/csv |
| GET | /stats/overview | Drugs, events, judgements, median lag, stale share, last ingestion time |
| GET | /stats/lag-distribution | group\_by drug, drug\_class, labeler or severity; histogram bins and quantiles |
| GET | /export/dataset.csv | Streamed full dataset export |
| GET | /methodology | Limits, disclaimers, prompt and model versions for the UI |
| GET | /eval/runs and /eval/runs/{id} | Read-only evaluation results |
| POST | /assistant/query | Server-Sent Events stream. Body: text (max 500 chars), session\_id (client UUID), spoken (boolean) |

**Admin endpoints (JWT with admin role)**

| Method | Path | Purpose |
| --- | --- | --- |
| POST | /admin/drugs | Add a seed drug by ingredient |
| POST | /admin/ingest/run | Enqueue ingestion (drug\_id optional, mode metadata, versions or full) |
| GET | /admin/ingestion-runs | Recent runs with stats and errors |
| POST | /admin/judge/run | Enqueue judging (drug\_id or event\_id, limit, force) |
| GET | /admin/jobs | Queue counts and failed jobs |
| GET | /admin/budget | LLM calls today per provider, LangSmith traces this month, database size in MB |
| GET | /admin/gold/next | Next item to annotate (stratified), with side-by-side evidence |
| POST | /admin/gold | Create or update a gold label |
| POST | /admin/eval/run | Run evaluation (method, split, model) |
| POST | /admin/views/refresh | Refresh materialized views |

**Response models (Pydantic).**

- DrugSummary: id, ingredient, drug\_class, events, generics, stale\_generics, median\_lag\_days, p90\_lag\_days, last\_event\_date.
- EventSummary: id, drug\_id, event\_date, section\_key, change\_type, severity, claim\_text, counts per status.
- JudgementOut: id, event\_id, generic\_set (setid, title, labeler, is\_repackager), status, lag\_days, first\_version (number, date), confidence, method, non\_monotonic, evidence (quotes, section\_key, version\_number, text\_hash).
- StaleGeneric: generic\_set, event, days\_since\_event, latest\_version\_date.
- Assistant SSE event types: token (text chunk), card (type drug\_summary, event or stale\_list, plus data), citation (id and label), spoken\_summary (max 40 words), done (usage), error (problem object).

FastAPI generates the OpenAPI schema. CI generates the TypeScript client with openapi-typescript and fails if the committed client is out of date.

## 11. LangChain, LangGraph and LangSmith design

Packages (pin exact versions in uv.lock; the stable lines in Nov 2026 are langchain 1.x, langchain-core 1.x, langgraph 1.x): langchain, langchain-core, langgraph, langsmith, plus provider packages langchain-google-genai, langchain-groq, langchain-openai (for OpenRouter through a custom base\_url) and langchain-ollama.

### 11.1 LLM factory (backend/app/llm/factory.py)

- get\_chat\_model(task) where task is classify, judge or assistant. It reads LLM\_PROVIDER\_ORDER (for example google\_genai,groq,openrouter,ollama) and one model-name variable per provider. Build each with init\_chat\_model using the provider:model form, temperature 0 for classify and judge, 0.2 for assistant. Chain providers with with\_fallbacks. Add a per-provider rate limiter (langchain\_core InMemoryRateLimiter) driven by env values and with\_retry for transient errors only.
- Never hardcode model names. Free tiers rotate models and limits.
- Before each call run check\_budget(provider, model) against env daily caps. If the cap is hit, raise BudgetExceeded; the worker sets the job to deferred with run\_after tomorrow. After each call, record calls and tokens in llm\_budget.
- Cache key = sha256 of task, prompt\_version, model family and canonical inputs. Look it up before calling. Bumping prompt\_version invalidates the cache on purpose.

### 11.2 Structured output

Use model.with\_structured\_output(Schema), with the json\_schema method when the provider supports it and function calling otherwise. Schemas in app/llm/schemas.py:

- ClassifyOut: is\_substantive (bool), change\_type (added, strengthened, modified, editorial), severity (boxed, major, moderate, minor), claim (one sentence, max 40 words), reason (max 25 words).
- JudgeOut: status (propagated, partial, not\_propagated, insufficient\_evidence), quotes (list of strings copied exactly from the supplied generic units), confidence (0 to 1), rationale (max 40 words). On a validation error retry once, then fall back to insufficient\_evidence and log it.

### 11.3 Prompts (app/llm/prompts.py, PROMPT\_VERSION = 'v1')

Classify system prompt:

```text
You compare two versions of one section of a US drug label. You are given one added or changed unit of text. Decide whether it is a substantive safety change (a new or stronger warning, adverse reaction, contraindication, interaction or population restriction) or editorial (formatting, renumbering, reference or wording cleanup with no new safety meaning). Be conservative: if the meaning is unchanged, answer editorial. Return only the requested fields.
```

Judge system prompt:

```text
You check whether a generic drug label contains the same safety information as a brand label. You get one CLAIM from the brand label and up to 5 numbered candidate UNITS from the generic label.
Rules:
1. propagated: the generic units state the same safety meaning; wording may differ.
2. partial: some but not all elements of the claim are present (for example the warning but not the affected population).
3. not_propagated: none of the units carry the claim.
4. insufficient_evidence: the units are unrelated or unclear.
Quote only text that appears word for word in the units. Never paraphrase inside quotes. Decide only from the supplied text, not from outside medical knowledge. Do not give medical advice.
```

Assistant system prompt (summary of requirements): answer only from tool results about label lag data; refuse medical advice and dosing questions with a short neutral message; always cite events or judgements by id; never use the words violation, non-compliant or unsafe; add the date caveat whenever a lag number is given; keep the answer under 120 words and add a spoken\_summary of at most 40 words; if tools return nothing, say so.

### 11.4 Assistant graph (LangGraph)

- State: messages, session\_id, tool\_results, citations, spoken.
- Nodes: guard\_in (length limit, prompt-injection patterns, medical-advice detector that returns a short refusal), agent (LLM with tools bound), tools (ToolNode), compose (structured final answer: answer, citations, spoken\_summary), guard\_out (verify every cited id exists and every number in the answer appears in tool results; remove anything unverified).
- Edges: agent to tools while tool calls exist (maximum 4 rounds), then compose, then guard\_out.
- Checkpointer: in-memory with a 30 minute TTL and a cap of 200 sessions, so the database does not grow.
- Tools, all read-only and typed: search\_drugs(query), get\_drug\_summary(drug\_id), list\_events(drug\_id, severity), get\_event\_status(event\_id), list\_stale\_generics(drug\_id, min\_days), explain\_method(). No tool writes, and none accepts raw SQL.
- Stream with astream\_events and map to the SSE event types in section 10.

### 11.5 LangSmith rules (the free plan allows 5,000 traces a month)

- Environment: LANGSMITH\_TRACING, LANGSMITH\_API\_KEY, LANGSMITH\_PROJECT (label-lag-radar-dev and label-lag-radar-prod), LANGSMITH\_ENDPOINT. Tracing is off in tests and CI.
- A trace is one root run; child runs inside it should not add to the count (verify on the LangSmith billing page). So wrap each worker batch of up to 25 judgements in ONE parent run named judge\_batch and let each judgement be a child run.
- Always trace assistant queries, evaluation experiments and error paths. Sample normal batch traces at TRACE\_SAMPLE\_RATE (default 0.2) using langsmith tracing\_context(enabled=...).
- trace\_budget table: increment on each root trace. Above 4,000 in a month, sample only errors and evaluations. Above 4,800, trace only admin-triggered runs. Show the meter on the admin page.
- Metadata on every run: prompt\_version, model, provider, drug\_id, event\_id, cache\_hit, git\_sha. Tags: classify, judge, assistant, eval.
- Feedback: the evidence viewer has thumbs up and down. Send it as LangSmith feedback when a trace id exists and always store it in your own table too.
- Retention is 14 days on the free plan, so keep tokens, latency and status in your own tables.
- Never put secrets or personal data in trace metadata. No audio is ever stored.

## 12. Evaluation plan

**Gold set.** 150 (event, generic set) pairs, stratified: 50 propagated, 40 not\_propagated, 30 partial, 30 hard cases (different wording, repackagers, old-format labels). Split 50 dev and 100 test. Never tune prompts on test. Annotate through /admin/gold/next with the brand claim and the generic section side by side. Annotate the test split twice, a week apart, and report intra-rater agreement (Cohen kappa). If a second annotator is available, report inter-annotator kappa.

**Methods compared.**

- B0 exact: normalised string match of the brand unit.
- B1 lexical: BM25 plus a similarity threshold tuned on dev.
- B2 LLM on full section: whole generic section in the prompt, no retrieval, no verification.
- B3 proposed: retrieval, deterministic shortcuts, judge, quote verification.
- Ablations: B3 without verification, B3 without shortcuts, B3 per free provider.

**Metrics.** Accuracy and macro-F1; precision and recall of not\_propagated (the stale-detection class); mean absolute error of lag days against the gold first version; evidence validity rate (quotes found verbatim); abstention rate; LLM calls and tokens per judgement; latency p50 and p95. Report 95 percent bootstrap confidence intervals and confusion matrices.

**Runner.** backend/app/evaluation/runner.py runs a method over a split without tracing and writes eval\_runs and eval\_items. A second command pushes a 50-example dev subset to a LangSmith dataset and runs LangSmith evaluate with custom evaluators (status match, quote verbatim, abstain). Keep LangSmith experiments near 50 examples per run so the monthly trace cap survives. CI runs a frozen 10-item fixture with fake models to catch plumbing and metric regressions.

**Reporting.** docs/methodology.md and the public Evaluation page show the table, the limits, and a plain statement of where the system fails.

## 13. Voice input and output (open source, on-device)

**Principles.** Audio never leaves the browser; only the transcript text is sent to the API. Voice is optional and off by default. Text is always shown. The spoken reply is the short spoken\_summary, never the whole answer.

**Speech to text.** Library: @huggingface/transformers (Transformers.js). Use the automatic-speech-recognition pipeline with an ONNX Whisper model (start with tiny.en at about 40 MB, offer base.en at about 76 MB), inside a Web Worker. Device: webgpu when navigator.gpu exists, otherwise wasm. Capture the microphone with getUserMedia and resample to 16 kHz mono Float32 with an AudioWorklet. MVP is push-to-talk (hold Space or press the mic button). Optional hands-free mode adds Silero VAD through onnxruntime-web. Fallback if the model cannot load: the browser Web Speech API, with a notice that some browsers send audio to their vendor. Desktop Chrome or Edge is the most reliable.

**Text to speech.** Library: kokoro-js (Kokoro 82M ONNX, quantised q8) in a Web Worker, WebGPU when available, otherwise WASM (verify model id and options in the kokoro-js README). Fallback: window.speechSynthesis. Queue audio chunks in an AudioContext so playback starts quickly. Controls: stop, speed, voice, mute. Barge-in: pressing the mic or Space stops playback at once.

**Loading and consent.** On first use show: Voice downloads about 120 MB of models and runs on your device. Cache models with the Cache API, show progress, and remember the choice in localStorage only.

**Modules.**

- features/voice: useSpeechToText.ts, useTextToSpeech.ts, stt.worker.ts, tts.worker.ts, VoiceButton.tsx, VoiceSettings.tsx, voiceCapabilities.ts (feature detection).
- features/assistant: AssistantDock.tsx with chat list, input box, mic button, streaming message, citation chips, speaking indicator and stop button.

**Accessibility.** Full keyboard use, aria-live region for streamed text, visible recording state, captions for spoken output, respect prefers-reduced-motion.

**Tests.** Unit-test the state machine (idle, loading, listening, transcribing, thinking, speaking, error) with mocked workers. Manual matrix: Chrome desktop with WebGPU, Firefox with WASM, Android Chrome. The app must work fully with voice disabled.

## 14. Frontend specification (React)

**Stack.** React 18 or newer, TypeScript strict, Vite, Tailwind CSS, shadcn/ui (Radix), React Router, TanStack Query, Recharts, Zod, openapi-typescript with openapi-fetch for the typed client, Vitest with Testing Library, Playwright for smoke tests. Hosted on Cloudflare Pages.

**Design direction.** Calm, clinical-editorial: lots of whitespace, a serif for page titles and a clean sans for data, tabular numerals in tables. Status colours must never be the only signal: propagated (green check), partial (amber half-circle), not yet reflected (red outlined dot with label), insufficient evidence (grey dash). Light and dark themes. WCAG 2.2 AA contrast, visible focus rings, keyboard-first.

**Pages.**

1. Dashboard: KPI cards (drugs tracked, events, median lag days, share of generics not yet reflected, last ingestion), lag histogram, table of slowest labelers, table of drugs sorted by stale count.
2. Drug page: header with brand set info; event timeline; the heatmap matrix (rows are generic sets, columns are events, cells show status and lag) with filters for repackagers and severity; click a cell to open the evidence drawer.
3. Event page: claim, severity, brand version and date; list of generics with status chips; filters; export to CSV.
4. Evidence viewer (drawer and full page): brand text and generic text side by side, with the verified quotes highlighted, version selector, link to the DailyMed set, thumbs up or down feedback.
5. Stale generics: filterable, sortable table with CSV download.
6. Evaluation: method comparison table, confusion matrices, abstention and evidence-validity rates, run history.
7. Methodology: plain-language method, limits, wording rules, data sources, model and prompt versions.
8. Assistant dock available on every page: chat, mic button, streaming answer, citation chips that open the evidence viewer, stop-speaking button.
9. Admin (Supabase Auth sign-in, admin role): ingestion runs, job queue, budget meters (LLM calls per provider today, LangSmith traces this month, database MB against 500 MB), gold-label annotation screen with keyboard shortcuts (1 to 4 pick a status, N next).

**Data and state.** Server state only in TanStack Query with sensible stale times; URL holds filters (shareable links); minimal client state (theme, voice settings, session\_id). SSE client for the assistant using fetch with ReadableStream, abort on navigation, automatic retry with backoff.

**Quality bars.**

- Loading skeletons, empty states, error boundaries with request\_id shown, offline notice.
- No layout shift on data load; tables virtualised above 200 rows.
- Bundle budget: initial JS under 250 KB gzipped; voice models lazy-loaded only after consent.
- Lighthouse performance at least 90 and accessibility at least 95 on the dashboard.
- Every page has a title, meta description and a visible last-updated timestamp for the data.
- Every status shown links to its evidence; no number appears without its definition on hover or in the methodology page.

## 15. Production-readiness checklist

**Security.**

- Secrets only in environment variables; .env.example documents them; gitleaks in pre-commit and CI.
- Supabase service credentials stay on the backend. Row Level Security stays on. The browser never receives database credentials.
- Admin routes require a verified Supabase JWT with the admin role; the allowed admin emails are in an env list as a second check.
- Validate all input with Pydantic; cap request body size; cap assistant text at 500 characters.
- Outbound HTTP allow-list (section 7). No user-controlled URLs.
- Rate limiting with slowapi (in-memory is acceptable on one free instance; note the limit in the runbook).
- Security headers (Content-Security-Policy, X-Content-Type-Options, Referrer-Policy, Permissions-Policy with microphone allowed for self only), strict CORS allow-list, no wildcard.
- Prompt-injection hygiene: label text is untrusted data; it is passed to the model only inside delimited blocks, the judge has no tools, and model output is schema-validated and quote-verified.
- pip-audit and npm audit in CI; Dependabot enabled.

**Reliability.**

- Idempotent jobs with attempts, backoff, and a dead-letter state (failed). The worker can be killed at any time and resumes.
- Unique constraints (section 9) make re-runs safe.
- Timeouts on every outbound call; circuit breaker around LLM providers through the fallback chain.
- Graceful shutdown, health and readiness probes, one uvicorn worker on the free host.
- Migrations are forward-only SQL files applied in CI and deploy; never edit an applied migration.
- Weekly pg\_dump of curated tables to a GitHub Actions artifact (the free Supabase plan has no point-in-time restore; verify current backup options).
- Keep-alive workflow so the Supabase project does not pause after 7 idle days.

**Observability.**

- structlog JSON logs with request\_id, route, latency, status; no personal data in logs.
- LangSmith as described in section 11.5. Own tables for budgets and eval results.
- /admin/budget shows quotas so you can see limits approaching before they bite.

**Testing.**

- Unit tests: SPL parser against fixture XML files, unit splitter, differ, retrieval, quote verification (including property tests with random whitespace and punctuation), lag and binary-search logic, budget guard.
- Integration tests: Postgres service container with the real migrations; DailyMed client against recorded cassettes (vcrpy); API tests with httpx AsyncClient.
- LLM tests use langchain\_core fake chat models. A golden test asserts that an invalid quote is rejected.
- Frontend: Vitest component tests, Playwright smoke (dashboard loads, drug page, evidence drawer, assistant text round trip with a mocked stream).
- Coverage gate: backend 80 percent, frontend 70 percent.

**CI/CD (GitHub Actions).**

- ci.yml on pull requests: ruff, mypy, pytest with Postgres service, openapi client drift check, eslint, tsc, vitest, build, Playwright smoke, pip-audit, npm audit, gitleaks.
- deploy: Cloudflare Pages deploys the frontend from main; Render deploys the backend Docker image from main after CI is green.
- ingest.yml: nightly schedule plus manual dispatch; runs python -m app.worker run with a time limit and the daily LLM caps; refreshes materialized views at the end.
- keepalive.yml: weekly database ping and a health ping to the API.

**Containers.** Multi-stage Dockerfile, uv-installed dependencies from the lockfile, non-root user, read-only filesystem where possible, HEALTHCHECK, no dev dependencies in the final image. docker-compose.yml runs Postgres (with pg\_trgm), the API, and the frontend dev server for local work.

**Privacy and legal.** Data is public labeling from NLM and FDA; cite both on the Methodology page and link to each record. The assistant stores no audio and keeps chat only in memory for 30 minutes. License the code MIT. Include a clear not-medical-advice notice in the footer and the assistant.

**Docs to ship.** README (quick start, architecture picture, screenshots), docs/methodology.md, docs/runbook.md (rotate keys, handle quota exhaustion, restore from dump, resume paused Supabase), docs/adr/ for every (verify) item.

## 16. Deployment on free tiers

**One-time setup.**

1. Supabase: create a free project. Copy the transaction pooler URL (runtime) and the session pooler or direct URL (migrations). Enable email sign-in, create your user, and set app\_metadata role to admin from the dashboard.
2. LLM keys: create free API keys for Google AI Studio (Gemini) and Groq; optionally OpenRouter. Optionally run Ollama locally with a small instruct model for development.
3. LangSmith: create a free Developer account, an API key and two projects (dev, prod).
4. Render: new Web Service from the GitHub repo, Docker, free instance, set env vars, health check path /healthz.
5. Cloudflare Pages: connect the repo, build command npm run build in frontend, output dir dist, set VITE\_API\_BASE\_URL.
6. GitHub: add repository secrets (DATABASE\_URL, LLM keys, LANGSMITH\_API\_KEY, SUPABASE\_URL) for the workflows.
7. Run migrations, add the seed drugs, run the first ingestion from the Actions tab.

**Environment variables (backend).**

| Variable | Meaning |
| --- | --- |
| ENV | dev, test or prod |
| DATABASE\_URL | Runtime connection (transaction pooler) |
| DATABASE\_URL\_MIGRATIONS | Migration connection (session pooler or direct) |
| SUPABASE\_URL, SUPABASE\_JWKS\_URL | For verifying admin JWTs |
| ADMIN\_EMAILS | Comma list of allowed admin emails |
| CORS\_ORIGINS | Comma list of allowed frontend origins |
| CONTACT\_EMAIL | Put in the User-Agent for DailyMed and FDA requests |
| LLM\_PROVIDER\_ORDER | For example google\_genai,groq,openrouter,ollama |
| LLM\_MODEL\_CLASSIFY\_x, LLM\_MODEL\_JUDGE\_x, LLM\_MODEL\_ASSISTANT\_x | Model name per provider x |
| GOOGLE\_API\_KEY, GROQ\_API\_KEY, OPENROUTER\_API\_KEY, OLLAMA\_BASE\_URL | Provider access |
| LLM\_DAILY\_CAP\_x, LLM\_RPS\_x | Daily call cap and rate per provider x |
| LANGSMITH\_TRACING, LANGSMITH\_API\_KEY, LANGSMITH\_PROJECT, LANGSMITH\_ENDPOINT | Tracing |
| TRACE\_SAMPLE\_RATE | Default 0.2 for batch runs |
| DB\_SIZE\_LIMIT\_MB | Default 400 |
| STALE\_DAYS | Default 90 |

Frontend variable: VITE\_API\_BASE\_URL, plus the Supabase URL and anon key for admin sign-in only.

**Free-tier caveats to state in the README.** The API sleeps when idle and the first request after a pause is slow; Supabase pauses after 7 idle days unless the keep-alive runs; LLM provider quotas change without notice, so the daily caps are env values; LangSmith traces vanish after 14 days. For real production traffic, the upgrade path is a paid Render instance and the Supabase Pro plan; the code needs no change.

## 17. Cursor rule files (.cursor/rules)

```text
# .cursor/rules/00-project.mdc
---
description: Label Lag Radar project rules
alwaysApply: true
---
- Source of truth is docs/SPEC.md. Check it before designing anything.
- Free and open source only. No paid services, no credit card dependencies.
- Never invent library APIs; read installed source or docs. Record spec deviations in docs/adr/.
- Small commits per task. Run tests, ruff, mypy, eslint and tsc before finishing a task.
- UI and assistant copy must follow the wording rules in section 3 of the spec.
- Every displayed claim links to verified evidence.
```

```text
# .cursor/rules/10-backend.mdc
---
description: Backend conventions
globs: backend/**/*.py
alwaysApply: false
---
- Python 3.12, async everywhere, SQLAlchemy 2 style, Pydantic v2 models for all I/O.
- Layers: api -> services -> repositories. No SQL in routers.
- All outbound HTTP through the allow-listed client with timeouts and retries.
- All LLM access through app/llm/factory.py. Structured output, cache, budget check, tracing rules.
- Stream-parse XML. Keep memory low.
- Type hints required; mypy strict on app/.
```

```text
# .cursor/rules/20-frontend.mdc
---
description: Frontend conventions
globs: frontend/src/**/*.{ts,tsx}
alwaysApply: false
---
- TypeScript strict, no any. Use the generated API client only; no hand-written fetch except the SSE client.
- Server state in TanStack Query. URL holds filters.
- Accessible by default: labels, roles, focus order, aria-live for streams.
- Status is never conveyed by colour alone.
- Voice models load lazily after explicit consent.
```

```text
# .cursor/rules/30-db.mdc
---
description: Database and migrations
globs: supabase/migrations/**/*.sql
alwaysApply: false
---
- Forward-only migrations. Never edit an applied file; add a new one.
- RLS enabled on every table. No policies for anon or authenticated.
- Keep the database small: dedupe text by hash, store only safety sections, never raw SPL files.
```

```text
# .cursor/rules/40-testing.mdc
---
description: Testing rules
globs: **/tests/**
alwaysApply: false
---
- No live network or live LLM calls in tests. Use cassettes and fake chat models.
- Every bug fix gets a regression test.
- Quote verification and lag logic need property-based or table-driven tests.
```

## 18. Phase prompts (paste one at a time after the Master Prompt)

**Phase 0. Scaffold (half a day).**

```text
Phase 0. Create the repo skeleton from section 6 of docs/SPEC.md: backend (uv, FastAPI app factory, config via pydantic-settings, structlog, /healthz and /readyz, error handlers returning problem+json), frontend (Vite React TS, Tailwind, shadcn/ui, router, a placeholder dashboard), docker-compose.yml with Postgres, Makefile (make dev, test, lint, migrate), pre-commit (ruff, mypy, eslint, gitleaks), the five .cursor/rules files from section 17, and ci.yml. Acceptance: make test and make lint pass, docker compose up serves the API and the frontend, CI is green.
```

**Phase 1. Database (half a day).**

```text
Phase 1. Add supabase/migrations/0001_init.sql exactly as in section 9, async SQLAlchemy models and repositories, a migration runner, and integration tests against a Postgres service container. Add the database-size guard (blocks ingestion above DB_SIZE_LIMIT_MB) and the llm_budget and trace_budget helpers. Acceptance: migrations apply cleanly twice (idempotent runner), repository tests pass, RLS is enabled on every table.
```

**Phase 2. Ingestion (2 days).**

```text
Phase 2. Implement section 7: allow-listed rate-limited DailyMed client, Orange Book importer and RLD linker, SPL parser (lxml, safety sections by LOINC, unit normaliser, hash dedupe), seed loader from config/seed_drugs.yaml, ingestion_runs logging, and the CLI python -m app.worker ingest. Record real sample SPL files as fixtures and recorded HTTP cassettes. Verify every (verify) item against real responses and write ADRs. Acceptance: ingesting warfarin and montelukast stores brand and generic sets with all versions' safety sections; re-running changes nothing; parser tests cover old-format and PLR-format labels.
```

**Phase 3. Event detection (1 to 2 days).**

```text
Phase 3. Implement section 8 steps A to C: units, differ, ClassifyOut chain through the LLM factory (fake model in tests), safety_events creation with claim_hash dedupe, optional SrLC CSV importer for validation. Add a CLI command to detect events for one drug. Acceptance: for warfarin and montelukast, events are produced; editorial-only diffs produce none in tests; a rerun creates no duplicates.
```

**Phase 4. Judging and lag (2 days).**

```text
Phase 4. Implement section 8 steps D to H plus section 11.1 to 11.3 and 11.5: retrieval, deterministic shortcuts, JudgeOut chain, quote verifier, binary search over generic versions with non-monotonic flag, lag computation, DB job queue with SKIP LOCKED, daily budgets, cache keys, judge_batch parent traces. Acceptance: tests prove invalid quotes are rejected, budget exhaustion defers jobs, a killed worker resumes, and a seed drug runs end to end with a local or free-tier model.
```

**Phase 5. API (1 to 2 days).**

```text
Phase 5. Implement every endpoint in section 10 with Pydantic models, pagination, filters, CSV export, rate limits, CORS, security headers, and Supabase JWT admin auth. Generate the OpenAPI client for the frontend and add the drift check to CI. Acceptance: API tests cover every route and error shape; the admin routes reject missing, expired and non-admin tokens.
```

**Phase 6. Assistant (1 to 2 days).**

```text
Phase 6. Implement section 11.4: LangGraph assistant with the read-only tools, guard_in and guard_out, SSE streaming, in-memory checkpointer with TTL, always-trace rule for LangSmith. Acceptance: tests with a fake model show that medical-advice questions are refused, that unverified numbers are stripped, that tool rounds are capped, and that the SSE stream emits token, citation, spoken_summary and done events.
```

**Phase 7. Frontend (3 days).**

```text
Phase 7. Build section 14 pages using the generated client. Start with dashboard, drug page with heatmap, event page and evidence viewer, then stale list, methodology, evaluation and admin. Follow the design direction and quality bars. Acceptance: Playwright smoke tests pass, Lighthouse targets are met, keyboard-only navigation works on every page.
```

**Phase 8. Voice (1 to 2 days).**

```text
Phase 8. Implement section 13 in frontend/src/features/voice and AssistantDock: Whisper STT and Kokoro TTS in Web Workers with WebGPU and WASM fallback, push-to-talk, consent dialog with model download progress, speechSynthesis and Web Speech fallbacks, barge-in, captions, state machine tests. Verify model ids against the library READMEs and write an ADR. Acceptance: voice round trip works on desktop Chrome, the app is fully usable with voice off, initial bundle budget still met.
```

**Phase 9. Evaluation (2 days, partly manual).**

```text
Phase 9. Implement section 12: gold annotation screen and endpoints, baselines B0 to B3, metrics with bootstrap intervals, runner, LangSmith dev-subset experiment command, public Evaluation page, docs/methodology.md. Acceptance: python -m app.evaluation run --method B3 --split dev writes eval_runs and eval_items; the Evaluation page renders the comparison table and confusion matrices.
```

**Phase 10. Harden and ship (1 to 2 days).**

```text
Phase 10. Complete section 15 and 16: Dockerfile hardening, nightly ingest and keep-alive workflows, deploy configs for Render and Cloudflare Pages, README with architecture diagram and screenshots, runbook, ADR cleanup, dependency audit, final accessibility and performance pass. Acceptance: a fresh clone can follow the README to a working deployment using only free tiers.
```

## 19. Definition of done and risks

**Definition of done.**

- 25 seed drugs ingested; events detected; judgements stored with verified evidence.
- Gold set of 150 labelled; B0 to B3 evaluated with confidence intervals; results published in the app and in docs/methodology.md.
- Public site live on free tiers; assistant answers with citations; voice works on desktop Chrome.
- CI green with coverage gates; no secrets in the repo; runbook written.
- A short write-up with your headline numbers: median lag, share of generics not yet reflected, and how B3 compares with the baselines.

**Main risks and mitigations.**

| Risk | Mitigation |
| --- | --- |
| LLM quota runs out or changes | Provider fallback, env caps, job deferral, cache, Ollama fallback, deterministic shortcuts that skip the model |
| Database passes 500 MB | Hash-deduplicated sections, safety sections only, size guard at 400 MB, fewer seed drugs |
| LangSmith 5,000-trace cap | Batch parent traces, sampling, trace budget, local evaluation runner |
| ANDA to brand linking is wrong | Confidence score, manual override table, show link method in the UI |
| Old-format labels break section parsing | Fixtures for both formats, fall back to whole-label text with lower confidence |
| Misreading dates as approval dates | Wording rules, methodology page, tooltip on every lag number |
| Model hallucinated quotes | Verbatim quote verification, downgrade to insufficient\_evidence |
| Voice models too heavy on low-end devices | Opt-in, tiny model first, Web Speech and speechSynthesis fallbacks, text always available |
| Render cold starts | Loading states, optional health ping, honest README note |

**After v1.** Add the Interaction Reciprocity idea as a second module on the same ingestion layer; add Bangla voice with a multilingual Whisper model; publish the dataset and a short workshop paper.
