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

-- Optional, explicit publication channel for MUTOPIA. Run only after reviewing
-- the disclosure model; private vault rows and the private bucket stay private.
create table if not exists public.mutopia_public_records (
  id text primary key,
  owner_id uuid not null references auth.users(id),
  title text not null check (length(title) <= 200),
  type text not null check (type in ('SOURCE', 'PRINCIPLE', 'IDEA', 'VISUAL')),
  category text not null default '' check (length(category) <= 120),
  tags jsonb not null default '[]'::jsonb check (jsonb_typeof(tags) = 'array'),
  body text not null default '' check (length(body) <= 12000),
  relations jsonb not null default '[]'::jsonb check (jsonb_typeof(relations) = 'array'),
  created_at timestamptz,
  image_path text,
  published_at timestamptz not null default now()
);
alter table public.mutopia_public_records enable row level security;
revoke all on public.mutopia_public_records from anon, authenticated;
grant select on public.mutopia_public_records to anon, authenticated;
grant insert, update, delete on public.mutopia_public_records to authenticated;
drop policy if exists mutopia_public_read on public.mutopia_public_records;
create policy mutopia_public_read on public.mutopia_public_records
  for select to anon, authenticated using (true);
drop policy if exists mutopia_owner_manage on public.mutopia_public_records;
create policy mutopia_owner_manage on public.mutopia_public_records
  for all to authenticated
  using ((select auth.uid()) = owner_id)
  with check ((select auth.uid()) = owner_id);

insert into storage.buckets (id, name, public, file_size_limit)
values ('mutopia-public', 'mutopia-public', true, 5242880)
on conflict (id) do update set public = true, file_size_limit = 5242880;
drop policy if exists mutopia_public_image_read on storage.objects;
create policy mutopia_public_image_read on storage.objects
  for select to anon, authenticated using (bucket_id = 'mutopia-public');
drop policy if exists mutopia_owner_image_write on storage.objects;
create policy mutopia_owner_image_write on storage.objects
  for all to authenticated
  using (bucket_id = 'mutopia-public' and (storage.foldername(name))[1] = (select auth.uid())::text)
  with check (bucket_id = 'mutopia-public' and (storage.foldername(name))[1] = (select auth.uid())::text);
