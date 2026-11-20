# 부자알람 봇 (buza-bot)

투자 정보 요약 텔레그램 봇 — **유튜브 요약 + 미국 상장사 IR 공시/뉴스 종합 + 딥다이브**.

## 기능

```
유튜브
  영상 링크 전송 / /yt <링크>          즉석 요약 (타임스탬프 링크 포함)
  /add <채널URL>                      채널 구독 → 새 영상 자동 요약 푸시
  /list · /remove <번호>              구독 관리

IR 공시 + 뉴스 (미국 상장사, SEC EDGAR + 구글뉴스)
  /ir <티커>                          최근 공시(실적+주요건) 종합 + 분기 재무추이 + 뉴스
  /dd <티커> [경쟁사티커]              딥다이브: 회사개요+밸류에이션(시총·P/S 실계산)+
                                       기술적시그널+뉴스센티먼트+내부자거래+리스크
  /watch <티커> · /unwatch · /watchlist  신규 공시·신규 뉴스 자동 알림 등록/관리
  /report <티커>                      인스타 캐러셀용 8슬라이드 리포트(사업개요·벡터 방향성·
                                       재무제표 표+그래프·밸류에이션·어닝콜 하이라이트·
                                       투자포인트·출처요약). 숫자마다 출처·갱신일 명시

히스토리
  /recap [일수]                       최근 요청 내역 요약 (기본 7일)
```

## 아키텍처

```
[유저] ──DM──▶ [GitHub Actions 크론, 15분마다] run.py
                   │  bot.poll()      유저 명령 1건 처리 (즉시 반환, 롱폴링 아님)
                   │  (6시간마다) engine.refresh·fanout + ir.check_watches
                   │
              [Supabase] users · subscriptions · analyses · deliveries · bot_state(polling offset)
              [로컬 JSON, 매 실행 후 레포에 커밋] ir_state · ir_financials · ir_profile ·
                                                  cik_map · cmd_log · job_state
                   │
   유튜브: RSS 감지 → 자막 → Gemini → 텍스트 요약
   IR:     EDGAR submissions → 공시 본문+EX-99 → Gemini → Pillow 카드(PNG)
   뉴스:   구글뉴스 RSS(영어+스페인어 로케일 병합) — Gemini 미사용, 무료
   밸류에이션: 발행주식수(공시 추출·캐시) × 현재가(Yahoo 비공식 API) — 결정론적, 무료
```

핵심: **분석 1회 → 다수 팬아웃.** 유저가 늘어도 AI 비용은 콘텐츠 양에만 비례.

## 스택
- 인바운드: **GitHub Actions 크론**(15분 간격, `concurrency` 그룹으로 중복실행 방지). 실행마다
  새 컨테이너라 로컬 JSON 상태는 **실행 끝에 레포로 커밋**해 다음 실행이 이어받음(`run.yml` 참고).
  ⚠️ 로컬 PC에서 동시에 폴링 돌리지 말 것(getUpdates offset 충돌).
- DB: Supabase(Postgres, users/subscriptions/analyses/deliveries/polling offset)
- 요약: Gemini 무료 티어 — 모델별 쿼터 분리를 이용한 폴백 체인 (2.5-flash → 2.5-flash-lite → 2.0-flash).
  Grounding(구글서치)은 무료 티어 할당량 0으로 확인 — 자동화된 실시간 웹리서치는 유료 전용.
- IR 데이터: SEC EDGAR API(무료, User-Agent 필수). 10-K/20-F는 inline XBRL 숨김 메타데이터
  스트립 필요(`_strip_html`의 `<ix:header>` 제거).
- 뉴스: 구글뉴스 RSS(무료, Gemini 미사용)
- 가격: Yahoo Finance 비공식 chart API(무료, v7/quoteSummary는 인증 필요해서 막힘 — v8/chart만 사용)
- 카드 렌더: **Pillow 직접 그리기**(`card.py` 빠른카드 1080폭 / `report.py` 인스타 캐러셀 1080x1080 정사각) —
  브라우저 헤드리스 자동화에 의존하지 않음
- 어닝콜: Motley Fool 무료 전문(`requests`로 직결 가능 확인) — 티커→URL은 종목페이지 임베드 JSON에서
  자동탐색(nasdaq/nyse 순 시도), "Welcome to"~"Motley Fool Transcribing" 구간만 추출
- 방향성(벡터): 스칼라 최신값이 아니라 QoQ 변화율+궤적(가속/둔화/방향전환)을 계산 — FY(연간)는
  분기 비교에서 제외(스케일 다름), 차트에는 별도 색으로 함께 표시
- 결제: 텔레그램 Stars (B3, 미착수)

## 단계
- **B1** 멀티유저 구독 + IR/딥다이브/히스토리 ← 지금
- **B2** 온보딩: 관심분야 → 유튜버 검색·추천 (YouTube Data API)
- **B3** 수익화: Stars 구독, 무료/유료 티어 게이팅

## 셋업
1. BotFather로 새 봇 생성 → 토큰
2. Supabase 프로젝트 생성 → `schema.sql` 실행 → URL·service key
3. GitHub repo **Settings → Secrets and variables → Actions**에 등록:
   `TELEGRAM_TOKEN` · `GEMINI_KEY` · `SUPABASE_URL` · `SUPABASE_KEY` · `YT_PROXY`(유튜브 자막,
   GH Actions 데이터센터 IP는 유튜브가 차단해서 레지덴셜 프록시 필수)
4. `.github/workflows/run.yml`의 `schedule` 크론이 활성화돼 있는지 확인 (기본 15분 간격)
5. 로컬 개발 시: `.env.example` → `.env` 복사 후 값 채우기, `pip install -r requirements.txt`

## ⚠️ 법적 유의
남의 영상 요약을 유료 재배포하는 건 회색지대. 매 항목 **원본 링크·시점 표기**(트래픽 환원),
"원본 대체" 아닌 **인사이트 큐레이션·집계**로 포지셔닝, 다국어(한→영)로 시장 분리. 규모 커지면 제휴 고려.
