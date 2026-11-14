-- Medicines added by users (fetched by the nightly job) and leaflet checks against US brand
-- safety changes. Leaflet uploads are unverified user submissions.
alter table drugs add column requested_at timestamptz;

create table leaflet_checks (
  id uuid primary key default gen_random_uuid(),
  drug_id uuid not null references drugs(id) on delete cascade,
  country text not null default 'BD' check (country ~ '^[A-Z]{2}$'),
  brand_name text not null,
  manufacturer text,
  registration_no text,
  source text not null check (source in ('pdf_text', 'vision', 'typed')),
  file_sha256 text,
  leaflet_text text not null,
  results jsonb not null,
  counts jsonb not null,
  consistency jsonb not null default '{}'::jsonb,
  prompt_version text not null,
  provider text,
  model text,
  created_at timestamptz not null default now()
);

create index leaflet_checks_drug_idx on leaflet_checks (drug_id, created_at desc);
create index leaflet_checks_sha_idx on leaflet_checks (file_sha256);

alter table leaflet_checks enable row level security;
