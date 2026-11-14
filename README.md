# Label Lag Radar

Research tool that measures how long generic drug labels take to show a brand drug's new safety
changes, using public DailyMed label versions and the FDA Orange Book.

**Not medical advice. Not a regulatory finding.** Dates are DailyMed publication dates, not the
dates companies made or submitted changes.

## Architecture

```mermaid
flowchart LR
  OB[FDA Orange Book] --> I[Ingest]
  DM[DailyMed SPL versions] --> I
  I --> DB[(Postgres on Supabase)]
  DB --> D[Detect brand safety changes]
  D -->|classify, cached| LLM[LLM providers<br/>Gemini, OpenRouter, Groq, Ollama]
  D --> DB
  DB --> J[Judge generic labels]
  J -->|judge, verified quotes| LLM
  J --> DB
  DB --> API[FastAPI]
  API --> WEB[React app]
```

## Pipeline

```mermaid
flowchart TD
  A[Orange Book products] --> B[Group into NDA and ANDA applications]
  B --> C[Link generics to the brand reference listing]
  C --> E[List DailyMed label sets per application]
  E --> F[Store every version, parse safety sections by LOINC code]
  F --> G[Diff consecutive brand versions unit by unit]
  G --> H{Substantive safety change?}
  H -- editorial --> X[Drop]
  H -- yes --> K[Safety event]
  K --> L[Retrieve matching text in each generic label]
  L --> M{Near-identical text?}
  M -- yes --> P[Reflected]
  M -- no --> N{Any similar text?}
  N -- no --> Q[Not yet reflected]
  N -- yes --> O[Model judgement, quotes verified word for word]
  O --> R[Binary search for the first generic version that reflects it]
  P --> R
  R --> S[Lag in days]
```

How each step works:

1. **Ingest.** The Orange Book links brand (RLD) and generic applications. Each application's
   DailyMed label sets and all their versions are stored; safety sections are parsed by LOINC
   code and de-duplicated by hash.
2. **Detect.** Consecutive brand versions are diffed unit by unit. Added or changed units go to a
   classifier that drops editorial edits; substantive ones become safety events.
3. **Judge.** For each event and generic label, the matching text is retrieved (BM25 plus fuzzy
   match). Near-identical text is "reflected" and unrelated text is "not yet reflected" without a
   model call; otherwise a model judges and every quote must appear word for word. A binary search
   finds the first generic version that reflects the change, which gives the lag.
4. **Serve.** A read-only API and a React app show KPIs, a per-drug heatmap, the evidence for each
   judgement and the list of generics not yet reflecting changes (CSV export).

## LLM provider fallback

```mermaid
sequenceDiagram
  participant W as Worker
  participant C as llm_cache
  participant B as llm_budget
  participant P1 as Gemini
  participant P2 as OpenRouter
  W->>C: look up hash of task, prompt version, inputs
  alt cached
    C-->>W: stored answer, no model call
  else not cached
    W->>B: daily cap left for Gemini?
    W->>P1: structured request
    P1-->>W: error or rate limit
    W->>B: daily cap left for OpenRouter?
    W->>P2: structured request
    P2-->>W: answer
    W->>B: record call and tokens
    W->>C: store answer
  end
```

Providers are tried in `LLM_PROVIDER_ORDER`. When every provider's daily cap is used up, the run
stops with status `partial` and resumes from the cache on the next run.

## Deployment

```mermaid
flowchart LR
  U[Browser] --> CF[Cloudflare Pages<br/>React app]
  CF -->|/api/v1| R[Render<br/>FastAPI container]
  R --> S[(Supabase Postgres)]
  GH[GitHub Actions<br/>nightly.yml] -->|ingest, detect, judge| S
  GH --> DMS[DailyMed and FDA]
  GH --> LLMS[LLM providers]
```

## Data model

