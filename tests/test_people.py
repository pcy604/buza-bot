"""인물 추적 회귀 테스트 — 네트워크·LLM 없이 돈다.

    python tests/test_people.py

2026-10-03: 박세익 대표처럼 한 사람이 체슬리TV(본진) 외에 김작가TV·머니인사이드·
한국경제TV 등에 출연하는데, 채널 구독만으로는 본진 것만 받는다.
"""
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import people

people.PEOPLE_PATH = Path(tempfile.mkdtemp()) / 'people_state.json'

# ── 등록·해제 ────────────────────────────────────────────────────────
assert people.add(1, '박세익') and not people.add(1, '박세익'), '중복 등록이 막히지 않음'
assert people.watches_of(1) == ['박세익']
assert people.add(1, '김학균') and people.watches_of(1) == ['박세익', '김학균']
assert people.remove(1, '박세익') and people.watches_of(1) == ['김학균']
assert not people.remove(1, '없는사람'), '없는 이름 해제가 성공으로 보고됨'
assert people.watches_of(999) == [], '등록 안 한 사용자에게 목록이 생김'
print('✅ 등록·중복차단·해제·미등록자 분리')

# ── 동명이인 (실측: '박세익' 검색에 '박세환' 이 섞여 들어왔다) ────────
REAL = [
    {'title': "코스닥 10월부터 대반전! | 박세익 체슬리투자자문 대표", 'channel': '한국경제TV'},
    {'title': "10월부터 주도주 완전히 바뀐다 (박세익 대표)", 'channel': '김작가 TV'},
    {'title': '오늘 장 열리기 전에 봐야 할 총정리 (박세익 전무, 김학균 센터장)', 'channel': '김작가 TV'},
]
FAKE = [
    {'title': '4분기 투자 포트폴리오에 새로 담을 것 (박세환 박사, 소현철 박사)', 'channel': '김작가 TV'},
    {'title': '삼성전자·하이닉스 다음은 소부장? (체슬리 최일호 부사장, 박세환 박사)', 'channel': '김작가 TV'},
]
for v in REAL:
    assert people.is_really('박세익', v), f'본인인데 걸러짐: {v["title"][:30]}'
for v in FAKE:
    assert not people.is_really('박세익', v), f'동명이인인데 통과: {v["title"][:30]}'
print(f'✅ 동명이인: 본인 {len(REAL)}건 통과 · 박세환 {len(FAKE)}건 차단')

# 채널명에만 이름이 있어도 본인으로 본다(제목에 이름을 안 쓰는 채널 대비)
assert people.is_really('체슬리', {'title': '오늘의 시황', 'channel': '체슬리TV'})
print('✅ 채널명에 이름이 있는 경우도 인정')

# ── 재생시간 파싱 ────────────────────────────────────────────────────
assert people._seconds('20:03') == 1203
assert people._seconds('1:12:16') == 4336
assert people._seconds('3:51:46') == 13906
assert people._seconds('') is None and people._seconds('LIVE') is None
print('✅ 재생시간 파싱(mm:ss / h:mm:ss / 없음)')

# ── 파싱 실패와 '결과 0건'은 구분돼야 한다 ──────────────────────────
# 유튜브가 페이지 구조를 바꾸면 둘 다 0건으로 보이는데, 전자는 고장이고 후자는 정상이다.
class _R:
    text = '<html>no data here</html>'
orig = people.__dict__.get('requests')
import types as _t
fake = _t.SimpleNamespace(get=lambda *a, **k: _R())
sys.modules['requests'] = fake
try:
    found, ok = people.find('아무개', 'UA')
    assert found == [] and ok is False, f'파싱 실패를 정상으로 보고: {ok}'
finally:
    del sys.modules['requests']
    import requests  # noqa: F401  — 원복
print('✅ 파싱 실패(ok=False)와 결과 0건(ok=True)을 구분')

# ── 다중 검색어 (2026-10-03) ─────────────────────────────────────────
# '박세익' 19건 vs '체슬리 박세익' 18건인데 겹치는 건 10건뿐이고 새로 8건이 나왔다.
# 유튜브 검색은 조합을 바꾸면 좁혀지는 게 아니라 **다른 그물**이 된다 → 합집합.
people.PEOPLE_PATH.unlink(missing_ok=True)
assert people.add(2, '박세익', '체슬리')
assert people.queries_of(2, '박세익') == ['박세익', '체슬리 박세익']
assert people.watches_of(2) == ['박세익']
assert not people.add(2, '박세익', '체슬리'), '같은 검색어 중복 추가가 통과'
assert people.add(2, '박세익', '워매신박'), '검색어 추가가 막힘'
assert people.queries_of(2, '박세익') == ['박세익', '체슬리 박세익', '워매신박 박세익']
print('✅ 다중 검색어: 소속으로 검색어 추가 · 중복 차단 · 누적')

# 소속은 **판정 조건이 아니다** — 타채널은 소속을 생략한다(실측 8건이 그랬다)
assert people.is_really('박세익', {'title': '(박세익 대표)', 'channel': '김작가 TV'}), \
    '소속이 없다고 본인을 걸렀다 — 타채널 출연이 이 기능의 존재 이유다'
print('✅ 소속 없는 타채널 영상도 본인으로 인정')

# 합집합: 같은 영상이 두 검색어에 다 나와도 한 번만
calls = []
def _fake_find(q, ua):
    calls.append(q)
    return ([{'video_id': 'a', 'title': 'A'}, {'video_id': 'b', 'title': 'B'}] if q == '박세익'
            else [{'video_id': 'b', 'title': 'B'}, {'video_id': 'c', 'title': 'C'}]), True
_orig = people.find
people.find = _fake_find
try:
    got, ok = people.find_many(['박세익', '체슬리 박세익'], 'UA')
finally:
    people.find = _orig
assert [v['video_id'] for v in got] == ['a', 'b', 'c'], got
assert ok and calls == ['박세익', '체슬리 박세익']
print('✅ 합집합: 중복 제거(ab + bc → abc) · 검색어 순서대로 호출')

assert people.remove(2, '박세익') and people.watches_of(2) == []
print('✅ 해제 시 검색어까지 같이 제거')
