"""코너 선택 회귀 테스트 — 네트워크·LLM 없이 돈다.

    python tests/test_corners.py

실제 RSS 제목만 사용한다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import corners as C

TITLES = [
    "시장의 '뉴노멀'이 바뀐다…고금리·고유가에 맞춰ㅣ명민준, 박가영 [주린이 구조대]",
    "금리인상 사이클, 돈 벌고 빠져나올 타이밍ㅣ명민준 [주린이 구조대]",
    "[26.09.16 오후 방송 전체보기] 국내증시를 사야 할 때? 블랙록의 비중확대!",
    "[9월 16일 마감시황] 예상된 인상보다 동결이 더 위험하다?ㅣ홍선애",
    "금리 불안에 흔들리는 주식시장 ㅣ 박지훈 부장 [아침앤투자]",
    "'하락장 선 넘는 악플' 대처법 | 정프로 & 빈센트 [더블 체크]",
]
ch = C.survey(TITLES)
names = [n for n, _ in ch]
assert '주린이구조대' in names, names
assert ch[0] == ('주린이구조대', 2), ch[0]
assert '오후방송전체보기' in names
print(f'✅ 코너 추출: {len(ch)}종 — {", ".join(names)}')

assert C.worth_choosing(ch), '고를 만한데 아니라고 판정'
assert not C.worth_choosing([('(코너표시 없음)', 17)]), '코너가 없는 채널에 선택지를 띄움'
assert not C.worth_choosing([('주린이구조대', 5)]), '코너 1종인데 선택지를 띄움'
print('✅ 선택 UI 표시 판정: 2종 이상일 때만')

# ── 화이트리스트 동작 ────────────────────────────────────────────────
chosen = {'주린이구조대', '아침앤투자'}
kept = [t for t in TITLES if C.keep(t, chosen)]
assert len(kept) == 3, [t[:30] for t in kept]
assert all('전체보기' not in t for t in kept)
print(f'✅ 화이트리스트: {len(TITLES)}건 → {len(kept)}건')

# 비어 있으면 '전부' — 구독했는데 아무것도 안 오는 상태를 막는다
assert all(C.keep(t, set()) for t in TITLES), '미설정인데 전부 막혔다'
print('✅ 미설정이면 전부 통과(구독 직후 빈 채널 방지)')

# ── 제목 형식이 바뀌면 새 코너로 잡힌다 ──────────────────────────────
# ⚠️ 기준은 '고른 코너'가 아니라 **설정 당시 보였던 코너 전체**여야 한다.
#    chosen 을 기준으로 삼으면 안 고른 코너가 매주 '새 코너'로 올라온다.
seen = set(names)                      # 설정 시점에 보였던 것 전부
added = C.detect_new(seen, TITLES + ['새 코너가 생겼다 [모닝 브리핑]'])
assert [k for k, _ in added] == ['모닝브리핑'], added
assert C.detect_new(seen, TITLES) == [], '변한 게 없는데 알림이 뜸'
assert C.detect_new(set(), TITLES) == [], '미설정인데 변화 알림이 뜸'
# 안 고른 코너는 새 코너가 아니다 — 이게 이번에 고친 버그다.
assert C.detect_new(seen, TITLES) == [], '안 고른 코너가 새 코너로 잡힘'
print(f'✅ 형식 변경 감지: 새 코너 {[k for k, _ in added]} (안 고른 기존 코너는 제외)')

assert C.seen_of({'corners_seen': ['a', 'b'], 'corners': ['a']}) == {'a', 'b'}
assert C.seen_of({'corners': ['a']}) == {'a'}, '옛 레코드 호환 실패'
print('✅ seen/chosen 분리 저장')

# ── 저장 포맷 왕복 ───────────────────────────────────────────────────
assert C.selected_of({'corners': ['a', 'b']}) == {'a', 'b'}
assert C.selected_of({'corners': 'a\x1fb'}) == {'a', 'b'}, '문자열 저장 형식을 못 읽음'
assert C.selected_of({}) == set() and C.selected_of(None) == set()
print('✅ 저장 포맷: 배열·문자열 양쪽 읽기')

print('\n' + C.format_list(ch[:3], chosen))

# ── 코너명이 아닌 대괄호 (2026-10-03 운영에서 발견) ───────────────────
from channels import program as _pg
assert _pg('첫 방송 | 팀 체슬리 [Since 2023.09.18.월]') == '(코너표시 없음)', \
    '채널 개설일 표식이 코너명으로 올라갔다 — 새 코너 알림까지 떴던 건이다'
assert _pg('금융보국의 꿈 [3부]') == '(코너표시 없음)', '편 번호 [3부] 가 코너 "부" 로 잡혔다'
assert _pg('강의 소개 [주식 투자의 정석 : 기초편]') == '주식투자의정석:기초편', '정상 코너가 걸러졌다'
assert _pg('[9월 16일 마감시황] 동결') == '마감시황' and _pg('반도체 [워매신박 / 26.09.16.수]') == '워매신박'
print('✅ 날짜표식·편번호 제외 · 정상 코너 유지')
