-- ============================================================
-- בודק העבודות: מסד הנתונים המשותף (Supabase / PostgreSQL)
--
-- מי מריץ: כל חבר צוות שהקים את הפרויקט ב-Supabase (לא חייב להיות בעל הריפו).
-- המדריך המלא נמצא באתר בכתובת #/setup, ובקובץ SETUP.md.
--
-- איך מריצים: Supabase → SQL Editor → New query → להדביק את כל הקובץ → Run.
-- התוצאה הצפויה: "Success. No rows returned".
-- בטוח להריץ שוב: הקובץ לא מוחק נתונים ולא יוצר כפילויות.
--
-- מה הקובץ עושה, לפי הסדר:
--   1. טבלת members: רשימת הצוות (שמות משתמש ב-GitHub) ותפקיד: admin או staff.
--   2. פונקציות שבודקות מי מחובר והאם הוא בצוות או מנהל.
--   3. טבלאות הנתונים: קורסים, מטלות, מחוונים, הגשות, הנחיות לכל שלב, הגדרות, יומן ריצות.
--   4. חתימה אוטומטית: כל שינוי שומר מתי ומי (לפי GitHub) עשה אותו.
--   5. הרשאות: רק חברי צוות קוראים וכותבים, רק מנהל מוחק או מנהל את רשימת הצוות.
--   6. עדכונים חיים: כל שינוי מגיע מיד לכל מי שמחובר לאתר.
--   7. תיקייה פרטית לקבצי הפתרונות הרשמיים.
--   8. הצוות ההתחלתי: השותפים שכבר אישרו את ההזמנה לריפו ב-GitHub.
--
-- מי רואה מה:
--   * רק משתמשי GitHub שמופיעים בטבלת members יכולים לקרוא ולכתוב.
--   * מי שנכנס לאתר בלי להתחבר רואה רק את נתוני ההדגמה שבקוד, לא את המסד.
--   * ההרשאות נאכפות כאן, במסד עצמו (Row Level Security), ולא רק בקוד של האתר.
--
-- פעולות נפוצות (להריץ ב-SQL Editor, שם אין מגבלות הרשאה):
--   להוסיף את עצמך כמנהל, אם הקמת את המסד ואינך ברשימה שבסוף הקובץ:
--     insert into public.members (github_username, role) values ('your-github-name', 'admin')
--     on conflict (github_username) do update set role = 'admin';
--   להפוך חבר צוות קיים למנהל:
--     update public.members set role = 'admin' where github_username = 'their-github-name';
--   לראות את הרשימה:
--     select * from public.members;
-- ============================================================

-- ---------- צוות ----------
create table if not exists public.members (
  github_username text primary key,
  role text not null default 'staff' check (role in ('admin', 'staff')),
  added_at timestamptz not null default now()
);

-- שם המשתמש ב-GitHub של מי שמחובר עכשיו.
-- נלקח מ-auth.identities (שהמשתמש לא יכול לערוך), ולא מ-user_metadata (שהוא כן יכול).
create or replace function public.current_github_login() returns text
language sql stable security definer set search_path = '' as $$
  select i.identity_data ->> 'user_name'
  from auth.identities i
  where i.user_id = auth.uid() and i.provider = 'github'
  limit 1;
$$;

create or replace function public.is_member() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.members m
    where lower(m.github_username) = lower(public.current_github_login())
  );
$$;

create or replace function public.is_admin() returns boolean
language sql stable security definer set search_path = '' as $$
  select exists (
    select 1 from public.members m
    where lower(m.github_username) = lower(public.current_github_login()) and m.role = 'admin'
  );
$$;

-- כל שינוי נחתם בזמן ובשם המשתמש ב-GitHub של מי שעשה אותו
create or replace function public.touch() returns trigger
language plpgsql security definer set search_path = '' as $$
begin
  new.updated_at := now();
  new.updated_by := public.current_github_login();
  return new;
end;
$$;

-- ---------- נתונים ----------
create table if not exists public.courses (
  id text primary key,
  name text not null,
  updated_at timestamptz not null default now(),
  updated_by text
);

create table if not exists public.assignments (
  id text primary key,
  course_id text not null references public.courses (id) on delete cascade,
  n int not null,
  title text not null,
  due timestamptz not null,
  phase text not null default 'new',
  pulled_at timestamptz,
  graded_at timestamptz,
  returned_at timestamptz,
  last_fresh int,
  solution_file text,
  solution_path text,
  updated_at timestamptz not null default now(),
  updated_by text
);
create index if not exists assignments_course_idx on public.assignments (course_id);

create table if not exists public.rubrics (
  course_id text primary key references public.courses (id) on delete cascade,
  questions jsonb not null default '[]',
  emphases jsonb not null default '[]',
  updated_at timestamptz not null default now(),
  updated_by text
);

