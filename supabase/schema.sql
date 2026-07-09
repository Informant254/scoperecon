-- ScopeRecon: Bug Bounty Recon Dashboard
-- Run in Supabase SQL Editor. Enable: Auth (email), Realtime optional.

create extension if not exists "pgcrypto";
create extension if not exists "uuid-ossp";

-- ---------------------------------------------------------------------------
-- Enums
-- ---------------------------------------------------------------------------
create type public.plan_tier as enum ('free', 'pro', 'team');
create type public.subscription_status as enum (
  'none', 'trialing', 'active', 'past_due', 'canceled', 'incomplete', 'unpaid'
);
create type public.asset_type as enum (
  'domain', 'subdomain', 'ip', 'url', 'api', 'mobile', 'cloud', 'other'
);
create type public.severity_status as enum (
  'queued', 'running', 'completed', 'failed', 'canceled'
);
create type public.finding_severity as enum (
  'info', 'low', 'medium', 'high', 'critical'
);
create type public.finding_status as enum (
  'new', 'triaged', 'reported', 'duplicate', 'resolved', 'ignored'
);

-- ---------------------------------------------------------------------------
-- Profiles (1:1 with auth.users)
-- ---------------------------------------------------------------------------
create table public.profiles (
  id uuid primary key references auth.users (id) on delete cascade,
  email text not null,
  full_name text,
  company text,
  plan public.plan_tier not null default 'free',
  stripe_customer_id text unique,
  stripe_subscription_id text unique,
  subscription_status public.subscription_status not null default 'none',
  current_period_end timestamptz,
  scan_quota_monthly int not null default 5,
  scans_used_this_month int not null default 0,
  quota_reset_at timestamptz not null default (date_trunc('month', now()) + interval '1 month'),
  api_key_hash text,
  api_key_prefix text,
  api_key_created_at timestamptz,
  onboarding_completed boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint profiles_email_format check (email ~* '^[^@]+@[^@]+\.[^@]+$'),
  constraint profiles_quota_nonneg check (scan_quota_monthly >= 0 and scans_used_this_month >= 0)
);

create index profiles_stripe_customer_idx on public.profiles (stripe_customer_id)
  where stripe_customer_id is not null;
create index profiles_plan_idx on public.profiles (plan);

-- ---------------------------------------------------------------------------
-- Programs (bug bounty programs / scopes)
-- ---------------------------------------------------------------------------
create table public.programs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  name text not null,
  platform text, -- hackerone, bugcrowd, intigriti, yeswehack, private
  program_url text,
  handle text,
  notes text,
  is_active boolean not null default true,
  in_scope_summary text,
  out_of_scope_summary text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint programs_name_len check (char_length(name) between 1 and 200)
);

create index programs_user_id_idx on public.programs (user_id);
create index programs_user_active_idx on public.programs (user_id, is_active);

-- ---------------------------------------------------------------------------
-- Assets
-- ---------------------------------------------------------------------------
create table public.assets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  program_id uuid not null references public.programs (id) on delete cascade,
  asset_type public.asset_type not null default 'domain',
  value text not null,
  is_in_scope boolean not null default true,
  tags text[] not null default '{}',
  tech_stack jsonb not null default '[]'::jsonb,
  last_seen_at timestamptz,
  first_seen_at timestamptz not null default now(),
  risk_score numeric(5,2) not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint assets_value_len check (char_length(value) between 1 and 2048),
  constraint assets_risk_range check (risk_score >= 0 and risk_score <= 100),
  constraint assets_unique_per_program unique (program_id, value)
);

create index assets_user_id_idx on public.assets (user_id);
create index assets_program_id_idx on public.assets (program_id);
create index assets_value_trgm_idx on public.assets (value);
create index assets_risk_idx on public.assets (user_id, risk_score desc);

-- ---------------------------------------------------------------------------
-- Scans
-- ---------------------------------------------------------------------------
create table public.scans (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  program_id uuid not null references public.programs (id) on delete cascade,
  status public.scan_status not null default 'queued',
  scan_type text not null default 'passive_recon',
  target_seed text not null,
  config jsonb not null default '{}'::jsonb,
  progress int not null default 0,
  error_message text,
  assets_discovered int not null default 0,
  findings_count int not null default 0,
  started_at timestamptz,
  finished_at timestamptz,
  idempotency_key text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint scans_progress_range check (progress >= 0 and progress <= 100),
  constraint scans_idempotency_unique unique (user_id, idempotency_key)
);

create index scans_user_id_idx on public.scans (user_id);
create index scans_status_idx on public.scans (status) where status in ('queued', 'running');
create index scans_program_id_idx on public.scans (program_id);

