create extension if not exists pgcrypto;

create table if not exists patients (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  phone text not null,
  caregiver_name text,
  caregiver_phone text not null,
  created_at timestamptz default now()
);

create unique index if not exists idx_patients_phone_unique on patients(phone);

create table if not exists medicines (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid references patients(id) on delete cascade,
  name text,
  dosage text,
  frequency text,
  instructions text,
  image_url text,
  raw_ocr_text text,
  detected_at timestamptz default now()
);

create table if not exists reminders (
  id uuid primary key default gen_random_uuid(),
  medicine_id uuid references medicines(id) on delete cascade,
  patient_id uuid references patients(id) on delete cascade,
  reminder_time time not null,
  days_of_week text[] default array['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
  is_active boolean default true,
  last_sent_at timestamptz,
  created_at timestamptz default now()
);

create table if not exists known_faces (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid references patients(id) on delete cascade,
  label text,
  face_encoding bytea not null,
  image_url text,
  times_seen integer default 1,
  is_familiar boolean default false,
  first_seen_at timestamptz default now(),
  last_seen_at timestamptz default now()
);

create table if not exists alerts (
  id uuid primary key default gen_random_uuid(),
  patient_id uuid references patients(id) on delete cascade,
  type text not null check (type in ('medicine_reminder', 'unfamiliar_face', 'hazard_sos')),
  severity text not null check (severity in ('info', 'warning', 'critical')),
  title text not null,
  message text,
  image_url text,
  sent_to_patient boolean default false,
  sent_to_caregiver boolean default false,
  acknowledged boolean default false,
  created_at timestamptz default now()
);

create index if not exists idx_medicines_patient_detected_at on medicines(patient_id, detected_at desc);
create index if not exists idx_reminders_patient_active on reminders(patient_id, is_active);
create index if not exists idx_known_faces_patient_last_seen on known_faces(patient_id, last_seen_at desc);
create index if not exists idx_alerts_patient_created_at on alerts(patient_id, created_at desc);

insert into storage.buckets (id, name, public)
values ('detection-images', 'detection-images', true)
on conflict (id) do update set public = true;

grant usage on schema public to anon, authenticated;
grant select, insert, update, delete on all tables in schema public to anon, authenticated;
grant usage, select on all sequences in schema public to anon, authenticated;

alter default privileges in schema public
grant select, insert, update, delete on tables to anon, authenticated;

alter default privileges in schema public
grant usage, select on sequences to anon, authenticated;

alter table patients enable row level security;
alter table medicines enable row level security;
alter table reminders enable row level security;
alter table known_faces enable row level security;
alter table alerts enable row level security;

drop policy if exists "patients_public_access" on patients;
create policy "patients_public_access"
on patients
for all
to anon, authenticated
using (true)
with check (true);

drop policy if exists "medicines_public_access" on medicines;
create policy "medicines_public_access"
on medicines
for all
to anon, authenticated
using (true)
with check (true);

drop policy if exists "reminders_public_access" on reminders;
create policy "reminders_public_access"
on reminders
for all
to anon, authenticated
using (true)
with check (true);

drop policy if exists "known_faces_public_access" on known_faces;
create policy "known_faces_public_access"
on known_faces
for all
to anon, authenticated
using (true)
with check (true);

drop policy if exists "alerts_public_access" on alerts;
create policy "alerts_public_access"
on alerts
for all
to anon, authenticated
using (true)
with check (true);

drop policy if exists "detection_images_public_select" on storage.objects;
create policy "detection_images_public_select"
on storage.objects
for select
to anon, authenticated
using (bucket_id = 'detection-images');

drop policy if exists "detection_images_public_insert" on storage.objects;
create policy "detection_images_public_insert"
on storage.objects
for insert
to anon, authenticated
with check (bucket_id = 'detection-images');

drop policy if exists "detection_images_public_update" on storage.objects;
create policy "detection_images_public_update"
on storage.objects
for update
to anon, authenticated
using (bucket_id = 'detection-images')
with check (bucket_id = 'detection-images');

drop policy if exists "detection_images_public_delete" on storage.objects;
create policy "detection_images_public_delete"
on storage.objects
for delete
to anon, authenticated
using (bucket_id = 'detection-images');

do $$
begin
  if not exists (
    select 1
    from pg_publication_tables
    where pubname = 'supabase_realtime'
      and schemaname = 'public'
      and tablename = 'alerts'
  ) then
    alter publication supabase_realtime add table public.alerts;
  end if;
end $$;