create table if not exists public.submissions (
  id text primary key,
  assignment_id text not null references public.assignments (id) on delete cascade,
  student_name text not null,
  student_id text not null,
  email text,
  submitted_at timestamptz not null,
  late boolean not null default false,
  scanned boolean not null default false,
  files jsonb not null default '[]',
  status text not null default 'pulled' check (status in ('pulled', 'grading', 'graded', 'returned', 'error')),
  q jsonb,
  score int check (score between 0 and 100),
  issue text,
  feedback text,
  updated_at timestamptz not null default now(),
  updated_by text
);
create index if not exists submissions_assignment_idx on public.submissions (assignment_id);

-- ההנחיות שכותבים בלשונית "הנחיות" של כל שלב
create table if not exists public.stage_instructions (
  stage text primary key check (stage in ('pull', 'grade', 'ret')),
  body text not null default '',
  updated_at timestamptz not null default now(),
  updated_by text
);

-- הגדרות: חיבור למודל, Claude, פורמט ההחזרה
create table if not exists public.settings (
  key text primary key,
  value jsonb not null,
  updated_at timestamptz not null default now(),
  updated_by text
);

create table if not exists public.runs (
  id bigint generated always as identity primary key,
  at timestamptz not null default now(),
  kind text not null check (kind in ('pull', 'grade', 'return', 'error')),
  text text not null,
  where_text text,
  actor text default public.current_github_login()
);
create index if not exists runs_at_idx on public.runs (at desc);

-- ---------- חתימת שינויים ----------
do $$
declare t text;
begin
  foreach t in array array['courses', 'assignments', 'rubrics', 'submissions', 'stage_instructions', 'settings'] loop
    execute format('drop trigger if exists touch on public.%I', t);
    execute format('create trigger touch before insert or update on public.%I for each row execute function public.touch()', t);
  end loop;
end $$;

-- ---------- הרשאות (Row Level Security) ----------
alter table public.members enable row level security;
drop policy if exists "team reads members" on public.members;
drop policy if exists "admins add members" on public.members;
drop policy if exists "admins edit members" on public.members;
drop policy if exists "admins remove members" on public.members;
create policy "team reads members" on public.members for select to authenticated using (public.is_member());
create policy "admins add members" on public.members for insert to authenticated with check (public.is_admin());
create policy "admins edit members" on public.members for update to authenticated using (public.is_admin()) with check (public.is_admin());
create policy "admins remove members" on public.members for delete to authenticated using (public.is_admin());

do $$
declare t text;
begin
  foreach t in array array['courses', 'assignments', 'rubrics', 'submissions', 'stage_instructions', 'settings', 'runs'] loop
    execute format('alter table public.%I enable row level security', t);
    execute format('drop policy if exists "team reads" on public.%I', t);
    execute format('drop policy if exists "team adds" on public.%I', t);
    execute format('drop policy if exists "team edits" on public.%I', t);
    execute format('drop policy if exists "admins delete" on public.%I', t);
    execute format('create policy "team reads" on public.%I for select to authenticated using (public.is_member())', t);
    execute format('create policy "team adds" on public.%I for insert to authenticated with check (public.is_member())', t);
    execute format('create policy "team edits" on public.%I for update to authenticated using (public.is_member()) with check (public.is_member())', t);
    execute format('create policy "admins delete" on public.%I for delete to authenticated using (public.is_admin())', t);
  end loop;
end $$;

-- ---------- עדכונים חיים: כל שינוי מגיע מיד לכל מי שמחובר ----------
do $$
declare t text;
begin
  foreach t in array array['members', 'courses', 'assignments', 'rubrics', 'submissions', 'stage_instructions', 'settings', 'runs'] loop
    begin
      execute format('alter publication supabase_realtime add table public.%I', t);
    exception when duplicate_object then null;
    end;
  end loop;
end $$;

-- ---------- קבצים: הפתרונות הרשמיים ----------
insert into storage.buckets (id, name, public)
values ('solutions', 'solutions', false)
on conflict (id) do nothing;

drop policy if exists "team reads solutions" on storage.objects;
drop policy if exists "team uploads solutions" on storage.objects;
drop policy if exists "team replaces solutions" on storage.objects;
create policy "team reads solutions" on storage.objects for select to authenticated
  using (bucket_id = 'solutions' and public.is_member());
create policy "team uploads solutions" on storage.objects for insert to authenticated
  with check (bucket_id = 'solutions' and public.is_member());
create policy "team replaces solutions" on storage.objects for update to authenticated
  using (bucket_id = 'solutions' and public.is_member()) with check (bucket_id = 'solutions' and public.is_member());

-- ---------- הצוות ההתחלתי: השותפים בריפו ב-GitHub ----------
-- מצטרפים חדשים מוסיפים מדף "חיבורים והגדרות" באתר (רק מנהל).
insert into public.members (github_username, role) values
  ('matanravitsky-crypto', 'admin'),
  ('ezraariel', 'staff'),
  ('orimes-source', 'staff'),
  ('Shazumi178', 'staff'),
  ('noa-rodnizky', 'staff'),
  ('tikochin', 'staff')
on conflict (github_username) do nothing;
