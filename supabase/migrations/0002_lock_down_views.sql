-- Views run with the owner's rights and materialized views cannot have RLS, so on Supabase
-- they would be readable through the Data API. Make the view respect RLS of its base table
-- and remove direct access for the API roles. The backend role keeps full access.
alter view v_current_judgement set (security_invoker = true);

do $$
declare r text;
begin
  foreach r in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke all on v_current_judgement, mv_drug_lag from %I', r);
    end if;
  end loop;
end $$;
