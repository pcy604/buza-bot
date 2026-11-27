# 유튜브 쇼츠 자동 업로드 설정 (차니 1회, 약 10분)

1. https://console.cloud.google.com/ → 새 프로젝트 → **YouTube Data API v3** 사용 설정
2. API 및 서비스 → OAuth 동의 화면 → 외부 · 테스트 사용자에 쇼츠 올릴 구글 계정 추가
3. 사용자 인증 정보 → OAuth 클라이언트 ID → **데스크톱 앱** → 클라이언트 ID·보안 비밀 복사
4. https://developers.google.com/oauthplayground → 오른쪽 위 ⚙️ → "Use your own OAuth credentials" 체크 → 3번 값 입력
   → 왼쪽에 `https://www.googleapis.com/auth/youtube.upload` 입력 → Authorize → 계정 선택
   → Exchange authorization code for tokens → **Refresh token** 복사
5. https://github.com/pcy604/buza-bot/settings/secrets/actions → New secret 3개:
   `YT_CLIENT_ID` · `YT_CLIENT_SECRET` · `YT_REFRESH_TOKEN`
⚠️ 동의 화면이 '테스트' 상태면 refresh token 이 7일 뒤 만료된다 → 게시(프로덕션)로 바꾸거나 매주 4번 반복.
