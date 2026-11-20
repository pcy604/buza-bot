-- 소셜 발행 큐 + 이미지 공개 버킷 (2026-11-12). Supabase SQL Editor 또는 MCP apply_migration 으로 1회 실행.
create table if not exists social_posts (
  id            bigserial primary key,
  content_slug  text not null,
  platform      text not null check (platform in ('threads','x','instagram','naver')),
  payload       jsonb not null,            -- {texts:[], images:[], note}
  status        text not null default 'draft' check (status in ('draft','approved','published','failed')),
  external_id   text,                      -- 게시 후 플랫폼 ID
  error         text,
  created_at    timestamptz default now(),
  published_at  timestamptz
);
create index if not exists social_posts_status on social_posts(status);
insert into storage.buckets (id, name, public) values ('social','social', true) on conflict (id) do nothing;