-- ---------------------------------------------------------------------------
-- Findings
-- ---------------------------------------------------------------------------
create table public.findings (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  program_id uuid not null references public.programs (id) on delete cascade,
  asset_id uuid references public.assets (id) on delete set null,
  scan_id uuid references public.scans (id) on delete set null,
  title text not null,
  description text,
  severity public.finding_severity not null default 'info',
  status public.finding_status not null default 'new',
  category text, -- open_port, takeover, exposed_panel, tech, dns, other
  evidence jsonb not null default '{}'::jsonb,
  cvss numeric(3,1),
  bounty_estimate_usd numeric(12,2),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint findings_title_len check (char_length(title) between 1 and 300)
);

create index findings_user_id_idx on public.findings (user_id);
create index findings_program_id_idx on public.findings (program_id);
create index findings_severity_idx on public.findings (user_id, severity);
create index findings_status_idx on public.findings (user_id, status);

-- ---------------------------------------------------------------------------
-- Stripe webhook events (idempotency + audit)
-- ---------------------------------------------------------------------------
create table public.stripe_events (
  id text primary key, -- evt_...
  type text not null,
  api_version text,
  livemode boolean not null default false,
  payload jsonb not null,
  processed_at timestamptz,
  process_error text,
  created_at timestamptz not null default now()
);

create index stripe_events_type_idx on public.stripe_events (type);
create index stripe_events_unprocessed_idx on public.stripe_events (created_at)
  where processed_at is null;

-- ---------------------------------------------------------------------------
-- Checkout sessions (server-side verification trail)
-- ---------------------------------------------------------------------------
create table public.checkout_sessions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references public.profiles (id) on delete cascade,
  stripe_session_id text unique not null,
  price_id text not null,
  plan public.plan_tier not null,
  status text not null default 'created', -- created, completed, expired
  amount_total int,
  currency text,
  created_at timestamptz not null default now(),
  completed_at timestamptz
);

create index checkout_sessions_user_idx on public.checkout_sessions (user_id);

-- ---------------------------------------------------------------------------
-- Rate limit buckets (API abuse protection)
-- ---------------------------------------------------------------------------
create table public.rate_limits (
  bucket_key text primary key,
  window_start timestamptz not null,
  request_count int not null default 0,
  updated_at timestamptz not null default now()
);

-- ---------------------------------------------------------------------------
-- Audit log
-- ---------------------------------------------------------------------------
create table public.audit_log (
  id bigserial primary key,
  user_id uuid references public.profiles (id) on delete set null,
  action text not null,
  resource_type text,
  resource_id text,
  ip_hash text,
  meta jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create index audit_log_user_idx on public.audit_log (user_id, created_at desc);

-- ---------------------------------------------------------------------------
-- updated_at trigger
-- ---------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger profiles_updated_at before update on public.profiles
  for each row execute function public.set_updated_at();
create trigger programs_updated_at before update on public.programs
  for each row execute function public.set_updated_at();
create trigger assets_updated_at before update on public.assets
  for each row execute function public.set_updated_at();
create trigger scans_updated_at before update on public.scans
  for each row execute function public.set_updated_at();
create trigger findings_updated_at before update on public.findings
  for each row execute function public.set_updated_at();

-- ---------------------------------------------------------------------------
-- Auth: create profile on signup
-- ---------------------------------------------------------------------------
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email, full_name)
  values (
    new.id,
    coalesce(new.email, ''),
    coalesce(new.raw_user_meta_data->>'full_name', null)
  );
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- ---------------------------------------------------------------------------
-- Plan quota helpers (SECURITY DEFINER — only called from trusted paths)
-- ---------------------------------------------------------------------------
create or replace function public.plan_scan_quota(p public.plan_tier)
returns int
language sql
immutable
as $$
  select case p
    when 'free' then 5
    when 'pro' then 200
    when 'team' then 1000
    else 5
  end;
$$;

