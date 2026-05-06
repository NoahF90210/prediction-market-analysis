create extension if not exists pgcrypto;

create schema if not exists market_analysis;

create table if not exists market_analysis.platforms (
    platform text primary key,
    display_name text not null,
    created_at timestamptz not null default now()
);

insert into market_analysis.platforms (platform, display_name)
values
    ('polymarket', 'Polymarket'),
    ('kalshi', 'Kalshi')
on conflict (platform) do update
set display_name = excluded.display_name;

create table if not exists market_analysis.ingestion_runs (
    id uuid primary key default gen_random_uuid(),
    platform text not null references market_analysis.platforms(platform),
    run_type text not null,
    status text not null default 'started',
    cursor text,
    page_count integer not null default 0,
    inserted_count integer not null default 0,
    updated_count integer not null default 0,
    failure_text text,
    metadata jsonb not null default '{}'::jsonb,
    started_at timestamptz not null default now(),
    finished_at timestamptz
);

create table if not exists market_analysis.raw_markets (
    id bigint generated always as identity primary key,
    platform text not null references market_analysis.platforms(platform),
    source_market_id text not null,
    source_event_id text,
    event_title text,
    title text not null,
    slug text,
    raw_platform_category text,
    raw_tags jsonb not null default '[]'::jsonb,
    series_ticker text,
    event_ticker text,
    subtitle text,
    rules_primary text,
    open_time timestamptz,
    close_time timestamptz,
    resolved_at timestamptz generated always as (coalesce(close_time, open_time)) stored,
    resolution text,
    forecast_prob numeric,
    forecast_source text,
    volume numeric,
    source_url text,
    raw_payload jsonb not null default '{}'::jsonb,
    ingested_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (platform, source_market_id)
);

create table if not exists market_analysis.raw_market_tags (
    id bigint generated always as identity primary key,
    platform text not null,
    source_market_id text not null,
    tag_slug text,
    tag_label text,
    tag_position integer,
    created_at timestamptz not null default now()
);

create unique index if not exists raw_market_tags_unique_idx
    on market_analysis.raw_market_tags (
        platform,
        source_market_id,
        coalesce(tag_slug, ''),
        coalesce(tag_label, ''),
        coalesce(tag_position, -1)
    );

create table if not exists market_analysis.market_history_points (
    id bigint generated always as identity primary key,
    platform text not null,
    source_market_id text not null,
    observed_at timestamptz,
    yes_price numeric,
    payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (platform, source_market_id, observed_at)
);

create table if not exists market_analysis.category_overrides (
    id bigint generated always as identity primary key,
    platform text not null,
    match_field text not null,
    match_type text not null,
    match_value text not null,
    canonical_category text not null,
    confidence numeric not null default 1.0,
    reason text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists market_analysis.normalized_markets (
    id bigint generated always as identity primary key,
    platform text not null,
    source_market_id text not null,
    source_event_id text,
    title text not null,
    slug text,
    category text not null,
    canonical_category text not null,
    category_source text not null,
    category_confidence numeric not null default 0,
    needs_review boolean not null default true,
    review_reason text,
    raw_platform_category text,
    raw_tags jsonb not null default '[]'::jsonb,
    resolution text,
    forecast_prob numeric,
    forecast_source text,
    volume numeric,
    meets_volume_threshold boolean not null default false,
    include_in_analysis boolean not null default false,
    analysis_ready boolean not null default false,
    exclude_reason text not null default '',
    is_cross_platform_comparable boolean not null default false,
    normalized_at timestamptz not null default now(),
    unique (platform, source_market_id)
);

create table if not exists market_analysis.scored_markets (
    id bigint generated always as identity primary key,
    platform text not null,
    source_market_id text not null,
    category text not null,
    forecast_prob numeric not null,
    forecast_source text,
    resolution text not null,
    outcome integer not null,
    brier numeric not null,
    log_loss numeric not null,
    open_time timestamptz,
    close_time timestamptz,
    volume numeric,
    duration_bucket text,
    volume_bucket text,
    scored_at timestamptz not null default now(),
    unique (platform, source_market_id)
);

create or replace view market_analysis.analysis_ready_summary as
select
    platform,
    category,
    count(*) as markets,
    avg(brier) as avg_brier,
    avg(log_loss) as avg_log_loss,
    avg(volume) as avg_volume
from market_analysis.scored_markets
group by platform, category;

create or replace view market_analysis.market_coverage_summary as
select
    platform,
    count(*) as captured_markets,
    count(*) filter (where include_in_analysis) as reviewed_markets,
    count(*) filter (where analysis_ready) as analysis_ready_markets,
    count(*) filter (where not meets_volume_threshold) as below_threshold_markets,
    count(*) filter (where needs_review) as review_flagged_markets
from market_analysis.normalized_markets
group by platform;
