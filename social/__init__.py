"""소셜 발행 파이프라인 — 콘텐츠 1개 → 플랫폼별 포스트 N개 → Supabase 큐 → 승인 → API 게시.

흐름:  content/*.json  ─adapt─▶  social_posts(status=draft)  ─approve─▶  approved  ─publish─▶  published
                                       │ (텔레그램 OWNER_CHAT 으로 미리보기 전송)
설계 원칙: 생성은 자동, 게시는 사람이 승인한 뒤(유사투자자문 리스크). 네이버 블로그는 초안만(API 없음).
"""
