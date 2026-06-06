-- RoK KP Dashboard — Supabase schema
-- Run this in the Supabase SQL Editor to initialise (or update) the project.

create table if not exists public.rok_imports (
    id          uuid        primary key,
    filename    text        not null,
    report_date date        not null,
    imported_at timestamptz not null,
    file_hash   text        not null unique,
    row_count   integer     not null
);

create table if not exists public.rok_stats (
    import_id          uuid   not null references public.rok_imports(id) on delete cascade,
    character_id       text   not null,
    username           text   not null,
    power              bigint not null,
    highest_power      bigint not null,
    t5_deaths          bigint not null,
    t4_deaths          bigint not null,
    t3_deaths          bigint not null,
    t2_deaths          bigint not null,
    t1_deaths          bigint not null,
    total_kill_points  bigint not null,
    t5_kills           bigint not null,
    t4_kills           bigint not null,
    t3_kills           bigint not null,
    t2_kills           bigint not null,
    t1_kills           bigint not null,
    resources_gathered bigint not null,
    primary key (import_id, character_id)
);

-- Indexes for fast cross-report and time-series queries
create index if not exists rok_stats_character_id_idx  on public.rok_stats   (character_id);
create index if not exists rok_imports_report_date_idx on public.rok_imports  (report_date desc);
create index if not exists rok_stats_import_id_idx     on public.rok_stats    (import_id);

create table if not exists public.rok_goal_bands (
    band_id     text              primary key,
    label       text              not null,
    min_power   bigint            not null,
    max_power   bigint,
    target_dkpi numeric(10, 6)   not null,
    sort_order  integer           not null,
    updated_at  timestamptz       default now()
);

-- Seed default "Balanceado" preset (upsert — safe to run multiple times)
insert into public.rok_goal_bands
    (band_id, label, min_power, max_power, target_dkpi, sort_order)
values
    ('0_10m',    '0-10M',    0,          10000000, 0.008, 1),
    ('10_30m',   '10M-30M',  10000000,   30000000, 0.012, 2),
    ('30_60m',   '30M-60M',  30000000,   60000000, 0.018, 3),
    ('60_90m',   '60M-90M',  60000000,   90000000, 0.024, 4),
    ('90m_plus', '90M+',     90000000,   null,     0.030, 5)
on conflict (band_id) do update set
    label       = excluded.label,
    min_power   = excluded.min_power,
    max_power   = excluded.max_power,
    target_dkpi = excluded.target_dkpi,
    sort_order  = excluded.sort_order,
    updated_at  = now();
