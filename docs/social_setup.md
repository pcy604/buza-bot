# 소셜 API 계정 설정 (2026-11-12 실제 진행 기록)

키·토큰은 `.env`(로컬)와 GitHub repo Settings → Secrets에 **본인이** 넣는다. 채팅에 붙여넣지 않는다.

## 현재 상태 (11-12 저녁)
- Meta 개발자 등록 완료(페이스북 개인 계정 Park Chaneui, 연락 이메일 learner_99@naver.com, 역할 개발자).
- Meta 앱 **stock_studian** 생성: 앱 ID `1568975631932493`, 이용 사례 = Threads API + Instagram API.
- Threads: 권한 threads_basic·threads_content_publish 추가, 콜백 URL 3개 저장, **Threads 테스터 @stock_studian 초대 = 대기 중**.
- Instagram: **보류** — 아래 "Instagram" 참고.
- X: **보류** — 종량제(글 $0.015, URL 포함 글 $0.20). 카드 등록·크레딧 구매가 필요해서 다음에.

## Threads — 남은 3단계
1. **Threads 앱(폰)에서 초대 수락**: 프로필 → 설정 → 계정 → 웹사이트 권한 → 초대 → stock_studian 앱 수락.
2. 개발자 포털 → 앱 stock_studian → 이용 사례 → Threads API 액세스 → **설정** 탭 → 맨 아래 **사용자 토큰 생성기** → stock_studian 행의 **토큰 생성** → 권한 동의 → 토큰 복사.
   - 직접 URL: https://developers.facebook.com/apps/1568975631932493/use_cases/customize/settings/?use_case_enum=THREADS_API&selected_tab=settings&product_route=threads-api
3. `.env`에 `THREADS_TOKEN=<토큰>` 넣고 `python -m social check` → THREADS_USER_ID 값을 알려주면 그것도 `.env`에 추가 → 다시 `check` → OK.
- 토큰은 60일. 만료 전 `python -m social refresh`.

## Instagram — 2026-11 기준 바뀐 것
"Instagram 로그인만으로 되는 API 설정" 탭이 사라지고 **"Unified login"**(권장)과 "Facebook 로그인 포함"(레거시) 둘만 남았다.
- Unified login: **비즈니스 포트폴리오 필요**(무료). business.facebook.com → 비즈니스 포트폴리오 만들기(이름 stock_studian, 본인 이름, 이메일) → 그 뒤 앱의 Instagram 이용 사례 → "API setup with Unified login" → 포트폴리오 연결 → 인스타 계정 연결/테스터 → 토큰.
- Facebook 로그인 포함: 인스타 계정을 **페이스북 페이지에 연결**해야 하고 더 이상 업데이트 안 됨. 비추.
→ 결정: 비즈니스 포트폴리오를 만들면 이어서 진행. 포트폴리오 생성은 계정 생성에 해당해 사용자가 직접 한다.

## X (보류)
- 콘솔: https://console.x.com (계정 stock_studian, 앱 1개 Development 상태로 이미 생성됨).
- 선불 크레딧 종량제. 카드 등록 후 첫 구매 시 $20 무료 크레딧. **자동 충전은 끄고** 소액 수동 구매.
- 키: 콘솔 → 앱 → 권한 Read and Write 로 바꾼 **뒤** Access Token/Secret 생성 → `.env`의 X_ 4개.

## 확인 명령
```
python -m social check                             # 토큰 생존 확인(게시 없음) ← "발행 직전" 기준
python -m social list                              # 큐 상태 (#4 threads, #5 x, #6 instagram = draft)
python -m social approve 4 && python -m social publish 4   # 실제 게시는 사용자 지시 후에만
```

## 안 되는 것
- 네이버 블로그: 공식 API 없음 → `python -m social naver ...` 로 마크다운만 뽑아 수동 게시.
- 유튜브 업로드 API: 미검증 앱은 private 강제 → 수동 업로드.
