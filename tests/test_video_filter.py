"""합본(전체방송) 건너뛰기 회귀 테스트 — 네트워크·LLM 없이 돈다.

    python tests/test_video_filter.py

2026-09-17 실측(분석 257건): 합본은 전체의 6%인데 실패의 31%를 차지했고,
실패율은 31% vs 나머지 4%로 8배였다. 원인은 대부분 토큰 한도 초과다.
가장 비싸고 가장 자주 실패하는데 내용은 짧은 클립들과 중복이었다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import analyzer as A

F = A.FULL_BROADCAST
# 실제 RSS에서 가져온 제목만 쓴다.
FULL = ['[26.09.16 오후 방송 전체보기] 국내증시를 사야 할 때? 블랙록의 비중확대!',
        '[26.09.08 오후 방송 전체보기] 약속의 두 시, 맴도는 골드만삭스의 예언',
        '매일 아침 펀드매니저들의 운용회의 라이브 | 박세익 전무 [모닝브리프 / 26.09.16.수]']
CLIP = ['반도체에서 빠진 돈이 의외의 섹터로 몰렸다ㅣ체슬리투자자문 박세익 전무 [워매신박]',
        '[9월 16일 마감시황] 예상된 인상보다 동결이 더 위험하다?',
        '모두 방어주로 옮겼다면 바로 그때가 바닥일 수 있다 | 박세익 전무 [모닝브리프]',
        '금리 불안에 흔들리는 주식시장, 결국 반도체가 답이다? ㅣ 박지훈 부장 [아침앤투자]']
for t in FULL:
    assert F.search(t), f'합본인데 못 잡음: {t}'
for t in CLIP:
    assert not F.search(t), f'클립인데 합본으로 잡힘: {t}'
print(f'✅ 합본 {len(FULL)}건 판별 · 클립 {len(CLIP)}건 통과')

# ── 조건부 동작: 클립이 있을 때만 건너뛴다 ──────────────────────────
import xml.etree.ElementTree as ET
from datetime import datetime, timezone


def _feed(titles):
    now = datetime.now(timezone.utc).isoformat()
    items = ''.join(
        f'<entry><yt:videoId>v{i}</yt:videoId><title>{t}</title>'
        f'<published>{now}</published></entry>' for i, t in enumerate(titles))
    return (f'<feed xmlns="http://www.w3.org/2005/Atom" '
            f'xmlns:yt="http://www.youtube.com/xml/schemas/2015">{items}</feed>').encode()


class _R:
    def __init__(self, c): self.content = c


def run(titles):
    orig = A.requests.get
    A.requests.get = lambda *a, **k: _R(_feed(titles))
    try:
        return [v['title'] for v in A.fetch_recent_videos('UC_test', 'TEST')]
    finally:
        A.requests.get = orig


mixed = run([FULL[0], CLIP[0], CLIP[1]])
assert FULL[0] not in mixed and len(mixed) == 2, f'클립이 있는데 합본이 남음: {mixed}'
print('✅ 클립이 있으면 합본만 빠진다')

only_full = run([FULL[0], FULL[2]])
assert len(only_full) == 2, f'합본뿐인데 통째로 비었다: {only_full}'
print('✅ 합본뿐이면 그대로 처리한다(채널이 통째로 비지 않게)')

# '다시보기'는 무조건 차단에서 조건부로 옮겼다 — 그것만 있으면 살아남아야 한다.
only_replay = run(['[다시보기] 9월 16일 마감시황'])
assert len(only_replay) == 1, '다시보기만 있는 채널이 통째로 비었다'
print('✅ 다시보기 단독이면 살아남는다(예전엔 무조건 버려졌다)')

# 쇼츠·예고는 여전히 무조건 제외
assert run(['#shorts 짧은영상', CLIP[0]]) == [CLIP[0]], '쇼츠가 안 걸러짐'
assert run(['[예고] 내일 방송', CLIP[0]]) == [CLIP[0]], '예고가 안 걸러짐'
print('✅ 쇼츠·예고는 여전히 무조건 제외')
