-- 부자알람 봇 — Supabase(Postgres) 스키마
-- Supabase 대시보드 → SQL Editor 에 붙여넣고 실행.

-- 유저: 텔레그램 chat_id 기준
create table if not exists users (
    chat_id      bigint primary key,
    username     text,
    lang         text default '한국어',          -- 요약 출력 언어
    tier         text default 'free',            -- free | paid
    tier_until   timestamptz,                    -- 유료 만료 시각
    state        text default 'new',             -- 온보딩 상태 (new|onboarding|active)
    created_at   timestamptz default now()
);

-- 구독: 유저가 고른 구루 채널 (다:다)
create table if not exists subscriptions (
    id           bigserial primary key,
    chat_id      bigint references users(chat_id) on delete cascade,
    channel_id   text not null,                  -- 유튜브 채널ID (UC…)
    channel_name text,
    added_at     timestamptz default now(),
    unique (chat_id, channel_id)
);

-- 채널 마스터: 누군가 구독 중인 모든 채널의 합집합 (분석 엔진이 순회)
create table if not exists channels (
    channel_id   text primary key,
    name         text,
    last_checked timestamptz
);

-- 분석 캐시: 영상 1개당 1회만 분석 (핵심 비용 절감 — 유저 수 무관)
create table if not exists analyses (
    video_id     text primary key,
    channel_id   text,
    title        text,
    published    timestamptz,
    analysis     jsonb,                          -- one_liner/summary/tickers/key_points…
    source       text,                           -- transcript | video | fail
    attempts     int default 0,
    created_at   timestamptz default now()
);

-- 발송 기록: 유저에게 이미 보낸 영상 (중복 방지)
create table if not exists deliveries (
    chat_id      bigint,
    video_id     text,
    sent_at      timestamptz default now(),
    primary key (chat_id, video_id)
);

-- 봇 폴링 오프셋 (단일 행)
create table if not exists bot_state (
    id           int primary key default 1,
    tg_offset    bigint default 0
);
insert into bot_state (id, tg_offset) values (1, 0)
on conflict (id) do nothing;

create index if not exists idx_sub_chat    on subscriptions(chat_id);
create index if not exists idx_sub_channel on subscriptions(channel_id);
create index if not exists idx_ana_channel on analyses(channel_id);