```mermaid
erDiagram
  drugs ||--o{ applications : has
  drugs ||--o{ spl_sets : has
  applications ||--o{ spl_sets : labels
  spl_sets ||--o{ spl_versions : versions
  spl_versions ||--o{ version_sections : sections
  section_texts ||--o{ version_sections : "text by hash"
  spl_sets ||--o{ safety_events : "brand changes"
  safety_events ||--o{ propagation_judgements : judged
  spl_sets ||--o{ propagation_judgements : "generic label"
```

Full design: [docs/SPEC.md](docs/SPEC.md). Decisions: [docs/adr](docs/adr).

## Run locally

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22, Postgres 17.

```bash
cp backend/.env.example backend/.env      # fill in CONTACT_EMAIL, DATABASE_URL and LLM keys
cd backend
uv sync
uv run python -m app.db.migrate
uv run python -m app.worker ingest --drug warfarin --drug montelukast
uv run python -m app.worker detect --drug warfarin --drug montelukast --max-calls 40
uv run python -m app.worker judge  --drug warfarin --drug montelukast --max-calls 40
uv run uvicorn app.main:create_app --factory --reload   # API on http://localhost:8000/api/docs

cd ../frontend
npm ci
npm run dev                                # http://localhost:5173
```

`make dev`, `make test` and `make lint` (or `scripts/tasks.ps1` on Windows) wrap the same
commands; `docker compose up` starts Postgres, the API and the frontend together.

Tests: `uv run pytest` (integration tests need `TEST_DATABASE_URL`) and `npm test`.

## Deploy

1. **Supabase.** Create a project. Copy the transaction pooler URL (port 6543) as `DATABASE_URL`
   with the `postgresql+asyncpg://` scheme, and the session pooler URL (port 5432) as
   `DATABASE_URL_MIGRATIONS`. Run `uv run python -m app.db.migrate` once.
2. **LLM providers.** Add keys for the providers you use (`GOOGLE_API_KEY`, `OPENROUTER_API_KEY`,
   `GROQ_API_KEY`) and set their order in `LLM_PROVIDER_ORDER`. Model names are env values per
   provider and task, for example `LLM_MODEL_CLASSIFY_openrouter`; daily caps are
   `LLM_DAILY_CAP_<provider>`.
3. **Render.** New Blueprint from this repo ([render.yaml](render.yaml)). Fill the secret env vars,
   including `CORS_ORIGINS` with the Pages URL.
4. **Cloudflare Pages.** Root `frontend`, build `npm run build`, output `dist`, env
   `VITE_API_BASE_URL` set to the Render URL.
5. **GitHub Actions.** Add secrets `DATABASE_URL`, `DATABASE_URL_MIGRATIONS`, `CONTACT_EMAIL` and
   the provider keys, and variables for the model names (for example
   `LLM_MODEL_CLASSIFY_GOOGLE_GENAI`). [nightly.yml](.github/workflows/nightly.yml) then ingests,
   detects and judges every night and can be started by hand from the Actions tab.

**Hosting caveats.** On Render's starter instance the API sleeps when idle, so the first request
after a pause is slow. A Supabase starter project pauses after 7 idle days; the nightly job keeps
it active. Provider quotas can change without notice, which is why daily caps are env values. The
database stops ingesting new text above `DB_SIZE_LIMIT_MB` (400).

## Known limits

- Dates are publication dates. A change may be pending at FDA or worded differently.
- Some brand labels are no longer on DailyMed (for example Coumadin); repackaged copies of the
  brand label then stand in as brand history, and their dates are less precise.
- Old-format labels split sections differently from PLR labels, so a format conversion can be
  detected as new text.
- Repackager labels copy their source and are excluded from counts by default.

## Scope

Built: ingestion, event detection, judging and lag, the public read API, and the dashboard, drug,
event, stale and methodology pages. Not built yet (see SPEC phases 6, 8 and 9 and the admin
endpoints in section 10): the LangGraph assistant, voice, the evaluation harness and the admin
screens.
