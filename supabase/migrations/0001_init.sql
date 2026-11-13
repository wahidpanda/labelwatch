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
