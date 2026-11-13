# 0002: Lock down views for the Supabase Data API

Date: 2026-11-13. Status: accepted.

## Context

Section 9 enables RLS on every table, but `v_current_judgement` is a plain view (runs with
the owner's rights, so it bypasses RLS) and `mv_drug_lag` is a materialized view (RLS is not
supported). Supabase exposes the `public` schema to the `anon` and `authenticated` roles, so
both would be readable from the browser with the publishable key. The spec says the browser
never reads the database directly.

## Decision

Keep `0001_init.sql` exactly as in the spec. Add `0002_lock_down_views.sql`, which sets
`security_invoker = true` on the view and revokes all privileges on both views from `anon` and
`authenticated` when those roles exist (they do not exist in plain local Postgres).

## Consequences

Only the backend database role reads the views. Integration tests assert the revocation when
the roles are present.