create or replace function public.reset_quota_if_needed(p_user_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  r public.profiles%rowtype;
begin
  select * into r from public.profiles where id = p_user_id for update;
  if not found then
    return;
  end if;
  if r.quota_reset_at <= now() then
    update public.profiles
    set
      scans_used_this_month = 0,
      quota_reset_at = date_trunc('month', now()) + interval '1 month',
      scan_quota_monthly = public.plan_scan_quota(plan)
    where id = p_user_id;
  end if;
end;
$$;

create or replace function public.consume_scan_quota(p_user_id uuid)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  r public.profiles%rowtype;
begin
  perform public.reset_quota_if_needed(p_user_id);
  select * into r from public.profiles where id = p_user_id for update;
  if not found then
    return false;
  end if;
  if r.scans_used_this_month >= r.scan_quota_monthly then
    return false;
  end if;
  update public.profiles
  set scans_used_this_month = scans_used_this_month + 1
  where id = p_user_id;
  return true;
end;
$$;

-- Only service_role / backend should call consume_scan_quota
revoke all on function public.consume_scan_quota(uuid) from public;
revoke all on function public.reset_quota_if_needed(uuid) from public;
grant execute on function public.consume_scan_quota(uuid) to service_role;
grant execute on function public.reset_quota_if_needed(uuid) to service_role;

-- ---------------------------------------------------------------------------
-- Apply plan from Stripe (service_role only)
-- ---------------------------------------------------------------------------
create or replace function public.apply_subscription(
  p_user_id uuid,
  p_plan public.plan_tier,
  p_status public.subscription_status,
  p_stripe_customer_id text,
  p_stripe_subscription_id text,
  p_period_end timestamptz
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.profiles
  set
    plan = p_plan,
    subscription_status = p_status,
    stripe_customer_id = coalesce(p_stripe_customer_id, stripe_customer_id),
    stripe_subscription_id = p_stripe_subscription_id,
    current_period_end = p_period_end,
    scan_quota_monthly = public.plan_scan_quota(p_plan),
    updated_at = now()
  where id = p_user_id;
end;
$$;

revoke all on function public.apply_subscription(uuid, public.plan_tier, public.subscription_status, text, text, timestamptz) from public;
grant execute on function public.apply_subscription(uuid, public.plan_tier, public.subscription_status, text, text, timestamptz) to service_role;

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
alter table public.profiles enable row level security;
alter table public.programs enable row level security;
alter table public.assets enable row level security;
alter table public.scans enable row level security;
alter table public.findings enable row level security;
alter table public.stripe_events enable row level security;
alter table public.checkout_sessions enable row level security;
alter table public.rate_limits enable row level security;
alter table public.audit_log enable row level security;

-- Profiles: users read/update self only (no plan/stripe fields via client — enforced by column grants + trigger)
create policy profiles_select_own on public.profiles
  for select using (auth.uid() = id);

create policy profiles_update_own_safe on public.profiles
  for update
  using (auth.uid() = id)
  with check (auth.uid() = id);

-- Block clients from self-upgrading plan / forging Stripe IDs
create or replace function public.protect_billing_fields()
returns trigger
language plpgsql
as $$
begin
  if auth.role() = 'authenticated' then
    new.plan := old.plan;
    new.stripe_customer_id := old.stripe_customer_id;
    new.stripe_subscription_id := old.stripe_subscription_id;
    new.subscription_status := old.subscription_status;
    new.current_period_end := old.current_period_end;
    new.scan_quota_monthly := old.scan_quota_monthly;
    new.scans_used_this_month := old.scans_used_this_month;
    new.quota_reset_at := old.quota_reset_at;
    new.api_key_hash := old.api_key_hash;
    new.api_key_prefix := old.api_key_prefix;
    new.api_key_created_at := old.api_key_created_at;
  end if;
  return new;
end;
$$;

create trigger profiles_protect_billing
  before update on public.profiles
  for each row execute function public.protect_billing_fields();

-- Programs
create policy programs_select_own on public.programs
  for select using (auth.uid() = user_id);
create policy programs_insert_own on public.programs
  for insert with check (auth.uid() = user_id);
create policy programs_update_own on public.programs
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy programs_delete_own on public.programs
  for delete using (auth.uid() = user_id);

-- Assets
create policy assets_select_own on public.assets
  for select using (auth.uid() = user_id);
create policy assets_insert_own on public.assets
  for insert with check (auth.uid() = user_id);
create policy assets_update_own on public.assets
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy assets_delete_own on public.assets
  for delete using (auth.uid() = user_id);

-- Scans: clients can insert queued only; status transitions server-side (service_role)
create policy scans_select_own on public.scans
  for select using (auth.uid() = user_id);
create policy scans_insert_own on public.scans
  for insert with check (
    auth.uid() = user_id
    and status = 'queued'
    and progress = 0
  );
create policy scans_update_own_meta on public.scans
  for update using (auth.uid() = user_id)
  with check (auth.uid() = user_id and status = 'canceled'); -- user may cancel only

-- Findings: read/update status; inserts primarily from service_role
create policy findings_select_own on public.findings
  for select using (auth.uid() = user_id);
create policy findings_update_own on public.findings
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy findings_insert_own on public.findings
  for insert with check (auth.uid() = user_id);

-- Stripe / rate / audit: no client access
create policy stripe_events_deny_all on public.stripe_events
  for all using (false);
create policy checkout_select_own on public.checkout_sessions
  for select using (auth.uid() = user_id);
create policy rate_limits_deny_all on public.rate_limits
  for all using (false);
create policy audit_select_own on public.audit_log
  for select using (auth.uid() = user_id);

-- service_role bypasses RLS by default in Supabase

-- ---------------------------------------------------------------------------
-- Hardening: limit what authenticated role can do on sensitive tables
-- ---------------------------------------------------------------------------
revoke all on public.stripe_events from authenticated, anon;
revoke all on public.rate_limits from authenticated, anon;
revoke insert, update, delete on public.checkout_sessions from authenticated, anon;
grant select on public.checkout_sessions to authenticated;

grant select, update on public.profiles to authenticated;
grant select, insert, update, delete on public.programs to authenticated;
grant select, insert, update, delete on public.assets to authenticated;
grant select, insert, update on public.scans to authenticated;
grant select, insert, update on public.findings to authenticated;
grant select on public.audit_log to authenticated;
