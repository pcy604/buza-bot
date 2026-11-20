"""감시 뉴스 푸시 회귀 테스트 — 네트워크·LLM 없이 돈다.

    python tests/test_news_push.py

2026-09-21: /ir 카드에는 뉴스 요약을 붙였는데 **감시 푸시 경로는 링크 그대로**였다.
사건 6건이면 알림이 6번 울리고 뭐가 중요한지는 사용자가 골라야 했다.
"""
import sys
from pathlib import Path

ROOT_GUARD = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_GUARD))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
import ir
import tempfile
import tg

# ⚠️ **맨 앞에서** 로그 경로를 임시 폴더로 돌린다. 2026-09-22 에 이걸 테스트 중간에서
#    했다가, 그 앞의 send_ir_news 호출들이 **운영 news_log.json 에 그대로 기록**됐고
#    러너가 그 파일을 커밋해 14건이 운영 집계에 섞였다. 테스트가 운영 지표를 오염시키면
#    그 지표를 믿을 수 없게 된다.
ir.NEWS_LOG_PATH = pathlib_tmp = __import__('pathlib').Path(tempfile.mkdtemp()) / 'news_log.json'

SENT = []
tg.send_message = lambda c, t, **k: (SENT.append(t), True)[1]
import bot

EVENTS = [
    {'title': 'Satellogic Expands Slingshot III Work', 'link': 'https://x/1',
     'source': 'GlobeNewswire', 'date': '2026-09-20', 'echo': 3},
    {'title': 'Q3 guidance raised & margins improve <10%', 'link': 'https://x/2',
     'source': 'Reuters', 'date': '2026-09-20', 'echo': 1},
]
DIGEST = [{'headline': '해군 감시 사업 확대', 'so_what': '단발 계약이 반복 매출로 바뀔 신호', 'date': '2026-09-20'}]

# ── 요약이 있을 때: 한 메시지, 요약이 위 ──────────────────────────────
SENT.clear()
assert bot.send_ir_news(1, 'SATL', EVENTS, DIGEST)
assert len(SENT) == 1, f'메시지가 {len(SENT)}개로 쪼개짐 — 한 번에 보내야 한다'
m = SENT[0]
assert '해군 감시 사업 확대' in m and '반복 매출' in m, '요약이 안 들어감'
assert 'https://x/1' in m and 'https://x/2' in m, '원문 링크가 빠짐'
assert m.index('해군 감시') < m.index('원문'), '요약이 링크보다 아래에 있음'
assert '매체 3곳' in m, 'echo 표시가 빠짐'
print('✅ 요약 있음: 1개 메시지 · 요약 먼저 · 링크·echo 유지')

# ── HTML 깨짐 방지: 제목의 &·< 가 그대로 나가면 텔레그램이 400 을 낸다 ──
assert '&amp;' in m and '&lt;10%' in m, f'HTML 이스케이프 안 됨'
assert '<a href=' in m and '<b>' in m, '의도한 태그까지 이스케이프됨'
print('✅ 제목의 &·< 이스케이프 (메시지 전체 발송 실패 방지)')

# ── 요약 실패(None): 링크는 살리고, 왜 없는지 밝힌다 ──────────────────
SENT.clear()
bot.send_ir_news(1, 'SATL', EVENTS, None)
m2 = SENT[0]
assert 'https://x/1' in m2, '요약 실패했다고 뉴스까지 사라짐'
assert '요약을 못' in m2, '요약이 없는 이유를 안 밝힘'
print('✅ 요약 실패: 링크 보존 + 사유 표기')

# ── 요약이 빈 배열(추릴 게 없음)이면 사유 문구 없이 링크만 ────────────
SENT.clear()
bot.send_ir_news(1, 'SATL', EVENTS, [])
assert '요약을 못' not in SENT[0], '빈 요약을 실패로 표기함'
print('✅ 추릴 게 없을 때와 실패를 구분')

# ── 옛 호출부(단건 dict) 호환 ────────────────────────────────────────
SENT.clear()
assert bot.send_ir_news(1, 'SATL', EVENTS[0])
assert len(SENT) == 1 and 'https://x/1' in SENT[0]
print('✅ 단건 dict 로 불러도 동작(옛 호출부 호환)')

