-- Cache of structured LLM outputs keyed by task, prompt version, model family and inputs
-- (SPEC 11.1). Bumping PROMPT_VERSION changes every key, which invalidates the cache on purpose.
create table llm_cache (
  cache_key text primary key,
  task text not null check (task in ('classify', 'judge')),
  prompt_version text not null,
  model text not null,
  provider text not null,
  output jsonb not null,
  created_at timestamptz not null default now()
);

alter table llm_cache enable row level security;
