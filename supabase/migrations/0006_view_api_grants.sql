-- Re-apply API role revokes after 0005 recreated v_current_judgement and mv_drug_lag.
do $$
declare r text;
begin
  foreach r in array array['anon', 'authenticated'] loop
    if exists (select 1 from pg_roles where rolname = r) then
      execute format('revoke all on v_current_judgement, mv_drug_lag from %I', r);
    end if;
  end loop;
end $$;
