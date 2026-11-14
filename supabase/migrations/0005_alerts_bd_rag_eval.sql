-- Alerts, Bangladesh brand index, RAG corpus, eval extras, Jev/cascade judgement methods.
create extension if not exists pg_trgm;

create table subscribers (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  email_norm text not null unique,
  locale text not null default 'en' check (locale in ('en', 'bn')),
  frequency text not null default 'weekly' check (frequency in ('immediate', 'weekly')),
  min_severity text not null default 'major' check (min_severity in ('boxed', 'major', 'moderate', 'minor')),
  status text not null default 'pending' check (status in ('pending', 'active', 'unsubscribed', 'bounced')),
  consent_version text not null,
  consented_at timestamptz not null default now(),
  confirmed_at timestamptz,
  unsubscribed_at timestamptz,
  last_digest_at timestamptz,
  created_at timestamptz not null default now()
);

create table watchlists (
  subscriber_id uuid not null references subscribers (id) on delete cascade,
  drug_id uuid not null references drugs (id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (subscriber_id, drug_id)
);

create table notification_events (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('new_event', 'stale_generic')),
  drug_id uuid not null references drugs (id) on delete cascade,
  event_id uuid references safety_events (id) on delete cascade,
  generic_set_id uuid references spl_sets (id) on delete cascade,
  dedupe_key text not null unique,
  payload jsonb not null default '{}',
  created_at timestamptz not null default now()
);

create table email_outbox (
  id uuid primary key default gen_random_uuid(),
  subscriber_id uuid not null references subscribers (id) on delete cascade,
  template text not null check (template in ('confirm', 'alert', 'digest', 'test')),
  locale text not null,
  subject text not null,
  dedupe_key text not null unique,
  context jsonb not null default '{}',
  status text not null default 'queued' check (status in ('queued', 'sending', 'sent', 'failed', 'skipped')),
  attempts int not null default 0,
  last_error text,
  provider_message_id text,
  scheduled_at timestamptz not null default now(),
  sent_at timestamptz,
  created_at timestamptz not null default now()
);
create index email_outbox_status_scheduled_idx on email_outbox (status, scheduled_at);

create table ingredient_synonyms (
  alias_norm text primary key,
  ingredient_norm text not null,
  source text
);

create table bd_brands (
  id uuid primary key default gen_random_uuid(),
  brand_name text not null,
  brand_norm text not null,
  generic_name text not null,
  generic_norm text not null,
  drug_id uuid references drugs (id) on delete set null,
  strength text,
  dosage_form text,
  manufacturer text,
  source text not null,
  source_license text,
  created_at timestamptz not null default now(),
  unique (brand_norm, strength, dosage_form, manufacturer)
);
create index bd_brands_brand_trgm on bd_brands using gin (brand_norm gin_trgm_ops);
create index bd_brands_generic on bd_brands (generic_norm);

create table rag_docs (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('event', 'judgement', 'method', 'faq', 'drug')),
  ref_id uuid,
  lang text not null default 'en',
  title text not null,
  body text not null,
  meta jsonb not null default '{}',
  tsv tsvector generated always as (
    to_tsvector('simple'::regconfig, coalesce(title, '') || ' ' || body)
  ) stored,
  updated_at timestamptz not null default now(),
  unique (kind, ref_id, lang)
);
create index rag_docs_tsv on rag_docs using gin (tsv);
create index rag_docs_title_trgm on rag_docs using gin (title gin_trgm_ops);

create table chat_feedback (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null,
  message_id text not null,
  rating smallint not null check (rating in (-1, 1)),
  comment text,
  created_at timestamptz not null default now()
);

create table eval_items_extra (
  id uuid primary key default gen_random_uuid(),
  kind text not null check (kind in ('data_qa', 'retrieval', 'refusal', 'injection', 'bd_brand')),
  lang text not null default 'en',
  question text not null,
  expected jsonb not null,
  split text not null default 'test' check (split in ('dev', 'test')),
  created_at timestamptz not null default now()
);

alter table propagation_judgements drop constraint if exists propagation_judgements_method_check;
alter table propagation_judgements add constraint propagation_judgements_method_check check (
  method in (
    'baseline_exact',
    'baseline_unchanged',
    'baseline_lexical',
    'llm',
    'jev',
    'cascade',
    'human'
  )
);

drop materialized view if exists mv_drug_lag;
drop view if exists v_current_judgement;

create view v_current_judgement as
select distinct on (event_id, generic_set_id) *
from propagation_judgements
where method in (
  'llm',
  'jev',
  'cascade',
  'baseline_exact',
  'baseline_unchanged',
  'baseline_lexical',
  'human'
)
order by event_id, generic_set_id, (method = 'human') desc, created_at desc;

create materialized view mv_drug_lag as
select
  e.drug_id,
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

do $$
declare
  t text;
begin
  for t in
    select tablename
    from pg_tables
    where schemaname = 'public'
      and tablename not in ('schema_migrations')
  loop
    execute format('alter table %I enable row level security', t);
  end loop;
end $$;

alter view v_current_judgement set (security_invoker = true);