# ── 사건 0건이면 아무것도 안 보낸다 ──────────────────────────────────
SENT.clear()
assert bot.send_ir_news(1, 'SATL', [], None) is False and not SENT
print('✅ 신규 0건이면 발송 안 함')

# ── 길이 한도: 구글 뉴스 링크가 길어 메시지가 통째로 반려되는 걸 막는다 ──
# 실측 구글 뉴스 링크는 300~350자다. 한도(3800)에 닿으려면 그보다 길어야 하므로
# 700자로 잡는다 — 6건 캡 안에서도 잘리는 상황을 강제한다.
LONG = 'https://news.google.com/rss/articles/' + 'A' * 700
many = [{'title': f'사건 {i}', 'link': f'{LONG}{i}', 'source': 'X', 'date': '2026-09-20'}
        for i in range(8)]
SENT.clear()
bot.send_ir_news(1, 'SATL', many, DIGEST)
m3 = SENT[0]
assert len(m3) <= 4096, f'텔레그램 한도 초과: {len(m3)}자'
assert '해군 감시 사업 확대' in m3, '길이 줄이면서 요약을 버렸다'
assert '외 ' in m3, f'생략된 건수를 안 알림'
print(f'✅ 길이 한도: {len(m3)}자 · 요약 보존 · 생략 건수 표기')

# 실측 길이(약 350자 링크 6건)에서는 잘리지 않아야 한다 — 과하게 자르면 정보가 준다.
real = [{'title': f'사건 {i}', 'link': 'https://news.google.com/rss/articles/' + 'A' * 320,
         'source': 'X', 'date': '2026-09-20'} for i in range(6)]
SENT.clear()
bot.send_ir_news(1, 'SATL', real, DIGEST)
assert '외 ' not in SENT[0], '실측 길이인데 링크를 잘랐다'
print(f'✅ 실측 길이({len(SENT[0])}자)에서는 6건 전부 유지')

# ── 계측: 요약이 나갔는지 / 폴백이었는지 / 못 갔는지 구분되는가 ──────
# 2026-09-22 자가점검에서 이 기능만 기록이 없어 "경로는 돌았는데 결과는 모름"이었다.
# 앞 단계 호출도 같은 로그에 쌓이므로 여기서 비우고 이 섹션 것만 센다.
ir.NEWS_LOG_PATH.unlink(missing_ok=True)
SENT.clear()
bot.send_ir_news(1, 'SATL', EVENTS, DIGEST)          # 요약 발송
bot.send_ir_news(1, 'SATL', EVENTS, None)            # 폴백 발송
tg.send_message = lambda c, t, **k: False            # 발송 실패 상황
bot.send_ir_news(1, 'SATL', EVENTS, DIGEST)
tg.send_message = lambda c, t, **k: (SENT.append(t), True)[1]

assert not ir.NEWS_LOG_PATH.is_relative_to(ROOT_GUARD), '운영 로그에 쓰고 있다'
recs = ir.news_log(1)
sends = [r for r in recs if r.get('stage') == 'send']
assert len(sends) == 3, f'발송 기록 {len(sends)}건 (3이어야)'
assert sends[0]['sent'] and not sends[0]['fallback'], '요약 발송이 폴백으로 기록됨'
assert sends[1]['fallback'], '폴백인데 기록 안 됨'
assert sends[2]['sent'] is False, '발송 실패가 성공으로 기록됨'
assert all('chars' in r and 'digest' in r for r in sends), '길이·요약수가 안 남음'
print(f'✅ 계측: 요약/폴백/발송실패 3경우 구분 · 길이·건수 기록')

import brief
brief_h = brief.news_push_health(1)
assert brief_h['sends'] == 3 and brief_h['send_fail'] == 1 and brief_h['fallback'] == 1, brief_h
print(f"✅ 주간 브리핑 집계: 발송 {brief_h['sends']} · 실패 {brief_h['send_fail']} · 폴백 {brief_h['fallback']}")
