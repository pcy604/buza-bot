# 텔레그램 즉시 응답 세팅 (10분)

## 왜

GitHub Actions `schedule` 크론은 무료 티어에서 심하게 지연된다. 2026-07-26 실측:

| 설정 | 실제 간격 |
|---|---|
| `4,19,34,49 * * * *` (15분) | 62분 · 71분 · 105분 · 68분 · 95분 |

코드로 못 고친다(플랫폼 한계). 대신 **텔레그램 → Cloudflare Worker → GitHub
`repository_dispatch`** 경로를 만들면 명령이 **수초 내에** Actions를 깨운다.
크론은 주기작업(영상갱신·IR감시) 전용으로 남긴다.

```
지금:  /report → (크론 대기 60~105분) → 생성 3~4분 → 도착
이후:  /report → 즉시 "접수" → Actions 수초 내 시작 → 생성 3~4분 → 도착
```

## 준비물

- Cloudflare 계정 (무료, **카드 불필요**)
- GitHub Fine-grained PAT

## 1. GitHub 토큰 발급

<https://github.com/settings/personal-access-tokens/new>

- Repository access → **Only select repositories** → `buza-bot`
- Permissions → Repository permissions → **Contents: Read and write**
- 만료일 설정 후 생성 → `github_pat_...` 복사

> `repository_dispatch`는 Contents 쓰기 권한이 필요하다.

## 2. Cloudflare Worker 생성

1. <https://dash.cloudflare.com> → Workers & Pages → **Create** → Worker
2. 이름 예: `buza-webhook` → Deploy
3. **Edit code** → 기존 내용 지우고 [`worker.js`](worker.js) 전체 붙여넣기 → Deploy
4. Settings → **Variables and Secrets** → 아래 4개를 **Secret** 타입으로 추가

   | 이름 | 값 |
   |---|---|
   | `TELEGRAM_TOKEN` | 봇 토큰 |
   | `GH_TOKEN` | 1단계에서 만든 `github_pat_...` |
   | `GH_REPO` | `pcy604/buza-bot` |
   | `WEBHOOK_SECRET` | 아무 문자열 (예: `buza-9f2k3x`) |

5. Worker URL 복사 (`https://buza-webhook.<계정>.workers.dev`)

## 3. GitHub 변수 등록

레포 → Settings → Secrets and variables → Actions → **Variables** 탭 →
New repository variable

- 이름 `USE_WEBHOOK`, 값 `true`

> 이걸 켜면 크론 실행이 `getUpdates` 폴링을 멈춘다.
> 웹훅이 걸린 상태에서 폴링하면 텔레그램이 409를 낸다.

## 4. 텔레그램 웹훅 등록

브라우저 주소창에 아래를 채워 넣고 실행 (`<>` 부분 교체):

```
https://api.telegram.org/bot<봇토큰>/setWebhook?url=<Worker URL>&secret_token=<WEBHOOK_SECRET>&allowed_updates=["message"]
```

`{"ok":true,"result":true,...}` 가 나오면 성공.

확인:

```
https://api.telegram.org/bot<봇토큰>/getWebhookInfo
```

`"pending_update_count":0` 이고 `"last_error_message"` 가 없어야 정상.

## 5. 테스트

텔레그램에서 `/report SATL` → **즉시** "리포트 생성 시작했어요" 가 오면 성공.
Actions 탭에 `repository_dispatch` 실행이 바로 뜬다.

## 되돌리기

```
https://api.telegram.org/bot<봇토큰>/deleteWebhook
```

그리고 GitHub Variables에서 `USE_WEBHOOK` 을 `false` 로. 즉시 기존 폴링 방식으로 돌아간다.

## 비용

- Cloudflare Workers 무료: 100,000 요청/일 — 개인 봇은 근처도 못 감
- GitHub Actions: private 레포 무료 2,000분/월. 웹훅 전환 시 **오히려 절약**된다
  (빈 크론 실행이 줄고, 명령이 있을 때만 무거운 작업이 돎)
