-- Run once in your own Supabase project's SQL Editor.
-- Sign up/create your sole user in Auth > Users and disable public signup.
create table if not exists public.vault_records (
  id text primary key,
  owner_id uuid not null references auth.users(id),
  metadata jsonb not null
);
alter table public.vault_records enable row level security;
create index if not exists vault_records_owner_idx on public.vault_records(owner_id);
revoke all on public.vault_records from anon;
grant select, insert, update, delete on public.vault_records to authenticated;
drop policy if exists vault_owner on public.vault_records;
create policy vault_owner on public.vault_records
  for all to authenticated
  using ((select auth.uid()) = owner_id)
  with check ((select auth.uid()) = owner_id and metadata->>'id' = id);

insert into storage.buckets (id, name, public, file_size_limit)
values ('idea-vault', 'idea-vault', false, 52428800)
on conflict (id) do update set public = false, file_size_limit = 52428800;
drop policy if exists idea_vault_owner on storage.objects;
create policy idea_vault_owner on storage.objects
  for all to authenticated
  using (bucket_id = 'idea-vault' and (storage.foldername(name))[1] = (select auth.uid())::text)
  with check (bucket_id = 'idea-vault' and (storage.foldername(name))[1] = (select auth.uid())::text);
