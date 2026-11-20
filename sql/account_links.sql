-- 텔레그램 ↔ 대시보드 계정 연결 (2026-11-12) — Supabase BUZA_ALARM 프로젝트 SQL Editor 에서 한 번 실행
create table if not exists public.account_links (
  uid text primary key,                 -- user_store._uid(email) 와 같은 sha256 — 이메일 원문은 저장하지 않는다
  code text,                            -- 1회용 연결 코드(30분)
  code_expires timestamptz,
  chat_id bigint,                       -- 연결된 텔레그램 chat
  linked_at timestamptz,
  watch_sync jsonb,                     -- 대시보드 → 봇 감시로 보낼 종목(봇이 처리 후 비움)
  updated_at timestamptz default now()
);
create unique index if not exists account_links_code on public.account_links(code) where code is not null;
alter table public.account_links enable row level security;  -- 정책 없음: service_role 만 읽고 쓴다(portfolios 와 동일)
